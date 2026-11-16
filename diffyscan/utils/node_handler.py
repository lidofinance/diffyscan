import json

from .common import mask_text
from .http_client import pull
from .logger import logger
from .custom_exceptions import DeploymentSimulationError, NodeError

DEFAULT_CALLER = "0x0000000000000000000000000000000000000000"
# EIP-7825 (Fusaka): max gas a single tx / contract creation may use. No real
# deployment can exceed this, so it is the correct simulation ceiling; values
# above it are rejected by strict/hosted nodes with an opaque "Invalid params".
DEFAULT_DEPLOYMENT_GAS_LIMIT = 16_777_216  # 2**24


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
    if not isinstance(result, str):
        raise NodeError(f"Malformed bytecode RPC response")
    logger.okay("Bytecode received")
    return result  # type cast is safe as `isinstance` enforced above


def get_chain_id(rpc_url: str) -> int:
    """Fetch chain ID from an RPC node."""
    logger.info(f'Receiving chain ID from "{mask_text(rpc_url)}" ...')
    chain_id = int(_rpc_call(rpc_url, "eth_chainId", []), 16)
    logger.okay("Chain ID received")
    return chain_id


def simulate_deployment(
    data: str,
    rpc_url: str,
    caller: str = DEFAULT_CALLER,
    gas_limit: int = DEFAULT_DEPLOYMENT_GAS_LIMIT,
) -> str:
    """Simulate contract deployment via eth_call and return deployed runtime bytecode."""
    logger.info(f'Simulating deployment via eth_call on "{mask_text(rpc_url)}" ...')

    try:
        result = _rpc_call(
            rpc_url,
            "eth_call",
            [
                {
                    "from": caller,
                    "to": None,
                    "gas": hex(gas_limit),
                    "data": data,
                },
                "latest",
            ],
        )
    except NodeError as exc:
        message = str(exc)
        node_prefix = f"{NodeError.prefix}: "
        if message.startswith(node_prefix):
            message = message[len(node_prefix) :]
        raise DeploymentSimulationError(message) from exc

    if not isinstance(result, str) or result == "0x":
        raise DeploymentSimulationError("eth_call returned empty runtime bytecode")

    logger.okay("eth_call returned runtime bytecode", f"{len(result[2:]) // 2} bytes")
    return result


def _has_code(contract_address: str, block: int, rpc_url: str) -> bool:
    code = _rpc_call(rpc_url, "eth_getCode", [contract_address, hex(block)])
    return isinstance(code, str) and code not in ("0x", "")


def find_creation_block(contract_address: str, rpc_url: str) -> int:
    """Find the first block with code at the address. Needs an archive RPC."""
    high = int(_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    if not _has_code(contract_address, high, rpc_url):
        raise NodeError(f"Empty bytecode for contract {contract_address}")
    low = -1  # the block before the genesis has no code
    while high - low > 1:
        middle = (low + high) // 2
        if _has_code(contract_address, middle, rpc_url):
            high = middle
        else:
            low = middle
    return high


def _find_creation_frame(frame: dict, contract_address: str) -> dict | None:
    if frame.get("type") in ("CREATE", "CREATE2") and (
        str(frame.get("to", "")).lower() == contract_address.lower()
    ):
        return frame
    for call in frame.get("calls") or []:
        found = _find_creation_frame(call, contract_address)
        if found is not None:
            return found
    return None


def get_creation_init_code(contract_address: str, rpc_url: str) -> str:
    """Read the init code of the contract from the call trace of its creation block.

    Needs an RPC with archive state and debug_traceBlockByNumber.
    """
    block = find_creation_block(contract_address, rpc_url)
    logger.info(f"Reading the creation of {contract_address} in block {block} ...")
    traces = _rpc_call(
        rpc_url, "debug_traceBlockByNumber", [hex(block), {"tracer": "callTracer"}]
    )
    for trace in traces if isinstance(traces, list) else []:
        frame = _find_creation_frame(trace.get("result") or {}, contract_address)
        if frame is not None and isinstance(frame.get("input"), str):
            logger.okay("Creation init code received", f"block {block}")
            return str(frame["input"])
    raise NodeError(f"No creation of {contract_address} in the trace of block {block}")


def get_constructor_arguments_from_creation(
    contract_address: str, creation_code: str, rpc_url: str
) -> str:
    """Return the init code of the creation after the compiled creation code."""
    init_code = get_creation_init_code(contract_address, rpc_url)
    if len(init_code) < len(creation_code):
        raise NodeError(
            f"Creation init code of {contract_address} is shorter than the compiled creation code"
        )
    return "0x" + init_code[len(creation_code) :]
