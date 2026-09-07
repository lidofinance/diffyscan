---
name: add-explorer
description: Adds or repairs Diffyscan explorer API routing and response adapters for a new host, chain or payload format. Use when explorer support is missing or dispatches incorrectly. If an existing adapter supports the deployment, continue with new-config instead of changing code.
argument-hint: "[explorer-name]"
disable-model-invocation: true
---

Find the smallest change that supports the requested explorer. Run commands from the repository root.

## 1. Decide whether code is needed

Read the supported-explorer section of [configuration](../../../docs/configuration.md) and `_get_explorer_fetcher` in `diffyscan/utils/explorer.py`. Check the actual host and current official API documentation or a response fixture; a legacy config does not prove current service availability.

1. Existing Etherscan-compatible API: use its supported endpoint configuration. Etherscan v2 uses `api.etherscan.io` plus `explorer_chain_id`.
2. Existing Blockscout host match: config-only. Unrecognized domains fall through to Etherscan, which may return incomplete sources rather than an immediate error.
3. New Blockscout host: use exact hostname equality for a single requested host. Add a separate exact-match branch if necessary; this does not require refactoring existing routes. Use a domain suffix only when subdomain support is part of the task, with a dot boundary. Test near-misses including `evil-<hostname>`; copying a permissive existing `endswith` pattern would silently broaden the new route.
4. Different response format: add an adapter and dispatch rule, with token behavior based on the API requirements.

For config-only work use [new-config](../new-config/SKILL.md). Avoid adding a fetcher for a chain already served by an existing one.

Read [response mapping](references/response-mapping.md) when implementing a fetcher or diagnosing lost source/settings fields; it covers payload keys, argument shapes and normalization pitfalls.

## 2. Implement and test

Inspect `get_contract_from_explorer`, the selected fetcher and helpers in `diffyscan/utils/explorer.py`. Dispatch returns `(fetcher, requires_token)`; the caller chooses arguments from that flag. Runtime token loading happens before dispatch, even when an adapter does not send a token.

Use `fetch` from `diffyscan/utils/http_client.py` to retain shared User-Agent and error handling. Normalize through existing helpers where applicable:

- `_build_source_files`: primary and additional sources;
- `_build_solc_input`: sources and compiler settings;
- `_build_contract_payload` and `_attach_contract_metadata`: name, compiler, `solcInput`, constructor arguments, EVM version and linked libraries.

Preserve available settings and source paths. Distinguish missing constructor metadata from an empty value; resolve libraries to defining files. The zkSync adapter currently returns `sources` without the `solcInput` required downstream: treat this as an existing compatibility gap, not a template.

Add mocked tests in `tests/test_explorer_utils.py` for dispatch, normalized payload, error/unverified responses and relevant metadata. Isolate cache use so prior responses cannot make the tests pass. A routing-only change still needs a regression test.

```sh
uv run pytest -q tests/test_explorer_utils.py tests/test_http_client.py
uv run mypy
uv run black --check diffyscan tests
```

For broader adapter changes run the full suite. With credentials and a deployment fixture, run `uv run diffyscan path/to/config.yaml --json` and inspect source and bytecode results using [JSON output](../../../docs/json-output.md). Mocked parsing tests do not prove end-to-end chain support.

## 3. Document the supported behavior

Update [configuration](../../../docs/configuration.md) when routing changes. Add a deployment config or `.env.example` entry only if needed for the task. Report behavior, tests and any unverified live integration.
