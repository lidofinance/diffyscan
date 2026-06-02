# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Diffyscan

Diffyscan verifies deployed EVM smart contracts match their GitHub source by:
1. Fetching verified source from blockchain explorers (Etherscan, Blockscout, zkSync, Mantle)
2. Diffing against GitHub repo sources (HTML diff reports saved to `digest/`)
3. Optionally recompiling from GitHub and comparing bytecode against on-chain bytecode, handling constructor args, libraries, and immutable references

## Commands

```bash
# Install dependencies
uv sync --locked --group dev

# Run tests
uv run pytest -q

# Run a single test
uv run pytest tests/test_config_loading.py -q
uv run pytest tests/test_config_loading.py::test_name -q

# Run the CLI
uv run diffyscan config_samples/lido_dao_sepolia_config.json

# Format code
uv run black diffyscan/ tests/

# Run pre-commit hooks
uv run pre-commit run --all-files

# Install git hooks (pre-commit + commit-msg via gitlint)
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Architecture

Entry point: `diffyscan/diffyscan.py:main` — parses CLI args, loads config (JSON or YAML), then runs source diff and bytecode diff for each contract.

### Core flow

`process_config()` orchestrates per-config:
- `run_source_diff()` — fetches explorer sources and GitHub sources, generates HTML diffs via `difflib.HtmlDiff`
- `run_bytecode_diff()` — compiles GitHub sources with solc, simulates deployment via `eth_call`, compares bytecode

### Utility modules (`diffyscan/utils/`)

- **explorer.py** — largest module; fetches/parses contracts from blockchain explorers, handles multi-chain API differences, library detection, EVM version normalization, solc compilation
- **github.py** — GitHub API integration, file fetching with caching, dependency resolution (e.g. `@openzeppelin/contracts-v4.4`)
- **binary_verifier.py** — EVM bytecode parsing into instructions, metadata trimming, deep comparison with immutable region exclusion
- **compiler.py** — solc binary download (platform-aware), SHA256 verification, compilation via standard JSON
- **encoder.py** — ABI encoding for constructor arguments (address, bool, int/uint, bytes, tuples, arrays)
- **calldata.py** — resolves constructor calldata from config or explorer metadata
- **node_handler.py** — RPC calls: `eth_getCode`, `eth_chainId`, `eth_call`
- **common.py** — config loading (with YAML hex address validation), HTTP helpers, caching with SHA256 validation
- **custom_types.py** — TypedDict definitions: `Config`, `BinaryConfig`, `ExplorerContract`, `GithubRepo`
- **custom_exceptions.py** — exception hierarchy; `ExceptionHandler` controls fail-or-log behavior

### Config schema

Configs live in `config_samples/` organized by chain (ethereum, optimism, zksync, etc.):
```
contracts:          { "0xaddr": "ContractName" }
network:            "mainnet"  # required in TypedDict, unused at runtime
explorer_hostname:  "api.etherscan.io"
explorer_token_env_var: "ETHERSCAN_EXPLORER_TOKEN"
github_repo:        { url, commit, relative_root }
dependencies:       { "dep_name": { url, commit, relative_root } }
bytecode_comparison: { constructor_calldata, constructor_args, libraries }
```

### Environment variables

Supports loading from `.env` (see `.env.example`), or set directly: `GITHUB_API_TOKEN`, `ETHERSCAN_EXPLORER_TOKEN`, `REMOTE_RPC_URL` (for bytecode comparison).

## Code style

- Formatter: **black** (enforced via pre-commit)
- Commit messages: validated by **gitlint**
- Python >=3.11
