import json

import pytest

from diffyscan.diffyscan import _get_local_inputs
from diffyscan.utils.explorer import build_contract_from_local_input
from diffyscan.utils.custom_exceptions import ExplorerError


def _write_standard_json(tmp_path, **settings):
    payload = {
        "language": "Solidity",
        "sources": {"contracts/Foo.sol": {"content": "contract Foo {}"}},
        "settings": settings,
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload))
    return str(path)


def test_build_contract_from_local_input_shape(tmp_path):
    path = _write_standard_json(tmp_path, evmVersion="cancun")
    contract = build_contract_from_local_input("Foo", path, "v0.8.26+commit.8a97fa7a")

    assert contract["name"] == "Foo"
    assert contract["compiler"] == "v0.8.26+commit.8a97fa7a"
    assert contract["evm_version"] == "cancun"
    assert contract["libraries"] is None
    assert contract["constructor_arguments"] is None
    assert "contracts/Foo.sol" in contract["solcInput"]["sources"]
    # outputSelection is forced so bytecode parsing always has what it needs
    output_selection = contract["solcInput"]["settings"]["outputSelection"]
    assert "evm.deployedBytecode" in output_selection["*"]["*"]


def test_build_contract_from_local_input_keeps_libraries(tmp_path):
    libs = {"contracts/Foo.sol": {"Lib": "0x" + "11" * 20}}
    path = _write_standard_json(tmp_path, libraries=libs)
    contract = build_contract_from_local_input("Foo", path, "v0.8.26")
    assert contract["libraries"] == libs


def test_build_contract_from_local_input_errors(tmp_path):
    missing_sources = tmp_path / "bad.json"
    missing_sources.write_text(json.dumps({"language": "Solidity"}))
    for path in (missing_sources, tmp_path / "does_not_exist.json"):
        with pytest.raises(ExplorerError):
            build_contract_from_local_input("Foo", str(path), "v0.8.26")


def test_get_local_inputs_resolves_relative_to_config(tmp_path):
    config = {
        "local_compilation": {
            "compiler": "v0.8.26",
            "inputs": {"0xAbC0000000000000000000000000000000000001": "inputs/Foo.json"},
        }
    }
    config_path = str(tmp_path / "cfg.yaml")
    resolved = _get_local_inputs(config, config_path)

    # address lowercased, path made absolute against the config directory
    expected = str(tmp_path / "inputs" / "Foo.json")
    assert resolved == {"0xabc0000000000000000000000000000000000001": expected}


def test_get_local_inputs_empty_when_absent(tmp_path):
    assert _get_local_inputs({}, str(tmp_path / "cfg.yaml")) == {}
