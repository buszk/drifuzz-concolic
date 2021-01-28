#!/usr/bin/env -S python3 -u
import os
import sys
import argparse
import subprocess
from copy import deepcopy
from collections import namedtuple
from common import *
from result import ConcolicResult
from mtype import Cond

parser = argparse.ArgumentParser()
parser.add_argument("target")
parser.add_argument("input")
args = parser.parse_args()

BranchT = namedtuple("BranchT", "index pc cond hash vars file")
ScoreT = namedtuple("ScoreT", "ummio nmmio")

br_model = {} #{br: Cond}
br_model = {
    0xffffffffa01b2640: 1,
    0xffffffffa01bd000: 0,
    0xffffffffa01bd00b: 2,
}
br_blacklist = []
br_blacklist = [
    0xffffffffa01bd000,
    0xffffffffa01bd00b,
]
unflippable = {}

def get_out_file(n):
    return os.path.join(get_out_dir(args.target), str(n))

def get_concolic_log():
    return os.path.join('work', args.target, 'concolic.log')

def comp_score(score1, score2):
    s1 = score1.ummio *1000 - score1.nmmio
    s2 = score2.ummio *1000 - score2.nmmio
    return s1 - s2

def best(tup1, tup2):
    """ Choose between two converge test result
    Args:
        tup1: first converge result
        tup2: second converge result

    Returns:
        tup: the better result
        same (bool): if both sides are the same

    """
    print('[search_mass]: best')
    print('true model:', tup1[0], tup1[2])
    print('false model', tup2[0], tup2[2])
    score1, output1, converge1, path1, model1, newbr1 = tup1
    score2, output2, converge2, path2, model2, newbr2 = tup2
    if not newbr1 and not newbr2:
        # Neither has new branches: ignore convergence, return best score
        return (tup1, False) if (comp_score(score1, score2) > 0) else (tup2, False)
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
        return (tup1, False) if (comp_score(score1, score2) > 0) else (tup2, False)

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
    copy = deepcopy(d1)
    copy.update(d2)
    return copy

def last_branch_in_model(model):
    last = 0
    for key, _ in model.items():
        last = key
    return last

def pc_in_path(pc, path):
    print(f'[search_mass]: pc_in_path {hex(pc)}')
    for br in path:
        if pc == br.pc:
            return True
    return False

def next_branch_pc(model, path):
    for br in path:
        if br.pc in model:
            continue
        return br.pc
    return 0

def next_switch(model, path):
    pc = 0
    h = 0
    v = 0
    idxs = []
    outputs = []

    for br in path:
        if br.pc in model and pc == 0:
            continue
        elif pc == 0:
            pc = br.pc
            h = br.hash
            v = br.vars
            idxs.append(br.index)
            outputs.append(br.file)
        elif pc == br.pc and br.hash != h and br.vars == v:
            # Same bytes different hash
            idxs.append(br.index)
            outputs.append(br.file)
        else:
            break
    if len(idxs) > 1:
        print("[search_mass]: next switch ", idxs)
        return pc, outputs
    else:
        return 0, 0
    



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
    print('[search_mass]: get_next_path')
    result = -1
    path = []
    br_pc = 0
    new_branch = False
    with open(get_drifuzz_path_constraints(args.target), 'r') as f:
        toadd = False
        for line in f:
            if "Count: " in line:
                sp = line.split(' ')
                assert(sp[0] == 'Count:')
                assert(sp[2] == 'Condition:')
                assert(sp[4] == 'PC:')
                assert(sp[6] == 'Hash:')
                assert(sp[8] == 'Vars:')
                count = int(sp[1])
                condition = int(sp[3])
                pc = int(sp[5], 16)
                h = int(sp[7], 16)
                v = int(sp[9], 16)
                toadd = True
            elif toadd and "Inverted" in line:
                toadd = False
                print(count, hex(pc), condition)
                br = BranchT(count, pc, condition, h, v, file_to_bytes(get_out_file(count)))
                path.append(br)
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
    print('[search_mass]: num_unique_mmio')
    s = set()
    with open(get_drifuzz_index(args.target), 'r') as f:
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
    """Number of flippable branch

    Returns:
        n: Number of flippable branch
    """
    print('[search_mass]: num_concolic_branches')
    count = 0
    with open(get_drifuzz_path_constraints(args.target), 'r') as f:
        for line in f:
            toadd = False
            if "Count: " in line:
                toadd = True
            elif toadd and "Inverted" in line:
                toadd = False
                count += 1
    return count

