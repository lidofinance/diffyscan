import os
import subprocess
import signal

from urllib.parse import urlparse
from utils.logger import logger
from utils.constants import LOCAL_RPC_URL, REMOTE_RPC_URL
from utils.binary_verifier import get_chain_id
class Ganache:
  sub_process = None
  
  def __init__(self):
      pass
  
  def start(self):
    
      local_node_command = (
        f'ganache --host {urlparse(LOCAL_RPC_URL).hostname} ' \
        f'--port {urlparse(LOCAL_RPC_URL).port} ' \
        f'--chain.chainId {get_chain_id (REMOTE_RPC_URL)} ' \
        f'--fork.url {REMOTE_RPC_URL} ' \
        f'-l 92000000 --hardfork istanbul -d '
      )

      self.sub_process = subprocess.Popen("exec "+ local_node_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      
      logger.info(f'Ganache successfully started: "{local_node_command}", PID {self.sub_process.pid}')
    
  def stop(self):
      if self.sub_process is not None and self.sub_process.poll() is None:
          os.kill(self.sub_process.pid, signal.SIGTERM)
          logger.info(f'Ganache stopped, PID {self.sub_process.pid}')

ganache = Ganache()