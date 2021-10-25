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

    self._operations = [opcodes[op] for op in selection]

  def generate(self, fullCsv=False, count=1, gasLimit=10000, seed=None):
    """
    Main entrypoint of the CLI tool. Should dispatch to the desired generation routine and print
    programs to STDOUT

    Parameters:
    fullCsv (boolean): if set, will generate programs with accompanying data in CSV format
    count (int): the number of programs
    gasLimit(int): the gas limit for a single program
    seed: a seed for random number generator, if None then default behaviour for random()
    """

    if seed:
      random.seed(a=seed, version=2)

    programs = []
    for i in range(count):
      program = self._generate_random_arithmetic(gasLimit)
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

  def _generate_random_arithmetic(self, gasLimit):
    """
    Generates one large programs with multiple arithmetic operations
    """
    # generated bytecode
    bytecode = self._random_push32()
    # number of operations including pushes
    ops_count = 1
    # gas used
    gas = 3
    # constant list of arithmetic operations
    arithmetic_ops = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09]
    while gas < gasLimit:
      op = random.choice(arithmetic_ops)
      operation = self._operations[op]
      # one value is always on the stack
      needed_pushes = int(operation['Removed from stack']) - 1
      # i.e. 23 from 0x23
      opcode = operation['Value'][2:4]
      for i in range(needed_pushes):
        bytecode += self._random_push32()
      bytecode += opcode
      ops_count += needed_pushes + 1
      # push goes for 3
      gas += 3 * needed_pushes + int(operation['Gas Used'])
    return Program(bytecode, ops_count)

  def _random_push32(self):
    value = random.getrandbits(256)
    value = hex(value)
    value = value[2:]
    if len(value) < 64:
      value = (64-len(value))*'0' + value
    return '7f' + value

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
