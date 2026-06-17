"""Guard against `any: true` wildcards creeping back into sample configs.

`allowed_diffs … any: true` is a blanket escape hatch: it suppresses *every*
diff for a contract, so it hides unexpected drift and provides no audit trail of
what actually differs. The granular facets (`immutables`, `byte_ranges`,
`cbor_metadata`, `line_ranges`, `files`) should be preferred.

A handful of wildcards are unavoidable today and are listed in
``KNOWN_WILDCARDS`` below, each with the reason it cannot be tightened. Any new
wildcard makes this test fail; either tighten the rule to a granular facet or,
if it is genuinely unavoidable, add it here with a justification (and ideally a
plan to remove it).
"""

from __future__ import annotations

import glob
import json
import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_GLOB = os.path.join(REPO_ROOT, "config_samples", "**", "*")

# (config path relative to config_samples, diff_kind, lowercased address) -> why
# it cannot currently be tightened to a granular facet.
KNOWN_WILDCARDS: dict[tuple[str, str, str], str] = {
    (
        "ethereum/hoodi/vaults/hoodi_vaults_testnet_config.json",
        "bytecode",
        "0x933b84d2c01b04c2f53cd2fb1b7055241e122c83",
    ): "V3TemporaryAdmin: testnet deployed an earlier V3 iteration; whole bytecode differs",
    (
        "ethereum/hoodi/vaults/hoodi_vaults_testnet_config.json",
        "bytecode",
        "0xe22486ea7ce77dae718ffa7b7114fd50cf73cbac",
    ): "V3VoteScript: testnet deployed an earlier V3 iteration; whole bytecode differs",
    (
        "ethereum/hoodi/vaults/hoodi_vaults_testnet_config.json",
        "bytecode",
        "0xd253b0ca059343e70474e685beb2974f10ccfa67",
    ): "V3Template: testnet deployed an earlier V3 iteration; whole bytecode differs",
    (
        "ethereum/hoodi/vaults/hoodi_vaults_testnet_config.json",
        "bytecode",
        "0x2f0303f20e0795e6ccd17bd5efe791a586f28e03",
    ): "DepositSecurityModule: constructor deployment reverts on testnet (eth_call), bytecode cannot be simulated",
}


def _load(path: str) -> dict | None:
    try:
        with open(path) as handle:
            data = (
                json.load(handle) if path.endswith(".json") else yaml.safe_load(handle)
            )
    except (json.JSONDecodeError, yaml.YAMLError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _iter_wildcards():
    for path in sorted(glob.glob(CONFIG_GLOB, recursive=True)):
        if not path.endswith((".json", ".yaml", ".yml")):
            continue
        data = _load(path)
        if not isinstance(data, dict):
            continue
        allowed_diffs = data.get("allowed_diffs") or {}
        rel = os.path.relpath(path, os.path.join(REPO_ROOT, "config_samples"))
        for diff_kind in ("source", "bytecode"):
            for address, rules in (allowed_diffs.get(diff_kind) or {}).items():
                if not isinstance(rules, list):
                    continue
                for rule in rules:
                    if isinstance(rule, dict) and rule.get("any") is True:
                        yield (rel, diff_kind, address.lower())


def test_no_unexpected_wildcard_allowed_diffs():
    found = set(_iter_wildcards())
    known = set(KNOWN_WILDCARDS)

    unexpected = sorted(found - known)
    assert not unexpected, (
        "Unexpected `allowed_diffs … any: true` wildcard(s) found. Tighten them "
        "to granular facets (immutables/byte_ranges/cbor_metadata/line_ranges/"
        "files), or add to KNOWN_WILDCARDS with a justification:\n"
        + "\n".join(f"  - {kind} {addr} in {cfg}" for cfg, kind, addr in unexpected)
    )

    stale = sorted(known - found)
    assert not stale, (
        "KNOWN_WILDCARDS lists entries that no longer exist (tightened or "
        "removed?). Delete these stale exceptions:\n"
        + "\n".join(f"  - {kind} {addr} in {cfg}" for cfg, kind, addr in stale)
    )
