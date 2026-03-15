---
name: add-explorer
description: Add support for a new blockchain explorer API to diffyscan. Use when a new chain or explorer type needs to be supported.
disable-model-invocation: true
argument-hint: [explorer-name]
---

Guide through adding support for a new blockchain explorer to diffyscan.

## Architecture context

Explorer support lives in `diffyscan/utils/explorer.py`. The module handles multiple explorer API flavors:

1. **Etherscan-compatible** (most common) — standard `module=contract&action=getsourcecode` API
2. **Blockscout** — similar API but uses `chain_id` parameter and different response structure
3. **zkSync block-explorer-api** — different endpoint structure entirely
4. **Mantle** — Etherscan-compatible with minor differences

## Key functions to modify

1. **`get_contract_from_explorer()`** — main entry point that dispatches to the right fetcher based on hostname
2. **Response parsing** — each explorer type may return source code in different formats (standard JSON, single file, multi-file)
3. **`get_explorer_hostname()` / `get_explorer_chain_id()`** in the same module — may need hostname pattern matching

## Steps to add a new explorer

1. **Determine API compatibility**: Most EVM explorers are Etherscan-compatible. Check the explorer's API docs.

2. **If Etherscan-compatible**: Usually just need to:
   - Add the hostname to config samples
   - Test that existing parsing works
   - Add a sample config in `config_samples/<chain>/`

3. **If different API**: Need to:
   - Add detection logic in `get_contract_from_explorer()` (typically hostname-based)
   - Implement a new fetch function following existing patterns
   - Handle response format differences in source parsing
   - Add tests in `tests/test_explorer_utils.py`

4. **Add a config sample** in `config_samples/<chain>/` with the new explorer

## Testing

- Add unit tests for any new parsing logic in `tests/test_explorer_utils.py`
- Add a regression config in `config_samples/` for CI
- Test with `uv run diffyscan <config> --yes --cache-explorer`

## Checklist
- [ ] Explorer API response format understood
- [ ] Detection/dispatch logic added if needed
- [ ] Source code parsing handles the new format
- [ ] Constructor args / EVM version extraction works
- [ ] Config sample created
- [ ] Tests added
- [ ] `.env.example` updated with new token env var if needed
