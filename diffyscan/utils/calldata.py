from .logger import logger
from .encoder import encode_constructor_arguments
from .custom_exceptions import CalldataError


def _check_calldata_config(
    contract_address: str, binary_config: dict
) -> tuple[bool, bool]:
    """
    Check which calldata configuration method is available and validate consistency.

    Args:
        contract_address: The contract address
        binary_config: Binary comparison configuration

    Returns:
        tuple: (has_raw_calldata, has_args)

    Raises:
        CalldataError: If configuration is invalid
    """
    has_raw = (
        "constructor_calldata" in binary_config
        and contract_address in binary_config["constructor_calldata"]
    )

    has_args = (
        "constructor_args" in binary_config
        and contract_address in binary_config["constructor_args"]
    )

    # Validate: can't have both
    if has_raw and has_args:
        raise CalldataError(
            f"Contract {contract_address} found in both 'constructor_args' and 'constructor_calldata' in config"
        )

    # Validate: must have at least one
    if not has_raw and not has_args:
        raise CalldataError(
            f"Contract {contract_address} not found in 'constructor_args' or 'constructor_calldata' in config, "
            "but ABI has a constructor"
        )

    return has_raw, has_args


def get_calldata(
    contract_address_from_config: str,
    target_compiled_contract: dict,
    binary_config: dict,
) -> str | None:
    """
    Get constructor calldata from config or encode from constructor arguments.

    Args:
        contract_address_from_config: The contract address
        target_compiled_contract: The compiled contract data
        binary_config: Binary comparison configuration

    Returns:
        The encoded calldata or None if no constructor

    Raises:
        CalldataError: If calldata configuration is invalid
    """
    constructor_abi = get_constructor_abi(target_compiled_contract)

    if constructor_abi is None:
        logger.info(
            "Contract's ABI doesn't have a constructor, calldata calculation skipped"
        )
        return None

    logger.okay("Constructor in ABI successfully found")

    has_raw, has_args = _check_calldata_config(
        contract_address_from_config, binary_config
    )

    if has_raw:
        return get_raw_calldata_from_config(contract_address_from_config, binary_config)

    # Must have args if we got here (validation ensures one or the other)
    return parse_calldata_from_config(
        contract_address_from_config,
        binary_config["constructor_args"],
        constructor_abi,
    )


def get_constructor_abi(target_compiled_contract: dict) -> list | None:
    """
    Extract constructor ABI from compiled contract.

    Args:
        target_compiled_contract: The compiled contract data

    Returns:
        The constructor inputs list or None if no constructor
    """
    constructor_abi = None
    try:
        constructor_abi = [
            entry["inputs"]
            for entry in target_compiled_contract["abi"]
            if entry["type"] == "constructor"
        ][0]
    except IndexError:
        return None

    return constructor_abi if len(constructor_abi) > 0 else None


def get_raw_calldata_from_config(
    contract_address_from_config: str, binary_config: dict
) -> str:
    """Get raw calldata from config."""
    logger.info("Trying to use prepared calldata from config")

    calldata_field = binary_config["constructor_calldata"]
    prepared_calldata_from_config = calldata_field[contract_address_from_config]
    return prepared_calldata_from_config


def parse_calldata_from_config(
    contract_address_from_config: str,
    constructor_args: dict,
    constructor_abi: list | None,
) -> str:
    """
    Parse and encode calldata from constructor arguments in config.

    Args:
        contract_address_from_config: The contract address
        constructor_args: Constructor arguments from config
        constructor_abi: Constructor ABI

    Returns:
        The encoded calldata

    Raises:
        CalldataError: If encoding fails
    """
    logger.info("Trying to parse calldata from config")

    constructor_config_args = constructor_args[contract_address_from_config]

    if constructor_abi is None:
        if len(constructor_config_args) > 0:
            raise CalldataError(
                f"Constructor args provided for contract without constructor: {contract_address_from_config}"
            )
        return ""

    calldata = encode_constructor_arguments(constructor_abi, constructor_config_args)

    if not calldata:
        raise CalldataError("Contract calldata is empty")

    return calldata
