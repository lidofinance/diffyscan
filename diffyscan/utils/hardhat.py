import os
import subprocess
import signal

from urllib.parse import urlparse
from .logger import logger
from .constants import LOCAL_RPC_URL, REMOTE_RPC_URL
from .binary_verifier import get_chain_id


class Hardhat:
    sub_process = None
    TIMEOUT_FOR_INIT_SEC = 5

    def __init__(self):
        pass

    def is_port_in_use(self, parsed_url) -> bool:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((parsed_url.hostname, parsed_url.port)) == 0

    def start(self, hardhat_path):
        parsed_url = urlparse(LOCAL_RPC_URL)

        local_node_command = (
            f"npx hardhat node --hostname {parsed_url.hostname} "
            f"--port {parsed_url.port} "
            f"--config {hardhat_path} "
        )

        logger.info(f'Trying to start Ganache: "{local_node_command}"')
        is_port_used = self.is_port_in_use(parsed_url)
        if is_port_used:
            answer = input(f'Port {parsed_url.port} is busy. Fix it? write "yes": ')
            if answer.lower() == "yes":
                return_code = subprocess.call(
                    f"exec npx kill-port {parsed_url.port}", shell=True
                )
                if return_code == 0:
                    is_port_used = self.is_port_in_use(parsed_url)
        if is_port_used:
            raise ValueError(f"Failed to start Ganache: {parsed_url.netloc} is busy")
        self.sub_process = subprocess.Popen(
            "exec " + local_node_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            _, errs = self.sub_process.communicate(timeout=self.TIMEOUT_FOR_INIT_SEC)
            if errs:
                raise ValueError(f"Failed to start Ganache: {errs.decode()}")
        except subprocess.TimeoutExpired:
            is_port_used = self.is_port_in_use(parsed_url)
            if is_port_used:
                logger.okay(f"Ganache successfully started, PID {self.sub_process.pid}")
            else:
                raise ValueError(f"Failed to start Ganache: something is wrong")

    def stop(self):
        if self.sub_process is not None and self.sub_process.poll() is None:
            os.kill(self.sub_process.pid, signal.SIGTERM)
            logger.info(f"Ganache stopped, PID {self.sub_process.pid}")


hardhat = Hardhat()
