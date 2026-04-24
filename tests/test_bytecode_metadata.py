import json

import pytest

from diffyscan.utils.calldata import get_calldata
from diffyscan.utils.custom_exceptions import CalldataError, CompileError, NodeError
from diffyscan.utils.explorer import (
    _get_contract_from_blockscout,
    _get_contract_from_etherscan,
    compile_contract_from_explorer,
)
from diffyscan.utils.node_handler import simulate_deployment


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_get_calldata_prefers_manual_config_over_explorer_metadata():
    compiled_contract = {
        "abi": [
            {
                "type": "constructor",
                "inputs": [{"name": "owner", "type": "address"}],
            }
        ]
    }
    binary_config = {
        "constructor_calldata": {
            "0x0000000000000000000000000000000000000001": "0x1234abcd"
        }
    }

    result = get_calldata(
        "0x0000000000000000000000000000000000000001",
        compiled_contract,
        binary_config,
        "deadbeef",
    )

    assert result == "1234abcd"


def test_get_calldata_uses_explorer_metadata_when_manual_config_missing():
    compiled_contract = {
        "abi": [
            {
                "type": "constructor",
                "inputs": [{"name": "owner", "type": "address"}],
            }
        ]
    }

    result = get_calldata(
        "0x0000000000000000000000000000000000000001",
        compiled_contract,
        None,
        "deadbeef",
    )

    assert result == "deadbeef"


def test_get_calldata_raises_when_constructor_args_are_missing_everywhere():
    compiled_contract = {
        "abi": [
            {
                "type": "constructor",
                "inputs": [{"name": "owner", "type": "address"}],
            }
        ]
    }

    with pytest.raises(CalldataError, match="explorer metadata"):
        get_calldata(
            "0x0000000000000000000000000000000000000001",
            compiled_contract,
            None,
            None,
        )


def test_simulate_deployment_uses_eth_call(monkeypatch):
    captured = {}

    def fake_pull(rpc_url, payload, headers):
        captured["rpc_url"] = rpc_url
        captured["headers"] = headers
        captured["payload"] = json.loads(payload)
        return DummyResponse({"result": "0x60016000"})

    monkeypatch.setattr("diffyscan.utils.node_handler.pull", fake_pull)

    result = simulate_deployment("0x6001600055", "https://rpc.example")

    assert result == "0x60016000"
    assert captured["rpc_url"] == "https://rpc.example"
    assert captured["headers"] == {"Content-Type": "application/json"}
    assert captured["payload"]["method"] == "eth_call"
    assert captured["payload"]["params"][0]["to"] is None
    assert captured["payload"]["params"][0]["data"] == "0x6001600055"


def test_simulate_deployment_uses_custom_caller(monkeypatch):
    captured = {}

    def fake_pull(rpc_url, payload, headers):
        captured["payload"] = json.loads(payload)
        return DummyResponse({"result": "0x60016000"})

    monkeypatch.setattr("diffyscan.utils.node_handler.pull", fake_pull)

    simulate_deployment(
        "0x6001600055",
        "https://rpc.example",
        caller="0x0000000000000000000000000000000000000002",
    )

    assert (
        captured["payload"]["params"][0]["from"]
        == "0x0000000000000000000000000000000000000002"
    )


def test_simulate_deployment_surfaces_rpc_errors(monkeypatch):
    def fake_pull(rpc_url, payload, headers):
        return DummyResponse(
            {"error": {"message": "execution reverted", "data": "0x08c379a0"}}
        )

    monkeypatch.setattr("diffyscan.utils.node_handler.pull", fake_pull)

    with pytest.raises(NodeError, match="execution reverted"):
        simulate_deployment("0x6001600055", "https://rpc.example")


def test_get_contract_from_etherscan_extracts_metadata(monkeypatch):
    def fake_fetch(url):
        return DummyResponse(
            {
                "message": "OK",
                "result": [
                    {
                        "ContractName": "Demo",
                        "CompilerVersion": "v0.8.25+commit.b61c2a91",
                        "SourceCode": "contract Demo { constructor(address owner) {} }",
                        "OptimizationUsed": "1",
                        "Runs": "200",
                        "ConstructorArguments": "0000000000000000000000000000000000000000000000000000000000000042",
                        "EVMVersion": "paris",
                        "Library": "contracts/libraries/Helper.sol:Helper:0x1111111111111111111111111111111111111111",
                    }
                ],
            }
        )

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)

    contract = _get_contract_from_etherscan(
        None,
        "api.etherscan.io",
        "0x0000000000000000000000000000000000000001",
    )

    assert contract["constructor_arguments"].endswith("42")
    assert contract["evm_version"] == "paris"
    assert contract["libraries"] == {
        "contracts/libraries/Helper.sol": {
            "Helper": "0x1111111111111111111111111111111111111111"
        }
    }


def test_get_contract_from_etherscan_retries_rate_limit(monkeypatch):
    responses = iter(
        [
            {
                "message": "NOTOK",
                "result": "Max calls per sec rate limit reached (3/sec)",
            },
            {
                "message": "OK",
                "result": [
                    {
                        "ContractName": "Demo",
                        "CompilerVersion": "v0.8.25+commit.b61c2a91",
                        "SourceCode": "contract Demo {}",
                        "OptimizationUsed": "1",
                        "Runs": "200",
                    }
                ],
            },
        ]
    )
    sleeps = []

    def fake_fetch(url):
        return DummyResponse(next(responses))

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)
    monkeypatch.setattr("diffyscan.utils.explorer.time.sleep", sleeps.append)

    contract = _get_contract_from_etherscan(
        None,
        "api.etherscan.io",
        "0x0000000000000000000000000000000000000001",
    )

    assert contract["name"] == "Demo"
    assert sleeps == [1.0]


