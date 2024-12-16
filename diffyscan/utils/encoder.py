from .custom_exceptions import EncoderError


def to_hex_with_alignment(value: int) -> str:
    return format(value, "064x")


def encode_address(address: str) -> str:
    number = int(address, 16)
    return to_hex_with_alignment(number)


def encode_bytes32(data: str) -> str:
    return data.replace("0x", "")


def encode_bytes(data: str) -> str:
    bytes_str = data.lstrip("0x")
    if not bytes_str:
        return to_hex_with_alignment(0)

    # Calculate the length of the hex-encoded 32-bytes padded data
    # since EVM uses 32-byte (256-bit) words
    count_of_bytes_from_hex = len(bytes_str) // 2
    encoded_length = 0
    if count_of_bytes_from_hex > 0:
        encoded_length = ((len(bytes_str) - 1) // 64 + 1) * 64
    bytes_str += "0" * (encoded_length - len(bytes_str))
    return to_hex_with_alignment(count_of_bytes_from_hex) + bytes_str


def encode_tuple(types: list, args: list):
    args_length = len(types)
    encoded_offsets = ""
    encoded_data = ""
    for arg_index in range(args_length):
        arg_type = types[arg_index]
        arg_value = args[arg_index]
        if arg_type == "address":
            encoded_offsets += encode_address(arg_value)
        elif arg_type == "uint256" or arg_type == "bool" or arg_type == "uint8":
            encoded_offsets += to_hex_with_alignment(arg_value)
        elif arg_type == "bytes32":
            encoded_offsets += encode_bytes32(arg_value)
        elif arg_type == "address[]" and not arg_value:
            encoded_data += to_hex_with_alignment(0)
            offset = to_hex_with_alignment((arg_index + args_length) * 32)
            encoded_offsets += offset
        else:
            raise EncoderError(
                f"Unknown constructor argument type '{arg_type}' in tuple"
            )
    return encoded_offsets + encoded_data


def encode_dynamic_type(arg_value: str, argument_index: int):
    offset_to_start_of_data_part = to_hex_with_alignment((argument_index + 1) * 32)
    encoded_value = encode_bytes(arg_value)
    return offset_to_start_of_data_part, encoded_value


def encode_string(arg_length: int, compl_data: list, arg_value: str):
    argument_index = arg_length + len(compl_data)
    encoded_value = arg_value.encode("utf-8")
    offset_to_start_of_data_part = to_hex_with_alignment(argument_index * 32)
    encoded_value_length = to_hex_with_alignment(len(encoded_value))
    return (
        offset_to_start_of_data_part,
        encoded_value_length,
        encoded_value.hex().ljust(64, "0"),
    )


def encode_constructor_arguments(constructor_abi: list, constructor_config_args: list):
    # see https://docs.soliditylang.org/en/develop/abi-spec.html#contract-abi-specification
    # transferred from here:
    # https://github.com/lidofinance/lido-dao/blob/master/bytecode-verificator/bytecode_verificator.sh#L369-L405
    arg_length = len(constructor_abi)

    constructor_calldata = ""
    compl_data = []
    try:
        for argument_index in range(arg_length):
            arg_type = constructor_abi[argument_index]["type"]
            arg_value = constructor_config_args[argument_index]
            if arg_type == "address":
                constructor_calldata += encode_address(arg_value)
            elif (
                arg_type == "uint256"
                or arg_type == "bool"
                or arg_type == "uint8"
                or arg_type == "uint32"
            ):
                constructor_calldata += to_hex_with_alignment(arg_value)
            elif arg_type == "bytes32":
                constructor_calldata += encode_bytes32(arg_value)
            elif arg_type == "bytes" or arg_type.endswith("[]"):
                offset_to_start_of_data_part, encoded_value = encode_dynamic_type(
                    arg_value, argument_index
                )
                constructor_calldata += offset_to_start_of_data_part
                compl_data.append(encoded_value)
            elif arg_type == "string":
                offset_to_start_of_data_part, encoded_value_length, encoded_value = (
                    encode_string(arg_length, compl_data, arg_value)
                )
                constructor_calldata += offset_to_start_of_data_part
                compl_data.append(encoded_value_length)
                compl_data.append(encoded_value)
            elif arg_type == "tuple":
                args_tuple_types = [
                    component["type"]
                    for component in constructor_abi[argument_index]["components"]
                ]
                if all(arg == "address[]" for arg in args_tuple_types):
                    argument_index = len(constructor_calldata) // 64
                    offset_to_start_of_data_part = to_hex_with_alignment(
                        (argument_index + 1) * 32
                    )
                    constructor_calldata += offset_to_start_of_data_part
                    compl_data.append(encode_tuple(args_tuple_types, arg_value))
                else:
                    constructor_calldata += encode_tuple(args_tuple_types, arg_value)
            else:
                raise EncoderError(f"Unknown constructor argument type: {arg_type}")
    except Exception as e:
        raise EncoderError(e) from None
    for offset_to_start_of_data_part in compl_data:
        constructor_calldata += offset_to_start_of_data_part

    return constructor_calldata
