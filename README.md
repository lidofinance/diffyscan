# Diffyscan

![python >=3.11,<4](https://img.shields.io/badge/python-≥3.11,<4-blue)
![uv](https://img.shields.io/badge/uv-managed-blue)
![license MIT](https://img.shields.io/badge/license-MIT-brightgreen)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Diff deployed EVM-compatible smart contract sourcecode and bytecode against the specified GitHub repo commit.

Key features:

- retrieve and diff sources from the GitHub repo against the queried ones from a blockscan service (e.g. Etherscan)
- compare bytecode by compiling GitHub sources and simulating constructor execution via remote `eth_call` against live chain state - enabled by default
- automatically reuse explorer-provided constructor calldata, library addresses, and EVM version for bytecode comparison
- configurable `allowed_diffs` rules for granular bytecode and source diff allowlisting, with summary suggestions for uncovered diffs
- supports both **JSON and YAML** configuration files (`.json`, `.yaml`, `.yml`)
- automatic environment variable loading from `.env` files
- cache sources from blockchain explorers (option `--cache-explorer`) and GitHub files (option `--cache-github`) to avoid re-fetching on repeated runs
- preprocess imports to flat paths for Brownie compatibility (option `--support-brownie`)
- skip binary comparison if needed (option `--skip-binary-comparison`)

## Install

```bash
# Pin a tag or commit instead of floating HEAD for reproducible installs.
uv tool install git+https://github.com/lidofinance/diffyscan@<tag-or-commit>
```

## Development setup

### Dev Container (recommended)

The fastest way to get a working development environment. Works with VS Code, GitHub Codespaces, and any [Dev Container](https://containers.dev/)-compatible tool.

1. Open this repo in VS Code
2. When prompted "Reopen in Container", click yes (or run **Dev Containers: Reopen in Container** from the command palette)
3. Wait for the container to build — dependencies, git hooks, and `.env` are set up automatically

That's it. Run tests with `uv run pytest -q` or the CLI with `uv run diffyscan config_samples/lido_dao_sepolia_config.json`.

### Manual setup

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.11+

```bash
uv sync --locked --group dev
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Run tests:

```bash
uv run pytest -q
```

Run hooks manually:

```bash
uv run pre-commit run --all-files
```

Run the CLI locally:

```bash
uv run diffyscan config_samples/lido_dao_sepolia_config.json
```

## Usage

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Or set environment variables directly:

```bash
export ETHERSCAN_EXPLORER_TOKEN=<your-etherscan-token>
export GITHUB_API_TOKEN=<your-github-token>
export REMOTE_RPC_URL=<remote-rpc-url>
```

Start script with one of the examples provided (or entire folder of configs)

```bash
diffyscan config_samples/lido_dao_sepolia_config.json
```

When no path is given, diffyscan looks for `config.json`, `config.yaml`, or `config.yml` in the current directory. When a directory is given, all `.json`, `.yaml`, and `.yml` files inside it are processed.

Alternatively, create a new config file near `diffyscan.py`. Configs can be written in JSON or YAML. The `bytecode_comparison` section is optional and only needed for manual overrides when explorer metadata is missing or you want to override it:

**JSON** (`config.json`):

```json
{
  "contracts": {
    "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8": "OssifiableProxy",
    "0xDba5Ad530425bb1b14EECD76F1b4a517780de537": "LidoLocator"
  },
  "explorer_hostname": "api.etherscan.io",
  "explorer_chain_id": 17000,
  "explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN",
  "github_repo": {
    "url": "https://github.com/lidofinance/lido-dao",
    "commit": "cadffa46a2b8ed6cfa1127fca2468bae1a82d6bf",
    "relative_root": ""
  },
  "dependencies": {
    "@openzeppelin/contracts-v4.4": {
      "url": "https://github.com/OpenZeppelin/openzeppelin-contracts",
      "commit": "6bd6b76d1156e20e45d1016f355d154141c7e5b9",
      "relative_root": "contracts"
    }
  },
  "fail_on_bytecode_comparison_error": true,
  "bytecode_comparison": {
    "constructor_calldata": {
      "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8": "000000000000000000000000ab89ed3d8f31bcf8bb7de53f02084d1e6f043d34000000000000000000000000e92329ec7ddb11d25e25b3c21eebf11f15eb325d00000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000000"
    },
    "constructor_args": {
      "0xDba5Ad530425bb1b14EECD76F1b4a517780de537": [
        [
          "0x4E97A3972ce8511D87F334dA17a2C332542a5246",
          "0x045dd46212A178428c088573A7d102B9d89a022A",
          "0xE73a3602b99f1f913e72F8bdcBC235e206794Ac8",
          "0x072f72BE3AcFE2c52715829F2CD9061A6C8fF019",
          "0x3F1c547b21f65e10480dE3ad8E19fAAC46C95034",
          "0xF0d576c7d934bBeCc68FE15F1c5DAF98ea2B78bb",
          "0x072f72BE3AcFE2c52715829F2CD9061A6C8fF019",
          "0x4E46BD7147ccf666E1d73A3A456fC7a68de82eCA",
          "0xd6EbF043D30A7fe46D1Db32BA90a0A51207FE229",
          "0xE92329EC7ddB11D25e25b3c21eeBf11f15eB325d",
          "0xffDDF7025410412deaa05E3E1cE68FE53208afcb",
          "0xc7cc160b58F8Bb0baC94b80847E2CF2800565C50",
          "0xF0179dEC45a37423EAD4FaD5fCb136197872EAd9",
          "0xC01fC1F2787687Bc656EAc0356ba9Db6e6b7afb7"
        ]
      ]
    }
  }
}
```

**YAML** (`config.yaml`):

```yaml
contracts:
  "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8": OssifiableProxy
  "0xDba5Ad530425bb1b14EECD76F1b4a517780de537": LidoLocator

explorer_hostname: api.etherscan.io
explorer_chain_id: 17000
explorer_token_env_var: ETHERSCAN_EXPLORER_TOKEN

github_repo:
  url: https://github.com/lidofinance/lido-dao
  commit: cadffa46a2b8ed6cfa1127fca2468bae1a82d6bf
  relative_root: ""

dependencies:
  "@openzeppelin/contracts-v4.4":
    url: https://github.com/OpenZeppelin/openzeppelin-contracts
    commit: 6bd6b76d1156e20e45d1016f355d154141c7e5b9
    relative_root: contracts
```

> **Important:** In YAML configs, always quote contract addresses (e.g. `"0x1234..."`). Unquoted hex values will be parsed as integers by YAML, and diffyscan will raise an error if this happens.

### Granular allowlists

Use `allowed_diffs` to describe exactly which differences are expected. The same schema works in JSON and YAML.

```yaml
allowed_diffs:
  bytecode:
    "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8":
      - reason: Proxy immutable owner differs on deployment
        immutables:
          - offset: 320
            value: "0x000000000000000000000000ab89ed3d8f31bcf8bb7de53f02084d1e6f043d34"
        cbor_metadata: true
      - reason: Alternate constructor calldata on testnet
        constructor_calldata: "0x1234abcd"

  source:
    "0xDba5Ad530425bb1b14EECD76F1b4a517780de537":
      - reason: Version banner differs
        line_ranges:
          - file: contracts/utils/Versioned.sol
            github: { start: 17, count: 2 }
            explorer: { start: 17, count: 2 }
      - reason: Generated file differs
        files:
          - contracts/generated/BuildInfo.sol
```

Supported bytecode facets:

- `immutables`: exact expected on-chain values for compiler-derived immutable regions
- `cbor_metadata: true`: allow trailing Solidity metadata changes
- `byte_ranges`: allow explicit runtime byte ranges
- `constructor_args` or `constructor_calldata`: re-simulate deployment with alternate constructor input
- `any: true`: blanket escape hatch

Supported source facets:

- `line_ranges`: exact changed hunks using 1-based `start` and `count`
- `files`: allow any hunk inside specific files
- `any: true`: blanket escape hatch

When an uncovered diff is found, diffyscan prints a suggested `allowed_diffs` snippet in the final summary. Immutable-backed bytecode diffs are suggested as exact immutable values before falling back to byte ranges.

`--allow-bytecode-diff` and `--allow-source-diff` still work, but they are now deprecated shorthands for `any: true`. Move those rules into the config file so the summary suggestions can help you tighten them over time.

Start the script

```bash
diffyscan /path/to/config.json
diffyscan /path/to/config.yaml
```

To skip binary comparison (which is enabled by default):

```bash
diffyscan /path/to/config.json --skip-binary-comparison
```

> Note: Brownie verification tooling might rewrite the imports in the source submission. It transforms relative paths to imported contracts into flat paths ('./folder/contract.sol' -> 'contract.sol'), which makes Diffyscan unable to find a contract for verification.

For contracts whose sources were verified by brownie tooling:

```bash
diffyscan /path/to/config.json --support-brownie
```

### Caching

Diffyscan supports two types of caching to speed up repeated runs and reduce API rate limiting:

#### Cache Explorer Sources

Cache contract sources from blockchain explorers (Etherscan, Blockscout, etc.):

```bash
diffyscan config_samples/lido_dao_sepolia_config.json --cache-explorer
```

Explorer sources are cached in `.diffyscan_cache/` with unique identifiers based on chain ID and contract address (e.g., `1_0xcontractaddress.json`).

#### Cache GitHub Files

Cache files retrieved from GitHub repositories:

```bash
diffyscan config_samples/lido_dao_sepolia_config.json --cache-github
```

GitHub files are cached in `.diffyscan_cache/github/` with SHA256 hash identifiers based on repository, commit, and file path.

#### Using Both Caches

For maximum performance, enable both caches:

```bash
diffyscan config_samples/lido_dao_sepolia_config.json --cache-explorer --cache-github
```

**Benefits:**

- Significantly faster repeated runs (no API calls)
- API rate limit friendly for both Etherscan and GitHub
- Works offline after initial fetch
- Useful for repeated testing and development

**Cache management:**

```bash
# Clear all caches
rm -rf .diffyscan_cache/

# Clear only explorer cache
rm -rf .diffyscan_cache/*.json

# Clear only GitHub cache
rm -rf .diffyscan_cache/github/

# View cached files
ls -la .diffyscan_cache/
```

ℹ️ See more config examples inside the [config_samples](./config_samples/) dir.
