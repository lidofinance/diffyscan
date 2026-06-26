import json

import pytest

from diffyscan.utils.allowed_diffs import (
    build_bytecode_suggestion_entry,
    build_effective_allowed_diffs,
    build_source_suggestion_entry,
    evaluate_bytecode_rules,
    evaluate_source_rules,
    normalize_source_hunks,
    render_suggestion_snippet,
    summarize_bytecode_uncovered,
    summarize_source_uncovered_hunks,
    validate_allowed_diffs_config,
)

ADDR = "0x0000000000000000000000000000000000000001"


def _config_with(diff_kind: str, rule: dict) -> dict:
    return {
        "contracts": {ADDR: "Test"},
        "allowed_diffs": {diff_kind: {ADDR: [rule]}},
    }


def test_build_effective_allowed_diffs_uses_config():
    config = {
        "contracts": {"0x0000000000000000000000000000000000000001": "Test"},
        "allowed_diffs": {
            "bytecode": {
                "0x0000000000000000000000000000000000000001": [
                    {"reason": "config", "cbor_metadata": True}
                ]
            }
        },
    }

    result = build_effective_allowed_diffs(config)

    assert result["bytecode"]["0x0000000000000000000000000000000000000001"] == [
        {
            "reason": "config",
            "cbor_metadata": True,
        }
    ]


def test_normalize_source_hunks_preserves_insert_replace_delete_spans():
    github_lines = ["a", "b", "c"]
    explorer_lines = ["a", "B", "c", "d"]

    hunks = normalize_source_hunks(github_lines, explorer_lines)

    assert hunks == [
        {
            "github": {"start": 2, "count": 1},
            "explorer": {"start": 2, "count": 1},
            "tag": "replace",
        },
        {
            "github": {"start": 4, "count": 0},
            "explorer": {"start": 4, "count": 1},
            "tag": "insert",
        },
    ]


def test_evaluate_source_rules_matches_files_and_exact_line_ranges():
    source_result = {
        "has_diff": True,
        "files": [
            {
                "path": "contracts/A.sol",
                "hunks": [
                    {
                        "github": {"start": 10, "count": 1},
                        "explorer": {"start": 10, "count": 1},
                    }
                ],
            },
            {
                "path": "contracts/generated/B.sol",
                "hunks": [
                    {
                        "github": {"start": 1, "count": 0},
                        "explorer": {"start": 1, "count": 12},
                    }
                ],
            },
        ],
    }
    rules = [
        {
            "reason": "expected",
            "line_ranges": [
                {
                    "file": "contracts/A.sol",
                    "github": {"start": 10, "count": 1},
                    "explorer": {"start": 10, "count": 1},
                }
            ],
            "files": ["contracts/generated/B.sol"],
        }
    ]

    evaluation = evaluate_source_rules(source_result, rules)
    assert evaluation["status"] == "allowed"
    assert set(evaluation["matched_facets"]) == {"files", "line_ranges"}


def test_evaluate_source_rules_rejects_shifted_hunks():
    source_result = {
        "has_diff": True,
        "files": [
            {
                "path": "contracts/A.sol",
                "hunks": [
                    {
                        "github": {"start": 10, "count": 1},
                        "explorer": {"start": 10, "count": 1},
                    }
                ],
            }
        ],
    }
    rules = [
        {
            "reason": "wrong span",
            "line_ranges": [
                {
                    "file": "contracts/A.sol",
                    "github": {"start": 11, "count": 1},
                    "explorer": {"start": 10, "count": 1},
                }
            ],
        }
    ]

    evaluation = evaluate_source_rules(source_result, rules)
    assert evaluation["status"] == "failed"


def test_build_source_suggestion_entry_prefers_files_for_missing_file():
    source_result = {
        "has_diff": True,
        "files": [
            {
                "path": "contracts/generated/BuildInfo.sol",
                "hunks": [
                    {
                        "github": {"start": 1, "count": 0},
                        "explorer": {"start": 1, "count": 4},
                    }
                ],
                "github_line_count": 0,
                "explorer_line_count": 4,
            },
            {
                "path": "contracts/A.sol",
                "hunks": [
                    {
                        "github": {"start": 2, "count": 1},
                        "explorer": {"start": 2, "count": 1},
                    }
                ],
                "github_line_count": 5,
                "explorer_line_count": 5,
            },
        ],
    }

    suggestion = build_source_suggestion_entry(source_result)

    assert suggestion == {
        "reason": "TODO: explain why this diff is expected",
        "files": ["contracts/generated/BuildInfo.sol"],
        "line_ranges": [
            {
                "file": "contracts/A.sol",
                "github": {"start": 2, "count": 1},
                "explorer": {"start": 2, "count": 1},
            }
        ],
    }


