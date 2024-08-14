import difflib
import sys
import time
import argparse
import os

from .utils.common import load_config, load_env, prettify_solidity
from .utils.constants import *
from .utils.explorer import (
    get_contract_from_explorer,
    compile_contract_from_explorer,
    get_contract_creation_code,
)
from .utils.github import (
    get_file_from_github,
    get_file_from_github_recursive,
    resolve_dep,
)
from .utils.helpers import create_dirs
from .utils.logger import logger
from .utils.binary_verifier import *
from .utils.hardhat import hardhat
from .utils.node_handler import *
from .utils.calldata import get_calldata

__version__ = "0.0.0"


g_skip_user_input: bool = False


def run_bytecode_diff(
    contract_address_from_config,
    contract_name_from_config,
    contract_source_code,
    config,
    deployer_account,
):
    address_name = f"{contract_address_from_config} : {contract_name_from_config}"
    logger.divider()
    logger.info(f"Binary bytecode comparion started for {address_name}")

    if deployer_account is None:
        raise ValueError(f"The deployer account isn't set)")

    target_compiled_contract = compile_contract_from_explorer(contract_source_code)

    contract_creation_code, immutables = get_contract_creation_code(
        target_compiled_contract
    )
    skip_deploy_error = config["binary_checking"]["skip_deploy_error"]

    calldata, text_error = get_calldata(
        contract_address_from_config,
        target_compiled_contract,
        config["binary_checking"],
    )
    if calldata is not None:
        contract_creation_code += calldata
    elif text_error is not None:
        skip_or_raise(skip_deploy_error, text_error)
        return

    local_RPC_URL = config["binary_checking"]["local_RPC_URL"]
    local_contract_address, text_reason = deploy_contract(
        local_RPC_URL, deployer_account, contract_creation_code
    )

    if local_contract_address is None:
        skip_or_raise(
            skip_deploy_error,
            f"Failed to deploy bytecode to {local_RPC_URL} {text_reason}",
        )
        return

    local_deployed_bytecode = get_bytecode_from_node(
        local_contract_address, local_RPC_URL
    )
    if local_deployed_bytecode is None:
        skip_or_raise(
            skip_deploy_error,
            text_error=f"Failed to receive bytecode from {local_RPC_URL})",
        )
        return

    remote_RPC_URL = config["binary_checking"]["remote_RPC_URL"]
    remote_deployed_bytecode = get_bytecode_from_node(
        contract_address_from_config, remote_RPC_URL
    )
    if remote_deployed_bytecode is None:
        skip_or_raise(
            skip_deploy_error,
            f"Failed to receive bytecode from {remote_RPC_URL})",
        )
        return

    to_match(
        local_deployed_bytecode,
        remote_deployed_bytecode,
        immutables,
    )


def raise_error_or_log(message: str, raise_exception: bool = True):
    if skip_deploy_error:
        logger.error(text_error)
    else:
        raise ValueError(text_error)


def run_source_diff(
    contract_address_from_config,
    contract_code,
    config,
    github_api_token,
    recursive_parsing=False,
    prettify=False,
):
    logger.divider()
    logger.okay("Contract", contract_address_from_config)
    logger.okay("Blockchain explorer Hostname", config["explorer_hostname"])
    logger.okay("Repo", config["github_repo"]["url"])
    logger.okay("Repo commit", config["github_repo"]["commit"])
    logger.okay("Repo relative root", config["github_repo"]["relative_root"])

    logger.divider()

    logger.info(
        f"Fetching source code from blockchain explorer {config['explorer_hostname']} ..."
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


def process_config(path: str, recursive_parsing: bool, unify_formatting: bool):
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
        raise ValueError(
            f'Failed to find explorer token in env ("ETHERSCAN_EXPLORER_TOKEN")'
        )

    contracts = config["contracts"]
    binary_check = (
        "binary_checking" in config
        and "enable" in config["binary_checking"]
        and config["binary_checking"]["enable"]
    )

    try:
        if binary_check:
            hardhat.start(path, config["binary_checking"])
            deployer_account = get_account(config["binary_checking"]["local_RPC_URL"])
        else:
            logger.warn("Binary checking not activated")

        for contract_address, contract_name in contracts.items():
            contract_code = get_contract_from_explorer(
                explorer_token,
                config["explorer_hostname"],
                contract_address,
                contract_name,
            )
            run_source_diff(
                contract_address,
                contract_code,
                config,
                GITHUB_API_TOKEN,
                recursive_parsing,
                unify_formatting,
            )
            if binary_check:
                run_binary_diff(
                    contract_address,
                    contract_name,
                    contract_code,
                    config,
                    deployer_account,
                )
    except KeyboardInterrupt:
        logger.info(f"Keyboard interrupt by user")
    finally:
        if binary_check:
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
        "--yes",
        "-y",
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
        "-p",
        help="Unify formatting by prettier before comparing",
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
    if args.path is None:
        process_config(DEFAULT_CONFIG_PATH, args.support_brownie, args.prettify)
    elif os.path.isfile(args.path):
        process_config(args.path, args.support_brownie, args.prettify)
    elif os.path.isdir(args.path):
        for filename in os.listdir(args.path):
            config_path = os.path.join(args.path, filename)
            if os.path.isfile(config_path):
                process_config(config_path, args.support_brownie, args.prettify)
    else:
        logger.error(f"Specified config path {args.path} not found")
        sys.exit(1)

    execution_time = time.time() - START_TIME

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)


if __name__ == "__main__":
    main()
