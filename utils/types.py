from typing import TypedDict


class Config(TypedDict):
    contracts: dict[str, str]
    network: str
    github_repo: str
    dependencies: dict[str, str]
