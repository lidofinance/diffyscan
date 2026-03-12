import json
import os
import copy
import re

from .common import fetch, load_cache, save_cache
from .logger import logger
from .compiler import (
    get_solc_native_platform_from_os,
    get_compiler_info,
    prepare_compiler,
    verify_compiler_integrity,
    compile_contracts,
    get_target_compiled_contract,
)
from .constants import SOLC_DIR
from .custom_exceptions import CompileError, ExplorerError

# Cache directory for storing Etherscan sources
CACHE_DIR = os.path.join(os.getcwd(), ".diffyscan_cache")
HEX_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
LIBRARY_REFERENCE_RE = re.compile(r"\blibrary\s+([A-Za-z_][A-Za-z0-9_]*)\b")


def _default_output_selection() -> dict:
    return {
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
    }


def get_solc_sources(solc_input: dict) -> dict:
    return solc_input.get("sources", solc_input)


def _build_source_files(
    primary_path: str,
    primary_source: str,
    additional_sources: list[dict] | None = None,
    *,
    path_key: str,
    content_key: str,
) -> dict[str, dict[str, str]]:
    source_files = {primary_path: {"content": primary_source}}
    for entry in additional_sources or []:
        source_files[entry[path_key]] = {"content": entry[content_key]}
    return source_files


def _build_solc_input(
    source_files: dict[str, dict[str, str]],
    *,
    optimizer_enabled: bool,
    optimizer_runs: int | str,
    settings: dict | None = None,
) -> dict:
    solc_settings = copy.deepcopy(settings or {})
    solc_settings.setdefault(
        "optimizer",
        {
            "enabled": optimizer_enabled,
            "runs": int(optimizer_runs or 0),
        },
    )
    solc_settings["outputSelection"] = _default_output_selection()
    return {
        "language": "Solidity",
        "sources": source_files,
        "settings": solc_settings,
    }


def _build_contract_payload(
    name: str,
    compiler: str,
    solc_input: dict,
    *,
    constructor_arguments: str | None = None,
    evm_version: str | None = None,
    libraries: dict | list | str | None = None,
) -> dict:
    contract = {
        "name": name,
        "compiler": compiler,
        "solcInput": solc_input,
    }
    _attach_contract_metadata(
        contract,
        get_solc_sources(solc_input),
        constructor_arguments,
        evm_version,
        libraries,
    )
    return contract


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
    return os.path.join(CACHE_DIR, f"{cache_key}.json")


def _get_cache_metadata(
    explorer_hostname: str,
    contract_address: str,
    contract_name: str,
    chain_id: int | None,
) -> dict[str, str | int | None]:
    return {
        "schema": "explorer-contract",
        "explorer_hostname": explorer_hostname,
        "contract_address": contract_address.lower(),
        "contract_name": contract_name,
        "chain_id": chain_id,
    }


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

    results = response["result"]
    if not results:
        raise ExplorerError(f"Empty result from explorer API for contract {contract}")
    result = results[0]
    if "ContractName" not in result:
        _error_no_source_code_and_exit(contract)

    solc_input = result["SourceCode"]
    if not isinstance(solc_input, str):
        raise ExplorerError(
            f"Unexpected SourceCode type for {contract}: {type(solc_input).__name__}"
        )
    if solc_input.startswith("{{"):
        parsed_solc_input = json.loads(solc_input[1:-1])
    else:
        source_files = _build_source_files(
            result["ContractName"],
            solc_input,
            path_key="file_path",
            content_key="source_code",
        )
        parsed_solc_input = _build_solc_input(
            source_files,
            optimizer_enabled=result.get("OptimizationUsed") == "1",
            optimizer_runs=result.get("Runs", 0),
        )
    return _build_contract_payload(
        result["ContractName"],
        result["CompilerVersion"],
        parsed_solc_input,
        constructor_arguments=result.get("ConstructorArguments"),
        evm_version=result.get("EVMVersion"),
        libraries=result.get("Library"),
    )


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

    results = response["result"]
    if not results:
        raise ExplorerError(
            f"Empty result from Mantle explorer for contract {contract}"
        )
    data = results[0]
    if "ContractName" not in data:
        _error_no_source_code_and_exit(contract)

    # Build source files dictionary from the primary file and additional sources
    source_files = _build_source_files(
        data["FileName"],
        data["SourceCode"],
        data.get("AdditionalSources"),
        path_key="Filename",
        content_key="SourceCode",
    )
    solc_input = _build_solc_input(
        source_files,
        optimizer_enabled=data.get("OptimizationUsed", "0") == "1",
        optimizer_runs=data.get("Runs", "200"),
    )
    return _build_contract_payload(
        data["ContractName"],
        data["CompilerVersion"],
        solc_input,
        constructor_arguments=data.get("ConstructorArguments"),
        evm_version=data.get("EVMVersion"),
        libraries=data.get("Library"),
    )


