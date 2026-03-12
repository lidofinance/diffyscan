import difflib
import sys
import time
import argparse
import os
import traceback

from dotenv import load_dotenv

from . import __version__
from .utils.common import load_config, load_env
from .utils.constants import (
    DIFFS_DIR,
    START_TIME,
)
from .utils.explorer import (
    get_contract_from_explorer,
    compile_contract_from_explorer,
    parse_compiled_contract,
    get_explorer_hostname,
    get_explorer_chain_id,
    merge_libraries,
    get_solc_sources,
)
from .utils.github import (
    get_file_from_github,
    get_file_from_github_recursive,
    resolve_dep,
)
from .utils.helpers import create_dirs
from .utils.logger import logger
from .utils.binary_verifier import deep_match_bytecode
from .utils.node_handler import (
    get_bytecode_from_node,
    get_chain_id,
    simulate_deployment,
)
from .utils.calldata import get_calldata
from .utils.custom_exceptions import (
    ExceptionHandler,
    BaseCustomException,
    CompileError,
)


def _fetch_github_source(
    path_to_file: str,
    config: dict,
    github_api_token: str,
    recursive_parsing: bool,
    cache_github: bool,
) -> str | None:
    repo, dep_name = resolve_dep(path_to_file, config)
    if not dep_name:
        repo = config["github_repo"]

    fetcher = (
        get_file_from_github_recursive if recursive_parsing else get_file_from_github
    )
    return fetcher(github_api_token, repo, path_to_file, dep_name, cache_github)


def _build_github_solc_input(
    contract_source_code,
    config,
    github_api_token,
    recursive_parsing,
    cache_github,
):
    solc_input = contract_source_code["solcInput"]
    sources = get_solc_sources(solc_input)
    updated_sources = {}
    missing = []

    for path_to_file in sources:
        github_file = _fetch_github_source(
            path_to_file,
            config,
            github_api_token,
            recursive_parsing,
            cache_github,
        )

        if not github_file:
            missing.append(path_to_file)
            continue

        updated_sources[path_to_file] = {"content": github_file}

    if "sources" in solc_input:
        github_solc_input = dict(solc_input)
        github_solc_input["sources"] = updated_sources
    else:
        github_solc_input = {"sources": updated_sources}

    return github_solc_input, missing


def run_bytecode_diff(
    contract_address_from_config,
    contract_name_from_config,
    contract_source_code,
    config,
    github_api_token,
    recursive_parsing,
    cache_github,
    remote_rpc_url,
):
    """Run bytecode comparison. Returns True if bytecodes match."""
    address_name = f"{contract_address_from_config} : {contract_name_from_config}"
    logger.divider()
    logger.info(f"Binary bytecode comparison started for {address_name}")

    explorer_libraries = contract_source_code.get("libraries")
    manual_libraries = config.get("bytecode_comparison", {}).get("libraries")
    libraries = merge_libraries(explorer_libraries, manual_libraries)
    evm_version = contract_source_code.get("evm_version")
    explorer_constructor_arguments = contract_source_code.get("constructor_arguments")

    _log_explorer_bytecode_metadata(
        explorer_constructor_arguments,
        evm_version,
        explorer_libraries,
        manual_libraries,
    )

    github_solc_input, missing_sources = _build_github_solc_input(
        contract_source_code,
        config,
        github_api_token,
        recursive_parsing,
        cache_github,
    )
    if missing_sources:
        missing_preview = ", ".join(missing_sources[:5])
        more = ""
        if len(missing_sources) > 5:
            more = f" (and {len(missing_sources) - 5} more)"
        raise CompileError(
            "missing GitHub sources for bytecode compilation; "
            f"count={len(missing_sources)}; first={missing_preview}{more}"
        )

    github_contract_source = dict(contract_source_code)
    github_contract_source["solcInput"] = github_solc_input
    target_compiled_contract = compile_contract_from_explorer(
        github_contract_source, libraries, evm_version
    )
    logger.okay("Compiled contract for bytecode comparison using GitHub sources")

    contract_creation_code, local_compiled_bytecode, immutables = (
        parse_compiled_contract(target_compiled_contract)
    )

    remote_deployed_bytecode = get_bytecode_from_node(
        contract_address_from_config, remote_rpc_url
    )

    is_fully_matched = local_compiled_bytecode == remote_deployed_bytecode

    if is_fully_matched:
        logger.okay("Bytecodes fully match")
        return True

    logger.info("Static bytecodes do not match, simulating constructor via eth_call")

    calldata = get_calldata(
        contract_address_from_config,
        target_compiled_contract,
        config.get("bytecode_comparison"),
        explorer_constructor_arguments,
    )

    deployment_call_data = _append_calldata(contract_creation_code, calldata)
    local_deployed_bytecode = simulate_deployment(deployment_call_data, remote_rpc_url)

    is_fully_matched = local_deployed_bytecode == remote_deployed_bytecode

    if is_fully_matched:
        logger.okay("Bytecodes fully match")
        return True

    return deep_match_bytecode(
        local_deployed_bytecode,
        remote_deployed_bytecode,
        immutables,
    )


