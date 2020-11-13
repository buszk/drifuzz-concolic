#!/usr/bin/env -S python3 -u
import os
import sys
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
br_model = {
    
    0xffffffffa01c0ebe: 1,
    0xffffffffa01c1c66: 1,
    0xffffffffa01c1bfc: 1,
    0xffffffffa01c12c6: 1,
    0xffffffffa012271f: 0,
    0xffffffffa012a24e: 0,
    0xffffffffa012a7f6: 0,
    0xffffffffa0132c57: 1,
    0xffffffffa01329ac: 1,
    0xffffffffa01bffb6: 0,
    0xffffffffa01bfec0: 0,
    0xffffffffa01bd110: 0,
    0xffffffffa01bd007: 1,
    0xffffffffa01bd00b: 1,
    0xffffffffa01bd000: 0,
    0xffffffffa01b263e: 1,

}

def best(tup1, tup2):
    """ Choose between two converge test result
    Args:
        tup1: first converge result
        tup2: second converge result

    Returns:
        tup: the better result
        same (bool): if both sides are the same

    """
    print('[search]: best', 'true model:', tup1[0], tup1[2], 'false model', tup2[0], tup2[2])
    score1, output1, converge1, path1, model1, newbr1 = tup1
    score2, output2, converge2, path2, model2, newbr2 = tup2
    if not newbr1 and not newbr2:
        # Neither has new branches: ignore convergence, return best score
        return (tup1, False) if (score1 > score2) else (tup2, False)
    if converge1 and not converge2:
        # Only the first converge
        return tup1, False
    elif not converge1 and converge2:
        # Only the second converge
        return tup2, False
    elif not converge1 and not converge2:
        # Neither converge
        return tup1, False
    elif score1 == score2:
        # Both converge with same scores
        return tup1, True
    else:
        # Both converge with different scores
        return (tup1, False) if (score1 > score2) else (tup2, False)

def file_to_bytes(fname):
    with open(fname, 'rb') as f:
        return f.read()

def bytes_to_file(fname, bs):
    with open(fname, 'wb') as f:
        return f.write(bs)

def remove_if_exits(fname):
    if os.path.exists(fname):
        os.remove(fname)

def merge_dict(d1, d2):
    d1.update(d2)
    return d1

def last_branch_in_model(model):
    for key, _ in model.items():
        return key
    return 0

def print_model(model):
    for key, value in model.items():
        print(f'    {hex(key)}: {value}')
    
def get_next_path(model):
    """Parse and choose the next branch to flip from model
    Args:
        model (dict): input model

    Returns:
        result: branch index to flip
        path: the path of last execution
        br_pc: the flipped branch program counter
        new_branch: path has a new branch not covered by model
    """
    print('[search]: get_next_path')
    result = -1
    path = []
    br_pc = 0
    new_branch = False
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
                new_branch = True
                continue
            if model[pc] == Cond.BOTH:
                continue
            if model[pc] != condition and result == -1:
                result = count
                br_pc = pc
    return result, path, br_pc, new_branch

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

def get_score():
    # 1000 * unique pc - total pc
    print('[search]: get_score')
    count = 0
    pcs = []
    with open('/tmp/drifuzz_path_constraints', 'r') as f:
        for line in f:
            if "Count: " in line:
                sp = line.split(' ')
                assert(sp[0] == 'Count:')
                assert(sp[2] == 'Condition:')
                assert(sp[4] == 'PC:')
                pc = int(sp[5], 16)
                count += 1
                if pc not in pcs:
                    pcs.append(pc)
    return len(pcs) * 1000 - count



def run_concolic(target, inp):
    """Run concolic script
    Args:
        target (str): target module
        inp (str): input file
    """
    print('[search]: run_concolic')
    # shutil.rmtree('out')

    remove_if_exits('/tmp/drifuzz_index')
    remove_if_exits('/tmp/drifuzz_path_constraints')

    print(f'Executing input {inp}')
    with open('concolic.log', 'a+') as f:
        cmd = ['./concolic.py', target, inp, 'out']
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f)
        p.wait()
        assert(p.returncode == 0)

def execute(model, input):
    """Execute model given initial input
    Args:
        model (dict): input model
        input (bytearray): initial seed

    Returns:
        score: score of given model
        output (bytearray): mutated output
        converged (bool): whether the model converged
        path (list): concolic pc's
        new_branch: path has a new branch not covered by model
    """
    print('[search]: execute')
    bytes_to_file('out/0', input)
    remaining_redo = 2
    test_branch = last_branch_in_model(model)
    run_concolic('ath10k_pci', 'out/0')
    curr_count, path, br_pc, new_branch = get_next_path(model)
    if test_branch != 0:
        while remaining_redo > 0 and not test_branch in path:
            print('[search]: repeat because new edge not seen')
            run_concolic('ath10k_pci', 'out/0')
            curr_count, path, br_pc, new_branch = get_next_path(model)
            remaining_redo -= 1
    # remaining_run = 10
    remaining_run = 5
    while remaining_run > 0:
        
        if (curr_count < 0):
            break
        run_concolic('ath10k_pci', f'out/{str(curr_count)}')
        curr_count, path, br_pc, new_branch = get_next_path(model)

        if test_branch != 0:
            remaining_redo = 2
            while remaining_redo > 0 and not test_branch in path:
                print('[search]: repeat because new edge not seen')
                remaining_redo -= 1
                run_concolic('ath10k_pci', 'out/0')
                curr_count, path, br_pc, new_branch = get_next_path(model)


        # Dec remaining_run only when flipping the testing branch
        print(f"br_pc {hex(br_pc)}, last_branch_in_model {hex(test_branch)}")
        if test_branch == br_pc:
            remaining_run -= 1
    
    if remaining_run == 0:
        return get_score(), file_to_bytes('out/0'), False, path, new_branch
    
    return get_score(), file_to_bytes('out/0'), True, path, new_branch
    


def converge(model, input):
    """converge test
    Args:
        model: input model
        input (str): input file

    Returns:
        score: score of given model
        output (bytearray): mutated output
        converged (bool): whether the model converged
        path (list): concolic pc's
        model: the input model itself
        new_branch: path has a new branch not covered by model
    """
    print('[search]: converge: model:')
    print_model(model)
    return __converge(model, input, 0)

def __converge(model, input, depth):
    print('[search]: __converge')
    score, output, converged, path, new_branch = execute(model, input)
    if (depth == 0):
        return score, output, converged, path, model, new_branch
    for br in path:
        if br in br_model:
            continue
        tup, eq = best(__converge(merge_dict({br: Cond.TRUE}, model), output, depth-1),
                       __converge(merge_dict({br: Cond.FALSE}, model), output, depth-1))
        score, output, converged, path, model, new_branch = tup
        if eq:
            model[br] = Cond.BOTH
        
        return score, output, converged, path, model, new_branch
    # All branches are present in model
    return score, output, converged, path, model, new_branch

def search():
    """search for an optimal input
    """
    print('[search]: search')
    global br_model
    input = b''
    with open(args.input, "rb") as f:
        input = f.read()
    score, output, converged, path, new_branch = execute(br_model, input)
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
            score, output, converged, path, model, newbr = tup
            if eq:
                model[br] = Cond.BOTH
            br_model = model
            print("[search] current model:")
            print_model(br_model)
            break

    bytes_to_file('out/0', output)
    # print_model(br_model)


if __name__ == '__main__':
    try:
        search()
    except KeyboardInterrupt:
        print('KeyboardInterrupt received')
        subprocess.check_call(['pkill', '-9', 'panda'])
        subprocess.check_call(['pkill', '-9', 'python'])
        sys.exit()