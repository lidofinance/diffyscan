import hashlib
import subprocess
import json
import os
import stat


from utils.common import fetch, pull, get_solc_native_platform_from_os
from utils.helpers import create_dirs
from utils.logger import logger

RPC_URL = os.getenv('RPC_URL', '')
if not RPC_URL:
    raise ValueError('RPC_URL variable is not set')

def get_compiler_info(platform, required_compiler_version):
    compilers_list_url = (
      f'https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/{platform}/list.json'   
    )
    available_compilers_list = fetch(compilers_list_url).json()
    required_build_info = next((compiler for compiler in available_compilers_list['builds'] if compiler['longVersion'] == required_compiler_version), None)

    if not required_build_info:
      raise ValueError(f'Required compiler version for "{platform}" is not found')
    
    return required_build_info

def download_compiler(platform, build_info, destination_path):
    compiler_url = (
                    f'https://binaries.soliditylang.org/{platform}/{build_info["path"]}'
    )
    download_compiler_response = fetch(compiler_url)  

    with open(destination_path, 'wb') as compiler_file:
      compiler_file.write(download_compiler_response.content)
    return download_compiler_response.content
      
def check_compiler_checksum(compiler, valid_checksum):
    compiler_checksum = hashlib.sha256(compiler).hexdigest()
    if compiler_checksum != valid_checksum:
      raise ValueError(f'Bad checksum')
    
def set_compiler_executable(compiler_path):
    compiler_file_rights = os.stat(compiler_path)
    os.chmod(compiler_path, compiler_file_rights.st_mode | stat.S_IEXEC)
    
def compile_contract(compiler_path, input_settings):
    process = subprocess.run([compiler_path,'--standard-json'], input=input_settings.encode(), capture_output=True, check=True, timeout=30)
    return json.loads(process.stdout)

def prepare_compiler(platform, build_info, compiler_path):
    create_dirs(compiler_path)
    compiler_binary = download_compiler(platform, build_info, compiler_path)
    valid_checksum = build_info['sha256'][2:];
    check_compiler_checksum(compiler_binary, valid_checksum)
    set_compiler_executable(compiler_path)

def get_target_contract(compilation_result, target_contract_name):
    contracts = compilation_result['contracts'].values();
    contracts_to_check = []
    for contracts in compilation_result['contracts'].values():
        for name, contract in contracts.items():
            if name == target_contract_name:
                contracts_to_check.append(contract)

    if len(contracts_to_check) != 1:
        raise ValueError('multiple contracts with the same name')

    logger.info('Contracts were successfully compiled. The target contract is ready for matching')

    return contracts_to_check[0]

def get_bytecode_from_etherscan(code):
    platform = get_solc_native_platform_from_os()
    build_name = code["compiler"][1:]
    build_info = get_compiler_info(platform, build_name)
    compilers_dir_path = os.getenv('SOLC_DIR', 'solc')
    compiler_path = os.path.join(compilers_dir_path, build_info['path'])
    
    is_compiler_already_prepared = os.path.isfile(compiler_path)
    
    if not is_compiler_already_prepared:   
      prepare_compiler(platform, build_info, compiler_path)
      
    input_settings = json.dumps(code["solcInput"])
    contract_name = code['name']

    compilation_result = compile_contract(compiler_path, input_settings)

    target_contract = get_target_contract(compilation_result, contract_name)
  
    expected_bytecode = target_contract['evm']['deployedBytecode']['object']
    
    immutables = {}
    if ('immutableReferences' in target_contract['evm']['deployedBytecode']):
      immutable_references = target_contract['evm']['deployedBytecode']['immutableReferences']
      for refs in immutable_references.values():
          for ref in refs:
              immutables[ref['start']] = ref['length'] 
    
    return expected_bytecode, immutables

def get_bytecode_from_blockchain(contract_address):
    logger.info(f'Retrieving the bytecode by contract address "{contract_address}" from the blockchain...')

    payload = json.dumps({'id': 1, 'jsonrpc': '2.0', 'method': 'eth_getCode', 'params': [contract_address, 'latest']})
    sources_url_response = pull(RPC_URL, payload)
    
    sources_url_response_in_json = sources_url_response.json()
    if 'result' in sources_url_response_in_json:
      bytecode = sources_url_response_in_json['result']
    else:
      raise ValueError(f'Failed to find section "result" in response')
    
    logger.okay(f'Bytecode was successfully fetched')
    
    return bytecode


          
