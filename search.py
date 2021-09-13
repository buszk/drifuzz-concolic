#!/usr/bin/env -S python3 -u
import os
import sys
import argparse
import subprocess
from enum import IntEnum
from copy import deepcopy
from collections import namedtuple
from common import *
from result import *
from mtype import *

parser = argparse.ArgumentParser()
parser.add_argument("target")
parser.add_argument("input")
args = parser.parse_args()


br_model = {}  # {br: Cond}
br_blacklist = []


def get_out_file(n):
    return os.path.join(get_out_dir(args.target), str(n))


def get_concolic_log():
    return os.path.join('work', args.target, 'concolic.log')


def comp_score(score1, score2):
    s1 = score1.ummio * 1000 - score1.nmmio
    s2 = score2.ummio * 1000 - score2.nmmio
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
    print('[search]: best', 'true model:', tup1[0],
          tup1[2], 'false model', tup2[0], tup2[2])
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
    for key, _ in model.items():
        return key
    return 0


def pc_in_path(pc, path):
    print(f'[search]: pc_in_path {hex(pc)}')
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
        print("[search]: next switch ", idxs)
        return pc, outputs
    else:
        return 0, 0


def print_model(model):
    for key, value in model.items():
        print(f'    {hex(key)}: {value}')


def run_concolic(target, inp, zeros=[], ones=[]):
    """Run concolic script
    Args:
        target (str): target module
        inp (str): input file
        zeros ([int]): branch pc forced to be zero
        ones ([int]): branch pc forced to be one 
    """
    print('[search]: run_concolic')
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
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f)
        p.wait()
        assert(p.returncode == 0 or p.returncode == 1)
    result = ConcolicResult(
        get_drifuzz_path_constraints(args.target),
        get_drifuzz_index(args.target),
        outdir=get_out_dir(args.target))
    return result


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
    bytes_to_file(get_out_file(0), input)
    # remaining_redo = 2
    test_branch = last_branch_in_model(model)
    result = run_concolic(args.target, get_out_file(0))
    score = result.score_after_first_appearence(test_branch)
    path = result.get_path()
    new_branch = result.has_new_branch(model)
    curr_count, br_pc = result.next_branch_to_flip(model)
    remaining_run = 5
    remaining_others = 10
    while remaining_run > 0 and remaining_others > 0:

        if (curr_count < 0):
            break
        result = run_concolic(args.target, get_out_file(curr_count))
        score = result.score_after_first_appearence(test_branch)
        path = result.get_path()
        new_branch = result.has_new_branch(model)
        curr_count, br_pc = result.next_branch_to_flip(model)

        # Dec remaining_run only when flipping the testing branch
        print(f"br_pc {hex(br_pc)}, last_branch_in_model {hex(test_branch)}")
        if test_branch == br_pc:
            remaining_run -= 1
            remaining_others = 10
        else:
            remaining_others -= 1

    if remaining_run == 0:
        return score, file_to_bytes(get_out_file(0)), False, path, new_branch

    return score, file_to_bytes(get_out_file(0)), True, path, new_branch


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
    print('[search]: converge: model:')
    return __converge(model, input, 1)


def __converge(model, input, depth):
    print('[search]: __converge')
    print_model(model)
    score, output, converged, path, new_branch = execute(model, input)
    switch_pc, outputs = next_switch(model, path)
    if (depth == 0):
        return score, output, converged, path, model, new_branch
    br = next_branch_pc(model, path)
    if br == 0:
        return score, output, converged, path, model, new_branch

    if switch_pc:
        tup = converge_switch(merge_dict(
            {switch_pc: Cond.BOTH}, br_model), outputs)
        score, output, converged, path, model, new_branch = tup
    else:
        tup, eq = best(__converge(merge_dict({br: Cond.TRUE}, model), output, depth-1),
                       __converge(merge_dict({br: Cond.FALSE}, model), output, depth-1))
        score, output, converged, path, model, new_branch = tup
        if eq:
            model[br] = Cond.BOTH
    return score, output, converged, path, model, new_branch


def converge_switch(model, outputs):
    print('[search]: converge_switch')
    assert(len(outputs) > 1)
    tup0 = __converge(model, outputs[0], 0)
    for f in outputs[1:]:
        tup = __converge(model, f, 0)
        tup0, conv = best(tup0, tup)
    return tup0


def update_one_branch(model, new_model):
    print('[search]: update_one_branch')
    print('model:')
    print_model(model)
    print('new_model:')
    print_model(new_model)

    last = 0
    for k in new_model.keys():
        if not k in model:
            last = k
        else:
            break
    model[last] = new_model[last]


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
        tup = converge(br_model, output)
        score, output, converged, path, model, new_branch = tup
        update_one_branch(br_model, model)
        print("[search] current model:")
        print_model(br_model)

    bytes_to_file(get_out_file(0), output)
    # print_model(br_model)


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
