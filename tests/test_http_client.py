import pathlib
import re

import pytest

from diffyscan.utils.http_client import (
    DEFAULT_USER_AGENT,
    USER_AGENT_ENV_VAR,
    fetch,
    get_user_agent,
    pull,
)

HTTP_CLIENT_MODULE = "diffyscan.utils.http_client"


class DummyResponse:
    def raise_for_status(self):
        return None


@pytest.fixture
def get_calls(monkeypatch):
    calls = []

    def fake_get(url, headers=None):
        calls.append((url, headers))
        return DummyResponse()

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.get", fake_get)
    return calls


@pytest.fixture
def post_calls(monkeypatch):
    calls = []

    def fake_post(url, data=None, headers=None):
        calls.append((url, data, headers))
        return DummyResponse()

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.post", fake_post)
    return calls


def test_default_user_agent_identifies_diffyscan():
    assert "diffyscan/" in DEFAULT_USER_AGENT
    assert "python-requests" not in DEFAULT_USER_AGENT


def test_default_user_agent_passes_cloudflare_browser_checks():
    assert DEFAULT_USER_AGENT.startswith("Mozilla/5.0")


def test_env_var_overrides_user_agent(monkeypatch):
    monkeypatch.setenv(USER_AGENT_ENV_VAR, "custom-agent/1.0")
    assert get_user_agent() == "custom-agent/1.0"


def test_fetch_sends_default_user_agent(monkeypatch, get_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://example.com/api")

    assert get_calls == [
        ("https://example.com/api", {"User-Agent": DEFAULT_USER_AGENT})
    ]


def test_fetch_sends_overridden_user_agent(monkeypatch, get_calls):
    monkeypatch.setenv(USER_AGENT_ENV_VAR, "custom-agent/1.0")

    fetch("https://example.com/api")

    assert get_calls[0][1] == {"User-Agent": "custom-agent/1.0"}


def test_fetch_preserves_caller_headers(monkeypatch, get_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://example.com/api", headers={"Authorization": "token secret"})

    assert get_calls[0][1] == {
        "User-Agent": DEFAULT_USER_AGENT,
        "Authorization": "token secret",
    }


def test_fetch_lets_caller_override_user_agent(monkeypatch, get_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://example.com/api", headers={"User-Agent": "explicit/1.0"})

    assert get_calls[0][1] == {"User-Agent": "explicit/1.0"}


def test_pull_sends_default_user_agent(monkeypatch, post_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    pull("https://example.com/rpc", "{}", {"Content-Type": "application/json"})

    assert post_calls == [
        (
            "https://example.com/rpc",
            "{}",
            {
                "User-Agent": DEFAULT_USER_AGENT,
                "Content-Type": "application/json",
            },
        )
    ]


def test_no_direct_requests_usage_outside_http_client():
    package_dir = pathlib.Path(__file__).parent.parent / "diffyscan"
    direct_call_re = re.compile(r"\brequests\.(get|post|request|Session)\b")

    offenders = [
        str(path.relative_to(package_dir))
        for path in package_dir.rglob("*.py")
        if path.name != "http_client.py" and direct_call_re.search(path.read_text())
    ]

    assert not offenders, f"Use http_client.fetch/pull instead of requests: {offenders}"
