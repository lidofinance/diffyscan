# Check immutable-rule coverage

This synthetic check demonstrates one immutable plus metadata in a single rule. Adapt offsets, values and regions to the evidence. It tests rule semantics, not a deployment or the reason for accepting a difference. Run from the repository root:

```python
from diffyscan.utils.allowed_diffs import evaluate_bytecode_rules

rule = {
    "reason": "Synthetic fixture: one immutable and metadata",
    "immutables": [{"offset": 32, "value": "0x" + "11" * 32}],
    "cbor_metadata": True,
}
base = {
    "exact_match": False,
    "runtime_mismatch_ranges": [{"offset": 32, "length": 32, "immutable": True}],
    "metadata_mismatch": True,
    "string_literal_mismatch": False,
    "length_mismatch": False,
    "immutable_regions": {32: 32},
    "remote_runtime_bytecode": "0x" + "00" * 32 + "11" * 32 + "00" * 8,
}

def verdict(**changes):
    analysis = {**base, **changes}
    return evaluate_bytecode_rules(
        analysis, [rule], lambda _rule: analysis
    )["status"]

assert verdict() == "allowed"
assert verdict(remote_runtime_bytecode="0x" + "00" * 32 + "22" * 32 + "00" * 8) == "failed"
assert verdict(runtime_mismatch_ranges=[
    *base["runtime_mismatch_ranges"],
    {"offset": 64, "length": 1, "immutable": False},
]) == "failed"
assert verdict(immutable_regions={32: 31}) == "failed"
assert verdict(length_mismatch=True) == "failed"
assert verdict(string_literal_mismatch=True) == "failed"
```

For rules with constructor overrides, the provider needs the corresponding simulated analysis; returning the base analysis would not test that behavior. Use the matching patterns in `tests/test_allowed_diffs.py`.
