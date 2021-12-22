#!/usr/bin/env python3

import os
import json
import argparse
import binascii
import subprocess
from common import get_search_save, get_out_dir, get_drifuzz_index, get_drifuzz_path_constraints
from result import ConcolicResult

parser = argparse.ArgumentParser()
parser.add_argument("target")
args = parser.parse_args()
target = args.target

def remove_if_exits(fname):
    if os.path.exists(fname):
        os.remove(fname)

with open(get_search_save(target),
            'r') as infile:
    dump = json.load(infile)
    cur_input = binascii.unhexlify(dump['cur_input'].encode('ascii'))

    with open(f"{get_out_dir(args.target)}/0", 'wb') as f:
        f.write(cur_input)


remove_if_exits(get_drifuzz_index(args.target))
remove_if_exits(get_drifuzz_path_constraints(args.target))

cmd = ['./concolic.py', target, f"{get_out_dir(args.target)}/0"]
cmd += ['--noflip']
cmd += ['--notest']
cmd += ['--forcesave']
print(' '.join(cmd))
p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
p.wait()
result = ConcolicResult(
        get_drifuzz_path_constraints(args.target),
        get_drifuzz_index(args.target),
        noflip=True,
        outdir=get_out_dir(args.target))

print("="*40)
print(f"Feasible: {len(result.conflicting_bytes)==0}")
print(f"Number of total concolic branches: {result.num_concolic_branch()}")
print(f"Number of unique concolic branches: {len(result.symbolic_branches_ips())}")

print("Concolic branches: {}")
for ip in result.symbolic_branches_ips():
    print(hex(ip))
