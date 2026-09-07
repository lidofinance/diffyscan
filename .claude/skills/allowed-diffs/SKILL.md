---
name: allowed-diffs
description: Adds, reviews or tightens Diffyscan allowed_diffs rules for explained source or bytecode differences, including replacing any wildcards with granular rules. Use when accepting an expected diff or narrowing an exception; use debug-diff first if its cause is unknown.
---

Encode an explained difference without accepting unrelated drift. Run commands from the repository root.

## 1. Establish evidence

Read the target config, [bytecode comparison](../../../docs/bytecode-comparison.md) and [JSON output](../../../docs/json-output.md). Confirm chain, contract, pinned source and why the difference is intended. If unknown, use [debug-diff](../debug-diff/SKILL.md) before changing policy.

Use `suggested_rule` and actual diff evidence as a starting point. Suggestions describe observations; they do not justify accepting them. To replace a wildcard, remove only that rule for a diagnostic run or use a temporary config copy, then inspect uncovered differences. Preserve other rules and contract scope.

## 2. Choose a rule

Inspect `evaluate_source_rules`, `evaluate_bytecode_rules` and matchers in `diffyscan/utils/allowed_diffs.py` when coverage is unclear. Rules are alternatives: one rule must cover the differences; separate entries do not accumulate coverage. Combine necessary facets within one rule.

- Prefer source `line_ranges` for exact hunks. Coordinates are 1-based; `count: 0` represents insertion/deletion. `files` accepts future changes throughout named files.
- Prefer bytecode `immutables` with exact on-chain values at compiler-derived offsets when those values explain the difference. `byte_ranges` constrains offsets and lengths but does not pin values there.
- Add `cbor_metadata: true` for explained metadata differences, combined with other necessary facets in the same rule.
- Use `constructor_args` or `constructor_calldata` for an explained alternate simulation, respecting mutual exclusion. Verify the resulting runtime; an override alone does not prove a match.
- Runtime length and string-literal mismatches currently cannot be accepted by granular byte ranges. Report that limitation without silently widening an exception.

Every rule needs a concrete `reason` describing deployment evidence and intended scope. `any: true` excludes other facets and accepts future drift. Bytecode `any` can also suppress deployment-simulation errors, but not arbitrary compilation or calldata failures. Difficulty reproducing bytecode alone does not justify it. If a wildcard is justified within the requested policy change, document the limitation and align `KNOWN_WILDCARDS` in `tests/test_no_wildcard_regression.py`. Remove stale registry entries when removing wildcards; do not weaken the guard.

The exclusivity of `any` applies inside one `allowed_diffs` rule. A constructor override in the separate `bytecode_comparison` section can coexist with an `any` rule; that combination is broad policy, not a schema conflict.

## 3. Verify the result

Apply [validate-config](../validate-config/SKILL.md), then:

```sh
uv run pytest -q tests/test_allowed_diffs.py tests/test_no_wildcard_regression.py tests/test_configs.py
uv run diffyscan path/to/config.yaml --json -E -G
```

Confirm the intended contract is `allowed` or `exact`, matched reason/facets fit the change, and requested contracts and comparisons remain covered. Check JSON status and errors even with exit code 0. For a new granular rule, evaluate an unrelated hunk, byte offset or immutable value against the matcher and confirm it stays rejected, scoped to the rule's intended guarantees.

In the CLI JSON report, use `contracts[].bytecode.facets` and `.reason`; `matched_facets` and `matched_rule` are internal result fields, not report keys.

For a runnable immutable-rule check, adapt [the matcher example](references/check-immutable-rule.md). `evaluate_bytecode_rules` requires a callable analysis provider; each negative case must supply its changed analysis to that callback as well as to the base argument.

Report evidence, accepted scope, remaining drift protection and checks actually run. If live verification is unavailable, state that the rule has not been verified on chain.