def test_evaluate_bytecode_rules_matches_exact_immutable_values():
    analysis = {
        "exact_match": False,
        "runtime_mismatch_ranges": [{"offset": 1, "length": 1, "immutable": True}],
        "metadata_mismatch": False,
        "string_literal_mismatch": False,
        "length_mismatch": False,
        "immutable_regions": {1: 1},
        "remote_runtime_bytecode": "0x6002fe",
        "immutable_observations": [
            {
                "offset": 1,
                "length": 1,
                "local_value": "0x01",
                "remote_value": "0x02",
                "differs": True,
            }
        ],
    }
    rules = [{"reason": "expected", "immutables": [{"offset": 1, "value": "0x02"}]}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda rule: analysis)

    assert evaluation["status"] == "allowed"
    assert evaluation["matched_facets"] == ["immutables"]


def test_evaluate_bytecode_rules_uses_constructor_override_analysis():
    base_analysis = {
        "exact_match": False,
        "runtime_mismatch_ranges": [{"offset": 10, "length": 2, "immutable": False}],
        "metadata_mismatch": False,
        "string_literal_mismatch": False,
        "length_mismatch": False,
        "immutable_regions": {},
        "remote_runtime_bytecode": "0x6001fe",
        "immutable_observations": [],
    }
    alt_analysis = {
        **base_analysis,
        "exact_match": True,
        "runtime_mismatch_ranges": [],
    }
    rules = [{"reason": "constructor override", "constructor_args": ["0x01"]}]

    calls = {"count": 0}

    def provider(rule):
        calls["count"] += 1
        return alt_analysis

    evaluation = evaluate_bytecode_rules(base_analysis, rules, provider)

    assert evaluation["status"] == "allowed"
    assert "constructor_args" in evaluation["matched_facets"]
    assert calls["count"] == 1


def test_build_bytecode_suggestion_entry_prefers_immutables_plus_metadata():
    analysis = {
        "exact_match": False,
        "runtime_mismatch_ranges": [{"offset": 1, "length": 1, "immutable": True}],
        "immutable_observations": [
            {
                "offset": 1,
                "length": 1,
                "local_value": "0x01",
                "remote_value": "0x02",
                "differs": True,
            }
        ],
        "metadata_mismatch": True,
        "string_literal_mismatch": False,
        "length_mismatch": False,
    }

    suggestion = build_bytecode_suggestion_entry(analysis)

    assert suggestion == {
        "reason": "TODO: explain why this diff is expected",
        "immutables": [{"offset": 1, "value": "0x02"}],
        "cbor_metadata": True,
    }


def test_render_suggestion_snippet_matches_file_extension():
    entry = {"reason": "expected", "any": True}

    json_snippet = render_suggestion_snippet(
        "config.json",
        "bytecode",
        "0x0000000000000000000000000000000000000001",
        entry,
    )
    yaml_snippet = render_suggestion_snippet(
        "config.yaml",
        "source",
        "0x0000000000000000000000000000000000000001",
        entry,
    )

    assert (
        json.loads(json_snippet)["allowed_diffs"]["bytecode"][
            "0x0000000000000000000000000000000000000001"
        ][0]["any"]
        is True
    )
    assert "allowed_diffs:" in yaml_snippet
    assert "source:" in yaml_snippet


# --- evaluate_source_rules: any rule ---


def test_evaluate_source_rules_any_allows_all_diffs():
    source_result = {
        "has_diff": True,
        "files": [
            {
                "path": "contracts/A.sol",
                "hunks": [
                    {
                        "github": {"start": 1, "count": 5},
                        "explorer": {"start": 1, "count": 3},
                    }
                ],
            }
        ],
    }
    rules = [{"reason": "blanket", "any": True}]

    evaluation = evaluate_source_rules(source_result, rules)
    assert evaluation["status"] == "allowed"
    assert evaluation["matched_facets"] == ["any"]


