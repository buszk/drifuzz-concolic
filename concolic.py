#!/usr/bin/env -S python3 -u
import os
import sys
import subprocess
import argparse
import tempfile
from multiprocessing import Process
from os.path import join, exists
from common import *
from result import *
from drifuzz_util import *
sys.path.append(join(PANDA_SRC, "panda/scripts"))
from run_guest import create_recording

import pdb, traceback, signal
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
args = parser.parse_args()

outdir=get_out_dir(args.target)
if args.outdir:
    outdir = args.outdir
if not exists(outdir):
    os.mkdir(outdir)

tempdirname = ""
if args.tempdir:
    td = tempfile.TemporaryDirectory()
    tempdirname = td.name

def __get_drifuzz_index():
    if args.tempdir and tempdirname:
        return join(tempdirname, 'drifuzz_index')
    else:
        return get_drifuzz_index(args.target)
def __get_drifuzz_path_constraints():
    if args.tempdir and tempdirname:
        return join(tempdirname, 'drifuzz_path_constraints')
    else:
        return get_drifuzz_path_constraints(args.target)

def get_trim_start():
    with open(__get_drifuzz_index(), 'r') as f:
        for line in f:
            entries = line.split(', ')
            assert(entries[5].split(' ')[0] == 'rr_count:')
            rr_count = int(entries[5].split(' ')[1], 16)
            return rr_count
    return 0

def form_jcc_mod_optiom():
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

def run_concolic(do_record=True, do_trim= True, do_replay=True):

    ret = 0
    trim_failed = False
    socket_file = ""
    tf = None
    socket_thread = None
    global_module = None
    if args.socket:
        socket_file = args.socket
    else:
        global_module = GlobalModel()
        global_module.load_data(args.target)
        command_handler = CommandHandler(global_module, seed=args.seed)
        tf = tempfile.NamedTemporaryFile()
        socket_thread = SocketThread(command_handler, tf.name)
        socket_thread.start()
        socket_file = tf.name

    time.sleep(.1)
    target = args.target
    if args.tempdir:
        extra_args = get_extra_args(target, socket=socket_file, tempdir=tempdirname)
    else:
        extra_args = get_extra_args(target, socket=socket_file)
    extra_args += form_jcc_mod_optiom()

    trim_failed = True
    # Record
    if do_record:
        try:
            p = Process(target = create_recording,
                            args = (qemu_path, get_qcow(args.target, id=args.id), get_snapshot(target),
                                get_cmd(target), copy_dir, get_recording_path(target), expect_prompt, cdrom,
                                ),
                            kwargs= {'extra_args':extra_args})
            # create_recording(qemu_path, get_qcow(args.target,id=args.id), get_snapshot(target), \
            #         get_cmd(target), copy_dir, get_recording_path(target), \
            #         expect_prompt, cdrom, extra_args=extra_args)
            p.start()
            MAX_RECORD_SECONDS = 30
            for i in range(MAX_RECORD_SECONDS):
                p.join(timeout=1)
                # Process finished
                if p.exitcode != None:
                    break
                print(f"[{i}] join failed")
                if i == MAX_RECORD_SECONDS - 1:
                    p.kill()
                    raise TimeoutError()
        except:
            if socket_thread:
                global_module.save_data(args.target)
                socket_thread.stop()
            print('PANDA record failed!')
            return 1

        # Sanity check?
        mmio_count = len(open(__get_drifuzz_index()).readlines())
        if (mmio_count > 10000 and args.target_branch_pc == 0) or \
            (mmio_count > 200000):
            print(f"There is way too many mmio ({mmio_count}) in the exeuction. Terminate")
            if socket_thread:
                socket_thread.stop()
            return 1

        # Trim
        if do_trim:
            cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
                "-replay", get_recording_path(target),
                "-panda", f"scissors:name={get_reduced_recording_path(target)},start={get_trim_start()-1000}",
                "-pandalog", get_pandalog(target)]
            cmd += extra_args
            p = subprocess.Popen(cmd)
            p.wait()
            if p.returncode != 0:
                # global_module.save_data(args.target)
                # socket_thread.stop()
                print('PANDA Trim failed!')
                trim_failed = True
                # return 1
            else:
                trim_failed = False
        else:
            trim_failed = True
            
    # Replay
    if do_replay:
        env={
            "LD_PRELOAD":"/home/zekun/bpf/install/lib/libz3.so",
            **os.environ
        }
        record_path = get_recording_path(target) if trim_failed else get_reduced_recording_path(target)
        cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
            "-replay", record_path,
            "-panda", f"tainted_drifuzz:target_branch_pc={args.target_branch_pc},after_target_limit={args.after_target_limit}",
            "-panda", "tainted_branch",
            #"-d", "in_asm",
            #"-d", "in_asm,op,llvm_ir",
            #"-dfilter", "0xffffffffa0128000..0xffffffffffffffff",
            "-pandalog", get_pandalog(target)]
        cmd += extra_args

        if args.pincpu:
            import multiprocessing
            cpu_count = os.cpu_count()
            cmd = ["taskset", "-c", args.pincpu] + cmd

        if args.gdbreplay:
            cmd = ["gdb", "-ex", "r", "--args"] + cmd

        print(" ".join(cmd))
        p = subprocess.Popen(cmd, env=env)
        p.wait()
        if p.returncode != 0:
            if socket_thread:
                global_module.save_data(args.target)
                socket_thread.stop()
            print(f'PANDA replay failed! exitcode={p.returncode}')
            ret = 1


    if socket_thread:
        global_module.save_data(args.target)
        tf.close()
        print("Stopping thread")
        socket_thread.stop()
        print("Thread stopped")
    return ret

def parse_concolic():
    CR_result = ConcolicResult(
                    __get_drifuzz_path_constraints(),
                    __get_drifuzz_index())
    jcc_mod_pc = {}
    for pc in args.ones:
        jcc_mod_pc[int(pc, 16)] = 1
    for pc in args.zeros:
        jcc_mod_pc[int(pc, 16)] = 0

    CR_result.set_jcc_mod(jcc_mod_pc)
    jcc_ok = CR_result.is_jcc_mod_ok()
    CR_result.generate_inverted_input(args.seed, outdir)
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
    if rp and ret:
        print(f"Concolic run/replay failed with status {ret}")
        return ret
    if ps and parse_concolic() == False:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
