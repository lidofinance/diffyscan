# Diagnostic recipes

Use the relevant section for an observed failure. Commands run from the repository root; replace placeholders with the target run's values.

## Locate the evidence

Each run writes `digest/<timestamp>/logs.txt` and source HTML under `digest/<timestamp>/diffs/<address>/`. Prefer the JSON report's `log_file` and source `diffs[].report` fields. If only a config path is known:

```sh
rg -l --fixed-strings 'Loading config path/to/config.yaml' digest -g logs.txt
rg --files digest/<timestamp>/diffs/<address>
```

Compare candidate logs with the requested command, config and contract. A newer unrelated run does not replace the failing run's evidence.

## Missing or empty constructor calldata

1. Inspect the constructor ABI and saved explorer metadata. `get_calldata` skips argument handling when the ABI has no constructor inputs. With inputs, an absent metadata value and an empty hex value lead to different diagnostics.
2. Check manual `constructor_args` and `constructor_calldata` for the exact address spelling used in `contracts`. They are mutually exclusive and override explorer calldata.
3. If metadata is insufficient, identify the creation transaction for this chain/address from deployment records or the explorer's creation API. Obtain a creation trace when the RPC supports it; with `callTracer`, locate the relevant CREATE/CREATE2 frame, including internal factory calls.
4. Match the frame to the target deployment. Separate its input into exact linked creation bytecode and ABI-encoded arguments using the matching build artifact. Do not treat a matching address substring as the boundary.
5. Decode and re-encode the arguments against the constructor ABI; verify they account for the complete argument suffix. Compare deployer/caller and deployment records. Same-address deployments on other chains are corroborating evidence only after their creation inputs are established.
6. Set one manual override if needed, then rerun bytecode comparison. Use `deployment_from` when constructor behavior depends on `msg.sender`. Missing traces or matching artifacts leave recovery unresolved.

For a proxy, separately establish proxy and implementation identity from deployment records and the proxy's on-chain mechanism. Checking the implementation address does not verify either contract's source or bytecode by itself.

Distinguish CREATE from CREATE2 when reasoning about cross-chain addresses. CREATE2 binds the factory address, salt and hash of the complete initcode, including appended constructor arguments, as specified in [EIP-1014](https://eips.ethereum.org/EIPS/eip-1014). With factory and salt fixed, changing those arguments changes the derived address under the usual hash-collision assumption. Equal addresses alone do not establish the creation mechanism or inputs; identical initcode can also execute against different chain state.

## Error-to-check map

| Error or observation | Concrete next check |
| --- | --- |
| `missing GitHub sources for bytecode compilation` | Inspect the listed paths against commit, `relative_root` and dependency prefixes. Use `extra_sources` only for required files absent from the explorer set. |
| `Failed to infer source path for library` or `unlinked libraries` | Locate the library declaration and solc link references; correct the definition-file key and address. |
| Constructor address in both override maps | Keep the one supported by deployment evidence; match address casing to `contracts`. |
| `intrinsic gas too low` during simulation | Inspect the request gas cap and chain/RPC limits; use a supported `deployment_gas_limit` instead of disabling bytecode comparison. |
| Contract-name mismatch | Compare requested address, chain, config name and returned name; establish verification status separately. |
| Immutable mismatch | Map the exact offset/value to compiler immutable references and deployment behavior. Use a justified exact-value rule only after explaining the difference. |
| Clean source diff but bytecode mismatch | Compare compiler version, settings, EVM version, linked libraries and constructor simulation; clean source alone does not prove bytecode. |

For flattened source, inspect how `_get_contract_from_etherscan` reconstructs `solcInput`: only basic optimizer settings are retained in that path. Missing original settings are a possible reproduction gap, not automatic justification for a wildcard. Preserve the gap in the result if it cannot be resolved.
