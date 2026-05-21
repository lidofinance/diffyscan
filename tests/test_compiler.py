"""Tests for diffyscan.utils.compiler.compile_contracts error handling."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from diffyscan.utils.compiler import compile_contracts
from diffyscan.utils.custom_exceptions import CompileError


def _fake_run(stdout: bytes):
    def runner(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr=b"", returncode=0)

    return runner


def test_compile_contracts_raises_when_output_has_no_contracts(monkeypatch):
    """solc returning only errors must surface a CompileError, not KeyError downstream."""
    errors_only = json.dumps(
        {
            "errors": [
                {
                    "severity": "error",
                    "formattedMessage": (
                        'ParserError: Source "@openzeppelin/contracts/utils/'
                        'cryptography/MessageHashUtils.sol" not found.'
                    ),
                    "message": "Source not found",
                }
            ]
        }
    ).encode()

    monkeypatch.setattr(subprocess, "run", _fake_run(errors_only))

    with pytest.raises(CompileError) as excinfo:
        compile_contracts("/fake/solc", "{}")

    msg = str(excinfo.value)
    assert "solc returned no contracts" in msg
    assert "MessageHashUtils.sol" in msg


def test_compile_contracts_filters_warnings_when_no_contracts(monkeypatch):
    """Warnings should be ignored when picking which messages to surface."""
    payload = json.dumps(
        {
            "errors": [
                {"severity": "warning", "message": "spdx warning"},
                {
                    "severity": "error",
                    "formattedMessage": "DeclarationError: Identifier not found.",
                },
            ]
        }
    ).encode()

    monkeypatch.setattr(subprocess, "run", _fake_run(payload))

    with pytest.raises(CompileError) as excinfo:
        compile_contracts("/fake/solc", "{}")

    msg = str(excinfo.value)
    assert "DeclarationError" in msg
    assert "spdx warning" not in msg
    assert "1 error(s)" in msg


def test_compile_contracts_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(b"not json at all"))

    with pytest.raises(CompileError) as excinfo:
        compile_contracts("/fake/solc", "{}")

    assert "non-JSON output" in str(excinfo.value)


def test_compile_contracts_returns_output_on_success(monkeypatch):
    payload = json.dumps(
        {"contracts": {"Demo.sol": {"Demo": {"abi": [], "evm": {}}}}}
    ).encode()
    monkeypatch.setattr(subprocess, "run", _fake_run(payload))

    result = compile_contracts("/fake/solc", "{}")
    assert "contracts" in result
    assert "Demo" in result["contracts"]["Demo.sol"]