def run_source_diff(
    contract_address_from_config,
    contract_code,
    config,
    github_api_token,
    recursive_parsing=False,
    cache_github=False,
    skip_user_input=False,
):
    """Run source code diff for a contract. Returns a stats dict."""
    source_files = get_solc_sources(contract_code["solcInput"])
    standard_json_format = is_standard_json_contract(source_files)

    explorer_hostname = get_explorer_hostname(config)
    explorer_chain_id = get_explorer_chain_id(config)
    logger.divider()
    logger.okay("Contract", contract_address_from_config)
    logger.okay("Blockchain explorer Hostname", explorer_hostname)
    if explorer_chain_id:
        logger.okay("Blockchain explorer Chain ID", explorer_chain_id)
    else:
        logger.warn("Blockchain explorer Chain ID isn't set")
    logger.okay("Repo", config["github_repo"]["url"])
    logger.okay("Repo commit", config["github_repo"]["commit"])
    logger.okay("Repo relative root", config["github_repo"]["relative_root"])

    logger.divider()

    logger.info(
        f"Fetching source code from blockchain explorer {explorer_hostname} ..."
    )

    files_count = len(source_files)
    logger.okay("Contract", contract_code["name"])
    logger.okay("Files", files_count)

    if not skip_user_input:
        if sys.stdin.isatty():
            input("Press Enter to proceed...")
        else:
            logger.info("Skipping prompt (non-interactive stdin).")
        logger.divider()

    logger.info("Diffing...")

    report = []

    for file_number, (path_to_file, source_code) in enumerate(
        source_files.items(), start=1
    ):
        if not standard_json_format:
            path_to_file = path_to_file + ".sol"

        split_path_to_file = path_to_file.split("/")
        origin = split_path_to_file[0]
        filename = split_path_to_file[-1]

        logger.update_info(f"File {file_number} / { files_count}", filename)

        diff_report_filename = None
        diffs_count = None
        github_file = _fetch_github_source(
            path_to_file,
            config,
            github_api_token,
            recursive_parsing,
            cache_github,
        )

        file_found = bool(github_file)
        if not github_file:
            github_file = "<!-- No file content -->"

        explorer_content = source_code["content"]

        github_lines = github_file.splitlines()
        explorer_lines = explorer_content.splitlines()

        diff_html = difflib.HtmlDiff().make_file(github_lines, explorer_lines)
        diff_report_filename = (
            f"{DIFFS_DIR}/{contract_address_from_config}/{filename}.html"
        )

        create_dirs(diff_report_filename)
        with open(diff_report_filename, "w") as f:
            f.write(diff_html)

        diffs = difflib.unified_diff(github_lines, explorer_lines)
        diffs_count = len(list(diffs))

        report_data = [
            file_number,
            filename,
            file_found,
            diffs_count,
            origin,
            diff_report_filename,
        ]

        report.append(report_data)

    logger.divider()

    files_found = sum(row[2] for row in report)
    logger.info(f"Files found: {files_found} / {files_count}")

    identical_files = sum(row[3] == 0 for row in report)
    logger.info(f"Identical files: {identical_files} / {files_found}")

    files_with_diffs = sum(row[2] and row[3] > 0 for row in report)

    logger.report_table(report)

    return {
        "files_count": files_count,
        "files_found": files_found,
        "identical_files": identical_files,
        "files_with_diffs": files_with_diffs,
        "contract_address": contract_address_from_config,
        "contract_name": contract_code["name"],
    }


def _load_explorer_token(config: dict) -> str | None:
    """Load explorer token from config env var name, falling back to ETHERSCAN_EXPLORER_TOKEN."""
    env_var = config.get("explorer_token_env_var")
    if env_var:
        token = load_env(env_var, masked=True, required=False)
        if token:
            return token
        logger.warn(f'Explorer token not found in env ("{env_var}")')
    else:
        logger.warn('Config missing "explorer_token_env_var"')

    token = os.getenv("ETHERSCAN_EXPLORER_TOKEN")
    if token is None:
        logger.warn("Fallback ETHERSCAN_EXPLORER_TOKEN not set")
    return token


