from typing import TypedDict, NotRequired


class BinaryConfig(TypedDict):
    hardhat_config_name: str
    constructor_calldata: NotRequired[dict[str, str]]
    constructor_args: NotRequired[dict[str, list]]
    libraries: NotRequired[dict[str, dict[str, str]]]


class GithubRepo(TypedDict):
    url: str
    commit: str
    relative_root: str


class Config(TypedDict):
    contracts: dict[str, str]
    network: str
    github_repo: GithubRepo
    dependencies: NotRequired[dict[str, GithubRepo]]
    explorer_hostname: str
    explorer_token_env_var: NotRequired[str]
    explorer_chain_id: NotRequired[int]
    bytecode_comparison: NotRequired[BinaryConfig]
    fail_on_bytecode_comparison_error: NotRequired[bool]
    source_comparison: NotRequired[bool]
