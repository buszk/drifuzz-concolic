#!/usr/bin/env python3
import pty
import subprocess
from drifuzz_util import *

class Panda:
    def __init__(self):
        self.cmd = ["python3", "./analyze.py",
            "--record", "--replay",
            "--target", "alx",
            "--socket", qemu_socket]

    def run(self):
        subprocess.check_call(["which", "python3"])
        print(" ".join(self.cmd))
        master, slave = pty.openpty()
        self.process = subprocess.Popen(self.cmd,
                                        stdin=slave,
                                        stdout=None,
                                        stderr=None,
                                        env=os.environ)
        self.process.wait()

def concolic_record():
    global_module = GlobalModel()
    command_handler = CommandHandler(global_module)
    socket_thread = SocketThread(command_handler, qemu_socket)

    socket_thread.start()

    time.sleep(.1)

    panda = Panda()
    panda.run()
    socket_thread.stop()

def main():
    concolic_record()


if __name__ == "__main__":
    main()
