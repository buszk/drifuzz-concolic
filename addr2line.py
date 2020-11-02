#!/usr/bin/env python3
import sys
import argparse
import subprocess
import intervaltree
from os.path import expanduser,join

parser = argparse.ArgumentParser()
parser.add_argument('addr', type=str)
args = parser.parse_args()

addr = 0
if len(args.addr) >= 2 and args.addr[0:2] == '0x':
    addr = int(args.addr[2:], 16)
elif 'f' in addr:
    addr = int(args.addr, 16)
else:
    addr = int(args.addr)

tree = intervaltree.IntervalTree()
tree.addi(0xffffffffa01b0000, 0xffffffffa01b0000 + 126976, "ath10k_pci")
tree.addi(0xffffffffa0018000, 0xffffffffa0018000 + 1642496, "ath10k_core")
tree.addi(0xffffffffa0000000, 0xffffffffa0000000 + 90112, "ath")


assert(len(tree[addr]) == 1)

module_name = list(tree[addr])[0][2]
module_base = list(tree[addr])[0][0]
print(f"module_name: {module_name}")
print(f"module_base: {module_base}")

home = expanduser("~")
linux_build = join(home, "Workspace", "git", "Drifuzz", "linux-module-build")
p = subprocess.Popen(['find', linux_build, '-iname', f'{module_name}.ko'], 
                        stdout=subprocess.PIPE)
module_path = str(p.communicate()[0], encoding='utf-8')[:-1]
print(f"module_path: {module_path}")

offset = hex(addr - module_base)
cmd = ['addr2line', '-f', '-i', '-e', module_path, '-a', offset]
print(' '.join(cmd))
p = subprocess.Popen(cmd)
p.wait()