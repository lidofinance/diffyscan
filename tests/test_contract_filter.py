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


def test_filter_nonexistent_address_returns_empty():
    filtered = apply_filter(CONTRACTS, ["0x0000000000000000000000000000000000000000"])
    assert filtered == {}


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
