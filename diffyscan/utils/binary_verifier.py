import hashlib
import subprocess
import json
import os
import stat

from .common import fetch, pull, get_solc_native_platform_from_os
from .helpers import create_dirs
from .logger import *
from .encoder import encode_constructor_arguments
from .constants import SOLC_DIR, OPCODES
    
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

    try:
        with open(destination_path, 'wb') as compiler_file:
            compiler_file.write(download_compiler_response.content)
    except IOError as e:
        raise ValueError(f"Error writing to file: {e}")
    except Exception as e:
        raise ValueError(f"An error occurred: {e}")
    return download_compiler_response.content
      
def check_compiler_checksum(compiler, valid_checksum):
    compiler_checksum = hashlib.sha256(compiler).hexdigest()
    if compiler_checksum != valid_checksum:
      raise ValueError(f'Bad checksum')
    
def set_compiler_executable(compiler_path):
    compiler_file_rights = os.stat(compiler_path)
    os.chmod(compiler_path, compiler_file_rights.st_mode | stat.S_IEXEC)
    
def compile_contracts(compiler_path, input_settings):
    try:
        process = subprocess.run([compiler_path,'--standard-json'], input=input_settings.encode(), capture_output=True, check=True, timeout=30)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Error during subprocess execution: {e}")
    except subprocess.TimeoutExpired as e:
        raise ValueError(f"Process timed out: {e}")
    except Exception as e:
        raise ValueError(f"An unexpected error occurred: {e}")
    return json.loads(process.stdout)

def prepare_compiler(platform, build_info, compiler_path):
    create_dirs(compiler_path)
    compiler_binary = download_compiler(platform, build_info, compiler_path)
    valid_checksum = build_info['sha256'][2:];
    check_compiler_checksum(compiler_binary, valid_checksum)
    set_compiler_executable(compiler_path)

def get_target_compiled_contract(compiled_contracts, target_contract_name):
    contracts_to_check = []
    for contracts in compiled_contracts:
        for name, contract in contracts.items():
            if name == target_contract_name:
                contracts_to_check.append(contract)

    if len(contracts_to_check) != 1:
        raise ValueError('multiple contracts with the same name')

    logger.okay('Contracts were successfully compiled. The target contract is ready for matching')

    return contracts_to_check[0]

def get_contract_creation_code_from_etherscan(contract_code, constructor_args, contract_address_from_config):
    platform = get_solc_native_platform_from_os()
    build_name = contract_code["compiler"][1:]
    build_info = get_compiler_info(platform, build_name)
    compiler_path = os.path.join(SOLC_DIR, build_info['path'])
    
    is_compiler_already_prepared = os.path.isfile(compiler_path)
    
    if not is_compiler_already_prepared:   
      prepare_compiler(platform, build_info, compiler_path)
      
    input_settings = json.dumps(contract_code["solcInput"])   
    compiled_contracts = compile_contracts(compiler_path, input_settings)['contracts'].values()

    target_contract_name = contract_code['name']
    target_compiled_contract = get_target_compiled_contract(compiled_contracts, target_contract_name)

    contract_creation_code = f'0x{target_compiled_contract['evm']['bytecode']['object']}'
    immutables = {}
    if ('immutableReferences' in target_compiled_contract['evm']['deployedBytecode']):
      immutable_references = target_compiled_contract['evm']['deployedBytecode']['immutableReferences']
      for refs in immutable_references.values():
          for ref in refs:
              immutables[ref['start']] = ref['length'] 
    constructor_abi = None
    try:
        constructor_abi = [entry["inputs"] for entry in target_compiled_contract['abi'] if entry["type"] == "constructor"][0]
    except IndexError:
        logger.info(f'Constructor in ABI not found')
        return contract_creation_code, immutables
      
    if contract_address_from_config not in constructor_args:
        raise ValueError(f"Failed to find constructorArgs")  
      
    constructor_calldata = None

    if constructor_args is not None and contract_address_from_config in constructor_args:
        constructor_args = constructor_args [contract_address_from_config]
        if constructor_args:
            constructor_calldata = encode_constructor_arguments(constructor_abi, constructor_args)
            return contract_creation_code+constructor_calldata, immutables

    return contract_creation_code, immutables, False

def get_bytecode(contract_address, rpc_url):
    logger.info(f'Receiving the bytecode from "{rpc_url}" ...')

    payload = json.dumps({'id': 1, 'jsonrpc': '2.0', 'method': 'eth_getCode', 'params': [contract_address, 'latest']})
    
    sources_url_response_in_json = pull(rpc_url, payload).json()
    if 'result' not in sources_url_response_in_json or sources_url_response_in_json['result'] == '0x':
        return None
        
    logger.okay(f'Bytecode was successfully received')
    return sources_url_response_in_json['result']

