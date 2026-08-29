import pytest

from diffyscan.utils.explorer import BROWSER_USER_AGENT, get_contract_from_explorer

BLOCKSCOUT_HOSTS = [
    "robinhoodchain.blockscout.com",
    "eth.blockscout.com",
    "base.blockscout.com",
    "explorer.mode.network",
    "explorer.swellnetwork.io",
    "blockscout.lisk.com",
    "explorer.inkonchain.com",
    "testnet.routescan.io",
    "explorer.monadvision.com",
]
CONTRACT = "0x2bd3d5965b26b51814ac95127b2b80dd6ccc0fa1"


class DummyResponse:
    def json(self):
        return {
            "name": "AdaptiveCurveIrm",
            "compiler_version": "v0.8.19+commit.7dd6d404",
            "file_path": "src/AdaptiveCurveIrm.sol",
            "source_code": "contract AdaptiveCurveIrm {}",
            "additional_sources": [],
            "optimization_enabled": True,
            "optimization_runs": 999999,
            "evm_version": "paris",
        }


@pytest.mark.parametrize("hostname", BLOCKSCOUT_HOSTS)
def test_blockscout_request_sends_browser_user_agent(monkeypatch, hostname):
    calls = []

    def fake_fetch(url, headers=None):
        calls.append((url, headers))
        return DummyResponse()

    monkeypatch.setattr("diffyscan.utils.explorer.fetch", fake_fetch)

    get_contract_from_explorer(None, hostname, CONTRACT, "AdaptiveCurveIrm")

    assert calls
    assert calls[0][1] == {"User-Agent": BROWSER_USER_AGENT}


def test_browser_user_agent_looks_like_a_browser():
    assert BROWSER_USER_AGENT.startswith("Mozilla/5.0")
    assert "python-requests" not in BROWSER_USER_AGENT
