# JSON Output Format

[Back to README](../README.md) · [CLI Reference](cli.md)

`diffyscan <config> --json` writes exactly one JSON object to stdout and nothing
else. Human-readable logs go to the file named in `log_file`; tracebacks go to
stderr. `--json` implies `--yes`, so the run never waits for input.

```sh
diffyscan path/to/config.yaml --json -E -G
```

## Rules for parsers

- Keys whose value would be `null` or an empty list are omitted. Treat a missing
  key as "nothing to report". `summary` and `contracts` are always present.
- Check `status` before the exit code. A contract skipped because of an error
  keeps the exit code at 0 when the config sets
  `fail_on_bytecode_comparison_error: false`, but `status` becomes `error`.
- Addresses are printed as written in the config (checksummed or not). Compare
  them case-insensitively.
- New keys may be added in later versions; unknown keys should be ignored.

## Top level

| Key | Type | Meaning |
| --- | --- | --- |
| `status` | `"passed"`, `"failed"`, `"error"` | `passed`: exit code 0 and every contract verified. `failed`: an unallowed diff, or `--contract` matched nothing. `error`: the run aborted, or at least one contract was skipped because of an error. |
| `exit_code` | int | Process exit code, same as without `--json`. |
| `error` | string | Only when the run aborted (missing config, bad token). `"<ExceptionType>: <message>"`. |
| `duration_seconds` | float | Wall time of the run. |
| `log_file` | string | Path to the full human-readable log of this run. |
| `summary` | object | Counters, see below. |
| `contracts` | array | One entry per checked contract, see below. |

### `summary`

```json
"summary": {
  "source":   { "total": 4, "exact": 3, "allowed": 1, "failed": 0 },
  "bytecode": { "total": 4, "exact": 2, "allowed": 1, "failed": 1 },
  "contract_errors": 1
}
```

`source` or `bytecode` is absent when that comparison did not run for any
contract. `contract_errors` is absent when zero.

## `contracts[]`

Every entry has `config` (path of the config file), `address`, and `name`.
Then one of:

- `source` and/or `bytecode`: the comparison results.
- `error`: the contract was skipped before any comparison finished. `source`
  and `bytecode` are absent.

### `source`

| Key | Present when | Meaning |
| --- | --- | --- |
| `status` | always | `exact`, `allowed`, or `failed`. |
| `files` | always | Number of source files in the explorer-verified set. |
| `missing` | some files not found on GitHub | Count of files missing at the pinned commit. |
| `with_diffs` | some files differ | Count of files with at least one hunk. |
| `diffs` | any file differs or is missing | One object per such file: `path`, `report` (HTML diff path), `missing: true` when absent on GitHub, `hunks`. |
| `facets`, `reason` | `status` is `allowed` | Facets of the matching `allowed_diffs` rule (`line_ranges`, `files`, `any`) and its `reason`. |
| `suggested_rule` | `status` is `failed` | Ready `allowed_diffs.source` entry covering the uncovered diff. Replace its placeholder `reason`. |

A hunk is one `SequenceMatcher` opcode with 1-based line numbers:

```json
{ "github": { "start": 12, "count": 1 }, "explorer": { "start": 12, "count": 2 }, "tag": "replace" }
```

`tag` is `replace`, `insert`, or `delete`, from the GitHub side to the explorer
side. `count: 0` marks the insertion point on the side that has no lines.

### `bytecode`

| Key | Present when | Meaning |
| --- | --- | --- |
| `status` | always | `exact`, `allowed`, or `failed`. |
| `uncovered` | `status` is `failed` and the comparison ran | Labels of differences no rule covers: `offset=<n> length=<n>[ immutable]`, `cbor_metadata`, `string_literal`, `runtime_length`. |
| `error` | the comparison itself failed | Compile, calldata, or deployment-simulation error text. `status` is `failed`. |
| `facets`, `reason` | `status` is `allowed` | Facets of the matching rule (`immutables`, `byte_ranges`, `cbor_metadata`, `constructor_args`, `constructor_calldata`, `any`) and its `reason`. |
| `suggested_rule` | `status` is `failed` and a diff was analyzed | Ready `allowed_diffs.bytecode` entry: `immutables` with observed on-chain values when only immutable slots differ, otherwise `byte_ranges`, plus `cbor_metadata: true` when metadata differs. |

## Example

```json
{
  "status": "failed",
  "exit_code": 1,
  "duration_seconds": 41.2,
  "log_file": "digest/1788770889/logs.txt",
  "summary": {
    "source": { "total": 2, "exact": 2, "allowed": 0, "failed": 0 },
    "bytecode": { "total": 2, "exact": 0, "allowed": 1, "failed": 1 }
  },
  "contracts": [
    {
      "config": "configs/example/mainnet/config.yaml",
      "address": "0x05Af8e10964Ad5536a643Ce7b9C831F45DC9D43e",
      "name": "Guard",
      "source": { "status": "exact", "files": 26 },
      "bytecode": {
        "status": "allowed",
        "facets": ["immutables"],
        "reason": "Bytecode differs only at immutable slots that depend on address(this)"
      }
    },
    {
      "config": "configs/example/mainnet/config.yaml",
      "address": "0x7305bB45aF91893B7BCaF0Ad8Eae37cb16820Bb8",
      "name": "Proxy",
      "source": { "status": "exact", "files": 14 },
      "bytecode": {
        "status": "failed",
        "uncovered": ["offset=1234 length=32 immutable"],
        "suggested_rule": {
          "reason": "TODO: explain why this diff is expected",
          "immutables": [{ "offset": 1234, "value": "0x00..01" }]
        }
      }
    }
  ]
}
```

Useful `jq` one-liners:

```sh
# Overall verdict
diffyscan cfg.yaml --json | jq -r .status

# Contracts that need attention
diffyscan cfg.yaml --json | jq '.contracts[] | select(.error or .source.status=="failed" or .bytecode.status=="failed")'

# Ready-to-paste allowlist suggestions
diffyscan cfg.yaml --json | jq '.contracts[] | {address, source: .source.suggested_rule, bytecode: .bytecode.suggested_rule} | select(.source or .bytecode)'
```
