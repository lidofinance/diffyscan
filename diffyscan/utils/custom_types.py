from typing import TypedDict, NotRequired


class BinaryConfig(TypedDict):
    hardhat_config_name: NotRequired[str]
    constructor_calldata: NotRequired[dict[str, str]]
    constructor_args: NotRequired[dict[str, list]]
    libraries: NotRequired[dict[str, dict[str, str]]]


class ImmutableRule(TypedDict):
    offset: int
    value: str


class ByteRangeRule(TypedDict):
    offset: int
    length: int


class SourceSpan(TypedDict):
    start: int
    count: int


class SourceLineRangeRule(TypedDict):
    file: str
    github: SourceSpan
    explorer: SourceSpan


class AllowedBytecodeDiffRule(TypedDict):
    reason: str
    any: NotRequired[bool]
    immutables: NotRequired[list[ImmutableRule]]
    cbor_metadata: NotRequired[bool]
    byte_ranges: NotRequired[list[ByteRangeRule]]
    constructor_args: NotRequired[list]
    constructor_calldata: NotRequired[str]


class AllowedSourceDiffRule(TypedDict):
    reason: str
    any: NotRequired[bool]
    files: NotRequired[list[str]]
    line_ranges: NotRequired[list[SourceLineRangeRule]]


class AllowedDiffsConfig(TypedDict):
    bytecode: NotRequired[dict[str, list[AllowedBytecodeDiffRule]]]
    source: NotRequired[dict[str, list[AllowedSourceDiffRule]]]


class ExplorerContract(TypedDict, total=False):
    name: str
    compiler: str
    solcInput: dict
    constructor_arguments: str
    evm_version: str
    libraries: dict[str, dict[str, str]]


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
    explorer_hostname_env_var: NotRequired[str]
    explorer_token_env_var: NotRequired[str]
    explorer_chain_id: NotRequired[int]
    bytecode_comparison: NotRequired[BinaryConfig]
    allowed_diffs: NotRequired[AllowedDiffsConfig]
    fail_on_bytecode_comparison_error: NotRequired[bool]
    source_comparison: NotRequired[bool]
    audit_url: NotRequired[str]
    metadata: NotRequired[dict]
