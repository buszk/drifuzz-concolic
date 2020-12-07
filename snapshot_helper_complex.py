#!/usr/bin/env -S python3 -u

from common import *
import subprocess
import argparse
from os.path import isfile
from common import get_raw_img, get_qcow

import time
from drifuzz_util import GlobalModel, CommandHandler, SocketThread, qemu_socket

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

# Setup drifuzz model
global_module = GlobalModel()
global_module.load_data()
command_handler = CommandHandler(global_module)
socket_thread = SocketThread(command_handler, qemu_socket)

socket_thread.start()

# Start qemu to obtain snapshot
time.sleep(.1)
cmd = [qemu_path]
cmd += [get_qcow(args.target)]
cmd += get_extra_args(args.target,socket=qemu_socket)

print(" ".join(cmd))
subprocess.check_call(cmd)

socket_thread.stop()
