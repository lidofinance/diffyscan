---
name: add-explorer
description: Add support for a new blockchain explorer API to diffyscan. Use when a new chain or explorer type needs to be supported.
disable-model-invocation: true
argument-hint: [explorer-name]
---

Guide through adding support for a new blockchain explorer to diffyscan.

## Decision tree: do you need code changes?

Most new chains need NO code changes. Work through this list in order:

1. **Etherscan v2 API (preferred)** -- If the chain is listed on Etherscan's v2 supported chains, create a config with `"explorer_hostname": "api.etherscan.io"` and `"explorer_chain_id": <chain-id>`. Done. No code changes. This uses the endpoint `https://api.etherscan.io/v2/api?chainid=<id>&module=contract&action=getsourcecode&address=<addr>`.

2. **Legacy Etherscan-compatible hostname** -- If the chain has its own Etherscan-style API (e.g. `api.basescan.org`, `api-optimistic.etherscan.io`), create a config with just `"explorer_hostname"` (no `explorer_chain_id`). The default fetcher handles it. No code changes.

3. **Existing Blockscout domain** -- If the chain uses a Blockscout instance whose domain already ends with one of the recognized suffixes (see dispatcher below), create a config with that hostname. No code changes.

4. **New Blockscout domain** -- If the chain uses Blockscout but with an unrecognized domain, add the domain suffix to `_get_explorer_fetcher()`. One-line change.

5. **Entirely new API format** -- Only if the explorer has a non-Etherscan, non-Blockscout API do you need a new fetcher function.

## Architecture: `diffyscan/utils/explorer.py`

All explorer logic lives in one file. The call flow is:

```
get_contract_from_explorer()          # public entry point, handles caching
  -> _get_explorer_fetcher()          # dispatcher: hostname -> (fetcher_fn, requires_token)
  -> fetcher(...)                     # one of the four fetchers below
  -> _validate_contract_name()        # verify name matches config
```

### The dispatcher: `_get_explorer_fetcher(explorer_hostname)`

This function maps hostnames to fetcher functions using prefix/suffix matching. It returns a tuple of `(fetcher_function, requires_token: bool)`.

Current routing rules (checked in order):

| Condition | Fetcher | Token required? |
|---|---|---|
| `hostname.startswith("zksync")` | `_get_contract_from_zksync` | No |
| `hostname.endswith("mantle.xyz")` | `_get_contract_from_mantle` | No |
| `hostname.endswith("lineascan.build")` | `_get_contract_from_etherscan` (token forced to `None`) | No |
| `hostname.endswith(...)` any of: `mode.network`, `blockscout.com`, `swellnetwork.io`, `lisk.com`, `inkonchain.com`, `routescan.io`, `monadvision.com` | `_get_contract_from_blockscout` | No |
| **Default (everything else)** | `_get_contract_from_etherscan` | **Yes** |

When `requires_token` is True, the caller passes `(token, hostname, address, chain_id)`. When False, the caller passes `(hostname, address)` only.

### Fetcher 1: `_get_contract_from_etherscan(token, hostname, address, chain_id=None)`

Handles both Etherscan v2 and legacy Etherscan APIs.

- **v2 endpoint** (when `chain_id` is set): `https://{hostname}/v2/api?chainid={chain_id}&module=contract&action=getsourcecode&address={address}&apikey={token}`
- **Legacy endpoint** (when `chain_id` is None): `https://{hostname}/api?module=contract&action=getsourcecode&address={address}&apikey={token}`
- Has built-in rate-limit retry logic (up to 5 retries with linear backoff)
- Response format: `{"message": "OK", "result": [{"ContractName": ..., "SourceCode": ..., "CompilerVersion": ..., ...}]}`
- If `SourceCode` starts with `{{`, it is treated as a JSON solc standard input (stripped of outer braces and parsed)
- Otherwise, `_build_source_files()` + `_build_solc_input()` construct the solc input from flat source

### Fetcher 2: `_get_contract_from_blockscout(hostname, address)`

- Endpoint: `https://{hostname}/api/v2/smart-contracts/{address}`
- No API token needed
- Response is a flat JSON object with fields: `name`, `file_path`, `source_code`, `additional_sources` (list of `{file_path, source_code}`), `compiler_version`, `compiler_settings`, `optimization_enabled`, `optimization_runs`, `constructor_args`, `evm_version`, `external_libraries` (list of `{name, address, ...}`)
- Note: the response uses both `optimization_runs` and `optimizations_runs` (typo in some Blockscout versions); the code checks both

### Fetcher 3: `_get_contract_from_zksync(hostname, address)`

- Endpoint: `https://{hostname}/contract_verification/info/{address}`
- No API token needed
- Response: `{"verifiedAt": ..., "request": {"ContractName": ..., "CompilerVersion": ..., "sourceCode": {"sources": ...}}}`
- Returns a minimal contract dict with `name`, `sources`, `compiler` -- does NOT go through `_build_contract_payload` or `_attach_contract_metadata`
- **Outlier:** Unlike the other fetchers, this does not return `solcInput`. Downstream code (`run_source_diff`, `run_bytecode_diff`) expects `contract["solcInput"]`, so zkSync contracts use a different code path. New fetchers should follow the standard shape returned by `_build_contract_payload` (`name`, `compiler`, `solcInput`, plus optional `constructor_arguments`, `evm_version`, `libraries`).

