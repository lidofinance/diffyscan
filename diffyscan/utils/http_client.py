from functools import wraps
import os
import time
from urllib.parse import urlsplit

import requests

from .. import __version__
from .common import mask_text
from .custom_exceptions import NodeError, ExplorerError
from .logger import logger

USER_AGENT_ENV_VAR = "DIFFYSCAN_USER_AGENT"
# Cloudflare in front of some Blockscout instances rejects non-browser
# User-Agents, so keep a browser-like prefix; the trailing token identifies
# diffyscan.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    f"diffyscan/{__version__}"
)


def get_user_agent() -> str:
    """Return the User-Agent for outgoing requests, overridable via env."""
    return os.getenv(USER_AGENT_ENV_VAR) or DEFAULT_USER_AGENT


def _same_origin_referer(url: str) -> str | None:
    """`https://host/` for a URL, or None when it has no host.

    The origin only, never the full URL. A Referer is the sort of header the other end logs, and
    explorer URLs carry API keys in their query string -- which is why this module already
    redacts them from error text.
    """
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


#: One queue per host: two explorers in one run have separate limits and separate queues.
_pace: dict[str, dict[str, float]] = {}
DEFAULT_INTERVAL_SECONDS = 1 / 3  # the free etherscan tier
MAX_INTERVAL_SECONDS = 60.0


#: Limits known before any host has refused anything, by host suffix, longest first.
KNOWN_LIMITS: tuple[tuple[str, int], ...] = (
    # measured 2026-09-17: the instance states X-RateLimit-Limit 10 on refusal
    ("blockscout.com", 10),
    ("api.etherscan.io", 180),
)


def _opening_interval(host: str) -> float:
    for suffix, per_minute in KNOWN_LIMITS:
        if host == suffix or host.endswith("." + suffix):
            return min(60.0 / per_minute, MAX_INTERVAL_SECONDS)
    return DEFAULT_INTERVAL_SECONDS


def _pace_for(url: str) -> dict[str, float]:
    host = (urlsplit(url).netloc or url).lower()
    return _pace.setdefault(host, {"interval": _opening_interval(host), "next_at": 0.0})


def reserve_slot(url: str, now: float | None = None) -> float:
    """How long this request waits, booking the slot for it."""
    now = time.monotonic() if now is None else now
    pace = _pace_for(url)
    slot = max(now, pace["next_at"])
    pace["next_at"] = slot + pace["interval"]
    return slot - now


def learn_rate_limit(url: str, headers=None, now: float | None = None) -> float:
    """Take a host's limit from its own refusal.

    `RateLimit-Limit` and `Retry-After` are what a server states when it turns a request away,
    and reading them beats measuring by trial. Without either the interval doubles.
    """
    now = time.monotonic() if now is None else now
    pace = _pace_for(url)
    per_minute = _number((headers or {}).get("RateLimit-Limit") or (headers or {}).get("X-RateLimit-Limit"))
    retry_after = _number((headers or {}).get("Retry-After"))
    if per_minute and per_minute > 0:
        pace["interval"] = min(60.0 / per_minute, MAX_INTERVAL_SECONDS)
    else:
        pace["interval"] = min(pace["interval"] * 2, MAX_INTERVAL_SECONDS)
    pace["next_at"] = max(pace["next_at"], now + (retry_after or pace["interval"]))
    return pace["interval"]


def reset_pacing() -> None:
    _pace.clear()


def _number(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _build_headers(headers: dict | None, url: str | None = None) -> dict:
    built = {"User-Agent": get_user_agent()}
    # A browser reading an explorer's API sends a Referer, and Cloudflare in front of some
    # Blockscout instances answers 403 without one, whatever the User-Agent says.
    referer = _same_origin_referer(url) if url else None
    if referer:
        built["Referer"] = referer
    return {**built, **(headers or {})}


def _redact_url(message: str, url: str) -> str:
    """Hide the request URL in error text: RPC paths and explorer queries carry API keys."""
    message = message.replace(url, "[redacted URL]")
    parsed = urlsplit(url)
    request_target = parsed.path or "/"
    if parsed.query:
        request_target += f"?{parsed.query}"
    # urllib3 connection errors include only the path and query.
    if request_target != "/":
        message = message.replace(request_target, "[redacted URL]")
    return message


def _handle_request_errors(error_class: type[BaseException]):
    """Decorator to handle HTTP request errors and convert them to custom exceptions."""

    def decorator(func):
        @wraps(func)
        def wrapper(url: str, *args, **kwargs) -> requests.Response:
            try:
                response: requests.Response = func(url, *args, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as exc:
                body = ""
                if exc.response is not None:
                    if exc.response.status_code == 429:
                        learn_rate_limit(url, exc.response.headers)
                    if exc.response.headers.get("cf-mitigated") == "challenge":
                        raise error_class(
                            _redact_url(f"HTTP error: {exc}", url)
                            + ". The host is behind a Cloudflare challenge that "
                            "rejected the request. A browser-like User-Agent and a "
                            "same-origin Referer are already sent; try another "
                            f"User-Agent via {USER_AGENT_ENV_VAR}, or reach the "
                            "contract through a different explorer for this chain"
                        ) from None
                    try:
                        body = f" Response: {exc.response.text}"
                    except Exception:
                        pass
                # `from None` keeps the unredacted requests exception out of tracebacks
                raise error_class(
                    _redact_url(f"HTTP error: {exc}{body}", url)
                ) from None
            except requests.exceptions.RequestException as exc:
                raise error_class(_redact_url(str(exc), url)) from None

        return wrapper

    return decorator


@_handle_request_errors(ExplorerError)
def fetch(url: str, headers: dict | None = None) -> requests.Response:
    """Fetch data from a URL with error handling."""
    logger.log(f"Fetch: {mask_text(url)}")
    delay = reserve_slot(url)
    if delay > 0:
        time.sleep(delay)
    return requests.get(url, headers=_build_headers(headers, url))


@_handle_request_errors(NodeError)
def pull(
    url: str, payload: str | None = None, headers: dict | None = None
) -> requests.Response:
    """Post data to a URL with error handling."""
    logger.log(f"Pull: {mask_text(url)}")
    return requests.post(url, data=payload, headers=_build_headers(headers))