OPCODES = {
    0x00: 'STOP', 0x01: 'ADD', 0x02: 'MUL', 0x03: 'SUB', 0x04: 'DIV', 0x05: 'SDIV',
    0x06: 'MOD', 0x07: 'SMOD', 0x08: 'ADDMOD', 0x09: 'MULMOD', 0x0A: 'EXP', 0x0B: 'SIGNEXTEND',
    0x10: 'LT', 0x11: 'GT', 0x12: 'SLT', 0x13: 'SGT', 0x14: 'EQ', 0x15: 'ISZERO', 0x16: 'AND',
    0x17: 'OR', 0x18: 'XOR', 0x19: 'NOT', 0x1A: 'BYTE', 0x1B: 'SHL', 0x1C: 'SHR', 0x1D: 'SAR',
    0x20: 'SHA3',
    0x30: 'ADDRESS', 0x31: 'BALANCE', 0x32: 'ORIGIN', 0x33: 'CALLER',
    0x34: 'CALLVALUE', 0x35: 'CALLDATALOAD', 0x36: 'CALLDATASIZE', 0x37: 'CALLDATACOPY',
    0x38: 'CODESIZE', 0x39: 'CODECOPY', 0x3A: 'GASPRICE', 0x3B: 'EXTCODESIZE',
    0x3C: 'EXTCODECOPY', 0x3D: 'RETURNDATASIZE', 0x3E: 'RETURNDATACOPY', 0x3F: 'EXTCODEHASH',
    0x40: 'BLOCKHASH', 0x41: 'COINBASE', 0x42: 'TIMESTAMP', 0x43: 'NUMBER',
    0x44: 'PREVRANDAO', 0x45: 'GASLIMIT', 0x46: 'CHAINID', 0x47: 'SELFBALANCE', 0x48: 'BASEFEE',
    0x50: 'POP', 0x51: 'MLOAD', 0x52: 'MSTORE', 0x53: 'MSTORE8',
    0x54: 'SLOAD', 0x55: 'SSTORE', 0x56: 'JUMP', 0x57: 'JUMPI',
    0x58: 'PC', 0x59: 'MSIZE', 0x5A: 'GAS', 0x5B: 'JUMPDEST',
    0x5F: 'PUSH0', 0x60: 'PUSH1', 0x61: 'PUSH2', 0x62: 'PUSH3', 0x63: 'PUSH4', 0x64: 'PUSH5',
    0x65: 'PUSH6', 0x66: 'PUSH7', 0x67: 'PUSH8', 0x68: 'PUSH9', 0x69: 'PUSH10', 0x6A: 'PUSH11',
    0x6B: 'PUSH12', 0x6C: 'PUSH13', 0x6D: 'PUSH14', 0x6E: 'PUSH15', 0x6F: 'PUSH16', 0x70: 'PUSH17',
    0x71: 'PUSH18', 0x72: 'PUSH19', 0x73: 'PUSH20', 0x74: 'PUSH21', 0x75: 'PUSH22', 0x76: 'PUSH23',
    0x77: 'PUSH24', 0x78: 'PUSH25', 0x79: 'PUSH26', 0x7A: 'PUSH27', 0x7B: 'PUSH28', 0x7C: 'PUSH29',
    0x7D: 'PUSH30', 0x7E: 'PUSH31', 0x7F: 'PUSH32',
    0x80: 'DUP1', 0x81: 'DUP2', 0x82: 'DUP3', 0x83: 'DUP4',
    0x84: 'DUP5', 0x85: 'DUP6', 0x86: 'DUP7', 0x87: 'DUP8',
    0x88: 'DUP9', 0x89: 'DUP10', 0x8A: 'DUP11', 0x8B: 'DUP12',
    0x8C: 'DUP13', 0x8D: 'DUP14', 0x8E: 'DUP15', 0x8F: 'DUP16',
    0x90: 'SWAP1', 0x91: 'SWAP2', 0x92: 'SWAP3', 0x93: 'SWAP4',
    0x94: 'SWAP5', 0x95: 'SWAP6', 0x96: 'SWAP7', 0x97: 'SWAP8',
    0x98: 'SWAP9', 0x99: 'SWAP10', 0x9A: 'SWAP11', 0x9B: 'SWAP12',
    0x9C: 'SWAP13', 0x9D: 'SWAP14', 0x9E: 'SWAP15', 0x9F: 'SWAP16',
    0xA0: 'LOG0', 0xA1: 'LOG1', 0xA2: 'LOG2', 0xA3: 'LOG3', 0xA4: 'LOG4',
    0xF0: 'CREATE', 0xF1: 'CALL', 0xF2: 'CALLCODE', 0xF3: 'RETURN', 0xF4: 'DELEGATECALL',
    0xF5: 'CREATE2', 0xFA: 'STATICCALL', 0xFD: 'REVERT', 0xFE: 'INVALID', 0xFF: 'SELFDESTRUCT',
}
      
def parse(bytecode):
    instructions = []
    buffer = bytearray.fromhex(bytecode[2:] if bytecode.startswith('0x') else bytecode)
    i = 0
    while i < len(buffer):
        opcode = buffer[i]
        length = 1 + (opcode >= 0x5f and opcode <= 0x7f) * (opcode - 0x5f)
        instructions.append({
            'start': i,
            'length': length,
            'op': {'name': OPCODES.get(opcode, 'INVALID'), 'code': opcode},
            'bytecode': buffer[i:i + length].hex()
        })
        i += length
    return instructions
      