def test_evaluate_source_rules_exact_match_needs_no_rules():
    source_result = {"has_diff": False, "files": []}

    evaluation = evaluate_source_rules(source_result, [])
    assert evaluation["status"] == "exact"
    assert evaluation["allowed"] is True


# --- normalize_source_hunks: deletion case ---


def test_normalize_source_hunks_deletion():
    github_lines = ["a", "b", "c"]
    explorer_lines = ["a", "c"]

    hunks = normalize_source_hunks(github_lines, explorer_lines)

    assert hunks == [
        {
            "github": {"start": 2, "count": 1},
            "explorer": {"start": 2, "count": 0},
            "tag": "delete",
        }
    ]


# --- evaluate_bytecode_rules: byte_ranges ---


def _make_base_analysis(**overrides):
    base = {
        "exact_match": False,
        "runtime_mismatch_ranges": [],
        "metadata_mismatch": False,
        "string_literal_mismatch": False,
        "length_mismatch": False,
        "immutable_regions": {},
        "remote_runtime_bytecode": "0x6001fe",
        "immutable_observations": [],
    }
    base.update(overrides)
    return base


def test_evaluate_bytecode_rules_byte_ranges_covers_mismatch():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 5, "length": 3, "immutable": False}],
    )
    rules = [{"reason": "expected", "byte_ranges": [{"offset": 5, "length": 3}]}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "allowed"
    assert "byte_ranges" in evaluation["matched_facets"]


def test_evaluate_bytecode_rules_byte_ranges_partial_coverage_fails():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 5, "length": 4, "immutable": False}],
    )
    rules = [{"reason": "too narrow", "byte_ranges": [{"offset": 5, "length": 2}]}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "failed"


# --- evaluate_bytecode_rules: cbor_metadata only ---


def test_evaluate_bytecode_rules_metadata_only_allowed():
    analysis = _make_base_analysis(metadata_mismatch=True)
    rules = [{"reason": "metadata differs", "cbor_metadata": True}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "allowed"
    assert "cbor_metadata" in evaluation["matched_facets"]


def test_evaluate_bytecode_rules_metadata_without_rule_fails():
    analysis = _make_base_analysis(metadata_mismatch=True)
    rules = [{"reason": "wrong facet", "byte_ranges": [{"offset": 0, "length": 1}]}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "failed"


# --- evaluate_bytecode_rules: rejection cases ---


def test_evaluate_bytecode_rules_string_literal_mismatch_fails():
    analysis = _make_base_analysis(string_literal_mismatch=True)
    rules = [{"reason": "should fail", "cbor_metadata": True}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "failed"


def test_evaluate_bytecode_rules_length_mismatch_fails():
    analysis = _make_base_analysis(length_mismatch=True)
    rules = [{"reason": "should fail", "cbor_metadata": True}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "failed"


def test_evaluate_bytecode_rules_immutable_wrong_value_fails():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 1, "length": 1, "immutable": True}],
        immutable_regions={1: 1},
        remote_runtime_bytecode="0x6002fe",
    )
    rules = [{"reason": "wrong value", "immutables": [{"offset": 1, "value": "0x03"}]}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "failed"


def test_evaluate_bytecode_rules_immutable_wrong_offset_fails():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 1, "length": 1, "immutable": True}],
        immutable_regions={1: 1},
        remote_runtime_bytecode="0x6002fe",
    )
    # offset 0 is not an immutable region
    rules = [{"reason": "wrong offset", "immutables": [{"offset": 0, "value": "0x60"}]}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "failed"


# --- evaluate_bytecode_rules: any ---


def test_evaluate_bytecode_rules_any_allows_everything():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 0, "length": 3, "immutable": False}],
        metadata_mismatch=True,
        string_literal_mismatch=True,
    )
    rules = [{"reason": "blanket", "any": True}]

    evaluation = evaluate_bytecode_rules(analysis, rules, lambda r: analysis)
    assert evaluation["status"] == "allowed"
    assert evaluation["matched_facets"] == ["any"]


# --- evaluate_bytecode_rules: scoring / best_analysis ---


