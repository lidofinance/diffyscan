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

# Cache directory for storing Etherscan sources
CACHE_DIR = os.path.join(os.getcwd(), ".diffyscan_cache")


def _errorNoSourceCodeAndExit(address):
    logger.error("source code is not verified or an EOA address", address)
    sys.exit(1)


def _get_cache_key(contract_address, chain_id):
    """
    Generate a unique cache key from contract address and chain ID.

    Args:
        contract_address: The contract address
        chain_id: The chain ID (can be None)

    Returns:
        A string cache key
    """
    # Normalize address to lowercase
    normalized_address = contract_address.lower()

    # Combine with chain_id (use "unknown" if chain_id is None)
    chain_id_str = str(chain_id) if chain_id is not None else "unknown"

    # Create cache key: chainid_address
    return f"{chain_id_str}_{normalized_address}"


def _get_cache_path(cache_key):
    """Get the file path for a cache key."""
    return os.path.join(CACHE_DIR, f"{cache_key}.json")


def _load_from_cache(contract_address, chain_id):
    """
    Load contract data from cache if available.

    Args:
        contract_address: The contract address
        chain_id: The chain ID

    Returns:
        Cached contract data or None if not found
    """
    cache_key = _get_cache_key(contract_address, chain_id)
    cache_path = _get_cache_path(cache_key)

    if os.path.exists(cache_path):
        try:
            logger.info(f"Loading contract from cache: {cache_key}")
            with open(cache_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warn(f"Failed to load from cache: {e}")
            return None
    return None


def _save_to_cache(contract_address, chain_id, contract_data):
    """
    Save contract data to cache.

    Args:
        contract_address: The contract address
        chain_id: The chain ID
        contract_data: The contract data to cache
    """
    cache_key = _get_cache_key(contract_address, chain_id)
    cache_path = _get_cache_path(cache_key)

    try:
        # Create cache directory if it doesn't exist
        os.makedirs(CACHE_DIR, exist_ok=True)

        with open(cache_path, "w") as f:
            json.dump(contract_data, f, indent=2)
        logger.info(f"Saved contract to cache: {cache_key}")
    except Exception as e:
        logger.warn(f"Failed to save to cache: {e}")


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
    use_cache=False,
):
    # Try to load from cache if enabled
    if use_cache:
        cached_result = _load_from_cache(contract_address, chain_id)
        if cached_result is not None:
            # Verify the cached contract name matches config
            contract_name_from_cache = cached_result["name"]
            if contract_name_from_cache != contract_name_from_config:
                raise ExplorerError(
                    f"Contract name in config does not match with cached data {contract_address}: \
                      {contract_name_from_config} != {contract_name_from_cache}",
                )
            return cached_result
        else:
            logger.warn(f"No cached explorer contract found for {contract_address}")

    # Fetch from explorer if not cached
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

    # Save to cache if enabled
    if use_cache:
        _save_to_cache(contract_address, chain_id, result)

    return result


def compile_contract_from_explorer(contract_code, libraries=None):
    required_platform = get_solc_native_platform_from_os()
    build_name = contract_code["compiler"][1:]
    build_info = get_compiler_info(required_platform, build_name)
    compiler_path = os.path.join(SOLC_DIR, build_info["path"])

    is_compiler_already_prepared = os.path.isfile(compiler_path)

    if not is_compiler_already_prepared:
        prepare_compiler(required_platform, build_info, compiler_path)

    solc_input = contract_code["solcInput"]

    # Add libraries to solc input before compilation if provided
    if libraries:
        logger.okay(f"Adding libraries to solc input: {libraries}")
        if "settings" not in solc_input:
            solc_input["settings"] = {}
        if "libraries" not in solc_input["settings"]:
            solc_input["settings"]["libraries"] = {}
        solc_input["settings"]["libraries"].update(libraries)

    input_settings = json.dumps(solc_input)
    compiled_contracts = compile_contracts(compiler_path, input_settings)[
        "contracts"
    ].values()

    target_contract_name = contract_code["name"]
    compiled_contract = get_target_compiled_contract(
        compiled_contracts, target_contract_name
    )

    return compiled_contract


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
