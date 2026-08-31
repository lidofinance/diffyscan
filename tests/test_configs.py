from pathlib import Path

from diffyscan.utils.common import load_config

CONFIG_DIR = Path("configs")
REQUIRED_GITHUB_KEYS = {"url", "commit", "relative_root"}


def config_paths():
    supported = {".json", ".yaml", ".yml"}
    return sorted(p for p in CONFIG_DIR.rglob("*") if p.suffix.lower() in supported)


def test_config_fields_present():
    for path in config_paths():
        print(path)

        cfg = load_config(str(path))
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

        cfg = load_config(str(path))
        for addr in cfg.get("contracts", {}):
            assert (
                addr.startswith("0x") and len(addr) == 42
            ), f"Bad addr {addr} in {path}"
