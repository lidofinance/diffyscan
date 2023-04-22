import json
import sys

from utils.common import fetch
from utils.logger import logger


def get_contract_from_etherscan(token, network, contract):
    etherscan_api_subdomain = "" if network == "mainnet" else f"-{network}"
    etherscan_link = f"https://api{etherscan_api_subdomain}.etherscan.io/api?module=contract&action=getsourcecode&address={contract}&apikey={token}"

    response = fetch(etherscan_link)

    if response["message"] == "NOTOK":
        logger.error("Failed", response["result"])
        sys.exit()

    data = response["result"][0]
    if not data["ContractName"]:
        logger.error("Contract not found", contract)
        sys.exit()

    contract_name = data["ContractName"]
    source_files = json.loads(data["SourceCode"][1:-1])["sources"].items()

    return (contract_name, source_files)
