import json
import sys

from utils.common import fetch
from utils.logger import logger


def get_contract_from_etherscan(token, indexer_host, contract):
    etherscan_link = f"https://{indexer_host}/api?module=contract&action=getsourcecode&address={contract}&apikey={token}"

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
