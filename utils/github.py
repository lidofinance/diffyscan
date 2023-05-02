import base64
import re
from utils.common import fetch, parse_repo_link
from utils.constants import CONTRACTS_DIR
from utils.logger import logger


def get_file_from_github(github_api_token, dependency_repo, filepath, dep_name):
    user_slash_repo, ref = parse_repo_link(dependency_repo)
    path_to_file = construct_filepath(filepath, dep_name)

    github_api_url = (
        f"https://api.github.com/repos/{user_slash_repo}/contents/{path_to_file}"
    )

    if ref:
        github_api_url += "?ref=" + ref

    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    )

    file_content = github_data.get("content")

    if not file_content:
        logger.error("No file content")

    return base64.b64decode(file_content).decode()


def construct_filepath(filepath, dep_name):
    # return the same thing if the file is in the local repo
    if is_local_file(filepath):
        assert not dep_name, "file is local but dep is present"
        return filepath

    dep_name_and_slash_length = len(dep_name) + 1
    filepath_without_dep_name = filepath[dep_name_and_slash_length:]

    return (
        filepath_without_dep_name
        if filepath_without_dep_name.startswith("contracts")
        else f"contracts/{filepath_without_dep_name}"
    )


def resolve_dep(filepath, config):
    # find the dependency that matches the filepath
    # e.g. "@openzeppelin/contracts-v4.4" in "@openzeppelin/contracts-v4.4/utils/structs/EnumerableSet.sol"
    dep_names = sorted(list(config["dependencies"].keys()), key=len, reverse=True)

    for dep_name in dep_names:
        if filepath.startswith(f"{dep_name}/"):
            return (config["dependencies"][dep_name], dep_name)

    return (None, None)


def is_local_file(filepath):
    return filepath.split("/")[0] == CONTRACTS_DIR
