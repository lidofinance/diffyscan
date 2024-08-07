import platform
import hashlib
import subprocess
import json
import os
import stat
import sys

from .common import fetch
from .helpers import create_dirs
from .logger import logger


def get_solc_native_platform_from_os():
    platform_name = sys.platform
    if platform_name == "linux":
        return "linux-amd64"
    elif platform_name == "darwin":
        return "macosx-amd64" if platform.machine() == "x86_64" else "macosx-arm64"
    else:
        raise ValueError(f"Unsupported platform {platform_name}")


def get_compiler_info(required_platform, required_compiler_version):
    compilers_list_url = f"https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/{required_platform}/list.json"
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
        raise ValueError(
            f'Required compiler version for "{required_platform}" is not found'
        )

    return required_build_info


def download_compiler(required_platform, build_info, destination_path):
    compiler_url = (
        f'https://binaries.soliditylang.org/{required_platform}/{build_info["path"]}'
    )
    download_compiler_response = fetch(compiler_url)

    try:
        with open(destination_path, "wb") as compiler_file:
            compiler_file.write(download_compiler_response.content)
    except IOError as e:
        raise ValueError(f"Error writing to file: {e}")
    except Exception as e:
        raise ValueError(f"An error occurred: {e}")
    return download_compiler_response.content


def check_compiler_checksum(compiler, valid_checksum):
    compiler_checksum = hashlib.sha256(compiler).hexdigest()
    if compiler_checksum != valid_checksum:
        raise ValueError(
            f"Compiler checksum mismatch. Expected: {valid_checksum}, Got: {compiler_checksum}"
        )


def set_compiler_executable(compiler_path):
    compiler_file_rights = os.stat(compiler_path)
    os.chmod(compiler_path, compiler_file_rights.st_mode | stat.S_IEXEC)


def prepare_compiler(required_platform, build_info, compiler_path):
    create_dirs(compiler_path)
    compiler_binary = download_compiler(required_platform, build_info, compiler_path)
    valid_checksum = build_info["sha256"][2:]
    check_compiler_checksum(compiler_binary, valid_checksum)
    set_compiler_executable(compiler_path)


def compile_contracts(compiler_path, input_settings):
    try:
        process = subprocess.run(
            [compiler_path, "--standard-json"],
            input=input_settings.encode(),
            capture_output=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Error during subprocess execution: {e}")
    except subprocess.TimeoutExpired as e:
        raise ValueError(f"Process timed out: {e}")
    except Exception as e:
        raise ValueError(f"An unexpected error occurred: {e}")
    return json.loads(process.stdout)


def get_target_compiled_contract(compiled_contracts, target_contract_name):
    contracts_to_check = []
    for contracts in compiled_contracts:
        for name, contract in contracts.items():
            if name == target_contract_name:
                contracts_to_check.append(contract)

    if len(contracts_to_check) != 1:
        raise ValueError("multiple contracts with the same name")

    logger.okay(f"Contracts were successfully compiled")

    return contracts_to_check[0]
