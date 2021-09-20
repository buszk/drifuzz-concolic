#!/usr/bin/env -S python3 -u
import json
import os
import sys
import argparse
import subprocess
from copy import deepcopy
from common import *
from result import ConcolicResult
from mtype import *

parser = argparse.ArgumentParser()
parser.add_argument("target")
parser.add_argument("input")
parser.add_argument("--resume", default=False, action="store_true")
parser.add_argument("--mutate", default=False, action="store_true")
args = parser.parse_args()

br_model = {}  # {br: Cond}
br_blacklist = set()
cur_input = b''


def get_out_file(n):
    return os.path.join(get_out_dir(args.target), str(n))


def get_concolic_log():
    return os.path.join('work', args.target, 'concolic.log')


def comp_score(score1, score2):
    s1 = score1.new * 5000 + score1.ummio * 1000 - score1.nmmio
    s2 = score2.new * 5000 + score2.ummio * 1000 - score2.nmmio
    return s1 - s2


def best(tup1, tup2, check_converge=True):
    """ Choose between two converge test result
    Args:
        tup1: first converge result
        tup2: second converge result

    Returns:
        tup: the better result
        same (bool): if both sides are the same

    """
    print('[search_group]: best')
    print('first model:', tup1[0], tup1[2])
    print('second model', tup2[0], tup2[2])
    score1, output1, converge1, path1, model1, newbr1, result1 = tup1
    score2, output2, converge2, path2, model2, newbr2, result2 = tup2
    print('score diff:', comp_score(score1, score2))
    if not newbr1 and not newbr2:
        # Neither has new branches: ignore convergence, return best score
        return (tup1, False) if (comp_score(score1, score2) > 0) else (tup2, False)
    if check_converge and converge1 and not converge2:
        # Only the first converge
        return tup1, False
    elif check_converge and not converge1 and converge2:
        # Only the second converge
        return tup2, False
    elif check_converge and not converge1 and not converge2:
        # Neither converge
        return (tup1, False) if (comp_score(score1, score2) > 0) else (tup2, False)
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
    print(f'[search_group]: pc_in_path {hex(pc)}')
    for br in path:
        if pc == br.pc:
            return True
    return False


def occurrence_in_path(pc, path):
    count = 0
    for br in path:
        if pc == br.pc:
            count += 1
    return count


def next_branch_pc(model, path):
    for br in path:
        if br.pc in model:
            continue
        return br.pc
    return 0


def print_model(model):
    for key, value in model.items():
        print(f'    {hex(key)}: {value}')


def model_string(model):
    result = ""
    for val in model.values():
        result += str(val)
    return result


def get_lists_from_model(model, blacklist={}, ignore=0):
    zeros = []
    ones = []
    others = []
    jcc_pcs = {}
    for k, v in model.items():
        if k not in blacklist and \
                k not in br_blacklist and \
                k != ignore:
            if v == Cond.FALSE:
                zeros.append(k)
                jcc_pcs[k] = False
            elif v == Cond.TRUE:
                ones.append(k)
                jcc_pcs[k] = True
            else:
                others.append(k)
        else:
            others.append(k)
    return zeros, ones, others, jcc_pcs


