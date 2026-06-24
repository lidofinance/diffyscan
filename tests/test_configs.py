import json
import yaml
from pathlib import Path

CONFIG_DIR = Path("config_samples")
REQUIRED_GITHUB_KEYS = {"url", "commit", "relative_root"}


def config_paths():
    supported = {".json", ".yaml", ".yml"}
    return sorted(p for p in CONFIG_DIR.rglob("*") if p.suffix.lower() in supported)


def load(path):
    with open(path) as f:
        if path.suffix.lower() in (".yaml", ".yml"):
            return yaml.safe_load(f)
        return json.load(f)


def is_solc_standard_input(cfg) -> bool:
    """solc standard-JSON inputs (used by local_compilation configs) live next to
    configs but are not configs themselves."""
    return (
        isinstance(cfg, dict)
        and "contracts" not in cfg
        and cfg.get("language") == "Solidity"
        and "sources" in cfg
    )


def test_config_fields_present():
    for path in config_paths():
        print(path)

        cfg = load(path)
        if is_solc_standard_input(cfg):
            continue
        assert "contracts" in cfg and cfg["contracts"], f"{path} missing contracts"
        assert "github_repo" in cfg
        assert REQUIRED_GITHUB_KEYS <= set(
            cfg["github_repo"]
        ), f"{path} github_repo keys"
        assert "dependencies" in cfg
        # local_compilation configs verify bytecode without an explorer
        assert (
            "explorer_hostname" in cfg
            or "explorer_hostname_env_var" in cfg
            or "local_compilation" in cfg
        ), f"{path} missing explorer_hostname or local_compilation"


def test_contract_addresses_format():
    for path in config_paths():
        print(path)

        cfg = load(path)
        if is_solc_standard_input(cfg):
            continue
        for addr in cfg.get("contracts", {}):
            assert (
                addr.startswith("0x") and len(addr) == 42
            ), f"Bad addr {addr} in {path}"
