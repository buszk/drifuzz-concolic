
import os, sys
import subprocess32 
from tempdir import TempDir
from os.path import join, dirname, abspath

target = "alx"

extra_args = ['-m', '1G']
extra_args += ["-kernel", "/home/zekun/Workspace/git/Drifuzz/linux-module-build/arch/x86_64/boot/bzImage"]
extra_args += ["-append", "console=ttyS1 nokaslr root=/dev/sda earlyprintk=serial"]
extra_args += ['-net', 'user']
extra_args += ['-net', 'nic,model={}'.format(target)]
extra_args += ['-device', 'drifuzz']

BASE_DIR = dirname(abspath(__file__))
PANDA_SRC = join(BASE_DIR, "..", "panda")
PANDA_BUILD = join(BASE_DIR, "..", "panda-build")
qemu_path = join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64")
qcow = join(BASE_DIR, "buster.qcow2")

snapshot = "{}_root".format(target)
expect_prompt = "root@syzkaller:~#"
cdrom = "ide1-cd0"
copy_dir = join(BASE_DIR, "copy-dir")
cmd = [join(copy_dir, "driver-{}.sh".format(target))]
recording_path = join(BASE_DIR, target)
pandalog = join(BASE_DIR, "{}.plog".format(target))
home=os.path.expanduser("~")
drifuzz = join(home, "Workspace/git/Drifuzz")