def _setup_binary_comparison(config: dict) -> str:
    """Load REMOTE_RPC_URL and configure exception handling for bytecode comparison."""
    remote_rpc_url = load_env("REMOTE_RPC_URL", masked=True, required=True)
    ExceptionHandler.initialize(config.get("fail_on_bytecode_comparison_error", True))
    return remote_rpc_url


def _append_calldata(creation_code: str, calldata: str | None) -> str:
    if not calldata:
        return creation_code
    return creation_code + calldata


def _log_explorer_bytecode_metadata(
    constructor_arguments: str | None,
    evm_version: str | None,
    explorer_libraries: dict | None,
    manual_libraries: dict | None,
) -> None:
    constructor_length = (
        "missing"
        if constructor_arguments is None
        else f"{len(constructor_arguments) // 2} bytes"
    )
    logger.okay("Explorer constructor calldata", constructor_length)
    logger.okay("Explorer EVM version", evm_version or "default")
    logger.okay(
        "Explorer library count",
        sum(len(libraries) for libraries in (explorer_libraries or {}).values()),
    )
    if manual_libraries:
        logger.warn(
            "Manual libraries override explorer metadata",
            sum(len(libraries) for libraries in manual_libraries.values()),
        )


def _warn_deprecated_hardhat_settings(
    config: dict, hardhat_config_path: str | None
) -> None:
    if hardhat_config_path:
        logger.warn("--hardhat-path is deprecated and ignored")

    bytecode_comparison = config.get("bytecode_comparison", {})
    if isinstance(bytecode_comparison, dict) and bytecode_comparison.get(
        "hardhat_config_name"
    ):
        logger.warn(
            'Config key "bytecode_comparison.hardhat_config_name" is deprecated and ignored'
        )


def process_config(
    path: str,
    hardhat_config_path: str | None,
    recursive_parsing: bool,
    enable_binary_comparison: bool,
    cache_explorer: bool,
    cache_github: bool,
    skip_user_input: bool = False,
):
    """Process a config file and run source + bytecode comparisons."""
    # Reset exception handler to default before each config
    ExceptionHandler.initialize(True)

    logger.info(f"Loading config {path}...")
    config = load_config(path)
    _warn_deprecated_hardhat_settings(config, hardhat_config_path)

    # Load tokens and validate
    explorer_token = _load_explorer_token(config)
    github_api_token = load_env("GITHUB_API_TOKEN", masked=True, required=True)

    # Setup binary comparison if enabled
    remote_rpc_url = None
    if enable_binary_comparison:
        remote_rpc_url = _setup_binary_comparison(config)

    # Check if source comparison is enabled
    enable_source_comparison = config.get("source_comparison", True)
    if not enable_source_comparison:
        logger.warn(
            f'Source code comparison is disabled in {path}. To enable, set "source_comparison": true in the config'
        )

    # Statistics tracking
    source_stats = []
    bytecode_stats = []

    try:
        if enable_binary_comparison:
            logger.info("Getting remote chain ID...")
            remote_chain_id = get_chain_id(remote_rpc_url)
            logger.okay("Remote chain ID", remote_chain_id)

        for contract_address, contract_name in config["contracts"].items():
            try:
                contract_code = get_contract_from_explorer(
                    explorer_token,
                    get_explorer_hostname(config),
                    contract_address,
                    contract_name,
                    get_explorer_chain_id(config),
                    cache_explorer,
                )

                if enable_source_comparison:
                    source_result = run_source_diff(
                        contract_address,
                        contract_code,
                        config,
                        github_api_token,
                        recursive_parsing,
                        cache_github,
                        skip_user_input,
                    )
                    source_stats.append(source_result)

                if enable_binary_comparison:
                    try:
                        bytecode_match = run_bytecode_diff(
                            contract_address,
                            contract_name,
                            contract_code,
                            config,
                            github_api_token,
                            recursive_parsing,
                            cache_github,
                            remote_rpc_url,
                        )
                        bytecode_stats.append(
                            {
                                "contract_address": contract_address,
                                "contract_name": contract_name,
                                "match": bytecode_match,
                            }
                        )
                    except BaseCustomException as exc:
                        # Treat bytecode comparison errors as reportable diffs; final
                        # allowlist handling happens after all contracts are processed.
                        logger.error(str(exc))
                        bytecode_stats.append(
                            {
                                "contract_address": contract_address,
                                "contract_name": contract_name,
                                "match": False,
                            }
                        )
            except BaseCustomException as custom_exc:
                ExceptionHandler.raise_exception_or_log(custom_exc)
                traceback.print_exc()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt by user")

    return {
        "source_stats": source_stats,
        "bytecode_stats": bytecode_stats,
        "config_path": path,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", "-V", action="store_true", help="Display version information"
    )
    parser.add_argument(
        "path", nargs="?", default=None, help="Path to config or directory with configs"
    )
    parser.add_argument(
        "--hardhat-path",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--yes",
        "-Y",
        help="If set don't ask for input before validating each contract",
        action="store_true",
    )
    parser.add_argument(
        "--support-brownie",
        help="Support recursive retrieving for contracts. It may be useful for contracts whose sources have been verified by the brownie tooling, which automatically replaces relative paths to contracts in imports with plain contract names.",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--skip-binary-comparison",
        "-S",
        help="Skip binary bytecode comparison (enabled by default)",
        action="store_true",
    )
    parser.add_argument(
        "--cache-explorer",
        "-E",
        help="Cache contract sources from blockchain explorers to avoid re-fetching on repeated runs",
        action="store_true",
    )
    parser.add_argument(
        "--cache-github",
        "-G",
        help="Cache files retrieved from GitHub to avoid re-fetching on repeated runs",
        action="store_true",
    )
    parser.add_argument(
        "--allow-source-diff",
        dest="allow_source_diff",
        action="append",
        default=[],
        help="Allow source diffs for a specific contract address (0x...). Can be passed multiple times.",
    )
    parser.add_argument(
        "--allow-bytecode-diff",
        dest="allow_bytecode_diff",
        action="append",
        default=[],
        help="Allow bytecode diffs for a specific contract address (0x...). Can be passed multiple times.",
    )
    parser.add_argument(
        "--log-level",
        choices=["info", "okay", "warn", "error"],
        default="info",
        help="Set log level (default: info). Use 'warn' or 'error' to reduce output.",
    )
    parser.add_argument(
        "--quiet",
        "-Q",
        help="Hide info messages, show okay/warn/error (shorthand for --log-level okay)",
        action="store_true",
    )
    return parser.parse_args()


