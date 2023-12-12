import base64
from utils.common import fetch, parse_repo_link
from utils.logger import logger

def get_file_from_github(github_api_token, dependency_repo, path_to_file, dep_name):
    path_to_file = path_to_file_without_dependency(path_to_file, dep_name)

    user_slash_repo = parse_repo_link(dependency_repo['url'])

    github_api_url = (
        f"https://api.github.com/repos/{user_slash_repo}/contents/{dependency_repo['relative_root']}/{path_to_file}"
    )

    github_api_url += "?ref=" + dependency_repo['commit']

    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    )

    file_content = github_data.get("content")

    if not file_content:
        logger.error("No file content")

    return base64.b64decode(file_content).decode()

def get_file_from_github_recursive(github_api_token, dependency_repo, path_to_file, dep_name):
    path_to_file = path_to_file_without_dependency(path_to_file, dep_name)
    user_slash_repo = parse_repo_link(dependency_repo['url'])
    
    direct_file_content = _get_direct_file(github_api_token, user_slash_repo, dependency_repo['relative_root'], path_to_file, dependency_repo['commit'])
    if direct_file_content:
        return direct_file_content
    
    return _recursive_search(github_api_token, user_slash_repo, dependency_repo['relative_root'], path_to_file, dependency_repo['commit'])


def _get_direct_file(github_api_token, user_slash_repo, relative_root, path_to_file, commit):
    github_api_url = f"https://api.github.com/repos/{user_slash_repo}/contents/{relative_root}/{path_to_file}?ref={commit}"
    response = fetch(github_api_url, headers={"Authorization": f"token {github_api_token}"})

    if response is None:
        return None
    github_data = response

    if isinstance(github_data, dict) and github_data.get('type') == 'file':
        file_content = github_data.get("content")
        if not file_content:
            logger.error(f"No file content in {path_to_file}")
            return None
        return base64.b64decode(file_content).decode()

    return None


def _recursive_search(github_api_token, user_slash_repo, relative_path, filename, commit, checked_dirs=None):
    if checked_dirs is None:
        checked_dirs = []

    github_api_url = f"https://api.github.com/repos/{user_slash_repo}/contents/{relative_path}/{filename}?ref={commit}"
    github_data = fetch(github_api_url, headers={"Authorization": f"token {github_api_token}"})

    if github_data and isinstance(github_data, dict) and "content" in github_data:
        return base64.b64decode(github_data["content"]).decode()

    github_api_url = f"https://api.github.com/repos/{user_slash_repo}/contents/{relative_path}?ref={commit}"
    github_data = fetch(github_api_url, headers={"Authorization": f"token {github_api_token}"})

    if github_data and isinstance(github_data, list):
        directories = [item['path'] for item in github_data if item['type'] == 'dir']

        for dir_path in directories:
            if dir_path in checked_dirs:
                continue

            checked_dirs.append(dir_path)
            found_content = _recursive_search(github_api_token, user_slash_repo, dir_path, filename, commit, checked_dirs)
            if found_content:
                return found_content

        if relative_path and relative_path not in checked_dirs:
            checked_dirs.append(relative_path)
            return _recursive_search(github_api_token, user_slash_repo, '', filename, commit, checked_dirs)

    return None


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
