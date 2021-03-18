from os.path import join
from copy import deepcopy
from mtype import *

# TODO: duplicate code
def file_to_bytes(fname):
    with open(fname, 'rb') as f:
        return f.read()

class ExecutedBranch(object):
    """
    docstring
    """
    def __init__(self, count:int, pc:int, cond:int, hash:int, vars:int,
                    sym_vars:[str], inverted_vals:{int:int}):
        self.count = count
        self.pc = pc
        self.cond = cond
        self.hash = hash
        self.vars = vars
        self.sym_vars = sym_vars
        self.inverted_vals = inverted_vals
        self.flippable = (inverted_vals != {})
        self._flipped_input = None
    
    def __str__(self):
        return  f'Count: {self.count}, PC: {hex(self.pc)}, Cond: {self.cond}, ' \
                f'Hash: {hex(self.hash)}, Vars: {hex(self.vars)}, ' \
                f'Flippable: {self.flippable}, ' \
                f'Sym_vars: {",".join(self.sym_vars)}'

    def set_flipped_input(self, input:bytearray):
        assert self.flippable
        self._flipped_input = input

    def get_flipped_input(self):
        assert self._flipped_input
        return self._flipped_input

class ConcolicResult(object):
    """
    docstring
    """
    def __init__(self, path_constraints_file, index_file, outdir=""):
        """
        docstring
        """
        self.input2seed = {}
        self.executed_branches:[ExecutedBranch] = []
        self.num_unique_mmio = 0
        self._appeared_mmio = {}
        self.jcc_mod = {}
        self.jcc_mod_set = False
        self.mod_value = {}
        self.conflict_pcs = {}
        with open(index_file, 'r') as f:
            for line in f:
                entries = line.split(', ')
                assert(entries[0].split(' ')[0] == 'input_index:')
                assert(entries[1].split(' ')[0] == 'seed_index:')
                assert(entries[2].split(' ')[0] == 'size:')
                input_index = int(entries[0].split(' ')[1], 16)
                seed_index = int(entries[1].split(' ')[1], 16)
                size = int(entries[2].split(' ')[1])
                for i in range(size):
                    self.input2seed[input_index+i] = seed_index+i
                if len(entries) > 3:
                    # mmio
                    assert(entries[3].split(' ')[0] == 'address:')
                    address = int(entries[3].split(' ')[1], 16)
                    if address not in self._appeared_mmio:
                        self.num_unique_mmio += 1
                        self._appeared_mmio[address] = True
                else:
                    # dma
                    pass
        
        with open(path_constraints_file, 'r') as f:
            for line in f:
                assert(line[-1] == '\n')
                line = line[:-1]
                if '= Z3 Path Solver End =' in line:
                    # reset and export
                    self.executed_branches.append( \
                        ExecutedBranch(count, pc, condition, h, v,
                                        sym_vars, inverted_vals))

                elif 'Count:' in line:
                    sym_vars = []
                    inverted_vals = {}

                    splited = line.split(' ')
                    assert(splited[0] == 'Count:')
                    assert(splited[2] == 'Condition:')
                    assert(splited[4] == 'PC:')
                    assert(splited[6] == 'Hash:')
                    assert(splited[8] == 'Vars:')
                    count = int(splited[1])
                    condition = int(splited[3])
                    pc = int(splited[5], 16)
                    h = int(splited[7], 16)
                    v = int(splited[9], 16)

                elif 'Related input' in line:
                    splited = line.split(' ')
                    assert(splited[0] == 'Related')
                    assert(splited[1] == 'input:')
                    assert(splited[2][:4] == 'val_')
                    val_name = splited[2]
                    sym_vars += [val_name]

                elif 'Inverted value' in line:
                    splited = line.split(' ')
                    assert(splited[0] == 'Inverted')
                    assert(splited[1] == 'value:')
                    assert(splited[2][:4] == 'val_')
                    assert(splited[3] == '=')
                    assert(splited[4][:2] == '#x')
                    input_index = int(splited[2][4:], 16)
                    new_val = int(splited[4][2:], 16)
                    val_name = splited[2]
                    assert(new_val >= 0 and new_val <= 255)
                    if input_index in self.input2seed:
                        seed_index = self.input2seed[input_index]
                        inverted_vals[seed_index] = new_val
                    else:
                        print('Some input_index is not mapped to seed_index')
                        print('Maybe qemu simulated some reg')
                
                elif 'JCC Mod Output End' in line:
                    pass

                elif 'Mod value' in line:
                    splited = line.split(' ')
                    assert(splited[0] == 'Mod')
                    assert(splited[1] == 'value:')
                    assert(splited[2][:4] == 'val_')
                    assert(splited[3] == '=')
                    assert(splited[4][:2] == '#x')
                    input_index = int(splited[2][4:], 16)
                    new_val = int(splited[4][2:], 16)
                    val_name = splited[2]
                    assert(new_val >= 0 and new_val <= 255)
                    if input_index in self.input2seed:
                        seed_index = self.input2seed[input_index]
                        self.mod_value[seed_index] = new_val
                    else:
                        print('Some input_index is not mapped to seed_index')
                        print('Maybe qemu simulated some reg')
                
                elif 'Conflict PC' in line:
                    splited = line.split(' ')
                    assert(splited[0] == 'Conflict')
                    assert(splited[1] == 'PC:')
                    assert(splited[3] == 'Condition:')
                    pcval = int(splited[2], 16)
                    condval = int(splited[4])
                    self.conflict_pcs[pcval] = condval
        
        if outdir != "":
            for br in self.executed_branches:
                if br.flippable:
                    br.set_flipped_input(file_to_bytes(join(outdir, str(br.count))))

    def __str__(self):
        """
        docstring
        """
        return '\n'.join([str(x) for x in self.executed_branches])

    def _bytearray_set(self, bs, ind, val):
        if ind < len(bs):
            bs[ind] = val
        else:
            bs.extend(b'\xaa'*(ind-len(bs)))
            bs.append(val)

    def generate_inverted_input(self, seed_fn, outdir):
        """
        docstring
        """
        orig:bytearray
        with open(seed_fn, 'rb') as f:
            orig = bytearray(f.read())

        # jcc mod modifies the branch instruction to always go the targeted
        # direction 0 or 1. Here, we flip all the jcc branch that is
        # inconsistent with targeted direction.
        # UPDATE
        for k, v in self.mod_value.items():
            self._bytearray_set(orig, k, v)

        copy = deepcopy(orig)
        with open(join(outdir, '0'), 'wb') as o:
            o.write(orig)

        for EB_branch in self.executed_branches:
            for k, v in EB_branch.inverted_vals.items():
                self._bytearray_set(copy, k, v)
            with open(join(outdir, str(EB_branch.count)), 'wb') as o:
                o.write(copy)
            copy = deepcopy(orig)

    def read_inverted_input(self, outdir):
        result = {}
        for EB_branch in self.executed_branches:
            if EB_branch.flippable:
                with open(join(outdir, str(EB_branch.count)), 'rb') as i:
                    result[EB_branch.count] = i.read()
        return result

    def last_flippable(self, pc):
        for EB_branch in reversed(self.executed_branches):
            if EB_branch.flippable and EB_branch.pc == pc:
                return EB_branch.count

    def is_jcc_mod_ok(self):
        """
        docstring
        """
        assert self.jcc_mod_set
        return len(self.conflict_pcs) == 0
    
    #deprecated
    def jcc_mod_confict_pcs(self):
        """
        docstring
        """
        # assert self.jcc_mod_set
        # jcc_var_set = {}
        # conficlt_pc = []
        # var2brs = {}
        # for EB_branch in self.executed_branches:
        #     if EB_branch.pc in self.jcc_mod:
        #         for var in EB_branch.sym_vars:
        #             jcc_var_set[var] = True
        #             if var in var2brs:
        #                 if EB_branch.pc not in var2brs[var]:
        #                     var2brs[var].append(EB_branch.pc)
        #             else:
        #                 var2brs[var] = [EB_branch.pc]
        #     else:
        #         for var in EB_branch.sym_vars:
        #             if var in jcc_var_set:
        #                 for p in var2brs[var]:
        #                     if p not in conficlt_pc:
        #                         conficlt_pc.append(p)
                        
        #     # print(jcc_var_set, EB_branch.sym_vars)
        # return conficlt_pc
        return self.conflict_pcs

    def get_conflict_pcs(self):
        return self.conflict_pcs

    def pc_in_path(self, pc):
        for br in self.executed_branches:
            if br.flippable and br.pc == pc:
                return True
        return False

    def next_new_branch(self, model):
        for br in self.executed_branches:
            if br.flippable and br.pc not in model:
                return br.pc
        return 0

    def num_concolic_branch(self):
        """
        docstring
        """
        result = 0
        for br in self.executed_branches:
            if br.flippable:
                result += 1
        return result
    
    def score_after_first_appearence(self, pc):
        """
        docstring
        """
        count = 0
        pcs = []
        after = False
        pcs_before = []
        new_pcs = []
        for br in self.executed_branches:
            # print(br)
            if not br.flippable:
                continue
            if not after and br.pc not in pcs_before:
                pcs_before.append(br.pc)
            if br.pc == pc:
                after = True
            if after:
                count += 1
                if br.pc not in pcs:
                    pcs.append(br.pc)
                if br.pc not in pcs_before:
                    if br.pc not in new_pcs:
                        new_pcs.append(br.pc)
        if len(pcs) == 0 and count == 0 and pc != 0:
            print(f"target: {pc}")
            assert(False and "Got zero score, check drifuzz/path_constraints")
        return ScoreT(len(new_pcs), len(pcs), count)
        
    def next_branch_to_flip(self, model):
        print("[result] next_branch_to_flip")
        for br in self.executed_branches:
            print(br)
            if not br.flippable:
                # print("not flippable")
                continue
            if br.pc in self.jcc_mod:
                # print("in jcc_mod")
                continue
            if br.pc not in model:
                # print("not in model")
                continue
            if model[br.pc] >= 2: #Cond.BOTH
                # print("model both")
                continue
            # print(model[br.pc], br.cond, model[br.pc] == br.cond)
            if model[br.pc] != br.cond:
                print(br.count, hex(br.pc))
                return br.count, br.pc
        print(-1, 0)
        return -1, 0

    def next_switch_to_flip(self, model):
        curr_pc = 0
        h = 0
        v = 0
        idxs = []
        outputs = []
        for br in self.executed_branches:
            if not br.flippable:
                continue
            elif br.pc in model and curr_pc == 0:
                continue
            elif br.pc in self.jcc_mod and curr_pc == 0:
                continue
            
            if curr_pc == 0:
                curr_pc = br.pc
                h = br.hash
                v = br.vars
                idxs.append(br.count)
                outputs.append(br.get_flipped_input())
            elif curr_pc == br.pc and br.hash != h and br.vars == v:
                # Same bytes different hash
                idxs.append(br.count)
                outputs.append(br.get_flipped_input())
            else:
                break
        if len(idxs) > 1:
            print('[result] next switch: ', idxs)
            return curr_pc, outputs
        else:
            return 0, 0

    def has_new_branch(self, model):
        for br in self.executed_branches:
            if br.flippable and br.pc not in model:
                return True
        return False

    def set_jcc_mod(self, jcc_mod):
        self.jcc_mod = jcc_mod
        self.jcc_mod_set = True

    def unflippable_model(self):
        """
        docstring
        """
        res = {}
        for br in self.executed_branches:
            if not br.flippable:
                if br.pc in res and res[br.pc] != br.cond:
                    res[br.pc] == Cond.BOTH
                else:
                    res[br.pc] = br.cond
        return res

    def get_path(self):
        path = []
        for br in self.executed_branches:
            if br.flippable:
                a = BranchT(
                    br.count,
                    br.pc,
                    br.cond,
                    br.hash,
                    br.vars,
                    br.get_flipped_input(),
                )
                path.append(a)
        return path

if __name__ == '__main__':
    CR_a = ConcolicResult('work/ath9k/drifuzz_path_constraints', 'work/ath9k/drifuzz_index')
    print(CR_a)