def print_final_summary(
    all_results: list[dict],
    enable_source_comparison: bool,
    enable_binary_comparison: bool,
) -> None:
    logger.divider()
    logger.divider()
    logger.info("=" * 80)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 80)

    if enable_source_comparison:
        # Aggregate source code statistics
        total_contracts = 0
        contracts_with_diffs = []
        total_files_with_diffs = 0

        for result in all_results:
            for stat in result["source_stats"]:
                total_contracts += 1
                if stat["files_with_diffs"] > 0:
                    contracts_with_diffs.append(
                        {
                            "address": stat["contract_address"],
                            "name": stat["contract_name"],
                            "files_with_diffs": stat["files_with_diffs"],
                            "total_files": stat["files_found"],
                        }
                    )
                    total_files_with_diffs += stat["files_with_diffs"]

        logger.divider()
        logger.info("SOURCE CODE COMPARISON SUMMARY:")
        logger.okay(f"Total contracts analyzed: {total_contracts}")
        logger.okay(
            f"Contracts with non-zero source diffs: {len(contracts_with_diffs)}"
        )
        logger.okay(f"Total files with non-zero diffs: {total_files_with_diffs}")

        if contracts_with_diffs:
            logger.divider()
            logger.warn("Contracts with source code differences:")
            for contract in contracts_with_diffs:
                logger.warn(
                    f"  • {contract['name']} ({contract['address']}): "
                    f"{contract['files_with_diffs']} file(s) with diffs out of {contract['total_files']}"
                )

    if enable_binary_comparison:
        # Aggregate bytecode statistics
        total_bytecode_checks = 0
        bytecode_mismatches = []

        for result in all_results:
            for stat in result["bytecode_stats"]:
                total_bytecode_checks += 1
                if not stat["match"]:
                    bytecode_mismatches.append(
                        {
                            "address": stat["contract_address"],
                            "name": stat["contract_name"],
                        }
                    )

        logger.divider()
        logger.info("BYTECODE COMPARISON SUMMARY:")
        logger.okay(f"Total contracts analyzed: {total_bytecode_checks}")
        logger.okay(
            f"Contracts with non-zero bytecode diffs: {len(bytecode_mismatches)}"
        )

        if bytecode_mismatches:
            logger.divider()
            logger.warn("Contracts with bytecode differences:")
            for contract in bytecode_mismatches:
                logger.warn(f"  • {contract['name']} ({contract['address']})")

    logger.divider()
    logger.info("=" * 80)


