import hashlib
import subprocess
import json
import os
import stat
import sys

from .common import fetch
from .helpers import create_dirs
from .logger import logger
from .custom_exceptions import CompileError

SOLC_PLATFORM_MAP = {
    "linux": "linux-amd64",
    "darwin": "macosx-amd64",
    "win32": "windows-amd64",
}


def get_solc_native_platform_from_os() -> str:
    """
    Get the Solidity compiler platform identifier for the current OS.

    Returns:
        Platform identifier string

    Raises:
        CompileError: If the platform is not supported
    """
    platform_name = sys.platform
    try:
        return SOLC_PLATFORM_MAP[platform_name]
    except KeyError as exc:
        raise CompileError(f"Unsupported platform {platform_name}") from exc


def get_compiler_info(required_platform: str, required_compiler_version: str) -> dict:
    compilers_list_url = f"https://raw.githubusercontent.com/ethereum/solc-bin/refs/heads/gh-pages/{required_platform}/list.json"
    available_compilers_list = fetch(compilers_list_url).json()
    required_build_info = next(
        (
            compiler
            for compiler in available_compilers_list["builds"]
            if compiler["longVersion"] == required_compiler_version
        ),
        None,
    )

    if not required_build_info:
        raise CompileError(
            f'Required compiler version "{required_compiler_version}" for "{required_platform}" is not found'
        )

    return required_build_info


def prepare_compiler(
    required_platform: str, build_info: dict, compiler_path: str
) -> None:
    """Download, verify, and prepare the Solidity compiler."""
    create_dirs(compiler_path)
    compiler_url = (
        f'https://binaries.soliditylang.org/{required_platform}/{build_info["path"]}'
    )
    compiler_binary = fetch(compiler_url).content

    try:
        with open(compiler_path, "wb") as compiler_file:
            compiler_file.write(compiler_binary)
    except OSError as exc:
        raise CompileError(f"Error writing to file: {exc}") from exc

    verify_compiler_integrity(compiler_path, build_info)


def verify_compiler_integrity(compiler_path: str, build_info: dict) -> None:
    try:
        with open(compiler_path, "rb") as compiler_file:
            compiler_binary = compiler_file.read()
    except OSError as exc:
        raise CompileError(f"Error reading compiler file: {exc}") from exc

    valid_checksum = build_info["sha256"].removeprefix("0x")
    compiler_checksum = hashlib.sha256(compiler_binary).hexdigest()
    if compiler_checksum != valid_checksum:
        raise CompileError(
            f"Compiler checksum mismatch. Expected: {valid_checksum}, Got: {compiler_checksum}"
        )

    compiler_file_rights = os.stat(compiler_path)
    os.chmod(compiler_path, compiler_file_rights.st_mode | stat.S_IEXEC)


def compile_contracts(compiler_path: str, input_settings: str) -> dict:
    """Compile Solidity contracts using the solc compiler."""
    try:
        process = subprocess.run(
            [compiler_path, "--standard-json"],
            input=input_settings.encode(),
            capture_output=True,
            check=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as e:
        raise CompileError(f"Error during compiler subprocess execution: {e}")
    except subprocess.TimeoutExpired as e:
        raise CompileError(f"Compiler process timed out: {e}")
    except Exception as e:
        raise CompileError(f"An unexpected error occurred: {e}")
    return json.loads(process.stdout)


def get_target_compiled_contract(
    compiled_contracts: list, target_contract_name: str
) -> dict:
    contracts_to_check = [
        contract
        for contracts in compiled_contracts
        for name, contract in contracts.items()
        if name == target_contract_name
    ]

    if len(contracts_to_check) != 1:
        raise CompileError("multiple contracts with the same name")

    logger.okay("Contracts were successfully compiled")

    return contracts_to_check[0]
