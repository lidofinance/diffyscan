from .logger import logger
from .encoder import encode_constructor_arguments
from .custom_exceptions import CalldataError

def get_calldata(contract_address_from_config, target_compiled_contract, binary_config):
    calldata = get_raw_calldata_from_config(contract_address_from_config, binary_config)
    if calldata is not None:
          return calldata
       
    calldata = parse_calldata_from_config(
        contract_address_from_config,
        binary_config["constructor_args"],
        target_compiled_contract,
    )

    return calldata
            
def get_constructor_abi(target_compiled_contract):
    constructor_abi = None
    try:
        constructor_abi = [entry["inputs"] for entry in target_compiled_contract['abi'] if entry["type"] == "constructor"][0]
    except IndexError:
        logger.okay(f"Contract's ABI doesn't have a constructor, calldata calculation skipped")
        return None

    logger.okay(f'Constructor in ABI successfully found: {[arg['type'] for arg in constructor_abi]}')
    return constructor_abi

def get_raw_calldata_from_config(contract_address_from_config, binary_config):
    if "constructor_calldata" not in binary_config or contract_address_from_config not in binary_config["constructor_calldata"]:
        return None
    calldata_field = binary_config["constructor_calldata"]
    logger.info(f"Trying to use prepared calldata from config")
    prepared_calldata_from_config = calldata_field[contract_address_from_config]
    return prepared_calldata_from_config
    
def parse_calldata_from_config(contract_address_from_config, constructor_args, target_compiled_contract):    
    logger.info(f"Trying to parse calldata from config")
    constructor_abi = get_constructor_abi(target_compiled_contract)
    if constructor_abi is None:
        raise CalldataError("Failed to find ABI constructor in compiled contract") 
      
    if constructor_args is None:
        raise CalldataError("Failed to find constructor's args in config") 
    
    if contract_address_from_config not in constructor_args:
        raise CalldataError("Failed to find contract calldata in config") 

    calldata = encode_constructor_arguments(constructor_abi, constructor_args [contract_address_from_config])
    
    if not calldata:
        raise CalldataError("Contract calldata is empty") 
          
    return calldata
