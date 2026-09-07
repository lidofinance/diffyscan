"""Tests for the --json machine-readable output mode."""

import json

import pytest

import diffyscan.diffyscan as runner
from diffyscan.utils.logger import Logger, bgGreen, bgRed

ADDR = "0x0000000000000000000000000000000000000001"


@pytest.fixture(autouse=True)
def _restore_logger_stdout():
    yield
    runner.logger.stdout_enabled = True


def _source_stat(status="failed"):
    return {
        "contract_address": ADDR,
        "contract_name": "Test",
        "status": status,
        "files_count": 2,
        "files_found": 2,
        "identical_files": 1,
        "files_with_diffs": 1,
        "matched_rule": None,
        "matched_facets": [],
        "suggestion_entry": {"reason": "TODO", "line_ranges": []},
        "has_diff": True,
        "files": [
            {
                "path": "contracts/Same.sol",
                "filename": "Same.sol",
                "origin": "contracts",
                "file_found": True,
                "diff_report_filename": "digest/1/diffs/Same.sol.html",
                "diffs_count": 0,
                "hunks": [],
                "github_line_count": 10,
                "explorer_line_count": 10,
            },
            {
                "path": "contracts/Changed.sol",
                "filename": "Changed.sol",
                "origin": "contracts",
                "file_found": True,
                "diff_report_filename": "digest/1/diffs/Changed.sol.html",
                "diffs_count": 4,
                "hunks": [
                    {
                        "github": {"start": 3, "count": 1},
                        "explorer": {"start": 3, "count": 1},
                        "tag": "replace",
                    }
                ],
                "github_line_count": 10,
                "explorer_line_count": 10,
            },
        ],
    }


def _bytecode_stat(status="exact"):
    return runner._bytecode_result(
        ADDR, "Test", status=status, match=status == "exact", has_diff=False
    )


def _result(source_stats, bytecode_stats, path="config.yaml", contract_errors=None):
    return {
        "source_stats": source_stats,
        "bytecode_stats": bytecode_stats,
        "contract_errors": contract_errors or [],
        "config_path": path,
        "matched_count": 1,
        "interrupted": False,
        "error": None,
    }


def test_report_merges_source_and_bytecode_per_contract():
    report = runner.build_json_report(
        [_result([_source_stat()], [_bytecode_stat()])],
        exit_code=1,
        error=None,
        duration_seconds=1.23456,
    )

    assert report["status"] == "failed"
    assert report["exit_code"] == 1
    assert "error" not in report
    assert report["duration_seconds"] == 1.235
    assert report["summary"] == {
        "source": {"total": 1, "exact": 0, "allowed": 0, "failed": 1},
        "bytecode": {"total": 1, "exact": 1, "allowed": 0, "failed": 0},
    }

    [contract] = report["contracts"]
    assert contract["config"] == "config.yaml"
    assert contract["address"] == ADDR
    assert contract["name"] == "Test"
    # Clean results carry only their status; empty fields are omitted.
    assert contract["bytecode"] == {"status": "exact"}
    assert contract["source"]["status"] == "failed"
    assert contract["source"]["files"] == 2
    assert contract["source"]["with_diffs"] == 1
    assert "missing" not in contract["source"]
    assert contract["source"]["suggested_rule"] == {"reason": "TODO", "line_ranges": []}
    # Only files that differ or are missing are listed.
    [diff] = contract["source"]["diffs"]
    assert diff["path"] == "contracts/Changed.sol"
    assert diff["report"] == "digest/1/diffs/Changed.sol.html"
    assert diff["hunks"][0]["tag"] == "replace"


def test_allowed_diff_keeps_reason_and_facets_only():
    stat = _bytecode_stat("allowed")
    stat["matched_rule"] = {
        "reason": "proxy admin immutable",
        "immutables": [{"offset": 1, "value": "0x01"}],
    }
    stat["matched_facets"] = ["immutables"]

    report = runner.build_json_report(
        [_result([], [stat])], exit_code=0, error=None, duration_seconds=0
    )

    assert report["contracts"][0]["bytecode"] == {
        "status": "allowed",
        "facets": ["immutables"],
        "reason": "proxy admin immutable",
    }