def run_concolic_model(target, inp, model):
    global br_blacklist
    test_branch = last_branch_in_model(model)
    zeros, ones, others, jcc_pcs = get_lists_from_model(model)

    # First run
    print("First concolic model run")
    result: ConcolicResult = run_concolic(
        target, inp, zeros=zeros, ones=ones, others=others, target_br=test_branch)
    if result == None:
        return None
    result.set_jcc_mod(jcc_pcs)
    if result.is_jcc_mod_ok():
        return result
    elif test_branch in br_blacklist:
        # If test_branch is alreay black-listed, we need to add conflict pcs
        # to blacklist. We definitely want to single step them.
        [br_blacklist.add(k) for k in result.get_conflict_pcs()]

    # A test print
    result.next_branch_to_flip(model)
    print("\n".join([str(hex(x)) for x in result.get_conflict_pcs().keys()]))

    fixer = {}
    # Fixer may not be valid if multiple values are set for
    # the same (region, ioaddr, offset) pair
    fixer_valid = True
    for x, newval in result.conflicting_bytes.items():
        print(x, newval)
        sp = x.split('_')
        region = 0
        if sp[1] == 'io' or sp[1] == 'consistent':
            region = 1 if sp[1] == 'io' else 2
            ioaddr = int(sp[2], 16)
            offset = int(sp[4], 16)
            key = (region, ioaddr)
            if key in fixer:
                for s in fixer[key]:
                    if s == offset:
                        fixer_valid = False
                fixer[key].add((offset, newval))
            else:
                fixer[key] = set([(offset, newval)])

    # Run with a fixer
    if test_branch not in br_blacklist and fixer_valid:
        print("Repeat with a fixer")
        tmp = file_to_bytes(inp)
        result: ConcolicResult = run_concolic(
            target, get_out_file(0), zeros=zeros, ones=ones, others=others, target_br=test_branch, fixer=fixer)
        if result == None:
            return None
        result.set_jcc_mod(jcc_pcs)
        if result.is_jcc_mod_ok():
            return result
        print("\n".join([str(hex(x))
              for x in result.get_conflict_pcs().keys()]))
        # Restore input file
        bytes_to_file(get_out_file(0), tmp)

    # # Run a second time
    # print("Repeat with updated output")
    # blacklist = result.get_conflict_pcs()
    # zeros, ones, others, jcc_pcs = get_lists_from_model(model)
    # result: ConcolicResult = run_concolic(target, get_out_file(
    #     0), zeros=zeros, ones=ones, others=others, target_br=test_branch)
    # if result == None:
    #     return None
    # result.set_jcc_mod(jcc_pcs)
    # if result.is_jcc_mod_ok():
    #     return result
    # # assert(False)

    # Remove target and try
    # There is not need to remove if test_branch is already black-listed
    # Previous `run_concolic` already tested
    print("Remove target and fall back")
    blacklist = result.get_conflict_pcs()
    zeros, ones, others, jcc_pcs = get_lists_from_model(
        model, blacklist=blacklist, ignore=test_branch)
    result: ConcolicResult = run_concolic(target, get_out_file(
        0), zeros=zeros, ones=ones, others=others, target_br=test_branch)
    if result == None:
        return None
    result.set_jcc_mod(jcc_pcs)
    if result.is_jcc_mod_ok():
        br_blacklist.add(test_branch)
        return result

    # Add conflict pc's and try again
    print("Add conflict pcs and try again")
    blacklist = result.jcc_mod_confict_pcs()
    zeros, ones, others, jcc_pcs = get_lists_from_model(
        merge_dict(model, blacklist))
    result: ConcolicResult = run_concolic(target, get_out_file(
        0), zeros=zeros, ones=ones, others=others, target_br=test_branch)
    if result == None:
        return None
    result.set_jcc_mod(jcc_pcs)
    if result.is_jcc_mod_ok():
        return result
    assert False and "Cannot find a feasible path for given model"
    # return None


