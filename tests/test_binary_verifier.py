import pytest

from diffyscan.utils.binary_verifier import deep_match_bytecode
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
