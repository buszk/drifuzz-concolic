#!/usr/bin/env -S python3 -u
import os
import sys
import subprocess
import argparse
from os.path import join, exists
from common import *
from result import *
from drifuzz_util import *
sys.path.append(join(PANDA_SRC, "panda/scripts"))
from run_guest import create_recording

parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('seed', type=str)
parser.add_argument('--gdbreplay', default=False, action="store_true")
parser.add_argument('--debugreplay', default=False, action="store_true")
parser.add_argument('--ones', nargs='+', type=str, default=[])
parser.add_argument('--zeros', nargs='+', type=str, default=[])
args = parser.parse_args()

outdir=get_out_dir(args.target)
if not exists(outdir):
    os.mkdir(outdir)

def get_trim_start():
    with open(get_drifuzz_index(args.target), 'r') as f:
        for line in f:
            entries = line.split(', ')
            assert(entries[5].split(' ')[0] == 'rr_count:')
            rr_count = int(entries[5].split(' ')[1], 16)
            return rr_count
    return 0

def run_concolic(do_record=True, do_replay=True):
    global_module = GlobalModel()
    global_module.load_data(args.target)
    command_handler = CommandHandler(global_module, seed=args.seed)
    socket_thread = SocketThread(command_handler, qemu_socket)

    socket_thread.start()

    time.sleep(.1)
    target = args.target
    extra_args = get_extra_args(target, socket=qemu_socket)
    
    jcc_mod_str = 'jcc_mod:'
    for e in args.zeros:
        if e[0:2] == '0x':
            e = e[2:]
        jcc_mod_str += f"0x{e}=0,"
    for e in args.ones:
        if e[0:2] == '0x':
            e = e[2:]
        jcc_mod_str += f"0x{e}=1,"
    if jcc_mod_str != 'jcc_mod:':
        jcc_mod_str = jcc_mod_str[:-1]
        extra_args += ['-panda', jcc_mod_str]
    print(jcc_mod_str)

    # Record
    if do_record:
        create_recording(qemu_path, get_qcow(target), get_snapshot(target), \
                get_cmd(target), copy_dir, get_recording_path(target), \
                expect_prompt, cdrom, extra_args=extra_args)

        # Sanity check?
        mmio_count = len(open(get_drifuzz_index(args.target)).readlines())
        if mmio_count > 10000:
            print("There is way too many mmio in the exeuction. Terminate")
            socket_thread.stop()
            return 1

        # Trim
        cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
            "-replay", get_recording_path(target),
            "-panda", f"scissors:name={get_reduced_recording_path(target)},start={get_trim_start()-1000}",
            "-pandalog", get_pandalog(target)]
        cmd += extra_args
        subprocess.check_call(cmd)

    # Replay
    if do_replay:
        env={
            "LD_PRELOAD":"/home/zekun/bpf/install/lib/libz3.so",
            **os.environ
        }
        cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
            "-replay", get_reduced_recording_path(target),
            "-panda", "tainted_drifuzz",
            "-panda", "tainted_branch",
            #"-d", "in_asm",
            #"-d", "in_asm,op,llvm_ir",
            #"-dfilter", "0xffffffffa0128000..0xffffffffffffffff",
            "-pandalog", get_pandalog(target)]
        cmd += extra_args

        if args.gdbreplay:
            cmd = ["gdb", "-ex", "r", "--args"] + cmd
        print(" ".join(cmd))
        subprocess.check_call(cmd, env=env)

    global_module.save_data(args.target)

    socket_thread.stop()
    return 0

def parse_concolic():
    CR_result = ConcolicResult(
                    get_drifuzz_path_constraints(args.target),
                    get_drifuzz_index(args.target))
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
    if args.debugreplay:
        return False, True
    else:
        return True, True

def main():
    setup_work_dir(target=args.target)
    rc, rp = parse_arguments()
    if run_concolic(do_record=rc, do_replay=rp):
        return 2
    if parse_concolic() == False:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
