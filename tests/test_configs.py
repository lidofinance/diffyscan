import json
from pathlib import Path

CONFIG_DIR = Path("config_samples")
REQUIRED_GITHUB_KEYS = {"url", "commit", "relative_root"}


def config_paths():
    return [p for p in CONFIG_DIR.rglob("*.json")]


def load(path):
    with open(path) as f:
        return json.load(f)


def test_config_fields_present():
    for path in config_paths():
        print(path)

        cfg = load(path)
        assert "contracts" in cfg and cfg["contracts"], f"{path} missing contracts"
        assert "github_repo" in cfg
        assert REQUIRED_GITHUB_KEYS <= set(
            cfg["github_repo"]
        ), f"{path} github_repo keys"
        assert "dependencies" in cfg
        assert "explorer_hostname" in cfg or "explorer_hostname_env_var" in cfg


def test_contract_addresses_format():
    for path in config_paths():
        print(path)

        cfg = load(path)
        for addr in cfg.get("contracts", {}):
            assert (
                addr.startswith("0x") and len(addr) == 42
            ), f"Bad addr {addr} in {path}"
