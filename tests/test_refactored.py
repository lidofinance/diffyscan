"""Tests safeguarding the refactoring changes."""

import pytest

from diffyscan.utils.encoder import (
    to_hex_with_alignment,
    encode_address,
    encode_int,
    encode_fixed_bytes,
    encode_bytes,
    encode_array,
    _parse_int_type,
    _parse_bytesN,
    _encode_static_value,
)
from diffyscan.utils.calldata import normalize_calldata, _get_constructor_abi
from diffyscan.utils.common import mask_text, parse_repo_link
from diffyscan.utils.constants import PUSH0, PUSH32, OPCODES
from diffyscan.utils.custom_exceptions import CalldataError, EncoderError
from diffyscan.utils.explorer import merge_libraries, get_solc_sources

# --- encoder tests ---


class TestEncoder:
    def test_to_hex_with_alignment(self):
        assert to_hex_with_alignment(0) == "0" * 64
        assert to_hex_with_alignment(1) == "0" * 63 + "1"
        assert to_hex_with_alignment(255) == "0" * 62 + "ff"

    def test_parse_int_type(self):
        assert _parse_int_type("uint256") == (256, False)
        assert _parse_int_type("int128") == (128, True)
        assert _parse_int_type("uint") == (256, False)
        assert _parse_int_type("int") == (256, True)

    def test_parse_int_type_invalid(self):
        with pytest.raises(EncoderError):
            _parse_int_type("string")

    def test_parse_bytesN(self):
        assert _parse_bytesN("bytes32") == 32
        assert _parse_bytesN("bytes1") == 1
        assert _parse_bytesN("bytes") is None
        assert _parse_bytesN("uint256") is None

    def test_encode_address(self):
        result = encode_address("0x0000000000000000000000000000000000000001")
        assert result == "0" * 63 + "1"

    def test_encode_int_positive(self):
        result = encode_int(42, 256, False)
        assert result == "0" * 62 + "2a"

    def test_encode_int_negative_signed(self):
        result = encode_int(-1, 256, True)
        assert result == "f" * 64

    def test_encode_int_from_hex_string(self):
        result = encode_int("ff", 256, False)
        assert result == "0" * 62 + "ff"

    def test_encode_fixed_bytes(self):
        result = encode_fixed_bytes("0xabcd", 2)
        assert result == "abcd" + "0" * 60

    def test_encode_fixed_bytes_too_long(self):
        with pytest.raises(EncoderError):
            encode_fixed_bytes("0xaabbcc", 1)

    def test_encode_bytes_empty(self):
        result = encode_bytes("0x")
        assert result == to_hex_with_alignment(0)

    def test_encode_bytes_data(self):
        result = encode_bytes("0xaabb")
        assert result.startswith(to_hex_with_alignment(2))

    def test_encode_static_value_bool(self):
        assert _encode_static_value("bool", True) == to_hex_with_alignment(1)
        assert _encode_static_value("bool", False) == to_hex_with_alignment(0)

    def test_encode_static_value_unknown(self):
        with pytest.raises(EncoderError):
            _encode_static_value("string", "hello")

    def test_encode_array_addresses(self):
        addrs = [
            "0x0000000000000000000000000000000000000001",
            "0x0000000000000000000000000000000000000002",
        ]
        result = encode_array("address", addrs)
        assert result.startswith(to_hex_with_alignment(2))


# --- calldata tests ---


class TestCalldata:
    def test_normalize_calldata_with_prefix(self):
        assert normalize_calldata("0xaabb") == "aabb"

    def test_normalize_calldata_without_prefix(self):
        assert normalize_calldata("aabb") == "aabb"

    def test_normalize_calldata_empty(self):
        assert normalize_calldata("") == ""
        assert normalize_calldata("0x") == ""

    def test_normalize_calldata_invalid_hex(self):
        with pytest.raises(CalldataError):
            normalize_calldata("xyz")

    def test_normalize_calldata_odd_length(self):
        with pytest.raises(CalldataError):
            normalize_calldata("abc")

    def test_normalize_calldata_not_string(self):
        with pytest.raises(CalldataError):
            normalize_calldata(123)

    def test_get_constructor_abi_found(self):
        contract = {
            "abi": [
                {"type": "function", "name": "foo", "inputs": []},
                {"type": "constructor", "inputs": [{"name": "x", "type": "uint256"}]},
            ]
        }
        result = _get_constructor_abi(contract)
        assert result == [{"name": "x", "type": "uint256"}]

    def test_get_constructor_abi_no_constructor(self):
        contract = {"abi": [{"type": "function", "name": "foo", "inputs": []}]}
        assert _get_constructor_abi(contract) is None

    def test_get_constructor_abi_empty_inputs(self):
        contract = {"abi": [{"type": "constructor", "inputs": []}]}
        assert _get_constructor_abi(contract) is None

    def test_get_constructor_abi_no_abi(self):
        assert _get_constructor_abi({}) is None


# --- common tests ---


class TestCommon:
    def test_mask_text(self):
        assert mask_text("abcdefghij") == "abc****hij"

    def test_mask_text_short(self):
        result = mask_text("ab", show_start=1, show_end=1)
        assert result == "ab"

    def test_parse_repo_link(self):
        url = "https://github.com/user/repo/tree/main/src"
        assert parse_repo_link(url) == "user/repo"

    def test_parse_repo_link_simple(self):
        url = "https://github.com/user/repo"
        assert parse_repo_link(url) == "user/repo"


# --- constants tests ---


class TestConstants:
    def test_push0_value(self):
        assert PUSH0 == 0x5F
        assert OPCODES[PUSH0] == "PUSH0"

    def test_push32_value(self):
        assert PUSH32 == 0x7F
        assert OPCODES[PUSH32] == "PUSH32"


# --- explorer utils tests ---


class TestExplorerUtils:
    def test_merge_libraries_both_none(self):
        assert merge_libraries(None, None) is None

    def test_merge_libraries_one_set(self):
        libs = {"path.sol": {"Lib": "0x1234"}}
        assert merge_libraries(libs, None) == libs

    def test_merge_libraries_merge(self):
        a = {"path.sol": {"LibA": "0x1"}}
        b = {"path.sol": {"LibB": "0x2"}}
        result = merge_libraries(a, b)
        assert result == {"path.sol": {"LibA": "0x1", "LibB": "0x2"}}

    def test_merge_libraries_override(self):
        a = {"path.sol": {"Lib": "0x1"}}
        b = {"path.sol": {"Lib": "0x2"}}
        result = merge_libraries(a, b)
        # Second arg overrides first
        assert result == {"path.sol": {"Lib": "0x2"}}

    def test_get_solc_sources_standard(self):
        solc_input = {"sources": {"a.sol": {}}, "settings": {}}
        assert get_solc_sources(solc_input) == {"a.sol": {}}

    def test_get_solc_sources_fallback(self):
        # When no "sources" key, returns the dict itself
        solc_input = {"Contract": {"content": "..."}}
        assert get_solc_sources(solc_input) == solc_input
