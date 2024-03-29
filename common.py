
import os
import sys
import fcntl
from tempdir import TempDir
from os.path import join, dirname, abspath

RECORD_ERROR_CODE = 2
MAPPING_ERROR_CODE = 3
BASE_DIR = dirname(abspath(__file__))
DRIFUZZ = abspath(join(BASE_DIR, "..", "Drifuzz"))
PANDA_SRC = abspath(join(BASE_DIR, "..", "panda"))
LINUX_BUILD = join(DRIFUZZ, "linux-module-build")
PANDA_BUILD = join(DRIFUZZ, "panda-build")
qemu_path = join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64")

expect_prompt = "root@syzkaller:~#"
cdrom = "ide1-cd0"
copy_dir = join(BASE_DIR, "copy-dir")
work = join(dirname(abspath(__file__)), "work")
out = "out"


def is_test_target(target):
    return 'drifuzz-test' in target


def get_drifuzz_index(target):
    return join(work, target, "drifuzz_index")


def get_drifuzz_path_constraints(target):
    return join(work, target, "drifuzz_path_constraints")


def get_global_module(target):
    return join(work, target, f"{target}.sav")


def get_search_save(target):
    return join(work, target, "search.sav")


def create_if_not_exist(d):
    if not os.path.exists(d):
        os.makedirs(d)


def setup_work_dir(target=""):
    create_if_not_exist(work)
    if target != "":
        create_if_not_exist(join(work, target))
        create_if_not_exist(join(work, target, out))


def get_out_dir(target):
    return join(work, target, out)


def get_raw_img():
    return join(DRIFUZZ, 'image', 'buster.img')


def get_snapshot(target):
    return target


def get_qcow(target, id=""):
    if id:
        return join(work, target, f"{target}_{id}.qcow2")
    return join(work, target, f"{target}.qcow2")


def get_cmd(target):
    if is_test_target(target):
        target = 'drifuzz-test'
        return [join(copy_dir, "prog-modprobe.sh"), target]
    return [join(copy_dir, "prog-init.sh"), target]


def get_recording_path(target):
    return join(BASE_DIR, work, target, target)


def get_reduced_recording_path(target):
    return join(BASE_DIR, work, target, f"{target}_reduced")


def get_pandalog(target):
    return join(BASE_DIR, work, target, f"{target}.plog")


common_extra_args = ['-m', '512M']
common_extra_args += ['-nographic', '-no-acpi']


def get_extra_args(target, socket='', prog='', tempdir='', usb=False):
    orig = target
    if is_test_target(target):
        target = 'drifuzz-test'

    extra_args = common_extra_args
    extra_args += ["-kernel",
                   f"{DRIFUZZ}/linux-module-build/arch/x86_64/boot/bzImage"]
    extra_args += ["-append",
                   f"console=ttyS0 nokaslr root=/dev/sda earlyprintk=serial net.ifnames=0 modprobe.blacklist=e1000,{target}"]

    drifuzz_dev_arg = 'drifuzz'
    drifuzz_dev_arg += f',target={target}'
    if socket != '':
        drifuzz_dev_arg += f',socket={socket}'
    if prog != '':
        drifuzz_dev_arg += f',prog={prog}'
    if tempdir == '':
        drifuzz_dev_arg += f',tmpdir={join(work, orig)}'
    else:
        drifuzz_dev_arg += f',tmpdir={tempdir}'

    extra_args += ['-device', drifuzz_dev_arg]

    if not usb:
        # PCI Device
        extra_args += ['-net', 'user']
        if target != 'drifuzz-test':
            extra_args += ['-net', f'nic,model={target}']
        else:
            extra_args += ['-net', f'nic,model={orig}']
    else:
        # USB Device
        extra_args += ['-usb']
        extra_args += ['-device', 'qemu-xhci,id=xhci']

        extra_args += ['-device', target]
        extra_args += ['-usbDescFile', '/dev/urandom',  # '/home/zekun/Workspace/git/USBFuzz/seeds/usb_s2a2s6m',
                       '-usbDataFile', '/dev/urandom']

    return extra_args


class Locker:
    def __enter__(self):
        self.fp = open("./lockfile.lck")
        fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX)

    def __exit__(self, _type, value, tb):
        fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
        self.fp.close()
