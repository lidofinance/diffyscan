import json
import sys

from utils.common import fetch
from utils.logger import logger


def _errorNoSourceCodeAndExit(address):
    logger.error("source code is not verified or an EOA address", address)
    sys.exit(1)


def _get_contract_from_etherscan(token, etherscan_hostname, contract):
    etherscan_link = f"https://{etherscan_hostname}/api?module=contract&action=getsourcecode&address={contract}"
    if token is not None:
        etherscan_link = f"{etherscan_link}?apikey={token}"

    response = fetch(etherscan_link)

    if response["message"] == "NOTOK":
        logger.error("Failed", response["result"])
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)
        sys.exit(1)

    data = response["result"][0]
    if "ContractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    contract_name = data["ContractName"]

    json_escaped = data["SourceCode"].startswith("{{")
    source_files = (
        json.loads(data["SourceCode"][1:-1])["sources"].items()
        if json_escaped
        else json.loads(data["SourceCode"]).items()
    )

    return (contract_name, source_files)


def _get_contract_from_zksync(zksync_explorer_hostname, contract):
    zksync_explorer_link = (
        f"https://{zksync_explorer_hostname}/contract_verification/info/{contract}"
    )

    response = fetch(zksync_explorer_link)

    if not response.get("verifiedAt"):
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)
        sys.exit(1)

    data = response["request"]
    if "ContractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    contract_name = data["contractName"].split(":")[-1]
    source_files = data["sourceCode"]["sources"].items()

    return (contract_name, source_files)


def _get_contract_from_mantle(mantle_explorer_hostname, contract):
    etherscan_link = f"https://{mantle_explorer_hostname}/api?module=contract&action=getsourcecode&address={contract}"

    response = fetch(etherscan_link)

    data = response["result"][0]
    if "ContractName" not in data:
        _errorNoSourceCodeAndExit(contract)

    source_files = [(data["FileName"], {"content": data["SourceCode"]})]
    for entry in data.get("AdditionalSources", []):
        source_files.append((entry["Filename"], {"content": entry["SourceCode"]}))

    return (data["ContractName"], source_files)


def get_contract_from_explorer(token, explorer_hostname, contract):
    if explorer_hostname.startswith("zksync"):
        return _get_contract_from_zksync(explorer_hostname, contract)
    if explorer_hostname.endswith("mantle.xyz"):
        return _get_contract_from_mantle(explorer_hostname, contract)
    if explorer_hostname.endswith("lineascan.build"):
        return _get_contract_from_etherscan(None, explorer_hostname, contract)
    return _get_contract_from_etherscan(token, explorer_hostname, contract)