def match(actualBytecode, expectedBytecode, immutables):
    logger.info('Comparing actual code with the expected one:')

    actualInstructions = parse(actualBytecode)
    expectedInstructions = parse(expectedBytecode)
    maxInstructionsCount = max(len(actualInstructions), len(expectedInstructions))

    differences = []
    for i in range(maxInstructionsCount):
        actual = actualInstructions[i] if i < len(actualInstructions) else None
        expected = expectedInstructions[i] if i < len(expectedInstructions) else None
        if not actual and not expected:
            raise ValueError('Invalid instructions data')
        elif actual.get('bytecode') != expected.get('bytecode'):
            differences.append(i)

    if not differences:
        logger.okay(f'Bytecodes are fully matched')
        return
    logger.warn(f'Bytecodes have differences')

    nearLinesCount = 3
    checkpoints = {0, *differences}

    if actualInstructions:
        checkpoints.add(len(actualInstructions) - 1)

    if expectedInstructions:
        checkpoints.add(len(expectedInstructions) - 1)

    for ind in list(checkpoints):
        startIndex = max(0, ind - nearLinesCount)
        lastIndex = min(ind + nearLinesCount, maxInstructionsCount - 1)
        for i in range(startIndex, lastIndex + 1):
            checkpoints.add(i)

    checkpointsArray = sorted(list(checkpoints))

    def hex(index, padStart=2):
        return f'{index:0{padStart}X}'

    def red(text):
        return f'\u001b[31m{text}\x1b[0m'

    def bgRed(text):
        return f'\u001b[37;41m{text}\x1b[0m'

    def green(text):
        return f'\u001b[32m{text}\x1b[0m'

    def bgGreen(text):
        return f'\u001b[37;42m{text}\x1b[0m'

    def bgYellow(text):
        return f'\u001b[37;43m{text}\x1b[0m'

    logger.divider()
    logger.info(f'0000 00 STOP - both expected and actual bytecode instructions match')
    logger.info(f'{bgRed("0x0002")} - the actual bytecode differs')
    logger.info(f'{bgYellow("0x0001")} - the actual bytecode differs on the immutable reference position')
    logger.info(f'{bgGreen("0x0003")} - the expected bytecode value when it doesn\'t match the actual one')
    logger.info(f'{red("0000 00 STOP")} - the actual bytecode instruction doesn\'t exist, but expected is present')
    logger.info(f'{green("0000 00 STOP")} - the actual bytecode instruction exists when the expected doesn\'t')
    logger.divider()
    for i in range(len(checkpointsArray)):
        currInd = checkpointsArray[i]
        prevInd = checkpointsArray[i - 1] if i > 0 else None
        if prevInd and prevInd != currInd - 1:
            print('...')

        actual = actualInstructions[currInd] if currInd < len(actualInstructions) else None
        expected = expectedInstructions[currInd] if currInd < len(expectedInstructions) else None

        if not actual and expected:
            params = '0x' + expected['bytecode'][2:]
            print(red(f'{hex(currInd, 4)} {hex(expected["op"]["code"])} {expected["op"]["name"]} {params}'))
        elif actual and not expected:
            params = '0x' + actual['bytecode'][2:]
            print(green(f'{hex(currInd, 4)} {hex(actual["op"]["code"])} {actual["op"]["name"]} {params}'))
        elif actual and expected:
            opcode = hex(actual["op"]["code"]) if actual["op"]["code"] == expected["op"]["code"] else bgRed(hex(actual["op"]["code"])) + ' ' + bgGreen(hex(expected["op"]["code"]))
            opname = actual["op"]["name"] if actual["op"]["name"] == expected["op"]["name"] else bgRed(actual["op"]["name"]) + ' ' + bgGreen(expected["op"]["name"])
            actualParams = '0x' + actual['bytecode'][2:] if len(actual['bytecode']) > 2 else ''
            expectedParams = '0x' + expected['bytecode'][2:] if len(expected['bytecode']) > 2 else ''

            paramsLength = len(expected['bytecode']) // 2 - 1
            isImmutable = immutables.get(expected['start'] + 1) == paramsLength
            params = actualParams if actualParams == expectedParams else (bgYellow(actualParams) + ' ' + bgGreen(expectedParams) if isImmutable else bgRed(actualParams) + ' ' + bgGreen(expectedParams))
            print(f'{hex(currInd, 4)} {opcode} {opname} {params}')
        else:
            raise ValueError('Invalid bytecode difference data')

def parse(bytecode):
  buffer = bytes.fromhex(bytecode[2:] if bytecode.startswith('0x') else bytecode)
  instructions = []
  i = 0
  while i < len(buffer):
      opcode = buffer[i]
      length = 1 + (opcode - 0x5f if 0x5f <= opcode <= 0x7f else 0)
      instructions.append({
          'start': i,
          'length': length,
          'op': {'name': OPCODES.get(opcode, 'INVALID'), 'code': opcode},
          'bytecode': buffer[i:i+length].hex()
      })
      i += length
  return instructions