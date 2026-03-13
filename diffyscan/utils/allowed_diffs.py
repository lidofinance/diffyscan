from __future__ import annotations

import copy
import json
import os
from difflib import SequenceMatcher

import yaml

from .binary_verifier import slice_hex
from .calldata import normalize_calldata
from .logger import logger

_RULE_REASON_PLACEHOLDER = "TODO: explain why this diff is expected"
_BYTECODE_RULE_FIELDS = {
    "reason",
    "any",
    "immutables",
    "cbor_metadata",
    "byte_ranges",
    "constructor_args",
    "constructor_calldata",
}
_SOURCE_RULE_FIELDS = {"reason", "any", "files", "line_ranges"}


def validate_allowed_diffs_config(config: dict, path: str) -> None:
    allowed_diffs = config.get("allowed_diffs")
    if allowed_diffs is None:
        return
    if not isinstance(allowed_diffs, dict):
        raise ValueError(f"{path}: allowed_diffs must be a mapping")

    contracts = config.get("contracts", {})
    contract_addresses = {
        address.lower() for address in contracts if isinstance(address, str)
    }
    contract_original_case = {
        address.lower(): address for address in contracts if isinstance(address, str)
    }

    for diff_kind, entries_by_address in allowed_diffs.items():
        if diff_kind not in {"bytecode", "source"}:
            raise ValueError(
                f"{path}: allowed_diffs.{diff_kind} is not supported "
                "(expected bytecode or source)"
            )
        if not isinstance(entries_by_address, dict):
            raise ValueError(f"{path}: allowed_diffs.{diff_kind} must be a mapping")

        for address, entries in entries_by_address.items():
            if not isinstance(address, str):
                raise ValueError(
                    f"{path}: allowed_diffs.{diff_kind} address keys must be strings"
                )
            if contract_addresses and address.lower() not in contract_addresses:
                raise ValueError(
                    f"{path}: allowed_diffs.{diff_kind}.{address} is not present "
                    "in contracts"
                )
            original = contract_original_case.get(address.lower())
            if original and original != address:
                logger.warn(
                    f"allowed_diffs.{diff_kind} address {address} has different casing "
                    f"than contracts key {original}",
                )
            if not isinstance(entries, list) or not entries:
                raise ValueError(
                    f"{path}: allowed_diffs.{diff_kind}.{address} must be a non-empty list"
                )

            for index, entry in enumerate(entries, start=1):
                scope = f"{path}: allowed_diffs.{diff_kind}.{address}[{index}]"
                if diff_kind == "bytecode":
                    _validate_bytecode_rule_entry(entry, scope)
                else:
                    _validate_source_rule_entry(entry, scope)


def build_effective_allowed_diffs(
    config: dict,
    cli_source_addrs: list[str] | None = None,
    cli_bytecode_addrs: list[str] | None = None,
) -> dict:
    allowed_diffs = config.get("allowed_diffs") or {}
    effective: dict[str, dict[str, list[dict]]] = {"source": {}, "bytecode": {}}

    for diff_kind in ("source", "bytecode"):
        entries_by_address = allowed_diffs.get(diff_kind, {})
        if not isinstance(entries_by_address, dict):
            continue

        for address, entries in entries_by_address.items():
            normalized_address = address.lower()
            effective[diff_kind][normalized_address] = [
                _normalize_rule_entry(diff_kind, entry, origin="config")
                for entry in entries
            ]

    for diff_kind, addresses in (
        ("source", cli_source_addrs or []),
        ("bytecode", cli_bytecode_addrs or []),
    ):
        if not addresses:
            continue
        logger.warn(
            f"--allow-{diff_kind}-diff is deprecated",
            "move these rules into config.allowed_diffs",
        )
        for address in addresses:
            normalized_address = address.lower()
            if normalized_address in effective[diff_kind]:
                logger.warn(
                    f"Ignoring CLI --allow-{diff_kind}-diff for {address}",
                    "config.allowed_diffs takes precedence",
                )
                continue
            effective[diff_kind][normalized_address] = [
                {
                    "reason": f"CLI allow-{diff_kind}-diff",
                    "any": True,
                    "_origin": "cli",
                }
            ]

    return effective


