import json
import yaml
import pytest
from pathlib import Path

from diffyscan.utils.common import load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"

FULL_JSON_FIXTURE = FIXTURES_DIR / "full_config.json"
FULL_YAML_FIXTURE = FIXTURES_DIR / "full_config.yaml"

# Every top-level key found across all 113 config_samples
ALL_TOP_LEVEL_KEYS = {
    "contracts",
    "github_repo",
    "dependencies",
    "explorer_hostname",
    "explorer_token_env_var",
    "explorer_hostname_env_var",
    "explorer_chain_id",
    "bytecode_comparison",
    "allowed_diffs",
    "fail_on_bytecode_comparison_error",
    "audit_url",
    "metadata",
}


SAMPLE_CONFIG = {
    "contracts": {"0x0000000000000000000000000000000000000001": "TestContract"},
    "explorer_hostname": "api.etherscan.io",
    "explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN",
    "github_repo": {
        "url": "https://github.com/example/repo",
        "commit": "abc123",
        "relative_root": "",
    },
    "dependencies": {},
}


def test_load_json_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(SAMPLE_CONFIG))
    result = load_config(str(path))
    assert result == SAMPLE_CONFIG


def test_load_yaml_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(SAMPLE_CONFIG))
    result = load_config(str(path))
    assert result == SAMPLE_CONFIG


def test_load_yml_config(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text(yaml.dump(SAMPLE_CONFIG))
    result = load_config(str(path))
    assert result == SAMPLE_CONFIG


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("")
    with pytest.raises(ValueError, match="Unsupported config file extension"):
        load_config(str(path))


def test_yaml_and_json_produce_identical_config(tmp_path):
    json_path = tmp_path / "config.json"
    yaml_path = tmp_path / "config.yaml"
    json_path.write_text(json.dumps(SAMPLE_CONFIG))
    yaml_path.write_text(yaml.dump(SAMPLE_CONFIG))
    assert load_config(str(json_path)) == load_config(str(yaml_path))


def test_yaml_comments_are_ignored(tmp_path):
    """Comments are the whole reason we migrated to YAML — verify they parse cleanly."""
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
# Top-level comment
contracts:
  "0x0000000000000000000000000000000000000001": TransparentUpgradeableProxy # Vault
  "0x0000000000000000000000000000000000000002": Vault # implementation
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies:
  lib/foo:
    url: https://github.com/example/dep
    commit: def456
    relative_root: contracts
    # version 1.0.0
"""
    )
    result = load_config(str(path))
    assert (
        result["contracts"]["0x0000000000000000000000000000000000000001"]
        == "TransparentUpgradeableProxy"
    )
    assert result["contracts"]["0x0000000000000000000000000000000000000002"] == "Vault"
    # Ensure comments don't leak as keys
    assert "//" not in result
    assert "//" not in result["dependencies"]["lib/foo"]


def test_malformed_yaml_raises(tmp_path):
    """Invalid YAML should raise a clear error, not produce silent garbage."""
    path = tmp_path / "config.yaml"
    path.write_text("contracts:\n  bad: [unterminated\n")
    with pytest.raises(yaml.YAMLError):
        load_config(str(path))


def test_malformed_json_raises(tmp_path):
    """Invalid JSON should raise a clear error."""
    path = tmp_path / "config.json"
    path.write_text('{"contracts": {trailing comma,}}')
    with pytest.raises(json.JSONDecodeError):
        load_config(str(path))


def test_case_insensitive_extension(tmp_path):
    """Extensions like .YAML or .JSON should work since we lowercase."""
    yaml_path = tmp_path / "config.YAML"
    yaml_path.write_text(yaml.dump(SAMPLE_CONFIG))
    assert load_config(str(yaml_path)) == SAMPLE_CONFIG

    json_path = tmp_path / "config.JSON"
    json_path.write_text(json.dumps(SAMPLE_CONFIG))
    assert load_config(str(json_path)) == SAMPLE_CONFIG


def test_yaml_preserves_hex_address_strings(tmp_path):
    """YAML auto-coerces unquoted hex (0x1A -> int 26). Quoted addresses must stay strings."""
    path = tmp_path / "config.yaml"
    # Write raw YAML with quoted hex addresses to ensure they stay as strings
    path.write_text(
        """\
contracts:
  "0x00000000000000000000000000000000000000AB": TestContract
  "0x0000000000000000000000000000000000000100": AnotherContract
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
explorer_chain_id: 1
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies: {}
"""
    )
    result = load_config(str(path))
    addresses = list(result["contracts"].keys())
    for addr in addresses:
        assert isinstance(
            addr, str
        ), f"Address {addr!r} was coerced from string to {type(addr)}"
        assert addr.startswith("0x"), f"Address {addr!r} lost its 0x prefix"
    assert "0x00000000000000000000000000000000000000AB" in result["contracts"]
    assert "0x0000000000000000000000000000000000000100" in result["contracts"]
    # explorer_chain_id should remain an int
    assert isinstance(result["explorer_chain_id"], int)


def test_yaml_unquoted_hex_address_raises(tmp_path):
    """Unquoted hex addresses get coerced to int by PyYAML — load_config must catch this."""
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
contracts:
  0x00000000000000000000000000000000000000AB: TestContract
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies: {}
"""
    )
    with pytest.raises(ValueError, match="parsed as integer"):
        load_config(str(path))


