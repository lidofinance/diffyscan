import json

from .common import pull, mask_text
from .logger import logger
from .custom_exceptions import NodeError


def get_bytecode_from_node(contract_address: str, rpc_url: str) -> str:
    """
    Get the bytecode of a contract from an RPC node.

    Args:
        contract_address: The contract address
        rpc_url: The RPC URL

    Returns:
        The contract bytecode as a hex string

    Raises:
        NodeError: If the bytecode cannot be retrieved
    """
    logger.info(f'Receiving the bytecode from "{mask_text(rpc_url)}" ...')

    payload = json.dumps(
        {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_getCode",
            "params": [contract_address, "latest"],
        }
    )

    headers = {"Content-Type": "application/json"}
    sources_url_response_in_json = pull(rpc_url, payload, headers).json()
    if (
        "result" not in sources_url_response_in_json
        or sources_url_response_in_json["result"] == "0x"
    ):
        raise NodeError(f"Received bad response: {sources_url_response_in_json}")

    logger.okay("Bytecode was successfully received")
    return sources_url_response_in_json["result"]


def get_chain_id(rpc_url: str) -> int:
    """
    Get the chain ID from an RPC node.

    Args:
        rpc_url: The RPC URL

    Returns:
        The chain ID as an integer

    Raises:
        NodeError: If the chain ID cannot be retrieved
    """
    logger.info(f'Receiving the chain ID from "{mask_text(rpc_url)}" ...')

    payload = json.dumps(
        {"id": 1, "jsonrpc": "2.0", "method": "eth_chainId", "params": []}
    )

    headers = {"Content-Type": "application/json"}
    chain_id_response = pull(rpc_url, payload, headers).json()

    if "result" not in chain_id_response:
        raise NodeError(f"Failed to retrieve chain ID: {chain_id_response}")

    logger.okay("Chain ID was successfully received")

    # Convert hex string to decimal integer
    chain_id = int(chain_id_response["result"], 16)
    return chain_id


def get_account(rpc_url: str) -> str:
    """
    Get the first account from an RPC node.

    Args:
        rpc_url: The RPC URL

    Returns:
        The account address

    Raises:
        NodeError: If no account is available
    """
    logger.info(f'Receiving the account from "{rpc_url}" ...')

    payload = json.dumps(
        {"id": 42, "jsonrpc": "2.0", "method": "eth_accounts", "params": []}
    )

    headers = {"Content-Type": "application/json"}
    account_address_response = pull(rpc_url, payload, headers).json()

    if "result" not in account_address_response:
        raise NodeError("The deployer account isn't set")

    logger.okay("The account was successfully received")

    return account_address_response["result"][0]


def deploy_contract(rpc_url: str, deployer: str, data: str) -> str:
    """
    Deploy a contract and return its address.

    Args:
        rpc_url: The RPC URL
        deployer: The deployer account address
        data: The contract creation bytecode

    Returns:
        The deployed contract address

    Raises:
        NodeError: If deployment fails
    """
    logger.info(f'Trying to deploy transaction to "{rpc_url}" ...')

    payload_sendTransaction = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "eth_sendTransaction",
            "params": [{"from": deployer, "gas": 9000000, "input": data}],
            "id": 1,
        }
    )
    headers = {"Content-Type": "application/json"}
    response_sendTransaction = pull(rpc_url, payload_sendTransaction, headers).json()

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
