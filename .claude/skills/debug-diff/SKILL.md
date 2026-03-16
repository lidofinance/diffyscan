---
name: debug-diff
description: Debug a failed diffyscan verification run. Analyzes diffs, identifies root causes. Use when diffyscan exits with non-zero or shows unexpected diffs.
argument-hint: [config-path-or-contract-address]
---

Help debug a failed diffyscan verification. The user may provide a config path, contract address, or describe the failure.

## Diagnostic steps

### 1. Check the digest output
Each run creates a timestamped directory under `digest/`. The timestamp is `int(time.time())` captured at process start (see `diffyscan/utils/constants.py`):
- `digest/{timestamp}/logs.txt` -- full run log (written by `Logger` in `diffyscan/utils/logger.py`)
- `digest/{timestamp}/diffs/{contract_address}/{filename}.html` -- per-file HTML source diff reports

Find the most recent run:
```bash
ls -lt digest/ | grep "^d" | head -5
```

Then inspect its contents:
```bash
# View the log
cat digest/<timestamp>/logs.txt

# List HTML diff reports for a specific contract
ls digest/<timestamp>/diffs/<contract_address>/
```

### 2. Identify the type of failure

**Source code diffs** -- files differ between GitHub and the blockchain explorer:
- Check if the `commit` in `github_repo` matches what was actually deployed
- Check if `relative_root` is correct (sources may live in a subdirectory of the repo)
- Check if entries in `dependencies` have the right `commit` hashes and `relative_root` paths
- Look for import path mismatches (flat vs nested -- may need `--support-brownie` for brownie-verified contracts)
- Open the HTML diff files (`digest/{timestamp}/diffs/{address}/*.html`) to see exactly which lines differ
- The report table in logs shows columns: `#`, `Filename`, `Found`, `Diffs`, `Origin`, `Report`

**Bytecode diffs** -- compiled bytecode does not match on-chain:
- Missing or wrong constructor arguments -- see `constructor_calldata` or `constructor_args` under the `bytecode_comparison` config key
- Missing libraries -- check if the contract uses external libraries that need addresses in `bytecode_comparison.libraries`
- Wrong EVM version -- the explorer may report a different version than expected
- Immutable variables -- `deep_match_bytecode()` in `diffyscan/utils/binary_verifier.py` compares instruction-by-instruction and tolerates differences that fall within known immutable reference regions. If all diffs are in immutable positions it logs a warning and returns `False` (still reported as a non-match — use `--allow-bytecode-diff 0xAddr` to accept). Differences outside immutable regions raise `BinVerifierError`
- Optimizer settings mismatch -- the solcInput from the explorer includes optimizer settings; the GitHub recompilation must match

**Compilation errors** (raised as `CompileError`):
- Missing GitHub sources -- a dependency is not configured or has a wrong `relative_root`. The error message is: `"missing GitHub sources for bytecode compilation; count=N; first=path1, path2..."` (from `run_bytecode_diff()` in `diffyscan/diffyscan.py`)
- Solc version mismatch -- check that the compiler version exists for the platform (solc binaries are cached in `~/.cache/diffyscan/solc/` or equivalent via `XDG_CACHE_HOME`)

**Constructor calldata errors** (raised as `CalldataError` from `diffyscan/utils/calldata.py`):
- `"No constructor calldata found for 0x... (not in config and not in explorer metadata)"` -- need to add `constructor_calldata` or `constructor_args` to the config
- `"Contract 0x... found in both 'constructor_args' and 'constructor_calldata'"` -- only one should be specified per contract

**Network/API errors**:
- Explorer API rate limiting -- try `--cache-explorer` to reuse cached responses (cached in `.diffyscan_cache/`)
- RPC errors -- check that `REMOTE_RPC_URL` env var is valid and the node supports `eth_call`
- Explorer token missing -- the config key `explorer_token_env_var` names the env var holding the API token; if absent, falls back to `ETHERSCAN_EXPLORER_TOKEN`

### 3. Common fixes

| Symptom | Likely fix |
|---------|-----------|
| `"missing GitHub sources for bytecode compilation"` | Add the missing dependency to `dependencies` in the config with correct `url`, `commit`, and `relative_root` |
| Source diffs in OpenZeppelin or other dependency imports | Check the dependency `commit` hash matches what was used at deploy time |
| Bytecode mismatch after constructor | Add `constructor_calldata` (raw hex) or `constructor_args` (ABI-typed values) for the contract under `bytecode_comparison` |
| `"Failed to infer source path for library '...' from explorer metadata"` | Add library addresses to `bytecode_comparison.libraries` keyed by `"path/to/File.sol": {"LibName": "0xAddr"}` |
| All files show diffs | Wrong `commit` or `relative_root` in `github_repo` |
| Single contract fails | May need a per-contract `constructor_calldata` or `constructor_args` entry |
| `"Bytecodes have differences not on the immutable reference position"` | Real bytecode mismatch -- check compiler version, optimizer settings, EVM version, and library addresses |
| `"Exiting with non-zero code due to unallowed diffs"` | Either fix the diffs or use `--allow-source-diff 0xAddr` / `--allow-bytecode-diff 0xAddr` for known acceptable diffs |

### 4. Suggest a re-run command
After fixing, suggest:
```bash
uv run diffyscan <config-path> --yes --cache-explorer --cache-github
```

- `--yes` (`-Y`) skips the interactive prompt before each contract
- `--cache-explorer` (`-E`) reuses cached explorer responses from `.diffyscan_cache/`
- `--cache-github` (`-G`) reuses cached GitHub file fetches
- `--support-brownie` enables recursive retrieval for brownie-verified contracts with flattened import paths
- `--allow-source-diff 0xAddr` accepts source diffs for a specific address (can be repeated)
- `--allow-bytecode-diff 0xAddr` accepts bytecode diffs for a specific address (can be repeated)
