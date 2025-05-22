from .logger import logger
from .encoder import encode_constructor_arguments
from .custom_exceptions import CalldataError


def get_calldata(contract_address_from_config, target_compiled_contract, binary_config):
    constructor_abi = get_constructor_abi(target_compiled_contract)

    if constructor_abi is None:
        logger.info(
            "Contract's ABI doesn't have a constructor, calldata calculation skipped"
        )
        return None
    else:
        logger.okay("Constructor in ABI successfully found")

    raw_calldata_exist = (
        "constructor_calldata" in binary_config
        and contract_address_from_config in binary_config["constructor_calldata"]
    )

    calldata_args_exist = (
        "constructor_args" in binary_config
        and contract_address_from_config in binary_config["constructor_args"]
    )

    if raw_calldata_exist and calldata_args_exist:
        raise CalldataError(
            "Contract address found in 'constructor_args' and in 'constructor_calldata' in config"
        )
    if not raw_calldata_exist and not calldata_args_exist:
        raise CalldataError(
            "Contract address not found in 'constructor_args' and in 'constructor_calldata' in config, but ABI has a constructor"
        )

    if raw_calldata_exist:
        return get_raw_calldata_from_config(contract_address_from_config, binary_config)

    if calldata_args_exist:
        return parse_calldata_from_config(
            contract_address_from_config,
            binary_config["constructor_args"],
            constructor_abi,
        )
    return None


def get_constructor_abi(target_compiled_contract):
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


def get_raw_calldata_from_config(contract_address_from_config, binary_config):
    logger.info("Trying to use prepared calldata from config")

    calldata_field = binary_config["constructor_calldata"]
    prepared_calldata_from_config = calldata_field[contract_address_from_config]
    return prepared_calldata_from_config


def parse_calldata_from_config(
    contract_address_from_config, constructor_args, constructor_abi
):
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
