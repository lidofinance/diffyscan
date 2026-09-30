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
    status_code = 200

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
        (
            "https://example.com/api",
            {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://example.com/"},
        )
    ]


def test_fetch_sends_overridden_user_agent(monkeypatch, get_calls):
    monkeypatch.setenv(USER_AGENT_ENV_VAR, "custom-agent/1.0")

    fetch("https://example.com/api")

    assert get_calls[0][1] == {
        "User-Agent": "custom-agent/1.0",
        "Referer": "https://example.com/",
    }


def test_fetch_preserves_caller_headers(monkeypatch, get_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://example.com/api", headers={"Authorization": "token secret"})

    assert get_calls[0][1] == {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://example.com/",
        "Authorization": "token secret",
    }


def test_fetch_lets_caller_override_user_agent(monkeypatch, get_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://example.com/api", headers={"User-Agent": "explicit/1.0"})

    assert get_calls[0][1] == {
        "User-Agent": "explicit/1.0",
        "Referer": "https://example.com/",
    }


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
    def __init__(self, headers, text, status_code=403):
        self.headers = headers
        self.text = text
        self.status_code = status_code

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


def test_fetch_sends_a_same_origin_referer(monkeypatch, get_calls):
    """Cloudflare in front of some Blockscout instances answers 403 to a request carrying no
    Referer, whatever its User-Agent says."""
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://explorer.example/api/v2/smart-contracts/0xabc")

    assert get_calls[0][1]["Referer"] == "https://explorer.example/"


def test_the_referer_carries_the_origin_and_never_the_query(monkeypatch, get_calls):
    """An explorer URL carries the API key in its query string -- which is why this module
    redacts URLs from its own error text. A Referer is logged at the other end, so it gets the
    origin and nothing else."""
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("https://api.explorer.example/api?module=contract&apikey=SECRET")

    referer = get_calls[0][1]["Referer"]
    assert referer == "https://api.explorer.example/"
    assert "SECRET" not in referer and "?" not in referer


def test_a_caller_s_own_referer_is_left_alone(monkeypatch, get_calls):
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch(
        "https://explorer.example/api",
        headers={"Referer": "https://elsewhere.example/"},
    )

    assert get_calls[0][1]["Referer"] == "https://elsewhere.example/"


def test_a_url_with_no_host_gets_no_referer(monkeypatch, get_calls):
    """A relative or malformed URL has no origin to send back, and inventing one would be a
    header that says something untrue."""
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    fetch("not-a-url")

    assert "Referer" not in get_calls[0][1]


def test_posting_to_a_node_sends_no_referer(monkeypatch, post_calls):
    """`pull` talks to JSON-RPC nodes, not to websites. Nothing there asks for a Referer, and
    the header would only widen what a node operator sees."""
    monkeypatch.delenv(USER_AGENT_ENV_VAR, raising=False)

    pull("https://node.example/rpc", "{}", {"Content-Type": "application/json"})

    assert "Referer" not in post_calls[0][2]


def test_each_host_gets_its_own_queue(monkeypatch):
    """Rate limits on one host must not delay requests to another."""
    from diffyscan.utils.http_client import reserve_slot, reset_pacing

    reset_pacing()
    assert reserve_slot("https://api.etherscan.io/v2/api", now=100.0) == 0
    assert reserve_slot("https://one.blockscout.com/api", now=100.0) == 0
    assert reserve_slot("https://api.etherscan.io/v2/api", now=100.0) == pytest.approx(
        1 / 3
    )


def test_blockscout_has_no_assumed_per_minute_limit():
    from diffyscan.utils.http_client import reserve_slot, reset_pacing

    reset_pacing()
    reserve_slot("https://one.blockscout.com/api", now=100.0)
    assert reserve_slot("https://one.blockscout.com/api", now=100.0) == pytest.approx(
        1 / 3
    )


def test_bare_limit_does_not_imply_a_window():
    from diffyscan.utils.http_client import learn_rate_limit, reset_pacing

    reset_pacing()
    assert learn_rate_limit(
        "https://one.blockscout.com/api", {"X-RateLimit-Limit": "10"}, now=100.0
    ) == pytest.approx(2 / 3)


def test_retry_after_says_when_to_resume():
    from diffyscan.utils.http_client import learn_rate_limit, reserve_slot, reset_pacing

    reset_pacing()
    learn_rate_limit("https://two.blockscout.com/api", {"Retry-After": "30"}, now=100.0)

    assert reserve_slot("https://two.blockscout.com/api", now=100.0) == pytest.approx(
        30.0
    )


@pytest.fixture(autouse=True)
def pacing_clock(monkeypatch):
    from diffyscan.utils.http_client import reset_pacing

    reset_pacing()
    sleeps: list[float] = []
    clock = {"now": 100.0, "sleeps": sleeps}

    def sleep(delay):
        sleeps.append(delay)
        clock["now"] += delay

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.time.monotonic", lambda: clock["now"])
    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.time.sleep", sleep)
    return clock


@pytest.mark.parametrize(
    "authority", ["user:SECRET@host.example:8443", "user:SECRET@[::1]:8443"]
)
def test_referer_strips_userinfo(get_calls, authority):
    fetch(f"https://{authority}/api?apikey=OTHER")
    assert get_calls[0][1]["Referer"] == f"https://{authority.rsplit('@', 1)[-1]}/"


@pytest.mark.parametrize("retry_after", ["120", "Wed, 30 Sep 2026 14:02:00 GMT"])
def test_fetch_retries_current_get_after_explicit_cooldown(
    monkeypatch, pacing_clock, retry_after
):
    from datetime import datetime, timezone

    epoch = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.time.time", lambda: epoch)
    calls = []
    success = DummyResponse()

    def get(url, headers=None):
        calls.append(url)
        return (
            FailingResponse({"Retry-After": retry_after}, "limited", 429)
            if len(calls) == 1
            else success
        )

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.get", get)
    assert fetch("https://example.com/api") is success
    assert len(calls) == 2
    assert pacing_clock["sleeps"] == [120.0]


@pytest.mark.parametrize("retry_after", ["invalid", "NaN", "inf"])
def test_invalid_retry_after_uses_backoff(monkeypatch, pacing_clock, retry_after):
    responses = iter(
        [FailingResponse({"Retry-After": retry_after}, "limited", 429), DummyResponse()]
    )
    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda *args, **kwargs: next(responses)
    )
    fetch("https://example.com/api")
    assert pacing_clock["sleeps"] == [pytest.approx(2 / 3)]


def test_get_retries_are_bounded(monkeypatch):
    from diffyscan.utils.custom_exceptions import ExplorerError
    from diffyscan.utils.http_client import MAX_RATE_LIMIT_RETRIES

    calls = []

    def get(*args, **kwargs):
        calls.append(args)
        return FailingResponse({}, "limited", 429)

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.get", get)
    with pytest.raises(ExplorerError):
        fetch("https://example.com/api")
    assert len(calls) == MAX_RATE_LIMIT_RETRIES + 1


def test_post_is_not_retried_on_rate_limit(monkeypatch):
    from diffyscan.utils.custom_exceptions import NodeError

    calls = []

    def post(*args, **kwargs):
        calls.append(args)
        return FailingResponse({}, "limited", 429)

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.post", post)
    with pytest.raises(NodeError):
        pull("https://node.example/rpc", "{}")
    assert len(calls) == 1


@pytest.mark.parametrize("reset_ms", [60000, 273095])
def test_blockscout_reset_recovers_after_window(monkeypatch, pacing_clock, reset_ms):
    responses = iter(
        [
            FailingResponse(
                {"bypass-429-option": "no_bypass", "x-ratelimit-reset": str(reset_ms)},
                "limited",
                429,
            ),
            DummyResponse(),
        ]
    )
    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda *args, **kwargs: next(responses)
    )
    fetch("https://blockscout.example/api")
    assert pacing_clock["sleeps"] == [pytest.approx(reset_ms / 1000)]


