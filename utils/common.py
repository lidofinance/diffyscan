import difflib
import json
import os
import sys
from urllib.parse import urlparse

import requests

from utils.constants import CONFIG_PATH
from utils.logger import logger
from utils.types import Config


def load_env(variable_name, masked=False):
    value = os.getenv(variable_name)

    if not value:
        logger.error("Env not found", variable_name)
        sys.exit()

    printable_value = mask_text(value) if masked else value

    logger.okay(f"{variable_name}", printable_value)
    return value


def load_config() -> Config:
    config_path = get_config_path()

    with open(config_path, mode="r") as config_file:
        return json.load(config_file)


def add_dependency_to_config(dependency):
    config_path = get_config_path()

    with open(config_path, mode="r") as config_file:
        config = json.load(config_file)

    with open(config_path, mode="w") as config_file:
        config["dependencies"][dependency] = ""
        config_file.write(json.dumps(config))


def get_config_path() -> str:
    return CONFIG_PATH


def fetch(url, headers={}):
    logger.log(f"fetch: {url}")
    response = requests.get(url, headers=headers)

    if not response.ok and response.status_code != 200:
        logger.error(f"Request failed", url)
        sys.exit()

    return response.json()


def mask_text(text, mask_start=3, mask_end=3):
    text_length = len(text)
    mask = "*" * (text_length - mask_start - mask_end)
    return text[:mask_start] + mask + text[text_length - mask_end :]


def parse_repo_link(repo_link):
    parse_result = urlparse(repo_link)
    repo_location = [item.strip("/") for item in parse_result[2].split("tree")]
    user_slash_repo = repo_location[0]
    ref = repo_location[1] if len(repo_location) > 1 else None
    return (user_slash_repo, ref)
