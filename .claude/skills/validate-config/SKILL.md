---
name: validate-config
description: Reviews an existing Diffyscan YAML or JSON config for load errors, runtime prerequisites, pinned sources, address mappings and broad exceptions. Use for config review or preflight validation; failed live runs belong to debug-diff and new deployment setup to new-config.
argument-hint: "[config-path]"
---

Validate the requested config without claiming static checks prove a deployment matches. Run commands from the repository root.

## 1. Load and inspect

Read the config, [configuration reference](../../../docs/configuration.md), `diffyscan/utils/common.py` and `diffyscan/utils/custom_types.py`. TypedDicts describe structure; they do not enforce it at runtime. Check the actual loader:

```sh
uv run python - path/to/config.yaml <<'PY'
import sys
from diffyscan.utils.common import load_config
load_config(sys.argv[1])
print("Config load passed")
PY
```

Then inspect what the loader does not fully validate:

- Nonempty `contracts`, string names and valid 20-byte hexadecimal addresses. Quote YAML hex keys and values, including nested overrides.
- `github_repo` and each dependency have `url`, a full commit SHA and `relative_root`. Dependency prefixes match published source paths. Repository config tests require `dependencies`, including when empty.
- An explicit explorer hostname or `explorer_hostname_env_var`; the runtime resolves the latter when the explicit hostname is absent. `network`, `audit_url` and `metadata` are optional descriptive fields.
- `get_explorer_chain_id` in `diffyscan/utils/explorer.py` converts the configured value with `int()`. Check that it identifies the intended chain; conversion alone does not validate a chain ID. Confirm the API and RPC agree; the CLI does not compare their chain IDs.
- Credential variable names and availability without printing values. Explorer token fallback is supported; an omitted token variable name is not inherently invalid. A token value is loaded even for adapters that do not send it.
- Boolean flags and enabled comparisons. `source_comparison: false` combined with `--skip-binary-comparison` is rejected.

## 2. Review overrides and exceptions

Read [bytecode comparison](../../../docs/bytecode-comparison.md). Cross-check per-contract keys against `contracts`; flag unused entries. Preserve exact address spelling for `constructor_args` and `constructor_calldata`: their runtime lookup is case-sensitive, unlike allowed-diff rules. Check calldata hex, argument list shapes, mutually exclusive constructor overrides, `deployment_from` addresses and `extra_sources` paths. Library keys identify the definition file and apply to all contracts in the config.

`load_config` validates `allowed_diffs` through `diffyscan/utils/allowed_diffs.py`. Schema validity does not justify a rule: inspect reason and scope. Use [allowed-diffs](../allowed-diffs/SKILL.md) when tightening or adding exceptions.

With bytecode comparison enabled, `fail_on_bytecode_comparison_error: false` lets outer per-contract errors continue, including explorer/source errors. With `--skip-binary-comparison`, that config flag is not applied. Caught bytecode errors produce failed results, except that a bytecode `any: true` rule marks `DeploymentSimulationError` as allowed.

For changes under `configs/`, run:

```sh
uv run pytest -q tests/test_configs.py tests/test_no_wildcard_regression.py
```

These tests inspect repository configs, not arbitrary files outside `configs/`. Loader success alone does not cover all schema fields, source availability, compiler reproduction or on-chain correctness.

## 3. Report

List concrete errors with config keys and locations, then evidence gaps or recommendations. Separate loader success, repository tests and live verification. If live verification was requested, run it with `--json` and inspect status, errors and coverage using [JSON output](../../../docs/json-output.md); otherwise report the static verdict and its limits. Edit the config only when the task includes fixes.

Treat placeholder-looking addresses and commits as unverified inputs, not proof that a fetch will fail. An empty `dependencies` map is not an error without evidence of unresolved imports: those sources may belong to the primary repository. Report supported defaults as defaults rather than missing-field findings, and keep a review-only answer focused on findings instead of rewriting a valid config.