def test_github_reset_is_not_blockscout_milliseconds(monkeypatch, pacing_clock):
    responses = iter(
        [
            FailingResponse({"x-ratelimit-reset": "1790776800"}, "limited", 429),
            DummyResponse(),
        ]
    )
    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda *args, **kwargs: next(responses)
    )
    fetch("https://api.github.com/api")
    assert pacing_clock["sleeps"] == [pytest.approx(2 / 3)]


@pytest.mark.parametrize("value", ["1e9", "+120", "1_20", "120.5", "1e300"])
def test_retry_after_rejects_non_decimal_delay(value):
    from diffyscan.utils.http_client import _retry_after

    assert _retry_after(value) is None


def test_obsolete_http_date_uses_utc(monkeypatch):
    import os
    import time
    from datetime import datetime, timezone
    from diffyscan.utils.http_client import _retry_after

    previous = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", "America/New_York")
        time.tzset()
        epoch = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc).timestamp()
        monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.time.time", lambda: epoch)
        assert _retry_after("Wed Sep 30 14:02:00 2026") == 120
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


@pytest.mark.parametrize("value", ["3600", "9" * 400])
def test_excessive_cooldown_fails_without_sleep(monkeypatch, pacing_clock, value):
    from diffyscan.utils.custom_exceptions import ExplorerError

    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get",
        lambda *args, **kwargs: FailingResponse({"Retry-After": value}, "limited", 429),
    )
    with pytest.raises(ExplorerError, match="budget"):
        fetch("https://example.com/api")
    assert pacing_clock["sleeps"] == []