def get_score(model):
    # 1000 * unique pc - total pc
    print('[search_mass]: get_score', end='')
    count = 0
    pcs = []
    last_pc = last_branch_in_model(model)
    after = False
    with open(get_drifuzz_path_constraints(args.target), 'r') as f:
        for line in f:
            if "Count: " in line:
                sp = line.split(' ')
                assert(sp[0] == 'Count:')
                assert(sp[2] == 'Condition:')
                assert(sp[4] == 'PC:')
                pc = int(sp[5], 16)
                if pc == last_pc:
                    after = True
                if after:
                    count += 1
                    if pc not in pcs:
                        pcs.append(pc)
    print(f' {len(pcs)} {count}')
    return ScoreT(len(pcs), count)

def run_concolic_model(target, inp, model):
    global br_blacklist
    zeros = []
    ones = []
    jcc_pcs = {}
    latest_br_pc = last_branch_in_model(model)
    for k, v in model.items():
        if k in br_blacklist:
            continue
        if v == Cond.FALSE:
            zeros.append(k)
            jcc_pcs[k] = False
        elif v == Cond.TRUE:
            ones.append(k)
            jcc_pcs[k] = True
    result:ConcolicResult = run_concolic(target, inp, zeros=zeros, ones=ones)
    if result == None:
        return None
    result.set_jcc_mod(jcc_pcs)
    if result.is_jcc_mod_ok():
        return result

    # Remove latest branch pc and try again
    remove_list = result.jcc_mod_confict_pcs()
    br_blacklist += remove_list
    for rpc in remove_list:
        jcc_pcs.pop(rpc, None)
        if rpc in zeros:
            zeros.remove(rpc)
        if rpc in ones:
            ones.remove(rpc)
    result:ConcolicResult = run_concolic(target, inp, zeros=zeros, ones=ones)
    if result == None:
        return None
    result.set_jcc_mod(jcc_pcs)
    if result.is_jcc_mod_ok():
        return result
    else:
        assert False




def run_concolic(target, inp, zeros=[], ones=[]):
    """Run concolic script
    Args:
        target (str): target module
        inp (str): input file
        zeros ([int]): branch pc forced to be zero
        ones ([int]): branch pc forced to be one 
    Returns:
        result (ConcolicResult):
    """
    print('[search_mass]: run_concolic')
    # shutil.rmtree('out')

    remove_if_exits(get_drifuzz_index(args.target))
    remove_if_exits(get_drifuzz_path_constraints(args.target))

    print(f'Executing input {inp}')
    
    extra_args = []
    if len(zeros) > 0:
        extra_args += ['--zeros']
        extra_args += [str(hex(x)) for x in zeros]

    if len(ones) > 0:
        extra_args += ['--ones']
        extra_args += [str(hex(x)) for x in ones]

    with open(get_concolic_log(), 'a+') as f:
        cmd = ['./concolic.py', target, inp] + extra_args
        global br_blacklist
        print(' '.join([str(hex(x)) for x in br_blacklist]))
        print(' '.join(cmd))
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f)
        p.wait()
        if p.returncode == 2:
            return None
        assert(p.returncode == 0 or p.returncode == 1)

    result = ConcolicResult(
        get_drifuzz_path_constraints(args.target),
        get_drifuzz_index(args.target),
        outdir=get_out_dir(args.target))
    global unflippable
    unflippable = result.unflippable_model()
    return result

