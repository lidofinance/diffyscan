import base64
import re
from utils.common import fetch, parse_repo_link
from utils.logger import logger


def get_file_from_github(github_api_token, dependency_repo, filepath):
    user_slash_repo, ref = parse_repo_link(dependency_repo)
    path_to_file = re.search("contracts.*", filepath).group(0)

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
