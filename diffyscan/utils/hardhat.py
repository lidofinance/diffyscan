import os
import subprocess
import signal

from urllib.parse import urlparse
from .logger import logger
from .custom_exceptions import HardhatError


class Hardhat:
    sub_process = None
    TIMEOUT_FOR_INIT_SEC = 5

    def __init__(self):
        pass

    def is_port_in_use(self, parsed_url) -> bool:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((parsed_url.hostname, parsed_url.port)) == 0

    def start(
        self,
        main_config_relative_path: str,
        hardhat_config_name: str,
        local_rpc_url: str,
        remote_rpc_url: str,
    ):
        parsed_url = urlparse(local_rpc_url)
        if parsed_url.port == None:
            raise HardhatError(
                f"Invalid LOCAL_RPC_URL (TCP port not specified): '{local_rpc_url}'"
            )

        hardhat_config_path = os.path.join(
            os.path.dirname(main_config_relative_path), "hardhat_config.js"
        )

        if not os.path.isfile(hardhat_config_path):
            hardhat_config_path = Hardhat.get_config_path(
                os.path.dirname(main_config_relative_path),
                "hardhat_configs",
                hardhat_config_name,
            )
            if not os.path.isfile(hardhat_config_path):
                raise HardhatError(f"Failed to find any Hardhat config")

        local_node_command = (
            f"npx hardhat node --hostname {parsed_url.hostname} "
            f"--port {parsed_url.port} "
            f"--config {hardhat_config_path} "
            f"--fork {remote_rpc_url}"
        )

        logger.info(f'Trying to start Hardhat: "{local_node_command}"')
        is_port_used = self.is_port_in_use(parsed_url)
        if is_port_used:
            answer = input(
                f'Port {parsed_url.port} is busy. Kill the app instance occupying the port? write "yes": '
            )
            if answer.lower() == "yes":
                return_code = subprocess.call(
                    f"exec npx kill-port {parsed_url.port}", shell=True
                )
                if return_code == 0:
                    is_port_used = self.is_port_in_use(parsed_url)
        if is_port_used:
            raise HardhatError(f"{parsed_url.netloc} is busy")
        self.sub_process = subprocess.Popen(
            "exec " + local_node_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            _, errs = self.sub_process.communicate(timeout=self.TIMEOUT_FOR_INIT_SEC)
            if errs:
                raise HardhatError(f"{errs.decode()}")
        except subprocess.TimeoutExpired:
            is_port_used = self.is_port_in_use(parsed_url)
            if is_port_used:
                logger.okay(f"Hardhat successfully started, PID {self.sub_process.pid}")
            else:
                raise HardhatError(f"something is wrong")

    def stop(self):
        if self.sub_process is not None and self.sub_process.poll() is None:
            os.kill(self.sub_process.pid, signal.SIGTERM)
            logger.info(f"Hardhat stopped, PID {self.sub_process.pid}")

    @staticmethod
    def get_config_path(from_path: str, to_path: str, filename: str) -> str:
        return os.path.normpath(os.path.join(from_path, os.pardir, to_path, filename))


hardhat = Hardhat()
