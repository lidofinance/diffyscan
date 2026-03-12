from diffyscan.utils.explorer import get_contract_from_explorer, get_explorer_hostname


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_get_explorer_hostname_direct():
    cfg = {"explorer_hostname": "api.etherscan.io"}
    assert get_explorer_hostname(cfg) == "api.etherscan.io"


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
