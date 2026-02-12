import base64
import binascii
import os
import hashlib

from .common import fetch, parse_repo_link
from .logger import logger

# Cache directory for storing GitHub files
GITHUB_CACHE_DIR = os.path.join(os.getcwd(), ".diffyscan_cache", "github")


def _get_github_cache_key(user_slash_repo, commit, relative_root, path_to_file):
    """
    Generate a unique cache key for a GitHub file.

    Args:
        user_slash_repo: Repository in format "user/repo"
        commit: Git commit hash
        relative_root: Relative root path in the repo
        path_to_file: Path to the file

    Returns:
        A string cache key (hash)
    """
    # Combine all parts to create unique identifier
    cache_string = f"{user_slash_repo}:{commit}:{relative_root}:{path_to_file}"
    # Use SHA256 hash for consistent, filesystem-safe cache keys
    return hashlib.sha256(cache_string.encode()).hexdigest()


def _get_github_cache_path(cache_key):
    """Get the file path for a GitHub cache key."""
    return os.path.join(GITHUB_CACHE_DIR, f"{cache_key}.txt")


def _load_from_github_cache(user_slash_repo, commit, relative_root, path_to_file):
    """
    Load file content from GitHub cache if available.

    Returns:
        Cached file content or None if not found
    """
    cache_key = _get_github_cache_key(
        user_slash_repo, commit, relative_root, path_to_file
    )
    cache_path = _get_github_cache_path(cache_key)

    if os.path.exists(cache_path):
        try:
            logger.info(f"Loading GitHub file from cache: {path_to_file}")
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warn(f"Failed to load from GitHub cache: {e}")
            return None
    return None


def _save_to_github_cache(
    user_slash_repo, commit, relative_root, path_to_file, content
):
    """
    Save file content to GitHub cache.

    Args:
        user_slash_repo: Repository in format "user/repo"
        commit: Git commit hash
        relative_root: Relative root path in the repo
        path_to_file: Path to the file
        content: File content to cache
    """
    cache_key = _get_github_cache_key(
        user_slash_repo, commit, relative_root, path_to_file
    )
    cache_path = _get_github_cache_path(cache_key)

    try:
        # Create cache directory if it doesn't exist
        os.makedirs(GITHUB_CACHE_DIR, exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved GitHub file to cache: {path_to_file}")
    except Exception as e:
        logger.warn(f"Failed to save to GitHub cache: {e}")


def get_file_from_github(
    github_api_token: str,
    dependency_repo: dict,
    path_to_file: str,
    dep_name: str | None,
    use_cache: bool = False,
) -> str | None:
    path_to_file = path_to_file_without_dependency(path_to_file, dep_name)
    user_slash_repo = parse_repo_link(dependency_repo["url"])

    # Try to load from cache if enabled
    if use_cache:
        cached_content = _load_from_github_cache(
            user_slash_repo,
            dependency_repo["commit"],
            dependency_repo["relative_root"],
            path_to_file,
        )
        if cached_content is not None:
            return cached_content

    github_api_url = get_github_api_url(
        user_slash_repo,
        dependency_repo["relative_root"],
        path_to_file,
        dependency_repo["commit"],
    )

    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    ).json()

    if not github_data:
        logger.error("No github data for", github_api_url)
        return None

    file_content = github_data.get("content")

    if not file_content:
        logger.error("No file content")
        return None

    try:
        decoded_content = base64.b64decode(file_content).decode()
    except (binascii.Error, UnicodeDecodeError) as e:
        logger.error(f"Failed to decode GitHub file content: {e}")
        return None

    # Save to cache if enabled
    if use_cache:
        _save_to_github_cache(
            user_slash_repo,
            dependency_repo["commit"],
            dependency_repo["relative_root"],
            path_to_file,
            decoded_content,
        )

    return decoded_content