def test_empty_yaml_raises(tmp_path):
    """An empty YAML file (or one with only comments) should raise, not return None."""
    path = tmp_path / "config.yaml"
    path.write_text("# just a comment\n")
    with pytest.raises(ValueError, match="empty or contains only comments"):
        load_config(str(path))


def test_bytecode_comparison_unquoted_hex_raises(tmp_path):
    """Unquoted hex in bytecode_comparison.constructor_args keys should be caught."""
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
contracts:
  "0x0000000000000000000000000000000000000001": TestContract
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies: {}
bytecode_comparison:
  constructor_args:
    0x00000000000000000000000000000000000000AB:
      - "0x01"
"""
    )
    with pytest.raises(ValueError, match="bytecode_comparison.constructor_args"):
        load_config(str(path))


def test_bytecode_comparison_library_unquoted_hex_raises(tmp_path):
    """Unquoted hex in bytecode_comparison.libraries values should be caught."""
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
contracts:
  "0x0000000000000000000000000000000000000001": TestContract
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies: {}
bytecode_comparison:
  libraries:
    "contracts/Foo.sol":
      MyLib: 0x00000000000000000000000000000000000000AB
"""
    )
    with pytest.raises(ValueError, match="bytecode_comparison.libraries"):
        load_config(str(path))


def test_allowed_diffs_unknown_address_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x00000000000000000000000000000000000000AB": [
                            {"reason": "bad", "any": True}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="is not present in contracts"):
        load_config(str(path))


def test_allowed_diffs_any_cannot_be_combined(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {
                                "reason": "bad",
                                "any": True,
                                "cbor_metadata": True,
                            }
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="cannot combine any"):
        load_config(str(path))


