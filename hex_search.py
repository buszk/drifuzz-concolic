#!/usr/bin/env python3

import os
import struct
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('file', type=str)
parser.add_argument('seq', type=str)
args = parser.parse_args()

odd_n = (len(args.seq) % 2) == 1
search_bytes: bytes = b""
ind = 0
for i in range((len(args.seq)+1)//2):
    byte = 0
    if i == 0 and odd_n:
        byte = int(args.seq[ind], 16)
        ind += 1
    else:
        byte += int(args.seq[ind], 16) * 16
        byte += int(args.seq[ind+1], 16)
        ind += 2
    search_bytes = bytes([byte]) + search_bytes


assert os.path.exists(args.file)
with open(args.file, 'rb') as f:
    bs = f.read()
    res = 0
    while True:
        res = bs.find(search_bytes, res+1)
        if res == -1:
            break
        print(hex(res))
