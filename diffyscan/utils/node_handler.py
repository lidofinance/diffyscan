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
    response = pull(rpc_url, payload, {"Content-Type": "application/json"}).json()

    if "error" in response:
        err = response["error"]
        msg = err.get("message", "unknown RPC error")
        data = err.get("data")
        raise NodeError(f"{msg}. data={data}" if data is not None else msg)

    if "result" not in response:
        raise NodeError(f"Bad response for {method}: {response}")

    return response["result"]


def get_bytecode_from_node(contract_address: str, rpc_url: str) -> str:
    """Fetch deployed bytecode for a contract address via eth_getCode."""
    logger.info(f'Receiving bytecode from "{mask_text(rpc_url)}" ...')
    result = _rpc_call(rpc_url, "eth_getCode", [contract_address, "latest"])
    if result == "0x":
        raise NodeError(f"Empty bytecode for contract {contract_address}")
    logger.okay("Bytecode received")
    return result


def get_chain_id(rpc_url: str) -> int:
    """Fetch chain ID from an RPC node."""
    logger.info(f'Receiving chain ID from "{mask_text(rpc_url)}" ...')
    chain_id = int(_rpc_call(rpc_url, "eth_chainId", []), 16)
    logger.okay("Chain ID received")
    return chain_id


def simulate_deployment(data: str, rpc_url: str, caller: str = DEFAULT_CALLER) -> str:
    """Simulate contract deployment via eth_call and return deployed runtime bytecode."""
    logger.info(f'Simulating deployment via eth_call on "{mask_text(rpc_url)}" ...')

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

    logger.okay("eth_call returned runtime bytecode", f"{len(result[2:]) // 2} bytes")
    return result
