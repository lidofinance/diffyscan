import json

import pytest

from diffyscan.diffyscan import _get_local_inputs
from diffyscan.utils.common import load_config
from diffyscan.utils.custom_exceptions import ExplorerError
from diffyscan.utils.explorer import build_contract_from_local_input


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
    assert contract.get("libraries") is None
    assert contract.get("constructor_arguments") is None
    assert "contracts/Foo.sol" in contract["solcInput"]["sources"]
    # outputSelection is forced so bytecode parsing always has what it needs
    output_selection = contract["solcInput"]["settings"]["outputSelection"]
    assert "evm.deployedBytecode" in output_selection["*"]["*"]


def test_build_contract_from_local_input_keeps_libraries(tmp_path):
    lib_address = "0x" + "11" * 20
    payload = {
        "language": "Solidity",
        "sources": {"contracts/Lib.sol": {"content": "library Lib {}"}},
        "settings": {"libraries": {"contracts/Lib.sol": {"Lib": lib_address}}},
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload))

    contract = build_contract_from_local_input("Lib", str(path), "v0.8.26")
    assert contract["libraries"] == {"contracts/Lib.sol": {"Lib": lib_address}}


def test_build_contract_from_local_input_errors(tmp_path):
    missing_sources = tmp_path / "bad.json"
    missing_sources.write_text(json.dumps({"language": "Solidity"}))
    not_json = tmp_path / "not.json"
    not_json.write_text("{nope")
    for path in (missing_sources, not_json, tmp_path / "does_not_exist.json"):
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


def test_get_local_inputs_keeps_absolute_paths(tmp_path):
    absolute = str(tmp_path / "elsewhere" / "Foo.json")
    config = {
        "local_compilation": {
            "compiler": "v0.8.26",
            "inputs": {"0xAbC0000000000000000000000000000000000001": absolute},
        }
    }
    resolved = _get_local_inputs(config, str(tmp_path / "cfg.yaml"))
    assert resolved == {"0xabc0000000000000000000000000000000000001": absolute}


def test_build_contract_from_local_input_null_settings(tmp_path):
    payload = {
        "language": "Solidity",
        "sources": {"contracts/Foo.sol": {"content": "contract Foo {}"}},
        "settings": None,
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload))

    contract = build_contract_from_local_input("Foo", str(path), "v0.8.26")
    output_selection = contract["solcInput"]["settings"]["outputSelection"]
    assert "evm.deployedBytecode" in output_selection["*"]["*"]


def test_yaml_unquoted_local_input_address_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "contracts:\n"
        '  "0x0000000000000000000000000000000000000001": Foo\n'
        "local_compilation:\n"
        "  compiler: v0.8.26\n"
        "  inputs:\n"
        "    0x0000000000000000000000000000000000000001: inputs/foo.json\n"
    )
    with pytest.raises(ValueError, match="local_compilation.inputs"):
        load_config(str(path))


def test_get_local_inputs_empty_when_absent(tmp_path):
    assert _get_local_inputs({}, str(tmp_path / "cfg.yaml")) == {}
    assert _get_local_inputs({"local_compilation": {}}, str(tmp_path / "c.yaml")) == {}
