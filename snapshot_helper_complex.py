#!/usr/bin/env -S python3 -u

from common import *
import subprocess
import argparse
from os.path import isfile

import time
from drifuzz_util import GlobalModel, CommandHandler, SocketThread, qemu_socket

parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('--raw', type=str)
parser.add_argument('qcow', type=str)
args = parser.parse_args()

if not isfile(args.qcow) and not isfile(args.raw):
    print(f'{args.qcow} does not exist, must provide raw img with --raw')
    import sys
    sys.exit(1)

if isfile(args.raw):
    qemu_img_path = f"{PANDA_BUILD}/qemu-img"

    cmd = [qemu_img_path]
    cmd += ['convert', '-f', 'raw', '-O', 'qcow2', args.raw, args.qcow]
    subprocess.check_call(cmd)

global_module = GlobalModel()
global_module.load_data()
command_handler = CommandHandler(global_module)
socket_thread = SocketThread(command_handler, qemu_socket)

socket_thread.start()

time.sleep(.1)
cmd = [qemu_path]
cmd += [args.qcow]
cmd += get_extra_args(args.target,socket=qemu_socket)

print(" ".join(cmd))
subprocess.check_call(cmd)

socket_thread.stop()