def get_account(rpc_url):
    logger.info(f'Receiving the account from "{rpc_url}" ...')
   
    payload = json.dumps({'id': 42, 'jsonrpc': '2.0', 'method': 'eth_accounts', 'params': []})
    
    account_address_response = pull(rpc_url, payload).json()
    
    if 'result' not in account_address_response:
      return None

    logger.okay(f'The account was successfully received')

    return account_address_response['result'][0]
  
def deploy_contract(rpc_url, deployer, data): 
  logger.info(f'Trying to deploy transaction to "{rpc_url}" ...')
  
  payload_sendTransaction = json.dumps({
      "jsonrpc": "2.0",
      "method": "eth_sendTransaction",
      "params": [{
          "from": deployer,
          "gas": 9000000,
          "input": data
      }],
      "id": 1
  })
  response_sendTransaction = pull(rpc_url, payload_sendTransaction).json()

  if 'error' in response_sendTransaction:
    return None, response_sendTransaction['error']['message']
  
  logger.okay(f'Transaction was successfully deployed')

  tx_hash = response_sendTransaction['result']
  
  payload_getTransactionReceipt = json.dumps({'id': 1, 'jsonrpc': '2.0', 'method': 'eth_getTransactionReceipt', 'params':[tx_hash]})
  response_getTransactionReceipt = pull(rpc_url, payload_getTransactionReceipt).json()   
  
  if 'result' not in response_getTransactionReceipt or \
    'contractAddress' not in response_getTransactionReceipt['result'] or \
    'status' not in response_getTransactionReceipt['result'] :
      return None, f'Failed to received transaction receipt'

  if response_getTransactionReceipt['result']['status'] != '0x1':
    return None, f'Failed to received transaction receipt. \
  Transaction has been reverted (status 0x0). Input missmatch?'
  
  contract_address = response_getTransactionReceipt['result']['contractAddress']
  
  return contract_address, ''
             
def to_match(actualBytecode, expectedBytecode, immutables, remote_contract_address):
    logger.info('Comparing actual code with the expected one...')

    actualInstructions = parse(actualBytecode)
    expectedInstructions = parse(expectedBytecode)
    maxInstructionsCount = max(len(actualInstructions), len(expectedInstructions))

    differences = []
    for i in range(maxInstructionsCount):
        actual = actualInstructions[i] if i < len(actualInstructions) else None
        expected = expectedInstructions[i] if i < len(expectedInstructions) else None
        if not actual and not expected:
            raise ValueError('Invalid instructions data')
        elif (actual is not None) and (actual.get('bytecode') != expected.get('bytecode')):
            differences.append(i)

    if not differences:
        logger.okay(f'Bytecodes are fully matched (contract {remote_contract_address})')
        return
    logger.warn(f'Bytecodes have differences contract {remote_contract_address})')

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
            print(logger.red(f'{to_hex(currInd, 4)} {to_hex(expected["op"]["code"])} {expected["op"]["name"]} {params}'))
        elif actual and not expected:
            params = '0x' + actual['bytecode'][2:]
            print(logger.green(f'{to_hex(currInd, 4)} {to_hex(actual["op"]["code"])} {actual["op"]["name"]} {params}'))
        elif actual and expected:
            opcode = to_hex(actual["op"]["code"]) if actual["op"]["code"] == expected["op"]["code"] else bgRed(to_hex(actual["op"]["code"])) + ' ' + bgGreen(to_hex(expected["op"]["code"]))
            opname = actual["op"]["name"] if actual["op"]["name"] == expected["op"]["name"] else bgRed(actual["op"]["name"]) + ' ' + bgGreen(expected["op"]["name"])
            actualParams = '0x' + actual['bytecode'][2:] if len(actual['bytecode']) > 2 else ''
            expectedParams = '0x' + expected['bytecode'][2:] if len(expected['bytecode']) > 2 else ''

            paramsLength = len(expected['bytecode']) // 2 - 1
            isImmutable = immutables.get(expected['start'] + 1) == paramsLength
            params = actualParams if actualParams == expectedParams else (bgYellow(actualParams) + ' ' + bgGreen(expectedParams) if isImmutable else bgRed(actualParams) + ' ' + bgGreen(expectedParams))
            print(f'{to_hex(currInd, 4)} {opcode} {opname} {params}')
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
