import base64
import binascii
import os

from .common import (
    build_hashed_cache_key,
    fetch,
    load_cache,
    parse_repo_link,
    save_cache,
)
from .logger import logger

# Cache directory for storing GitHub files
GITHUB_CACHE_DIR = os.path.join(os.getcwd(), ".diffyscan_cache", "github")


def _get_github_cache_path(
    user_slash_repo: str,
    commit: str,
    relative_root: str,
    path_to_file: str,
) -> str:
    cache_key = build_hashed_cache_key(
        user_slash_repo,
        commit,
        relative_root,
        path_to_file,
    )
    return os.path.join(GITHUB_CACHE_DIR, f"{cache_key}.txt")


def _build_repo_file_request(
    dependency_repo: dict,
    path_to_file: str,
    dep_name: str | None,
) -> tuple[str, str, str, str]:
    normalized_path = path_to_file_without_dependency(path_to_file, dep_name)
    return (
        parse_repo_link(dependency_repo["url"]),
        dependency_repo["commit"],
        dependency_repo["relative_root"],
        normalized_path,
    )


def _get_github_headers(github_api_token: str) -> dict[str, str]:
    return {"Authorization": f"token {github_api_token}"}


def _fetch_github_json(
    github_api_token: str,
    user_slash_repo: str,
    relative_root: str,
    path_to_file: str | None,
    commit: str,
) -> tuple[str, dict | list | None]:
    github_api_url = get_github_api_url(
        user_slash_repo,
        relative_root,
        path_to_file,
        commit,
    )
    response = fetch(github_api_url, headers=_get_github_headers(github_api_token))
    return github_api_url, response.json()


def _decode_github_file_content(
    file_content: str,
    path_to_file: str,
) -> str | None:
    try:
        return base64.b64decode(file_content).decode()
    except (binascii.Error, UnicodeDecodeError) as e:
        logger.error(f"Failed to decode GitHub file content for {path_to_file}: {e}")
        return None


def _extract_github_file_content(
    github_data: dict | list | None,
    path_to_file: str,
    *,
    require_file_type: bool = False,
) -> str | None:
    if not isinstance(github_data, dict):
        return None

    if require_file_type and github_data.get("type") != "file":
        return None

    file_content = github_data.get("content")
    if not file_content:
        logger.error(f"No file content in {path_to_file}")
        return None

    return _decode_github_file_content(file_content, path_to_file)


def _fetch_exact_github_file(
    github_api_token: str,
    user_slash_repo: str,
    relative_root: str,
    path_to_file: str,
    commit: str,
    *,
    require_file_type: bool = False,
    log_missing_data: bool = False,
) -> str | None:
    github_api_url, github_data = _fetch_github_json(
        github_api_token,
        user_slash_repo,
        relative_root,
        path_to_file,
        commit,
    )
    if not github_data:
        if log_missing_data:
            logger.error("No github data for", github_api_url)
        return None

    return _extract_github_file_content(
        github_data,
        path_to_file,
        require_file_type=require_file_type,
    )


def _get_file_from_github_with_cache(
    github_api_token: str,
    dependency_repo: dict,
    path_to_file: str,
    dep_name: str | None,
    use_cache: bool,
    fetcher,
) -> str | None:
    user_slash_repo, commit, relative_root, path_to_file = _build_repo_file_request(
        dependency_repo,
        path_to_file,
        dep_name,
    )
    cache_path = _get_github_cache_path(
        user_slash_repo,
        commit,
        relative_root,
        path_to_file,
    )

    if use_cache:
        cached_content = load_cache(cache_path, "GitHub file", path_to_file)
        if cached_content is not None:
            return cached_content

    content = fetcher(
        github_api_token,
        user_slash_repo,
        relative_root,
        path_to_file,
        commit,
    )

    if use_cache and content is not None:
        save_cache(cache_path, "GitHub file", path_to_file, content)

    return content


def get_file_from_github(
    github_api_token: str,
    dependency_repo: dict,
    path_to_file: str,
    dep_name: str | None,
    use_cache: bool = False,
) -> str | None:
    return _get_file_from_github_with_cache(
        github_api_token,
        dependency_repo,
        path_to_file,
        dep_name,
        use_cache,
        lambda *args: _fetch_exact_github_file(*args, log_missing_data=True),
    )


def get_file_from_github_recursive(
    github_api_token: str,
    dependency_repo: dict,
    path_to_file: str,
    dep_name: str | None,
    use_cache: bool = False,
) -> str | None:
    return _get_file_from_github_with_cache(
        github_api_token,
        dependency_repo,
        path_to_file,
        dep_name,
        use_cache,
        _recursive_search,
    )


def _recursive_search(
    github_api_token,
    user_slash_repo,
    relative_path,
    filename,
    commit,
    checked_dirs=None,
):
    checked_dirs = checked_dirs or set()

    direct_file_content = _fetch_exact_github_file(
        github_api_token,
        user_slash_repo,
        relative_path,
        filename,
        commit,
        require_file_type=True,
    )
    if direct_file_content is not None:
        return direct_file_content

    _, github_data = _fetch_github_json(
        github_api_token,
        user_slash_repo,
        relative_path,
        None,
        commit,
    )
    if isinstance(github_data, list):
        directories = [item["path"] for item in github_data if item["type"] == "dir"]

        for dir_path in directories:
            if dir_path in checked_dirs:
                continue

            checked_dirs.add(dir_path)
            found_content = _recursive_search(
                github_api_token,
                user_slash_repo,
                dir_path,
                filename,
                commit,
                checked_dirs,
            )
            if found_content is not None:
                return found_content

        if relative_path and relative_path not in checked_dirs:
            checked_dirs.add(relative_path)
            return _recursive_search(
                github_api_token,
                user_slash_repo,
                "",
                filename,
                commit,
                checked_dirs,
            )

    return None


def path_to_file_without_dependency(path_to_file: str, dep_name: str | None) -> str:
    """
    Exclude dependency prefix from path to file.

    Example: "@aragon/something/lib/my.sol" => "lib/my.sol"

    Args:
        path_to_file: The full file path
        dep_name: The dependency name prefix to remove

    Returns:
        The file path without the dependency prefix
    """
    return path_to_file if not dep_name else path_to_file[len(dep_name) + 1 :]


def resolve_dep(path_to_file: str, config: dict) -> tuple[dict | None, str | None]:
    """
    Find the dependency configuration that matches the path_to_file.

    Example: "@openzeppelin/contracts-v4.4" in
    "@openzeppelin/contracts-v4.4/utils/structs/EnumerableSet.sol"

    Args:
        path_to_file: The file path to resolve
        config: The configuration dict containing dependencies

    Returns:
        A tuple of (dependency_config, dep_name) or (None, None)
    """
    for dep_name in sorted(config.get("dependencies", {}), key=len, reverse=True):
        if path_to_file.startswith(f"{dep_name}/"):
            return config["dependencies"][dep_name], dep_name

    return None, None


def get_github_api_url(
    user_slash_repo: str, relative_root: str, path_to_file: str | None, commit: str
) -> str:
    """
    Build GitHub API URL for fetching file contents.

    Args:
        user_slash_repo: Repository in format "user/repo"
        relative_root: Relative root path in the repo
        path_to_file: Path to the file (can be None for directory listing)
        commit: Git commit hash or branch name

    Returns:
        The GitHub API URL
    """
    url = f"https://api.github.com/repos/{user_slash_repo}/contents"
    if relative_root:
        url += f"/{relative_root}"
    if path_to_file:
        url += f"/{path_to_file}"
    if commit:
        url += f"?ref={commit}"
    return url