def main() -> None:
    """Main entry point for the diffyscan application."""
    load_dotenv()
    args = parse_arguments()
    skip_user_input = args.yes
    if args.quiet:
        logger.set_level("okay")
    else:
        logger.set_level(args.log_level)
    if args.version:
        print(f"Diffyscan {__version__}")
        return
    logger.info("Welcome to Diffyscan!")
    logger.divider()

    # Binary comparison is enabled by default, unless --skip-binary-comparison is set
    enable_binary_comparison = not args.skip_binary_comparison

    # Resolve config paths
    config_paths = []
    supported_extensions = (".json", ".yaml", ".yml")

    if args.path is None:
        config_path = next(
            (
                p
                for p in ("config.json", "config.yaml", "config.yml")
                if os.path.isfile(p)
            ),
            None,
        )
        if config_path is None:
            error_msg = "No config file found. Create config.json or config.yaml in the current directory, or specify a path with --path."
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        config_paths.append(config_path)
    elif os.path.isfile(args.path):
        config_paths.append(args.path)
    elif os.path.isdir(args.path):
        for filename in sorted(os.listdir(args.path)):
            full_path = os.path.join(args.path, filename)
            if os.path.isfile(full_path) and filename.lower().endswith(
                supported_extensions
            ):
                config_paths.append(full_path)
    else:
        error_msg = f"Specified config path {args.path} not found"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    # Process all config files
    all_results = []
    for config_path in config_paths:
        result = process_config(
            config_path,
            args.hardhat_path,
            args.support_brownie,
            enable_binary_comparison,
            args.cache_explorer,
            args.cache_github,
            skip_user_input,
        )
        all_results.append(result)

    execution_time = time.time() - START_TIME

    # Determine what comparisons were enabled (check first result)
    enable_source_comparison = any(len(r["source_stats"]) > 0 for r in all_results)

    # Print final summary
    print_final_summary(all_results, enable_source_comparison, enable_binary_comparison)

    # Prepare allowlists (lowercased addresses)
    allowed_source_addrs = set(addr.lower() for addr in (args.allow_source_diff or []))
    allowed_bytecode_addrs = set(
        addr.lower() for addr in (args.allow_bytecode_diff or [])
    )

    # Compute unallowed diffs
    unallowed_source_diffs = 0
    if enable_source_comparison:
        for result in all_results:
            for stat in result["source_stats"]:
                if (
                    stat["files_with_diffs"] > 0
                    and stat["contract_address"].lower() not in allowed_source_addrs
                ):
                    unallowed_source_diffs += 1

    unallowed_bytecode_diffs = 0
    if enable_binary_comparison:
        for result in all_results:
            for stat in result["bytecode_stats"]:
                if (not stat["match"]) and stat[
                    "contract_address"
                ].lower() not in allowed_bytecode_addrs:
                    unallowed_bytecode_diffs += 1

    # Report allowlisted diffs for visibility
    if allowed_source_addrs or allowed_bytecode_addrs:
        logger.divider()
        if allowed_source_addrs:
            logger.warn(
                "Allowed source diffs for addresses",
                ", ".join(sorted(allowed_source_addrs)),
            )
        if allowed_bytecode_addrs:
            logger.warn(
                "Allowed bytecode diffs for addresses",
                ", ".join(sorted(allowed_bytecode_addrs)),
            )

    # Decide exit code: non-zero if any unallowed diffs exist
    has_unallowed_diffs = (unallowed_source_diffs > 0) or (unallowed_bytecode_diffs > 0)

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)

    if has_unallowed_diffs:
        # Explicitly log a final line explaining failure condition
        logger.error(
            "Exiting with non-zero code due to unallowed diffs",
            f"source={unallowed_source_diffs}, bytecode={unallowed_bytecode_diffs}",
        )
        sys.exit(1)
    else:
        sys.exit(0)


def is_standard_json_contract(source_files: dict) -> bool:
    """True if source uses Standard JSON format (paths with .sol or /), not single-file."""
    keys = list(source_files)
    if len(keys) != 1:
        return True
    first_key = keys[0] if isinstance(keys[0], str) else keys[0][0]
    return ".sol" in first_key or "/" in first_key


if __name__ == "__main__":
    main()
