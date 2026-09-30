from functools import wraps
from email.utils import parsedate_to_datetime
from datetime import timezone
import re
import math
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
    return f"{parsed.scheme}://{parsed.netloc.rsplit('@', 1)[-1]}/"


#: One queue per host: two explorers in one run have separate limits and separate queues.
_pace: dict[str, dict[str, float]] = {}
DEFAULT_INTERVAL_SECONDS = 1 / 3  # the free etherscan tier
MAX_INTERVAL_SECONDS = 60.0


MAX_RATE_LIMIT_RETRIES = 5
MAX_RETRY_WAIT_SECONDS = 300.0


def _pace_for(url: str) -> dict[str, float]:
    parsed = urlsplit(url)
    host = (parsed.netloc.rsplit("@", 1)[-1] or url).lower()
    return _pace.setdefault(host, {"next_at": 0.0})


def reserve_slot(url: str, now: float | None = None) -> float:
    """How long this request waits, booking the slot for it."""
    now = time.monotonic() if now is None else now
    pace = _pace_for(url)
    slot = max(now, pace["next_at"])
    pace["next_at"] = slot + DEFAULT_INTERVAL_SECONDS
    return slot - now


def learn_rate_limit(
    url: str,
    headers=None,
    now: float | None = None,
    backoff: float = 2 / 3,
    status: int = 429,
) -> float:
    """Share a cooldown, without persisting one request's exponential backoff."""
    now = time.monotonic() if now is None else now
    headers = requests.structures.CaseInsensitiveDict(headers or {})
    delay = _retry_after(headers.get("Retry-After"))
    # Blockscout sends x-ratelimit-reset on every response; only a 429 makes it a cooldown.
    if delay is None and status == 429 and "bypass-429-option" in headers:
        reset = headers.get("x-ratelimit-reset", "")
        if re.fullmatch(r"[0-9]+", reset):
            delay = float(reset) / 1000
    wait = backoff if delay is None else delay
    if not math.isfinite(wait) or wait > MAX_RETRY_WAIT_SECONDS:
        raise ExplorerError(
            f"HTTP cooldown {wait:g}s exceeds the {MAX_RETRY_WAIT_SECONDS:g}s wait budget"
        )
    pace = _pace_for(url)
    pace["next_at"] = max(pace["next_at"], now + wait)
    return wait


def reset_pacing() -> None:
    _pace.clear()


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]+", value):
        return float(value)
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, date.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
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
    waited = 0.0
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        delay = reserve_slot(url)
        if not math.isfinite(delay) or waited + delay > MAX_RETRY_WAIT_SECONDS:
            raise ExplorerError(
                f"HTTP retry needs {delay:g}s more after {waited:g}s; wait budget is {MAX_RETRY_WAIT_SECONDS:g}s"
            )
        if delay > 0:
            time.sleep(delay)
            waited += delay
        response = requests.get(url, headers=_build_headers(headers, url))
        transient = response.status_code in (429, 502, 503, 504) or (
            response.status_code == 500 and "bypass-429-option" in response.headers
        )
        if not transient or response.headers.get("cf-mitigated") == "challenge":
            return response
        if attempt == MAX_RATE_LIMIT_RETRIES:
            learn_rate_limit(
                url, response.headers, backoff=0, status=response.status_code
            )
            raise ExplorerError(
                f"HTTP {response.status_code} after {attempt + 1} attempts and {waited:g}s waiting"
            )
        backoff = min(
            DEFAULT_INTERVAL_SECONDS * 2 ** (attempt + 1), MAX_INTERVAL_SECONDS
        )
        wait = learn_rate_limit(
            url, response.headers, backoff=backoff, status=response.status_code
        )
        logger.warn(
            f"HTTP {response.status_code}; retry {attempt + 1}/{MAX_RATE_LIMIT_RETRIES} in {wait:g}s",
            mask_text(url),
        )

    raise AssertionError("unreachable")


@_handle_request_errors(NodeError)
def pull(
    url: str, payload: str | None = None, headers: dict | None = None
) -> requests.Response:
    """Post data to a URL with error handling."""
    logger.log(f"Pull: {mask_text(url)}")
    return requests.post(url, data=payload, headers=_build_headers(headers))
