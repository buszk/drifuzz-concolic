#!/usr/bin/env python3

import tempfile
from pexpect import fdpexpect
import socket
import time
import json
import sys
from common import *
import subprocess
import argparse
from os.path import isfile
from common import get_raw_img, get_qcow


parser = argparse.ArgumentParser()
parser.add_argument('--dryrun', default=False, action='store_true')
parser.add_argument('--usb', default=False, action='store_true')
parser.add_argument('target', type=str)
args = parser.parse_args()

setup_work_dir(target=args.target)

# Remove qcow if exists
if not args.dryrun and isfile(get_qcow(args.target)):
    os.remove(get_qcow(args.target))

# Create qcow
qemu_img_path = f"{PANDA_BUILD}/qemu-img"

cmd = [qemu_img_path]
cmd += ['convert', '-f', 'raw', '-O', 'qcow2',
        get_raw_img(), get_qcow(args.target)]

if args.dryrun:
    print(cmd)
else:
    subprocess.check_call(cmd)

# Start qemu to obtain snapshot
cmd = [get_qcow(args.target)]
cmd += get_extra_args(args.target, usb=args.usb)

print(" ".join([qemu_path] + cmd))

if args.dryrun:
    sys.exit()

serial_socket_f = tempfile.NamedTemporaryFile().name
monitor_socket_f = tempfile.NamedTemporaryFile().name
cmd.append('-serial')
cmd.append(f'unix:{serial_socket_f},server,nowait')
cmd.append('-monitor')
cmd.append(f'unix:{monitor_socket_f},server,nowait')
cmd = [qemu_path] + cmd
print(" ".join(cmd))
p = subprocess.Popen(cmd)
time.sleep(1)  # Wait for socket server to be initialized
serial_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
serial_sock.connect(serial_socket_f)
serial_session = fdpexpect.fdspawn(serial_sock.fileno(), timeout=10)
serial_session.logfile = sys.stderr.buffer
# Login
serial_session.expect('syzkaller login: ', timeout=600)
print("Login prompt")
serial_session.sendline('root')
serial_session.expect('root@syzkaller:~# ')
print("Logged in")
# Remove e1000 if exist
if args.usb:
    serial_session.sendline('rmmod e1000')
    serial_session.expect('root@syzkaller:~# ')
# Load dependent kernels
serial_session.sendline(
    f'modprobe -v -n {args.target} |sed \$d > load_dep_module.sh')
serial_session.expect('root@syzkaller:~# ')
serial_session.sendline('bash load_dep_module.sh')
serial_session.expect('root@syzkaller:~# ')
serial_session.sendline('cat /proc/modules')
serial_session.expect('root@syzkaller:~# ')

# Collect module addresses for addr2line.py
config = {}
for line in serial_session.before.decode('utf-8').split('\n'):
    if not 'Live 0x' in line:
        continue
    mod = line.split(' ')[0]
    if mod in config:
        break
    size = int(line.split(' ')[1])
    addr = int(line.split(' ')[5], 16)
    config[mod] = [addr, size]
addr_sav = join(work, args.target, 'modaddr.sav')
with open(addr_sav, 'w+') as f:
    json.dump(config, f)

monitor_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
monitor_sock.connect(monitor_socket_f)
monitor_session = fdpexpect.fdspawn(monitor_sock.fileno(), timeout=10)
monitor_session.logfile = sys.stderr.buffer
monitor_session.expect('(qemu)')
monitor_session.sendline(f'savevm {args.target}')
monitor_session.expect('(qemu)')
monitor_session.sendline('quit')
p.wait()
print("")
print("done")
if not config:
    print("WARNING: module address parsing failed.")
    print("  addr2line.py scirpt probably won't work")
