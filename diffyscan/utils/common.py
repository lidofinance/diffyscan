import hashlib
import json
import os
from functools import wraps

import requests
import yaml

from urllib.parse import urlparse

from .logger import logger
from .custom_types import Config
from .custom_exceptions import NodeError, ExplorerError


def load_env(
    variable_name: str, required: bool = True, masked: bool = False
) -> str | None:
    """Load an environment variable with optional masking and requirement checking."""
    value = os.getenv(variable_name)

    if required and not value:
        msg = f"Required environment variable not found: {variable_name}"
        logger.error(msg)
        raise ValueError(msg)

    if value:
        display = mask_text(value) if masked else value
        logger.okay(variable_name, display)
    else:
        logger.info(f"{variable_name} var is not set")

    return value


def load_config(path: str) -> Config:
    ext = os.path.splitext(path)[1].lower()
    with open(path, mode="r", encoding="utf-8") as config_file:
        if ext in (".yaml", ".yml"):
            return _load_yaml_config(config_file, path)
        if ext == ".json":
            return json.load(config_file)
    raise ValueError(f"Unsupported config file extension: {ext}")


def _load_yaml_config(config_file, path: str) -> Config:
    config = yaml.safe_load(config_file)
    if config is None:
        raise ValueError(f"{path}: YAML file is empty or contains only comments")
    if not isinstance(config, dict):
        raise ValueError(
            f"{path}: YAML root must be a mapping, got {type(config).__name__}"
        )
    _validate_yaml_hex_keys(config, path)
    return config


def _quote_hex(value: int) -> str:
    return f'"{value:#0{42}x}"'


def _raise_if_yaml_int(value: object, message_builder) -> None:
    if isinstance(value, int):
        raise ValueError(message_builder(value))


def _validate_yaml_address_keys(mapping: dict | None, path: str, section: str) -> None:
    if not isinstance(mapping, dict):
        return

    for key in mapping:
        _raise_if_yaml_int(
            key,
            lambda parsed_key: (
                f"{path}: {section} address was parsed as integer ({parsed_key:#x}). "
                f"Quote it: {_quote_hex(parsed_key)}"
            ),
        )


def _validate_yaml_hex_keys(config: dict, path: str) -> None:
    """Check that YAML didn't coerce hex addresses to integers."""
    contracts = config.get("contracts")
    if isinstance(contracts, dict):
        for key, value in contracts.items():
            _raise_if_yaml_int(
                key,
                lambda parsed_key: (
                    f"{path}: contract address was parsed as integer ({parsed_key:#x}). "
                    f"Quote it: {_quote_hex(parsed_key)}"
                ),
            )
            _raise_if_yaml_int(
                value,
                lambda parsed_value: (
                    f"{path}: contract name for {key} was parsed as integer ({parsed_value}). "
                    "Quote it in the YAML file."
                ),
            )

    bytecode = config.get("bytecode_comparison")
    if not isinstance(bytecode, dict):
        return

    for section in ("constructor_args", "constructor_calldata"):
        _validate_yaml_address_keys(
            bytecode.get(section),
            path,
            f"bytecode_comparison.{section}",
        )

    libraries = bytecode.get("libraries")
    if isinstance(libraries, dict):
        for key, libs in libraries.items():
            if isinstance(libs, dict):
                for lib_name, lib_addr in libs.items():
                    _raise_if_yaml_int(
                        lib_addr,
                        lambda parsed_addr: (
                            f"{path}: bytecode_comparison.libraries.{key}.{lib_name} "
                            f"was parsed as integer ({parsed_addr:#x}). "
                            f"Quote it: {_quote_hex(parsed_addr)}"
                        ),
                    )


def _handle_request_errors(error_class: type[BaseException]):
    """Decorator to handle HTTP request errors and convert them to custom exceptions."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs) -> requests.Response:
            try:
                response = func(*args, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as exc:
                body = ""
                if exc.response is not None:
                    try:
                        body = f" Response: {exc.response.text}"
                    except Exception:
                        pass
                raise error_class(f"HTTP error: {exc}{body}")
            except requests.exceptions.RequestException as exc:
                raise error_class(str(exc))

        return wrapper

    return decorator


def build_hashed_cache_key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def load_cache(
    cache_path: str,
    cache_kind: str,
    display_name: str,
    loader=None,
):
    loader = loader or (lambda cache_file: cache_file.read())

    if not os.path.exists(cache_path):
        return None

    try:
        logger.info(f"Loading {cache_kind} from cache: {display_name}")
        with open(cache_path, "r", encoding="utf-8") as cache_file:
            return loader(cache_file)
    except Exception as exc:
        logger.warn(f"Failed to load {cache_kind} from cache: {exc}")
        return None


def save_cache(
    cache_path: str,
    cache_kind: str,
    display_name: str,
    value,
    writer=None,
) -> None:
    writer = writer or (lambda cache_file, cached_value: cache_file.write(cached_value))

    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            writer(cache_file, value)
        logger.info(f"Saved {cache_kind} to cache: {display_name}")
    except Exception as exc:
        logger.warn(f"Failed to save {cache_kind} to cache: {exc}")


@_handle_request_errors(ExplorerError)
def fetch(url: str, headers: dict | None = None) -> requests.Response:
    """Fetch data from a URL with error handling."""
    logger.log(f"Fetch: {mask_text(url)}")
    return requests.get(url, headers=headers)


@_handle_request_errors(NodeError)
def pull(
    url: str, payload: str | None = None, headers: dict | None = None
) -> requests.Response:
    """Post data to a URL with error handling."""
    logger.log(f"Pull: {url}")
    return requests.post(url, data=payload, headers=headers)


def mask_text(text: str, show_start: int = 3, show_end: int = 3) -> str:
    """Mask a text string, showing only the first and last few characters."""
    hidden = len(text) - show_start - show_end
    return text[:show_start] + "*" * max(hidden, 0) + text[len(text) - show_end :]


def parse_repo_link(repo_link: str) -> str:
    """Extract user/repo from a GitHub repository URL."""
    path = urlparse(repo_link).path
    return path.split("tree")[0].strip("/")
