"""Tests for the --contract / -C filter flag."""

import pytest

CONTRACTS = {
    "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa": "ContractA",
    "0xBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBb": "ContractB",
    "0xCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCc": "ContractC",
}


def apply_filter(contracts, contract_filter):
    """Reproduce the filter logic from process_config."""
    filter_set = (
        set(addr.lower() for addr in contract_filter) if contract_filter else None
    )
    result = {}
    for addr, name in contracts.items():
        if filter_set and addr.lower() not in filter_set:
            continue
        result[addr] = name
    return result


def test_no_filter_returns_all():
    assert apply_filter(CONTRACTS, None) == CONTRACTS
    assert apply_filter(CONTRACTS, []) == CONTRACTS


def test_filter_single_contract():
    filtered = apply_filter(CONTRACTS, ["0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"])
    assert list(filtered.keys()) == ["0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"]
    assert filtered["0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"] == "ContractA"


def test_filter_multiple_contracts():
    filtered = apply_filter(
        CONTRACTS,
        [
            "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa",
            "0xCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCcCc",
        ],
    )
    assert len(filtered) == 2
    assert "0xBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBb" not in filtered


def test_filter_is_case_insensitive():
    filtered = apply_filter(CONTRACTS, ["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"])
    assert len(filtered) == 1
    assert "ContractA" in filtered.values()


def filter_matched_any(config_contracts, contract_filter):
    """Reproduce the run-level check from main: did the filter match any contract?"""
    if not contract_filter:
        return True
    return any(
        apply_filter(contracts, contract_filter) for contracts in config_contracts
    )


def test_filter_nonexistent_address_returns_empty():
    filtered = apply_filter(CONTRACTS, ["0x0000000000000000000000000000000000000000"])
    assert filtered == {}


def test_filter_matching_nothing_is_an_error():
    # A filter that matches no contract in any config is a usage error (exit non-zero).
    assert (
        filter_matched_any([CONTRACTS], ["0x0000000000000000000000000000000000000000"])
        is False
    )


def test_filter_matching_in_any_config_is_ok():
    # Matching at least one contract in one of several configs is fine.
    other = {"0xDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDdDd": "ContractD"}
    assert (
        filter_matched_any(
            [other, CONTRACTS], ["0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"]
        )
        is True
    )


def test_no_filter_is_never_an_error():
    assert filter_matched_any([CONTRACTS], None) is True
    assert filter_matched_any([CONTRACTS], []) is True


def test_filter_mixed_case_multiple():
    filtered = apply_filter(
        CONTRACTS,
        [
            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "0xCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        ],
    )
    assert len(filtered) == 2
    names = set(filtered.values())
    assert names == {"ContractB", "ContractC"}
