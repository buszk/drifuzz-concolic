#!/usr/bin/env python3

from common import *
import subprocess
import argparse
from os.path import isfile
from common import get_raw_img, get_qcow


parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
args = parser.parse_args()

setup_work_dir(target=args.target)

# Remove qcow if exists
if isfile(get_qcow(args.target)):
    os.remove(get_qcow(args.target))

# Create qcow
qemu_img_path = f"{PANDA_BUILD}/qemu-img"

cmd = [qemu_img_path]
cmd += ['convert', '-f', 'raw', '-O', 'qcow2', get_raw_img(), get_qcow(args.target)]
subprocess.check_call(cmd)

# Start qemu to obtain snapshot
cmd = [qemu_path]
cmd += [get_qcow(args.target)]
cmd += get_extra_args(args.target)

print(" ".join(cmd))
subprocess.check_call(cmd)