def evaluate_source_rules(source_result: dict, rules: list[dict]) -> dict:
    if not source_result["has_diff"]:
        return {
            "status": "exact",
            "allowed": True,
            "matched_rule": None,
            "matched_facets": [],
        }

    for rule in rules:
        matched, facets = _matches_source_rule(source_result, rule)
        if matched:
            return {
                "status": "allowed",
                "allowed": True,
                "matched_rule": rule,
                "matched_facets": facets,
            }

    return {
        "status": "failed",
        "allowed": False,
        "matched_rule": None,
        "matched_facets": [],
    }


def evaluate_bytecode_rules(
    base_analysis: dict,
    rules: list[dict],
    analysis_provider,
) -> dict:
    if base_analysis["exact_match"]:
        return {
            "status": "exact",
            "allowed": True,
            "matched_rule": None,
            "matched_facets": [],
            "analysis": base_analysis,
            "best_analysis": base_analysis,
        }

    best_analysis = base_analysis

    for rule in rules:
        analysis = analysis_provider(rule)
        if _analysis_score(analysis) < _analysis_score(best_analysis):
            best_analysis = analysis

        matched, facets = _matches_bytecode_rule(analysis, rule)
        if matched:
            if "constructor_args" in rule:
                facets = [*facets, "constructor_args"]
            if "constructor_calldata" in rule:
                facets = [*facets, "constructor_calldata"]
            return {
                "status": "allowed",
                "allowed": True,
                "matched_rule": rule,
                "matched_facets": facets,
                "analysis": analysis,
                "best_analysis": best_analysis,
            }

    return {
        "status": "failed",
        "allowed": False,
        "matched_rule": None,
        "matched_facets": [],
        "analysis": base_analysis,
        "best_analysis": best_analysis,
    }


def normalize_source_hunks(
    github_lines: list[str], explorer_lines: list[str]
) -> list[dict]:
    matcher = _build_matcher(github_lines, explorer_lines)
    hunks = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            {
                "github": {"start": i1 + 1, "count": i2 - i1},
                "explorer": {"start": j1 + 1, "count": j2 - j1},
                "tag": tag,
            }
        )

    return hunks


def build_source_suggestion_entry(source_result: dict) -> dict | None:
    if not source_result["has_diff"]:
        return None

    entry: dict = {"reason": _RULE_REASON_PLACEHOLDER}
    file_suggestions = []
    line_ranges = []

    for file_result in source_result["files"]:
        if not file_result["hunks"]:
            continue

        if _is_full_file_insert_or_delete(file_result):
            file_suggestions.append(file_result["path"])
            continue

        for hunk in file_result["hunks"]:
            line_ranges.append(
                {
                    "file": file_result["path"],
                    "github": dict(hunk["github"]),
                    "explorer": dict(hunk["explorer"]),
                }
            )

    if file_suggestions:
        entry["files"] = sorted(file_suggestions)
    if line_ranges:
        entry["line_ranges"] = line_ranges

    if len(entry) == 1:
        return None
    return entry


def build_bytecode_suggestion_entry(analysis: dict) -> dict | None:
    if analysis["exact_match"]:
        return None

    entry: dict = {"reason": _RULE_REASON_PLACEHOLDER}
    runtime_ranges = analysis["runtime_mismatch_ranges"]
    runtime_is_all_immutable = bool(runtime_ranges) and all(
        range_info["immutable"] for range_info in runtime_ranges
    )

    if runtime_is_all_immutable:
        immutables = []
        for observed in analysis["immutable_observations"]:
            if observed["differs"]:
                immutables.append(
                    {
                        "offset": observed["offset"],
                        "value": observed["remote_value"],
                    }
                )
        if immutables:
            entry["immutables"] = immutables
    elif runtime_ranges:
        entry["byte_ranges"] = [
            {"offset": range_info["offset"], "length": range_info["length"]}
            for range_info in runtime_ranges
        ]

    if analysis["metadata_mismatch"]:
        entry["cbor_metadata"] = True

    if len(entry) == 1:
        entry["any"] = True

    return entry