def _get_contract_from_blockscout(explorer_hostname: str, contract: str) -> dict:
    explorer_link = f"https://{explorer_hostname}/api/v2/smart-contracts/{contract}"
    response = fetch(explorer_link).json()

    if "name" not in response:
        _error_no_source_code_and_exit(contract)

    if "file_path" not in response or "source_code" not in response:
        raise ExplorerError(
            f"Blockscout response missing file_path or source_code for {contract}"
        )

    source_files = _build_source_files(
        response["file_path"],
        response["source_code"],
        response.get("additional_sources"),
        path_key="file_path",
        content_key="source_code",
    )

    compiler_settings = copy.deepcopy(response.get("compiler_settings") or {})
    optimization_runs = response.get(
        "optimization_runs", response.get("optimizations_runs", 0)
    )
    solc_input = _build_solc_input(
        source_files,
        optimizer_enabled=response.get("optimization_enabled", False),
        optimizer_runs=optimization_runs,
        settings=compiler_settings,
    )
    return _build_contract_payload(
        response["name"],
        response["compiler_version"],
        solc_input,
        constructor_arguments=response.get("constructor_args"),
        evm_version=response.get("evm_version"),
        libraries=response.get("external_libraries"),
    )


def _attach_contract_metadata(
    contract: dict,
    source_files: dict,
    constructor_arguments: str | None,
    evm_version: str | None,
    libraries: dict | list | str | None,
) -> None:
    settings = contract.get("solcInput", {}).get("settings", {})

    normalized_constructor_arguments = _normalize_hex_string(
        constructor_arguments, prefix=False
    )
    if normalized_constructor_arguments is not None:
        contract["constructor_arguments"] = normalized_constructor_arguments

    normalized_evm_version = _normalize_evm_version(
        evm_version or settings.get("evmVersion")
    )
    if normalized_evm_version:
        contract["evm_version"] = normalized_evm_version

    settings_libraries = settings.get("libraries")
    normalized_libraries = merge_libraries(
        _parse_libraries(settings_libraries, source_files),
        _parse_libraries(libraries, source_files),
    )
    if normalized_libraries:
        contract["libraries"] = normalized_libraries


def _normalize_hex_string(value: str | None, prefix: bool = True) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExplorerError(
            f"Expected explorer hex field to be a string, got {type(value).__name__}"
        )

    normalized = value.strip()
    if normalized.startswith("0x"):
        normalized = normalized[2:]

    if normalized == "":
        return ""

    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ExplorerError(f"Explorer metadata is not valid hex: {value}") from exc

    if len(normalized) % 2 != 0:
        normalized = f"0{normalized}"

    return f"0x{normalized}" if prefix else normalized


