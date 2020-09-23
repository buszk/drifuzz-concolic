#!/usr/bin/env python3

from common import *
import subprocess
import argparse
from os.path import isfile


parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('--raw', type=str)
parser.add_argument('qcow', type=str)
args = parser.parse_args()

if not isfile(args.qcow) and not isfile(args.raw):
    print(f'{args.qcow} does not exist, must provide raw img with --raw')
    import sys
    sys.exit(1)

if not isfile(args.qcow):
    qemu_img_path = f"{PANDA_BUILD}/qemu-img"

    cmd = [qemu_img_path]
    cmd += ['convert', '-f', 'raw', '-O', 'qcow2', args.raw, args.qcow]
    subprocess.check_call(cmd)

cmd = [qemu_path]
cmd += [args.qcow]
cmd += get_extra_args(args.target)

print(" ".join(cmd))
subprocess.check_call(cmd)