
import os, sys
import subprocess32 
from tempdir import TempDir
from os.path import join, dirname, abspath


BASE_DIR = dirname(abspath(__file__))
PANDA_SRC = join(BASE_DIR, "..", "panda")
PANDA_BUILD = join(BASE_DIR, "..", "panda-build")
qemu_path = join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64")
qcow = join(BASE_DIR, "buster.qcow2")

expect_prompt = "root@syzkaller:~#"
cdrom = "ide1-cd0"
copy_dir = join(BASE_DIR, "copy-dir")
home=os.path.expanduser("~")
drifuzz = join(home, "Workspace/git/Drifuzz")

def get_snapshot(target):
    return "{}_root".format(target)

def get_cmd(target):
    return [join(copy_dir, "driver-{}.sh".format(target))]

def get_recording_path(target):
    return join(BASE_DIR, target)

def get_pandalog(target):
    return join(BASE_DIR, "{}.plog".format(target))

common_extra_args = ['-m', '1G']
common_extra_args += ["-kernel", "/home/zekun/Workspace/git/Drifuzz/linux-module-build/arch/x86_64/boot/bzImage"]
common_extra_args += ["-append", "console=ttyS1 nokaslr root=/dev/sda earlyprintk=serial"]

def get_extra_args(target):
    extra_args = common_extra_args
    extra_args += ['-net', 'user']
    extra_args += ['-net', 'nic,model={}'.format(target)]
    extra_args += ['-device', 'drifuzz']
    return extra_args

def get_extra_args_with_socket(target, socket):
    extra_args = common_extra_args
    extra_args += ['-net', 'user']
    extra_args += ['-net', 'nic,model={}'.format(target)]
    extra_args += ['-device', 'drifuzz,socket={}'.format(socket)]
    return extra_args

