import json

import pytest

from diffyscan.utils.custom_exceptions import ExplorerError
from diffyscan.utils.explorer import _get_contract_from_blockscout

from diffyscan.utils.explorer import get_contract_from_explorer


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_get_contract_from_explorer_uses_cache(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_fetch(url):
        calls["count"] += 1
        return DummyResponse(
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
            }
        )

    monkeypatch.setattr("diffyscan.utils.explorer.CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)

    first = get_contract_from_explorer(
        None,
        "api.etherscan.io",
        "0x0000000000000000000000000000000000000001",
        "Demo",
        use_cache=True,
    )
    second = get_contract_from_explorer(
        None,
        "api.etherscan.io",
        "0x0000000000000000000000000000000000000001",
        "Demo",
        use_cache=True,
    )

    assert first["name"] == second["name"] == "Demo"
    assert calls["count"] == 1


def test_get_contract_from_explorer_ignores_tampered_cache(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_fetch(url):
        calls["count"] += 1
        return DummyResponse(
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
            }
        )

    monkeypatch.setattr("diffyscan.utils.explorer.CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)

    first = get_contract_from_explorer(
        None,
        "api.etherscan.io",
        "0x0000000000000000000000000000000000000001",
        "Demo",
        use_cache=True,
    )

    cache_path = next(tmp_path.iterdir())
    tampered = json.loads(cache_path.read_text())
    tampered["value"]["name"] = "Tampered"
    cache_path.write_text(json.dumps(tampered))

    second = get_contract_from_explorer(
        None,
        "api.etherscan.io",
        "0x0000000000000000000000000000000000000001",
        "Demo",
        use_cache=True,
    )

    assert first["name"] == second["name"] == "Demo"
    assert calls["count"] == 2


BLOCKSCOUT_SOURCE = {
    "name": "Demo",
    "file_path": "Demo.sol",
    "source_code": "contract Demo {}",
    "compiler_version": "v0.8.25+commit.b61c2a91",
}


@pytest.mark.parametrize("payload", [None, [], "error", 42])
def test_blockscout_rejects_non_object_response(monkeypatch, payload):
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch", lambda url: DummyResponse(payload)
    )
    with pytest.raises(ExplorerError, match="response object"):
        _get_contract_from_blockscout("eth.blockscout.com", "0xabc")


@pytest.mark.parametrize(
    "field", ["name", "file_path", "source_code", "compiler_version"]
)
@pytest.mark.parametrize("value", [None, [], 123, ""])
def test_blockscout_rejects_invalid_required_fields(monkeypatch, field, value):
    payload = {**BLOCKSCOUT_SOURCE, field: value}
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch", lambda url: DummyResponse(payload)
    )
    with pytest.raises(ExplorerError):
        _get_contract_from_blockscout("eth.blockscout.com", "0xabc")


@pytest.mark.parametrize("field", ["file_path", "source_code", "compiler_version"])
def test_blockscout_rejects_missing_required_fields(monkeypatch, field):
    payload = dict(BLOCKSCOUT_SOURCE)
    del payload[field]
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch", lambda url: DummyResponse(payload)
    )
    with pytest.raises(ExplorerError, match=field):
        _get_contract_from_blockscout("eth.blockscout.com", "0xabc")


@pytest.mark.parametrize(
    "field,value",
    [
        ("additional_sources", {}),
        ("additional_sources", [None]),
        ("additional_sources", [{"file_path": "A.sol"}]),
        ("additional_sources", [{"file_path": [], "source_code": ""}]),
        ("compiler_settings", []),
        ("compiler_settings", "invalid"),
        ("optimization_runs", "invalid"),
        ("optimization_runs", []),
        ("optimization_runs", True),
    ],
)
def test_blockscout_rejects_invalid_optional_fields(monkeypatch, field, value):
    payload = {**BLOCKSCOUT_SOURCE, field: value}
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch", lambda url: DummyResponse(payload)
    )
    with pytest.raises(ExplorerError, match=field):
        _get_contract_from_blockscout("eth.blockscout.com", "0xabc")


def test_blockscout_reports_invalid_json(monkeypatch):
    class InvalidJSON:
        def json(self):
            raise ValueError("invalid JSON")

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", lambda url: InvalidJSON())
    with pytest.raises(ExplorerError, match="Invalid Blockscout JSON"):
        _get_contract_from_blockscout("eth.blockscout.com", "0xabc")
