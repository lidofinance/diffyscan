import pytest

from diffyscan.utils.binary_verifier import deep_match_bytecode, parse
from diffyscan.utils.constants import OPCODES, PUSH0, PUSH32
from diffyscan.utils.custom_exceptions import BinVerifierError


def test_length_mismatch_raises():
    actual = "0x6001600055fe"
    expected = "0x6001600055fe6001"

    with pytest.raises(BinVerifierError, match="different length"):
        deep_match_bytecode(actual, expected, immutables={})


def test_immutable_only_diff_returns_false():
    actual = "0x6001fe"
    expected = "0x6002fe"

    assert deep_match_bytecode(actual, expected, immutables={1: 1}) is False


def test_non_immutable_diff_raises():
    actual = "0x6001fe"
    expected = "0x6001fd"

    with pytest.raises(BinVerifierError, match="differences not on the immutable"):
        deep_match_bytecode(actual, expected, immutables={})


# --- Opcode parsing ---


@pytest.mark.parametrize(
    "code,name",
    sorted(OPCODES.items()),
    ids=[f"0x{code:02x}_{name}" for code, name in sorted(OPCODES.items())],
)
def test_parse_every_opcode(code, name):
    """Every opcode in the OPCODES table should be parsed without unknown warnings."""
    if PUSH0 <= code <= PUSH32:
        # PUSHn needs n bytes of immediate data after the opcode
        n = code - PUSH0
        bytecode = format(code, "02x") + "00" * n
    else:
        bytecode = format(code, "02x")

    instructions, unknown = parse(bytecode)
    assert unknown == set(), f"opcode 0x{code:02x} ({name}) flagged as unknown"
    assert len(instructions) == 1
    assert instructions[0]["op"]["name"] == name
    assert instructions[0]["op"]["code"] == code


@pytest.mark.parametrize("n", range(0, 33), ids=[f"PUSH{n}" for n in range(0, 33)])
def test_push_consumes_n_bytes(n):
    """PUSH0..PUSH32 should consume exactly 1 + n bytes."""
    code = PUSH0 + n
    immediate = "ab" * n
    bytecode = format(code, "02x") + immediate

    instructions, unknown = parse(bytecode)
    assert unknown == set()
    assert len(instructions) == 1
    assert instructions[0]["length"] == 1 + n
    assert instructions[0]["start"] == 0


def test_parse_unknown_opcode_detected():
    # 0x0C is not a valid EVM opcode
    instructions, unknown = parse("0c")
    assert unknown == {"0xc"}
    assert instructions[0]["op"]["name"] == "INVALID"


def test_parse_mixed_sequence():
    # STOP, ADD, PUSH1 0xff, TLOAD, MCOPY, BLOBHASH, JUMP
    bytecode = "000160ff5c5e4956"
    instructions, unknown = parse(bytecode)
    assert unknown == set()
    names = [i["op"]["name"] for i in instructions]
    assert names == ["STOP", "ADD", "PUSH1", "TLOAD", "MCOPY", "BLOBHASH", "JUMP"]
