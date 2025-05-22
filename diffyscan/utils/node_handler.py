import json

from .common import pull, mask_text
from .logger import logger
from .custom_exceptions import NodeError


def get_bytecode_from_node(contract_address, rpc_url):
    logger.info(f'Receiving the bytecode from "{mask_text(rpc_url)}" ...')

    payload = json.dumps(
        {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_getCode",
            "params": [contract_address, "latest"],
        }
    )

    sources_url_response_in_json = pull(rpc_url, payload).json()
    if (
        "result" not in sources_url_response_in_json
        or sources_url_response_in_json["result"] == "0x"
    ):
        raise NodeError(f"Received bad response: {sources_url_response_in_json}")

    logger.okay("Bytecode was successfully received")
    return sources_url_response_in_json["result"]


def get_account(rpc_url):
    logger.info(f'Receiving the account from "{rpc_url}" ...')

    payload = json.dumps(
        {"id": 42, "jsonrpc": "2.0", "method": "eth_accounts", "params": []}
    )

    account_address_response = pull(rpc_url, payload).json()

    if "result" not in account_address_response:
        raise NodeError("The deployer account isn't set")

    logger.okay("The account was successfully received")

    return account_address_response["result"][0]


def deploy_contract(rpc_url, deployer, data):
    logger.info(f'Trying to deploy transaction to "{rpc_url}" ...')

    payload_sendTransaction = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "eth_sendTransaction",
            "params": [{"from": deployer, "gas": 9000000, "input": data}],
            "id": 1,
        }
    )
    response_sendTransaction = pull(rpc_url, payload_sendTransaction).json()

    if "error" in response_sendTransaction:
        raise NodeError(response_sendTransaction["error"]["message"])

    logger.okay("Transaction was successfully deployed")

    tx_hash = response_sendTransaction["result"]

    payload_getTransactionReceipt = json.dumps(
        {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash],
        }
    )
    response_getTransactionReceipt = pull(rpc_url, payload_getTransactionReceipt).json()

    if (
        "result" not in response_getTransactionReceipt
        or "contractAddress" not in response_getTransactionReceipt["result"]
        or "status" not in response_getTransactionReceipt["result"]
    ):
        raise NodeError("Failed to receive transaction receipt")

    if response_getTransactionReceipt["result"]["status"] != "0x1":
        raise NodeError(
            "Failed to receive transaction receipt. \
  Transaction has been reverted (status 0x0). Input mismatch?",
        )

    contract_address = response_getTransactionReceipt["result"]["contractAddress"]

    return contract_address
