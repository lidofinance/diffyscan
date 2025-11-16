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


def _error_no_source_code_and_exit(address: str) -> None:
    """Report that source code is not available and raise an exception."""
    error_msg = f"Source code is not verified or an EOA address: {address}"
    logger.error(error_msg)
    raise ExplorerError(error_msg)


def _get_cache_key(contract_address: str, chain_id: int | None) -> str:
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


def _get_cache_path(cache_key: str) -> str:
    """Get the file path for a cache key."""
    return os.path.join(CACHE_DIR, f"{cache_key}.json")


def _load_from_cache(contract_address: str, chain_id: int | None) -> dict | None:
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


def _save_to_cache(
    contract_address: str, chain_id: int | None, contract_data: dict
) -> None:
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


def _get_contract_from_etherscan(
    token: str | None,
    etherscan_hostname: str,
    contract: str,
    chain_id: int | None = None,
) -> dict:
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
        _error_no_source_code_and_exit(contract)

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


def _get_contract_from_zksync(zksync_explorer_hostname: str, contract: str) -> dict:
    zksync_explorer_link = (
        f"https://{zksync_explorer_hostname}/contract_verification/info/{contract}"
    )

    response = fetch(zksync_explorer_link).json()

    if not response.get("verifiedAt"):
        error_msg = f"Contract not verified. Status: {response.get('status_code')}"
        logger.error(error_msg)
        raise ExplorerError(error_msg)

    data = response["request"]
    if "contractName" not in data:
        _error_no_source_code_and_exit(contract)

    contract = {
        "name": data["ContractName"],
        "sources": json.loads(data["sourceCode"]["sources"]),
        "compiler": data["CompilerVersion"],
    }
    return contract


def _get_contract_from_mantle(mantle_explorer_hostname: str, contract: str) -> dict:
    etherscan_link = f"https://{mantle_explorer_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    response = fetch(etherscan_link).json()

    data = response["result"][0]
    if "ContractName" not in data:
        _error_no_source_code_and_exit(contract)

    # Build source files dictionary from the primary file and additional sources
    source_files = {data["FileName"]: {"content": data["SourceCode"]}}
    for entry in data.get("AdditionalSources", []):
        source_files[entry["Filename"]] = {"content": entry["SourceCode"]}

    result = {
        "name": data["ContractName"],
        "solcInput": {
            "language": "Solidity",
            "sources": source_files,
            "settings": {
                "optimizer": {
                    "enabled": data.get("OptimizationUsed", "0") == "1",
                    "runs": int(data.get("Runs", "200")),
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
        "compiler": data["CompilerVersion"],
    }
    return result


def _get_contract_from_blockscout(explorer_hostname: str, contract: str) -> dict:
    explorer_link = f"https://{explorer_hostname}/api/v2/smart-contracts/{contract}"
    response = fetch(explorer_link).json()

    if "name" not in response:
        _error_no_source_code_and_exit(contract)

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


def _get_explorer_fetcher(explorer_hostname: str) -> tuple:
    """
    Determine which fetcher function to use based on the explorer hostname.

    Returns a tuple of (fetcher_function, requires_token)
    """
    if explorer_hostname.startswith("zksync"):
        return _get_contract_from_zksync, False
    elif explorer_hostname.endswith("mantle.xyz"):
        return _get_contract_from_mantle, False
    elif explorer_hostname.endswith("lineascan.build"):
        return (
            lambda hostname, address, token=None, chain_id=None: _get_contract_from_etherscan(
                None, hostname, address, chain_id
            ),
            False,
        )
    elif any(
        explorer_hostname.endswith(domain)
        for domain in [
            "mode.network",
            "blockscout.com",
            "swellnetwork.io",
            "lisk.com",
            "inkonchain.com",
        ]
    ):
        return _get_contract_from_blockscout, False
    else:
        # Default to Etherscan-compatible
        return _get_contract_from_etherscan, True


def _validate_contract_name(
    contract_address: str,
    expected_name: str,
    actual_name: str,
    source: str = "explorer",
) -> None:
    """Validate that the contract name from the source matches the expected name."""
    if actual_name != expected_name:
        raise ExplorerError(
            f"Contract name in config does not match with {source} {contract_address}: "
            f"{expected_name} != {actual_name}"
        )


def get_contract_from_explorer(
    token: str | None,
    explorer_hostname: str,
    contract_address: str,
    contract_name_from_config: str,
    chain_id: int | None = None,
    use_cache: bool = False,
) -> dict:
    # Try to load from cache if enabled
    if use_cache:
        cached_result = _load_from_cache(contract_address, chain_id)
        if cached_result is not None:
            _validate_contract_name(
                contract_address,
                contract_name_from_config,
                cached_result["name"],
                "cached data",
            )
            return cached_result
        else:
            logger.warn(f"No cached explorer contract found for {contract_address}")

    # Fetch from explorer if not cached
    fetcher, requires_token = _get_explorer_fetcher(explorer_hostname)

    if requires_token:
        result = fetcher(token, explorer_hostname, contract_address, chain_id)
    else:
        result = fetcher(explorer_hostname, contract_address)

    _validate_contract_name(
        contract_address,
        contract_name_from_config,
        result["name"],
        "blockchain explorer",
    )

    # Save to cache if enabled
    if use_cache:
        _save_to_cache(contract_address, chain_id, result)

    return result


def compile_contract_from_explorer(
    contract_code: dict, libraries: dict | None = None
) -> dict:
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


def parse_compiled_contract(
    target_compiled_contract: dict,
) -> tuple[str, str, dict[int, int]]:
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


def get_config_value(config: dict, key: str, warn_if_missing: bool = True):
    """
    Get a value from config with optional warning if missing.

    Args:
        config: Configuration dictionary
        key: Key to look up
        warn_if_missing: Whether to warn if the key is not found

    Returns:
        The config value or None if not found
    """
    value = config.get(key)
    if value is None and warn_if_missing:
        logger.warn(f'Failed to find "{key}" in the config')
    return value


def get_explorer_hostname(config: dict) -> str | None:
    """Get explorer hostname from config."""
    return get_config_value(config, "explorer_hostname", warn_if_missing=True)


def get_explorer_chain_id(config: dict) -> int | None:
    """Get explorer chain ID from config."""
    return get_config_value(config, "explorer_chain_id", warn_if_missing=False)
