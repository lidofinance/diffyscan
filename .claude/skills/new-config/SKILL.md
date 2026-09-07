---
name: new-config
description: Creates or extends a Diffyscan verification config for a deployed contract or deployment. Use for adding addresses, pinning GitHub sources and dependencies, or setting up a chain in configs/. Existing failing runs belong to debug-diff; explorer adapter code belongs to add-explorer.
argument-hint: "[chain] [contract-address] [github-repo-url]"
disable-model-invocation: true
---

Create a reproducible config covering the requested deployment. Run commands from the repository root.

## 1. Establish the inputs

Read [configuration](../../../docs/configuration.md) and a nearby config under `configs/<project>/<mainnet|testnet>/`. Confirm the chain, addresses and names, expected GitHub commit, source root, and explorer/RPC selection from deployment records and the user's context. Ask for information that cannot be established; do not invent a commit or shrink the requested contract set.

Use [add-explorer](../add-explorer/SKILL.md) if the host needs routing or API support. Check current official explorer documentation before choosing an endpoint; an old config does not establish current API availability.

## 2. Write the config

Use YAML unless another format is requested. Quote addresses and hexadecimal values. Follow project naming and include:

- `contracts`: deployed address to explorer contract name;
- `explorer_hostname` or `explorer_hostname_env_var` (the explicit hostname takes precedence);
- `explorer_chain_id` when the chosen API needs it;
- `github_repo`: `url`, full commit SHA, and `relative_root`;
- `dependencies`: import-prefix mappings pinned to full commits, or `{}` for repository config tests.

`network` is optional descriptive metadata. Add other optional fields only when needed. Store credential environment-variable names, not secrets. Set `explorer_token_env_var` to an available token variable, or confirm the `ETHERSCAN_EXPLORER_TOKEN` fallback is available. The runtime loads an explorer token and `GITHUB_API_TOKEN` even for adapters that do not send the explorer token. Bytecode comparison also needs the configured RPC URL; confirm its chain.

Read [bytecode comparison](../../../docs/bytecode-comparison.md) before adding manual overrides. Prefer explorer constructor metadata when it describes the deployment; manual calldata is not required for every constructor. Set only one of `constructor_args` and `constructor_calldata` per address. Key libraries by their definition file; the mapping applies to every contract in the config. Use `deployment_from` for a constructor that depends on its caller and `extra_sources` for required GitHub files missing from the explorer source set.

For proxies, distinguish proxy and implementation addresses and confirm requested scope from deployment records and on-chain state. Obtain missing calldata from the creation trace and exact creation-bytecode boundary, then ABI-decode it. An address substring is not a reliable boundary; matching addresses across chains alone do not establish identical calldata.

If constructor metadata is missing, follow [calldata recovery](../debug-diff/references/diagnostic-recipes.md#missing-or-empty-constructor-calldata) before writing an override.

## 3. Verify and hand off

Apply [validate-config](../validate-config/SKILL.md), then run the requested verification when credentials are available:

```sh
uv run diffyscan path/to/config.yaml --json -E -G
```

Read [JSON output](../../../docs/json-output.md): check `status`, errors, contract coverage and enabled comparisons as well as the exit code. Caches help repeated diagnosis; omit `-E` when fresh explorer evidence is needed. For a failed run use [debug-diff](../debug-diff/SKILL.md); for explained exceptions use [allowed-diffs](../allowed-diffs/SKILL.md).

Keep unverified contracts visible as unresolved scope. Do not comment them out, disable comparison, or accept proxy immutables merely to obtain a passing run. Report config paths, deployment/source evidence, checks performed and unresolved verification.
