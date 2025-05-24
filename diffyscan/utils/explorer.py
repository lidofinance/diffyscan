import json
import sys
import os

from .common import fetch, load_env
from .logger import logger
from .compiler import (
    get_solc_native_platform_from_os,
    get_compiler_info,
    prepare_compiler,
    compile_contracts,
    get_target_compiled_contract,
)
from .constants import SOLC_DIR
from .custom_exceptions import ExplorerError


def _errorNoSourceCodeAndExit(address):
    logger.error("source code is not verified or an EOA address", address)
    sys.exit(1)


def _get_contract_from_etherscan(token, etherscan_hostname, contract, chain_id=None):
    if chain_id is None:
        etherscan_link = f"https://{etherscan_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    else:
        etherscan_link = f"https://{etherscan_hostname}/v2/api?chainid={chain_id}&module=contract&action=getsourcecode&address={contract}"
    if token is not None:
        etherscan_link = f"{etherscan_link}&apikey={token}"

    response = fetch(etherscan_link).json()

    if response["message"] == "NOTOK":
        raise ExplorerError(f'Received bad response: {response["result"]}')

    result = response["result"][0]
    if "ContractName" not in result:
        _errorNoSourceCodeAndExit(contract)

    solc_input = result["SourceCode"]
    contract = {
        "name": result["ContractName"],
        "compiler": result["CompilerVersion"],
    }
    if solc_input.startswith("{{"):
        contract["solcInput"] = json.loads(solc_input[1:-1])
    else:
        contract["solcInput"] = {
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
        }
    return contract


def _get_contract_from_zksync(zksync_explorer_hostname, contract):
    zksync_explorer_link = (
        f"https://{zksync_explorer_hostname}/contract_verification/info/{contract}"
    )

    response = fetch(zksync_explorer_link).json()

    if not response.get("verifiedAt"):
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)
        sys.exit(1)

    data = response["request"]
    if "contractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    contract = {
        "name": data["ContractName"],
        "sources": json.loads(data["sourceCode"]["sources"]),
        "compiler": data["CompilerVersion"],
    }
    return contract


def _get_contract_from_mantle(mantle_explorer_hostname, contract):
    etherscan_link = f"https://{mantle_explorer_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    response = fetch(etherscan_link).json()

    data = response["result"][0]
    if "ContractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    source_files = [(data["FileName"], {"content": data["SourceCode"]})]
    for entry in data.get("AdditionalSources", []):
        source_files.append((entry["Filename"], {"content": entry["SourceCode"]}))

    contract = {
        "name": data["ContractName"],
        "sources": json.loads(data["sourceCode"]["sources"]),
        "compiler": data["CompilerVersion"],
    }
    return contract


def _get_contract_from_blockscout(explorer_hostname, contract):
    explorer_link = f"https://{explorer_hostname}/api/v2/smart-contracts/{contract}"
    response = fetch(explorer_link).json()

    if "name" not in response:
        _errorNoSourceCodeAndExit(contract)

    source_files = {response["file_path"]: {"content": response["source_code"]}}

    for entry in response.get("additional_sources", []):
        source_files[entry["file_path"]] = {"content": entry["source_code"]}

    contract = {
        "name": response["name"],
        "solcInput": {
            "language": "Solidity",
            "sources": source_files,
            "settings": {
                "optimizer": {
                    "enabled": response["optimization_enabled"],
                    "runs": int(response["optimization_runs"]),
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
        "compiler": response["compiler_version"],
    }
    return contract


def get_contract_from_explorer(
    token,
    explorer_hostname,
    contract_address,
    contract_name_from_config,
    chain_id=None,
):
    result = {}
    if explorer_hostname.startswith("zksync"):
        result = _get_contract_from_zksync(explorer_hostname, contract_address)
    elif explorer_hostname.endswith("mantle.xyz"):
        result = _get_contract_from_mantle(explorer_hostname, contract_address)
    elif explorer_hostname.endswith("lineascan.build"):
        result = _get_contract_from_etherscan(
            None, explorer_hostname, contract_address, chain_id
        )
    elif (
        explorer_hostname.endswith("mode.network")
        or explorer_hostname.endswith("blockscout.com")
        or explorer_hostname.endswith("swellnetwork.io")
        or explorer_hostname.endswith("lisk.com")
    ):
        result = _get_contract_from_blockscout(explorer_hostname, contract_address)
    else:
        result = _get_contract_from_etherscan(
            token, explorer_hostname, contract_address, chain_id
        )

    contract_name_from_etherscan = result["name"]
    if contract_name_from_etherscan != contract_name_from_config:
        raise ExplorerError(
            f"Contract name in config does not match with Blockchain explorer {contract_address}: \
              {contract_name_from_config} != {contract_name_from_etherscan}",
        )

    return result


def compile_contract_from_explorer(contract_code):
    required_platform = get_solc_native_platform_from_os()
    build_name = contract_code["compiler"][1:]
    build_info = get_compiler_info(required_platform, build_name)
    compiler_path = os.path.join(SOLC_DIR, build_info["path"])

    is_compiler_already_prepared = os.path.isfile(compiler_path)

    if not is_compiler_already_prepared:
        prepare_compiler(required_platform, build_info, compiler_path)

    input_settings = json.dumps(contract_code["solcInput"])
    compiled_contracts = compile_contracts(compiler_path, input_settings)[
        "contracts"
    ].values()

    target_contract_name = contract_code["name"]
    return get_target_compiled_contract(compiled_contracts, target_contract_name)


def parse_compiled_contract(target_compiled_contract):
    contract_creation_code_without_calldata = (
        "0x" + target_compiled_contract["evm"]["bytecode"]["object"]
    )
    deployed_bytecode = (
        "0x" + target_compiled_contract["evm"]["deployedBytecode"]["object"]
    )
    immutables = {}
    if "immutableReferences" in target_compiled_contract["evm"]["deployedBytecode"]:
        immutable_references = target_compiled_contract["evm"]["deployedBytecode"][
            "immutableReferences"
        ]
        for refs in immutable_references.values():
            for ref in refs:
                immutables[ref["start"]] = ref["length"]

    return contract_creation_code_without_calldata, deployed_bytecode, immutables


def get_explorer_hostname(config):
    explorer_hostname = None
    if "explorer_hostname" in config:
        explorer_hostname = config["explorer_hostname"]
    else:
        logger.warn(
            'Failed to find explorer hostname in the config ("explorer_hostname")'
        )
    return explorer_hostname


def get_explorer_chain_id(config):
    chain_id = None
    if "explorer_chain_id" in config:
        chain_id = config["explorer_chain_id"]
    return chain_id
