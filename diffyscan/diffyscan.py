import argparse
import difflib
import json
import os
import sys
import time
import traceback

from dotenv import load_dotenv

from . import __version__
from .utils.allowed_diffs import (
    build_bytecode_suggestion_entry,
    build_effective_allowed_diffs,
    build_source_suggestion_entry,
    evaluate_bytecode_rules,
    evaluate_source_rules,
    normalize_source_hunks,
    render_suggestion_snippet,
    summarize_bytecode_uncovered,
    summarize_source_uncovered_hunks,
)
from .utils.binary_verifier import analyze_bytecode_diff, log_bytecode_diff_analysis
from .utils.calldata import get_calldata
from .utils.common import load_config, load_env
from .utils.constants import DIFFS_DIR, START_TIME
from .utils.custom_exceptions import (
    BaseCustomException,
    CompileError,
    ExceptionHandler,
)
from .utils.explorer import (
    compile_contract_from_explorer,
    get_contract_from_explorer,
    get_explorer_chain_id,
    get_explorer_hostname,
    get_solc_sources,
    merge_libraries,
    parse_compiled_contract,
)
from .utils.github import (
    get_file_from_github,
    get_file_from_github_recursive,
    resolve_dep,
)
from .utils.helpers import create_dirs
from .utils.logger import logger
from .utils.node_handler import (
    get_bytecode_from_node,
    get_chain_id,
    simulate_deployment,
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

    assert repo is not None
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
    allowed_rules,
):
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

    if local_compiled_bytecode == remote_deployed_bytecode:
        logger.okay("Bytecodes fully match")
        return {
            "contract_address": contract_address_from_config,
            "contract_name": contract_name_from_config,
            "status": "exact",
            "match": True,
            "has_diff": False,
            "matched_rule": None,
            "matched_facets": [],
            "suggestion_entry": None,
        }

    logger.info("Static bytecodes do not match, simulating constructor via eth_call")

    calldata = get_calldata(
        contract_address_from_config,
        target_compiled_contract,
        config.get("bytecode_comparison"),
        explorer_constructor_arguments,
    )
    deployment_call_data = _append_calldata(contract_creation_code, calldata)
    local_deployed_bytecode = simulate_deployment(deployment_call_data, remote_rpc_url)

    if local_deployed_bytecode == remote_deployed_bytecode:
        logger.okay("Bytecodes fully match")
        return {
            "contract_address": contract_address_from_config,
            "contract_name": contract_name_from_config,
            "status": "exact",
            "match": True,
            "has_diff": False,
            "matched_rule": None,
            "matched_facets": [],
            "suggestion_entry": None,
        }

    base_analysis = analyze_bytecode_diff(
        local_deployed_bytecode,
        remote_deployed_bytecode,
        immutables,
    )
    analysis_cache: dict[str, dict] = {}

    def analysis_provider(rule: dict) -> dict:
        if "constructor_args" not in rule and "constructor_calldata" not in rule:
            return base_analysis

        cache_key = _constructor_rule_cache_key(rule)
        if cache_key in analysis_cache:
            return analysis_cache[cache_key]

        override_binary_config = _build_constructor_override_binary_config(
            contract_address_from_config,
            rule,
        )
        override_calldata = get_calldata(
            contract_address_from_config,
            target_compiled_contract,
            override_binary_config,
            None,
        )
        override_call_data = _append_calldata(
            contract_creation_code,
            override_calldata,
        )
        override_deployed_bytecode = simulate_deployment(
            override_call_data,
            remote_rpc_url,
        )
        analysis_cache[cache_key] = analyze_bytecode_diff(
            override_deployed_bytecode,
            remote_deployed_bytecode,
            immutables,
        )
        return analysis_cache[cache_key]

    evaluation = evaluate_bytecode_rules(
        base_analysis, allowed_rules, analysis_provider
    )

    suggestion_entry = None
    if evaluation["status"] == "allowed":
        _log_allowed_diff("bytecode", address_name, evaluation)
    else:
        best_analysis = evaluation["best_analysis"]
        log_bytecode_diff_analysis(best_analysis)
        _log_uncovered_bytecode_diff(best_analysis)
        suggestion_entry = build_bytecode_suggestion_entry(best_analysis)

    return {
        "contract_address": contract_address_from_config,
        "contract_name": contract_name_from_config,
        "status": evaluation["status"],
        "match": evaluation["status"] != "failed",
        "has_diff": True,
        "matched_rule": evaluation["matched_rule"],
        "matched_facets": evaluation["matched_facets"],
        "suggestion_entry": suggestion_entry,
    }


