#!/usr/bin/env -S python3 -u
import os
import pty
import subprocess
from drifuzz_util import *
import argparse
from os.path import join, exists

parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('seed', type=str)
parser.add_argument('out', type=str)
args = parser.parse_args()

if not exists(args.out):
    os.mkdir(args.out)

def bytearray_set(bs, ind, val):
    if ind < len(bs):
        bs[ind] = val
    else:
        bs.extend(b'\x00'*(ind-len(bs)))
        bs.append(val)


def run_concolic():
    global_module = GlobalModel()
    global_module.load_data()
    command_handler = CommandHandler(global_module, seed=args.seed)
    socket_thread = SocketThread(command_handler, qemu_socket)

    socket_thread.start()

    time.sleep(.1)

    cmd = ["python3", "./analyze.py",
            "--record",
            "--replay",
            "--target", args.target,
            "--socket", qemu_socket]
    
    p = subprocess.Popen(cmd, env=os.environ)
    p.wait()
    global_module.save_data()

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
    copy = orig
    with open(join(args.out, '0'), 'wb') as o:
        o.write(orig)

    out_index = -1
    warned = False
    with open('/tmp/drifuzz_path_constraints', 'r') as f:
        for line in f:
            assert(line[-1] == '\n')
            line = line[:-1]
            if '= Z3 Path Solver End =' in line:
                # reset and export
                with open(join(args.out, str(out_index)), 'wb') as o:
                    o.write(copy)
                copy = orig
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
    run_concolic()
    parse_concolic()

if __name__ == "__main__":
    main()
