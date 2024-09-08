import json
import os
import sys
import subprocess
import tempfile
import requests

from urllib.parse import urlparse

from .logger import logger
from .custom_types import Config
from .custom_exceptions import NodeError


def load_env(variable_name, required=True, masked=False):
    value = os.getenv(variable_name, default=None)

    if required and not value:
        logger.error("Env not found", variable_name)
        sys.exit(1)

    printable_value = mask_text(value) if masked and value is not None else str(value)

    if printable_value:
        logger.okay(f"{variable_name}", printable_value)
    else:
        logger.info(f"{variable_name} var is not set")

    return value


def load_config(path: str) -> Config:
    with open(path, mode="r") as config_file:
        return json.load(config_file)


def fetch(url, headers=None):
    logger.log(f"Fetch: {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        raise NodeError(f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise NodeError(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise NodeError(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise NodeError(f"Request exception occurred: {req_err}")

    return response


def pull(url, payload=None, headers=None):
    logger.log(f"Pull: {url}")
    try:
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        raise NodeError(f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise NodeError(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise NodeError(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise NodeError(f"Request exception occurred: {req_err}")

    return response


def mask_text(text, mask_start=3, mask_end=3):
    text_length = len(text)
    mask = "*" * (text_length - mask_start - mask_end)
    return text[:mask_start] + mask + text[text_length - mask_end :]


def parse_repo_link(repo_link):
    parse_result = urlparse(repo_link)
    repo_location = [item.strip("/") for item in parse_result[2].split("tree")]
    user_slash_repo = repo_location[0]
    return user_slash_repo


def prettify_solidity(solidity_contract_content: str):
    github_file_name = os.path.join(
        tempfile.gettempdir(), "9B91E897-EA51-4FCC-8DAF-FCFF135A6963.sol"
    )
    with open(github_file_name, "w") as fp:
        fp.write(solidity_contract_content)

    prettier_return_code = subprocess.call(
        [
            "npx",
            "prettier",
            "--plugin=prettier-plugin-solidity",
            "--write",
            github_file_name,
        ],
        stdout=subprocess.DEVNULL,
    )
    if prettier_return_code != 0:
        logger.error("Prettier/npx subprocess failed (see the error above)")
        sys.exit()
    with open(github_file_name, "r") as fp:
        return fp.read()
