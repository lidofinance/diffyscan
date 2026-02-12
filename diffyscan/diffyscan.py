import difflib
import sys
import time
import argparse
import os
import traceback

from dotenv import load_dotenv

from .utils.common import load_config, load_env, prettify_solidity
from .utils.constants import (
    DIFFS_DIR,
    DEFAULT_HARDHAT_CONFIG_PATH,
    START_TIME,
    DEFAULT_LOCAL_RPC_URL,
)
from .utils.explorer import (
    get_contract_from_explorer,
    compile_contract_from_explorer,
    parse_compiled_contract,
    get_explorer_hostname,
    get_explorer_chain_id,
)
from .utils.github import (
    get_file_from_github,
    get_file_from_github_recursive,
    resolve_dep,
)
from .utils.helpers import create_dirs
from .utils.logger import logger
from .utils.binary_verifier import deep_match_bytecode
from .utils.hardhat import hardhat
from .utils.node_handler import (
    get_bytecode_from_node,
    get_account,
    deploy_contract,
    get_chain_id,
)
from .utils.calldata import get_calldata
from .utils.custom_exceptions import (
    ExceptionHandler,
    BaseCustomException,
    BinVerifierError,
    CompileError,
)

__version__ = "0.0.0"


def _build_github_solc_input(
    contract_source_code,
    config,
    github_api_token,
    recursive_parsing,
    cache_github,
):
    solc_input = contract_source_code["solcInput"]
    sources = solc_input.get("sources", solc_input)
    updated_sources = {}
    missing = []

    for path_to_file, source in sources.items():
        repo, dep_name = resolve_dep(path_to_file, config)
        if not dep_name:
            repo = config["github_repo"]

        if recursive_parsing:
            github_file = get_file_from_github_recursive(
                github_api_token, repo, path_to_file, dep_name, cache_github
            )
        else:
            github_file = get_file_from_github(
                github_api_token, repo, path_to_file, dep_name, cache_github
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
    deployer_account,
    local_rpc_url,
    remote_rpc_url,
):
    """
    Run bytecode comparison for a contract.

    Returns:
        bool: True if bytecodes match (fully or only in immutables), False if there are differences
    """
    address_name = f"{contract_address_from_config} : {contract_name_from_config}"
    logger.divider()
    logger.info(f"Binary bytecode comparison started for {address_name}")

    # Get libraries from config if they exist
    libraries = config.get("bytecode_comparison", {}).get("libraries", None)
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
        github_contract_source, libraries
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

    logger.info(
        "Static bytecodes not match, trying local deployment to bind immutables"
    )

    calldata = get_calldata(
        contract_address_from_config,
        target_compiled_contract,
        config["bytecode_comparison"],
    )

    if calldata:
        contract_creation_code += calldata

    local_contract_address = deploy_contract(
        local_rpc_url, deployer_account, contract_creation_code
    )

    local_deployed_bytecode = get_bytecode_from_node(
        local_contract_address, local_rpc_url
    )

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
    prettify=False,
    cache_github=False,
    skip_user_input=False,
):
    """
    Run source code diff for a contract.

    Returns:
        dict: Statistics with keys:
            - 'files_count': total number of files
            - 'files_found': number of files found
            - 'identical_files': number of files with no diffs
            - 'files_with_diffs': number of files with non-zero diffs
            - 'contract_address': address of the contract
            - 'contract_name': name of the contract
    """
    source_files = (
        contract_code["solcInput"].items()
        if "sources" not in contract_code["solcInput"]
        else contract_code["solcInput"]["sources"].items()
    )

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

    for index, (path_to_file, source_code) in enumerate(source_files):
        if not is_standard_json_contract(source_files):
            path_to_file = path_to_file + ".sol"

        file_number = index + 1
        split_path_to_file = path_to_file.split("/")
        origin = split_path_to_file[0]
        filename = split_path_to_file[-1]

        logger.update_info(f"File {file_number} / { files_count}", filename)

        repo = None
        dep_name = None

        (repo, dep_name) = resolve_dep(path_to_file, config)
        if not dep_name:
            repo = config["github_repo"]

        diff_report_filename = None
        diffs_count = None

        if not repo:
            error_msg = f"File not found in any repository: {path_to_file}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        file_found = bool(repo)

        if recursive_parsing:
            github_file = get_file_from_github_recursive(
                github_api_token, repo, path_to_file, dep_name, cache_github
            )
        else:
            github_file = get_file_from_github(
                github_api_token, repo, path_to_file, dep_name, cache_github
            )

        if not github_file:
            github_file = "<!-- No file content -->"
            file_found = False

        explorer_content = source_code["content"]

        if prettify:
            github_file = prettify_solidity(github_file)
            explorer_content = prettify_solidity(explorer_content)

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

    files_found = len([row for row in report if row[2]])
    logger.info(f"Files found: {files_found} / {files_count}")

    identical_files = len([row for row in report if row[3] == 0])
    logger.info(f"Identical files: {identical_files} / {files_found}")

    files_with_diffs = len([row for row in report if row[2] and row[3] > 0])

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
    """
    Load explorer token from config or environment.

    Args:
        config: The configuration dictionary

    Returns:
        str or None: The explorer token if found
    """
    # Try config first
    if "explorer_token_env_var" in config:
        token = load_env(config["explorer_token_env_var"], masked=True, required=False)
        if token:
            return token
        logger.warn(
            f'Failed to find explorer token in env ("{config["explorer_token_env_var"]}")'
        )
    else:
        logger.warn(
            'Failed to find an explorer token in the config ("explorer_token_env_var")'
        )

    # Fall back to default environment variable
    token = os.getenv("ETHERSCAN_EXPLORER_TOKEN", default=None)
    if token is None:
        logger.warn('Failed to find explorer token in env ("ETHERSCAN_EXPLORER_TOKEN")')

    return token


