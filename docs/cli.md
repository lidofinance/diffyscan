# CLI Reference

[Back to README](../README.md)

```text
diffyscan [config-path] [options]
```

`config-path` is one JSON or YAML file, or a directory containing config files.
When omitted, Diffyscan looks for `config.json`, `config.yaml`, or `config.yml`
in the current directory.

| Option | Description |
| --- | --- |
| `-V, --version` | Print the installed Diffyscan version |
| `-Y, --yes` | Disable confirmation prompts before contract checks |
| `--support-brownie` | Resolve flattened imports with recursive GitHub lookup |
| `--no-support-brownie` | Disable Brownie import handling |
| `-S, --skip-binary-comparison` | Run source comparison without bytecode comparison |
| `-E, --cache-explorer` | Cache verified sources and metadata from the explorer |
| `-G, --cache-github` | Cache source files fetched from GitHub |
| `--log-level <level>` | Set `info`, `okay`, `warn`, or `error`; defaults to `info` |
| `-Q, --quiet` | Use the `okay` log level |
| `-C, --contract <address>` | Check one configured address; repeat for more addresses |

## Examples

Run one config:

```sh
diffyscan path/to/config.yaml
```

Run each config directly inside a directory:

```sh
diffyscan path/to/configs
```

Filter contracts and disable prompts:

```sh
diffyscan path/to/config.yaml -Y -C 0xFirstAddress -C 0xSecondAddress
```

Cache both remote source sets:

```sh
diffyscan path/to/config.yaml -E -G
```

Diffyscan exits with status 1 when a source or bytecode check fails, or when a
contract filter matches no configured address. Exact matches and differences
covered by `allowed_diffs` do not fail the run.
