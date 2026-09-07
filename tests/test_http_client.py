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


class FailingResponse:
    def __init__(self, headers, text):
        self.headers = headers
        self.text = text

    def raise_for_status(self):
        import requests

        raise requests.exceptions.HTTPError(
            "403 Client Error: Forbidden", response=self  # type: ignore[arg-type]
        )


def _fetch_error_message(monkeypatch, response) -> str:
    from diffyscan.utils.custom_exceptions import ExplorerError

    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda url, headers=None: response
    )
    with pytest.raises(ExplorerError) as exc_info:
        fetch("https://example.com/api")
    return str(exc_info.value)


def test_cloudflare_challenge_error_gives_hint_instead_of_html(monkeypatch):
    challenge_html = "<html>Just a moment...</html>" * 100
    message = _fetch_error_message(
        monkeypatch, FailingResponse({"cf-mitigated": "challenge"}, challenge_html)
    )

    assert "Cloudflare challenge" in message
    assert USER_AGENT_ENV_VAR in message
    assert "Just a moment" not in message


def test_plain_http_error_still_includes_response_body(monkeypatch):
    message = _fetch_error_message(monkeypatch, FailingResponse({}, "rate limited"))

    assert "Response: rate limited" in message


def test_http_error_hides_request_url_with_credentials(monkeypatch):
    from diffyscan.utils.custom_exceptions import ExplorerError

    url = "https://example.com/api?apikey=SECRET-TOKEN"

    class LeakyResponse(FailingResponse):
        def raise_for_status(self):
            import requests

            raise requests.exceptions.HTTPError(
                f"401 Client Error: Unauthorized for url: {url}",
                response=self,  # type: ignore[arg-type]
            )

    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get",
        lambda url, headers=None: LeakyResponse({}, "denied"),
    )
    with pytest.raises(ExplorerError) as exc_info:
        fetch(url)

    message = str(exc_info.value)
    assert "SECRET-TOKEN" not in message
    assert "401 Client Error" in message
    assert "Response: denied" in message
    # The chained requests exception would print the raw URL in tracebacks
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_connection_error_hides_request_url(monkeypatch):
    import requests

    from diffyscan.utils.custom_exceptions import NodeError

    url = "https://rpc.example.com/v3/SECRET-KEY"

    def failing_post(url, data=None, headers=None):
        raise requests.exceptions.ConnectionError(f"Failed to connect to {url}")

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.post", failing_post)
    with pytest.raises(NodeError) as exc_info:
        pull(url, "{}")

    assert "SECRET-KEY" not in str(exc_info.value)


@pytest.mark.parametrize("path", ["/v3/SECRET-KEY", "/api?apikey=SECRET-KEY"])
def test_connection_error_hides_relative_request_url(monkeypatch, path):
    import traceback

    import requests
    from urllib3.connectionpool import HTTPSConnectionPool
    from urllib3.exceptions import MaxRetryError

    from diffyscan.utils.custom_exceptions import NodeError

    def failing_post(url, data=None, headers=None):
        raise requests.exceptions.ConnectionError(
            MaxRetryError(
                HTTPSConnectionPool("rpc.example.com"), path, OSError("offline")
            )
        )

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.post", failing_post)
    with pytest.raises(NodeError) as exc_info:
        pull(f"https://rpc.example.com{path}", "{}")

    assert "SECRET-KEY" not in str(exc_info.value)
    assert "SECRET-KEY" not in "".join(traceback.format_exception(exc_info.value))
    assert "Max retries exceeded" in str(exc_info.value)


def test_no_direct_requests_usage_outside_http_client():
    package_dir = pathlib.Path(__file__).parent.parent / "diffyscan"
    direct_call_re = re.compile(
        r"\brequests\.(get|post|put|patch|delete|head|options|request|Session)\b"
        r"|\bfrom\s+requests\s+import\b"
    )

    offenders = [
        str(path.relative_to(package_dir))
        for path in package_dir.rglob("*.py")
        if path.name != "http_client.py" and direct_call_re.search(path.read_text())
    ]

    assert not offenders, f"Use http_client.fetch/pull instead of requests: {offenders}"
