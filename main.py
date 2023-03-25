import sys
import requests
import json
import base64
import time
import difflib
import os
from urllib.parse import urlparse


def main():
    # loading environment variables
    github_token = load_env("GITHUB_TOKEN")
    etherscan_token = load_env("ETHERSCAN_TOKEN")
    etherscan_network = load_env("ETHERSCAN_NETWORK", required=False)
    contract_address = load_env("CONTRACT_ADDRESS")
    repo_link = load_env("REPO_LINK")

    # fetching contract code from Etherscan
    etherscan_subdomain = "-" + etherscan_network if etherscan_network else ""
    etherscan_link = f"https://api{etherscan_subdomain}.etherscan.io/api?module=contract&action=getsourcecode&address={contract_address}&apikey={etherscan_token}"
    print(f"🔵 [INFO]: Fetching source code from {etherscan_link}")
    response = requests.get(etherscan_link)
    if response.status_code != 200:
        print("🔴 [ERROR]: Request to api.etherscan.io failed!")
        sys.exit()

    data = response.json()
    if data['message'] == "NOTOK":
        print(f"🔴 [ERROR]: Etherscan {data['result']}!")
        sys.exit()

    # transforming source code to (contract_path, {"content": "code"}) format
    contracts = json.loads(data['result'][0]["SourceCode"][1:-1])["sources"].items()

    # parsing github link to get user repo and ref (commit or branch)
    (user_slash_repo, ref) = parse_repo_link(repo_link)

    # aragon commit or branch, if aragon deps are used
    aragon_ref = None
    aragon_ref_provided = False

    # todo: add openzeppelin deps

    # keeping track for final stats
    no_diff_count = 0
    code_not_found_count = 0
    for contract_path, code in contracts:
        print("\n" + ("🤖 " * 40) + "\n")
        print("Contract path:", contract_path)

        # constructing github link to fetch from
        github_link = f"https://api.github.com/repos/{user_slash_repo}/contents/{contract_path}" + ("?ref=" + ref if ref else "")

        if "@aragon" in contract_path:

            if not aragon_ref_provided:
                print("🔵 [INFO]: Looks like the contract uses Aragon deps.")
                aragon_ref = input("🟡 [PROMPT]: Please specify Aragon ref (using default if none provided): ")
                aragon_ref_provided = True

            contract_path = contract_path.replace("@aragon/os/", "")
            github_link = f"https://api.github.com/repos/aragon/aragonOS/contents/{contract_path}" + ("?ref=" + aragon_ref if aragon_ref else "")

        print(f"🔵 [INFO]: Fetching source code from {github_link}")

        # fetching code from github
        github_response = requests.get(github_link, headers={"Authorization": f"token {github_token}"})
        github_data = github_response.json()
        contract_name = github_data.get("name")
        if not contract_name:
            code_not_found_count += 1
            print(f"🟠 [WARNING]: Failed to find {contract_path} in the repo!")
            continue

        # decode base64 to string
        encoded_source_code = github_data.get("content")
        github_file_content = base64.b64decode(encoded_source_code).decode()

        # split code by lines for differ
        github_code_lines = github_file_content.splitlines()
        etherscan_code_lines = code['content'].splitlines()

        # get diffs
        diffs = difflib.unified_diff(github_code_lines, etherscan_code_lines)

        # if diffs are present, output to diff view html
        if len(list(diffs)):
            diff_html = difflib.HtmlDiff().make_file(github_code_lines, etherscan_code_lines)
            filename = f"diffs/{contract_name}.html"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "w") as f:
                f.write(diff_html)
            print(f"🟠 [WARNING]: Diffs found in {contract_name}! More details in {filename}")
        else:
            no_diff_count += 1
            print(f"🟢 [SUCCESS]: No diffs found in {contract_name}!")

        # sleep for 1 second to avoid rate limiting
        time.sleep(1)
    
    # print final stats
    print("\n" + ("🏁 " * 40) + "\n")
    contracts_count = len(list(contracts))
    print(f"🧬 Identical files: {no_diff_count} / {contracts_count}")
    print(f"🔭 Code not found: {code_not_found_count} / {contracts_count}")


def load_env(variable_name, required=True):
    value = os.getenv(variable_name)
    if not value:
        if required:
            print(f"🔴 [ERROR]: `{variable_name}` unset!")
            sys.exit()
        else:
            print(f"🟠 [WARNING]: Proceeding without `{variable_name}`!")

    return value


def parse_repo_link(repo_link):
    parse_result = urlparse(repo_link)
    repo_location = [item.strip("/") for item in parse_result[2].split("tree")]
    user_slash_repo = repo_location[0]
    ref = repo_location[1] if len(repo_location) > 1 else None
    return (user_slash_repo, ref)




if __name__ == "__main__":
    main()

