from functools import wraps
import os
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


def _build_headers(headers: dict | None) -> dict:
    return {"User-Agent": get_user_agent(), **(headers or {})}


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
                            f"rejected the request; try overriding the User-Agent "
                            f"via {USER_AGENT_ENV_VAR}"
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
    return requests.get(url, headers=_build_headers(headers))


@_handle_request_errors(NodeError)
def pull(
    url: str, payload: str | None = None, headers: dict | None = None
) -> requests.Response:
    """Post data to a URL with error handling."""
    logger.log(f"Pull: {mask_text(url)}")
    return requests.post(url, data=payload, headers=_build_headers(headers))
