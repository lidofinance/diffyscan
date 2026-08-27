# Configuration Reference

[Back to README](../README.md)

Diffyscan accepts JSON, YAML, and YML files. Working configurations are under
[`config_samples/`](../config_samples/).

```yaml
contracts:
  "0x6019cB557978296Ba3C08a7B73225C0975dfb2f7": CircuitBreaker

explorer_hostname: api.etherscan.io
explorer_chain_id: 1
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN
rpc_url_env_var: REMOTE_RPC_URL

github_repo:
  url: https://github.com/lidofinance/circuit-breaker
  commit: b4b2fbc921b3191560a3fc62d502d4bb98ad99e1
  relative_root: ""

dependencies: {}
fail_on_bytecode_comparison_error: true
```

## Core fields

| Field | Description |
| --- | --- |
| `contracts` | Map of deployed addresses to contract names |
| `explorer_hostname` | API hostname used to fetch verified source and compiler metadata |
| `explorer_chain_id` | Chain ID sent to explorers that support multi-chain requests |
| `explorer_token_env_var` | Environment variable that contains the explorer API token |
| `rpc_url_env_var` | Environment variable that contains the RPC URL; defaults to `REMOTE_RPC_URL` |
| `github_repo` | Repository URL, pinned commit, and source root expected to match the deployment |
| `dependencies` | Imported source trees pinned to their repositories and commits |
| `source_comparison` | Enables source comparison; defaults to `true` |
| `fail_on_bytecode_comparison_error` | Treats bytecode processing errors as failures; defaults to `true` |
| `deployment_gas_limit` | Optional gas limit for constructor simulation |
| `bytecode_comparison` | Manual constructor, library, caller, and source overrides |
| `allowed_diffs` | Expected source or bytecode differences, scoped by contract |

If `explorer_token_env_var` is absent, Diffyscan falls back to
`ETHERSCAN_EXPLORER_TOKEN`. Set the field when a config uses another explorer
or token.

## GitHub sources

`github_repo` pins the source being verified:

```yaml
github_repo:
  url: https://github.com/lidofinance/lido-dao
  commit: cadffa46a2b8ed6cfa1127fca2468bae1a82d6bf
  relative_root: ""
```

Use a full commit hash for reproducible verification. `relative_root` points to
the directory that corresponds to paths published by the explorer.

Add imported source trees under `dependencies`:

```yaml
dependencies:
  "@openzeppelin/contracts-v4.4":
    url: https://github.com/OpenZeppelin/openzeppelin-contracts
    commit: 6bd6b76d1156e20e45d1016f355d154141c7e5b9
    relative_root: contracts
```

The dependency key must match the imported path prefix.

## Environment variables

Diffyscan loads a local `.env` file before reading credentials. A standard run
needs:

- `GITHUB_API_TOKEN`;
- the token named by `explorer_token_env_var`;
- the RPC URL named by `rpc_url_env_var` when bytecode comparison is enabled.

Keep secrets and RPC credentials out of the config file.

## YAML addresses

Quote every hexadecimal address in YAML:

```yaml
contracts:
  "0x1111111111111111111111111111111111111111": Example
```

YAML parses an unquoted hexadecimal value as an integer. Diffyscan rejects
integer addresses in `contracts`, `bytecode_comparison`, and `allowed_diffs`
instead of using a changed value.

## Bytecode and allowed differences

See [Bytecode Comparison](bytecode-comparison.md) for
`bytecode_comparison`, linked libraries, constructor simulation, and
`allowed_diffs`.
