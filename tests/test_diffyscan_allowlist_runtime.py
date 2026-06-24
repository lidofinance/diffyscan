import diffyscan.diffyscan as runner
from diffyscan.utils.custom_exceptions import CompileError, DeploymentSimulationError

ADDR = "0x0000000000000000000000000000000000000001"


def _config_with_any_rule() -> dict:
    return {
        "contracts": {ADDR: "Test"},
        "explorer_hostname": "api.etherscan.io",
        "source_comparison": False,
        "allowed_diffs": {
            "bytecode": {
                ADDR: [
                    {
                        "reason": "simulation cannot be reproduced",
                        "any": True,
                    }
                ]
            }
        },
    }


def _stub_process_config_dependencies(monkeypatch, config: dict) -> None:
    monkeypatch.setattr(runner, "load_config", lambda path: config)
    monkeypatch.setattr(runner, "_load_explorer_token", lambda cfg: "explorer-token")
    monkeypatch.setattr(runner, "load_env", lambda *args, **kwargs: "github-token")
    monkeypatch.setattr(runner, "_setup_binary_comparison", lambda cfg: "rpc-url")
    monkeypatch.setattr(runner, "get_chain_id", lambda rpc_url: 1)
    monkeypatch.setattr(
        runner,
        "get_contract_from_explorer",
        lambda *args, **kwargs: {"name": "Test", "solcInput": {"sources": {}}},
    )


def test_any_rule_does_not_suppress_compile_errors(monkeypatch):
    config = _config_with_any_rule()
    _stub_process_config_dependencies(monkeypatch, config)
    monkeypatch.setattr(
        runner,
        "run_bytecode_diff",
        lambda *args, **kwargs: (_ for _ in ()).throw(CompileError("boom")),
    )

    result = runner.process_config(
        "config.json",
        recursive_parsing=False,
        enable_binary_comparison=True,
        cache_explorer=False,
        cache_github=False,
        skip_user_input=True,
    )

    assert result["bytecode_stats"] == [
        {
            "contract_address": ADDR,
            "contract_name": "Test",
            "status": "failed",
            "match": False,
            "has_diff": True,
            "matched_rule": None,
            "matched_facets": [],
            "suggestion_entry": None,
        }
    ]


def test_any_rule_can_suppress_deployment_simulation_errors(monkeypatch):
    config = _config_with_any_rule()
    _stub_process_config_dependencies(monkeypatch, config)
    monkeypatch.setattr(
        runner,
        "run_bytecode_diff",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            DeploymentSimulationError("eth_call reverted")
        ),
    )

    result = runner.process_config(
        "config.json",
        recursive_parsing=False,
        enable_binary_comparison=True,
        cache_explorer=False,
        cache_github=False,
        skip_user_input=True,
    )

    assert result["bytecode_stats"][0]["status"] == "allowed"
    assert (
        result["bytecode_stats"][0]["matched_rule"]
        == config["allowed_diffs"]["bytecode"][ADDR][0]
    )
    assert result["bytecode_stats"][0]["matched_facets"] == ["any"]


def test_process_config_normalizes_explorer_chain_id(monkeypatch):
    config = {
        "contracts": {ADDR: "Test"},
        "explorer_hostname": "api.etherscan.io",
        "explorer_chain_id": "1",
        "source_comparison": False,
    }
    captured = {}
    _stub_process_config_dependencies(monkeypatch, config)

    def fake_get_contract_from_explorer(*args):
        captured["explorer_chain_id"] = args[4]
        return {"name": "Test", "solcInput": {"sources": {}}}

    monkeypatch.setattr(
        runner,
        "get_contract_from_explorer",
        fake_get_contract_from_explorer,
    )

    runner.process_config(
        "config.json",
        recursive_parsing=False,
        enable_binary_comparison=False,
        cache_explorer=False,
        cache_github=False,
        skip_user_input=True,
    )

    assert captured["explorer_chain_id"] == 1


def test_constructor_override_simulation_uses_deployment_gas_limit(monkeypatch):
    config = {
        "bytecode_comparison": {},
        "deployment_gas_limit": 12345,
    }
    base_analysis = {
        "exact_match": False,
        "runtime_mismatch_ranges": [{"offset": 0, "length": 1, "immutable": False}],
        "metadata_mismatch": False,
        "string_literal_mismatch": False,
        "length_mismatch": False,
        "immutable_regions": {},
        "remote_runtime_bytecode": "0x02",
        "immutable_observations": [],
    }
    override_analysis = {
        **base_analysis,
        "exact_match": True,
        "runtime_mismatch_ranges": [],
    }
    analyses = [base_analysis, override_analysis]
    simulate_calls = []

    monkeypatch.setattr(
        runner,
        "_build_github_solc_input",
        lambda *args, **kwargs: ({"sources": {}}, []),
    )
    monkeypatch.setattr(
        runner,
        "compile_contract_from_explorer",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        runner,
        "parse_compiled_contract",
        lambda compiled: ("0x60", "0xcompiled", {}),
    )
    monkeypatch.setattr(runner, "get_bytecode_from_node", lambda *args: "0xremote")
    monkeypatch.setattr(runner, "get_calldata", lambda *args, **kwargs: "0x00")

    def fake_simulate_deployment(data, rpc_url, **kwargs):
        simulate_calls.append(kwargs)
        return "0xbase" if len(simulate_calls) == 1 else "0xoverride"

    monkeypatch.setattr(runner, "simulate_deployment", fake_simulate_deployment)
    monkeypatch.setattr(
        runner,
        "analyze_bytecode_diff",
        lambda *args, **kwargs: analyses.pop(0),
    )

    result = runner.run_bytecode_diff(
        ADDR,
        "Test",
        {"solcInput": {"sources": {}}},
        config,
        github_api_token="github-token",
        recursive_parsing=False,
        cache_github=False,
        remote_rpc_url="rpc-url",
        allowed_rules=[{"reason": "alternate constructor", "constructor_args": [1]}],
    )

    assert result["status"] == "allowed"
    assert result["matched_facets"] == ["exact_match", "constructor_args"]
    assert [call["gas_limit"] for call in simulate_calls] == [12345, 12345]
