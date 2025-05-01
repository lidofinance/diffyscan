from .logger import logger
from .encoder import encode_constructor_arguments
from .custom_exceptions import CalldataError


def get_calldata(contract_address_from_config, target_compiled_contract, binary_config):

    raw_calldata_exist = (
        "constructor_calldata" in binary_config
        and contract_address_from_config in binary_config["constructor_calldata"]
    )

    calldata_args_exist = (
        "constructor_args" in binary_config
        and contract_address_from_config in binary_config["constructor_args"]
    )

    if raw_calldata_exist and calldata_args_exist:
        logger.warn(
            "Contract address found in 'constructor_args' and in 'constructor_calldata' in config"
        )
        return None
    if not raw_calldata_exist and not calldata_args_exist:
        logger.warn(
            "Contract address not found in 'constructor_args' and in 'constructor_calldata' in config"
        )
        return None
    if raw_calldata_exist:
        return get_raw_calldata_from_config(contract_address_from_config, binary_config)

    return parse_calldata_from_config(
        contract_address_from_config,
        binary_config["constructor_args"],
        target_compiled_contract,
    )


def get_constructor_abi(target_compiled_contract):
    constructor_abi = None
    try:
        constructor_abi = [
            entry["inputs"]
            for entry in target_compiled_contract["abi"]
            if entry["type"] == "constructor"
        ][0]
    except IndexError:
        logger.okay(
            f"Contract's ABI doesn't have a constructor, calldata calculation skipped"
        )
        return None

    logger.okay(f"Constructor in ABI successfully found")
    return constructor_abi


def get_raw_calldata_from_config(contract_address_from_config, binary_config):
    logger.info(f"Trying to use prepared calldata from config")

    calldata_field = binary_config["constructor_calldata"]
    prepared_calldata_from_config = calldata_field[contract_address_from_config]
    return prepared_calldata_from_config


def parse_calldata_from_config(
    contract_address_from_config, constructor_args, target_compiled_contract
):
    logger.info(f"Trying to parse calldata from config")
    constructor_abi = get_constructor_abi(target_compiled_contract)
    if constructor_abi is None:
        logger.warn("Failed to find ABI constructor in compiled contract")
        return None

    if constructor_args is None:
        logger.warn("Failed to find constructor's args in config")
        return None

    calldata = encode_constructor_arguments(
        constructor_abi, constructor_args[contract_address_from_config]
    )

    return calldata
