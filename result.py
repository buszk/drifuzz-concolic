from os.path import join
from copy import deepcopy

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
    
    def __str__(self):
        return  f'Count: {self.count}, PC: {hex(self.pc)}, Cond: {self.cond}, ' \
                f'Hash: {hex(self.hash)}, Vars: {hex(self.vars)}, ' \
                f'Sym_vars: {",".join(self.sym_vars)}'

class ConcolicResult(object):
    """
    docstring
    """
    def __init__(self, path_constraints_file, index_file):
        """
        docstring
        """
        self.input2seed = {}
        self.executed_branches:[ExecutedBranch] = []
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

    def __str__(self):
        """
        docstring
        """
        return '\n'.join([str(x) for x in self.executed_branches])

    def _bytearray_set(self, bs, ind, val):
        if ind < len(bs):
            bs[ind] = val
        else:
            bs.extend(b'\x00'*(ind-len(bs)))
            bs.append(val)

    def generate_inverted_input(self, seed_fn, outdir):
        """
        docstring
        """
        orig:bytearray
        with open(seed_fn, 'rb') as f:
            orig = bytearray(f.read())
        copy = deepcopy(orig)
        with open(join(outdir, '0'), 'wb') as o:
            o.write(orig)

        for EB_branch in self.executed_branches:
            for k, v in EB_branch.inverted_vals.items():
                self._bytearray_set(copy, k, v)
            with open(join(outdir, str(EB_branch.count)), 'wb') as o:
                o.write(copy)
            copy = deepcopy(orig)

    def is_jcc_mod_ok(self, pc_list):
        """
        docstring
        """
        jcc_var_set = {}
        for EB_branch in self.executed_branches:
            if EB_branch.pc in pc_list:
                for var in EB_branch.sym_vars:
                    jcc_var_set[var] = True
            else:
                for var in EB_branch.sym_vars:
                    if var in jcc_var_set:
                        return False
            # print(jcc_var_set, EB_branch.sym_vars)
        return True

if __name__ == '__main__':
    CR_a = ConcolicResult('work/ath9k/drifuzz_path_constraints', 'work/ath9k/drifuzz_index')
    print(CR_a)