from .logger import logger

def encode_address(address):
    number = int(address, 16)
    formatted_address = f"{number:064x}"
    return formatted_address

def encode_uint256(number):
    return format(number, "064x")

def encode_bytes32(data):
    return data.replace("0x", "")

def encode_bytes(data):
    bytes_str = data.lstrip("0x")
    data_length = len(bytes_str) // 2
    encoded_length = 0
    if data_length > 0:
        encoded_length = ((len(bytes_str) - 1) // 64 + 1) * 64
    bytes_str += "0" * (encoded_length - len(bytes_str))
    return format(data_length, "064x") + bytes_str

def encode_tuple(types, args):
    args_length = len(types)
    encoded_offsets = ""
    encoded_data = ""
    for arg_index in range(args_length):
        arg_type = types[arg_index]
        arg_value = args[arg_index]
        if arg_type == "address":
            encoded_offsets += encode_address(arg_value)
        elif arg_type == "uint256" or arg_type == "bool" or arg_type == 'uint8':
            encoded_offsets += encode_uint256(arg_value)
        elif arg_type == "bytes32":
            encoded_offsets += encode_bytes32(arg_value)
        elif arg_type == "address[]" and not arg_value:
            encoded_data += '0' * 64
            offset = format((arg_index + args_length) * 32, "064x")
            encoded_offsets += offset
        else:
            logger.warn(f"Unknown constructor argument type '{arg_type}', use --constructor-calldata instead")
    return encoded_offsets+encoded_data  

def to_hex_with_alignment(value):
    return format(value, "064x")

def encode_constructor_arguments(constructor_abi, constructor_config_args):
    arg_length = len(constructor_abi)

    logger.info(f"Constructor args types: {[arg['type'] for arg in constructor_abi]}")

    constructor_calldata = ""
    compl_data = []
    if arg_length > 0:
      for argument_index in range(arg_length):
          arg_type = constructor_abi[argument_index]["type"]
          arg_value = constructor_config_args[argument_index]
          if arg_type == "address":
              constructor_calldata += encode_address(arg_value)
          elif arg_type == "uint256" or arg_type == "bool" or arg_type == 'uint8':
              constructor_calldata += encode_uint256(arg_value)
          elif arg_type == "bytes32":
              constructor_calldata += encode_bytes32(arg_value)
          elif arg_type == "bytes":
              data = format((argument_index+1)*32, "064x")
              constructor_calldata+=data
              data2 = encode_bytes(arg_value)
              compl_data.append(data2)
          elif arg_type == "string":
              offset_arg = to_hex_with_alignment((arg_length  + len(compl_data))*32)
              constructor_calldata += offset_arg
              length_arg = to_hex_with_alignment(len(arg_value.encode('utf-8')))
              hex_text = arg_value.encode('utf-8').hex().ljust(64, '0')
              compl_data.append(length_arg)
              compl_data.append(hex_text)
          elif arg_type == "tuple":
              args_tuple_types = [component["type"] for component in constructor_abi[argument_index]["components"]]
              if len(args_tuple_types) and args_tuple_types[0] == "address[]":
                dynamic_type_length = format((len(constructor_calldata)//64 + 1) *32, "064x")
                constructor_calldata += dynamic_type_length
                logger.info(f'dynamic_type_length {dynamic_type_length}')
                compl_data.append(encode_tuple(args_tuple_types, arg_value))
              else:
                constructor_calldata += encode_tuple(args_tuple_types, arg_value)
          elif arg_type.endswith("[]"):
              data = format((argument_index+1)*32, "064x")
              constructor_calldata+=data
              data2 = encode_bytes(arg_value)
              compl_data.append(data2)
          else:
              raise ValueError(f"Unknown constructor argument type: {arg_type}")
      for data in compl_data:
            constructor_calldata += data

    return constructor_calldata
  
