import difflib
import sys
import time
import argparse
import os
import subprocess
import tempfile
import shutil
 
from utils.common import load_config, load_env
from utils.constants import DIFFS_DIR, START_TIME, DEFAULT_CONFIG_PATH
from utils.explorer import get_contract_from_explorer
from utils.github import get_file_from_github, get_file_from_github_recursive, resolve_dep
from utils.helpers import create_dirs
from utils.logger import logger
from utils.binary_verifier import *

__version__ = "0.0.0"


g_skip_user_input: bool = False

def prettify_solidity(solidity_contract_content: str):
    github_file_name = os.path.join(tempfile.gettempdir(), "9B91E897-EA51-4FCC-8DAF-FCFF135A6963.sol")
    with open(github_file_name, "w") as fp:
        fp.write(solidity_contract_content)
    prettier_return_code = subprocess.call(
        ["npx", "prettier", "--plugin=prettier-plugin-solidity", "--write", github_file_name],
        stdout=subprocess.DEVNULL)
    if prettier_return_code != 0:
        logger.error("Prettier/npx subprocess failed (see the error above)")
        sys.exit()
    with open(github_file_name, "r") as fp:
        return fp.read()

def run_binary_diff(contract_address, code):
    logger.info(f'Started binary checking')
    bytecode_from_etherscan, immutables = get_bytecode_from_etherscan(code)

    bytecode_from_blockchain = get_bytecode_from_blockchain(contract_address)
    
    match(bytecode_from_blockchain, bytecode_from_etherscan, immutables)

def run_source_diff(contract_address_from_config, contract_code, config, github_api_token, recursive_parsing=False, prettify=False):
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

    source_files = contract_code["solcInput"].items() if not "sources" in contract_code["solcInput"] else contract_code["solcInput"]["sources"].items()
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
            github_file = get_file_from_github_recursive(github_api_token, repo, path_to_file, dep_name)
        else:
            github_file = get_file_from_github(github_api_token, repo, path_to_file, dep_name)

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
        diff_report_filename = f"{DIFFS_DIR}/{contract_address_from_config}/{filename}.html"

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

def process_config(path: str, recursive_parsing: bool, unify_formatting: bool, binary_check: bool, autoclean: bool):
    logger.info(f"Loading config {path}...")
    config = load_config(path)

    github_api_token = load_env("GITHUB_API_TOKEN", masked=True)
    explorer_token = None
    if "explorer_token_env_var" in config:
        explorer_token = load_env(config["explorer_token_env_var"], masked=True, required=False)

    contracts = config["contracts"]
    for contract_address, contract_name in contracts.items():
        contract_code = get_contract_from_explorer(explorer_token, config["explorer_hostname"], contract_address, contract_name)
        run_source_diff(contract_address, contract_code, config, github_api_token, recursive_parsing, unify_formatting)
        if (binary_check):
            run_binary_diff(contract_address, contract_code)
    
    if (autoclean):
        builds_dir_path = os.getenv('SOLC_DIR', 'solc')
        shutil.rmtree(builds_dir_path)
        logger.okay(f'{builds_dir_path} deleted')

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", "-V", action="store_true", help="Display version information")
    parser.add_argument("path", nargs="?", default=None, help="Path to config or directory with configs")
    parser.add_argument("--yes", "-y", help="If set don't ask for input before validating each contract", action="store_true")
    parser.add_argument(
        "--support-brownie",
        help="Support recursive retrieving for contracts. It may be useful for contracts whose sources have been verified by the brownie tooling, which automatically replaces relative paths to contracts in imports with plain contract names.",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument("--prettify", "-p", help="Unify formatting by prettier before comparing", action="store_true")
    parser.add_argument("--binary-check", "-binary", help="Match contracts by binaries such as verify-bytecode.ts", default=True)
    parser.add_argument("--autoclean", "-clean", help="Autoclean build dir after work", default=True)
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
        process_config(DEFAULT_CONFIG_PATH, args.support_brownie, args.prettify, args.binary_check, args.autoclean)
    elif os.path.isfile(args.path):
        process_config(args.path, args.support_brownie, args.prettify, args.binary_check, args.autoclean)
    elif os.path.isdir(args.path):
        for filename in os.listdir(args.path):
            config_path = os.path.join(args.path, filename)
            if os.path.isfile(config_path):
                process_config(config_path, args.support_brownie, args.prettify, args.binary_check, args.autoclean)
    else:
        logger.error(f"Specified config path {args.path} not found")
        sys.exit(1)

    execution_time = time.time() - START_TIME

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)


if __name__ == "__main__":
    main()
