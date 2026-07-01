import pytest

from diffyscan.utils.binary_verifier import (
    analyze_bytecode_diff,
    parse,
)
from diffyscan.utils.constants import OPCODES, PUSH0, PUSH32


def test_analyze_bytecode_diff_detects_length_mismatch():
    local = "0x6001600055fe"
    remote = "0x6001600055fe6001"

    analysis = analyze_bytecode_diff(local, remote, immutables={})

    assert analysis["exact_match"] is False
    assert analysis["length_mismatch"] is True


def test_analyze_bytecode_diff_marks_immutable_ranges():
    local = "0x6001fe"
    remote = "0x6002fe"

    analysis = analyze_bytecode_diff(local, remote, immutables={1: 1})

    assert analysis["runtime_mismatch_ranges"] == [
        {"offset": 1, "length": 1, "immutable": True}
    ]


def test_analyze_bytecode_diff_marks_non_immutable_ranges():
    local = "0x6001fe"
    remote = "0x6001fd"

    analysis = analyze_bytecode_diff(local, remote, immutables={})

    assert analysis["runtime_mismatch_ranges"] == [
        {"offset": 2, "length": 1, "immutable": False}
    ]


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


def test_analyze_bytecode_diff_detects_metadata_only_difference():
    local = "0x6000abcd0002"
    remote = "0x6000dcba0002"

    analysis = analyze_bytecode_diff(local, remote, immutables={})

    assert analysis["exact_match"] is False
    assert analysis["runtime_mismatch_ranges"] == []
    assert analysis["metadata_mismatch"] is True


def test_analyze_bytecode_diff_tracks_immutable_observations():
    local = "0x6001fe"
    remote = "0x6002fe"

    analysis = analyze_bytecode_diff(local, remote, immutables={1: 1})

    assert analysis["runtime_mismatch_ranges"] == [
        {"offset": 1, "length": 1, "immutable": True}
    ]
    assert analysis["immutable_observations"] == [
        {
            "offset": 1,
            "length": 1,
            "local_value": "0x01",
            "remote_value": "0x02",
            "differs": True,
        }
    ]
