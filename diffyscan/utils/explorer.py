import json
import sys

from .common import fetch
from .logger import logger


def _errorNoSourceCodeAndExit(address):
    logger.error("source code is not verified or an EOA address", address)
    sys.exit(1)


def _get_contract_from_etherscan(token, etherscan_hostname, contract):
    etherscan_link = (
      f"https://{etherscan_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    )
    if token is not None:
        etherscan_link = f"{etherscan_link}&apikey={token}"

    response = fetch(etherscan_link).json()

    if response["message"] == "NOTOK":
        raise ValueError(response["result"])

    result = response["result"][0]
    if "ContractName" not in result:
        _errorNoSourceCodeAndExit(contract)

    solc_input = result['SourceCode']

    if solc_input.startswith('{{'):
        return {
            'name': result['ContractName'],
            'solcInput': json.loads(solc_input[1:-1]),
            'compiler': result['CompilerVersion']
        }
    else:
        return {
            'name': result['ContractName'],
            'compiler': result['CompilerVersion'],
            'solcInput': {
                'language': 'Solidity',
                'sources': {
                    result['ContractName']: {
                        'content': solc_input
                    }
                },
                'settings': {
                    'optimizer': {
                        'enabled': result['OptimizationUsed'] == '1',
                        'runs': int(result['Runs'])
                    },
                    'outputSelection': {
                        '*': {
                            '*': [
                                'abi',
                                'evm.bytecode',
                                'evm.deployedBytecode',
                                'evm.methodIdentifiers',
                                'metadata'
                            ],
                            '': ['ast']
                        }
                    }
                }
            }
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
        'name': data['ContractName'],
        'sources': json.loads(data["sourceCode"]["sources"]),
        'compiler': data["CompilerVersion"]
    }

def _get_contract_from_mantle(mantle_explorer_hostname, contract):
    etherscan_link = (
      f"https://{mantle_explorer_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    )
    response = fetch(etherscan_link).json

    data = response["result"][0]
    if "ContractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    source_files = [(data["FileName"], {"content": data["SourceCode"]})]
    for entry in data.get("AdditionalSources", []):
        source_files.append((entry["Filename"], {"content": entry["SourceCode"]}))

    return {
        'name': data['ContractName'],
        'sources': json.loads(data["sourceCode"]["sources"]),
        'compiler': data["CompilerVersion"]
    }

def get_contract_from_explorer(token, explorer_hostname, contract_address, contract_name_from_config):
    result = {}
    if explorer_hostname.startswith("zksync"):
        result = _get_contract_from_zksync(explorer_hostname, contract_address)
    elif explorer_hostname.endswith("mantle.xyz"):
        result = _get_contract_from_mantle(explorer_hostname, contract_address)
    elif explorer_hostname.endswith("lineascan.build"):
        result = _get_contract_from_etherscan(None, explorer_hostname, contract_address)
    else:
        result =_get_contract_from_etherscan(token, explorer_hostname, contract_address)
  
    contract_name_from_etherscan = result['name']
    if contract_name_from_etherscan != contract_name_from_config:
      raise ValueError(
          f"Contract name in config does not match with Blockchain explorer {contract_address}: {contract_name_from_config} != {contract_name_from_etherscan}",
      )
    
    return result
