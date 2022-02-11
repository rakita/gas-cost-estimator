import os
import csv
import fire
import sys
import subprocess
import tempfile
import binascii
import random

import constants

dir_path = os.path.dirname(os.path.realpath(__file__))


class Program(object):
  """
  POD object for a program
  """

  def __init__(self, bytecode, measured_op_position):
    self.bytecode = bytecode
    self.measured_op_position = measured_op_position


class ProgramGenerator(object):
  """
  Sample program generator for EVM instrumentation

  If used with `--fullCsv`, will print out a CSV in the following format:
  ```
  | program_id | opcode_measured | measured_op_position | bytecode |
  ```

  A sample usage `python3 program_generator/pg_arythmetic.py generate --count=2 --gasLimit=100 --seed=123123123`

  NOTE: `measured_op_position` doesn't take into account the specific instructions fired before the
  generated part starts executing. It is relative to the first instruction of the _generated_ part
  of the program. E.g.: `evmone` prepends `JUMPDESTI`, `openethereum_ewasm` prepends many instructions
  """

  def __init__(self):

    opcodes_file = os.path.join(dir_path, 'data', 'opcodes.csv')

    with open(opcodes_file) as csvfile:
      reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
      opcodes = {i['Value']: i for i in reader}

    opcodes = self._fill_opcodes_push_dup_swap(opcodes)

    selection_file = os.path.join(dir_path, 'data', 'selection.csv')

    with open(selection_file) as csvfile:
      reader = csv.DictReader(csvfile, delimiter=' ', quotechar='"')
      selection = [i['Opcode'] for i in reader]

    self._operations = {int(op, 16): opcodes[op] for op in selection}

  def generate(self, fullCsv=False, count=1, gasLimit=None, opsLimit=None, bytecodeLimit=None, seed=0, dominant=None, push=32, cleanStack=False):
    """
    Main entrypoint of the CLI tool. Should dispatch to the desired generation routine and print
    programs to STDOUT. If no limits given then by default opsLimit=100

    Parameters:
    fullCsv (boolean): if set, will generate programs with accompanying data in CSV format
    count (int): the number of programs
    gasLimit (int): the gas limit for a single program
    opsLimit (int): the limit operations for a single program, including pushes as one
    bytecodeLimit (int): the bytecode limit of a single program
    seed: a seed for random number generator, defaults to 0
    dominant: an opcode that is picked more often then others, probability ~0.5
    push: the range of default push used in the program, values 1..32, assign ops push1..push32
    cleanStack: whether to clean stack after every opcode or not, default is not
    """

    random.seed(a=seed, version=2)
    
    if not gasLimit and not opsLimit and not bytecodeLimit:
      opsLimit = 100

    programs = []
    for i in range(count):
      program = self._generate_random_arithmetic(gasLimit, opsLimit, bytecodeLimit, dominant, push, cleanStack)
      programs.append(program)

    if fullCsv:
      writer = csv.writer(sys.stdout, delimiter=',', quotechar='"')

      program_ids = [i for i, program in enumerate(programs)]
      bytecodes = [program.bytecode for program in programs]

      header = ['program_id', 'bytecode']
      writer.writerow(header)

      rows = zip(program_ids, bytecodes)
      for row in rows:
        writer.writerow(row)
    else:
      for program in programs:
        print(program.bytecode)

  def _generate_random_arithmetic(self, gasLimit, opsLimit, bytecodeLimit, dominant, push, cleanStack):
    """
    Generates one large programs with multiple arithmetic operations
    """

    if push < 1 or push > 32:
      raise ValueError(push)

    # generated bytecode
    bytecode = ''
    # number of operations including pushes
    ops_count = 0
    # gas used
    gas = 0
    if not cleanStack:
      # one value should be always on the stack
      bytecode += self._random_push(push)
      ops_count += 1
      gas += 3
    # constant list of arithmetic operations
    arithmetic_ops = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09]  # ADD MUL SUB DIV SDIV MOD SMOD ADDMOD MULMOD
    exp_ops = [0x0a]  # EXP
    bitwise_ops = [0x16, 0x17, 0x18, 0x19]  # AND OR XOR NOT
    byte_ops = [0x1a, 0x0b]  # BYTE SIGNEXTEND
    shift_ops = [0x1b, 0x1c, 0x1d]  # SHL, SHR, SAR
    comparison_ops = [0x10, 0x11, 0x12, 0x13, 0x14]  # LT, GT, SLT, SGT, EQ
    iszero_ops = [0x15]  # ISZERO
    all_ops = []
    all_ops.extend(arithmetic_ops)
    all_ops.extend(exp_ops)
    all_ops.extend(bitwise_ops)
    all_ops.extend(byte_ops)
    all_ops.extend(shift_ops)
    all_ops.extend(comparison_ops)
    all_ops.extend(iszero_ops)

    if dominant and dominant not in all_ops:
      raise ValueError(dominant)

    while (not gasLimit or gas < gasLimit) and (not opsLimit or ops_count < opsLimit) and (not bytecodeLimit or len(bytecode)<2*bytecodeLimit):
      if dominant:
        if random.random() < 0.5:
          op = dominant
        else:
          op = random.choice(all_ops)
      else:
        op = random.choice(all_ops)
      operation = self._operations[op]
      if cleanStack:
        # the stack is empty, put one value there
        bytecode += self._random_push(push)
        ops_count += 1
        gas += 3
      # one value is always on the stack
      needed_pushes = int(operation['Removed from stack']) - 1
      # i.e. 23 from 0x23
      opcode = operation['Value'][2:4]
      if op in arithmetic_ops or op in bitwise_ops or op in comparison_ops:
        for i in range(needed_pushes):
          bytecode += self._random_push(push)
      elif op in exp_ops:
        bytecode += self._random_push(1)  # the exponent less than 256
        bytecode += '90'  # SWAP1 so the exponent is first on the stack
        ops_count += 1   # additional SWAP1 cost
        gas += 3   # additional SWAP1 cost
      elif op in byte_ops:  # BYTE SIGNEXTEND needs 0-31 value on the stack
        bytecode += self._random_push_less_32()
      elif op in shift_ops:  # SHL, SHR, SAR need 0-255 value on the stack
        bytecode += self._random_push(1)
      bytecode += opcode
      ops_count += needed_pushes + 1
      # push goes for 3
      gas += 3 * needed_pushes
      if op in exp_ops:
        gas += 60  # gas cost of EXP with the exponent 0<exponent<256
      else:
        gas += int(operation['Gas Used'])
      if cleanStack:
        # empty the stack
        bytecode += '50'  # POP
        ops_count += 1
        gas += 2
    return Program(bytecode, ops_count)

  def _random_push(self, push):
    value = random.getrandbits(8*push)
    value = hex(value)
    value = value[2:]
    if len(value) < 2*push:
      value = (2*push-len(value))*'0' + value
    op_num = 6 * 16 + push - 1  # 0x60 is PUSH1
    op = hex(op_num)[2:]
    return op + value

  def _random_push_less_32(self):
    value = random.randint(0, 31)
    value = hex(value)
    value = value[2:]
    if len(value) < 2:
      value = (2-len(value))*'0' + value
    return '60' + value

  def _fill_opcodes_push_dup_swap(self, opcodes):
    pushes = constants.EVM_PUSHES
    dups = constants.EVM_DUPS
    swaps = constants.EVM_SWAPS

    pushes = self._opcodes_dict_push_dup_swap(pushes, [0] * len(pushes), [1] * len(pushes), parameter='00')
    opcodes = {**opcodes, **pushes}
    dups = self._opcodes_dict_push_dup_swap(dups, range(1, len(dups)), range(2, len(dups)+1))
    opcodes = {**opcodes, **dups}
    swaps = self._opcodes_dict_push_dup_swap(swaps, range(2, len(swaps)+1), range(2, len(swaps)+1))
    opcodes = {**opcodes, **swaps}
    return opcodes

  def _opcodes_dict_push_dup_swap(self, source, removeds, addeds, parameter=None):
    source_list = source.split()
    opcodes = source_list[::2]
    names = source_list[1::2]
    new_part = {
      opcode: {
        'Value': opcode,
        'Mnemonic': name,
        'Removed from stack': removed,
        'Added to stack': added,
        'Parameter': parameter
      } for opcode, name, removed, added in zip(opcodes, names, removeds, addeds)
    }

    return new_part

def main():
  fire.Fire(ProgramGenerator, name='generate')

if __name__ == '__main__':
  main()