def run_concolic(target, inp, zeros=[], ones=[], others=[], target_br=0, fixer={}):
    """Run concolic script
    Args:
        target (str): target module
        inp (str): input file
        zeros ([int]): branch pc forced to be zero
        ones ([int]): branch pc forced to be one
    Returns:
        result (ConcolicResult):
    """
    print('[search_group]: run_concolic')
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

    if len(others) > 0:
        extra_args += ['--others']
        extra_args += [str(hex(x)) for x in others]

    if target_br:
        extra_args += ['--target_branch_pc', str(hex(target_br))[2:]]
        extra_args += ['--after_target_limit', '256']

    # example fixer: {(1, 0x3a028): [(0, 0x02)]}
    if fixer:
        extra_args += ['--fixer_config',
                       json.dumps({str(k): [str(x) for x in v] for k, v in fixer.items()})]

    with open(get_concolic_log(), 'a+') as f:
        cmd = ['./concolic.py', target, inp] + extra_args
        print(' '.join(cmd))
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f)
        p.wait()
        if p.returncode == 2:
            return None
        assert(p.returncode == 0 or p.returncode == 1)

    if not os.path.exists(get_drifuzz_path_constraints(args.target)) or \
            not os.path.exists(get_drifuzz_index(args.target)):
        return None

    result = ConcolicResult(
        get_drifuzz_path_constraints(args.target),
        get_drifuzz_index(args.target),
        outdir=get_out_dir(args.target))
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
        result (ConcolicResult): result of execution
    """
    print('[search_group]: execute')
    bytes_to_file(get_out_file(0), input)
    # remaining_redo = 2
    test_branch = last_branch_in_model(model)
    # run_concolic(args.target, get_out_file(0))
    result = run_concolic_model(args.target, get_out_file(0), model)
    if result == None:
        # FIXME: experimental
        return ScoreT(0, 0, 0), input, False, [], False, result

    if test_branch in br_blacklist:
        model[test_branch] = Cond.BOTH

        result = run_concolic_model(args.target, get_out_file(0), model)
        if result == None:
            # FIXME: experimentalmeet.google.com/psc-nzur-fuwm
            return ScoreT(0, 0, 0), input, False, [], False, result

    if result.is_jcc_mod_ok():
        score = result.score_after_first_appearence(test_branch)
        path = result.get_path()
        new_branch = result.has_new_branch(model)
        curr_count, br_pc = result.next_branch_to_flip(model)
        if curr_count < 0:
            return score, file_to_bytes(get_out_file(0)), True, path, new_branch, result

    score = result.score_after_first_appearence(test_branch)
    path = result.get_path()
    new_branch = result.has_new_branch(model)
    curr_count, br_pc = result.next_branch_to_flip(model)
    print(f"br_pc {hex(br_pc)}, last_branch_in_model {hex(test_branch)}")
    while remaining_run > 0 and remaining_others > 0:

        if (curr_count < 0):
            break
        # run_concolic(args.target, get_out_file(curr_count))
        result = run_concolic_model(
            args.target, get_out_file(curr_count), model)
        if result == None:
            # FIXME: experimental
            return ScoreT(0, 0, 0), input, False, [], False, result
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
        return score, file_to_bytes(get_out_file(0)), False, path, new_branch, result

    return score, file_to_bytes(get_out_file(0)), True, path, new_branch, result


def converge(model, input, tup=None):
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
        result (ConcolicResult): result of execution
    """
    print('[search_group]: converge: model:')
    return __converge(model, input, 1, tup=tup)


def __converge(model, input, depth, tup=None):
    print('[search_group]: __converge')
    if depth == 0:
        print_model(model)
    if tup == None:
        tup = execute(model, input)
    score, output, converged, path, new_branch, result = tup
    orig_output = output

    # Base case
    if (depth == 0):
        return score, output, converged, path, model, new_branch, result

    # first branch not in model
    br = next_branch_pc(model, path)
    if br == 0:
        return score, output, converged, path, model, new_branch, result

    switch_pc, outputs, idxs = result.next_switch_to_flip(model)
    if switch_pc:
        # next branch is a swich
        tup = converge_switch(merge_dict(
            br_model, {switch_pc: Cond.SWITCH}), outputs, idxs)
        score, output, converged, path, model, new_branch, result = tup
    else:
        tup, eq = best(__converge(merge_dict(model, {br: Cond.TRUE}), output, depth-1),
                       __converge(merge_dict(model, {br: Cond.FALSE}), output, depth-1))
        score, output, converged, path, model, new_branch, result = tup
        if eq and occurrence_in_path(br, path) <= 2:
            print(f"[update_model] {hex(br)} Choose TRUE but BOTH are okay")
            model[br] = Cond.TRUE
        elif eq and occurrence_in_path(br, path) > 2:
            print(f"[update_model] {hex(br)} Choose BOTH")
            model[br] = Cond.BOTH
        elif occurrence_in_path(br, path) > 10:
            # This branch appears a lot. We need to test the random model with original input
            rand_tup = __converge(merge_dict(
                model, {br: Cond.RANDOM}), orig_output, 0)
            if best(tup, rand_tup, check_converge=False) == (rand_tup, False):
                print(
                    f"[update_model] {hex(br)} RANDOM is better than either TRUE/FALSE model")
                model[br] = Cond.RANDOM
            else:
                print(
                    f"[update_model] {hex(br)} Compared with RANDOM but we choose {model[br]}")
        else:
            print(f"[update_model] {hex(br)} Choose {model[br]}")
    return score, output, converged, path, model, new_branch, result


def converge_switch(model, outputs, idxs):
    print('[search_group]: converge_switch')
    assert(len(outputs) > 1)
    print('[search_group]: running ', idxs[0])
    tup0 = __converge(model, outputs[0], 0)
    for i in range(1, len(outputs)):
        f = outputs[i]
        print('[search_group]: running ', idxs[i])
        tup = __converge(model, f, 0)
        tup0, conv = best(tup0, tup)
    return tup0


