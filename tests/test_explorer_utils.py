import json

import pytest
import requests

from diffyscan.utils.custom_exceptions import ExplorerError
from diffyscan.utils.explorer import _get_contract_from_blockscout
from diffyscan.utils.explorer import _get_contract_from_etherscan
from diffyscan.utils.explorer import _get_contract_from_mantle
from diffyscan.utils.explorer import _get_contract_from_oklink
from diffyscan.utils.explorer import _get_contract_from_sourcify
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
        ("eth.blockscout.com", _get_contract_from_blockscout),
        ("eth.blockscout.com.evil.io", _get_contract_from_etherscan),
        ("explorer.mantle.xyz", _get_contract_from_mantle),
        ("evilblockscout.com", _get_contract_from_etherscan),
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


def test_blockscout_pro_puts_chain_id_in_path_and_sends_api_key(monkeypatch):
    urls = []

    class InvalidJSON:
        def json(self):
            raise ValueError("invalid JSON")

    def fake_fetch(url):
        urls.append(url)
        return InvalidJSON()

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)
    fetcher, requires_token = _get_explorer_fetcher("api.blockscout.com")
    assert requires_token
    with pytest.raises(ExplorerError, match="Invalid Blockscout JSON"):
        fetcher("key", "api.blockscout.com", "0xabc", 5042)
    assert urls == [
        "https://api.blockscout.com/5042/api/v2/smart-contracts/0xabc?apikey=key"
    ]


def test_blockscout_pro_requires_chain_id(monkeypatch):
    monkeypatch.setattr(
        "diffyscan.utils.explorer.fetch",
        lambda url: pytest.fail(f"unexpected request {url}"),
    )
    fetcher, _ = _get_explorer_fetcher("api.blockscout.com")
    with pytest.raises(ExplorerError, match="needs explorer_chain_id"):
        fetcher("key", "api.blockscout.com", "0xabc", None)


class SourcifyHTTPResponse:
    """An answer as `requests.get` gives it: Sourcify sends 404 and 400 with a JSON body."""

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.headers: dict = {}
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self.payload, str):
            raise ValueError("not JSON")
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Client Error", response=self  # type: ignore[arg-type]
            )


def _serve_sourcify(monkeypatch, payload, status_code=200):
    """Answer each GET of the real `fetch` with one Sourcify answer; return the URLs."""
    from diffyscan.utils.http_client import reset_pacing

    urls = []

    def fake_get(url, headers=None):
        urls.append(url)
        return SourcifyHTTPResponse(payload, status_code)

    reset_pacing()
    monkeypatch.setattr("diffyscan.utils.http_client.requests.get", fake_get)
    monkeypatch.setattr("diffyscan.utils.http_client.time.sleep", lambda delay: None)
    return urls


def _sourcify_payload(**fields):
    payload = {
        "match": "exact_match",
        "creationMatch": "exact_match",
        "runtimeMatch": "exact_match",
        "chainId": "1672",
        "address": "0xabc",
        "compilation": {
            "language": "Solidity",
            "compiler": "solc",
            "compilerVersion": "0.8.33+commit.64118f21",
            "name": "Demo",
            "fullyQualifiedName": "src/Demo.sol:Demo",
        },
        "stdJsonInput": {
            "language": "Solidity",
            "sources": {"src/Demo.sol": {"content": "contract Demo {}"}},
            "settings": {
                "viaIR": True,
                "optimizer": {"enabled": True, "runs": 200},
                "evmVersion": "prague",
                "remappings": ["forge-std/=lib/forge-std/src/"],
            },
        },
        "creationBytecode": {
            "transformationValues": {"constructorArguments": "0x" + "00" * 31 + "2a"}
        },
    }
    payload.update(fields)
    return payload


def test_get_contract_from_sourcify_builds_solc_input(monkeypatch):
    urls = _serve_sourcify(monkeypatch, _sourcify_payload())
    logged = []
    monkeypatch.setattr(
        "diffyscan.utils.explorer.logger.info",
        lambda text, value=None: logged.append((text, value)),
    )

    contract = _get_contract_from_sourcify("sourcify.dev", "0xabc", 1672)

    assert urls == [
        "https://sourcify.dev/server/v2/contract/1672/0xabc"
        "?fields=compilation,stdJsonInput,creationBytecode.transformationValues"
    ]
    assert contract["name"] == "Demo"
    assert contract["compiler"] == "v0.8.33+commit.64118f21"
    assert contract["solcInput"]["sources"] == {
        "src/Demo.sol": {"content": "contract Demo {}"}
    }
    settings = contract["solcInput"]["settings"]
    assert settings["viaIR"] is True
    assert settings["optimizer"] == {"enabled": True, "runs": 200}
    assert settings["remappings"] == ["forge-std/=lib/forge-std/src/"]
    assert "evm.deployedBytecode" in settings["outputSelection"]["*"]["*"]
    assert contract["evm_version"] == "prague"
    assert contract["constructor_arguments"] == "00" * 31 + "2a"
    assert logged == [
        ("Sourcify match", "exact_match (creation: exact_match, runtime: exact_match)")
    ]


