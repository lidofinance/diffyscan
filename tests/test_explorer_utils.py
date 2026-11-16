import json

import pytest

from diffyscan.utils.custom_exceptions import ExplorerError
from diffyscan.utils.explorer import _get_contract_from_blockscout
from diffyscan.utils.explorer import _get_contract_from_etherscan
from diffyscan.utils.explorer import _get_contract_from_mantle
from diffyscan.utils.explorer import _get_contract_from_oklink
from diffyscan.utils.explorer import _get_explorer_fetcher

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


@pytest.mark.parametrize(
    ("hostname", "fetcher"),
    [
        ("api.xlayerscan.com", _get_contract_from_blockscout),
        ("eth.blockscout.com", _get_contract_from_blockscout),
        ("explorer.mantle.xyz", _get_contract_from_mantle),
        ("evilblockscout.com", _get_contract_from_etherscan),
        ("evilxlayerscan.com", _get_contract_from_etherscan),
        ("api.xlayerscan.com.evil.io", _get_contract_from_etherscan),
        ("evilmantle.xyz", _get_contract_from_etherscan),
        ("evillineascan.build", _get_contract_from_etherscan),
    ],
)
def test_explorer_domains_match_on_a_dot_boundary(hostname, fetcher):
    assert _get_explorer_fetcher(hostname)[0] is fetcher


def _oklink_response(source_code, **fields):
    data = {
        "contractName": "Demo",
        "sourceCode": source_code,
        "compilerVersion": "v0.8.25+commit.b61c2a91",
        "optimization": "1",
        "optimizationRuns": "200",
        "evmVersion": "default",
        "libraryInfo": "",
        "remappings": ["forge-std/=lib/forge-std/src/"],
    }
    data.update(fields)
    return DummyResponse({"code": "0", "msg": "", "data": [data]})


def test_get_contract_from_oklink_builds_solc_input(monkeypatch):
    urls = []
    # OKLink returns UTF-8 source decoded as Latin-1.
    garbled = "// a \u2014 b".encode("utf-8").decode("latin-1")
    source = json.dumps(
        {"language": "Solidity", "sources": {"src/Demo.sol": {"content": garbled}}}
    )

    def fake_fetch(url):
        urls.append(url)
        return _oklink_response(source)

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)

    contract = _get_contract_from_oklink("www.oklink.com", "0xabc", 196)

    assert urls == [
        "https://www.oklink.com/api/v5/explorer/contract/verify-contract-info"
        "?chainShortName=XLAYER&contractAddress=0xabc"
    ]
    assert contract["name"] == "Demo"
    assert contract["compiler"] == "v0.8.25+commit.b61c2a91"
    assert contract["solcInput"]["sources"] == {
        "src/Demo.sol": {"content": "// a \u2014 b"}
    }
    settings = contract["solcInput"]["settings"]
    assert settings["optimizer"] == {"enabled": True, "runs": 200}
    assert settings["remappings"] == ["forge-std/=lib/forge-std/src/"]
    assert "evm_version" not in contract
    assert "constructor_arguments" not in contract


def test_get_contract_from_oklink_reads_a_single_file(monkeypatch):
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch",
        lambda url: _oklink_response("contract Demo {}", evmVersion="cancun"),
    )

    contract = _get_contract_from_oklink("www.oklink.com", "0xabc", 196)

    assert contract["solcInput"]["sources"] == {"Demo": {"content": "contract Demo {}"}}
    assert contract["evm_version"] == "cancun"


@pytest.mark.parametrize(
    ("payload", "chain_id", "message"),
    [
        ({"code": "0", "msg": "", "data": []}, 196, "not verified"),
        ({"code": "50038", "msg": "No chain", "data": []}, 196, "No chain"),
        ({"code": "0", "msg": "", "data": []}, 1, "short name"),
        ({"code": "0", "msg": "", "data": [{"contractName": "Demo"}]}, 196, "Invalid"),
    ],
)
def test_get_contract_from_oklink_rejects_bad_responses(
    monkeypatch, payload, chain_id, message
):
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch", lambda url: DummyResponse(payload)
    )

    with pytest.raises(ExplorerError, match=message):
        _get_contract_from_oklink("www.oklink.com", "0xabc", chain_id)


def test_oklink_dispatch_passes_the_chain_id(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "diffyscan.utils.explorer._get_contract_from_oklink",
        lambda hostname, address, chain_id: calls.append((hostname, address, chain_id)),
    )

    fetcher, requires_token = _get_explorer_fetcher("www.oklink.com")
    fetcher("token", "www.oklink.com", "0xabc", 196)

    assert requires_token is True
    assert calls == [("www.oklink.com", "0xabc", 196)]
    assert _get_explorer_fetcher("eviloklink.com")[0] is _get_contract_from_etherscan


def test_get_contract_from_oklink_keeps_submitted_settings(monkeypatch):
    source = json.dumps(
        {
            "language": "Solidity",
            "sources": {"src/Demo.sol": {"content": "contract Demo {}"}},
            "settings": {"viaIR": True, "optimizer": {"enabled": True, "runs": 1}},
        }
    )
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch", lambda url: _oklink_response(source)
    )

    settings = _get_contract_from_oklink("www.oklink.com", "0xabc", 196)["solcInput"][
        "settings"
    ]

    assert settings["viaIR"] is True
    assert settings["optimizer"] == {"enabled": True, "runs": 1}
    assert settings["remappings"] == ["forge-std/=lib/forge-std/src/"]
