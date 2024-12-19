import os
import subprocess
import signal
import time
import socket

from urllib.parse import urlparse
from .common import mask_text
from .logger import logger
from .custom_exceptions import HardhatError


class Hardhat:
    sub_process = None
    HARDHAT_START_TIMEOUT_SEC = 10
    HARDHAT_STOP_TIMEOUT_SEC = 10
    ATTEMPTS_FOR_CONNECT = 5

    def start(
        self,
        hardhat_config_path: str,
        local_rpc_url: str,
        remote_rpc_url: str,
    ):
        parsed_url = urlparse(local_rpc_url)
        if not parsed_url.port or not parsed_url.hostname:
            raise HardhatError(f"Invalid LOCAL_RPC_URL: '{local_rpc_url}'")

        if not os.path.isfile(hardhat_config_path):
            raise HardhatError(
                f"Failed to find Hardhat config by path '{hardhat_config_path}'"
            )

        hardhat_cmd = [
            "npx",
            "hardhat",
            "node",
            "--hostname",
            parsed_url.hostname,
            "--port",
            str(parsed_url.port),
            "--config",
            hardhat_config_path,
        ]
        hardhat_cmd_line_masked = " ".join(
            hardhat_cmd + ["--fork", mask_text(remote_rpc_url)]
        )
        hardhat_cmd.extend(["--fork", remote_rpc_url])

        logger.info(f'Trying to start Hardhat: "{hardhat_cmd_line_masked}"')
        is_port_used = self._is_port_in_use_(parsed_url)
        if is_port_used:
            answer = input(
                f'Port {parsed_url.port} is busy. Kill the app instance occupying the port? write "yes": '
            )
            if answer.lower() == "yes":
                return_code = subprocess.call(
                    f"exec npx kill-port {parsed_url.port}", shell=True
                )
                if return_code == 0:
                    is_port_used = self._is_port_in_use_(parsed_url)
        if is_port_used:
            raise HardhatError(f"{parsed_url.netloc} is busy")
        self.sub_process = subprocess.Popen(
            hardhat_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        start_time = time.time()
        while time.time() - start_time < self.HARDHAT_START_TIMEOUT_SEC:
            output = self.sub_process.stdout.readline().decode()
            if "WILL BE LOST" in output:
                logger.info("Hardhat node is ready")
                break
        else:
            raise HardhatError(
                f"Hardhat node seems to have failed to start in {self.HARDHAT_START_TIMEOUT_SEC}"
            )
        time.sleep(5)

    def stop(self):
        if self.sub_process is not None and self.sub_process.poll() is None:
            os.killpg(os.getpgid(self.sub_process.pid), signal.SIGTERM)
            try:
                self.sub_process.communicate(timeout=self.HARDHAT_STOP_TIMEOUT_SEC)
                time.sleep(1)
                logger.info(f"Hardhat stopped, PID {self.sub_process.pid}")
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.sub_process.pid), signal.SIGKILL)
                logger.info(
                    f"Hardhat process failed to terminate in {self.HARDHAT_STOP_TIMEOUT_SEC} seconds, sent KILL command to PID {self.sub_process.pid}"
                )
            try:
                self.sub_process.communicate(timeout=self.HARDHAT_STOP_TIMEOUT_SEC)
                logger.info(f"Hardhat got KILLed, PID {self.sub_process.pid}")
            except subprocess.TimeoutExpired:
                logger.error(
                    f"Hardhat process failed to got KILLed in {self.HARDHAT_STOP_TIMEOUT_SEC} seconds, PID {self.sub_process.pid}"
                )

    def _is_port_in_use_(self, parsed_url) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((parsed_url.hostname, parsed_url.port)) == 0

    def _handle_timeout(self, parsed_url):
        attempt = 1
        logger.info("The connection to Hardhat is taking longer than expected")

        while attempt <= self.ATTEMPTS_FOR_CONNECT:
            logger.info(f"Reconnecting to Hardhat, attempt #{attempt}")
            if self._is_port_in_use_(parsed_url):
                logger.okay(f"Hardhat successfully started, PID {self.sub_process.pid}")
                return
            attempt += 1
            time.sleep(self.TIMEOUT_FOR_CONNECT_SEC)

        raise HardhatError("Something is wrong")


hardhat = Hardhat()