def run_source_diff(
    contract_address_from_config,
    contract_code,
    config,
    github_api_token,
    allowed_rules,
    recursive_parsing=False,
    cache_github=False,
    skip_user_input=False,
):
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

    file_results = []
    report_table = []

    for file_number, (path_to_file, source_code) in enumerate(
        source_files.items(), start=1
    ):
        source_path = path_to_file if standard_json_format else f"{path_to_file}.sol"
        filename = source_path.split("/")[-1]
        origin = source_path.split("/")[0]

        logger.update_info(f"File {file_number} / {files_count}", filename)

        github_file = _fetch_github_source(
            source_path,
            config,
            github_api_token,
            recursive_parsing,
            cache_github,
        )

        file_found = bool(github_file)
        github_content = github_file or ""
        explorer_content = source_code["content"]

        github_lines = github_content.splitlines()
        explorer_lines = explorer_content.splitlines()
        diff_report_filename = (
            f"{DIFFS_DIR}/{contract_address_from_config}/{filename}.html"
        )
        diff_html = difflib.HtmlDiff().make_file(github_lines, explorer_lines)
        create_dirs(diff_report_filename)
        with open(diff_report_filename, "w", encoding="utf-8") as report_file:
            report_file.write(diff_html)

        diff_lines = list(difflib.unified_diff(github_lines, explorer_lines))
        hunks = normalize_source_hunks(github_lines, explorer_lines)

        file_result = {
            "path": source_path,
            "filename": filename,
            "origin": origin,
            "file_found": file_found,
            "diff_report_filename": diff_report_filename,
            "diffs_count": len(diff_lines),
            "hunks": hunks,
            "github_line_count": len(github_lines),
            "explorer_line_count": len(explorer_lines),
        }
        file_results.append(file_result)
        report_table.append(
            [
                file_number,
                filename,
                file_found,
                len(diff_lines),
                origin,
                diff_report_filename,
            ]
        )

    logger.divider()

    files_found = sum(bool(file_result["file_found"]) for file_result in file_results)
    logger.info(f"Files found: {files_found} / {files_count}")

    identical_files = sum(
        bool(file_result["file_found"] and not file_result["hunks"])
        for file_result in file_results
    )
    logger.info(f"Identical files: {identical_files} / {files_found}")

    files_with_diffs = sum(bool(file_result["hunks"]) for file_result in file_results)
    logger.report_table(report_table)

    source_result = {
        "files_count": files_count,
        "files_found": files_found,
        "identical_files": identical_files,
        "files_with_diffs": files_with_diffs,
        "contract_address": contract_address_from_config,
        "contract_name": contract_code["name"],
        "files": file_results,
        "has_diff": files_with_diffs > 0,
    }

    evaluation = evaluate_source_rules(source_result, allowed_rules)
    suggestion_entry = None

    if evaluation["status"] == "allowed":
        _log_allowed_diff("source", contract_address_from_config, evaluation)
    elif evaluation["status"] == "failed":
        _log_uncovered_source_diff(source_result)
        suggestion_entry = build_source_suggestion_entry(source_result)

    source_result.update(
        {
            "status": evaluation["status"],
            "matched_rule": evaluation["matched_rule"],
            "matched_facets": evaluation["matched_facets"],
            "suggestion_entry": suggestion_entry,
        }
    )
    return source_result


