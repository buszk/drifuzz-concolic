#!/usr/bin/env -S python3 -u
import os, sys
import subprocess
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
parser.add_argument('--gdbreplay', default=False, action="store_true")
parser.add_argument('--process', default=False, action="store_true")
parser.add_argument('--socket', default="", action="store")
parser.add_argument('--target', default="", action="store")
parser.add_argument('--all', default=False, action="store_true")
args = parser.parse_args()

target = "e1000"
if args.target != "":
    target = args.target

extra_args = get_extra_args(target, socket=args.socket)

if not (args.record or args.replay or args.process or args.all):
    print("Set an argument")
    sys.exit(1)

if args.record or args.all:
    create_recording(qemu_path, qcow, get_snapshot(target), \
            get_cmd(target), copy_dir, get_recording_path(target), \
            expect_prompt, cdrom, extra_args=extra_args)

if args.replay or args.all:
    env={
        "LD_PRELOAD":"/home/zekun/bpf/install/lib/libz3.so",
        **os.environ
    }
    cmd=[join(PANDA_BUILD, "x86_64-softmmu", "panda-system-x86_64"),
        "-replay", target,
        "-panda", "tainted_drifuzz",
        "-panda", "tainted_branch",
        "-pandalog", get_pandalog(target)]
    cmd += extra_args
    if args.gdbreplay:
        cmd = ["gdb", "-ex", "r", "--args"] + cmd
    print(" ".join(cmd))
    subprocess.check_call(cmd, env=env)

if args.process or args.all:
    tbms = []
    with PLogReader(get_pandalog(target)) as plr:
        for m in plr:
            if m.tainted_branch:
                tb = m.tainted_branch
                if tb.taint_query:
                    tcn = tb.taint_query[0].tcn
                    tbms.append(m)
            if m.tainted_instr:
                pass
                #print(hex(m.pc))
                #print(hex(m.instr))
                #print(type(m))


    for tbm in tbms:
        print(f"target: {target}")
        print(f"pc: {hex(tbm.pc)},"
                f"ptr: {hex(tbm.tainted_branch.taint_query[0].ptr)}, " +
                f"tcn: {tbm.tainted_branch.taint_query[0].tcn}")
