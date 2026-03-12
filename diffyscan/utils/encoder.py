import re

from .custom_exceptions import EncoderError

_INT_RE = re.compile(r"^(u?int)(\d*)$")
_BYTESN_RE = re.compile(r"^bytes(\d+)$")


def to_hex_with_alignment(value: int) -> str:
    """Encode a non-negative integer as a 32-byte (64 hex char) string."""
    return format(value, "064x")


def _parse_int_type(arg_type: str) -> tuple[int, bool]:
    """Parse 'uint256', 'int128', etc. into (bits, is_signed)."""
    m = _INT_RE.match(arg_type)
    if not m:
        raise EncoderError(f"Invalid integer type '{arg_type}'")
    is_signed = not m.group(1).startswith("u")
    bits = int(m.group(2)) if m.group(2) else 256
    return bits, is_signed


def _parse_bytesN(arg_type: str) -> int | None:
    """Return N from 'bytesN' or None if not a fixed-bytes type."""
    m = _BYTESN_RE.match(arg_type)
    return int(m.group(1)) if m else None


def encode_int(value, bits: int, is_signed: bool) -> str:
    """Encode an integer (possibly negative if signed) into 32 bytes via two's complement."""
    if isinstance(value, str):
        value = int(value, 16)
    elif isinstance(value, bool):
        value = int(value)

    if is_signed and value < 0:
        value = (1 << bits) + value

    return to_hex_with_alignment(value)


def encode_address(address: str) -> str:
    """Encode an address as a 32-byte hex string."""
    return to_hex_with_alignment(int(address.lower().replace("0x", ""), 16))


def encode_fixed_bytes(value: str, length: int) -> str:
    """Encode fixed-length bytes (bytes1..bytes32) right-padded to 32 bytes."""
    raw = value.lower().replace("0x", "")
    max_len = length * 2
    if len(raw) > max_len:
        raise EncoderError(
            f"Bytes value exceeds {length} bytes (max {max_len} hex chars)"
        )
    return raw.ljust(max_len, "0").ljust(64, "0")


def encode_bytes(data: str) -> str:
    """Encode dynamic `bytes` as [32-byte length, padded data]."""
    raw = data.lower().lstrip("0x")
    if not raw:
        return to_hex_with_alignment(0)

    byte_count = len(raw) // 2
    padding = (64 - len(raw) % 64) % 64
    return to_hex_with_alignment(byte_count) + raw + "0" * padding


def _encode_static_value(arg_type: str, val) -> str:
    """Encode a single static ABI value (address, bool, intN, bytesN)."""
    if arg_type == "address":
        return encode_address(val)
    if arg_type == "bool":
        return to_hex_with_alignment(int(bool(val)))

    if _INT_RE.match(arg_type):
        bits, is_signed = _parse_int_type(arg_type)
        return encode_int(
            int(val) if not isinstance(val, str) else val, bits, is_signed
        )

    n = _parse_bytesN(arg_type)
    if n is not None:
        return encode_fixed_bytes(val, n)

    raise EncoderError(f"Unknown static type '{arg_type}'")


def encode_tuple(components_abi: list, values: list) -> str:
    """Recursively encode a tuple (struct) with static and dynamic parts."""
    if len(components_abi) != len(values):
        raise EncoderError(
            f"Tuple component count mismatch: {len(components_abi)} vs {len(values)}"
        )

    static_parts = []
    dynamic_parts = []

    for comp, val in zip(components_abi, values):
        t = comp["type"]

        if t == "tuple":
            static_parts.append(encode_tuple(comp["components"], val))
        elif t.endswith("[]") or t in ("bytes", "string"):
            static_parts.append(None)  # placeholder for offset
            if t.endswith("[]"):
                dynamic_parts.append(encode_array(t[:-2], val))
            elif t == "bytes":
                dynamic_parts.append(encode_bytes(val))
            else:
                raise EncoderError("'string' inside tuple not implemented")
        else:
            static_parts.append(_encode_static_value(t, val))

    # Replace None placeholders with offsets
    static_size = 32 * len(static_parts)
    dynamic_offset = 0
    dynamic_iter = iter(dynamic_parts)

    for i, part in enumerate(static_parts):
        if part is None:
            static_parts[i] = to_hex_with_alignment(static_size + dynamic_offset)
            dyn = next(dynamic_iter)
            dynamic_offset += ((len(dyn) // 2 + 31) // 32) * 32

    return "".join(static_parts) + "".join(dynamic_parts)


def encode_dynamic_type(arg_value: str, argument_index: int):
    """Encode a top-level dynamic `bytes` argument as (offset, encoded_data)."""
    offset = to_hex_with_alignment((argument_index + 1) * 32)
    return offset, encode_bytes(arg_value)


def encode_string(arg_length: int, compl_data: list, arg_value: str):
    """Encode a top-level string argument as (offset, length_hex, contents_hex)."""
    argument_index = arg_length + len(compl_data)
    encoded = arg_value.encode("utf-8")
    hex_str = encoded.hex()
    padding = (64 - len(hex_str) % 64) % 64

    return (
        to_hex_with_alignment(argument_index * 32),
        to_hex_with_alignment(len(encoded)),
        hex_str + "0" * padding,
    )


def encode_array(element_type: str, elements: list) -> str:
    """Encode a one-dimensional dynamic array of a simple element type."""
    parts = [to_hex_with_alignment(len(elements))]

    for elem in elements:
        parts.append(_encode_static_value(element_type, elem))

    return "".join(parts)


def encode_constructor_arguments(
    constructor_abi: list, constructor_config_args: list
) -> str:
    """Encode constructor arguments according to ABI specification."""
    calldata_parts = []
    compl_data = []

    try:
        for i, abi_entry in enumerate(constructor_abi):
            arg_type = abi_entry["type"]
            arg_value = constructor_config_args[i]

            if arg_type in ("bytes",):
                offset, encoded = encode_dynamic_type(arg_value, i)
                calldata_parts.append(offset)
                compl_data.append(encoded)

            elif arg_type == "string":
                offset, length_hex, contents = encode_string(
                    len(constructor_abi), compl_data, arg_value
                )
                calldata_parts.append(offset)
                compl_data.extend([length_hex, contents])

            elif arg_type == "tuple":
                calldata_parts.append(encode_tuple(abi_entry["components"], arg_value))

            elif arg_type.endswith("[]"):
                calldata_parts.append(to_hex_with_alignment((i + 1) * 32))
                compl_data.append(encode_array(arg_type[:-2], arg_value))

            else:
                calldata_parts.append(_encode_static_value(arg_type, arg_value))

    except Exception as e:
        raise EncoderError(f"Failed to encode calldata: {e}") from None

    return "".join(calldata_parts) + "".join(compl_data)
