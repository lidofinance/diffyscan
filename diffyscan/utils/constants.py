import time
import os

DIGEST_DIR = "digest"
START_TIME = time.time()
START_TIME_INT = int(START_TIME)
DIFFS_DIR = f"{DIGEST_DIR}/{START_TIME_INT}/diffs"
LOGS_PATH = f"{DIGEST_DIR}/{START_TIME_INT}/logs.txt"
DEFAULT_CONFIG_PATH = "config.json"

REMOTE_RPC_URL = os.getenv("REMOTE_RPC_URL", "")
if not REMOTE_RPC_URL:
    raise ValueError("REMOTE_RPC_URL variable is not set")

SOLC_DIR = os.getenv("SOLC_DIR", "")
if SOLC_DIR == "":
    raise ValueError("SOLC_DIR variable is not set")

LOCAL_RPC_URL = os.getenv("LOCAL_RPC_URL", "")
if not LOCAL_RPC_URL:
    raise ValueError("LOCAL_RPC_URL variable is not set")

GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN", "")
if not GITHUB_API_TOKEN:
    raise ValueError("GITHUB_API_TOKEN variable is not set")