def render_suggestion_snippet(
    config_path: str,
    diff_kind: str,
    address: str,
    entry: dict,
) -> str:
    payload = {"allowed_diffs": {diff_kind: {address: [entry]}}}
    extension = os.path.splitext(config_path)[1].lower()

    if extension == ".json":
        return json.dumps(payload, indent=2)

    return yaml.safe_dump(payload, sort_keys=False).strip()


def summarize_source_uncovered_hunks(source_result: dict) -> list[str]:
    summaries = []
    for file_result in source_result["files"]:
        for hunk in file_result["hunks"]:
            summaries.append(
                f"{file_result['path']} "
                f"github:{hunk['github']['start']}+{hunk['github']['count']} "
                f"explorer:{hunk['explorer']['start']}+{hunk['explorer']['count']}"
            )
    return summaries


def summarize_bytecode_uncovered(analysis: dict) -> list[str]:
    summaries = []
    if analysis["runtime_mismatch_ranges"]:
        for range_info in analysis["runtime_mismatch_ranges"]:
            label = f"offset={range_info['offset']} length={range_info['length']}"
            if range_info["immutable"]:
                label += " immutable"
            summaries.append(label)
    if analysis["metadata_mismatch"]:
        summaries.append("cbor_metadata")
    if analysis["string_literal_mismatch"]:
        summaries.append("string_literal")
    if analysis["length_mismatch"]:
        summaries.append("runtime_length")
    return summaries


