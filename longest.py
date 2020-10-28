#!/usr/bin/env python3
import sys
import shutil
import subprocess
from time import sleep
from copy import deepcopy

model = {
    0xffffffffa01b263e: 1,
    0xffffffffa01bd000: 0,
    0xffffffffa01bd007: 1,
    0xffffffffa01bd110: 0,
    0xffffffffa01bd11f: 0,
    0xffffffffa01bd123: 0,
    0xffffffffa01bfec0: 0, #random guess
    0xffffffffa01bffb6: 0, #comp dev_id
    0xffffffffa01bffba: 0, #comp dev_id
    0xffffffffa01bcc8d: 0, #crashed
    0xffffffffa01d0025: 1, #guess
    0xffffffffa01d0027: 1, #guess
    0xffffffffa01bfec6: 0, #chip id != -1
    0xffffffffa012a7f6: 1, #hard to flip to 1
    0xffffffffa012a7f9: 0, #read_idx != -1
    0xffffffffa012a222: 1, #but can be both
    0xffffffffa012a22a: 1, #same as above
    0xffffffffa012a24e: 0, #EIO
    0xffffffffa01329ac: 1, #set
    0xffffffffa0132c57: 1,
    0xffffffffa0132c5a: 1,
}

curr_count = -1

def get_next_path():
    global curr_count
    result = -1
    with open('/tmp/drifuzz_path_constraints', 'r') as f:
        for line in f:
            if "Count: " not in line:
                continue
            sp = line.split(' ')
            assert(sp[0] == 'Count:')
            assert(sp[2] == 'Condition:')
            assert(sp[4] == 'PC:')
            count = int(sp[1])
            condition = int(sp[3])
            pc = int(sp[5], 16)
            if pc not in model:
                print(hex(pc), "not in model")
                assert(False)
            print(count, hex(pc), condition)
            if model[pc] != condition and result == -1:
                # assert curr_count < count and "Reversing edge did not succeed"q
                result = count
    return result

def run_concolic(target, inp):
    # shutil.rmtree('out')
    print(f'Executing input {inp}')
    with open('concolic.log', 'a+') as f:
        cmd = ['python3', 'concolic.py', target, inp, 'out']
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f)
        p.wait()
        assert(p.returncode == 0)

def main():
    global curr_count

    # run_concolic('ath10k_pci', 'random_seed')
    run_concolic('ath10k_pci', 'out/0')
    while True:
        curr_count = get_next_path()
        
        if (curr_count < 0):
            break
        sleep(3)
        run_concolic('ath10k_pci', f'out/{str(curr_count)}')
    print("END")




if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('KeyboardInterrupt received')
        subprocess.check_call(['pkill', '-9', 'panda'])
        subprocess.check_call(['pkill', '-9', 'python'])
        sys.exit()
