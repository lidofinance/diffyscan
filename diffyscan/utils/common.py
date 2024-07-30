import json
import os
import sys
from urllib.parse import urlparse

import requests

from .logger import logger
from .types import Config

def load_config(path: str) -> Config:
    with open(path, mode="r") as config_file:
        return json.load(config_file)

def handle_response(response, url):
    if response.status_code == 404:
        return None

    if not response.ok and response.status_code != 200:
        logger.error("Request failed", url)
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)

    return response

def fetch(url, headers={}):
    logger.log(f"Fetch: {url}")
    response = requests.get(url, headers=headers)

    return handle_response(response, url)

def pull(url, payload={}):
    logger.log(f"Pull: {url}")
    response = requests.post(url, data=payload)

    return handle_response(response, url)
  
def mask_text(text, mask_start=3, mask_end=3):
    text_length = len(text)
    mask = "*" * (text_length - mask_start - mask_end)
    return text[:mask_start] + mask + text[text_length - mask_end :]


def parse_repo_link(repo_link):
    parse_result = urlparse(repo_link)
    repo_location = [item.strip("/") for item in parse_result[2].split("tree")]
    user_slash_repo = repo_location[0]
    return user_slash_repo

def get_solc_native_platform_from_os():
    platform_name = sys.platform
    if platform_name == 'linux':
        return 'linux-amd64'
    elif platform_name == 'darwin':
        return 'macosx-amd64'
    else:
        raise ValueError(f'Unsupported platform {platform_name}')