def _validate_bytecode_rule_entry(entry: object, scope: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{scope} must be a mapping")
    _raise_unknown_keys(entry, _BYTECODE_RULE_FIELDS, scope)

    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{scope}.reason must be a non-empty string")

    _validate_any_field(entry, scope)

    facet_count = sum(
        key in entry
        for key in (
            "immutables",
            "cbor_metadata",
            "byte_ranges",
            "constructor_args",
            "constructor_calldata",
        )
    )
    if not entry.get("any") and facet_count == 0:
        raise ValueError(f"{scope} must declare at least one allowlist facet")

    if "constructor_args" in entry and "constructor_calldata" in entry:
        raise ValueError(
            f"{scope} cannot include both constructor_args and constructor_calldata"
        )

    if "cbor_metadata" in entry and entry["cbor_metadata"] is not True:
        raise ValueError(f"{scope}.cbor_metadata must be true when present")

    if "constructor_calldata" in entry:
        _validate_hex_string(
            entry["constructor_calldata"], f"{scope}.constructor_calldata"
        )

    immutables = entry.get("immutables")
    if immutables is not None:
        if not isinstance(immutables, list) or not immutables:
            raise ValueError(f"{scope}.immutables must be a non-empty list")
        seen_offsets = set()
        for index, immutable in enumerate(immutables, start=1):
            item_scope = f"{scope}.immutables[{index}]"
            if not isinstance(immutable, dict):
                raise ValueError(f"{item_scope} must be a mapping")
            if set(immutable) != {"offset", "value"}:
                raise ValueError(f"{item_scope} must only contain offset and value")
            offset = immutable.get("offset")
            if not isinstance(offset, int) or offset < 0:
                raise ValueError(f"{item_scope}.offset must be a non-negative integer")
            if offset in seen_offsets:
                raise ValueError(f"{scope}.immutables has a duplicate offset {offset}")
            seen_offsets.add(offset)
            _validate_hex_string(immutable.get("value"), f"{item_scope}.value")

    byte_ranges = entry.get("byte_ranges")
    if byte_ranges is not None:
        if not isinstance(byte_ranges, list) or not byte_ranges:
            raise ValueError(f"{scope}.byte_ranges must be a non-empty list")
        for index, range_entry in enumerate(byte_ranges, start=1):
            item_scope = f"{scope}.byte_ranges[{index}]"
            if not isinstance(range_entry, dict):
                raise ValueError(f"{item_scope} must be a mapping")
            if set(range_entry) != {"offset", "length"}:
                raise ValueError(f"{item_scope} must only contain offset and length")
            offset = range_entry.get("offset")
            length = range_entry.get("length")
            if not isinstance(offset, int) or offset < 0:
                raise ValueError(f"{item_scope}.offset must be a non-negative integer")
            if not isinstance(length, int) or length <= 0:
                raise ValueError(f"{item_scope}.length must be a positive integer")

    constructor_args = entry.get("constructor_args")
    if constructor_args is not None and not isinstance(constructor_args, list):
        raise ValueError(f"{scope}.constructor_args must be a list")


def _validate_source_rule_entry(entry: object, scope: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{scope} must be a mapping")
    _raise_unknown_keys(entry, _SOURCE_RULE_FIELDS, scope)

    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{scope}.reason must be a non-empty string")

    _validate_any_field(entry, scope)

    if not entry.get("any") and "files" not in entry and "line_ranges" not in entry:
        raise ValueError(f"{scope} must declare at least one allowlist facet")

    files = entry.get("files")
    if files is not None:
        if not isinstance(files, list) or not files:
            raise ValueError(f"{scope}.files must be a non-empty list")
        for index, file_path in enumerate(files, start=1):
            if not isinstance(file_path, str) or not file_path.strip():
                raise ValueError(
                    f"{scope}.files[{index}] must be a non-empty string path"
                )

    line_ranges = entry.get("line_ranges")
    if line_ranges is not None:
        if not isinstance(line_ranges, list) or not line_ranges:
            raise ValueError(f"{scope}.line_ranges must be a non-empty list")
        for index, line_range in enumerate(line_ranges, start=1):
            item_scope = f"{scope}.line_ranges[{index}]"
            if not isinstance(line_range, dict):
                raise ValueError(f"{item_scope} must be a mapping")
            if set(line_range) != {"file", "github", "explorer"}:
                raise ValueError(
                    f"{item_scope} must only contain file, github, and explorer"
                )
            file_path = line_range.get("file")
            if not isinstance(file_path, str) or not file_path.strip():
                raise ValueError(f"{item_scope}.file must be a non-empty string path")
            _validate_source_span(line_range.get("github"), f"{item_scope}.github")
            _validate_source_span(line_range.get("explorer"), f"{item_scope}.explorer")


def _normalize_rule_entry(diff_kind: str, entry: dict, origin: str) -> dict:
    normalized = copy.deepcopy(entry)
    normalized["_origin"] = origin

    if diff_kind == "bytecode":
        if "constructor_calldata" in normalized:
            normalized["constructor_calldata"] = normalize_calldata(
                normalized["constructor_calldata"]
            )
        if "immutables" in normalized:
            for immutable in normalized["immutables"]:
                immutable["value"] = _normalize_hex_string(
                    immutable["value"], prefix=True
                )
    return normalized


def _matches_source_rule(source_result: dict, rule: dict) -> tuple[bool, list[str]]:
    if rule.get("any"):
        return True, ["any"]

    allowed_files = set(rule.get("files", []))
    allowed_hunks = {
        _source_hunk_key(
            line_range["file"], line_range["github"], line_range["explorer"]
        )
        for line_range in rule.get("line_ranges", [])
    }

    for file_result in source_result["files"]:
        for hunk in file_result["hunks"]:
            if file_result["path"] in allowed_files:
                continue
            if (
                _source_hunk_key(file_result["path"], hunk["github"], hunk["explorer"])
                in allowed_hunks
            ):
                continue
            return False, []

    facets = []
    if allowed_files:
        facets.append("files")
    if allowed_hunks:
        facets.append("line_ranges")
    return True, facets


def _matches_bytecode_rule(analysis: dict, rule: dict) -> tuple[bool, list[str]]:
    if analysis["exact_match"]:
        return True, ["exact_match"]

    if rule.get("any"):
        return True, ["any"]

    if analysis["string_literal_mismatch"] or analysis["length_mismatch"]:
        return False, []

    if analysis["metadata_mismatch"] and not rule.get("cbor_metadata"):
        return False, []

    covered_offsets: set[int] = set()
    facets = []

    if "immutables" in rule:
        immutable_regions = analysis["immutable_regions"]
        remote_runtime = analysis["remote_runtime_bytecode"].removeprefix("0x")
        declared_offsets = set()
        for immutable in rule["immutables"]:
            offset = immutable["offset"]
            declared_offsets.add(offset)
            length = immutable_regions.get(offset)
            if length is None:
                return False, []
            expected_value = _normalize_hex_string(immutable["value"], prefix=False)
            if len(expected_value) != length * 2:
                return False, []
            observed_value = slice_hex(remote_runtime, offset, length)
            if observed_value.lower() != expected_value.lower():
                return False, []
            covered_offsets.update(range(offset, offset + length))

        if declared_offsets:
            facets.append("immutables")

    if "byte_ranges" in rule:
        for range_entry in rule["byte_ranges"]:
            start = range_entry["offset"]
            length = range_entry["length"]
            covered_offsets.update(range(start, start + length))
        facets.append("byte_ranges")

    for range_info in analysis["runtime_mismatch_ranges"]:
        if not set(
            range(range_info["offset"], range_info["offset"] + range_info["length"])
        ).issubset(covered_offsets):
            return False, []

    if analysis["metadata_mismatch"]:
        facets.append("cbor_metadata")

    return True, facets


def _analysis_score(analysis: dict) -> tuple[int, int, int, int]:
    mismatch_bytes = sum(
        range_info["length"] for range_info in analysis["runtime_mismatch_ranges"]
    )
    return (
        int(analysis["string_literal_mismatch"]),
        int(analysis["length_mismatch"]),
        mismatch_bytes,
        int(analysis["metadata_mismatch"]),
    )


def _source_hunk_key(file_path: str, github_span: dict, explorer_span: dict) -> tuple:
    return (
        file_path,
        github_span["start"],
        github_span["count"],
        explorer_span["start"],
        explorer_span["count"],
    )


def _is_full_file_insert_or_delete(file_result: dict) -> bool:
    if len(file_result["hunks"]) != 1:
        return False

    hunk = file_result["hunks"][0]
    github_count = hunk["github"]["count"]
    explorer_count = hunk["explorer"]["count"]

    if github_count == 0 and explorer_count == 0:
        return False

    return bool(
        (github_count == 0 and explorer_count == file_result["explorer_line_count"])
        or (explorer_count == 0 and github_count == file_result["github_line_count"])
    )


def _build_matcher(
    github_lines: list[str], explorer_lines: list[str]
) -> SequenceMatcher:

    return SequenceMatcher(None, github_lines, explorer_lines)


def _validate_any_field(entry: dict, scope: str) -> None:
    if "any" not in entry:
        return
    if entry["any"] is not True:
        raise ValueError(f"{scope}.any must be true when present")
    if set(entry) - {"reason", "any"}:
        raise ValueError(f"{scope} cannot combine any with other allowlist facets")


def _validate_source_span(span: object, scope: str) -> None:
    if not isinstance(span, dict):
        raise ValueError(f"{scope} must be a mapping")
    if set(span) != {"start", "count"}:
        raise ValueError(f"{scope} must only contain start and count")
    start = span.get("start")
    count = span.get("count")
    if not isinstance(start, int) or start < 1:
        raise ValueError(f"{scope}.start must be an integer >= 1")
    if not isinstance(count, int) or count < 0:
        raise ValueError(f"{scope}.count must be an integer >= 0")


def _raise_unknown_keys(entry: dict, allowed_keys: set[str], scope: str) -> None:
    unknown = sorted(set(entry) - allowed_keys)
    if unknown:
        raise ValueError(f"{scope} contains unsupported keys: {', '.join(unknown)}")


def _validate_hex_string(value: object, scope: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{scope} must be a hex string")
    try:
        _normalize_hex_string(value, prefix=False)
    except ValueError as exc:
        raise ValueError(f"{scope} {exc}") from exc


def _normalize_hex_string(value: str, prefix: bool = True) -> str:
    normalized = value.strip()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    if not normalized:
        raise ValueError("hex value cannot be empty")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError("value is not valid hex") from exc
    if len(normalized) % 2 != 0:
        raise ValueError("hex value must contain an even number of characters")
    normalized = normalized.lower()
    return f"0x{normalized}" if prefix else normalized
