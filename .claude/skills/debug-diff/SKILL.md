---
name: debug-diff
description: Debug a failed diffyscan verification run. Analyzes diffs, identifies root causes, and suggests fixes. Use when diffyscan exits with non-zero or shows unexpected diffs.
argument-hint: [config-path-or-contract-address]
---

Help debug a failed diffyscan verification. The user may provide a config path, contract address, or describe the failure.

## Diagnostic steps

### 1. Check the digest output
Look in the most recent `digest/` subdirectory for:
- `logs.txt` — full run log
- `<address>/*.html` — source diff HTML reports

```bash
ls -lt digest/ | head -5
```

### 2. Identify the type of failure

**Source code diffs** — files differ between GitHub and explorer:
- Check if the GitHub commit in the config matches what was actually deployed
- Check if `relative_root` is correct (sources may be in a subdirectory)
- Check if dependencies have the right commits
- Look for import path mismatches (flat vs nested paths — may need `--support-brownie`)
- Check for compiler-injected metadata differences (shouldn't appear in source, but sometimes explorers normalize whitespace)

**Bytecode diffs** — compiled bytecode doesn't match on-chain:
- Missing or wrong `constructor_calldata` / `constructor_args`
- Missing libraries — check if the contract uses external libraries that need addresses in `bytecode_comparison.libraries`
- Wrong EVM version — the explorer may report a different version than expected
- Immutable variables — `deep_match_bytecode` should handle these, but complex immutables may fail
- Optimizer settings mismatch — the solc input from the explorer includes optimizer settings

**Compilation errors**:
- Missing GitHub sources — dependency not configured or wrong `relative_root`
- Solc version mismatch — check that the compiler version exists for the platform

**Network/API errors**:
- Explorer API rate limiting — try `--cache-explorer` to reuse cached responses
- RPC errors — check `REMOTE_RPC_URL` is valid and supports `eth_call`

### 3. Common fixes

| Symptom | Likely fix |
|---------|-----------|
| "missing GitHub sources" | Add missing dependency to `dependencies` in config |
| Source diffs in OZ imports | Check dependency commit hash matches |
| Bytecode mismatch after constructor | Add `constructor_args` or `constructor_calldata` for the contract |
| "library not found" | Add library addresses to `bytecode_comparison.libraries` |
| All files show diffs | Wrong `commit` or `relative_root` in `github_repo` |
| Single contract fails | May need per-contract `constructor_calldata` entry |

### 4. Suggest a re-run command
After fixing, suggest:
```bash
uv run diffyscan <config-path> --yes --cache-explorer --cache-github
```

Use `--cache-explorer` and `--cache-github` to avoid re-fetching unchanged data.
Use `--allow-source-diff 0xAddr` or `--allow-bytecode-diff 0xAddr` for known acceptable diffs.