def test_report_status_reflects_error_and_pass():
    passed = runner.build_json_report(
        [_result([], [_bytecode_stat()])], exit_code=0, error=None, duration_seconds=0
    )
    assert passed["status"] == "passed"
    assert "source" not in passed["contracts"][0]
    assert "source" not in passed["summary"]

    errored = runner.build_json_report(
        [], exit_code=1, error="FileNotFoundError: nope", duration_seconds=0
    )
    assert errored["status"] == "error"
    assert errored["error"] == "FileNotFoundError: nope"
    assert errored["contracts"] == []
    assert errored["summary"] == {}


def test_swallowed_contract_errors_surface_as_error_status():
    failure = {
        "contract_address": ADDR,
        "contract_name": "Test",
        "error": "Failed to communicate with a remote resource: HTTP error: 401",
    }
    report = runner.build_json_report(
        [_result([], [], contract_errors=[failure])],
        exit_code=0,
        error=None,
        duration_seconds=0,
    )

    # Exit code stays 0 (fail_on_bytecode_comparison_error: false), but the
    # report must not read as "passed" when nothing was verified.
    assert report["status"] == "error"
    assert report["exit_code"] == 0
    assert report["summary"] == {"contract_errors": 1}
    [contract] = report["contracts"]
    assert contract["error"] == failure["error"]
    assert "source" not in contract and "bytecode" not in contract


def test_logger_stdout_can_be_muted(capsys, tmp_path):
    log = Logger(str(tmp_path / "logs.txt"))
    log.stdout_enabled = False
    log.info("hidden")
    log.report_table([[1, "a.sol", True, 0, "a", "r.html"]])
    log.divider()
    assert capsys.readouterr().out == ""
    assert "hidden" in (tmp_path / "logs.txt").read_text()


def test_logger_raw_logs_uncolored_line(capsys, tmp_path):
    log = Logger(str(tmp_path / "logs.txt"))
    log.raw(f"0001 60 PUSH1 {bgRed('0x01')} {bgGreen('0x02')}")
    assert (tmp_path / "logs.txt").read_text() == "0001 60 PUSH1 0x01 0x02\n"
    assert bgRed("0x01") in capsys.readouterr().out


def _run_main(monkeypatch, argv, process_config):
    monkeypatch.setattr(runner.sys, "argv", ["diffyscan", *argv])
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)
    monkeypatch.setattr(runner, "process_config", process_config)
    monkeypatch.setattr(runner.os.path, "isfile", lambda path: path == "config.yaml")
    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    return exc_info.value.code


def test_json_mode_prints_only_json_and_implies_yes(monkeypatch, capsys):
    seen = {}

    def fake_process_config(path, brownie, binary, cache_e, cache_g, yes, flt):
        seen["skip_user_input"] = yes
        return _result([], [_bytecode_stat("failed")], path)

    code = _run_main(monkeypatch, ["config.yaml", "--json"], fake_process_config)

    assert code == 1
    assert seen["skip_user_input"] is True
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["summary"]["bytecode"]["failed"] == 1


def test_json_mode_reports_exceptions_instead_of_crashing(monkeypatch, capsys):
    def boom(*args):
        raise RuntimeError("explorer is down")

    code = _run_main(monkeypatch, ["config.yaml", "-J"], boom)

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["error"] == "RuntimeError: explorer is down"


def test_json_mode_keeps_results_completed_before_fatal_error(monkeypatch, capsys):
    def partial(path, *args):
        result = _result([], [_bytecode_stat()], path)
        result["error"] = RuntimeError("explorer is down")
        return result

    code = _run_main(monkeypatch, ["config.yaml", "--json"], partial)

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["error"] == "RuntimeError: explorer is down"
    assert report["summary"]["bytecode"]["exact"] == 1


