#!/usr/bin/env python3
import sys
import json
import argparse
import tempfile
import subprocess
import intervaltree
from common import LINUX_BUILD, work
from os.path import expanduser, join, exists

parser = argparse.ArgumentParser()
parser.add_argument('target')
parser.add_argument('addr', type=str)
parser.add_argument('--clean', default=False, action='store_true')
args = parser.parse_args()

addr_sav = join(work, args.target, 'modaddr.sav')

def parse_concolic_log():
    config = {}
    cl = join(work, args.target, 'concolic.log')
    with open(cl) as f:
        for line in f:
            print(line)
            if not 'Live 0x' in line:
                continue
            mod = line.split(' ')[0]
            if mod in config:
                break
            size = int(line.split(' ')[1])
            addr = int(line.split(' ')[5], 16)
            config[mod] = [addr, size]
        return config

if exists(addr_sav) and not args.clean:
    with open(addr_sav, 'r') as f:
        config = json.load(f)
        print(config)
else:
    cl = join(work, args.target, 'concolic.log')
    if exists(cl):
        config = parse_concolic_log()
    else:
        print("Neither save nor concolic.log exist.")
        print("Cannot figure out base addresses for module")
        print(f"   ./snapshot_helper.py {args.target}")
        sys.exit(1)

    with open(addr_sav, 'w+') as f:
        json.dump(config, f)
addr = 0
if len(args.addr) >= 2 and args.addr[0:2] == '0x':
    addr = int(args.addr[2:], 16)
elif 'f' in args.addr:
    addr = int(args.addr, 16)
else:
    addr = int(args.addr)

tree = intervaltree.IntervalTree()
for mod, addrs in config.items():
    tree.addi(addrs[0], addrs[0] + addrs[1], mod)

if (len(tree[addr]) == 1):
    module_name = list(tree[addr])[0][2]
    module_base = list(tree[addr])[0][0]
    print(f"module_name: {module_name}")
    print(f"module_base: {hex(module_base)}")

    p = subprocess.Popen(['find', LINUX_BUILD, '-iname', f'{module_name}.ko'],
                         stdout=subprocess.PIPE)
    module_path = str(p.communicate()[0], encoding='utf-8')[:-1]
    print(f"module_path: {module_path}")

    offset = hex(addr - module_base)
    cmd = ['addr2line', '-f', '-i', '-e', module_path, '-a', offset]
    print(' '.join(cmd))
    p = subprocess.Popen(cmd)
    p.wait()
    cmd = ['objdump', '-Mintel', '-d', module_path,
           f'--start-addr={hex(addr - module_base-0x10)}',
           f'--stop-addr={hex(addr - module_base+0x10)}']
    print(' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    p.wait()
    prevlines = []
    # pyre-ignore[16]
    for line in p.stdout.readlines():
        line = line.decode('utf-8')
        if str(hex(addr - module_base))[2:] + ':' in line:
            print(prevlines[-1], end='')
            print(line, end='')
        prevlines.append(line)
else:
    cmd = ['addr2line', '-f', '-e',
           join(LINUX_BUILD, 'vmlinux'), '-a', f'{hex(addr)}']
    print(' '.join(cmd))
    p = subprocess.Popen(cmd)
    p.wait()
    cmd = ['objdump', '-Mintel', '-d', join(LINUX_BUILD, 'vmlinux'),
           f'--start-addr={hex(addr-0x10)}',
           f'--stop-addr={hex(addr+0x10)}']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    p.wait()
    prevlines = []
    for line in p.stdout.readlines():
        line = line.decode('utf-8')
        if str(hex(addr))[2:] + ':' in line:
            print(prevlines[-1], end='')
            print(line, end='')
        prevlines.append(line)
