#!/usr/bin/env -S python3 -u
import json
import os
import sys
import time
import hashlib
import argparse
import subprocess
from copy import deepcopy
from functools import reduce
from typing import Dict, Tuple
from common import *
from result import ConcolicResult
from mtype import *

parser = argparse.ArgumentParser()
parser.add_argument("target")
parser.add_argument("input")
parser.add_argument("--resume", default=False, action="store_true")
parser.add_argument("--mutate", default=False, action="store_true")
parser.add_argument('--usb', default=False, action="store_true")
parser.add_argument("--noterm", default=False, action="store_true")
args = parser.parse_args()

br_model = {}  # {br: Cond}
br_blacklist = set()
new_branch_ips = set()
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


def bytes_to_hash(bs):
    hash = hashlib.sha1(bs).hexdigest()
    hashfile = get_out_file(hash)
    with open(hashfile, 'wb') as f:
        f.write(bs)
    return hashfile


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
        print(f'    {hex(key)}: {Cond(value).name}')


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


def log_has_interface():
    with open(get_concolic_log()) as f:
        for line in f.readlines():
            if "wlan0:" in line or "eth0:" in line:
                return True
    return False


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

    # # Repeat with updated output
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

    # A test print
    # result.next_branch_to_flip(model)
    # print("\n".join([str(hex(x)) for x in result.get_conflict_pcs().keys()]))

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
    if test_branch not in br_blacklist and fixer_valid and fixer:
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

    # Remove target and try
    # There is not need to remove if test_branch is already black-listed
    # Previous `run_concolic` already tested
    # print("Remove target and fall back")
    # blacklist = result.get_conflict_pcs()
    # zeros, ones, others, jcc_pcs = get_lists_from_model(
    #     model, blacklist=blacklist, ignore=test_branch)
    # result: ConcolicResult = run_concolic(target, get_out_file(
    #     0), zeros=zeros, ones=ones, others=others, target_br=test_branch)
    # if result == None:
    #     return None
    # result.set_jcc_mod(jcc_pcs)
    # if result.is_jcc_mod_ok():
    #     br_blacklist.add(test_branch)
    #     return result

    # Add conflict pc's and try again
    # print("Add conflict pcs and try again")
    # blacklist = result.jcc_mod_confict_pcs()
    # zeros, ones, others, jcc_pcs = get_lists_from_model(
    #     merge_dict(model, blacklist))
    # result: ConcolicResult = run_concolic(target, get_out_file(
    #     0), zeros=zeros, ones=ones, others=others, target_br=test_branch)
    # if result == None:
    #     return None
    # result.set_jcc_mod(jcc_pcs)
    # if result.is_jcc_mod_ok():
    #     return result
    # assert False and "Cannot find a feasible path for given model"
    print("Cannot find a feasible path for given model")
    return None


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
    if len(zeros) == 0 and len(ones) == 0:
        extra_args += ['--forcesave']

    if len(zeros) > 0:
        extra_args += ['--zeros']
        extra_args += [str(hex(x)) for x in zeros]

    if len(ones) > 0:
        extra_args += ['--ones']
        extra_args += [str(hex(x)) for x in ones]

    if len(others) > 0:
        extra_args += ['--others']
        extra_args += [str(hex(x)) for x in others]

    # if target_br:
    #     extra_args += ['--target_branch_pc', str(hex(target_br))[2:]]
    #     extra_args += ['--after_target_limit', '256']

    # example fixer: {(1, 0x3a028): [(0, 0x02)]}
    if fixer:
        extra_args += ['--fixer_config',
                       json.dumps({str(k): [str(x) for x in v] for k, v in fixer.items()})]

    with open(get_concolic_log(), 'a+') as f:
        cmd = ['./concolic.py', target, inp]
        if args.usb:
            cmd += ['--usb']
        cmd += extra_args
        cmd += ['--noflip']
        print(' '.join(cmd))
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                             stdout=f, stderr=f)
        p.wait()
        if p.returncode == RECORD_ERROR_CODE:
            return None
        elif p.returncode == MAPPING_ERROR_CODE:
            assert False and "I/O tracing failed, check device memory mapping"
        assert p.returncode == 0 or p.returncode == 1

    if not os.path.exists(get_drifuzz_path_constraints(args.target)) or \
            not os.path.exists(get_drifuzz_index(args.target)):
        return None

    result = ConcolicResult(
        get_drifuzz_path_constraints(args.target),
        get_drifuzz_index(args.target),
        noflip=True,
        outdir=get_out_dir(args.target))
    return result


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