def test_allowed_diffs_constructor_args_and_calldata_are_mutually_exclusive(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {
                                "reason": "bad",
                                "constructor_args": ["0x01"],
                                "constructor_calldata": "0x01",
                            }
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(
        ValueError,
        match="cannot include both constructor_args and constructor_calldata",
    ):
        load_config(str(path))


def test_allowed_diffs_source_line_ranges_shape_is_validated(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "source": {
                        "0x0000000000000000000000000000000000000001": [
                            {
                                "reason": "bad",
                                "line_ranges": [
                                    {
                                        "file": "contracts/Foo.sol",
                                        "github": {"start": 0, "count": 1},
                                        "explorer": {"start": 1, "count": 1},
                                    }
                                ],
                            }
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="github.start must be an integer >= 1"):
        load_config(str(path))


def test_allowed_diffs_yaml_unquoted_address_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
contracts:
  "0x0000000000000000000000000000000000000001": TestContract
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_TOKEN
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies: {}
allowed_diffs:
  source:
    0x0000000000000000000000000000000000000001:
      - reason: generated file differs
        any: true
"""
    )
    with pytest.raises(
        ValueError, match="allowed_diffs.source address was parsed as integer"
    ):
        load_config(str(path))


def test_allowed_diffs_yaml_unquoted_immutable_hex_raises(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
contracts:
  "0x0000000000000000000000000000000000000001": TestContract
explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_TOKEN
github_repo:
  url: https://github.com/example/repo
  commit: abc123
  relative_root: ""
dependencies: {}
allowed_diffs:
  bytecode:
    "0x0000000000000000000000000000000000000001":
      - reason: immutable differs
        immutables:
          - offset: 0
            value: 0x0000000000000000000000000000000000000001
"""
    )
    with pytest.raises(
        ValueError,
        match="allowed_diffs.bytecode.0x0000000000000000000000000000000000000001\\[1\\].immutables\\[1\\].value",
    ):
        load_config(str(path))


# --- Full-fixture tests (max properties) ---


def test_full_json_fixture_loads():
    """The JSON fixture with every known property loads without error."""
    result = load_config(str(FULL_JSON_FIXTURE))
    assert ALL_TOP_LEVEL_KEYS <= set(result.keys())


def test_full_yaml_fixture_loads():
    """The YAML fixture with every known property (and comments) loads without error."""
    result = load_config(str(FULL_YAML_FIXTURE))
    assert ALL_TOP_LEVEL_KEYS <= set(result.keys())


def test_full_fixtures_produce_identical_dicts():
    """JSON and YAML full fixtures must produce the exact same dict."""
    json_result = load_config(str(FULL_JSON_FIXTURE))
    yaml_result = load_config(str(FULL_YAML_FIXTURE))
    assert json_result == yaml_result


def test_full_fixture_nested_types():
    """Verify types survive the round-trip for every nested structure."""
    result = load_config(str(FULL_YAML_FIXTURE))

    # contracts: all keys are hex strings, all values are strings
    for addr, name in result["contracts"].items():
        assert isinstance(addr, str) and addr.startswith(
            "0x"
        ), f"bad address key {addr!r}"
        assert isinstance(name, str), f"bad contract name {name!r}"

    # explorer_chain_id stays int
    assert result["explorer_chain_id"] == 1
    assert isinstance(result["explorer_chain_id"], int)

    # fail_on_bytecode_comparison_error stays bool
    assert result["fail_on_bytecode_comparison_error"] is True

    # bytecode_comparison.constructor_args values are lists of strings
    for addr, args in result["bytecode_comparison"]["constructor_args"].items():
        assert isinstance(args, list), f"constructor_args for {addr} should be list"
        for arg in args:
            assert isinstance(arg, str), f"constructor arg {arg!r} should be str"

    # bytecode_comparison.libraries nested dict of str -> str
    for path, libs in result["bytecode_comparison"]["libraries"].items():
        assert isinstance(libs, dict)
        for lib_name, lib_addr in libs.items():
            assert isinstance(lib_name, str)
            assert isinstance(lib_addr, str) and lib_addr.startswith("0x")

    for addr, rules in result["allowed_diffs"]["bytecode"].items():
        assert isinstance(addr, str) and addr.startswith("0x")
        assert isinstance(rules, list)
        for rule in rules:
            assert isinstance(rule["reason"], str)

    for src_rule in result["allowed_diffs"]["source"][
        "0x442af784A788A5bd6F42A01Ebe9F287a871243fb"
    ]:
        assert isinstance(src_rule["reason"], str)
        if "line_ranges" in src_rule:
            for line_range in src_rule["line_ranges"]:
                assert line_range["github"]["start"] >= 1
                assert line_range["explorer"]["count"] >= 0

    # metadata.timelock_requirements.minimum_delay_seconds stays int
    assert result["metadata"]["timelock_requirements"]["minimum_delay_seconds"] == 1
    assert isinstance(result["metadata"]["deployment_date"], str)


def test_full_fixture_yaml_comments_dont_create_extra_keys():
    """YAML fixture has many comments — none should leak as dict keys."""
    result = load_config(str(FULL_YAML_FIXTURE))

    def check_no_comment_keys(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert not str(k).startswith(
                    "#"
                ), f"comment leaked as key at {path}.{k}"
                assert str(k) != "//", f"JSON-style comment key at {path}.{k}"
                check_no_comment_keys(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_no_comment_keys(item, f"{path}[{i}]")

    check_no_comment_keys(result)


# --- allowed_diffs validation edge cases ---


def test_allowed_diffs_empty_immutables_list_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {"reason": "empty", "immutables": []}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="immutables must be a non-empty list"):
        load_config(str(path))


def test_allowed_diffs_byte_ranges_zero_length_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {
                                "reason": "bad range",
                                "byte_ranges": [{"offset": 0, "length": 0}],
                            }
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="length must be a positive integer"):
        load_config(str(path))


def test_allowed_diffs_unknown_keys_in_bytecode_entry_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {"reason": "bad", "cbor_metadata": True, "bogus_field": 1}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="unsupported keys"):
        load_config(str(path))


def test_allowed_diffs_unknown_keys_in_source_entry_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "source": {
                        "0x0000000000000000000000000000000000000001": [
                            {"reason": "bad", "files": ["A.sol"], "extra": "nope"}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="unsupported keys"):
        load_config(str(path))


def test_allowed_diffs_missing_reason_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {"cbor_metadata": True}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="reason must be a non-empty string"):
        load_config(str(path))


def test_allowed_diffs_no_facet_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "source": {
                        "0x0000000000000000000000000000000000000001": [
                            {"reason": "nothing else"}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="must declare at least one allowlist facet"):
        load_config(str(path))


def test_allowed_diffs_duplicate_immutable_offsets_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "bytecode": {
                        "0x0000000000000000000000000000000000000001": [
                            {
                                "reason": "dup",
                                "immutables": [
                                    {"offset": 10, "value": "0xab"},
                                    {"offset": 10, "value": "0xcd"},
                                ],
                            }
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="duplicate offset 10"):
        load_config(str(path))


def test_allowed_diffs_unsupported_diff_kind_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                **SAMPLE_CONFIG,
                "allowed_diffs": {
                    "storage": {
                        "0x0000000000000000000000000000000000000001": [
                            {"reason": "bad kind", "any": True}
                        ]
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="is not supported"):
        load_config(str(path))


# --- Boolean field validation ---


def test_source_comparison_string_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**SAMPLE_CONFIG, "source_comparison": "false"}))
    with pytest.raises(ValueError, match="source_comparison must be a boolean"):
        load_config(str(path))


def test_fail_on_bytecode_comparison_error_int_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({**SAMPLE_CONFIG, "fail_on_bytecode_comparison_error": 1})
    )
    with pytest.raises(
        ValueError, match="fail_on_bytecode_comparison_error must be a boolean"
    ):
        load_config(str(path))


def test_source_comparison_bool_accepted(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**SAMPLE_CONFIG, "source_comparison": False}))
    result = load_config(str(path))
    assert result["source_comparison"] is False
