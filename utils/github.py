import base64
from utils.common import fetch, parse_repo_link
from utils.logger import logger

def _get_file_from_github(
        github_api_token,
        url,
        path_to_file,
        repo_prefix,
        commit
    ):

    user_slash_repo = parse_repo_link(url)

    github_api_url = (
        f"https://api.github.com/repos/{user_slash_repo}/contents/{repo_prefix}/{path_to_file}"
    )

    github_api_url += "?ref=" + commit

    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    )

    file_content = github_data.get("content")

    if not file_content:
        logger.error("No file content")

    return base64.b64decode(file_content).decode()

def get_file_from_github(github_api_token, dependency_repo, filepath, dep_name):
    path_to_file = construct_filepath(filepath, dep_name)

    if dependency_repo.get("0"):
        for k in range(len(dependency_repo.keys())):
            k_str = str(k)
            start_string = dependency_repo[k_str].get("startswith")
            if not start_string:
                logger.error("dependencies with multiple repos must contain 'startswith' key")
            if not path_to_file.startswith(start_string):
                continue
            path_to_file = path_to_file[len(start_string):]

            return _get_file_from_github(
                github_api_token,
                dependency_repo[k_str]["url"],
                path_to_file,
                dependency_repo[k_str]['repo_prefix'],
                dependency_repo[k_str]["commit"]
            )

        logger.error("unable to find a proper dependency url")
    else:
        return _get_file_from_github(
            github_api_token,
            dependency_repo["url"],
            path_to_file,
            dependency_repo['repo_prefix'],
            dependency_repo["commit"]
        )

def construct_filepath(filepath, dep_name):
    # return the same thing if the file is in the local repo
    if dep_name is None:
        return filepath

    dep_name_and_slash_length = len(dep_name) + 1
    filepath_without_dep_name = filepath[dep_name_and_slash_length:]

    return filepath_without_dep_name


def resolve_dep(filepath, config):
    # find the dependency that matches the filepath
    # e.g. "@openzeppelin/contracts-v4.4" in "@openzeppelin/contracts-v4.4/utils/structs/EnumerableSet.sol"
    dep_names = sorted(list(config["dependencies"].keys()), key=len, reverse=True)

    for dep_name in dep_names:
        if filepath.startswith(f"{dep_name}/"):
            return (config["dependencies"][dep_name], dep_name)

    return (None, None)
