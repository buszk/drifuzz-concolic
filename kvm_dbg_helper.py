#!/usr/bin/env python3
import subprocess
import time
from common import *
import argparse

from concolic import GlobalModel, CommandHandler, SocketThread, qemu_socket


parser = argparse.ArgumentParser()
parser.add_argument('target')
args = parser.parse_args()

global_module = GlobalModel()
command_handler = CommandHandler(global_module)
socket_thread = SocketThread(command_handler, qemu_socket)

socket_thread.start()

time.sleep(.1)

cmd = [qemu_path]
cmd += get_extra_args(args.target, socket=qemu_socket, prog='init')
cmd += ['-enable-kvm']
cmd += ['-hda', f'{drifuzz}/image/buster.img']
cmd += ['-snapshot']

p = subprocess.Popen(cmd)
p.wait()
socket_thread.stop()
