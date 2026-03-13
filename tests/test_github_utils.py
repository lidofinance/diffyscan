import base64
import json

from diffyscan.utils.github import (
    get_file_from_github,
    get_file_from_github_recursive,
    get_github_api_url,
    path_to_file_without_dependency,
    resolve_dep,
)


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_get_github_api_url():
    url = get_github_api_url("user/repo", "src", "file.sol", "abc123")
    assert (
        url == "https://api.github.com/repos/user/repo/contents/src/file.sol?ref=abc123"
    )


def test_path_to_file_without_dependency():
    result = path_to_file_without_dependency("@oz/contracts/token.sol", "@oz/contracts")
    assert result == "token.sol"


def test_resolve_dep():
    cfg = {
        "dependencies": {
            "@oz/contracts": {"url": "u", "commit": "c", "relative_root": ""}
        }
    }
    repo, dep_name = resolve_dep("@oz/contracts/token.sol", cfg)
    assert dep_name == "@oz/contracts"
    assert repo is not None
    assert repo["commit"] == "c"


def test_get_file_from_github_decodes_content(monkeypatch):
    captured = {}

    def fake_fetch(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        payload = {"content": base64.b64encode(b"contract Demo {}").decode()}
        return DummyResponse(payload)

    monkeypatch.setattr("diffyscan.utils.github.fetch", fake_fetch)

    content = get_file_from_github(
        "github-token",
        {
            "url": "https://github.com/user/repo",
            "commit": "abc123",
            "relative_root": "src",
        },
        "contracts/Demo.sol",
        None,
    )

    assert content == "contract Demo {}"
    assert (
        captured["url"]
        == "https://api.github.com/repos/user/repo/contents/src/contracts/Demo.sol?ref=abc123"
    )
    assert captured["headers"] == {"Authorization": "token github-token"}


def test_get_file_from_github_recursive_searches_nested_directories(monkeypatch):
    encoded = base64.b64encode(b"contract Nested {}").decode()

    def fake_fetch(url, headers=None):
        if url.endswith("/contents/contracts/Foo.sol?ref=abc123"):
            return DummyResponse({"type": "dir"})
        if url.endswith("/contents/contracts?ref=abc123"):
            return DummyResponse([{"type": "dir", "path": "contracts/nested"}])
        if url.endswith("/contents/contracts/nested/Foo.sol?ref=abc123"):
            return DummyResponse({"type": "file", "content": encoded})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("diffyscan.utils.github.fetch", fake_fetch)

    content = get_file_from_github_recursive(
        "github-token",
        {
            "url": "https://github.com/user/repo",
            "commit": "abc123",
            "relative_root": "contracts",
        },
        "Foo.sol",
        None,
    )

    assert content == "contract Nested {}"


def test_get_file_from_github_uses_cache(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_fetch(url, headers=None):
        calls["count"] += 1
        payload = {"content": base64.b64encode(b"contract Cached {}").decode()}
        return DummyResponse(payload)

    monkeypatch.setattr("diffyscan.utils.github.GITHUB_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("diffyscan.utils.github.fetch", fake_fetch)

    repo = {
        "url": "https://github.com/user/repo",
        "commit": "abc123",
        "relative_root": "src",
    }
    first = get_file_from_github(
        "github-token", repo, "contracts/Cached.sol", None, True
    )
    second = get_file_from_github(
        "github-token",
        repo,
        "contracts/Cached.sol",
        None,
        True,
    )

    assert first == second == "contract Cached {}"
    assert calls["count"] == 1


def test_get_file_from_github_ignores_tampered_cache(monkeypatch, tmp_path):
    calls = {"count": 0}

    def fake_fetch(url, headers=None):
        calls["count"] += 1
        payload = {"content": base64.b64encode(b"contract Cached {}").decode()}
        return DummyResponse(payload)

    monkeypatch.setattr("diffyscan.utils.github.GITHUB_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("diffyscan.utils.github.fetch", fake_fetch)

    repo = {
        "url": "https://github.com/user/repo",
        "commit": "abc123",
        "relative_root": "src",
    }
    first = get_file_from_github(
        "github-token", repo, "contracts/Cached.sol", None, True
    )

    cache_path = next(tmp_path.iterdir())
    tampered = json.loads(cache_path.read_text())
    tampered["value"] = "contract Tampered {}"
    cache_path.write_text(json.dumps(tampered))

    second = get_file_from_github(
        "github-token", repo, "contracts/Cached.sol", None, True
    )

    assert first == second == "contract Cached {}"
    assert calls["count"] == 2
