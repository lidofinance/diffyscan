import difflib
import sys
import time
import argparse
import os
import traceback

from .utils.common import load_config, load_env, prettify_solidity
from .utils.constants import (
    DIFFS_DIR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_HARDHAT_CONFIG_PATH,
    START_TIME,
)
from .utils.explorer import (
    get_contract_from_explorer,
    compile_contract_from_explorer,
    parse_compiled_contract,
    get_explorer_hostname,
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
from .utils.node_handler import get_bytecode_from_node, get_account, deploy_contract
from .utils.calldata import get_calldata
from .utils.custom_exceptions import ExceptionHandler, BaseCustomException

__version__ = "0.0.0"


g_skip_user_input: bool = False


def run_bytecode_diff(
    contract_address_from_config,
    contract_name_from_config,
    contract_source_code,
    config,
    deployer_account,
    local_rpc_url,
    remote_rpc_url,
):
    address_name = f"{contract_address_from_config} : {contract_name_from_config}"
    logger.divider()
    logger.info(f"Binary bytecode comparison started for {address_name}")
    target_compiled_contract = compile_contract_from_explorer(contract_source_code)

    contract_creation_code, local_compiled_bytecode, immutables = (
        parse_compiled_contract(target_compiled_contract)
    )

    remote_deployed_bytecode = get_bytecode_from_node(
        contract_address_from_config, remote_rpc_url
    )

    is_fully_matched = local_compiled_bytecode == remote_deployed_bytecode

    if is_fully_matched:
        logger.okay(f"Bytecodes are fully matched")
        return

    logger.info(f"Automated match hasn't worked out")

    calldata = get_calldata(
        contract_address_from_config,
        target_compiled_contract,
        config["bytecode_comparison"],
    )

    contract_creation_code += calldata

    local_contract_address = deploy_contract(
        local_rpc_url, deployer_account, contract_creation_code
    )

    local_deployed_bytecode = get_bytecode_from_node(
        local_contract_address, local_rpc_url
    )

    is_fully_matched = local_deployed_bytecode == remote_deployed_bytecode

    if is_fully_matched:
        logger.okay(f"Bytecodes are fully matched")
        return

    deep_match_bytecode(
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
):
    explorer_hostname = get_explorer_hostname(config)
    logger.divider()
    logger.okay("Contract", contract_address_from_config)
    logger.okay("Blockchain explorer Hostname", explorer_hostname)
    logger.okay("Repo", config["github_repo"]["url"])
    logger.okay("Repo commit", config["github_repo"]["commit"])
    logger.okay("Repo relative root", config["github_repo"]["relative_root"])

    logger.divider()

    logger.info(
        f"Fetching source code from blockchain explorer {explorer_hostname} ..."
    )

    source_files = (
        contract_code["solcInput"].items()
        if not "sources" in contract_code["solcInput"]
        else contract_code["solcInput"]["sources"].items()
    )
    files_count = len(source_files)
    logger.okay("Contract", contract_code["name"])
    logger.okay("Files", files_count)

    if not g_skip_user_input:
        input("Press Enter to proceed...")
        logger.divider()

    logger.info("Diffing...")

    report = []

    for index, (path_to_file, source_code) in enumerate(source_files):
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
            logger.error("File not found", path_to_file)
            sys.exit()

        file_found = bool(repo)

        if recursive_parsing:
            github_file = get_file_from_github_recursive(
                github_api_token, repo, path_to_file, dep_name
            )
        else:
            github_file = get_file_from_github(
                github_api_token, repo, path_to_file, dep_name
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

    logger.report_table(report)


def process_config(
    path: str,
    hardhat_config_path: str,
    recursive_parsing: bool,
    unify_formatting: bool,
    enable_binary_comparison: bool,
):
    logger.info(f"Loading config {path}...")
    config = load_config(path)

    explorer_token = None
    if "explorer_token_env_var" in config:
        explorer_token = load_env(
            config["explorer_token_env_var"], masked=True, required=False
        )
    if explorer_token is None:
        logger.warn(
            f'Failed to find an explorer token in the config ("explorer_token_env_var")'
        )
        explorer_token = os.getenv("ETHERSCAN_EXPLORER_TOKEN", default=None)
    if explorer_token is None:
        logger.warn(
            f'Failed to find explorer token in env ("ETHERSCAN_EXPLORER_TOKEN")'
        )

    github_api_token = os.getenv("GITHUB_API_TOKEN", "")
    if not github_api_token:
        raise ValueError("GITHUB_API_TOKEN variable is not set")

    if enable_binary_comparison:
        if "bytecode_comparison" not in config:
            raise ValueError(f'Failed to find "bytecode_comparison" section in config')

        local_rpc_url = load_env("LOCAL_RPC_URL", masked=False, required=True)
        remote_rpc_url = load_env("REMOTE_RPC_URL", masked=True, required=True)

        ExceptionHandler.initialize(config["fail_on_comparison_error"])

    try:
        if enable_binary_comparison:
            hardhat.start(
                hardhat_config_path,
                local_rpc_url,
                remote_rpc_url,
            )
            deployer_account = get_account(local_rpc_url)

        for contract_address, contract_name in config["contracts"].items():
            try:
                contract_code = get_contract_from_explorer(
                    explorer_token,
                    get_explorer_hostname(config),
                    contract_address,
                    contract_name,
                )
                run_source_diff(
                    contract_address,
                    contract_code,
                    config,
                    github_api_token,
                    recursive_parsing,
                    unify_formatting,
                )
                if enable_binary_comparison:
                    run_bytecode_diff(
                        contract_address,
                        contract_name,
                        contract_code,
                        config,
                        deployer_account,
                        local_rpc_url,
                        remote_rpc_url,
                    )
            except BaseCustomException as custom_exc:
                ExceptionHandler.raise_exception_or_log(custom_exc)
                traceback.print_exc()
    except KeyboardInterrupt:
        logger.info(f"Keyboard interrupt by user")

    finally:
        if enable_binary_comparison:
            hardhat.stop()


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", "-V", action="store_true", help="Display version information"
    )
    parser.add_argument(
        "path", nargs="?", default=None, help="Path to config or directory with configs"
    )
    parser.add_argument(
        "hardhat_path", nargs="?", default=None, help="Path to Hardhat config"
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
        "--enable-binary-comparison",
        "-B",
        help="Enable binary bytecode comparison",
        action="store_true",
    )
    return parser.parse_args()


def main():
    global g_skip_user_input

    args = parse_arguments()
    g_skip_user_input = args.yes
    if args.version:
        print(f"Diffyscan {__version__}")
        return
    logger.info("Welcome to Diffyscan!")
    logger.divider()
    hardhat_config_path = (
        DEFAULT_HARDHAT_CONFIG_PATH if args.hardhat_path is None else args.hardhat_path
    )
    if args.path is None:
        process_config(
            DEFAULT_CONFIG_PATH,
            hardhat_config_path,
            args.support_brownie,
            args.prettify,
            args.enable_binary_comparison,
        )
    elif os.path.isfile(args.path):
        process_config(
            args.path,
            hardhat_config_path,
            args.support_brownie,
            args.prettify,
            args.enable_binary_comparison,
        )
    elif os.path.isdir(args.path):
        for filename in os.listdir(args.path):
            config_path = os.path.join(
                args.path, filename, args.enable_binary_comparison
            )
            if os.path.isfile(config_path):
                process_config(
                    config_path,
                    hardhat_config_path,
                    args.support_brownie,
                    args.prettify,
                    args.enable_binary_comparison,
                )
    else:
        logger.error(f"Specified config path {args.path} not found")
        sys.exit(1)

    execution_time = time.time() - START_TIME

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)


if __name__ == "__main__":
    main()
