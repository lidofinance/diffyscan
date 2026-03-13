import pytest

from diffyscan import diffyscan as diffyscan_module


def _capture_logger(monkeypatch):
    warnings = []
    infos = []
    okays = []
    errors = []

    monkeypatch.setattr(
        diffyscan_module.logger,
        "warn",
        lambda *args: warnings.append(args),
    )
    monkeypatch.setattr(
        diffyscan_module.logger,
        "info",
        lambda *args: infos.append(args),
    )
    monkeypatch.setattr(
        diffyscan_module.logger,
        "okay",
        lambda *args: okays.append(args),
    )
    monkeypatch.setattr(
        diffyscan_module.logger,
        "error",
        lambda *args: errors.append(args),
    )

    return warnings, infos, okays, errors


def test_load_explorer_token_reads_canonical_env_var(monkeypatch):
    warnings, _, _, errors = _capture_logger(monkeypatch)
    monkeypatch.setenv("ETHERSCAN_EXPLORER_TOKEN", "canonical-token")
    monkeypatch.delenv("ETHERSCAN_TOKEN", raising=False)

    token = diffyscan_module._load_explorer_token(
        {"explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN"}
    )

    assert token == "canonical-token"
    assert warnings == []
    assert errors == []


def test_load_explorer_token_falls_back_from_legacy_env_var(monkeypatch):
    warnings, _, _, errors = _capture_logger(monkeypatch)
    monkeypatch.delenv("ETHERSCAN_TOKEN", raising=False)
    monkeypatch.setenv("ETHERSCAN_EXPLORER_TOKEN", "canonical-token")

    token = diffyscan_module._load_explorer_token(
        {"explorer_token_env_var": "ETHERSCAN_TOKEN"}
    )

    assert token == "canonical-token"
    assert warnings == []
    assert errors == []


def test_load_explorer_token_legacy_env_var_requires_actionable_fallback(monkeypatch):
    warnings, _, _, errors = _capture_logger(monkeypatch)
    monkeypatch.delenv("ETHERSCAN_TOKEN", raising=False)
    monkeypatch.delenv("ETHERSCAN_EXPLORER_TOKEN", raising=False)

    with pytest.raises(
        ValueError,
        match="Set ETHERSCAN_EXPLORER_TOKEN or restore the legacy ETHERSCAN_TOKEN env var",
    ):
        diffyscan_module._load_explorer_token(
            {"explorer_token_env_var": "ETHERSCAN_TOKEN"}
        )

    assert warnings == []
    assert (
        "Explorer token not found. Set ETHERSCAN_EXPLORER_TOKEN or restore the legacy ETHERSCAN_TOKEN env var.",
    ) in errors


def test_load_explorer_token_uses_canonical_fallback_when_config_omits_env_var(
    monkeypatch,
):
    warnings, _, _, errors = _capture_logger(monkeypatch)
    monkeypatch.setenv("ETHERSCAN_EXPLORER_TOKEN", "canonical-token")
    monkeypatch.delenv("ETHERSCAN_TOKEN", raising=False)

    token = diffyscan_module._load_explorer_token({})

    assert token == "canonical-token"
    assert (
        'Config missing "explorer_token_env_var"; falling back to ETHERSCAN_EXPLORER_TOKEN',
    ) in warnings
    assert errors == []
