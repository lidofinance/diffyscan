import json
import os
import sys
import subprocess
import tempfile
import requests
import uuid

from urllib.parse import urlparse

from .logger import logger
from .custom_types import Config
from .custom_exceptions import NodeError, ExplorerError


def load_env(
    variable_name: str, required: bool = True, masked: bool = False
) -> str | None:
    """
    Load an environment variable with optional masking and requirement checking.

    Args:
        variable_name: Name of the environment variable
        required: If True, raise ValueError when variable is not set
        masked: If True, mask the value when logging

    Returns:
        The environment variable value or None if not set and not required

    Raises:
        ValueError: If required=True and variable is not set
    """
    value = os.getenv(variable_name, default=None)

    if required and not value:
        error_msg = f"Required environment variable not found: {variable_name}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    printable_value = mask_text(value) if masked and value is not None else str(value)

    if printable_value:
        logger.okay(f"{variable_name}", printable_value)
    else:
        logger.info(f"{variable_name} var is not set")

    return value


def load_config(path: str) -> Config:
    with open(path, mode="r") as config_file:
        return json.load(config_file)


def _handle_request_errors(error_class: type[BaseException]):
    """Decorator to handle common HTTP request errors and convert them to custom exceptions."""

    def decorator(func):
        def wrapper(*args, **kwargs) -> requests.Response:
            try:
                response = func(*args, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as http_err:
                # Include response body for better debugging
                response_body = ""
                if http_err.response is not None:
                    try:
                        response_body = f" Response: {http_err.response.text}"
                    except Exception:
                        pass
                raise error_class(f"HTTP error occurred: {http_err}{response_body}")
            except requests.exceptions.ConnectionError as conn_err:
                raise error_class(f"Connection error occurred: {conn_err}")
            except requests.exceptions.Timeout as timeout_err:
                raise error_class(f"Timeout error occurred: {timeout_err}")
            except requests.exceptions.RequestException as req_err:
                raise error_class(f"Request exception occurred: {req_err}")

        return wrapper

    return decorator


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


def mask_text(text: str, mask_start: int = 3, mask_end: int = 3) -> str:
    """
    Mask a text string, showing only the beginning and end.

    Args:
        text: The text to mask
        mask_start: Number of characters to show at the start
        mask_end: Number of characters to show at the end

    Returns:
        The masked text
    """
    text_length = len(text)
    mask = "*" * (text_length - mask_start - mask_end)
    return text[:mask_start] + mask + text[text_length - mask_end :]


def parse_repo_link(repo_link: str) -> str:
    """
    Parse a GitHub repository link to extract user/repo.

    Args:
        repo_link: The full GitHub repository URL

    Returns:
        The user/repo part of the URL
    """
    parse_result = urlparse(repo_link)
    repo_location = [item.strip("/") for item in parse_result[2].split("tree")]
    user_slash_repo = repo_location[0]
    return user_slash_repo


def prettify_solidity(solidity_contract_content: str) -> str:
    """
    Prettify Solidity code using prettier.

    Args:
        solidity_contract_content: The Solidity source code to prettify

    Returns:
        The prettified Solidity source code

    Raises:
        RuntimeError: If prettier fails or times out
    """
    # Use tempfile.NamedTemporaryFile for secure temp file handling
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sol", delete=False, encoding="utf-8"
    ) as fp:
        github_file_name = fp.name
        fp.write(solidity_contract_content)

    try:
        subprocess.run(
            [
                "npx",
                "prettier",
                "--plugin=prettier-plugin-solidity",
                "--write",
                github_file_name,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=30,
        )

        with open(github_file_name, "r", encoding="utf-8") as fp:
            return fp.read()
    except subprocess.CalledProcessError as e:
        error_msg = f"Prettier/npx subprocess failed: {e.stderr.decode() if e.stderr else str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    except subprocess.TimeoutExpired as e:
        error_msg = "Prettier/npx subprocess timed out after 30 seconds"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    finally:
        # Always clean up the temp file
        try:
            os.unlink(github_file_name)
        except OSError:
            pass
