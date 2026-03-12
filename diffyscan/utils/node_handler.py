import json

from .common import pull, mask_text
from .logger import logger
from .custom_exceptions import NodeError

DEFAULT_CALLER = "0x0000000000000000000000000000000000000000"
DEPLOYMENT_SIMULATION_GAS_LIMIT = 100_000_000


def _rpc_call(rpc_url: str, method: str, params: list):
    payload = json.dumps(
        {"id": 1, "jsonrpc": "2.0", "method": method, "params": params}
    )
    headers = {"Content-Type": "application/json"}
    response = pull(rpc_url, payload, headers).json()

    if "error" in response:
        error = response["error"]
        message = error.get("message", "unknown RPC error")
        data = error.get("data")
        if data is not None:
            message = f"{message}. data={data}"
        raise NodeError(message)

    if "result" not in response:
        raise NodeError(f"Received bad response for {method}: {response}")

    return response["result"]


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

    deployed_bytecode = _rpc_call(rpc_url, "eth_getCode", [contract_address, "latest"])
    if deployed_bytecode == "0x":
        raise NodeError(f"Received empty bytecode for contract {contract_address}")

    logger.okay("Bytecode was successfully received")
    return deployed_bytecode


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

    chain_id = int(_rpc_call(rpc_url, "eth_chainId", []), 16)
    logger.okay("Chain ID was successfully received")

    return chain_id


def simulate_deployment(data: str, rpc_url: str, caller: str = DEFAULT_CALLER) -> str:
    """
    Simulate contract deployment via eth_call and return the deployed runtime bytecode.
    """
    logger.info(
        f'Simulating contract deployment via eth_call on "{mask_text(rpc_url)}" ...'
    )

    result = _rpc_call(
        rpc_url,
        "eth_call",
        [
            {
                "from": caller,
                "to": None,
                "gas": hex(DEPLOYMENT_SIMULATION_GAS_LIMIT),
                "data": data,
            },
            "latest",
        ],
    )

    if not isinstance(result, str) or result == "0x":
        raise NodeError("eth_call returned empty runtime bytecode")

    logger.okay(
        "eth_call returned deployed runtime bytecode",
        f"{len(result[2:]) // 2} bytes",
    )
    logger.info("eth_call bytecode preview", f"{result[:18]}...{result[-16:]}")

    return result