def _load_explorer_token(config: dict) -> str | None:
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
    remote_rpc_url = load_env("REMOTE_RPC_URL", masked=True, required=True)
    assert remote_rpc_url is not None  # guaranteed by required=True
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
    config: dict,
    hardhat_config_path: str | None,
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
    cli_allowed_source_diffs: list[str] | None,
    cli_allowed_bytecode_diffs: list[str] | None,
    skip_user_input: bool = False,
):
    ExceptionHandler.initialize(True)

    logger.info(f"Loading config {path}...")
    config: dict = load_config(path)  # type: ignore[assignment]
    _warn_deprecated_hardhat_settings(config, hardhat_config_path)
    effective_allowed_diffs = build_effective_allowed_diffs(
        config,
        cli_allowed_source_diffs,
        cli_allowed_bytecode_diffs,
    )

    explorer_token = _load_explorer_token(config)
    github_api_token = load_env("GITHUB_API_TOKEN", masked=True, required=True)

    remote_rpc_url = None
    if enable_binary_comparison:
        remote_rpc_url = _setup_binary_comparison(config)

    enable_source_comparison = config.get("source_comparison", True)
    if not enable_source_comparison:
        logger.warn(
            f'Source code comparison is disabled in {path}. To enable, set "source_comparison": true in the config'
        )

    source_stats = []
    bytecode_stats = []

    try:
        if enable_binary_comparison:
            assert remote_rpc_url is not None
            logger.info("Getting remote chain ID...")
            remote_chain_id = get_chain_id(remote_rpc_url)
            logger.okay("Remote chain ID", remote_chain_id)

        explorer_hostname = get_explorer_hostname(config)
        assert explorer_hostname is not None, "explorer_hostname is required"

        for contract_address, contract_name in config["contracts"].items():
            try:
                contract_code = get_contract_from_explorer(
                    explorer_token,
                    explorer_hostname,
                    contract_address,
                    contract_name,
                    get_explorer_chain_id(config),
                    cache_explorer,
                )

                address_key = contract_address.lower()
                source_rules = effective_allowed_diffs["source"].get(address_key, [])
                bytecode_rules = effective_allowed_diffs["bytecode"].get(
                    address_key, []
                )

                if enable_source_comparison:
                    source_result = run_source_diff(
                        contract_address,
                        contract_code,
                        config,
                        github_api_token,
                        source_rules,
                        recursive_parsing,
                        cache_github,
                        skip_user_input,
                    )
                    source_stats.append(source_result)

                if enable_binary_comparison:
                    try:
                        bytecode_result = run_bytecode_diff(
                            contract_address,
                            contract_name,
                            contract_code,
                            config,
                            github_api_token,
                            recursive_parsing,
                            cache_github,
                            remote_rpc_url,
                            bytecode_rules,
                        )
                        bytecode_stats.append(bytecode_result)
                    except BaseCustomException as exc:
                        logger.error(str(exc))
                        bytecode_stats.append(
                            {
                                "contract_address": contract_address,
                                "contract_name": contract_name,
                                "status": "failed",
                                "match": False,
                                "has_diff": True,
                                "matched_rule": None,
                                "matched_facets": [],
                                "suggestion_entry": None,
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
        "--version",
        "-V",
        action="store_true",
        help="Display version information",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to config or directory with configs",
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
        _print_source_summary(all_results)

    if enable_binary_comparison:
        _print_bytecode_summary(all_results)

    _print_allowlist_suggestions(all_results)

    logger.divider()
    logger.info("=" * 80)


def main() -> None:
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

    enable_binary_comparison = not args.skip_binary_comparison
    config_paths = []
    supported_extensions = (".json", ".yaml", ".yml")

    if args.path is None:
        config_path = next(
            (
                candidate
                for candidate in ("config.json", "config.yaml", "config.yml")
                if os.path.isfile(candidate)
            ),
            None,
        )
        if config_path is None:
            error_msg = (
                "No config file found. Create config.json or config.yaml in the current "
                "directory, or specify a path with --path."
            )
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

    all_results = []
    for config_path in config_paths:
        result = process_config(
            config_path,
            args.hardhat_path,
            args.support_brownie,
            enable_binary_comparison,
            args.cache_explorer,
            args.cache_github,
            args.allow_source_diff,
            args.allow_bytecode_diff,
            skip_user_input,
        )
        all_results.append(result)

    execution_time = time.time() - START_TIME
    enable_source_comparison = any(result["source_stats"] for result in all_results)

    print_final_summary(all_results, enable_source_comparison, enable_binary_comparison)

    has_unallowed_diffs = any(
        stat["status"] == "failed"
        for result in all_results
        for stat in result["source_stats"] + result["bytecode_stats"]
    )

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)

    if has_unallowed_diffs:
        source_failures = sum(
            stat["status"] == "failed"
            for result in all_results
            for stat in result["source_stats"]
        )
        bytecode_failures = sum(
            stat["status"] == "failed"
            for result in all_results
            for stat in result["bytecode_stats"]
        )
        logger.error(
            "Exiting with non-zero code due to unallowed diffs",
            f"source={source_failures}, bytecode={bytecode_failures}",
        )
        sys.exit(1)

    sys.exit(0)


def is_standard_json_contract(source_files: dict) -> bool:
    keys = list(source_files)
    if len(keys) != 1:
        return True
    first_key = keys[0]
    return ".sol" in first_key or "/" in first_key


def _log_allowed_diff(diff_kind: str, contract_label: str, evaluation: dict) -> None:
    matched_rule = evaluation["matched_rule"] or {}
    facets = ", ".join(
        evaluation["matched_facets"] or _present_rule_facets(matched_rule)
    )
    logger.warn(f"Allowed {diff_kind} diff", contract_label)
    logger.warn("Matched allowlist rule", matched_rule.get("reason"))
    if facets:
        logger.okay("Matched facets", facets)
    if matched_rule.get("any"):
        logger.warn(
            "Blanket allowlist matched",
            "consider replacing it with granular allowed_diffs rules",
        )


def _log_uncovered_source_diff(source_result: dict) -> None:
    logger.warn(
        "Source diff is not covered by allowlist",
        source_result["contract_address"],
    )
    for summary in summarize_source_uncovered_hunks(source_result):
        logger.warn("Uncovered source hunk", summary)


def _log_uncovered_bytecode_diff(analysis: dict) -> None:
    for summary in summarize_bytecode_uncovered(analysis):
        logger.warn("Uncovered bytecode diff", summary)
    for observed in analysis["immutable_observations"]:
        if observed["differs"]:
            logger.warn(
                "Observed immutable value",
                f"offset={observed['offset']} value={observed['remote_value']}",
            )


def _present_rule_facets(rule: dict) -> list[str]:
    facets = []
    for field in (
        "any",
        "immutables",
        "cbor_metadata",
        "byte_ranges",
        "constructor_args",
        "constructor_calldata",
        "files",
        "line_ranges",
    ):
        value = rule.get(field)
        if value not in (None, False, [], {}):
            facets.append(field)
    return facets


def _constructor_rule_cache_key(rule: dict) -> str:
    if "constructor_calldata" in rule:
        return f"constructor_calldata:{rule['constructor_calldata']}"
    return "constructor_args:" + json.dumps(rule["constructor_args"], sort_keys=True)


def _build_constructor_override_binary_config(
    contract_address: str,
    rule: dict,
) -> dict:
    if "constructor_calldata" in rule:
        return {
            "constructor_calldata": {contract_address: rule["constructor_calldata"]}
        }
    return {"constructor_args": {contract_address: rule["constructor_args"]}}


def _print_source_summary(all_results: list[dict]) -> None:
    source_stats = [
        stat for result in all_results for stat in result.get("source_stats", [])
    ]
    total_contracts = len(source_stats)
    exact_matches = sum(stat["status"] == "exact" for stat in source_stats)
    allowed_diffs = sum(stat["status"] == "allowed" for stat in source_stats)
    failed_diffs = [stat for stat in source_stats if stat["status"] == "failed"]
    total_files_with_diffs = sum(stat["files_with_diffs"] for stat in source_stats)

    logger.divider()
    logger.info("SOURCE CODE COMPARISON SUMMARY:")
    logger.okay(f"Total contracts analyzed: {total_contracts}")
    logger.okay(f"Exact matches: {exact_matches}")
    logger.okay(f"Allowed diffs: {allowed_diffs}")
    logger.okay(f"Failures: {len(failed_diffs)}")
    logger.okay(f"Total files with non-zero diffs: {total_files_with_diffs}")

    if failed_diffs:
        logger.divider()
        logger.warn("Contracts with uncovered source code differences:")
        for stat in failed_diffs:
            logger.warn(
                f"  • {stat['contract_name']} ({stat['contract_address']}): "
                f"{stat['files_with_diffs']} file(s) with diffs"
            )


def _print_bytecode_summary(all_results: list[dict]) -> None:
    bytecode_stats = [
        stat for result in all_results for stat in result.get("bytecode_stats", [])
    ]
    total_contracts = len(bytecode_stats)
    exact_matches = sum(stat["status"] == "exact" for stat in bytecode_stats)
    allowed_diffs = sum(stat["status"] == "allowed" for stat in bytecode_stats)
    failed_diffs = [stat for stat in bytecode_stats if stat["status"] == "failed"]

    logger.divider()
    logger.info("BYTECODE COMPARISON SUMMARY:")
    logger.okay(f"Total contracts analyzed: {total_contracts}")
    logger.okay(f"Exact matches: {exact_matches}")
    logger.okay(f"Allowed diffs: {allowed_diffs}")
    logger.okay(f"Failures: {len(failed_diffs)}")

    if failed_diffs:
        logger.divider()
        logger.warn("Contracts with uncovered bytecode differences:")
        for stat in failed_diffs:
            logger.warn(f"  • {stat['contract_name']} ({stat['contract_address']})")


def _print_allowlist_suggestions(all_results: list[dict]) -> None:
    grouped: dict[str, list[dict]] = {}

    for result in all_results:
        config_path = result["config_path"]

        for diff_kind, key in (
            ("source", "source_stats"),
            ("bytecode", "bytecode_stats"),
        ):
            for stat in result[key]:
                if not stat.get("suggestion_entry"):
                    continue
                grouped.setdefault(config_path, []).append(
                    {
                        "kind": diff_kind,
                        "address": stat["contract_address"],
                        "contract_name": stat["contract_name"],
                        "entry": stat["suggestion_entry"],
                    }
                )

    if not grouped:
        return

    logger.divider()
    logger.warn("ALLOWLIST SUGGESTIONS:")
    for config_path, suggestions in grouped.items():
        logger.warn("Config", config_path)
        for suggestion in suggestions:
            logger.warn(
                f"{suggestion['kind'].capitalize()} suggestion",
                f"{suggestion['contract_name']} ({suggestion['address']})",
            )
            snippet = render_suggestion_snippet(
                config_path,
                suggestion["kind"],
                suggestion["address"],
                suggestion["entry"],
            )
            logger.info(snippet)
            logger.divider()


if __name__ == "__main__":
    main()
