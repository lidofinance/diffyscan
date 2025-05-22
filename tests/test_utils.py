import pytest

from diffyscan.diffyscan import is_standard_json_contract


def test_single_file_format():
    source_files = [("Contract", {"content": "contract Contract { ... }"})]
    assert not is_standard_json_contract(source_files)


def test_standard_json_format():
    source_files = {
        "src/Contract.sol": {"content": "contract C {}"},
        "src/Dependency.sol": {"content": "contract D {}"},
    }
    assert is_standard_json_contract(source_files)
