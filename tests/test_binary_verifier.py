import pytest

from diffyscan.utils.binary_verifier import analyze_bytecode_diff, deep_match_bytecode
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
