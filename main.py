import difflib
import time

import termtables

from utils.common import add_dependency_to_config, load_config, load_env
from utils.constants import CONTRACTS_DIR, DIFFS_DIR, DIGEST_DIR
from utils.etherscan import get_contract_from_etherscan
from utils.github import get_file_from_github
from utils.helpers import create_dirs, remove_directory
from utils.logger import GREEN, RED, YELLOW, logger


def main():
    start_time = time.time()

    logger.info("Welcome to Diffyscan!")
    logger.divider()

    logger.info("Loading API tokens...")
    etherscan_api_token = load_env("ETHERSCAN_API_TOKEN", masked=True)
    github_api_token = load_env("GITHUB_API_TOKEN", masked=True)

    logger.divider()

    logger.info("Removing artifacts from the previous run...")
    remove_directory(DIGEST_DIR)

    logger.info("Loading config...")
    config = load_config()

    logger.okay("Contract", config["contract"])
    logger.okay("Network", config["network"])
    logger.okay("Repo", config["github_repo"])

    logger.divider()

    logger.info("Fetching source code from Etherscan...")
    contract_name, source_files = get_contract_from_etherscan(
        token=etherscan_api_token,
        network=config["network"],
        contract=config["contract"],
    )

    files_count = len(source_files)
    logger.okay("Contract", contract_name)
    logger.okay("Files", files_count)

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
            origin in config["dependencies"].keys()
            and config["dependencies"].get(origin) != ""
        ):
            repo = config["dependencies"].get(origin)
        else:
            add_dependency_to_config(origin)
            logger.log(f"Dependency not found: {origin}")

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


if __name__ == "__main__":
    main()
