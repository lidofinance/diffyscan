---
name: new-config
description: Create a new diffyscan verification config file for a deployed smart contract. Use when the user wants to verify a new contract or deployment.
disable-model-invocation: true
argument-hint: [chain] [contract-address] [github-repo-url]
---

Create a new diffyscan config file for verifying a deployed smart contract. The user may provide some or all of these details — ask for anything missing.

## Required information

1. **Chain**: Which blockchain (ethereum, optimism, base, zksync, linea, scroll, mantle, bsc, lisk, soneium, unichain, ink, swell, megaeth, plasma, mode, etc.)
2. **Network**: mainnet or testnet (hoodi/holesky/sepolia for Ethereum)
3. **Contract address(es)**: One or more `0x`-prefixed addresses and their contract names
4. **GitHub repo**: URL, commit hash, and relative root within the repo
5. **Explorer**: hostname and token env var name

## Config schema

Use YAML format by default (supports comments for annotating addresses). JSON if user requests it.

The `Config` TypedDict is defined in `diffyscan/utils/custom_types.py`. Template for new configs:

```yaml
contracts:
  "0xAddress": ContractName

network: mainnet  # required in TypedDict but unused at runtime; include for forward-compatibility

explorer_hostname: api.etherscan.io
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
explorer_chain_id: 1  # activates Etherscan v2 API

github_repo:
  url: https://github.com/org/repo
  commit: "<full-40-char-sha>"
  relative_root: ""

dependencies: {}
```

Note: `explorer_token_env_var`, `explorer_chain_id`, and `dependencies` are `NotRequired` in the TypedDict but should always be included in new configs. `network` is required in the TypedDict.

YAML gotcha: addresses and hex strings MUST be quoted (`"0xabc..."`) — unquoted hex gets parsed as integers. The `load_config` function validates this and raises `ValueError` if coercion is detected.

## Optional fields (add only when needed)

- `dependencies` — map of import path prefix to `{url, commit, relative_root}`. Common: `@openzeppelin/contracts`, `@openzeppelin/contracts-upgradeable`, `lib/openzeppelin-contracts/contracts`
- `bytecode_comparison` — object with:
  - `constructor_calldata` — raw hex calldata per address: `{"0xAddr": "0xabcd..."}`
  - `constructor_args` — typed args per address: `{"0xAddr": ["0xarg1", true, 42]}`
  - `libraries` — per source path: `{"contracts/lib/Foo.sol": {"Foo": "0xLibAddr"}}`
  - `hardhat_config_name` — (deprecated) name of a hardhat config file
- `fail_on_bytecode_comparison_error` — set to `true` for strict mode
- `source_comparison` — set to `false` to skip source diffs (bytecode-only check)
- `explorer_hostname_env_var` — config convention for external CI/tooling to pass the explorer hostname via env var (used for soneium, unichain). Note: diffyscan itself does NOT resolve this at runtime — `get_explorer_hostname()` only reads `explorer_hostname`. External scripts must set `explorer_hostname` before invoking diffyscan.
- `audit_url` — optional link to an audit report for documentation purposes
- `metadata` — optional object for deployment metadata (e.g. `chain_name`, `deployment_date`, `timelock_address`, `timelock_requirements`)

## Explorer configuration

The code dispatches to different explorer backends based on the hostname pattern (see `_get_explorer_fetcher()` in `diffyscan/utils/explorer.py`):

### Etherscan v2 API (preferred for Etherscan-supported chains)

Use `api.etherscan.io` as the hostname with `explorer_chain_id` to activate the v2 API (`/v2/api?chainid=`). This works for any Etherscan-supported chain with a single API token.

```json
"explorer_hostname": "api.etherscan.io",
"explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN",
"explorer_chain_id": 1
```

Common chain IDs: Ethereum=1, Optimism=10, Base=8453, BSC=56, Linea=59144, Scroll=534352, Sepolia=11155111, Hoodi=560048, Holesky=17000, Ink=57073, MegaETH=4326.

### Legacy per-chain Etherscan hostnames (still work, used in older configs)

