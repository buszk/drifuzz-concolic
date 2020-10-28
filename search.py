#!/usr/bin/env python3
import argparse
import subprocess
from enum import IntEnum
from copy import deepcopy

parser = argparse.ArgumentParser()
parser.add_argument("input")
args = parser.parse_args()

class Cond(IntEnum):
    FALSE = 0 #false
    TRUE = 1 #true
    BOTH = 2 #both

br_model = {} #{br: Cond}

def best(tup1, tup2):
    print('[search]: best', 'true', tup1[0], tup1[2], 'false', tup2[0], tup2[2])
    if tup1[2] and not tup2[2]:
        # Only the first converge
        return tup1, False
    elif not tup1[2] and tup2[2]:
        # Only the second converge
        return tup2, False
    elif not tup1[2] and not tup1[2]:
        # Neither converge
        return tup1, False
    elif tup1[0] == tup2[0]:
        # Both converge with same scores
        return tup1, True
    else:
        # Both converge with different scores
        return (tup1, False) if (tup1[0] > tup2[0]) else (tup2, False)

def file_to_bytes(fname):
    with open(fname, 'rb') as f:
        return f.read()

def bytes_to_file(fname, bs):
    with open(fname, 'wb') as f:
        return f.write(bs)

def merge_dict(d1, d2):
    d1.update(d2)
    return d1

def print_model(model):
    for key, value in model.items():
        print(f'    {hex(key)}: {value}')
    
def get_next_path(model):
    print('[search]: get_next_path')
    result = -1
    path = []
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
            print(count, hex(pc), condition)
            path.append(pc)
            if pc not in model:
                continue
            if model[pc] == Cond.BOTH:
                continue
            if model[pc] != condition and result == -1:
                result = count
    return result, path

def num_unique_mmio():
    print('[search]: num_unique_mmio')
    s = set()
    with open('/tmp/drifuzz_index', 'r') as f:
        for line in f:
            entries = line.split(', ')
            # assert(entries[0].split(' ')[0] == 'input_index:')
            # assert(entries[1].split(' ')[0] == 'seed_index:')
            # assert(entries[2].split(' ')[0] == 'size:')
            assert(entries[3].split(' ')[0] == 'address:')
            # input_index = int(entries[0].split(' ')[1], 16)
            # seed_index = int(entries[1].split(' ')[1], 16)
            # size = int(entries[2].split(' ')[1])
            address = int(entries[3].split(' ')[1], 16)
            s.add(address)
    return len(s)

def num_concolic_branches():
    print('[search]: num_concolic_branches')
    count = 0
    with open('/tmp/drifuzz_path_constraints', 'r') as f:
        for line in f:
            if "Count: " in line:
                count += 1
    return count


def run_concolic(target, inp):
    print('[search]: run_concolic')
    # shutil.rmtree('out')
    print(f'Executing input {inp}')
    with open('concolic.log', 'a+') as f:
        cmd = ['python3', 'concolic.py', target, inp, 'out']
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f)
        p.wait()
        assert(p.returncode == 0)

def execute(model, input):
    print('[search]: execute')
    with open('out/0', 'wb') as f:
        f.write(input)
    run_concolic('ath10k_pci', 'out/0')
    curr_count, path = get_next_path(model)
    # remaining_run = 10
    remaining_run = 5
    while remaining_run > 0:
        
        if (curr_count < 0):
            break
        run_concolic('ath10k_pci', f'out/{str(curr_count)}')
        curr_count, path = get_next_path(model)
        remaining_run -= 1
    
    if remaining_run == 0:
        return 0, file_to_bytes('out/0'), False, path
    
    return num_concolic_branches(), file_to_bytes('out/0'), True, path
    


def converge(model, input):
    print('[search]: converge: model:')
    print_model(model)
    return __converge(model, input, 0)

def __converge(model, input, depth):
    print('[search]: __converge')
    score, output, converged, path = execute(model, input)
    if (depth == 0):
        return score, output, converged, path, model
    for br in path:
        if br in br_model:
            continue
        tup, eq = best(__converge(merge_dict({br: Cond.TRUE}, model), output, depth-1),
                       __converge(merge_dict({br: Cond.FALSE}, model), output, depth-1))
        score, output, converged, path, model = tup
        if eq:
            model[br] = Cond.BOTH
        
        return score, output, converged, path, model
    # All branches are present in model
    return score, output, converged, path, model

def search():
    print('[search]: search')
    global br_model
    input = b''
    with open(args.input, "rb") as f:
        input = f.read()
    score, output, converged, path = execute(br_model, input)
    new_branch = True
    if not converged:
        print("Empty model does not converge")
        return
    while new_branch:
        new_branch = False
        for br in path:
            if br in br_model:
                continue
            new_branch = True
            tup, eq = best(converge(merge_dict({br: Cond.TRUE}, br_model), output),
                           converge(merge_dict({br: Cond.FALSE}, br_model), output))
            score, output, converged, path, model = tup
            if eq:
                model[br] = Cond.BOTH
            br_model = model
            print("[search] current model:")
            print_model(br_model)
    print(br_model)


if __name__ == '__main__':
    try:
        search()
    except KeyboardInterrupt:
        print('KeyboardInterrupt received')
        subprocess.check_call(['pkill', '-9', 'panda'])
        subprocess.check_call(['pkill', '-9', 'python'])
        sys.exit()