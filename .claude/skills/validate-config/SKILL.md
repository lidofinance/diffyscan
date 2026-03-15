---
name: validate-config
description: Validate a diffyscan config file for correctness before running verification. Checks schema, addresses, required fields, and common mistakes.
argument-hint: [config-path]
---

Validate the diffyscan config file at `$ARGUMENTS` (or ask for the path if not provided).

## Checks to perform

### Required fields
- `contracts` — must be a non-empty dict of `"0x..." : "ContractName"` pairs
- `explorer_hostname` — must be a string
- `github_repo` — must have `url`, `commit`, `relative_root`
  - `commit` should be a full 40-char SHA (warn if short)
  - `url` should be a valid GitHub URL

### Address validation
- All contract addresses must start with `0x` and be 42 characters (20 bytes)
- Check for mixed case (EIP-55 checksummed is fine, but flag all-lowercase or obviously wrong)
- In YAML files: verify hex strings are quoted (unquoted `0x...` becomes an integer)

### Explorer configuration
- `explorer_token_env_var` should be present (warn if missing — falls back to ETHERSCAN_EXPLORER_TOKEN)
- `explorer_hostname` should match a known explorer pattern

### Dependencies
- Each dependency must have `url`, `commit`, `relative_root`
- Dependency keys should match import paths used in the Solidity sources

### Bytecode comparison
- `constructor_calldata` values should be hex strings starting with `0x`
- `constructor_args` values should be arrays
- `libraries` should be `{"source/path.sol": {"LibName": "0xAddr"}}`
- Library addresses must be valid 0x-prefixed 42-char strings

### Cross-references
- Addresses in `bytecode_comparison.constructor_calldata`, `constructor_args` must exist in `contracts`
- Warn about contracts in `contracts` that have no bytecode_comparison entry (they'll use explorer defaults — this is usually fine)

## Output

Report issues as errors (must fix) or warnings (should review). If the config looks good, confirm it.

Read the config file using the Read tool and the TypedDict definitions in `diffyscan/utils/custom_types.py` for reference.
