from diffyscan.utils.github import (
    get_github_api_url,
    path_to_file_without_dependency,
    resolve_dep,
)


def test_get_github_api_url():
    url = get_github_api_url('user/repo', 'src', 'file.sol', 'abc123')
    assert url == 'https://api.github.com/repos/user/repo/contents/src/file.sol?ref=abc123'


def test_path_to_file_without_dependency():
    result = path_to_file_without_dependency('@oz/contracts/token.sol', '@oz/contracts')
    assert result == 'token.sol'


def test_resolve_dep():
    cfg = {
        'dependencies': {
            '@oz/contracts': {'url': 'u', 'commit': 'c', 'relative_root': ''}
        }
    }
    repo, dep_name = resolve_dep('@oz/contracts/token.sol', cfg)
    assert dep_name == '@oz/contracts'
    assert repo['commit'] == 'c'
