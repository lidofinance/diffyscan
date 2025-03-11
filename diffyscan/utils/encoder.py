import re

from .custom_exceptions import EncoderError


def _parse_solidity_int_type(arg_type: str) -> tuple[int, bool]:
    """
    Given a Solidity int/uint type (e.g. 'uint256', 'int128', 'uint', 'int'),
    returns (bits, is_signed).
      - bits = 256 if no explicit size is specified.
      - is_signed = True if it starts with 'int', False if 'uint'.
    """
    match = re.match(r"^(u?int)(\d*)$", arg_type)
    if not match:
        raise EncoderError(f"Invalid integer type format '{arg_type}'.")
    is_signed = not match.group(1).startswith("u")  # 'uint' => False, 'int' => True
    bits_str = match.group(2)
    bits = int(bits_str) if bits_str else 256
    return (bits, is_signed)


def to_hex_with_alignment(value: int) -> str:
    """
    Encodes `value` (non-negative integer) as a 32-byte hex string.
    For negative values, you must first apply two's complement.
    """
    return format(value, "064x")


def encode_int(value: int, bits: int, is_signed: bool) -> str:
    """
    Encodes an integer value (possibly negative if signed) into 32 bytes
    using two's complement for negative values.
    """
    # Convert bool to int if needed (though typically you'd handle bool in a separate branch).
    if isinstance(value, bool):
        value = 1 if value else 0

    # Python's 'format' doesn't automatically do two's-complement for negative integers.
    # So if it's signed and value is negative, convert by adding 2^bits.
    if is_signed and value < 0:
        # e.g. for int256, 2^256 + value
        value = (1 << bits) + value

    # Now ensure it fits within 'bits'
    # (if bits=8, max = 2^7 - 1 for signed or 2^8-1 for unsigned).
    # We'll skip a strict bounds check for brevity, but you could raise an error
    # if abs(value) >= 2^(bits-1) for signed or value >= 2^bits for unsigned.

    return to_hex_with_alignment(value)


def encode_address(address: str) -> str:
    """
    Encodes an address as a 32-byte hex string.
    Assumes 'address' is already a hex string (with '0x' or without).
    """
    address_no_0x = address.lower().replace("0x", "")
    # Convert to int
    number = int(address_no_0x, 16)
    return to_hex_with_alignment(number)


def encode_fixed_bytes(value: str, length: int) -> str:
    """
    Encodes fixed-length bytes (e.g., bytes1..bytes32) into 32 bytes.
    """
    raw_hex = value.lower().replace("0x", "")
    max_hex_len = length * 2  # each byte => 2 hex chars
    if len(raw_hex) > max_hex_len:
        raise EncoderError(
            f"Provided bytes length exceeds {length} bytes (max {max_hex_len} hex chars)."
        )
    # Right-pad the actual bytes to `length`, then pad to 32 bytes total
    raw_hex = raw_hex.ljust(max_hex_len, "0")
    return raw_hex.ljust(64, "0")


def encode_bytes(data: str) -> str:
    """
    Encodes a dynamic `bytes` value as:
      [ 32-byte length, (N + padded to multiple of 32) bytes data ]
    Naive approach: `data` is a hex string (with or without 0x).
    """
    bytes_str = data.lower().lstrip("0x")
    if not bytes_str:
        # length = 0
        return to_hex_with_alignment(0)

    count_of_bytes_from_hex = len(bytes_str) // 2
    # how many hex chars needed to pad to next 32-byte boundary:
    remainder = len(bytes_str) % 64
    if remainder != 0:
        padding_needed = 64 - remainder
    else:
        padding_needed = 0

    padded_bytes_str = bytes_str + ("0" * padding_needed)

    # first 32 bytes = length, then the data
    return to_hex_with_alignment(count_of_bytes_from_hex) + padded_bytes_str