def get_file_from_github_recursive(
    github_api_token: str,
    dependency_repo: dict,
    path_to_file: str,
    dep_name: str | None,
    use_cache: bool = False,
) -> str | None:
    path_to_file = path_to_file_without_dependency(path_to_file, dep_name)
    user_slash_repo = parse_repo_link(dependency_repo["url"])

    # Try to load from cache if enabled
    if use_cache:
        cached_content = _load_from_github_cache(
            user_slash_repo,
            dependency_repo["commit"],
            dependency_repo["relative_root"],
            path_to_file,
        )
        if cached_content is not None:
            return cached_content

    direct_file_content = _get_direct_file(
        github_api_token,
        user_slash_repo,
        dependency_repo["relative_root"],
        path_to_file,
        dependency_repo["commit"],
    )
    if direct_file_content:
        # Save to cache if enabled
        if use_cache:
            _save_to_github_cache(
                user_slash_repo,
                dependency_repo["commit"],
                dependency_repo["relative_root"],
                path_to_file,
                direct_file_content,
            )
        return direct_file_content

    recursive_content = _recursive_search(
        github_api_token,
        user_slash_repo,
        dependency_repo["relative_root"],
        path_to_file,
        dependency_repo["commit"],
    )

    # Save to cache if enabled and content was found
    if use_cache and recursive_content:
        _save_to_github_cache(
            user_slash_repo,
            dependency_repo["commit"],
            dependency_repo["relative_root"],
            path_to_file,
            recursive_content,
        )

    return recursive_content


def _get_direct_file(
    github_api_token, user_slash_repo, relative_root, path_to_file, commit
):
    github_api_url = get_github_api_url(
        user_slash_repo, relative_root, path_to_file, commit
    )
    response = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    ).json()

    if response is None:
        return None
    github_data = response

    if isinstance(github_data, dict) and github_data.get("type") == "file":
        file_content = github_data.get("content")
        if not file_content:
            logger.error(f"No file content in {path_to_file}")
            return None
        try:
            return base64.b64decode(file_content).decode()
        except (binascii.Error, UnicodeDecodeError) as e:
            logger.error(
                f"Failed to decode GitHub file content for {path_to_file}: {e}"
            )
            return None

    return None


def _recursive_search(
    github_api_token,
    user_slash_repo,
    relative_path,
    filename,
    commit,
    checked_dirs=None,
):
    if checked_dirs is None:
        checked_dirs = []

    github_api_url = get_github_api_url(
        user_slash_repo, relative_path, filename, commit
    )
    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    ).json()

    if github_data and isinstance(github_data, dict) and "content" in github_data:
        try:
            return base64.b64decode(github_data["content"]).decode()
        except (binascii.Error, UnicodeDecodeError) as e:
            logger.error(f"Failed to decode GitHub content for {filename}: {e}")
            return None

    github_api_url = get_github_api_url(user_slash_repo, relative_path, None, commit)
    github_data = fetch(
        github_api_url, headers={"Authorization": f"token {github_api_token}"}
    ).json()

    if github_data and isinstance(github_data, list):
        directories = [item["path"] for item in github_data if item["type"] == "dir"]

        for dir_path in directories:
            if dir_path in checked_dirs:
                continue

            checked_dirs.append(dir_path)
            found_content = _recursive_search(
                github_api_token,
                user_slash_repo,
                dir_path,
                filename,
                commit,
                checked_dirs,
            )
            if found_content:
                return found_content

        if relative_path and relative_path not in checked_dirs:
            checked_dirs.append(relative_path)
            return _recursive_search(
                github_api_token, user_slash_repo, "", filename, commit, checked_dirs
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
    if not dep_name:
        return path_to_file

    dep_name_and_slash_length = len(dep_name) + 1
    path_to_file_without_dependency = path_to_file[dep_name_and_slash_length:]

    return path_to_file_without_dependency


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
    dep_names = sorted(
        list(config.get("dependencies", {}).keys()), key=len, reverse=True
    )

    for dep_name in dep_names:
        if path_to_file.startswith(f"{dep_name}/"):
            return (config["dependencies"][dep_name], dep_name)

    return (None, None)


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
