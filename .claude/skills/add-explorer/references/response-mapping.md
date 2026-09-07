# Explorer response mapping

Use this checklist when adapting a response fixture. Confirm behavior in `diffyscan/utils/explorer.py` before editing: these are the current parser assumptions, not a guarantee that an external endpoint remains available.

## Call and return contract

`get_contract_from_explorer` handles cache lookup, selects the fetcher, checks the contract name and saves the result. A token-using fetcher receives `(token, hostname, address, chain_id)`; a token-free fetcher receives `(hostname, address)`.

Return `name`, `compiler` and `solcInput` with `sources` and `settings`. Shared helpers attach `constructor_arguments`, `evm_version` and `libraries` when available. Test through the public entry point as well as any new parser helper, with an isolated cache.

## Etherscan

The adapter uses `/api` without chain ID and `/v2/api` with chain ID. It reads the first item in `result`, checks `message: NOTOK` and empty results, and handles rate limits through `_fetch_etherscan_response`.

| Response field | Use |
| --- | --- |
| `ContractName` | Expected name; also the source key for flattened input |
| `CompilerVersion` | Compiler selection |
| `SourceCode` starting with `{{` | Remove one outer brace pair and parse standard JSON |
| Other string `SourceCode` | Build one source under `ContractName`, with `OptimizationUsed` and `Runs` |
| `ConstructorArguments`, `EVMVersion`, `Library` | Normalize through `_build_contract_payload` |

The flattened Etherscan path does not retain arbitrary original settings or parse `AdditionalSources`. Do not assume it preserves remappings or via-IR. A source key without a file extension is a clue to inspect the original payload, not proof that bytecode cannot match.

## Blockscout

The adapter requests `/api/v2/smart-contracts/{address}`. Map primary `file_path` / `source_code` and each `additional_sources` item using those same keys. `name` and `compiler_version` supply identity and compiler.

Preserve `compiler_settings`; handle both `optimization_runs` and the fallback spelling `optimizations_runs`. Other inputs are `optimization_enabled`, `constructor_args`, `evm_version` and `external_libraries`.

Test absent name, absent primary source fields, multiple source files and relevant metadata. `constructor_args` being absent and being empty are different cases.

## Mantle and zkSync

Mantle reads Etherscan-style `result[0]`, but the primary source path is `FileName`; `AdditionalSources` entries use `Filename` and `SourceCode`. Preserve this capitalization distinction in fixtures.

The existing zkSync fetcher returns a different shape without `solcInput` and has inconsistent `contractName` / `ContractName` access. Do not copy these assumptions into a new adapter or claim the common comparison flow supports them without a reproducing test and a fix.

## Library normalization

`_attach_contract_metadata` merges libraries from explorer fields and `solcInput.settings.libraries`. Resolve a library to the file containing its definition, not a file importing it. Add fixtures for any new library response format and check that solc link references are satisfied.
