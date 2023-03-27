import sys
import requests
import json
import base64
import time
import difflib
import os
import re
from urllib.parse import urlparse

import logger 




def main():
    logger.greet()
    logger.divider()

    logger.info("Loading environment variables...")
    github_token = load_env("GITHUB_TOKEN", masked=True)
    etherscan_token = load_env("ETHERSCAN_TOKEN", masked=True)
    etherscan_network = load_env("ETHERSCAN_NETWORK", "mainnet")
    contract_address = load_env("CONTRACT_ADDRESS")
    repo_link = load_env("REPO_LINK")
    logger.okay("Environment variables loaded!")
    logger.divider()

    logger.info("Fetching source code from Etherscan...")
    contract_data = fetch_contract_data_from_etherscan(etherscan_token, etherscan_network, contract_address)
    logger.okay("Contract found", contract_data["ContractName"])
    source_code_files = json.loads(contract_data["SourceCode"][1:-1])["sources"].items()
    files_count = len(source_code_files)
    logger.info(f"Files bundled", files_count)

    identical_files_count = 0
    not_found_on_github_count = 0

    dependencies = {}

    for index, (filepath, source) in enumerate(source_code_files):
        logger.divider()
        # parsing github link to get user repo and ref (commit or branch)
        (user_slash_repo, ref) = parse_repo_link(repo_link)


        split_filepath = filepath.split("/")
        filename = split_filepath[-1]
        logger.info(f"File {index + 1}", filename)
        logger.info("Path", filepath)

        github_file_data = fetch_file_from_github(github_token, user_slash_repo, ref, filepath)

        if github_file_data.get("message") == "Not Found":
            logger.warn("File not found in the original repo!")
            logger.info("Looking through dependencies...")
            dependency_name = split_filepath[0]
            repo_location = dependencies.get(dependency_name)
            if repo_location:
                logger.okay("Found a dependency with similar path")
                (user_slash_repo, ref) = repo_location
                path_to_file = re.search("contracts.*", filepath).group(0)
                github_file_data = fetch_file_from_github(github_token, user_slash_repo, ref, path_to_file)
                if github_file_data.get("message") == "Not Found":
                    logger.warn(f"File not found in the {dependency_name} repo! Skipping")
            else:
                logger.warn("File not found in the dependencies list!")
                dependency_repo = logger.prompt(f"Provide a link to {dependency_name} repo")

                if dependency_repo:
                    repo_location = parse_repo_link(dependency_repo)
                    dependencies[dependency_name] = repo_location
                    (user_slash_repo, ref) = repo_location

                    path_to_file = re.search("contracts.*", filepath).group(0)
                    github_file_data = fetch_file_from_github(github_token, user_slash_repo, ref, path_to_file)
                    if github_file_data.get("message") == "Not Found":
                        logger.warn(f"File not found in the {dependency_name} repo! Skipping")
                        continue
                else:
                    logger.warn("Invalid link. Skipping this file")
                    not_found_on_github_count += 1
                    continue

        logger.okay(f"File found in {user_slash_repo}!")

        github_file = base64.b64decode(github_file_data["content"]).decode().splitlines()
        etherscan_file = source["content"].splitlines()

        diffs = difflib.unified_diff(github_file, etherscan_file)

        # if diffs are present, output to diff view html
        if len(list(diffs)):
            diff_html = difflib.HtmlDiff().make_file(github_file, etherscan_file)
            diff_report_filename = f"diffs/{filename}.html"
            os.makedirs(os.path.dirname(diff_report_filename), exist_ok=True)
            with open(diff_report_filename, "w") as f:
                f.write(diff_html)
            logger.warn(f"Diffs in {filename}! Report", diff_report_filename)
        else:
            identical_files_count += 1
            logger.okay(f"No diffs in {filename}!")

        time.sleep(1)

    
    # print final stats
    logger.divider()
    print(f"🧬 Identical files: {identical_files_count} / {files_count}")
    print(f"🔭 Code not found: {not_found_on_github_count} / {files_count}")


def load_env(variable_name, default_value=None, masked=False):
    value = os.getenv(variable_name)
    if not value:
        if default_value:
            logger.warn(f"{variable_name} not found! Using default", default_value)
            value = default_value
        else:
            logger.error(f"{variable_name} not found! Quitting...")
            sys.exit()

    printable_value = mask_text(value) if masked else value

    logger.okay(f"{variable_name}", printable_value)
    return value


def parse_repo_link(repo_link):
    parse_result = urlparse(repo_link)
    repo_location = [item.strip("/") for item in parse_result[2].split("tree")]
    user_slash_repo = repo_location[0]
    ref = repo_location[1] if len(repo_location) > 1 else None
    return (user_slash_repo, ref)


def mask_text(text, mask_start=3, mask_end=3):
    text_length = len(text)
    mask = "*" * (text_length - mask_start - mask_end)
    return text[:mask_start] + mask + text[text_length-mask_end:]


def fetch(url, headers={}):
    response = requests.get(url, headers=headers)

    hostname = urlparse(url)[1]
    logger.info("GET", hostname)
    if response.ok and response.status_code != 200:
        logger.error(f"Failed")
        sys.exit()

    return  response.json()


def fetch_contract_data_from_etherscan(token, network, contract_address):
    etherscan_subdomain = "-" + network if network else ""
    etherscan_link = f"https://api{etherscan_subdomain}.etherscan.io/api?module=contract&action=getsourcecode&address={contract_address}&apikey={token}"
    data = fetch(etherscan_link)
    if data["message"] == "NOTOK":
        logger.error("Failed", data["result"])
        sys.exit()

    return data["result"][0]


def fetch_file_from_github(github_token, user_slash_repo, ref, filepath):
    github_api_url = f"https://api.github.com/repos/{user_slash_repo}/contents/{filepath}" + ("?ref=" + ref if ref else "")
    print(github_api_url)
    return fetch(github_api_url, headers={"Authorization": f"token {github_token}"})


if __name__ == "__main__":
    main()

