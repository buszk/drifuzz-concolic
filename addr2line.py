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
    "rtl818x_pci": {
        "rtl818x_pci": [0xffffffffa0008000, 114688],
        "eeprom_93cx6": [0xffffffffa0000000, 16384],
    },
    "rtl8723ae": {
        "rtl8723ae": [0xffffffffa0100000, 372736],
        "btcoexist": [0xffffffffa0080000, 491520],
        "rtl_pci": [0xffffffffa0060000, 98304],
        "rtl8723_common": [0xffffffffa0050000, 45056],
        "rtlwifi": [0xffffffffa0000000, 311296],
    },
    "rtwpci": {
        "rtwpci": [0xffffffffa00b0000, 61440],
        "rtw88": [0xffffffffa0000000, 696320],
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
    cmd = ['objdump', '-d', module_path,
            f'--start-addr={hex(addr - module_base-0x10)}',
            f'--stop-addr={hex(addr - module_base+0x10)}']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    p.wait()
    prevlines = []
    for line in p.stdout.readlines():
        line = line.decode('utf-8')
        if str(hex(addr - module_base))[2:] + ':' in line:
            print(prevlines[-1], end='')
            print(line, end='')
        prevlines.append(line)
else:
    cmd = ['addr2line', '-f', '-e', join(linux_build, 'vmlinux'), '-a', f'{hex(addr)}']
    print(' '.join(cmd))
    p = subprocess.Popen(cmd)
    p.wait()
    cmd = ['objdump', '-d', join(linux_build, 'vmlinux'),
            f'--start-addr={hex(addr)-0x10}',
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