These are Etherscan-compatible and fall through to the default `_get_contract_from_etherscan` backend:

| Hostname | Token env var | Notes |
|---|---|---|
| `api-optimistic.etherscan.io` | `OPTISCAN_EXPLORER_TOKEN` | Optimism mainnet |
| `api.basescan.org` | `ETHERSCAN_EXPLORER_TOKEN` | Base mainnet |
| `api.lineascan.build` | `LINEA_EXPLORER_TOKEN` | Linea mainnet (special: token is ignored by dispatcher) |
| `api.scrollscan.com` | `ETHERSCAN_EXPLORER_TOKEN` (fallback) | Scroll mainnet |
| `api.bscscan.com` | `BSCSCAN_TOKEN` | BSC mainnet |
| `api-holesky.etherscan.io` | `ETHERSCAN_EXPLORER_TOKEN` | Holesky testnet |
| `api-hoodi.etherscan.io` | `ETHERSCAN_EXPLORER_TOKEN` | Hoodi testnet |
| `api-sepolia.etherscan.io` | `ETHERSCAN_EXPLORER_TOKEN` | Sepolia testnet |

**For new configs, prefer the v2 API approach** (`api.etherscan.io` + `explorer_chain_id`) over legacy per-chain hostnames.

### Non-Etherscan explorers (require their own hostname)

These are detected by hostname pattern and use different API backends:

| Type | Hostname pattern | Example hostnames | Token env var |
|---|---|---|---|
| zkSync | starts with `zksync` | `zksync2-mainnet-explorer.zksync.io` | (none needed) |
| Mantle | ends with `mantle.xyz` | `explorer.mantle.xyz`, `explorer.testnet.mantle.xyz` | (none needed) |
| Blockscout | ends with `blockscout.com`, `mode.network`, `swellnetwork.io`, `lisk.com`, `inkonchain.com`, `routescan.io`, `monadvision.com` | `blockscout.lisk.com`, `explorer.mode.network`, `explorer.swellnetwork.io`, `megaeth.blockscout.com`, `explorer.inkonchain.com` | Varies (some use API keys like `INK_API_KEY`, `MEGAETH_API_KEY`; some need none) |

Blockscout explorers use the `/api/v2/smart-contracts/{address}` endpoint. Some Blockscout-based explorers (ink, megaeth) also set `explorer_chain_id`.

**Note:** `api.routescan.io/v2/network/mainnet/evm/9745/etherscan` (used for Plasma) does NOT match the Blockscout dispatcher — the hostname ends with `etherscan`, not `routescan.io`. It falls through to the default Etherscan fetcher and uses `PLASMA_API_KEY`.

### `explorer_hostname_env_var` (CI convention only)

Some configs (soneium, unichain) use `explorer_hostname_env_var` instead of `explorer_hostname`. This is a convention for external CI/tooling — diffyscan's `get_explorer_hostname()` only reads `explorer_hostname` directly. External scripts must resolve the env var and set `explorer_hostname` before invoking diffyscan. For new configs, prefer hardcoding `explorer_hostname` directly unless there's a specific CI reason not to.

## File placement

Save configs to `config_samples/<chain>/<network>/` following existing naming conventions. Look at existing configs in that directory for patterns. Some older configs live directly under `config_samples/` (e.g. `lido_dao_holesky_config.json`) or under `config_samples/<chain>/` without a network subdirectory.

## Best practices

- **Use exact commit SHAs** — always use full 40-character commit hashes, never branch names or tags (they can change)
- **Enable bytecode comparison** — provide `constructor_calldata` or `constructor_args` for contracts with constructors so bytecode verification runs
- **Include `audit_url`** — link to the relevant audit report when available for cross-reference
- **Keep configs strict** — prefer explicit over implicit; include all fields even if optional, so verification is as thorough as possible

## Workflow

1. Gather required info from user (ask for missing pieces)
2. Look at existing configs in the same chain directory for reference patterns
3. Create the config file
4. Suggest running: `uv run diffyscan <config-path> --yes --cache-explorer --cache-github`