@pytest.mark.parametrize(
    "fields",
    [
        # A runtime-only match: Sourcify did not match the creation bytecode.
        {
            "match": "match",
            "creationMatch": None,
            "runtimeMatch": "match",
            "creationBytecode": {"transformationValues": None},
        },
        # A creation match of a contract without constructor arguments.
        {"creationBytecode": {"transformationValues": {}}},
    ],
)
def test_get_contract_from_sourcify_reads_a_match_without_constructor_arguments(
    monkeypatch, fields
):
    _serve_sourcify(monkeypatch, _sourcify_payload(**fields))

    contract = _get_contract_from_sourcify("sourcify.dev", "0xabc", 1672)

    assert contract["name"] == "Demo"
    assert "constructor_arguments" not in contract


def test_get_contract_from_sourcify_keeps_settings_without_an_optimizer(monkeypatch):
    standard_json = _sourcify_payload()["stdJsonInput"]
    del standard_json["settings"]["optimizer"]
    _serve_sourcify(monkeypatch, _sourcify_payload(stdJsonInput=standard_json))

    contract = _get_contract_from_sourcify("sourcify.dev", "0xabc", 1672)

    # An added optimizer block changes the metadata hash of the compiled bytecode.
    assert "optimizer" not in contract["solcInput"]["settings"]


@pytest.mark.parametrize(
    ("payload", "status_code", "chain_id", "message"),
    [
        # Captured answers of sourcify.dev: status and body.
        (
            {"match": None, "creationMatch": None, "runtimeMatch": None},
            404,
            1672,
            "not verified",
        ),
        (
            {
                "customCode": "unsupported_chain",
                "message": "Chain 123456789 not found",
                "errorId": "09e212c3",
            },
            400,
            123456789,
            "Chain 123456789 not found",
        ),
        ("<html>Not Found</html>", 404, 1672, "Invalid Sourcify JSON"),
        (["not", "an", "object"], 200, 1672, "Unexpected Sourcify response"),
        ({"match": "exact_match", "compilation": {}}, 200, 1672, "Unexpected Sourcify"),
        (_sourcify_payload(match="no_match"), 200, 1672, "Unexpected Sourcify match"),
    ],
)
def test_get_contract_from_sourcify_rejects_bad_responses(
    monkeypatch, payload, status_code, chain_id, message
):
    _serve_sourcify(monkeypatch, payload, status_code)

    with pytest.raises(ExplorerError, match=message):
        _get_contract_from_sourcify("sourcify.dev", "0xabc", chain_id)


def test_get_contract_from_sourcify_needs_a_chain_id(monkeypatch):
    urls = _serve_sourcify(monkeypatch, _sourcify_payload())

    with pytest.raises(ExplorerError, match="explorer_chain_id"):
        _get_contract_from_sourcify("sourcify.dev", "0xabc", None)

    assert urls == []


def _standard_json(**fields):
    standard_json = _sourcify_payload()["stdJsonInput"]
    standard_json.update(fields)
    return {"stdJsonInput": standard_json}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"compilation": {"language": "Solidity", "name": "Demo"}}, "compilerVersion"),
        (
            {
                "compilation": {
                    "language": "Vyper",
                    "name": "Demo",
                    "compilerVersion": "0.4.3+commit.bff19ea2",
                }
            },
            "not Solidity",
        ),
        (_standard_json(sources={}), "Invalid Sourcify sources"),
        (
            _standard_json(sources={"a.sol": "contract Demo {}"}),
            "Invalid Sourcify sources",
        ),
        (
            _standard_json(sources={"a.sol": {"urls": ["ipfs://x"]}}),
            "Invalid Sourcify sources",
        ),
        (
            _standard_json(sources={"a.sol": {"content": None}}),
            "Invalid Sourcify sources",
        ),
        (_standard_json(settings=[]), "Invalid Sourcify settings"),
    ],
)
def test_get_contract_from_sourcify_rejects_invalid_fields(
    monkeypatch, fields, message
):
    _serve_sourcify(monkeypatch, _sourcify_payload(**fields))

    with pytest.raises(ExplorerError, match=message):
        _get_contract_from_sourcify("sourcify.dev", "0xabc", 1672)


def test_sourcify_dispatch_passes_the_chain_id(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "diffyscan.utils.explorer._get_contract_from_sourcify",
        lambda hostname, address, chain_id: calls.append((hostname, address, chain_id)),
    )

    fetcher, requires_token = _get_explorer_fetcher("sourcify.dev")
    fetcher("token", "sourcify.dev", "0xabc", 1672)

    assert requires_token is True
    assert calls == [("sourcify.dev", "0xabc", 1672)]
    assert _get_explorer_fetcher("evilsourcify.dev")[0] is _get_contract_from_etherscan


def test_get_contract_from_explorer_reads_sourcify_and_caches_the_answer(
    monkeypatch, tmp_path
):
    urls = _serve_sourcify(monkeypatch, _sourcify_payload())
    monkeypatch.setattr("diffyscan.utils.explorer.CACHE_DIR", str(tmp_path))

    first = get_contract_from_explorer(
        None, "sourcify.dev", "0xabc", "Demo", 1672, use_cache=True
    )
    second = get_contract_from_explorer(
        None, "sourcify.dev", "0xabc", "Demo", 1672, use_cache=True
    )

    assert first == second
    assert first["compiler"] == "v0.8.33+commit.64118f21"
    assert len(urls) == 1
    with pytest.raises(ExplorerError, match="does not match"):
        get_contract_from_explorer(None, "sourcify.dev", "0xabc", "Other", 1672)