def test_wait_budget_is_cumulative(monkeypatch, pacing_clock):
    from diffyscan.utils.custom_exceptions import ExplorerError

    calls = []

    def get(*args, **kwargs):
        calls.append(args)
        return FailingResponse({"Retry-After": "200"}, "limited", 429)

    monkeypatch.setattr(f"{HTTP_CLIENT_MODULE}.requests.get", get)
    with pytest.raises(ExplorerError, match="budget"):
        fetch("https://example.com/api")
    assert len(calls) == 2
    assert pacing_clock["sleeps"] == [200]


def test_success_does_not_leave_backoff_for_next_request(monkeypatch, pacing_clock):
    responses = iter(
        [FailingResponse({}, "limited", 429), DummyResponse(), DummyResponse()]
    )
    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda *args, **kwargs: next(responses)
    )
    fetch("https://example.com/api")
    fetch("https://example.com/api")
    assert pacing_clock["sleeps"] == [pytest.approx(2 / 3), pytest.approx(1 / 3)]


@pytest.mark.parametrize(
    "status,headers",
    [
        (502, {}),
        (503, {"Retry-After": "2"}),
        (504, {}),
        (500, {"bypass-429-option": "no_bypass"}),
    ],
)
def test_transient_get_recovers(monkeypatch, pacing_clock, status, headers):
    responses = iter([FailingResponse(headers, "unavailable", status), DummyResponse()])
    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda *args, **kwargs: next(responses)
    )
    fetch("https://example.com/api")
    assert pacing_clock["sleeps"] == [pytest.approx(2 if status == 503 else 2 / 3)]


def test_cooldown_survives_exhausted_retry_budget(monkeypatch, pacing_clock):
    from diffyscan.utils.custom_exceptions import ExplorerError
    from diffyscan.utils.http_client import reserve_slot

    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get",
        lambda *args, **kwargs: FailingResponse({"Retry-After": "1"}, "limited", 429),
    )
    with pytest.raises(ExplorerError, match="6 attempts"):
        fetch("https://example.com/api")
    assert reserve_slot("https://example.com/api", now=pacing_clock["now"]) == 1


def test_excessive_header_does_not_poison_later_request(monkeypatch, pacing_clock):
    from diffyscan.utils.custom_exceptions import ExplorerError

    responses = iter(
        [
            FailingResponse({"Retry-After": "9999999999"}, "limited", 429),
            DummyResponse(),
        ]
    )
    monkeypatch.setattr(
        f"{HTTP_CLIENT_MODULE}.requests.get", lambda *args, **kwargs: next(responses)
    )
    with pytest.raises(ExplorerError, match="budget"):
        fetch("https://example.com/api")
    fetch("https://example.com/api")
    assert pacing_clock["sleeps"] == [pytest.approx(1 / 3)]
