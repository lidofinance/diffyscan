"""A contract that errors (e.g. unverified on the explorer) must not abort the run."""

import pytest

import diffyscan.diffyscan as ds
from diffyscan.utils.custom_exceptions import ExplorerError, CalldataError

ADDR_BAD = "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"
ADDR_OK = "0xBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBb"


def _patch_common(monkeypatch, config):
    monkeypatch.setattr(ds, "load_config", lambda path: config)
    monkeypatch.setattr(ds, "_warn_deprecated_hardhat_settings", lambda *a, **k: None)
    monkeypatch.setattr(ds, "_load_explorer_token", lambda config: "token")
    monkeypatch.setattr(ds, "load_env", lambda *a, **k: "gh-token")
    monkeypatch.setattr(ds, "get_explorer_hostname", lambda config: "host")
    monkeypatch.setattr(ds, "get_explorer_chain_id", lambda config: 1)
    monkeypatch.setattr(
        ds,
        "run_source_diff",
        lambda addr, code, *a, **k: {
            "files_count": 1,
            "files_found": 1,
            "identical_files": 1,
            "files_with_diffs": 0,
            "contract_address": addr,
            "contract_name": code["name"],
        },
    )


def test_unverified_contract_does_not_abort_run(monkeypatch):
    config = {"contracts": {ADDR_BAD: "Foo", ADDR_OK: "Bar"}}
    _patch_common(monkeypatch, config)

    def fake_fetch(token, host, addr, name, chain_id, cache):
        if addr == ADDR_BAD:
            raise ExplorerError("Contract name in config does not match")
        return {"name": name}

    monkeypatch.setattr(ds, "get_contract_from_explorer", fake_fetch)

    # binary comparison disabled so no RPC is needed
    result = ds.process_config("cfg", None, False, False, False, False, True)

    # the failing contract is recorded, the run did NOT raise
    assert len(result["errored_contracts"]) == 1
    assert result["errored_contracts"][0]["contract_address"] == ADDR_BAD
    # the second, healthy contract was still processed
    assert [s["contract_address"] for s in result["source_stats"]] == [ADDR_OK]


def test_all_contracts_ok_yields_no_errors(monkeypatch):
    config = {"contracts": {ADDR_OK: "Bar"}}
    _patch_common(monkeypatch, config)
    monkeypatch.setattr(
        ds, "get_contract_from_explorer", lambda *a, **k: {"name": "Bar"}
    )

    result = ds.process_config("cfg", None, False, False, False, False, True)

    assert result["errored_contracts"] == []
    assert len(result["source_stats"]) == 1


def test_bytecode_comparison_error_aborts_run(monkeypatch):
    """A bytecode comparison error (not a mismatch) is fatal and must propagate."""
    config = {"contracts": {ADDR_OK: "Bar"}}
    _patch_common(monkeypatch, config)
    monkeypatch.setattr(
        ds, "get_contract_from_explorer", lambda *a, **k: {"name": "Bar"}
    )
    monkeypatch.setattr(ds, "_setup_binary_comparison", lambda *a, **k: "http://rpc")
    monkeypatch.setattr(ds, "get_chain_id", lambda url: 1)

    def boom(*a, **k):
        raise CalldataError("empty constructor calldata")

    monkeypatch.setattr(ds, "run_bytecode_diff", boom)

    with pytest.raises(CalldataError):
        # enable_binary_comparison=True (4th positional arg)
        ds.process_config("cfg", None, False, True, False, False, True)
