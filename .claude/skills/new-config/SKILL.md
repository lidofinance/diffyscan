---
name: new-config
description: Create a new diffyscan verification config file for a deployed smart contract. Use when the user wants to verify a new contract or deployment.
disable-model-invocation: true
argument-hint: [chain] [contract-address] [github-repo-url]
---

Create a new diffyscan config file for verifying a deployed smart contract. The user may provide some or all of these details — ask for anything missing.

## Required information

1. **Chain**: Which blockchain (ethereum, optimism, base, zksync, linea, scroll, mantle, bsc, etc.)
2. **Network**: mainnet or testnet (hoodi/holesky/sepolia for Ethereum)
3. **Contract address(es)**: One or more `0x`-prefixed addresses and their contract names
4. **GitHub repo**: URL, commit hash, and relative root within the repo
5. **Explorer**: hostname and token env var name

## Config schema

Use JSON format by default. YAML if user requests it.

```json
{
  "contracts": {
    "0xAddress": "ContractName"
  },
  "explorer_hostname": "api.etherscan.io",
  "explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN",
  "github_repo": {
    "url": "https://github.com/org/repo",
    "commit": "<full-commit-sha>",
    "relative_root": ""
  }
}
```

## Optional fields (add only when needed)

- `explorer_chain_id` — required for Blockscout explorers and chains where chain ID differs from default
- `dependencies` — map of import path prefix to `{url, commit, relative_root}`. Common: `@openzeppelin/contracts`, `@openzeppelin/contracts-upgradeable`
- `bytecode_comparison` — object with:
  - `constructor_calldata` — raw hex calldata per address: `{"0xAddr": "0xabcd..."}`
  - `constructor_args` — typed args per address: `{"0xAddr": ["0xarg1", true, 42]}`
  - `libraries` — per source path: `{"contracts/lib/Foo.sol": {"Foo": "0xLibAddr"}}`
- `fail_on_bytecode_comparison_error` — set to `true` for strict mode
- `source_comparison` — set to `false` to skip source diffs (bytecode-only check)

## Explorer hostnames by chain

| Chain      | Hostname                        | Token env var                  |
|------------|---------------------------------|--------------------------------|
| Ethereum   | api.etherscan.io                | ETHERSCAN_EXPLORER_TOKEN       |
| Optimism   | api-optimistic.etherscan.io     | OPTISCAN_EXPLORER_TOKEN        |
| Base       | api.basescan.org                | BASESCAN_EXPLORER_TOKEN        |
| BSC        | api.bscscan.com                 | BSCSCAN_TOKEN                  |
| Linea      | api.lineascan.build             | LINEASCAN_EXPLORER_TOKEN       |
| Scroll     | api.scrollscan.com              | SCROLLSCAN_EXPLORER_TOKEN      |
| zkSync     | block-explorer-api.mainnet.zksync.io | (no token needed)         |
| Mantle     | api.mantlescan.xyz              | MANTLESCAN_EXPLORER_TOKEN      |

For Blockscout-based explorers, set `explorer_chain_id` explicitly.

## File placement

Save configs to `config_samples/<chain>/<network>/` following existing naming conventions. Look at existing configs in that directory for patterns.

## YAML gotchas

If generating YAML: addresses and hex strings MUST be quoted (`"0xabc..."`) — unquoted hex gets parsed as integers by YAML.

## Workflow

1. Gather required info from user (ask for missing pieces)
2. Look at existing configs in the same chain directory for reference patterns
3. Create the config file
4. Suggest running: `uv run diffyscan <config-path> --yes --cache-explorer --cache-github`
