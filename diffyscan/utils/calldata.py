from .logger import logger
from .encoder import encode_constructor_arguments
from .custom_exceptions import CalldataError


def get_calldata(
    contract_address: str,
    target_compiled_contract: dict,
    binary_config: dict | None = None,
    explorer_constructor_arguments: str | None = None,
) -> str | None:
    """Get constructor calldata from config, explorer metadata, or ABI encoding."""
    constructor_abi = _get_constructor_abi(target_compiled_contract)
    if constructor_abi is None:
        logger.info("No constructor in ABI, calldata calculation skipped")
        return None

    logger.okay("Constructor in ABI successfully found")
    binary_config = binary_config or {}

    # Check manual config sources
    has_raw = (
        "constructor_calldata" in binary_config
        and contract_address in binary_config["constructor_calldata"]
    )
    has_args = (
        "constructor_args" in binary_config
        and contract_address in binary_config["constructor_args"]
    )

    if has_raw and has_args:
        raise CalldataError(
            f"Contract {contract_address} found in both 'constructor_args' and 'constructor_calldata'"
        )

    if has_raw:
        logger.info("Using prepared calldata from config")
        return normalize_calldata(binary_config["constructor_calldata"][contract_address])

    if has_args:
        logger.info("Parsing calldata from config constructor_args")
        calldata = encode_constructor_arguments(
            constructor_abi, binary_config["constructor_args"][contract_address]
        )
        if not calldata:
            raise CalldataError("Encoded constructor calldata is empty")
        return calldata

    if explorer_constructor_arguments is not None:
        logger.info("Using constructor calldata from explorer metadata")
        normalized = normalize_calldata(explorer_constructor_arguments)
        if not normalized:
            raise CalldataError(
                f"Explorer metadata has empty constructor calldata for {contract_address}"
            )
        return normalized

    raise CalldataError(
        f"No constructor calldata found for {contract_address} "
        "(not in config and not in explorer metadata)"
    )


def normalize_calldata(calldata: str) -> str:
    """Normalize raw calldata to a hex string without the 0x prefix."""
    if not isinstance(calldata, str):
        raise CalldataError(
            f"Expected hex string, got {type(calldata).__name__}"
        )

    normalized = calldata.strip().removeprefix("0x")
    if not normalized:
        return ""

    try:
        int(normalized, 16)
    except ValueError as exc:
        raise CalldataError("Constructor calldata is not valid hex") from exc

    if len(normalized) % 2 != 0:
        raise CalldataError("Constructor calldata has odd number of hex chars")

    return normalized


def _get_constructor_abi(compiled_contract: dict) -> list | None:
    """Extract constructor input ABI from a compiled contract, or None if absent."""
    for entry in compiled_contract.get("abi", []):
        if entry.get("type") == "constructor" and entry.get("inputs"):
            return entry["inputs"]
    return None
