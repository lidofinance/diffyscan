---
name: validate-config
description: Validate a diffyscan config file for correctness before running verification. Checks schema, required fields, type correctness, and common mistakes.
argument-hint: [config-path]
---

Validate the diffyscan config file at `$ARGUMENTS` (or ask for the path if not provided).

Read the config file using the Read tool. Use the TypedDict definitions in `diffyscan/utils/custom_types.py` as the schema reference.

## Schema reference

The `Config` TypedDict (`diffyscan/utils/custom_types.py`) defines:

**Required fields:**
- `contracts` — `dict[str, str]` mapping address to contract name
- `network` — `str` (declared required in TypedDict but currently unused at runtime; include it for forward-compatibility)
- `explorer_hostname` — `str`
- `github_repo` — `GithubRepo` with required keys: `url`, `commit`, `relative_root`

**Optional fields (NotRequired):**
- `dependencies` — `dict[str, GithubRepo]`
- `explorer_token_env_var` — `str`
- `explorer_chain_id` — `int`
- `bytecode_comparison` — `BinaryConfig`
- `fail_on_bytecode_comparison_error` — `bool`
- `source_comparison` — `bool`

**Additional fields found in real configs but not in the TypedDict:**
- `explorer_hostname_env_var` — `str` (CI convention only — diffyscan does NOT resolve this at runtime; external tooling must set `explorer_hostname` before invoking)
- `audit_url` — `str`
- `metadata` — `dict` (free-form project metadata)

The `BinaryConfig` TypedDict has all-optional fields:
- `hardhat_config_name` — `str` (deprecated, ignored at runtime)
- `constructor_calldata` — `dict[str, str]` mapping address to raw hex calldata
- `constructor_args` — `dict[str, list]` mapping address to a list of ABI-encodable arguments
- `libraries` — `dict[str, dict[str, str]]` mapping source path to `{LibraryName: "0xAddress"}`

## Checks to perform

### 1. Required fields

- `contracts` must be present and be a non-empty dict
- `explorer_hostname` must be a string (or alternatively `explorer_hostname_env_var` must be present; real configs use one or both -- see `tests/test_configs.py` line 32)
- `github_repo` must be present and contain all three keys: `url`, `commit`, `relative_root`
- `network` is declared required in the TypedDict. Warn if missing, noting it is not used at runtime today but may be in the future

### 2. YAML hex coercion (what the codebase actually validates)

The function `_validate_yaml_hex_keys` in `diffyscan/utils/common.py` checks YAML configs for hex values that PyYAML silently coerced from strings to integers. It raises `ValueError` if any are found. Specifically it checks:

- **`contracts` keys** (address) -- raises if parsed as `int`
- **`contracts` values** (contract name) -- raises if parsed as `int`
- **`bytecode_comparison.constructor_args` keys** -- raises if parsed as `int`
- **`bytecode_comparison.constructor_calldata` keys** -- raises if parsed as `int`
- **`bytecode_comparison.libraries` values** (the library address strings) -- raises if parsed as `int`

This validation only runs for YAML files, not JSON. It only detects `int` coercion; it does NOT validate address format (0x prefix, 42 chars, valid hex, checksum).

### 3. Address format (best-practice recommendation only)

The codebase does NOT validate address format at config load time. There is no runtime check for 0x prefix, 42-character length, or hex validity on addresses in the config. Addresses are passed directly to the explorer API and RPC node.

However, the test suite (`tests/test_configs.py:test_contract_addresses_format`) asserts all `contracts` keys start with `0x` and are 42 characters. Recommend the same for any address in the config:
- Contract addresses in `contracts` keys
- Addresses in `bytecode_comparison.constructor_calldata` keys
- Addresses in `bytecode_comparison.constructor_args` keys
- Library addresses in `bytecode_comparison.libraries` values

### 4. Explorer configuration

- If `explorer_token_env_var` is missing, the runtime warns and falls back to `ETHERSCAN_EXPLORER_TOKEN` (see `_load_explorer_token` in `diffyscan/diffyscan.py`). Warn if absent.
- `explorer_chain_id` is optional; the runtime does not warn if missing (retrieved with `warn_if_missing=False`)
- `explorer_hostname` is retrieved with `warn_if_missing=True`; if absent the runtime logs a warning

### 5. GitHub repo fields

- `github_repo.url` should look like a GitHub URL
- `github_repo.commit` should ideally be a full 40-character SHA hex string (warn if short or non-hex)
- `github_repo.relative_root` can be an empty string (commonly is for root-level repos)

### 6. Dependencies

- Each dependency value must have `url`, `commit`, `relative_root` (same `GithubRepo` shape)
- Dependency keys should match import path prefixes used in Solidity sources (e.g. `@openzeppelin/contracts`, `lib/openzeppelin-contracts-upgradeable/contracts`)
- The runtime resolves dependencies by checking if a source file path starts with `"{dep_name}/"` (see `resolve_dep` in `diffyscan/utils/github.py`)

### 7. Bytecode comparison

- `constructor_calldata` values should be hex strings (the runtime strips `0x` prefix via `normalize_calldata` and validates hex content)
- `constructor_args` values must be lists (arrays of ABI-encodable values)
- A contract address must NOT appear in both `constructor_calldata` and `constructor_args` -- the runtime raises `CalldataError` if it does (see `get_calldata` in `diffyscan/utils/calldata.py`)
- `libraries` maps Solidity source file paths to `{LibraryName: "0xAddress"}` dicts
- `hardhat_config_name` is deprecated and ignored at runtime (a warning is logged)

### 8. Cross-reference checks

What the runtime actually does:
- Addresses in `bytecode_comparison.constructor_calldata` and `constructor_args` are looked up by contract address at runtime -- if a contract has a constructor but its address is not in either dict and the explorer has no constructor arguments, the runtime raises `CalldataError`
- Contracts listed in `contracts` that have no corresponding entry in `bytecode_comparison` will still work -- they fall back to explorer-provided constructor arguments
- There is no compile-time cross-reference validation in the codebase; all checks happen at runtime

Recommended cross-reference warnings:
- Warn if an address appears in `constructor_calldata` or `constructor_args` but not in `contracts` (it would be unused)
- Warn if a contract is in both `constructor_calldata` and `constructor_args` (runtime error)

### 9. Optional flags

- `fail_on_bytecode_comparison_error` defaults to `true` if absent
- `source_comparison` defaults to `true` if absent; set to `false` to skip source diffs

## Output

Report issues in two categories:
- **Errors** (must fix): missing required fields, type mismatches, YAML hex coercion, duplicate entries in both `constructor_calldata` and `constructor_args`
- **Warnings** (should review): missing `explorer_token_env_var`, short commit SHA, addresses not matching 0x/42-char format, missing `network`, deprecated `hardhat_config_name`, unused bytecode_comparison entries

If the config looks good, confirm it passes validation.
