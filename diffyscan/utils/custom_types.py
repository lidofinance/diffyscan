from typing import TypedDict, NotRequired


class BinaryConfig(TypedDict):
    constructor_calldata: NotRequired[dict[str, str]]
    constructor_args: NotRequired[dict[str, list]]
    deployment_from: NotRequired[dict[str, str]]
    libraries: NotRequired[dict[str, dict[str, str]]]
    extra_sources: NotRequired[dict[str, list[str]]]


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


class LocalCompilation(TypedDict):
    # full solc build string, e.g. "v0.8.26+commit.8a97fa7a"
    compiler: str
    # contract address -> path of its solc standard-JSON input file,
    # resolved relative to the config file
    inputs: dict[str, str]


class Config(TypedDict):
    contracts: dict[str, str]
    network: NotRequired[str]
    github_repo: GithubRepo
    dependencies: NotRequired[dict[str, GithubRepo]]
    explorer_hostname: str
    explorer_hostname_env_var: NotRequired[str]
    explorer_token_env_var: NotRequired[str]
    explorer_chain_id: NotRequired[int | str]
    rpc_url_env_var: NotRequired[str]
    deployment_gas_limit: NotRequired[int]
    bytecode_comparison: NotRequired[BinaryConfig]
    local_compilation: NotRequired[LocalCompilation]
    allowed_diffs: NotRequired[AllowedDiffsConfig]
    fail_on_bytecode_comparison_error: NotRequired[bool]
    source_comparison: NotRequired[bool]
    audit_url: NotRequired[str]
    metadata: NotRequired[dict]