def test_evaluate_bytecode_rules_picks_best_analysis():
    base = _make_base_analysis(
        runtime_mismatch_ranges=[
            {"offset": 0, "length": 10, "immutable": False},
            {"offset": 20, "length": 5, "immutable": False},
        ],
    )
    better = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 0, "length": 2, "immutable": False}],
    )
    # Neither rule matches, but better analysis has fewer mismatch bytes
    rules = [
        {"reason": "rule1", "constructor_args": ["0x01"]},
        {"reason": "rule2", "constructor_args": ["0x02"]},
    ]

    call_count = {"n": 0}

    def provider(rule):
        call_count["n"] += 1
        return better if call_count["n"] == 1 else base

    evaluation = evaluate_bytecode_rules(base, rules, provider)
    assert evaluation["status"] == "failed"
    # best_analysis should be the one with fewer mismatch bytes
    best = evaluation["best_analysis"]
    total_bytes = sum(r["length"] for r in best["runtime_mismatch_ranges"])
    assert total_bytes == 2


# --- build_bytecode_suggestion: byte_ranges path ---


def test_build_bytecode_suggestion_entry_non_immutable_suggests_byte_ranges():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[
            {"offset": 10, "length": 4, "immutable": False},
            {"offset": 20, "length": 2, "immutable": False},
        ],
    )

    suggestion = build_bytecode_suggestion_entry(analysis)
    assert suggestion is not None
    assert suggestion["byte_ranges"] == [
        {"offset": 10, "length": 4},
        {"offset": 20, "length": 2},
    ]
    assert "immutables" not in suggestion


# --- build_bytecode_suggestion: any fallback ---


def test_build_bytecode_suggestion_entry_fallback_to_any():
    # string literal mismatch with no runtime or metadata issues
    analysis = _make_base_analysis(string_literal_mismatch=True)

    suggestion = build_bytecode_suggestion_entry(analysis)
    assert suggestion is not None
    assert suggestion["any"] is True
    assert "immutables" not in suggestion
    assert "byte_ranges" not in suggestion


# --- summarize helpers ---


def test_summarize_source_uncovered_hunks():
    source_result = {
        "files": [
            {
                "path": "A.sol",
                "hunks": [
                    {
                        "github": {"start": 5, "count": 2},
                        "explorer": {"start": 5, "count": 3},
                    },
                ],
            }
        ]
    }
    summaries = summarize_source_uncovered_hunks(source_result)
    assert len(summaries) == 1
    assert "A.sol" in summaries[0]
    assert "github:5+2" in summaries[0]


def test_summarize_bytecode_uncovered():
    analysis = _make_base_analysis(
        runtime_mismatch_ranges=[{"offset": 10, "length": 4, "immutable": True}],
        metadata_mismatch=True,
        string_literal_mismatch=True,
        length_mismatch=True,
    )
    summaries = summarize_bytecode_uncovered(analysis)
    assert any("offset=10" in s for s in summaries)
    assert "cbor_metadata" in summaries
    assert "string_literal" in summaries
    assert "runtime_length" in summaries


# --- validate_allowed_diffs_config: happy path ---


def test_validate_allowed_diffs_config_accepts_valid_rules():
    config = {
        "contracts": {ADDR: "Test"},
        "allowed_diffs": {
            "bytecode": {
                ADDR: [
                    {"reason": "meta", "cbor_metadata": True},
                    {
                        "reason": "imm",
                        "immutables": [{"offset": 0, "value": "0x00"}],
                    },
                ]
            },
            "source": {
                ADDR: [
                    {"reason": "files", "files": ["a.sol"]},
                    {
                        "reason": "lines",
                        "line_ranges": [
                            {
                                "file": "a.sol",
                                "github": {"start": 1, "count": 2},
                                "explorer": {"start": 1, "count": 2},
                            }
                        ],
                    },
                ]
            },
        },
    }
    validate_allowed_diffs_config(config, "cfg")  # should not raise


def test_validate_allowed_diffs_config_noop_without_block():
    validate_allowed_diffs_config({"contracts": {}}, "cfg")


# --- validate_allowed_diffs_config: structural errors ---


def test_validate_rejects_non_mapping_allowed_diffs():
    with pytest.raises(ValueError, match="must be a mapping"):
        validate_allowed_diffs_config({"allowed_diffs": []}, "cfg")


def test_validate_rejects_unknown_diff_kind():
    config = {"contracts": {ADDR: "T"}, "allowed_diffs": {"runtime": {}}}
    with pytest.raises(ValueError, match="not supported"):
        validate_allowed_diffs_config(config, "cfg")


