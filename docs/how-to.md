# How-To Guides

[Back to README](../README.md)

## Install the CLI

Pin a release tag or commit so that later runs use the same Diffyscan code:

```sh
uv tool install git+https://github.com/lidofinance/diffyscan@<tag-or-commit>
```

Export the credentials named by your config. For example:

```sh
export GITHUB_API_TOKEN=<github-token>
export ETHERSCAN_EXPLORER_TOKEN=<explorer-token>
export REMOTE_RPC_URL=<rpc-url>
```

Run the installed command with your config:

```sh
diffyscan path/to/config.yaml
```

## Use the Dev Container

The repository's Dev Container uses the same Dockerfile as the regression
workflow. Open the checkout in a Dev Container-compatible editor. Its
post-create script installs dependencies and Git hooks, then copies
`.env.example` to `.env` when needed.

## Run a local checkout

```sh
uv sync --locked
cp .env.example .env
uv run diffyscan config_samples/ethereum/mainnet/circuit-breaker/circuit_breaker_config.yaml
```

Diffyscan loads the checkout's `.env` file. Set `GITHUB_API_TOKEN`, the explorer
token named by the config, and the RPC URL used by that config.

## Run every config in a directory

Pass a directory to process each `.json`, `.yaml`, and `.yml` file directly
inside it:

```sh
diffyscan path/to/configs
```

Directory discovery is not recursive. Pass a nested directory separately.

With no path, Diffyscan checks for `config.json`, `config.yaml`, then
`config.yml` in the current directory.

## Check selected contracts

Pass `--contract` (`-C`) more than once to select addresses from one config or
a directory of configs:

```sh
diffyscan path/to/config.yaml -C 0xFirstAddress -C 0xSecondAddress
```

The command exits with status 1 when no configured contract matches the filter.

## Compare sources only

Bytecode comparison is enabled by default. Skip it when you only need the source
diff:

```sh
diffyscan path/to/config.yaml --skip-binary-comparison
```

## Resolve Brownie-style imports

Brownie verification can flatten relative imports such as
`./interfaces/IFoo.sol` to `IFoo.sol`. Enable recursive GitHub lookup for
those submissions:

```sh
diffyscan path/to/config.yaml --support-brownie
```

## Cache remote inputs

Cache explorer responses and GitHub files for repeated runs:

```sh
diffyscan path/to/config.yaml --cache-explorer --cache-github
```

Explorer entries are stored in `.diffyscan_cache/`. GitHub entries are stored
in `.diffyscan_cache/github/`. Diffyscan validates cache metadata and content
hashes before reuse.

Remove both caches when you need fresh remote inputs:

```sh
rm -rf .diffyscan_cache/
```

## Run in CI

Use `--yes` to disable confirmation prompts and `--quiet` to hide informational
messages:

```sh
diffyscan path/to/configs --yes --quiet
```
