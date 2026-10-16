"""A contract that fails before its comparisons does not stop the run, but fails it."""

import json

import pytest

import diffyscan.diffyscan as runner
from diffyscan.utils import explorer
from diffyscan.utils.custom_exceptions import ExplorerError

UNVERIFIED = "0x0000000000000000000000000000000000000001"
VERIFIED = "0x0000000000000000000000000000000000000002"


@pytest.fixture(autouse=True)
def _restore_logger_stdout():
    yield
    runner.logger.stdout_enabled = True


@pytest.fixture
def run(monkeypatch):
    config = {
        "contracts": {UNVERIFIED: "BeaconProxy", VERIFIED: "Vault"},
        "explorer_hostname": "api.etherscan.io",
        "source_comparison": False,
    }
    monkeypatch.setattr(runner, "load_config", lambda path: config)
    monkeypatch.setattr(runner, "_load_explorer_token", lambda cfg: "explorer-token")
    monkeypatch.setattr(runner, "load_env", lambda *args, **kwargs: "github-token")
    # Keeps the handler in its default fail-on-error mode, as in a config with
    # fail_on_bytecode_comparison_error: true.
    monkeypatch.setattr(runner, "_setup_binary_comparison", lambda cfg: "rpc-url")
    monkeypatch.setattr(runner, "get_chain_id", lambda rpc_url: 1)

    def explorer_source(token, hostname, address, name, *args):
        if address == UNVERIFIED:
            raise ExplorerError(
                f"Source code is not verified or an EOA address: {address}"
            )
        return {"name": name, "solcInput": {"sources": {}}}

    monkeypatch.setattr(runner, "get_contract_from_explorer", explorer_source)
    monkeypatch.setattr(
        runner,
        "run_bytecode_diff",
        lambda address, name, *args: runner._bytecode_result(
            address, name, status="exact", match=True, has_diff=False
        ),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)
    monkeypatch.setattr(runner.os.path, "isfile", lambda path: path == "config.yaml")

    def main(*args):
        monkeypatch.setattr(runner.sys, "argv", ["diffyscan", "config.yaml", *args])
        with pytest.raises(SystemExit) as exc_info:
            runner.main()
        return exc_info.value.code

    return main


def test_a_contract_error_does_not_stop_the_other_contracts(run):
    result = runner.process_config("config.yaml", False, True, False, False, True)

    assert result["error"] is None
    assert [e["contract_address"] for e in result["contract_errors"]] == [UNVERIFIED]
    assert [s["contract_address"] for s in result["bytecode_stats"]] == [VERIFIED]


def test_the_run_prints_its_summaries_and_fails_on_a_contract_error(run, capsys):
    code = run()

    out = capsys.readouterr().out
    assert code == 1
    assert "BYTECODE COMPARISON SUMMARY" in out
    assert "CONTRACTS NOT CHECKED" in out
    assert f"BeaconProxy ({UNVERIFIED})" in out


def test_the_json_report_keeps_both_contracts(run, capsys):
    code = run("--json")

    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["status"] == "error"
    assert "error" not in report
    by_address = {c["address"]: c for c in report["contracts"]}
    assert "not verified" in by_address[UNVERIFIED]["error"]
    assert by_address[VERIFIED]["bytecode"]["status"] == "exact"


def test_an_empty_explorer_answer_reads_as_unverified_source(monkeypatch):
    monkeypatch.setattr(
        explorer,
        "_fetch_etherscan_response",
        lambda link, contract: {
            "status": "1",
            "message": "OK",
            "result": [{"ContractName": "", "SourceCode": "", "Proxy": "1"}],
        },
    )

    with pytest.raises(ExplorerError, match="not verified"):
        explorer._get_contract_from_etherscan(
            None, "api.etherscan.io", UNVERIFIED, 42161
        )
