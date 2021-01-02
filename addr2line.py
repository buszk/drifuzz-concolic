#!/usr/bin/env python3
import sys
import argparse
import subprocess
import intervaltree
from os.path import expanduser,join,isfile

parser = argparse.ArgumentParser()
parser.add_argument('target')
parser.add_argument('addr', type=str)
args = parser.parse_args()

addrs_config = {
    "ath10k_pci": {
        "ath10k_pci": [0xffffffffa01b0000, 126976],
        "ath10k_core": [0xffffffffa0018000, 1642496],
        "ath": [0xffffffffa0000000, 90112],
    },
    "ath9k": {
        "ath9k": [0xffffffffa0128000, 352256],
        "ath9k_common": [0xffffffffa0118000, 32768],
        "ath9k_hw": [0xffffffffa0018000, 1024000],
        "ath": [0xffffffffa0000000, 90112],
    },
    "iwlwifi": {
        "iwlwifi": [0xffffffffa0000000, 798720],
    },
}

addr = 0
if len(args.addr) >= 2 and args.addr[0:2] == '0x':
    addr = int(args.addr[2:], 16)
elif 'f' in args.addr:
    addr = int(args.addr, 16)
else:
    addr = int(args.addr)

tree = intervaltree.IntervalTree()
for mod, addrs in addrs_config[args.target].items():
    tree.addi(addrs[0], addrs[0] + addrs[1], mod)

home = expanduser("~")
linux_build = join(home, "Workspace", "git", "Drifuzz", "linux-module-build")

if (len(tree[addr]) == 1):
    module_name = list(tree[addr])[0][2]
    module_base = list(tree[addr])[0][0]
    print(f"module_name: {module_name}")
    print(f"module_base: {hex(module_base)}")

    p = subprocess.Popen(['find', linux_build, '-iname', f'{module_name}.ko'], 
                            stdout=subprocess.PIPE)
    module_path = str(p.communicate()[0], encoding='utf-8')[:-1]
    print(f"module_path: {module_path}")

    offset = hex(addr - module_base)
    cmd = ['addr2line', '-f', '-i', '-e', module_path, '-a', offset]
    print(' '.join(cmd))
    p = subprocess.Popen(cmd)
    p.wait()
else:
    cmd = ['addr2line', '-f', '-e', join(linux_build, 'vmlinux'), '-a', f'{hex(addr)}']
    print(' '.join(cmd))
    p = subprocess.Popen(cmd)
    p.wait()
