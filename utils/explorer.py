import json
import sys

from utils.common import fetch
from utils.logger import logger


def _get_contract_from_etherscan(token, etherscan_hostname, contract):
    etherscan_link = f"https://{etherscan_hostname}/api?module=contract&action=getsourcecode&address={contract}&apikey={token}"

    response = fetch(etherscan_link)

    if response["message"] == "NOTOK":
        logger.error("Failed", response["result"])
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)
        sys.exit(1)

    data = response["result"][0]
    if not data["ContractName"]:
        logger.error("Not a contract or source code is not verified", contract)
        sys.exit(1)

    contract_name = data["ContractName"]
    source_files = json.loads(data["SourceCode"][1:-1])["sources"].items()

    return (contract_name, source_files)

def _get_contract_from_zksync(token, zksync_explorer_hostname, contract):
    zksync_explorer_link = f"https://{zksync_explorer_hostname}/contract_verification/info/{contract}"

    response = fetch(zksync_explorer_link)

    if not response.get("verifiedAt"):
        logger.error("Status", response.status_code)
        logger.error("Response", response.text)
        sys.exit(1)

    data = response["request"]
    if not data["contractName"]:
        logger.error("Not a contract or source code is not verified", contract)
        sys.exit(1)

    contract_name = data["contractName"].split(":")[-1]
    source_files = data["sourceCode"]["sources"].items()

    return (contract_name, source_files)

def get_contract_from_explorer(token, explorer_hostname, contract):
    if explorer_hostname.startswith("zksync"):
        return _get_contract_from_zksync(token, explorer_hostname, contract)
    return _get_contract_from_etherscan(token, explorer_hostname, contract)