### Fetcher 4: `_get_contract_from_mantle(hostname, address)`

- Endpoint: `https://{hostname}/api?module=contract&action=getsourcecode&address={address}`
- No API token needed
- Etherscan-like response but uses `FileName` (not `ContractName`) as primary path, and `AdditionalSources` list uses `Filename`/`SourceCode` keys (note capitalization differences)

## Shared helpers

- **`_build_source_files(primary_path, primary_source, additional_sources, *, path_key, content_key)`** -- Assembles a `{path: {"content": source}}` dict. The `path_key` and `content_key` parameters handle the field name differences between explorers.
- **`_build_solc_input(source_files, *, optimizer_enabled, optimizer_runs, settings=None)`** -- Wraps source files into a standard solc JSON input with optimizer config and output selection.
- **`_build_contract_payload(name, compiler, solc_input, *, constructor_arguments, evm_version, libraries)`** -- Assembles the final contract dict and calls `_attach_contract_metadata()`.
- **`_attach_contract_metadata(contract, source_files, constructor_arguments, evm_version, libraries)`** -- Normalizes and attaches constructor args (hex string without 0x prefix), EVM version (None if "default"), and libraries (resolved to `{path: {name: address}}` format). Libraries can come from explorer response OR from `solcInput.settings.libraries`; both are merged.

## Steps: adding a new Etherscan v2 chain (no code changes)

1. Find the chain ID (e.g. from chainlist.org)
2. Create `config_samples/<chain>/<config>.json`:
   ```json
   {
     "contracts": { ... },
     "explorer_hostname": "api.etherscan.io",
     "explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN",
     "explorer_chain_id": <chain-id>,
     "github_repo": { ... }
   }
   ```
3. Test: `uv run diffyscan <config> --yes --cache-explorer`

## Steps: adding a new Blockscout domain

1. Add the domain suffix to the tuple in `_get_explorer_fetcher()` in `diffyscan/utils/explorer.py` (the `any(explorer_hostname.endswith(domain) for domain in [...])` block)
2. Create a config with `"explorer_hostname": "<blockscout-hostname>"`
3. Test: `uv run diffyscan <config> --yes --cache-explorer`

## Steps: adding a completely new explorer type

1. **Understand the API**: Document the endpoint URL, response shape, and which fields map to contract name, source code, compiler version, optimizer settings, constructor args, EVM version, and libraries.

2. **Add hostname detection** in `_get_explorer_fetcher()`: Add a new `elif` branch with `startswith()` or `endswith()` matching. Return `(your_fetcher, False)` -- most non-Etherscan explorers do not use API tokens.

3. **Implement the fetcher** `_get_contract_from_<name>(hostname, address)`:
   - Call the explorer API via `fetch(url).json()`
   - Validate response (check for verification status, required fields)
   - Use `_build_source_files()` to assemble sources (pass the correct `path_key`/`content_key` for the response format)
   - Use `_build_solc_input()` to wrap into solc input
   - Return via `_build_contract_payload()` to get normalized metadata
   - If the fetcher does not need a token, its signature should be `(hostname, address)` (two args). If it does need a token, use `(token, hostname, address, chain_id=None)` (four args) and set `requires_token=True` in the dispatcher.

4. **Add tests** in `tests/test_explorer_utils.py` -- follow the existing pattern: monkeypatch `fetch` to return a `DummyResponse`, call `get_contract_from_explorer()`, assert the result.

5. **Add a config sample** in `config_samples/<chain>/`.

## Config fields reference

| Field | Required | Description |
|---|---|---|
| `explorer_hostname` | Yes | API hostname (e.g. `api.etherscan.io`, `explorer.mode.network`) |
| `explorer_chain_id` | No | Chain ID for Etherscan v2 API; omit for legacy or non-Etherscan explorers |
| `explorer_token_env_var` | No | Env var name holding the API key (e.g. `ETHERSCAN_EXPLORER_TOKEN`) |

## Testing

- Unit tests: `tests/test_explorer_utils.py` -- monkeypatch `diffyscan.utils.explorer.fetch` and `CACHE_DIR`
- Integration: `uv run diffyscan <config> --yes --cache-explorer`
- The `--cache-explorer` flag caches responses to `.diffyscan_cache/` so repeated runs do not hit the API

## Checklist

- [ ] Determined whether code changes are actually needed (most chains: no)
- [ ] If Etherscan v2: config-only with `explorer_hostname` + `explorer_chain_id`
- [ ] If new Blockscout domain: added suffix to `_get_explorer_fetcher()` tuple
- [ ] If new API type: implemented fetcher, added dispatcher rule, used shared helpers
- [ ] Config sample created in `config_samples/<chain>/`
- [ ] Tests added in `tests/test_explorer_utils.py`
- [ ] `.env.example` updated if a new token env var is needed
