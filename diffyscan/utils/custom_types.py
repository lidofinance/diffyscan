from typing import TypedDict


class BinartConfig(TypedDict):
    raise_exception: bool
    hardhat_config_name: str
    local_RPC_URL: str
    remote_RPC_URL: str
    constructor_calldata: set
    constructor_args: set


class Config(TypedDict):
    contracts: dict[str, str]
    network: str
    github_repo: str
    dependencies: dict[str, str]
    explorer_hostname: str
    explorer_token_env_var: str
    bytecode_comparison: BinartConfig
