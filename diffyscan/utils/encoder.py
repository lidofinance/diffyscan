import re

from .custom_exceptions import EncoderError


def to_hex_with_alignment(value: int) -> str:
    return format(value, "064x")


def encode_address(address: str) -> str:
    number = int(address, 16)
    return to_hex_with_alignment(number)


def encode_fixed_bytes(value: str, length: int) -> str:
    raw_hex = value.lower().replace("0x", "")
    max_hex_len = length * 2  # each byte is 2 hex chars
    if len(raw_hex) > max_hex_len:
        raise EncoderError(
            f"Provided bytes length exceeds {length} bytes (max {max_hex_len} hex chars)."
        )
    # Right-pad with zeros up to fixed length, then left-pad to 64 hex chars total
    raw_hex = raw_hex.ljust(max_hex_len, "0")  # fill the fixed bytes
    return raw_hex.ljust(64, "0")  # fill up to 32 bytes in total


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
        elif arg_type == "bool":
            encoded_offsets += to_hex_with_alignment(int(bool(arg_value)))
        # Handle any integral type: uint, uint8..uint256, int, int8..int256
        elif re.match(r"^(u?int)(\d*)$", arg_type):
            encoded_offsets += to_hex_with_alignment(arg_value)
        # Handle fixed-length bytes (e.g. bytes1..bytes32)
        elif re.match(r"^bytes(\d+)$", arg_type):
            match_len = re.match(r"^bytes(\d+)$", arg_type)
            num_bytes = int(match_len.group(1))
            encoded_offsets += encode_fixed_bytes(arg_value, num_bytes)
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
            elif arg_type == "bool":
                constructor_calldata += to_hex_with_alignment(int(bool(arg_value)))
            # Handle any integral type: uint, uint8..uint256, int, int8..int256
            elif re.match(r"^(u?int)(\d*)$", arg_type):
                constructor_calldata += to_hex_with_alignment(arg_value)
            # Handle fixed-length bytes (e.g. bytes1..bytes32)
            elif re.match(r"^bytes(\d+)$", arg_type):
                match_len = re.match(r"^bytes(\d+)$", arg_type)
                num_bytes = int(match_len.group(1))
                constructor_calldata += encode_fixed_bytes(arg_value, num_bytes)
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
