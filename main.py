import difflib
import sys
import time

from utils.common import load_config, load_env
from utils.constants import CONTRACTS_DIR, DIFFS_DIR, DIGEST_DIR
from utils.etherscan import get_contract_from_etherscan
from utils.github import get_file_from_github
from utils.helpers import create_dirs, remove_directory
from utils.logger import logger


def run_diff(config, name, address, etherscan_api_token, github_api_token):
    start_time = time.time()
    logger.divider()
    logger.okay("Contract", address)
    logger.okay("Network", config["network"])
    logger.okay("Repo", config["github_repo"])

    logger.divider()

    logger.info("Fetching source code from Etherscan...")
    contract_name, source_files = get_contract_from_etherscan(
        token=etherscan_api_token,
        network=config["network"],
        contract=address,
    )

    if (contract_name != name):
        logger.error("Contract name in config does not match with etherscan", f"{address}: {name} != {contract_name}")
        sys.exit(1)

    files_count = len(source_files)
    logger.okay("Contract", contract_name)
    logger.okay("Files", files_count)

    input("Press Enter to proceed...")
    logger.divider()
    logger.info("Diffing...")

    report = []

    for index, (filepath, source_code) in enumerate(source_files):
        file_number = index + 1
        split_filepath = filepath.split("/")
        origin = split_filepath[0]
        filename = split_filepath[-1]

        logger.update_info(f"File {file_number} / { files_count}", filename)

        repo = None

        if origin == CONTRACTS_DIR:
            repo = config["github_repo"]
        elif (
            "dependencies" in config
            and origin in config["dependencies"].keys()
            and config["dependencies"].get(origin) != ""
        ):
            repo = config["dependencies"].get(origin)
        else:
            logger.warn(f"No file in github repo for: {filepath}")
            logger.divider()

        diff_report_filename = None
        diffs_count = None

        if repo:
            github_file = get_file_from_github(github_api_token, repo, filepath)

            github_lines = github_file.splitlines()
            etherscan_lines = source_code["content"].splitlines()

            diff_html = difflib.HtmlDiff().make_file(github_lines, etherscan_lines)
            diff_report_filename = f"{DIFFS_DIR}/{filename}.html"

            create_dirs(diff_report_filename)
            with open(diff_report_filename, "w") as f:
                f.write(diff_html)

            diffs = difflib.unified_diff(github_lines, etherscan_lines)
            diffs_count = len(list(diffs))

        file_found = bool(repo)

        report_data = [
            file_number,
            filename,
            file_found,
            diffs_count,
            origin,
            diff_report_filename,
        ]

        report.append(report_data)

    execution_time = time.time() - start_time

    logger.okay(f"Done in {round(execution_time, 3)}s ✨" + " " * 100)

    logger.divider()

    files_found = len([row for row in report if row[2]])
    logger.info(f"Files found: {files_found} / {files_count}")

    identical_files = len([row for row in report if row[3] == 0])
    logger.info(f"Identical files: {identical_files} / {files_found}")

    logger.report_table(report)


def main():
    logger.info("Welcome to Diffyscan!")
    logger.divider()

    logger.info("Loading API tokens...")
    etherscan_api_token = load_env("ETHERSCAN_API_TOKEN", masked=True)
    github_api_token = load_env("GITHUB_API_TOKEN", masked=True)
    contract_address = load_env("CONTRACT_ADDRESS", required=False)
    contract_name = load_env("CONTRACT_NAME", required=False)

    logger.divider()

    logger.info("Removing artifacts from the previous run...")
    remove_directory(DIGEST_DIR)

    logger.info("Loading config...")
    config = load_config()

    if contract_address is not None:
        logger.info(f"Running diff for a single contract {contract_name} ...")
        run_diff(config, contract_name, contract_address, etherscan_api_token, github_api_token)
    else:
        contracts = config["contracts"]
        logger.info(f"Running diff for contracts from config {contracts}...")
        for name, address in config["contracts"].items():
            run_diff(config, name, address, etherscan_api_token, github_api_token)


if __name__ == "__main__":
    main()