def test_json_mode_reports_interrupted_run_as_error(monkeypatch, capsys):
    def interrupted(path, *args):
        result = _result([], [_bytecode_stat()], path)
        result["interrupted"] = True
        return result

    code = _run_main(monkeypatch, ["config.yaml", "--json"], interrupted)

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["error"] == "KeyboardInterrupt: run interrupted by user"
    # Partial results are still reported so the consumer sees what was checked.
    assert report["summary"]["bytecode"]["exact"] == 1


def test_json_mode_reports_unmatched_filter_as_failed(monkeypatch, capsys):
    def nothing_matched(path, *args):
        result = _result([], [], path)
        result["matched_count"] = 0
        return result

    code = _run_main(
        monkeypatch, ["config.yaml", "--json", "--contract", ADDR], nothing_matched
    )

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert "error" not in report
    assert report["contracts"] == []


def test_json_mode_reports_empty_configs_as_failed(monkeypatch, capsys):
    def nothing_to_check(path, *args):
        result = _result([], [], path)
        result["matched_count"] = 0
        return result

    code = _run_main(monkeypatch, ["config.yaml", "--json"], nothing_to_check)

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert "error" not in report


@pytest.mark.parametrize("json_mode", [False, True])
def test_run_rejects_disabled_comparisons(monkeypatch, capsys, json_mode):
    monkeypatch.setattr(
        runner,
        "load_config",
        lambda path: {
            "contracts": {ADDR: "Test"},
            "explorer_hostname": "api.etherscan.io",
            "source_comparison": False,
        },
    )
    monkeypatch.setattr(runner, "_load_explorer_token", lambda cfg: "dummy")
    monkeypatch.setattr(runner, "load_env", lambda *args, **kwargs: "dummy")
    monkeypatch.setattr(runner, "get_contract_from_explorer", lambda *args: {})
    argv = ["config.yaml", "--skip-binary-comparison"]
    if json_mode:
        code = _run_main(monkeypatch, [*argv, "--json"], runner.process_config)
        report = json.loads(capsys.readouterr().out)
        assert code == 1
        assert report["status"] == "error"
        assert "Both source and bytecode comparisons are disabled" in report["error"]
    else:
        with pytest.raises(
            ValueError, match="Both source and bytecode comparisons are disabled"
        ):
            _run_main(monkeypatch, argv, runner.process_config)


def test_json_mode_reports_interrupt_during_setup_as_error(monkeypatch, capsys):
    def interrupted(*args):
        raise KeyboardInterrupt

    code = _run_main(monkeypatch, ["config.yaml", "--json"], interrupted)

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["error"] == "KeyboardInterrupt: run interrupted by user"


def test_directory_without_config_files_is_an_error(tmp_path):
    (tmp_path / "mainnet").mkdir()
    (tmp_path / "mainnet" / "core.yaml").write_text("contracts: {}\n")

    with pytest.raises(FileNotFoundError, match="not recursive"):
        runner._collect_config_paths(str(tmp_path))


def test_human_mode_still_raises(monkeypatch):
    def boom(*args):
        raise RuntimeError("explorer is down")

    monkeypatch.setattr(runner.sys, "argv", ["diffyscan", "config.yaml"])
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)
    monkeypatch.setattr(runner, "process_config", boom)
    monkeypatch.setattr(runner.os.path, "isfile", lambda path: path == "config.yaml")
    with pytest.raises(RuntimeError):
        runner.main()


def test_human_mode_reraises_error_returned_by_process_config(monkeypatch):
    def partial(path, *args):
        result = _result([], [_bytecode_stat()], path)
        result["error"] = RuntimeError("explorer is down")
        return result

    monkeypatch.setattr(runner.sys, "argv", ["diffyscan", "config.yaml"])
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)
    monkeypatch.setattr(runner, "process_config", partial)
    monkeypatch.setattr(runner.os.path, "isfile", lambda path: path == "config.yaml")
    with pytest.raises(RuntimeError, match="explorer is down"):
        runner.main()
