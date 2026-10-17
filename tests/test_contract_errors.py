"""A contract that fails before its comparisons does not stop the run, but fails it."""

import json

import pytest

import diffyscan.diffyscan as runner
from diffyscan.utils import explorer
from diffyscan.utils.custom_exceptions import ExplorerError

UNVERIFIED = "0x0000000000000000000000000000000000000001"
VERIFIED = "0x0000000000000000000000000000000000000002"


def _config(*, unverified=True, fail_on=None, source=False):
    contracts = {UNVERIFIED: "BeaconProxy"} if unverified else {}
    config = {
        "contracts": {**contracts, VERIFIED: "Vault"},
        "explorer_hostname": "api.etherscan.io",
        "source_comparison": source,
    }
    if fail_on is not None:
        config["fail_on_bytecode_comparison_error"] = fail_on
    return config


def _exact_source(address, *args):
    return {
        "contract_address": address,
        "contract_name": "Vault",
        "status": "exact",
        "files_count": 1,
        "files_found": 1,
        "identical_files": 1,
        "files_with_diffs": 0,
        "files": [],
        "matched_rule": None,
        "matched_facets": [],
        "suggestion_entry": None,
    }


@pytest.fixture(autouse=True)
def _restore_logger_stdout():
    yield
    runner.logger.stdout_enabled = True


@pytest.fixture
def run(monkeypatch):
    configs = {"config.yaml": _config()}
    monkeypatch.setattr(runner, "load_config", lambda path: configs[path])
    monkeypatch.setattr(runner, "_collect_config_paths", lambda path: list(configs))
    monkeypatch.setattr(runner, "_load_explorer_token", lambda cfg: "explorer-token")
    # Also answers the RPC variable, so the real _setup_binary_comparison applies
    # each config's fail_on_bytecode_comparison_error.
    monkeypatch.setattr(runner, "load_env", lambda *args, **kwargs: "env-value")
    monkeypatch.setattr(runner, "get_chain_id", lambda rpc_url: 1)

    def explorer_source(token, hostname, address, name, *args):
        if address == UNVERIFIED:
            raise ExplorerError(
                f"Source code is not verified or an EOA address: {address}"
            )
        return {"name": name, "solcInput": {"sources": {}}}

    monkeypatch.setattr(runner, "get_contract_from_explorer", explorer_source)
    monkeypatch.setattr(runner, "run_source_diff", _exact_source)
    monkeypatch.setattr(
        runner,
        "run_bytecode_diff",
        lambda address, name, *args: runner._bytecode_result(
            address, name, status="exact", match=True, has_diff=False
        ),
    )
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)

    def main(*args, use=None):
        if use is not None:
            configs.clear()
            configs.update(use)
        monkeypatch.setattr(runner.sys, "argv", ["diffyscan", "configs", *args])
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


def test_opting_out_keeps_exit_status_zero_and_reports_the_error(run, capsys):
    code = run("--json", use={"config.yaml": _config(fail_on=False)})

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["status"] == "error"


def test_without_bytecode_comparison_a_contract_error_fails_the_run(run):
    use = {"config.yaml": _config(fail_on=False, source=True)}

    assert run("--skip-binary-comparison", use=use) == 1


@pytest.mark.parametrize(
    "use, expected",
    [
        ({"strict": _config(), "lenient": _config(unverified=False, fail_on=False)}, 1),
        ({"lenient": _config(unverified=False, fail_on=False), "strict": _config()}, 1),
        ({"strict": _config(unverified=False), "lenient": _config(fail_on=False)}, 0),
        ({"lenient": _config(fail_on=False), "strict": _config(unverified=False)}, 0),
    ],
)
def test_each_config_applies_its_own_policy(run, use, expected):
    assert run(use=use) == expected


def test_an_empty_explorer_answer_reads_as_unverified_source(monkeypatch):
    monkeypatch.setattr(
        explorer,
        "_fetch_etherscan_response",
        lambda link, contract: {
            "status": "1",
            "message": "OK",
            "result": [
                {
                    "ContractName": "",
                    "SourceCode": "",
                    "CompilerVersion": "",
                    "Proxy": "1",
                }
            ],
        },
    )

    with pytest.raises(ExplorerError, match="not verified"):
        explorer._get_contract_from_etherscan(
            None, "api.etherscan.io", UNVERIFIED, 42161
        )


@pytest.mark.parametrize(
    "result", ["Contract source code not verified", ["bad"], [None]]
)
def test_malformed_explorer_result_is_a_handled_error(monkeypatch, result):
    monkeypatch.setattr(
        explorer,
        "_fetch_etherscan_response",
        lambda *args: {"status": "0", "message": "Error", "result": result},
    )
    with pytest.raises(ExplorerError, match="Unexpected.*result"):
        explorer._get_contract_from_etherscan(None, "api.etherscan.io", UNVERIFIED, 1)


def test_handled_error_keeps_traceback_in_log_only(run, monkeypatch, capsys):
    logs: list[str] = []
    monkeypatch.setattr(runner.logger, "log", logs.append)

    assert run() == 1

    captured = capsys.readouterr()
    from diffyscan.utils.logger import _ANSI_ESCAPE

    output = _ANSI_ESCAPE.sub("", captured.out)
    assert "CONTRACTS NOT CHECKED: 1" in output
    assert "CONTRACTS NOT CHECKED::" not in output
    assert "Traceback" not in captured.out + captured.err
    assert any("Traceback" in entry and "ExplorerError" in entry for entry in logs)
