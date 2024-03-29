#!/usr/bin/env -S python3 -u
import signal
import traceback
import pdb
import os
import sys
import subprocess
import argparse
import tempfile
from ast import literal_eval
from multiprocessing import Process
from os.path import join, exists
from common import *
from result import *
from drifuzz_util import *
sys.path.append(join(PANDA_SRC, "panda/scripts"))  # nopep8
from run_guest import create_recording  # nopep8


def handler(signum, frame):
    for th in threading.enumerate():
        print(th)
        traceback.print_stack(sys._current_frames()[th.ident])
        print()


signal.signal(signal.SIGUSR1, handler)

parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('seed', type=str)
parser.add_argument('--target_branch_pc', type=str, default='0')
parser.add_argument('--after_target_limit', type=str, default='10000')
parser.add_argument('--gdbreplay', default=False, action="store_true")
parser.add_argument('--debugreplay', default=False, action="store_true")
parser.add_argument('--recordonly', default=False, action="store_true")
parser.add_argument('--notrim', default=False, action="store_true")
parser.add_argument('--pincpu', type=str, default='')
parser.add_argument('--ones', nargs='+', type=str, default=[])
parser.add_argument('--zeros', nargs='+', type=str, default=[])
parser.add_argument('--others', nargs='+', type=str, default=[])
parser.add_argument('--outdir', type=str, default="")
parser.add_argument('--socket', type=str, default="")
parser.add_argument('--tempdir', default=False, action="store_true")
parser.add_argument('--id', default="", type=str)
parser.add_argument('--fixer_config', default="", type=str)
parser.add_argument('--noflip', default=False, action="store_true")
parser.add_argument('--usb', default=False, action="store_true")
parser.add_argument('--notest', default=False, action="store_true")
parser.add_argument('--forcesave', default=False, action="store_true")
args = parser.parse_args()

outdir = get_out_dir(args.target)
if args.outdir:
    outdir = args.outdir
if not exists(outdir):
    os.mkdir(outdir)

tempdirname = ""
if args.tempdir:
    td = tempfile.TemporaryDirectory()
    tempdirname = td.name


fixer = None
fixer_config: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
if args.fixer_config:
    json_dict = json.loads(args.fixer_config)
    fixer_config = {literal_eval(k): [literal_eval(x) for x in v] for k, v in json_dict.items()}
    print(fixer_config)
    fixer = Fixer(fixer_config)


def drifuzz_index_file():
    if args.tempdir and tempdirname:
        return join(tempdirname, 'drifuzz_index')
    else:
        return get_drifuzz_index(args.target)


def drifuzz_path_constraints_file():
    if args.tempdir and tempdirname:
        return join(tempdirname, 'drifuzz_path_constraints')
    else:
        return get_drifuzz_path_constraints(args.target)


def get_trim_start():
    with open(drifuzz_index_file(), 'r') as f:
        for line in f:
            entries = line.split(', ')
            assert(entries[5].split(' ')[0] == 'rr_count:')
            rr_count = int(entries[5].split(' ')[1], 16)
            return rr_count
    return 0


def form_jcc_mod_option():
    jcc_mod_str = 'jcc_mod:'
    for e in args.zeros:
        if e[0:2] == '0x':
            e = e[2:]
        jcc_mod_str += f"0x{e}=0,"
    for e in args.ones:
        if e[0:2] == '0x':
            e = e[2:]
        jcc_mod_str += f"0x{e}=1,"
    for e in args.others:
        if e[0:2] == '0x':
            e = e[2:]
        jcc_mod_str += f"0x{e}=2,"
    print(jcc_mod_str)
    if jcc_mod_str != 'jcc_mod:':
        jcc_mod_str = jcc_mod_str[:-1]
        return ['-panda', jcc_mod_str]
    return []


def record_command(target, extra_args, cmd, max_time_seconds):
    with Locker():
        p = Process(target=create_recording,
                    args=(qemu_path, get_qcow(args.target, id=args.id), get_snapshot(target),
                          cmd, copy_dir, get_recording_path(
                        target), expect_prompt, cdrom,
                    ),
                    kwargs={
                        'extra_args': extra_args,
                        'timeout': 5 if args.usb else 1200
                    })

        p.start()
        for i in range(max_time_seconds):
            p.join(timeout=1)
            # Process finished
            if p.exitcode != None:
                break
            if i == max_time_seconds - 1:
                p.kill()
                return False
        return True


