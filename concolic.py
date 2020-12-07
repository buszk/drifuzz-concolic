#!/usr/bin/env -S python3 -u
import os
import pty
import subprocess
import argparse
from os.path import join, exists
from copy import deepcopy
from common import *
from drifuzz_util import *
sys.path.append(join(PANDA_SRC, "panda/scripts"))
from run_guest import create_recording

parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('seed', type=str)
parser.add_argument('--gdbreplay', default=False, action="store_true")
args = parser.parse_args()

outdir=get_out_dir(args.target)
if not exists(outdir):
    os.mkdir(outdir)

def bytearray_set(bs, ind, val):
    if ind < len(bs):
        bs[ind] = val
    else:
        bs.extend(b'\x00'*(ind-len(bs)))
        bs.append(val)

def get_trim_start():
    with open('/tmp/drifuzz_index', 'r') as f:
        for line in f:
            entries = line.split(', ')
            assert(entries[5].split(' ')[0] == 'rr_count:')
            rr_count = int(entries[5].split(' ')[1], 16)
            return rr_count
    return 0

def run_concolic():
    global_module = GlobalModel()
    global_module.load_data(args.target)
    command_handler = CommandHandler(global_module, seed=args.seed)
    socket_thread = SocketThread(command_handler, qemu_socket)

    socket_thread.start()

    time.sleep(.1)
    # Record
    target = args.target
    extra_args = get_extra_args(target, socket=qemu_socket)
    create_recording(qemu_path, get_qcow(target), get_snapshot(target), \
            get_cmd(target), copy_dir, get_recording_path(target), \
            expect_prompt, cdrom, extra_args=extra_args)
    # Trim
    cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
        "-replay", get_recording_path(target),
        "-panda", f"scissors:name={get_reduced_recording_path(target)},start={get_trim_start()-1000}",
        "-pandalog", get_pandalog(target)]
    cmd += extra_args
    subprocess.check_call(cmd)

    # Replay
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

def parse_concolic():
    input2seed = {}
    orig:bytearray
    with open(args.seed, 'rb') as f:
        orig = bytearray(f.read())
    with open('/tmp/drifuzz_index', 'r') as f:
        for line in f:
            entries = line.split(', ')
            assert(entries[0].split(' ')[0] == 'input_index:')
            assert(entries[1].split(' ')[0] == 'seed_index:')
            assert(entries[2].split(' ')[0] == 'size:')
            input_index = int(entries[0].split(' ')[1], 16)
            seed_index = int(entries[1].split(' ')[1], 16)
            size = int(entries[2].split(' ')[1])
            for i in range(size):
                input2seed[input_index+i] = seed_index+i
    copy = deepcopy(orig)
    with open(join(outdir, '0'), 'wb') as o:
        o.write(orig)

    out_index = -1
    warned = False
    with open('/tmp/drifuzz_path_constraints', 'r') as f:
        for line in f:
            assert(line[-1] == '\n')
            line = line[:-1]
            if '= Z3 Path Solver End =' in line:
                # reset and export
                with open(join(outdir, str(out_index)), 'wb') as o:
                    o.write(copy)
                copy = deepcopy(orig)
            if 'Count:' in line:
                splited = line.split(' ')
                out_index = int(splited[1])
            if 'Inverted value' in line:
                splited = line.split(' ')
                assert(splited[0] == 'Inverted')
                assert(splited[1] == 'value:')
                assert(splited[2][:4] == 'val_')
                assert(splited[3] == '=')
                assert(splited[4][:2] == '#x')
                input_index = int(splited[2][4:], 16)
                new_val = int(splited[4][2:], 16)
                assert(new_val >= 0 and new_val <= 255)
                if input_index in input2seed:
                    seed_index = input2seed[input_index]
                    bytearray_set(copy, seed_index, new_val)
                elif not warned:
                    warned = True
                    print('Some input_index is not mapped to seed_index')
                    print('Maybe qemu simulated some reg')


def main():
    setup_work_dir(target=args.target)
    run_concolic()
    parse_concolic()

if __name__ == "__main__":
    main()