def execute(model, input, remaining_run=5, remaining_others=10):
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
    print('[search_mass]: execute')
    bytes_to_file(get_out_file(0), input)
    # remaining_redo = 2
    test_branch = last_branch_in_model(model)
    # run_concolic(args.target, get_out_file(0))
    result = run_concolic_model(args.target, get_out_file(0), model)
    if result == None:
        # FIXME: experimental
        return ScoreT(0,0), input, False, [], False
    curr_count, path, br_pc, new_branch = get_next_path(model)
    curr_count, br_pc = result.next_branch_to_flip(model)
    print(f"br_pc {hex(br_pc)}, last_branch_in_model {hex(test_branch)}")
    while remaining_run > 0 and remaining_others > 0:
        
        if (curr_count < 0):
            break
        # run_concolic(args.target, get_out_file(curr_count))
        result = run_concolic_model(args.target, get_out_file(curr_count), model)
        if result == None:
            # FIXME: experimental
            return ScoreT(0,0), input, False, [], False
        curr_count, path, br_pc, new_branch = get_next_path(model)
        curr_count, br_pc = result.next_branch_to_flip(model)

        # Dec remaining_run only when flipping the testing branch
        print(f"br_pc {hex(br_pc)}, last_branch_in_model {hex(test_branch)}")
        if test_branch == br_pc:
            remaining_run -= 1
            remaining_others = 10
        else:
            remaining_others -= 1
    
    if remaining_run == 0:
        return get_score(model), file_to_bytes(get_out_file(0)), False, path, new_branch
    
    return get_score(model), file_to_bytes(get_out_file(0)), True, path, new_branch


def converge(model, input):
    """converge test
    Args:
        model: input model
        input (bytearray): input file

    Returns:
        score: score of given model
        output (bytearray): mutated output
        converged (bool): whether the model converged
        path (list): concolic pc's
        model: the input model itself
        new_branch: path has a new branch not covered by model
    """
    print('[search_mass]: converge: model:')
    return __converge(model, input, 1)

def __converge(model, input, depth):
    print('[search_mass]: __converge')
    print_model(model)
    score, output, converged, path, new_branch = execute(model, input)
    switch_pc, outputs = next_switch(model, path)
    if (depth == 0):
        return score, output, converged, path, model, new_branch
    br = next_branch_pc(model, path)
    if br == 0:
        return score, output, converged, path, model, new_branch

    if switch_pc:
        tup = converge_switch(merge_dict({switch_pc: Cond.BOTH}, br_model), outputs)
        score, output, converged, path, model, new_branch = tup
    else:
        global unflippable
        if br not in unflippable:
            tup, eq = best(__converge(merge_dict(model, {br: Cond.TRUE}), output, depth-1),
                            __converge(merge_dict(model, {br: Cond.FALSE}), output, depth-1))
            score, output, converged, path, model, new_branch = tup
            if eq:
                model[br] = Cond.BOTH
        else:
            model[br] = unflippable[br]
            tup = __converge(merge_dict(model, {br: unflippable[br]}), output, depth-1)
            score, output, converged, path, model, new_branch = tup
    return score, output, converged, path, model, new_branch
    

def converge_switch(model, outputs):
    print('[search_mass]: converge_switch')
    assert(len(outputs) > 1)
    tup0 = __converge(model, outputs[0], 0)
    for f in outputs[1:]:
        tup = __converge(model, f, 0)
        tup0, conv = best(tup0, tup)
    return tup0

def update_one_branch(model, new_model):
    print('[search_mass]: update_one_branch')
    print('model:')
    print_model(model)

    last = 0
    for k in new_model.keys():
        if not k in model:
            last = k
            break
    assert(last != 0)
    model[last] = new_model[last]
    print('new_model:')
    print_model(model)
    

def search():
    """search for an optimal input
    """
    print('[search_mass]: search')
    global br_model
    input = b''
    with open(args.input, "rb") as f:
        input = f.read()
    # score, output, converged, path, new_branch = execute(br_model, input)
    # if not converged:
    #     print("Empty model does not converge")
    #     return
    new_branch = True
    output = input
    while new_branch:
        tup = converge(deepcopy(br_model), output)
        score, output, converged, path, model, new_branch = tup
        update_one_branch(br_model, model)
        print("[search_mass] current model:")
        print_model(br_model)
        if not new_branch:
            tup = execute(deepcopy(br_model), output, 
                            remaining_run=100,
                            remaining_others=100)
            score, output, converged, path, new_branch = tup

    bytes_to_file(get_out_file(0), output)
    print_model(br_model)


if __name__ == '__main__':
    if os.path.exists(get_concolic_log()):
        os.remove(get_concolic_log())
    try:
        search()
    except KeyboardInterrupt:
        print('KeyboardInterrupt received')
        subprocess.check_call(['pkill', '-9', 'panda'])
        subprocess.check_call(['pkill', '-9', 'python'])
        sys.exit()