def test_get_contract_from_blockscout_extracts_and_merges_metadata(monkeypatch):
    def fake_fetch(url):
        return DummyResponse(
            {
                "name": "Demo",
                "file_path": "contracts/Demo.sol",
                "source_code": "import './Helper.sol'; contract Demo { constructor(address owner) {} }",
                "additional_sources": [
                    {
                        "file_path": "contracts/Helper.sol",
                        "source_code": "library Helper {}",
                    }
                ],
                "optimization_enabled": True,
                "optimization_runs": 200,
                "compiler_version": "v0.8.25+commit.b61c2a91",
                "constructor_args": "deadbeef",
                "evm_version": "prague",
                "compiler_settings": {
                    "libraries": {
                        "contracts/Existing.sol": {
                            "Existing": "0x2222222222222222222222222222222222222222"
                        }
                    },
                    "evmVersion": "shanghai",
                },
                "external_libraries": [
                    {
                        "file_path": "contracts/Helper.sol",
                        "name": "Helper",
                        "address": "0x1111111111111111111111111111111111111111",
                    }
                ],
            }
        )

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)

    contract = _get_contract_from_blockscout(
        "eth.blockscout.com",
        "0x0000000000000000000000000000000000000001",
    )

    assert contract["constructor_arguments"] == "deadbeef"
    assert contract["evm_version"] == "prague"
    assert contract["libraries"] == {
        "contracts/Existing.sol": {
            "Existing": "0x2222222222222222222222222222222222222222"
        },
        "contracts/Helper.sol": {
            "Helper": "0x1111111111111111111111111111111111111111"
        },
    }


def test_compile_contract_from_explorer_merges_libraries_and_evm_version(monkeypatch):
    captured = {}
    contract_code = {
        "name": "Demo",
        "compiler": "v0.8.25+commit.b61c2a91",
        "solcInput": {
            "language": "Solidity",
            "sources": {"contracts/Demo.sol": {"content": "contract Demo {}"}},
            "settings": {
                "libraries": {
                    "contracts/Existing.sol": {
                        "Existing": "0x2222222222222222222222222222222222222222"
                    }
                }
            },
        },
    }

    monkeypatch.setattr(
        "diffyscan.utils.explorer.get_solc_native_platform_from_os",
        lambda: "linux-amd64",
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.get_compiler_info",
        lambda required_platform, build_name: {"path": "solc-linux-amd64-v0.8.25"},
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.os.path.isfile",
        lambda compiler_path: True,
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.verify_compiler_integrity",
        lambda compiler_path, build_info: None,
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.prepare_compiler",
        lambda *args, **kwargs: None,
    )

    def fake_compile_contracts(compiler_path, input_settings):
        captured["compiler_path"] = compiler_path
        captured["input_settings"] = json.loads(input_settings)
        return {"contracts": {"contracts/Demo.sol": {"Demo": {"abi": [], "evm": {}}}}}

    monkeypatch.setattr(
        "diffyscan.utils.explorer.compile_contracts",
        fake_compile_contracts,
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.get_target_compiled_contract",
        lambda compiled_contracts, target_name: {"abi": [], "evm": {}},
    )

    result = compile_contract_from_explorer(
        contract_code,
        {
            "contracts/Helper.sol": {
                "Helper": "0x1111111111111111111111111111111111111111"
            }
        },
        "paris",
    )

    assert result == {"abi": [], "evm": {}}
    assert captured["input_settings"]["settings"]["evmVersion"] == "paris"
    assert captured["input_settings"]["settings"]["libraries"] == {
        "contracts/Existing.sol": {
            "Existing": "0x2222222222222222222222222222222222222222"
        },
        "contracts/Helper.sol": {
            "Helper": "0x1111111111111111111111111111111111111111"
        },
    }
    assert contract_code["solcInput"]["settings"] == {
        "libraries": {
            "contracts/Existing.sol": {
                "Existing": "0x2222222222222222222222222222222222222222"
            }
        }
    }


def test_compile_contract_from_explorer_redownloads_tampered_cached_compiler(
    monkeypatch,
):
    calls = {"prepare": 0}
    contract_code = {
        "name": "Demo",
        "compiler": "v0.8.25+commit.b61c2a91",
        "solcInput": {
            "language": "Solidity",
            "sources": {"contracts/Demo.sol": {"content": "contract Demo {}"}},
            "settings": {},
        },
    }

    monkeypatch.setattr(
        "diffyscan.utils.explorer.get_solc_native_platform_from_os",
        lambda: "linux-amd64",
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.get_compiler_info",
        lambda required_platform, build_name: {"path": "solc-linux-amd64-v0.8.25"},
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.os.path.isfile",
        lambda compiler_path: True,
    )

    def fake_verify(compiler_path, build_info):
        raise CompileError("Compiler checksum mismatch")

    def fake_prepare(required_platform, build_info, compiler_path):
        calls["prepare"] += 1

    monkeypatch.setattr(
        "diffyscan.utils.explorer.verify_compiler_integrity",
        fake_verify,
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.prepare_compiler",
        fake_prepare,
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.compile_contracts",
        lambda compiler_path, input_settings: {
            "contracts": {"contracts/Demo.sol": {"Demo": {"abi": [], "evm": {}}}}
        },
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.get_target_compiled_contract",
        lambda compiled_contracts, target_name: {"abi": [], "evm": {}},
    )

    result = compile_contract_from_explorer(contract_code)

    assert result == {"abi": [], "evm": {}}
    assert calls["prepare"] == 1
