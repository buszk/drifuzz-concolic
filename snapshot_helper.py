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
cmd = [get_qcow(args.target)]
cmd += get_extra_args(args.target)

print(" ".join([qemu_path] + cmd))

import sys
import pexpect
p = pexpect.spawn(qemu_path, cmd)
p.logfile = sys.stderr.buffer
p.expect('syzkaller login: ', timeout=600)
p.sendline('root')
p.expect('root@syzkaller:~# ')
# Ctrl-A+C to open qemu console
p.send('\001c')
p.expect('(qemu)')
# Save snapshot
p.sendline(f'savevm {args.target}')
# Wait for saving to finish
p.expect('(qemu)')
# Ctrl-A+X to quit
p.send('\001x')
print("")
print("done")