def search_greedy():
    """search for an optimal input
    """
    print('[search_group]: search_greedy')
    global br_model
    global cur_input
    global new_branch_ips

    nonflippable = set()
    new_branch = True
    output = b''
    repeating_branches = set()
    with open(args.input, "rb") as f:
        output = f.read()
    if cur_input == b'':
        cur_input = output
    bytes_to_file(get_out_file(0), cur_input)
    print(
        f"New branches: {[hex(x) for x in new_branch_ips]}")

    result = run_concolic_model(args.target, get_out_file(0), br_model)
    assert result
    result.set_jcc_mod({})
    assert result.is_jcc_mod_ok()
    br_ips = result.symbolic_branches_ips()

    # Set new_branch_ips if not loaded from save file
    if not new_branch_ips:
        new_branch_ips = br_ips

    print("[search_group] current model:")
    print_model(br_model)
    iteration = 1
    while True:
        print("="*40)
        print(time.ctime())
        print(f"Current iteration: {iteration}")
        print(f"Branches[{len(br_ips)}]: {[hex(x) for x in br_ips]}")
        print(
            f"New branches[{len(new_branch_ips)}]: {[hex(x) for x in new_branch_ips]}")
        print(
            f"Nonflippable[{len(nonflippable)}]: {[hex(x) for x in nonflippable]}")
        iteration += 1
        prefered_results: Dict[Tuple[int,
                                     Cond], ConcolicResult] = {}
        prefered_results_old: Dict[Tuple[int,
                                         Cond], ConcolicResult] = {}

        def run_branch_condition(br, c):
            print(time.ctime())
            print(f"Trying ({hex(br)}, {c})")
            bytes_to_file(get_out_file(0), cur_input)
            infile = bytes_to_hash(cur_input)
            concolic_result = run_concolic_model(
                args.target, infile, merge_dict(deepcopy(br_model), {br: c}))
            if concolic_result:
                print(
                    f"({hex(br)}, {c}) gets score {concolic_result.execution_score()}")
                if concolic_result.new_branches(br_ips):
                    print(
                        f"Found new branches with choice ({hex(br)}, {c})")
                    print([hex(br)
                           for br in concolic_result.new_branches(br_ips)])
                    prefered_results[(br, c)] = concolic_result
                    print(
                        f"Outfile head: {concolic_result.mod_output[:4]}")
                else:
                    prefered_results_old[(br, c)] = concolic_result
                return concolic_result
            else:
                nonflippable.add(br)
                return None

        for br in new_branch_ips:
            if br in br_model:
                print(f"Skipping {br} because it's already in model")
                continue
            if br in nonflippable:
                print(f"Skipping {br} because it's nonflippable")
                continue
            count = 0
            for c in [True, False]:
                # Skip if current path already satisfies branch condition
                if result.satisfy(br, c):
                    print(f"Skipping {(hex(br),c)} because it's satisfied")
                    continue
                if run_branch_condition(br, c):
                    count += 1

            # This is a repeating branch. Both sides are feasible.
            if count == 2:
                repeating_branches.add(br)

        # Try utilize repeating branches
        if len(prefered_results) == 0:
            print(f"No new branches found. Try repeating branches")
            for br in repeating_branches:
                if br in br_model or br in nonflippable:
                    continue

                run_branch_condition(br, True)
                run_branch_condition(br, False)

        if len(prefered_results) == 0:
            print(f"No new branches found. Exit loop")
            break

        best_preferred = reduce(
            lambda x, y: x if x[1].execution_score() >= y[1].execution_score() else y, prefered_results.items())
        print(
            f"Best preferred branch-condition is ({hex(best_preferred[0][0])}, {best_preferred[0][1]})  with score {best_preferred[1].execution_score()}")
        br_model[best_preferred[0][0]] = best_preferred[0][1]
        result = best_preferred[1]
        ofile = bytes_to_hash(result.mod_output)
        raw_result = run_concolic_model(args.target, ofile, {})
        new_branch_ips = raw_result.new_branches(br_ips)
        br_ips = raw_result.symbolic_branches_ips()
        result = raw_result
        bytes_to_file(get_out_file(f"prev.{iteration-1}"), cur_input)
        cur_input = result.mod_output
        bytes_to_file(get_out_file(f"iter.{iteration-1}"), cur_input)
        print("[search_group] current model:")
        print_model(br_model)

        if not args.noterm and log_has_interface():
            print(f"Log file already shows presence of network interface. Terminate.")
            break

    bytes_to_file(get_out_file(0), cur_input)


def search():
    search_greedy()


def save_data(target):
    import binascii
    import json
    print('save_data', target)
    dump = {}
    dump['br_blacklist'] = list(br_blacklist)
    dump['br_model'] = [{'key': k, 'value': v} for k, v in br_model.items()]
    dump['cur_input'] = binascii.hexlify(cur_input).decode('ascii')
    dump['new_branch_ips'] = list(new_branch_ips)

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
    global br_model, br_blacklist, cur_input, new_branch_ips
    if not os.path.exists(get_search_save(target)):
        return
    with open(get_search_save(target),
              'r') as infile:
        dump = json.load(infile)
        br_blacklist = set(dump['br_blacklist'])
        new_branch_ips = set(dump['new_branch_ips'])
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
