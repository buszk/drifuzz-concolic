#!/usr/bin/env python3
import pty
import subprocess
from drifuzz_util import *
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('target', type=str)
parser.add_argument('seed', type=str)
parser.add_argument('out', type=str)
args = parser.parse_args()

def run_concolic():
    global_module = GlobalModel()
    command_handler = CommandHandler(global_module, seed=args.seed)
    socket_thread = SocketThread(command_handler, qemu_socket)

    socket_thread.start()

    time.sleep(.1)

    cmd = ["python3", "./analyze.py",
            "--record", "--replay",
            "--target", args.target,
            "--socket", qemu_socket]
    
    p = subprocess.Popen(cmd, env=os.environ)
    p.wait()

    socket_thread.stop()

def parse_concolic():
    pass

def main():
    run_concolic()
    parse_concolic()

if __name__ == "__main__":
    main()
