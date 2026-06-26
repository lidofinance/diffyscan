import pytest

from diffyscan.diffyscan import _get_deployment_from
from diffyscan.utils.custom_exceptions import CalldataError


def test_get_deployment_from_returns_contract_specific_caller():
    binary_config = {
        "deployment_from": {
            "0x0000000000000000000000000000000000000001": (
                "0x0000000000000000000000000000000000000002"
            )
        }
    }

    assert (
        _get_deployment_from(
            binary_config, "0x0000000000000000000000000000000000000001"
        )
        == "0x0000000000000000000000000000000000000002"
    )


def test_get_deployment_from_returns_none_when_missing():
    assert (
        _get_deployment_from(
            {"deployment_from": {}}, "0x0000000000000000000000000000000000000001"
        )
        is None
    )


def test_get_deployment_from_rejects_invalid_caller():
    binary_config = {
        "deployment_from": {"0x0000000000000000000000000000000000000001": "0x1234"}
    }

    with pytest.raises(CalldataError, match="20-byte hex address"):
        _get_deployment_from(
            binary_config, "0x0000000000000000000000000000000000000001"
        )
