import json
import sys

from .common import fetch
from .logger import logger
from .compiler import *
from .constants import SOLC_DIR
from .encoder import encode_constructor_arguments

def _errorNoSourceCodeAndExit(address):
    logger.error("source code is not verified or an EOA address", address)
    sys.exit(1)


def _get_contract_from_etherscan(token, etherscan_hostname, contract):
    etherscan_link = f"https://{etherscan_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    if token is not None:
        etherscan_link = f"{etherscan_link}&apikey={token}"

    response = fetch(etherscan_link).json()

    if response["message"] == "NOTOK":
        raise ValueError(response["result"])

    result = response["result"][0]
    if "ContractName" not in result:
        _errorNoSourceCodeAndExit(contract)

    solc_input = result["SourceCode"]

    if solc_input.startswith("{{"):
        return {
            "name": result["ContractName"],
            "solcInput": json.loads(solc_input[1:-1]),
            "compiler": result["CompilerVersion"],
        }
    else:
        return {
            "name": result["ContractName"],
            "compiler": result["CompilerVersion"],
            "solcInput": {
                "language": "Solidity",
                "sources": {result["ContractName"]: {"content": solc_input}},
                "settings": {
                    "optimizer": {
                        "enabled": result["OptimizationUsed"] == "1",
                        "runs": int(result["Runs"]),
                    },
                    "outputSelection": {
                        "*": {
                            "*": [
                                "abi",
                                "evm.bytecode",
                                "evm.deployedBytecode",
                                "evm.methodIdentifiers",
                                "metadata",
                            ],
                            "": ["ast"],
                        }
                    },
                },
            },
        }


def _get_contract_from_zksync(zksync_explorer_hostname, contract):
    zksync_explorer_link = (
        f"https://{zksync_explorer_hostname}/contract_verification/info/{contract}"
    )

    response = fetch(zksync_explorer_link).json

    if not response.get("verifiedAt"):
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)
        sys.exit(1)

    data = response["request"]
    if "contractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    return {
        "name": data["ContractName"],
        "sources": json.loads(data["sourceCode"]["sources"]),
        "compiler": data["CompilerVersion"],
    }


def _get_contract_from_mantle(mantle_explorer_hostname, contract):
    etherscan_link = f"https://{mantle_explorer_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    response = fetch(etherscan_link).json

    data = response["result"][0]
    if "ContractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    source_files = [(data["FileName"], {"content": data["SourceCode"]})]
    for entry in data.get("AdditionalSources", []):
        source_files.append((entry["Filename"], {"content": entry["SourceCode"]}))

    return {
        "name": data["ContractName"],
        "sources": json.loads(data["sourceCode"]["sources"]),
        "compiler": data["CompilerVersion"],
    }


def _get_contract_from_mode(mode_explorer_hostname, contract):
    mode_explorer_link = (
        f"https://{mode_explorer_hostname}/api/v2/smart-contracts/{contract}"
    )
    response = fetch(mode_explorer_link).json()

    if "name" not in response:
        _errorNoSourceCodeAndExit(contract)

    source_files = {response["file_path"]: {"content": response["source_code"]}}

    for entry in response.get("additional_sources", []):
        source_files[entry["file_path"]] = {"content": entry["source_code"]}

    return {
        "name": response["name"],
        "solcInput": {"language": "Solidity", "sources": source_files},
        "compiler": response["compiler_version"],
    }


def get_contract_from_explorer(
    token, explorer_hostname, contract_address, contract_name_from_config
):
    result = {}
    if explorer_hostname.startswith("zksync"):
        result = _get_contract_from_zksync(explorer_hostname, contract_address)
    elif explorer_hostname.endswith("mantle.xyz"):
        result = _get_contract_from_mantle(explorer_hostname, contract_address)
    elif explorer_hostname.endswith("lineascan.build"):
        result = _get_contract_from_etherscan(None, explorer_hostname, contract_address)
    elif explorer_hostname.endswith("mode.network"):
        result = _get_contract_from_mode(explorer_hostname, contract_address)
    else:
        result = _get_contract_from_etherscan(
            token, explorer_hostname, contract_address
        )

    contract_name_from_etherscan = result["name"]
    if contract_name_from_etherscan != contract_name_from_config:
        raise ValueError(
            f"Contract name in config does not match with Blockchain explorer {contract_address}: {contract_name_from_config} != {contract_name_from_etherscan}",
        )

    return result

def get_code_from_explorer(contract_code, constructor_args, contract_address_from_config):
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
        raise ValueError(f"Failed to find constructor args values {contract_address_from_config}")  
      
    constructor_calldata = None

    if constructor_args is not None and contract_address_from_config in constructor_args:
        constructor_args = constructor_args [contract_address_from_config]
        if constructor_args:
            constructor_calldata = encode_constructor_arguments(constructor_abi, constructor_args)
            return contract_creation_code+constructor_calldata, immutables

    return contract_creation_code, immutables, False