def test_validate_rejects_address_not_in_contracts():
    config = {
        "contracts": {ADDR: "T"},
        "allowed_diffs": {
            "bytecode": {
                "0x0000000000000000000000000000000000000002": [
                    {"reason": "x", "any": True}
                ]
            }
        },
    }
    with pytest.raises(ValueError, match="not present"):
        validate_allowed_diffs_config(config, "cfg")


def test_validate_rejects_empty_rule_list():
    with pytest.raises(ValueError, match="non-empty list"):
        validate_allowed_diffs_config(
            {"contracts": {ADDR: "T"}, "allowed_diffs": {"bytecode": {ADDR: []}}},
            "cfg",
        )


def test_validate_rejects_missing_reason():
    with pytest.raises(ValueError, match="reason"):
        validate_allowed_diffs_config(_config_with("bytecode", {"any": True}), "cfg")


# --- validate_allowed_diffs_config: facet rules ---


def test_validate_rejects_any_combined_with_facet():
    rule = {"reason": "x", "any": True, "cbor_metadata": True}
    with pytest.raises(ValueError, match="cannot combine any"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_rule_without_any_facet():
    with pytest.raises(ValueError, match="at least one allowlist facet"):
        validate_allowed_diffs_config(_config_with("bytecode", {"reason": "x"}), "cfg")


def test_validate_rejects_constructor_args_and_calldata_together():
    rule = {
        "reason": "x",
        "constructor_args": [1],
        "constructor_calldata": "0x00",
    }
    with pytest.raises(ValueError, match="cannot include both"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_cbor_metadata_not_true():
    rule = {"reason": "x", "cbor_metadata": False}
    with pytest.raises(ValueError, match="cbor_metadata must be true"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_duplicate_immutable_offset():
    rule = {
        "reason": "x",
        "immutables": [
            {"offset": 4, "value": "0x00"},
            {"offset": 4, "value": "0x11"},
        ],
    }
    with pytest.raises(ValueError, match="duplicate offset"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_negative_immutable_offset():
    rule = {"reason": "x", "immutables": [{"offset": -1, "value": "0x00"}]}
    with pytest.raises(ValueError, match="non-negative integer"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_zero_length_byte_range():
    rule = {"reason": "x", "byte_ranges": [{"offset": 0, "length": 0}]}
    with pytest.raises(ValueError, match="positive integer"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_odd_length_hex_value():
    rule = {"reason": "x", "immutables": [{"offset": 0, "value": "0x000"}]}
    with pytest.raises(ValueError, match="even number"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_non_hex_calldata():
    rule = {"reason": "x", "constructor_calldata": "0xzz"}
    with pytest.raises(ValueError, match="not valid hex"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


def test_validate_rejects_unknown_rule_key():
    rule = {"reason": "x", "cbor_metadata": True, "bogus": 1}
    with pytest.raises(ValueError, match="unsupported keys"):
        validate_allowed_diffs_config(_config_with("bytecode", rule), "cfg")


# --- validate_allowed_diffs_config: source rules ---


def test_validate_rejects_line_range_start_below_one():
    rule = {
        "reason": "x",
        "line_ranges": [
            {
                "file": "a.sol",
                "github": {"start": 0, "count": 1},
                "explorer": {"start": 1, "count": 1},
            }
        ],
    }
    with pytest.raises(ValueError, match="start must be an integer >= 1"):
        validate_allowed_diffs_config(_config_with("source", rule), "cfg")


def test_validate_rejects_empty_files_list():
    rule = {"reason": "x", "files": []}
    with pytest.raises(ValueError, match="files must be a non-empty list"):
        validate_allowed_diffs_config(_config_with("source", rule), "cfg")


# --- suggestion edge cases ---


def test_build_source_suggestion_entry_returns_none_without_diff():
    assert build_source_suggestion_entry({"has_diff": False, "files": []}) is None


def test_build_bytecode_suggestion_entry_metadata_only_is_not_wildcard():
    analysis = _make_base_analysis(metadata_mismatch=True)
    entry = build_bytecode_suggestion_entry(analysis)
    assert entry is not None
    assert entry == {"reason": entry["reason"], "cbor_metadata": True}
    assert "any" not in entry


def test_render_suggestion_snippet_reason_only_entry_roundtrips():
    entry = {"reason": "because", "any": True}
    snippet = render_suggestion_snippet("cfg.json", "bytecode", ADDR, entry)
    assert json.loads(snippet)["allowed_diffs"]["bytecode"][ADDR] == [entry]
