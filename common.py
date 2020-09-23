
import os, sys
from tempdir import TempDir
from os.path import join, dirname, abspath


BASE_DIR = dirname(abspath(__file__))
drifuzz = abspath(join(BASE_DIR, "..", "Drifuzz"))
PANDA_SRC = abspath(join(BASE_DIR, "..", "panda"))
PANDA_BUILD = join(drifuzz, "panda-build")
qemu_path = join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64")
qcow = join(BASE_DIR, "buster.qcow2")

expect_prompt = "root@syzkaller:~#"
cdrom = "ide1-cd0"
copy_dir = join(BASE_DIR, "copy-dir")

def get_snapshot(target):
    return "{}_root".format(target)

def get_cmd(target):
    return [join(copy_dir, "prog-eth-up-down.sh"), target]

def get_recording_path(target):
    return join(BASE_DIR, target)

def get_pandalog(target):
    return join(BASE_DIR, f"{target}.plog")

common_extra_args = ['-m', '1G']
common_extra_args += ['-nographic', '-no-acpi']

def get_extra_args(target, socket='', prog=''):
    extra_args = common_extra_args
    extra_args += ["-kernel", f"{drifuzz}/linux-module-build/arch/x86_64/boot/bzImage"]
    extra_args += ["-append", f"console=ttyS0 nokaslr root=/dev/sda earlyprintk=serial net.ifnames=0 modprobe.blacklist={target}"]

    drifuzz_dev_arg = 'drifuzz'
    drifuzz_dev_arg += f',target={target}'
    if socket != '':
        drifuzz_dev_arg += f',socket={socket}'
    if prog != '':
        drifuzz_dev_arg += f',prog={prog}'
    extra_args += ['-device', drifuzz_dev_arg]

    extra_args += ['-net', 'user']
    extra_args += ['-net', f'nic,model={target}']
    return extra_args