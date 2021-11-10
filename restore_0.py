#!/usr/bin/env python3

import json
import argparse
import binascii
from common import get_search_save, get_out_dir

parser = argparse.ArgumentParser()
parser.add_argument("target")
args = parser.parse_args()
target = args.target

with open(get_search_save(target),
            'r') as infile:
    dump = json.load(infile)
    cur_input = binascii.unhexlify(dump['cur_input'].encode('ascii'))

    with open(f"{get_out_dir(args.target)}/0", 'wb') as f:
        f.write(cur_input)