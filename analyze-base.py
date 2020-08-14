import os, sys
import subprocess32
from tempdir import TempDir
from os.path import join, dirname, abspath
BASE_DIR = dirname(abspath(__file__))
PANDA_SRC = join(BASE_DIR, "..", "panda")
PANDA_BUILD = join(BASE_DIR, "..", "panda-build")
sys.path.append(join(PANDA_SRC, "panda/scripts"))
from run_guest import create_recording
from plog_reader import PLogReader


qemu_path = join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64")
qcow = join(BASE_DIR, "buster.qcow2")
snapshot = "root"
expect_prompt = "root@syzkaller:~#"
cdrom = "ide1-cd0"
copy_dir = join(BASE_DIR, "copy-dir")
cmd = [join(copy_dir, "driver.sh")]
recording_path = join(BASE_DIR, "e1000")
extra_args = ['-m', '1G']
pandalog = join(BASE_DIR, "e1000-base.plog")


with PLogReader(pandalog) as plr:
    for m in plr:
        print hex(m.pc)