def encode_tuple(components_abi: list, values: list) -> str:
    """
    Recursively encodes a tuple (struct) with support for dynamic arrays.
    This version splits the tuple into a static part and a dynamic part.
    Dynamic components (like T[] or bytes) are replaced with an offset (relative
    to the start of the dynamic section), and their actual data is appended afterward.

    Note: This is a simplified implementation and may not cover all edge cases not presuming nested dynamic types.
    """
    if len(components_abi) != len(values):
        raise EncoderError(
            f"encode_tuple: mismatch in component count: {len(components_abi)} vs values: {len(values)}"
        )

    static_parts = []
    dynamic_parts = []

    # First, encode each element into a static part (if static) or reserve a placeholder (if dynamic).
    for comp, val in zip(components_abi, values):
        arg_type = comp["type"]

        # Nested tuple: recurse.
        if arg_type == "tuple":
            # (Assumes nested tuples are fully static
            static_parts.append(encode_tuple(comp["components"], val))

        # Dynamic array or dynamic bytes:
        elif arg_type.endswith("[]") or arg_type in ["bytes", "string"]:
            # Reserve a placeholder; dynamic data will be appended.
            static_parts.append(None)
            if arg_type.endswith("[]"):
                # For a dynamic array, the element type is the part before "[]".
                base_type = arg_type[:-2]
                dynamic_parts.append(encode_array(base_type, val))
            elif arg_type == "bytes":
                dynamic_parts.append(encode_bytes(val))
            else:
                raise EncoderError(
                    "encode_tuple: 'string' inside tuple not implemented."
                )

        # Otherwise, treat as a static type.
        elif arg_type == "address":
            static_parts.append(encode_address(val))
        elif arg_type == "bool":
            static_parts.append(to_hex_with_alignment(int(bool(val))))
        elif re.match(r"^(u?int)(\d*)$", arg_type):
            bits, is_signed = _parse_solidity_int_type(arg_type)
            static_parts.append(encode_int(int(val), bits, is_signed))
        elif re.match(r"^bytes(\d+)$", arg_type):
            match_len = re.match(r"^bytes(\d+)$", arg_type)
            num_bytes = int(match_len.group(1))
            static_parts.append(encode_fixed_bytes(val, num_bytes))
        else:
            raise EncoderError(f"Unknown type '{arg_type}' in tuple")

    # Now calculate the static size (each static part is 32 bytes)
    static_size = 32 * len(static_parts)
    dynamic_offset = 0
    # Replace None placeholders with offsets (relative to the beginning of the dynamic section)
    for i in range(len(static_parts)):
        if static_parts[i] is None:
            # The offset is computed as static_size + current dynamic_offset
            static_parts[i] = to_hex_with_alignment(static_size + dynamic_offset)
            # Assume each dynamic part is already 32-byte aligned.
            part_length = len(dynamic_parts.pop(0)) // 2
            # Round up to the next multiple of 32 bytes:
            padded_length = ((part_length + 31) // 32) * 32
            dynamic_offset += padded_length

    # Concatenate static parts and then (re-)concatenate dynamic parts.
    encoded_static = "".join(static_parts)
    # TODO: dynamic parts for this non-nested impl are omitted
    encoded_dynamic = ""

    return encoded_static + encoded_dynamic


def encode_dynamic_type(arg_value: str, argument_index: int):
    """
    Encodes a top-level dynamic `bytes` or array argument as:
      [ offset, ... data in the 'compl_data' section ... ]
    This snippet is naive: for a real array, you'd handle array length + each element.
    """
    # For now, we just handle a raw bytes value in hex form:
    offset_to_start_of_data_part = to_hex_with_alignment((argument_index + 1) * 32)
    encoded_value = encode_bytes(arg_value)
    return offset_to_start_of_data_part, encoded_value


def encode_string(arg_length: int, compl_data: list, arg_value: str):
    """
    Encodes a top-level string argument in the same offset + data approach
    used by 'encode_dynamic_type'. We do:
      [ offset, ... then length + contents in 'compl_data' ... ]
    """
    argument_index = arg_length + len(compl_data)
    encoded_value_bytes = arg_value.encode("utf-8")
    offset_to_start_of_data_part = to_hex_with_alignment(argument_index * 32)
    encoded_value_length = to_hex_with_alignment(len(encoded_value_bytes))
    # We'll pad the actual string data to a multiple of 32
    hex_str = encoded_value_bytes.hex()
    remainder = len(hex_str) % 64
    if remainder != 0:
        padding_needed = 64 - remainder
        hex_str += "0" * padding_needed

    return (
        offset_to_start_of_data_part,
        encoded_value_length,
        hex_str,
    )


def encode_array(element_type: str, elements: list) -> str:
    """
    Encodes a one-dimensional dynamic array of the given element_type:
      - (u)intX, bool, address, or a simple type you already handle
    Returns the concatenated hex string:
      [ 32-byte array length, each element in 32 bytes (or more if necessary) ]
    """
    # 1) Encode array length
    length_hex = to_hex_with_alignment(len(elements))

    # 2) Encode each element
    elements_hex = ""

    # The element_type might be 'address', 'uint256', etc.
    # If it's a nested array, e.g. 'uint256[]', you must do recursion.
    # For simplicity, let's handle only top-level single array of simple types.

    # If it's e.g. 'uint', parse bits, is_signed
    uint_int_match = re.match(r"^(u?int)(\d*)$", element_type)

    for elem in elements:
        if element_type == "address":
            elements_hex += encode_address(elem)

        elif element_type == "bool":
            elements_hex += to_hex_with_alignment(int(bool(elem)))

        elif uint_int_match:
            bits, is_signed = _parse_solidity_int_type(element_type)
            elements_hex += encode_int(int(elem), bits, is_signed)

        else:
            # If you have 'bytes32[]' or something else, handle it:
            bytesN_match = re.match(r"^bytes(\d+)$", element_type)
            if bytesN_match:
                num_bytes = int(bytesN_match.group(1))
                elements_hex += encode_fixed_bytes(elem, num_bytes)
            else:
                # If you want advanced features like nested arrays or strings, you'd do it here
                raise EncoderError(
                    f"encode_array: unhandled element type '{element_type}'"
                )

    return length_hex + elements_hex


def encode_constructor_arguments(constructor_abi: list, constructor_config_args: list):
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

            elif re.match(r"^(u?int)(\d*)$", arg_type):
                bits, is_signed = _parse_solidity_int_type(arg_type)
                constructor_calldata += encode_int(int(arg_value), bits, is_signed)

            elif re.match(r"^bytes(\d+)$", arg_type):
                match_len = re.match(r"^bytes(\d+)$", arg_type)
                num_bytes = int(match_len.group(1))
                constructor_calldata += encode_fixed_bytes(arg_value, num_bytes)

            elif arg_type == "bytes":
                offset, encoded_value = encode_dynamic_type(arg_value, argument_index)
                constructor_calldata += offset
                compl_data.append(encoded_value)

            elif arg_type == "string":
                offset, length_hex, contents_hex = encode_string(
                    arg_length, compl_data, arg_value
                )
                constructor_calldata += offset
                compl_data.append(length_hex)
                compl_data.append(contents_hex)

            elif arg_type == "tuple":
                tuple_abi = constructor_abi[argument_index]["components"]
                constructor_calldata += encode_tuple(tuple_abi, arg_value)

            elif arg_type.endswith("[]"):
                # The "base type" is everything before the final "[]"
                element_type = arg_type[:-2]  # e.g. "uint256" or "address"

                # 1) Write the offset for this dynamic array
                offset_hex = to_hex_with_alignment((argument_index + 1) * 32)
                constructor_calldata += offset_hex

                # 2) Build the array payload: length + each element
                array_payload = encode_array(element_type, arg_value)
                compl_data.append(array_payload)

            else:
                raise EncoderError(
                    f"Unknown or unhandled constructor argument type: {arg_type}"
                )

    except Exception as e:
        raise EncoderError(f"Failed to encode calldata arguments: {e}") from None

    # Finally, append any "completion" data
    for data_part in compl_data:
        constructor_calldata += data_part

    return constructor_calldata
