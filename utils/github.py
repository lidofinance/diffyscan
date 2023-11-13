import base64
from utils.common import fetch, parse_repo_link
from utils.logger import logger


def get_file_from_github(github_api_token, dependency_repo, path_to_file, dep_name):
    path_to_file = path_to_file_without_dependency(path_to_file, dep_name)

    user_slash_repo = parse_repo_link(dependency_repo["url"])

    github_api_url = f"https://api.github.com/repos/{user_slash_repo}/contents/{dependency_repo['relative_root']}/{path_to_file}"

    github_api_url += "?ref=" + dependency_repo["commit"]

    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    )

    file_content = github_data.get("content")

    if not file_content:
        logger.error("No file content")
        return None

    return base64.b64decode(file_content).decode()


def path_to_file_without_dependency(path_to_file, dep_name):
    # exclude dependency prefix from path to file
    # "@aragon/something/lib/my.sol" => "lib/my.sol"
    if not dep_name:
        return path_to_file

    dep_name_and_slash_length = len(dep_name) + 1
    path_to_file_without_dependency = path_to_file[dep_name_and_slash_length:]

    return path_to_file_without_dependency


def resolve_dep(path_to_file, config):
    # find the dependency that matches the path_to_file
    # e.g. "@openzeppelin/contracts-v4.4" in "@openzeppelin/contracts-v4.4/utils/structs/EnumerableSet.sol"
    dep_names = sorted(list(config["dependencies"].keys()), key=len, reverse=True)

    for dep_name in dep_names:
        if path_to_file.startswith(f"{dep_name}/"):
            return (config["dependencies"][dep_name], dep_name)

    return (None, None)