def _validate_github_token() -> str:
    """
    Validate that GitHub API token is set.

    Returns:
        The GitHub API token

    Raises:
        ValueError: If the token is not set
    """
    return load_env("GITHUB_API_TOKEN", masked=True, required=True)


def _setup_binary_comparison(config: dict) -> tuple[str, str]:
    """
    Setup and validate binary comparison configuration.

    Args:
        config: The configuration dictionary

    Returns:
        tuple: (local_rpc_url, remote_rpc_url)

    Raises:
        ValueError: If required configuration is missing
    """
    if "bytecode_comparison" not in config:
        raise ValueError('Failed to find "bytecode_comparison" section in config')

    # LOCAL_RPC_URL may be empty; default to localhost Ganache/Hardhat-compatible URL
    local_rpc_url = load_env("LOCAL_RPC_URL", masked=False, required=False)
    if not local_rpc_url:
        local_rpc_url = DEFAULT_LOCAL_RPC_URL
        logger.okay("LOCAL_RPC_URL (default)", local_rpc_url)
    remote_rpc_url = load_env("REMOTE_RPC_URL", masked=True, required=True)

    ExceptionHandler.initialize(config.get("fail_on_bytecode_comparison_error", True))

    return local_rpc_url, remote_rpc_url


def process_config(
    path: str,
    hardhat_config_path: str,
    recursive_parsing: bool,
    unify_formatting: bool,
    enable_binary_comparison: bool,
    cache_explorer: bool,
    cache_github: bool,
    skip_user_input: bool = False,
):
    """
    Process a config file and run comparisons.

    Returns:
        dict: Summary statistics with keys:
            - 'source_stats': list of per-contract source statistics
            - 'bytecode_stats': list of per-contract bytecode results
            - 'config_path': path to the config file
    """
    # Reset exception handler to default before each config
    ExceptionHandler.initialize(True)

    logger.info(f"Loading config {path}...")
    config = load_config(path)

    # Load tokens and validate
    explorer_token = _load_explorer_token(config)
    github_api_token = _validate_github_token()

    # Setup binary comparison if enabled
    local_rpc_url = None
    remote_rpc_url = None
    if enable_binary_comparison:
        local_rpc_url, remote_rpc_url = _setup_binary_comparison(config)

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

            hardhat.start(
                hardhat_config_path,
                local_rpc_url,
                remote_rpc_url,
                remote_chain_id,
            )
            logger.divider()
            logger.info("Getting local chain ID and deployer account...")
            deployer_account = get_account(local_rpc_url)
            local_chain_id = get_chain_id(local_rpc_url)

            logger.okay("Local chain ID", local_chain_id)

            if remote_chain_id != local_chain_id:
                raise ValueError(
                    f"Remote chain ID {remote_chain_id} does not match local chain ID {local_chain_id}"
                )

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
                        unify_formatting,
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
                            deployer_account,
                            local_rpc_url,
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

    finally:
        if enable_binary_comparison:
            hardhat.stop()

    return {
        "source_stats": source_stats,
        "bytecode_stats": bytecode_stats,
        "config_path": path,
    }


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", "-V", action="store_true", help="Display version information"
    )
    parser.add_argument(
        "path", nargs="?", default=None, help="Path to config or directory with configs"
    )
    parser.add_argument(
        "--hardhat-path",
        default=DEFAULT_HARDHAT_CONFIG_PATH,
        help="Path to Hardhat config",
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
        "--prettify",
        "-P",
        help="Unify formatting by prettier before comparing",
        action="store_true",
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
    return parser.parse_args()


def print_final_summary(
    all_results: list[dict],
    enable_source_comparison: bool,
    enable_binary_comparison: bool,
) -> None:
    """
    Print a final summary of all comparisons performed.

    Args:
        all_results: List of dictionaries with 'source_stats' and 'bytecode_stats'
        enable_source_comparison: Whether source comparison was enabled
        enable_binary_comparison: Whether bytecode comparison was enabled
    """
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
            logger.info("Contracts with source code differences:")
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
            logger.info("Contracts with bytecode differences:")
            for contract in bytecode_mismatches:
                logger.warn(f"  • {contract['name']} ({contract['address']})")

    logger.divider()
    logger.info("=" * 80)


def main() -> None:
    """Main entry point for the diffyscan application."""
    load_dotenv()
    args = parse_arguments()
    skip_user_input = args.yes
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
            args.prettify,
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
    """
    Determines if the contract source code is in Standard JSON format.

    Etherscan provides contract source code in two formats:
    1. Standard JSON - source files are organized in directories with dependencies,
       each file has proper path and .sol extension
    2. Single file - contract code is provided as a single string without dependencies,
       the file identifier is just a contract name without path or extension

    Examples:
        Single file format (no dependencies):
            source_files = dict_items([
                ('Contract', {'content': 'contract Contract { ... }'})
            ])

        Standard JSON format (with dependencies):
            source_files = dict_items([
                ('src/Contract.sol', {'content': 'contract Contract { ... }'}),
                ('src/Dependency.sol', {'content': 'contract Dependency { ... }'})
            ])

    Args:
        source_files: Dictionary of contract source files from Etherscan

    Returns:
        bool: True if the contract is in Standard JSON format, False if it's a single file
    """
    files = list(source_files)
    if len(files) != 1:
        return True

    filename, _ = files[0]
    return ".sol" in filename or "/" in filename


if __name__ == "__main__":
    main()
