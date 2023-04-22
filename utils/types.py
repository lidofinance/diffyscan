from typing import Dict, TypedDict


class Config(TypedDict):
    contract: str
    network: str
    github_repo: str
    dependencies: Dict[str, str]
