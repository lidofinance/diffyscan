---
name: debug-diff
description: Diagnoses failed or incomplete Diffyscan runs, unexpected source or bytecode differences, compilation failures and explorer or RPC errors. Use also when JSON reports error despite exit code 0. Explained exception changes belong to allowed-diffs; static config review belongs to validate-config.
argument-hint: "[config-path-or-contract-address]"
---

Find the cause while preserving requested verification scope. Run commands from the repository root.

## 1. Establish the failing run

Use the supplied JSON report and its `log_file`, or locate the digest matching the config, command and contract. Do not assume the newest digest belongs to the task. Read [JSON output](../../../docs/json-output.md) for status and partial-result semantics.

When a rerun is needed:

```sh
uv run diffyscan path/to/config.yaml --json -E -G --contract 0xADDRESS
```

Omit the filter for the full config. `--json` implies `--yes`; stdout is the report and tracebacks go to stderr. Read `status`, top-level and contract errors, comparison results and coverage. Exit code 0 alone is insufficient. Missing entries after an abort are not verified contracts. Distinguish an unmatched filter, an empty config and both comparisons disabled from success.

Caches accelerate diagnosis. Omit `-E` if explorer metadata may be stale; do not delete shared caches indiscriminately. Keep tokens and credential-bearing URLs out of shared output.

Use [diagnostic recipes](references/diagnostic-recipes.md) for locating digest evidence, recovering constructor calldata or following an error-specific check.

## 2. Trace the cause

Read [configuration](../../../docs/configuration.md) for prerequisites and [bytecode comparison](../../../docs/bytecode-comparison.md) for the trust model and overrides. Consult the relevant implementation:

| Evidence | Check next |
| --- | --- |
| Missing source or GitHub 404 | Commit, `relative_root` and import-prefix resolution in `diffyscan/utils/github.py`; distinguish a wrong path from a missing dependency. |
| Source hunks | Inspect report HTML and actual changes. Confirm deployment provenance before changing the pinned commit. Use `--support-brownie` only for flattened import-path resolution. |
| Compilation error | `run_bytecode_diff` in `diffyscan/diffyscan.py`, compiler/settings, dependencies, `extra_sources` and library definition paths. |
| Calldata or simulation error | `diffyscan/utils/calldata.py`, explorer metadata, constructor ABI, `deployment_from`, RPC state and `deployment_gas_limit`. Recover calldata from exact creation input and ABI, not an address substring or cross-chain address match. |
| Bytecode differences | `analyze_bytecode_diff` in `diffyscan/utils/binary_verifier.py` and evaluation in `diffyscan/utils/allowed_diffs.py`; inspect uncovered ranges, metadata, runtime length and immutable values. |
| Explorer error | Dispatch in `diffyscan/utils/explorer.py`, token lookup, response shape and verification status. A name mismatch may mean the wrong name, address or chain; it does not alone prove the contract is unverified. |
| HTTP challenge or RPC error | `diffyscan/utils/http_client.py`, `DIFFYSCAN_USER_AGENT`, endpoint availability, chain and supported RPC methods. |

Flattened submissions may lack settings needed to reproduce bytecode. Inspect the payload and compilation before attributing a mismatch to that limitation. Proxy immutable differences need an explanation for the observed values. Neither case alone justifies a wildcard or dropping bytecode verification.

Draft exception examples only for observed and explained differences. In particular, flattened source does not by itself establish a metadata mismatch: omit `cbor_metadata` unless that difference is evidenced. Leave unknown causes and values unresolved rather than filling them into a plausible `reason`.

## 3. Fix and verify

Make the smallest correction supported by evidence. For diagnosis-only requests, report it without editing. For intended differences, use [allowed-diffs](../allowed-diffs/SKILL.md). Keep unresolved contracts in scope instead of commenting them out or disabling comparisons to pass.

Rerun the affected contract after a fix, then the requested scope when available. Report root cause, evidence paths, changed fields, final statuses and unknowns. State any missing credentials or external dependency that prevented live confirmation.
