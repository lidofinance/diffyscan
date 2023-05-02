import time

DIGEST_DIR = "digest"
START_TIME = time.time()
START_TIME_INT = int(START_TIME)
DIFFS_DIR = f"{DIGEST_DIR}/{START_TIME_INT}/diffs"
LOGS_PATH = f"{DIGEST_DIR}/{START_TIME_INT}/logs.txt"
CONFIG_PATH = "config.json"
CONTRACTS_DIR = "contracts"
