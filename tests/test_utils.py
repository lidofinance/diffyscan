import pytest

from diffyscan.diffyscan import is_standard_json_contract
from diffyscan.utils.common import mask_text, pull


def test_single_file_format():
    source_files = [("Contract", {"content": "contract Contract { ... }"})]
    assert not is_standard_json_contract(source_files)


def test_standard_json_format():
    source_files = {
        "src/Contract.sol": {"content": "contract C {}"},
        "src/Dependency.sol": {"content": "contract D {}"},
    }
    assert is_standard_json_contract(source_files)


class DummyHttpResponse:
    def raise_for_status(self):
        return None


def test_pull_masks_rpc_url_in_logs(monkeypatch):
    logs = []
    url = "https://rpc.example/super-secret-token"

    monkeypatch.setattr(
        "diffyscan.utils.common.requests.post",
        lambda request_url, data=None, headers=None: DummyHttpResponse(),
    )
    monkeypatch.setattr("diffyscan.utils.common.logger.log", logs.append)

    pull(url, "{}", {"Content-Type": "application/json"})

    assert logs == [f"Pull: {mask_text(url)}"]
