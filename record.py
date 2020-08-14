#!/usr/bin/env python2
import os, sys
import subprocess32
from tempdir import TempDir
from os.path import join, dirname, abspath
from common import *
sys.path.append(join(PANDA_SRC, "panda/scripts"))
from run_guest import create_recording

create_recording(qemu_path, qcow, snapshot, cmd, \
        copy_dir, recording_path, expect_prompt, cdrom, \
        extra_args=extra_args)
