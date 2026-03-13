import hashlib
import json
import os
from functools import wraps

import requests
import yaml

from urllib.parse import urlparse

from .allowed_diffs import validate_allowed_diffs_config
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
            config: Config = json.load(config_file)
            _validate_loaded_config(config, path)
            return config
    raise ValueError(f"Unsupported config file extension: {ext}")


def _load_yaml_config(config_file, path: str) -> Config:
    config = yaml.safe_load(config_file)
    if config is None:
        raise ValueError(f"{path}: YAML file is empty or contains only comments")
    if not isinstance(config, dict):
        raise ValueError(
            f"{path}: configuration root must be a mapping, got {type(config).__name__}"
        )
    _validate_yaml_hex_keys(config, path)
    _validate_bool_fields(config, path)
    validate_allowed_diffs_config(config, path)
    return config  # type: ignore[return-value]


def _validate_loaded_config(config: object, path: str) -> None:
    if not isinstance(config, dict):
        raise ValueError(
            f"{path}: configuration root must be a mapping, got {type(config).__name__}"
        )
    _validate_bool_fields(config, path)
    validate_allowed_diffs_config(config, path)


def _validate_bool_fields(config: dict, path: str) -> None:
    for field in ("source_comparison", "fail_on_bytecode_comparison_error"):
        value = config.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(
                f"{path}: {field} must be a boolean, got {type(value).__name__} ({value!r})"
            )


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
    if isinstance(bytecode, dict):
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

    allowed_diffs = config.get("allowed_diffs")
    if not isinstance(allowed_diffs, dict):
        return

    for section in ("bytecode", "source"):
        entries_by_address = allowed_diffs.get(section)
        _validate_yaml_address_keys(
            entries_by_address,
            path,
            f"allowed_diffs.{section}",
        )
        if not isinstance(entries_by_address, dict):
            continue

        if section != "bytecode":
            continue

        for address, entries in entries_by_address.items():
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    continue
                if "constructor_calldata" in entry:
                    _raise_if_yaml_int(
                        entry["constructor_calldata"],
                        lambda parsed_value: (
                            f"{path}: allowed_diffs.bytecode.{address}[{index}].constructor_calldata "
                            f"was parsed as integer ({parsed_value:#x}). "
                            f"Quote it: {_quote_hex(parsed_value)}"
                        ),
                    )
                immutables = entry.get("immutables")
                if not isinstance(immutables, list):
                    continue
                for immutable_index, immutable in enumerate(immutables, start=1):
                    if not isinstance(immutable, dict):
                        continue
                    _raise_if_yaml_int(
                        immutable.get("value"),
                        lambda parsed_value: (
                            f"{path}: allowed_diffs.bytecode.{address}[{index}].immutables[{immutable_index}].value "
                            f"was parsed as integer ({parsed_value:#x}). "
                            f"Quote it: {_quote_hex(parsed_value)}"
                        ),
                    )


def _handle_request_errors(error_class: type[BaseException]):
    """Decorator to handle HTTP request errors and convert them to custom exceptions."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs) -> requests.Response:
            try:
                response: requests.Response = func(*args, **kwargs)
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


def _serialize_cache_value(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _build_cache_entry(value, metadata: dict | None = None) -> dict:
    payload = {
        "version": 1,
        "value": value,
        "sha256": hashlib.sha256(_serialize_cache_value(value).encode()).hexdigest(),
    }
    if metadata is not None:
        payload["metadata"] = metadata
    return payload


def _validate_cache_entry(
    cached_value,
    expected_metadata: dict | None,
    cache_kind: str,
    display_name: str,
):
    if not isinstance(cached_value, dict) or cached_value.get("version") != 1:
        logger.warn(f"Ignoring legacy or malformed {cache_kind} cache: {display_name}")
        return None

    if (
        expected_metadata is not None
        and cached_value.get("metadata") != expected_metadata
    ):
        logger.warn(
            f"Ignoring {cache_kind} cache with mismatched metadata: {display_name}"
        )
        return None

    value = cached_value.get("value")
    actual_sha256 = hashlib.sha256(_serialize_cache_value(value).encode()).hexdigest()
    if actual_sha256 != cached_value.get("sha256"):
        logger.warn(f"Ignoring tampered {cache_kind} cache: {display_name}")
        return None

    return value


def load_cache(
    cache_path: str,
    cache_kind: str,
    display_name: str,
    expected_metadata: dict | None = None,
):
    if not os.path.exists(cache_path):
        return None

    try:
        logger.info(f"Loading {cache_kind} from cache: {display_name}")
        with open(cache_path, "r", encoding="utf-8") as cache_file:
            cached_value = json.load(cache_file)
        return _validate_cache_entry(
            cached_value,
            expected_metadata,
            cache_kind,
            display_name,
        )
    except Exception as exc:
        logger.warn(f"Failed to load {cache_kind} from cache: {exc}")
        return None


def save_cache(
    cache_path: str,
    cache_kind: str,
    display_name: str,
    value,
    metadata: dict | None = None,
) -> None:
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            json.dump(
                _build_cache_entry(value, metadata),
                cache_file,
                indent=2,
                sort_keys=True,
            )
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
    logger.log(f"Pull: {mask_text(url)}")
    return requests.post(url, data=payload, headers=headers)


def mask_text(text: str, show_start: int = 3, show_end: int = 3) -> str:
    """Mask a text string, showing only the first and last few characters."""
    hidden = len(text) - show_start - show_end
    return text[:show_start] + "*" * max(hidden, 0) + text[len(text) - show_end :]


def parse_repo_link(repo_link: str) -> str:
    """Extract user/repo from a GitHub repository URL."""
    path = urlparse(repo_link).path
    return path.split("tree")[0].strip("/")