def run_concolic(do_record=True, do_trim=True, do_replay=True):

    ret = 0
    socket_file = ""
    tf = None
    socket_thread = None
    global_model = None
    if args.socket:
        socket_file = args.socket
    else:
        global_model = GlobalModel(forcesave=args.forcesave)
        global_model.load_data(args.target)
        command_handler = CommandHandler(
            global_model, seed=args.seed, fixer=fixer, usb=args.usb)
        tf = tempfile.NamedTemporaryFile()
        socket_thread = SocketThread(command_handler, tf.name)
        socket_thread.start()
        socket_file = tf.name

    time.sleep(.1)
    target = args.target
    if args.tempdir:
        extra_args = get_extra_args(
            target, socket=socket_file, tempdir=tempdirname, usb=args.usb)
    else:
        extra_args = get_extra_args(target, socket=socket_file, usb=args.usb)
    extra_args += form_jcc_mod_option()

    trim_succeed = False
    # Record
    if do_record:

        if not args.notest and not record_command(target, extra_args, ["ls"], 10):
            print("Even ls command timeout, recreate snapshot and try again")
            create_snapshot_cmd = [
                "python3", "-u", f"{dirname(__file__)}/snapshot_helper.py", target]
            if args.usb:
                create_snapshot_cmd += ['--usb']
            subprocess.Popen(create_snapshot_cmd).wait()
            assert record_command(target, extra_args, ["ls"], 10)
        try:
            # Regard record as hang if exceed MAX_RECORD_SECONDS
            MAX_RECORD_SECONDS = 20
            if not record_command(target, extra_args, get_cmd(target), MAX_RECORD_SECONDS):
                print('PANDA record timedout!')
                raise TimeoutError()
        except:
            if socket_thread:
                global_model.save_data(args.target)
                socket_thread.stop()
            print('PANDA record failed!')
            return RECORD_ERROR_CODE

        # Sanity check?
        if not os.path.exists(drifuzz_index_file()):
            print('PANDA record did not generate any I/O trace')
            print(f'Check if memory mapping is correct for {args.target}')
            if socket_thread:
                global_model.save_data(args.target)
                socket_thread.stop()
            return MAPPING_ERROR_CODE

        mmio_count = len(open(drifuzz_index_file()).readlines())
        if mmio_count > 100000:
            print(
                f"There is way too many mmio ({mmio_count}) in the exeuction. Terminate")
            if socket_thread:
                socket_thread.stop()
            return 1

        # Trim
        if do_trim and not args.usb:
            cmd = [join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
                   "-replay", get_recording_path(target),
                   "-panda", f"scissors:name={get_reduced_recording_path(target)},start={get_trim_start()-1000}",
                   "-pandalog", get_pandalog(target)]
            cmd += extra_args
            p = subprocess.Popen(cmd)
            p.wait()
            if p.returncode == 0:
                trim_succeed = True
            else:
                # global_model.save_data(args.target)
                # socket_thread.stop()
                print('PANDA Trim failed!')
                # return 1

    # Replay
    if do_replay:
        record_path = get_reduced_recording_path(
            target) if trim_succeed else get_recording_path(target)
        cmd = [join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
               "-replay", record_path,
               "-panda", f"tainted_drifuzz:target_branch_pc={args.target_branch_pc},after_target_limit={args.after_target_limit}",
               "-panda", "tainted_branch",
               # "-d", "in_asm",
               # "-d", "in_asm,op,llvm_ir",
               # "-dfilter", "0xffffffffa0000000..0xffffffffffffffff",
               "-pandalog", get_pandalog(target)]
        cmd += extra_args

        if args.pincpu:
            import multiprocessing
            cpu_count = os.cpu_count()
            cmd = ["taskset", "-c", args.pincpu] + cmd

        if args.gdbreplay:
            cmd = ["gdb", "-ex", "r", "--args"] + cmd

        print(" ".join(cmd))
        p = subprocess.Popen(cmd)
        p.wait()
        if p.returncode != 0:
            if socket_thread:
                global_model.save_data(args.target)
                socket_thread.stop()
            print(f'PANDA replay failed! exitcode={p.returncode}')
            ret = 1

    if socket_thread:
        global_model.save_data(args.target)
        tf.close()
        print("Stopping thread")
        socket_thread.stop()
        print("Thread stopped")
    return ret


def parse_concolic():
    CR_result = ConcolicResult(
        drifuzz_path_constraints_file(),
        drifuzz_index_file(),
        fixer=fixer_config)
    jcc_mod_pc = {}
    for pc in args.ones:
        jcc_mod_pc[int(pc, 16)] = 1
    for pc in args.zeros:
        jcc_mod_pc[int(pc, 16)] = 0

    CR_result.set_jcc_mod(jcc_mod_pc)
    if args.noflip:
        CR_result.generate_base_input(args.seed, outdir)
    else:
        CR_result.generate_inverted_input(args.seed, outdir)
    jcc_ok = CR_result.is_jcc_mod_ok()
    return jcc_ok


def parse_arguments():
    # record, trim, replay, parse
    if args.debugreplay:
        return False, True, True, False
    elif args.recordonly:
        return True, False, False, False
    elif args.notrim:
        return True, False, True, False
    else:
        return True, True, True, True


def main():
    setup_work_dir(target=args.target)
    rc, tm, rp, ps = parse_arguments()
    ret = run_concolic(do_record=rc, do_trim=tm, do_replay=rp)
    if rp and ret in [RECORD_ERROR_CODE, MAPPING_ERROR_CODE]:
        print(f"Concolic run/replay failed with status {ret}")
        return ret
    if ps and parse_concolic() == False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
