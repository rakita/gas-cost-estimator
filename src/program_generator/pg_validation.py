from distutils.command.clean import clean
import os
import csv
import fire
import sys
import random

import constants
from common import prepare_opcodes, get_selection, initial_mstore_bytecode, arity, jump_opcode_combo, byte_size_push


dir_path = os.path.dirname(os.path.realpath(__file__))


class Program(object):
  """
  POD object for a program
  """

  def __init__(self, bytecode, dominant):
    self.bytecode = bytecode
    self.dominant = dominant


class ProgramGenerator(object):
  """
  Sample program generator for EVM instrumentation

  If used with `--fullCsv`, will print out a CSV in the following format:
  ```
  | program_id | opcode_measured | measured_op_position | bytecode |
  ```

  A sample usage `python3 program_generator/pg_validation.py generate --count=2 --opsLimit=100 --seed=123123123`

  NOTE: `measured_op_position` doesn't take into account the specific instructions fired before the
  generated part starts executing. It is relative to the first instruction of the _generated_ part
  of the program. E.g.: `evmone` prepends `JUMPDESTI`, `openethereum_ewasm` prepends many instructions
  """

  def __init__(self, seed=0):
    random.seed(a=seed, version=2)

    opcodes = prepare_opcodes(os.path.join(dir_path, 'data', 'opcodes.csv'))
    selection = get_selection(os.path.join(dir_path, 'data', 'selection.csv'))

    self._operations = {int(op, 16): opcodes[op] for op in selection}

  # constant list of arithmetic operations
  arithmetic_ops = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09]  # ADD MUL SUB DIV SDIV MOD SMOD ADDMOD MULMOD
  exp_ops = [0x0a]  # EXP
  bitwise_ops = [0x16, 0x17, 0x18, 0x19]  # AND OR XOR NOT
  byte_ops = [0x1a, 0x0b]  # BYTE SIGNEXTEND
  shift_ops = [0x1b, 0x1c, 0x1d]  # SHL, SHR, SAR
  comparison_ops = [0x10, 0x11, 0x12, 0x13, 0x14]  # LT, GT, SLT, SGT, EQ
  iszero_ops = [0x15]  # ISZERO
  # ADDRESS, ORIGIN, CALLER, CALLVALUE, CODESIZE, GASPRICE, COINBASE, TIMESTAMP, NUMBER
  # DIFFICULTY, GASLIMIT, CHAINID, SELFBALANCE, PC, MSIZE, GAS
  simple_nullary_ops = [0x30, 0x32, 0x33, 0x34, 0x38, 0x3a, 0x41, 0x42, 0x43,
                        0x44, 0x45, 0x46, 0x47, 0x58, 0x59, 0x5a]
  pop_ops = [0x50]
  jumpdest_ops = [0x5b]  # JUMPDEST

  push_ops = [0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f]
  dup_ops = [0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f]
  swap_ops = [0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f]

  # CALLDATALOAD, CALLDATASIZE, CALLDATACOPY, CODECOPY, MLOAD
  memory_ops = [0x35, 0x36, 0x37, 0x39, 0x51]

  mstore_ops = [0x52, 0x53]  # MSTORE, MSTORE8
  jump_ops = [0x56, 0x57]  # JUMP, JUMPI
  returndata_ops = [0x3d]  # RETURNDATASIZE

  all_ops = []
  all_ops.extend(arithmetic_ops)
  all_ops.extend(exp_ops)
  all_ops.extend(bitwise_ops)
  all_ops.extend(byte_ops)
  all_ops.extend(shift_ops)
  all_ops.extend(comparison_ops)
  all_ops.extend(iszero_ops)
  all_ops.extend(simple_nullary_ops)
  all_ops.extend(pop_ops)
  all_ops.extend(jumpdest_ops)
  all_ops.extend(memory_ops)
  all_ops.extend(jump_ops)
  all_ops.extend(mstore_ops)
  all_ops.extend(returndata_ops)
  # PUSHes DUPs and SWAPs overwhelm the others if treated equally. We pick the class with probability as any
  # other OPCODE, and then the variant is drawn in a subsequent `random.choice` with equal probability.
  all_ops.append("PUSHclass")
  all_ops.append("DUPclass")
  all_ops.append("SWAPclass")

  def _resolve_op_class(self, op):

    if op == "PUSHclass":
      return random.choice(ProgramGenerator.push_ops)  
    elif op == "DUPclass":
      return random.choice(ProgramGenerator.dup_ops)
    elif op == "SWAPclass":
      return random.choice(ProgramGenerator.swap_ops)
    else:
      return op

  def generate(self, fullCsv=False, count=1, opsLimit=None, bytecodeLimit=None, dominant=None, push=32, cleanStack=False, randomizePush=False, randomizeOpsLimit=False):
    """
    Main entrypoint of the CLI tool. Should dispatch to the desired generation routine and print
    programs to STDOUT. If no limits given then by default opsLimit=100

    Parameters:
    fullCsv (boolean): if set, will generate programs with accompanying data in CSV format
    count (int): the number of programs 
    opsLimit (int): the limit operations for a single program, including pushes as one
    randomizeOpsLimit (boolean): whether the limit of operations should be randomized, up to the value of opsLimit
    bytecodeLimit (int): the bytecode limit of a single program
    dominant: an opcode that is picked more often then others, probability ~0.5
    push: the range of default push used in the program, values 1..32, assign ops push1..push32
    randomizePush: whether size of arguments should be randomized, up to the value of push
    cleanStack: whether to clean stack after every opcode or not, default is not
    """
    
    if not opsLimit and not bytecodeLimit:
      opsLimit = 100

    opsLimitMax = opsLimit

    if dominant and dominant != 'random' and dominant not in ProgramGenerator.all_ops:
      raise ValueError(dominant)
    
    dominant_choice = dominant

    programs = []
    for i in range(count):
      if randomizeOpsLimit:
        opsLimit = random.randint(1, opsLimitMax)
      else:
        opsLimit = opsLimitMax

      if dominant_choice == 'random':
        dominant = random.choice(ProgramGenerator.all_ops)
        dominant = self._resolve_op_class(dominant)
      else:
        dominant = dominant_choice

      program = self._generate_random_arithmetic(opsLimit, bytecodeLimit, dominant, push, cleanStack, randomizePush)
      programs.append(program)

    if fullCsv:
      writer = csv.writer(sys.stdout, delimiter=',', quotechar='"')

      program_ids = [i for i, program in enumerate(programs)]
      bytecodes = [program.bytecode for program in programs]
      dominants = [program.dominant for program in programs]

      header = ['program_id', 'bytecode', 'dominant']
      writer.writerow(header)

      rows = zip(program_ids, bytecodes, dominants)
      for row in rows:
        writer.writerow(row)
    else:
      for program in programs:
        print(program.bytecode)

  def _generate_random_arithmetic(self, opsLimit, bytecodeLimit, dominant, pushMax, cleanStack, randomizePush):
    """
    Generates one large programs with multiple arithmetic operations
    """

    if pushMax < 1 or pushMax > 32:
      raise ValueError(pushMax)

    # generated bytecode
    bytecode = ''
    # always preallocate memory to avoid uneven amount of allocation later
    bytecode += initial_mstore_bytecode()
    # always include at least one JUMP
    bytecode += jump_opcode_combo(bytecode, "56")
    # number of operations including pushes
    ops_count = 0
    if not cleanStack:
      previous_nreturns = 0

    while (not opsLimit or ops_count < opsLimit) and (not bytecodeLimit or len(bytecode)<2*bytecodeLimit):
      if dominant:
        if random.random() < 0.5:
          op = dominant
        else:
          op = random.choice(ProgramGenerator.all_ops)
      else:
        op = random.choice(ProgramGenerator.all_ops)

      op = self._resolve_op_class(op)

      operation = self._operations[op]
      nreturns = int(operation['Added to stack'])

      # determine how many args we need to push on the stack and push
      # some value have remained on the stack, unless we're in `cleanStack` mode, whereby they had been popped
      needed_pushes = arity(operation) if cleanStack else (arity(operation) - previous_nreturns)
      # i.e. 23 from 0x23
      opcode = operation['Value'][2:4]
      if op in ProgramGenerator.byte_ops:  # BYTE SIGNEXTEND needs 0-31 value on the top of the stack
        bytecode += self._random_push(pushMax, randomizePush) if cleanStack or previous_nreturns == 0 else ""
        bytecode += self._random_push_less_32()
      elif op in ProgramGenerator.shift_ops:  # SHL, SHR, SAR need 0-255 value on the top of the stack
        bytecode += self._random_push(pushMax, randomizePush) if cleanStack or previous_nreturns == 0 else ""
        bytecode += self._random_push(1, False)
      elif op in ProgramGenerator.memory_ops:
        # `cleanStack` is assumed here, otherwise memory OPCODEs might malfunction on arbitrarily large arguments
        assert cleanStack
        # argument btw 0 and 16KB
        bytecode += ''.join([byte_size_push(2, random.randint(0, (1<<14) - 1)) for _ in range(needed_pushes)])
      elif op in ProgramGenerator.mstore_ops:
        # `cleanStack` is assumed here, otherwise memory OPCODEs might malfunction on arbitrarily large arguments
        assert cleanStack
        # first arg is the stored value, then offset
        bytecode += self._random_push(pushMax, randomizePush)
        bytecode += byte_size_push(2, random.randint(0, (1<<14) - 1))
      else:
        # JUMP AND JUMPI are happy to fall in here, as they have their arity (needed pushes) reduced
        # we'll push their destinations later
        bytecode += ''.join([self._random_push(pushMax, randomizePush) for _ in range(needed_pushes)])
      ops_count += needed_pushes

      if op in ProgramGenerator.jump_ops:
        bytecode += jump_opcode_combo(bytecode, opcode)
        ops_count += 3
      else:
        bytecode += opcode
        ops_count += 1

      if op in ProgramGenerator.push_ops:
        bytecode += operation['Parameter']

      # Pop any results to keep the stack clean for the next iteration. Otherwise mark how many returns remain on
      # the stack after the OPCODE executed.
      if cleanStack:
        # empty the stack
        bytecode += '50' * nreturns  # POP
        ops_count += nreturns
      else:
        previous_nreturns = nreturns

    final_unreachable_placeholder = 'unreachable'
    bytecode += final_unreachable_placeholder

    return Program(bytecode, self._operations[dominant]['Mnemonic'] if dominant else None)

  # TODO deprecate in favor of functions from common.py
  def _random_push(self, pushMax, randomizePush):
    if randomizePush:
      push = random.randint(1, pushMax)
    else:
      push = pushMax

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

def main():
  fire.Fire(ProgramGenerator, name='generate')

if __name__ == '__main__':
  main()