def _normalize_evm_version(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExplorerError(
            f"Expected evm version to be a string, got {type(value).__name__}"
        )

    normalized = value.strip()
    if not normalized or normalized.lower() == "default":
        return None
    return normalized


def _parse_libraries(
    raw_libraries: dict | list | str | None, source_files: dict
) -> dict[str, dict[str, str]] | None:
    if raw_libraries in (None, "", [], {}):
        return None

    if isinstance(raw_libraries, dict):
        parsed = {}
        for key, value in raw_libraries.items():
            if isinstance(value, dict):
                parsed.setdefault(key, {})
                for lib_name, address in value.items():
                    parsed[key][lib_name] = _normalize_library_address(address)
                continue

            path, lib_name = _parse_qualified_library_name(str(key), source_files)
            parsed.setdefault(path, {})
            parsed[path][lib_name] = _normalize_library_address(value)
        return parsed or None

    if isinstance(raw_libraries, list):
        parsed = {}
        for item in raw_libraries:
            if not isinstance(item, dict):
                raise ExplorerError(
                    f"Unsupported explorer library entry type: {type(item).__name__}"
                )

            library_name = (
                item.get("name")
                or item.get("library_name")
                or item.get("contract_name")
            )
            file_path = item.get("file_path") or item.get("path")
            address = item.get("address") or item.get("contract_address")

            if not library_name or not address:
                raise ExplorerError(
                    f"Explorer library entry is missing name/address: {item}"
                )

            if not file_path:
                file_path = _infer_library_path(str(library_name), source_files)

            parsed.setdefault(str(file_path), {})
            parsed[str(file_path)][str(library_name)] = _normalize_library_address(
                address
            )
        return parsed or None

    if isinstance(raw_libraries, str):
        stripped = raw_libraries.strip()
        if not stripped:
            return None

        if stripped[0] in "[{":
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = None
            if decoded is not None:
                return _parse_libraries(decoded, source_files)

        parsed = {}
        for part in [
            chunk.strip() for chunk in re.split(r"[;,]", stripped) if chunk.strip()
        ]:
            if "=" in part:
                qualified_name, address = part.rsplit("=", 1)
            elif ":" in part:
                qualified_name, address = part.rsplit(":", 1)
            else:
                raise ExplorerError(f"Unsupported library entry: {part}")

            path, lib_name = _parse_qualified_library_name(qualified_name, source_files)
            parsed.setdefault(path, {})
            parsed[path][lib_name] = _normalize_library_address(address)

        return parsed or None

    raise ExplorerError(
        f"Unsupported explorer libraries type: {type(raw_libraries).__name__}"
    )


def _parse_qualified_library_name(
    qualified_name: str, source_files: dict
) -> tuple[str, str]:
    normalized = qualified_name.strip()
    if not normalized:
        raise ExplorerError("Explorer library name is empty")

    if ":" in normalized:
        maybe_path, maybe_lib_name = normalized.rsplit(":", 1)
        if maybe_path in source_files:
            return maybe_path, maybe_lib_name
        if "/" in maybe_path or maybe_path.endswith(".sol"):
            return maybe_path, maybe_lib_name

    return _infer_library_path(normalized, source_files), normalized


def _infer_library_path(library_name: str, source_files: dict) -> str:
    matches = []
    for path, source in source_files.items():
        content = source.get("content", "")
        if not isinstance(content, str):
            continue
        for declared_library_name in LIBRARY_REFERENCE_RE.findall(content):
            if declared_library_name == library_name:
                matches.append(path)
                break

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ExplorerError(
            f"Failed to infer source path for library '{library_name}' from explorer metadata"
        )
    raise ExplorerError(
        f"Multiple source files declare library '{library_name}': {matches}"
    )


def _normalize_library_address(address: str) -> str:
    normalized = _normalize_hex_string(str(address), prefix=True)
    if normalized is None or not HEX_ADDRESS_RE.match(normalized):
        raise ExplorerError(f"Invalid library address in explorer metadata: {address}")
    return normalized


def merge_libraries(
    *library_sets: dict[str, dict[str, str]] | None,
) -> dict[str, dict[str, str]] | None:
    merged = {}
    for library_set in library_sets:
        if not library_set:
            continue
        for path, libraries in library_set.items():
            merged.setdefault(path, {})
            merged[path].update(libraries)

    return merged or None


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
            "routescan.io",
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
    cache_key = _get_cache_key(contract_address, chain_id)
    cache_metadata = _get_cache_metadata(
        explorer_hostname,
        contract_address,
        contract_name_from_config,
        chain_id,
    )

    # Try to load from cache if enabled
    if use_cache:
        cached_result = load_cache(
            _get_cache_path(cache_key),
            "contract",
            cache_key,
            cache_metadata,
        )
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
        save_cache(
            _get_cache_path(cache_key),
            "contract",
            cache_key,
            result,
            cache_metadata,
        )

    return result


def compile_contract_from_explorer(
    contract_code: dict,
    libraries: dict | None = None,
    evm_version: str | None = None,
) -> dict:
    required_platform = get_solc_native_platform_from_os()
    build_name = contract_code["compiler"][1:]
    build_info = get_compiler_info(required_platform, build_name)
    compiler_path = os.path.join(SOLC_DIR, build_info["path"])

    if os.path.isfile(compiler_path):
        try:
            verify_compiler_integrity(compiler_path, build_info)
        except CompileError:
            logger.warn(
                "Cached compiler failed integrity check; re-downloading",
                build_info["path"],
            )
            prepare_compiler(required_platform, build_info, compiler_path)
    else:
        prepare_compiler(required_platform, build_info, compiler_path)

    solc_input = copy.deepcopy(contract_code["solcInput"])

    if "settings" not in solc_input:
        solc_input["settings"] = {}

    # Add libraries to solc input before compilation if provided
    if libraries:
        logger.okay(f"Adding libraries to solc input: {libraries}")
        if "libraries" not in solc_input["settings"]:
            solc_input["settings"]["libraries"] = {}
        for path, library_map in libraries.items():
            solc_input["settings"]["libraries"].setdefault(path, {})
            solc_input["settings"]["libraries"][path].update(library_map)

    if evm_version:
        logger.okay("Using EVM version from explorer metadata", evm_version)
        solc_input["settings"]["evmVersion"] = evm_version

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