def update_one_branch(model, new_model):
    print('[search_group]: update_one_branch')
    # print('model:')
    # print_model(model)

    last = 0
    for k in new_model.keys():
        if not k in model:
            last = k
            break
    assert(last != 0)
    model[last] = new_model[last]
    # print('new_model:')
    # print_model(model)


def search_greedy(itup=None):
    """search for an optimal input
    """
    print('[search_group]: search_greedy')
    global br_model
    global cur_input

    if itup:
        score, output, converged, path, model, new_branch, result = itup
        itup = score, output, converged, path, new_branch, result
    else:
        new_branch = True
        output = b''
        with open(args.input, "rb") as f:
            output = f.read()
        if cur_input == b'':
            cur_input = output

    print("[search_group] current model:")
    print_model(br_model)
    while new_branch:
        # Test: Add a new execution
        # _, cur_input, _, _, _, _ = execute(br_model, cur_input)
        tup = converge(
            deepcopy(br_model), deepcopy(cur_input),
            tup=itup)
        score, output, converged, path, model, new_branch, result = tup
        itup = (score, output, converged, path, new_branch, result)
        cur_input = output
        update_one_branch(br_model, model)
        print("[search_group] current model:")
        print_model(br_model)

    bytes_to_file(get_out_file(0), output)


def search_mutation():
    print('[search_group]: search_mutation')
    global br_model
    global cur_input
    ftup = execute(deepcopy(br_model), cur_input,
                   remaining_run=100,
                   remaining_others=100)
    score, output, converged, path, new_branch, result = ftup
    cur_input = output
    otup = score, output, converged, path, br_model, new_branch, result

    if new_branch:
        return otup

    # Collect outputs
    outputs = result.read_inverted_input(get_out_dir(args.target))

    # Try mutate model
    for pc, cond in reversed(br_model.items()):
        do_mutate = False
        if cond == Cond.TRUE:
            new_model = deepcopy(br_model)
            new_model[pc] = Cond.SWITCH
            do_mutate = True
        elif cond == Cond.FALSE:
            new_model = deepcopy(br_model)
            new_model[pc] = Cond.SWITCH
            do_mutate = True

        if do_mutate:
            last = result.last_flippable(pc)
            if last in outputs:
                tup = execute(new_model, outputs[last])
                score, output, converged, path, new_branch, result = tup
                if new_branch:
                    br_model = new_model
                    cur_input = output
                    otup = score, output, converged, path, br_model, new_branch, result
                    print("[Mutation] Found new branch!")
                    return otup
    return otup


def search():
    tup = None
    while True:
        search_greedy(itup=tup)
        if not args.mutate:
            break
        tup = search_mutation()
        # New branch ?
        if not tup[4]:
            break


def save_data(target):
    import binascii
    import json
    print('save_data', target)
    dump = {}
    dump['br_blacklist'] = list(br_blacklist)
    dump['br_model'] = [{'key': k, 'value': v} for k, v in br_model.items()]
    dump['cur_input'] = binascii.hexlify(cur_input).decode('ascii')

    def json_dumper(obj):
        return obj.__dict__
    with open(get_search_save(target),
              'w') as outfile:
        json.dump(dump, outfile, default=json_dumper, indent=4)
    print('save_data done')


def load_data(target):
    """
    Method to load an entire master state from JSON file...
    """
    import binascii
    import json
    import shutil
    global br_model, br_blacklist, cur_input
    if not os.path.exists(get_search_save(target)):
        return
    with open(get_search_save(target),
              'r') as infile:
        dump = json.load(infile)
        br_blacklist = set(dump['br_blacklist'])
        cur_input = binascii.unhexlify(dump['cur_input'].encode('ascii'))
        for entry in dump['br_model']:
            br_model[entry['key']] = entry['value']

    shutil.copyfile(get_search_save(target),
                    get_search_save(target)+".bk")


if __name__ == '__main__':
    if os.path.exists(get_concolic_log()):
        os.remove(get_concolic_log())
    if args.resume:
        load_data(args.target)
    try:
        search()
    except KeyboardInterrupt:
        print('KeyboardInterrupt received')
        p = subprocess.Popen(['pkill', '-9', 'panda'])
        p.wait()
        p = subprocess.Popen(['pkill', '-9', 'concolic.py'])
        p.wait()
    except Exception as e:
        print("======================")
        import traceback
        traceback.print_exc()
        print("======================")
    finally:
        save_data(args.target)
        sys.exit()
