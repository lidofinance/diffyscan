import base64
import re
from utils.common import fetch, parse_repo_link
from utils.constants import CONTRACTS_DIR
from utils.logger import logger


def get_file_from_github(github_api_token, dependency_repo, filepath):
    user_slash_repo, ref = parse_repo_link(dependency_repo)
    path_to_file = construct_filepath(filepath)

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


def construct_filepath(filepath):
    # return the same thing if the file is in the local repo
    if is_local_file(filepath):
        return filepath

    # extract "contracts..." substring (preceded by "/") from filepath
    # e.g. "@openzeppelin/contracts-v4.4/utils/structs/EnumerableSet.sol" => "contracts-v4.4/utils/structs/EnumerableSet.sol"
    regex = re.compile("(?<=\/)contracts.*")
    match = regex.search(filepath).group()

    # remove the version from path
    # e.g. "contracts-v4.4/utils/structs/EnumerableSet.sol" => "contracts/utils/structs/EnumerableSet.sol"
    return re.sub("contracts.*?\/", "contracts/", match)


def resolve_dep(filepath, config):
    # find the dependency that matches the filepath
    # e.g. "@openzeppelin/contracts-v4.4" in "@openzeppelin/contracts-v4.4/utils/structs/EnumerableSet.sol"
    dep_names = config["dependencies"].keys()
    match = next((dn for dn in iter(dep_names) if re.search(dn + "/", filepath)), None)

    if match:
        return config["dependencies"][match]


def is_local_file(filepath):
    return filepath.split("/")[0] == CONTRACTS_DIR
