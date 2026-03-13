import json

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
)


def test_build_effective_allowed_diffs_prefers_config_over_cli():
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

    result = build_effective_allowed_diffs(
        config,
        cli_source_addrs=[],
        cli_bytecode_addrs=["0x0000000000000000000000000000000000000001"],
    )

    assert result["bytecode"]["0x0000000000000000000000000000000000000001"] == [
        {
            "reason": "config",
            "cbor_metadata": True,
            "_origin": "config",
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


# --- build_effective_allowed_diffs: CLI-only address ---


def test_build_effective_allowed_diffs_cli_only_address():
    config = {
        "contracts": {"0x0000000000000000000000000000000000000001": "Test"},
    }

    result = build_effective_allowed_diffs(
        config,
        cli_source_addrs=["0x0000000000000000000000000000000000000001"],
        cli_bytecode_addrs=[],
    )

    rules = result["source"]["0x0000000000000000000000000000000000000001"]
    assert len(rules) == 1
    assert rules[0]["any"] is True
    assert rules[0]["_origin"] == "cli"


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
