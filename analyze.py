#!/usr/bin/env python2
import os, sys
import subprocess32 
from tempdir import TempDir
from os.path import join, dirname, abspath
from common import *
sys.path.append(join(PANDA_SRC, "panda/scripts"))
from run_guest import create_recording
from plog_reader import PLogReader
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--record', default=False, action="store_true")
parser.add_argument('--replay', default=False, action="store_true")
parser.add_argument('--process', default=False, action="store_true")
parser.add_argument('--all', default=False, action="store_true")
args = parser.parse_args()

if not (args.record or args.replay or args.process or args.all):
    print "Set an argument"
    sys.exit(1)

if args.record or args.all:
    create_recording(qemu_path, qcow, snapshot, cmd, \
            copy_dir, recording_path, expect_prompt, cdrom, \
            extra_args=extra_args)

if args.replay or args.all:
    cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
        "-replay", target,
        #"-panda", "callstack_instr",
        #"-panda", "tainted_dma",
        "-panda", "tainted_mmio",
        #"-panda", "tainted_instr",
        "-panda", "tainted_branch",
        "-pandalog", pandalog]
    cmd += extra_args
    print " ".join(cmd)
    subprocess32.check_call(cmd)

if args.process or args.all:
    tbms = []
    with PLogReader(pandalog) as plr:
        for m in plr:
            if m.tainted_branch:
                tb = m.tainted_branch
                if tb.taint_query:
                    tcn = tb.taint_query[0].tcn
                    tbms.append(m)
            if m.tainted_instr:
                pass
                #print hex(m.pc)
                #print hex(m.instr)
                #print type(m)


    for tbm in tbms:
        print 'pc: {0}, ptr: {1}, tcn: {2}'.format(hex(tbm.pc), 
                        hex(tbm.tainted_branch.taint_query[0].ptr),
                        tbm.tainted_branch.taint_query[0].tcn)
