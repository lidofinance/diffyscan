import time
import os

DIGEST_DIR = "digest"
START_TIME = time.time()
START_TIME_INT = int(START_TIME)
DIFFS_DIR = f"{DIGEST_DIR}/{START_TIME_INT}/diffs"
LOGS_PATH = f"{DIGEST_DIR}/{START_TIME_INT}/logs.txt"
DEFAULT_CONFIG_PATH = "config.json"

REMOTE_RPC_URL = os.getenv('REMOTE_RPC_URL', '')
if not REMOTE_RPC_URL:
    raise ValueError('REMOTE_RPC_URL variable is not set')

REMOTE_EXPLORER_NAME = os.getenv('REMOTE_EXPLORER_NAME', '')
if REMOTE_EXPLORER_NAME == '':
  raise ValueError('REMOTE_EXPLORER_NAME variable is not set')
  
LOCAL_RPC_URL = os.getenv('LOCAL_RPC_URL', '')
if not LOCAL_RPC_URL:
    raise ValueError('LOCAL_RPC_URL variable is not set')
