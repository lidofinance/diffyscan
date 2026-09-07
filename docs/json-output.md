# JSON Output Format

[Back to README](../README.md) · [CLI Reference](cli.md)

`diffyscan <config> --json` writes one JSON object to stdout. The
human-readable log goes to the file named in `log_file`, tracebacks go to
stderr. `--json` implies `--yes`, so the run does not prompt.

```sh
diffyscan path/to/config.yaml --json -E -G
```

## Rules for parsers

- Keys with a `null` or empty-list value are omitted. A missing key means
  nothing to report. `summary` and `contracts` are present in every report.
- Read `status` before the exit code. With
  `fail_on_bytecode_comparison_error: false` a contract skipped because of an
  error leaves the exit code at 0, while `status` becomes `error`.
- Addresses appear as written in the config, checksummed or not. Compare them
  case-insensitively.
- Later versions may add keys. Ignore unknown keys.

## Top level

| Key | Type | Meaning |
| --- | --- | --- |
| `status` | `"passed"`, `"failed"`, `"error"` | `passed`: exit code 0 and each contract verified. `failed`: an unallowed diff, or `--contract` matched nothing. `error`: the run aborted, or at least one contract was skipped because of an error. |
| `exit_code` | int | Process exit code, the same as without `--json`. |
| `error` | string | Present when the run aborted, for example on a missing config or a bad token. Format: `"<ExceptionType>: <message>"`. |
| `duration_seconds` | float | Wall time of the run. |
| `log_file` | string | Path to the human-readable log of this run. |
| `summary` | object | Counters, described below. |
| `contracts` | array | One entry per checked contract, described below. |

### `summary`

```json
"summary": {
  "source":   { "total": 4, "exact": 3, "allowed": 1, "failed": 0 },
  "bytecode": { "total": 4, "exact": 2, "allowed": 1, "failed": 1 },
  "contract_errors": 1
}
```

`source` or `bytecode` is absent when that comparison ran for no contract.
`contract_errors` is absent when zero.

## `contracts[]`

Each entry has `config` (path of the config file), `address`, and `name`, plus
either:

- `source` and/or `bytecode` with the comparison results, or
- `error` when the contract was skipped before a comparison finished. `source`
  and `bytecode` are then absent.

### `source`

| Key | Present when | Meaning |
| --- | --- | --- |
| `status` | in every entry | `exact`, `allowed`, or `failed`. |
| `files` | in every entry | Number of source files in the explorer-verified set. |
| `missing` | a file is absent on GitHub | Count of files absent at the pinned commit. |
| `with_diffs` | a file differs | Count of files with at least one hunk. |
| `diffs` | a file differs or is absent | One object per such file: `path`, `report` (path of the HTML diff), `missing: true` when absent on GitHub, `hunks`. |
| `facets`, `reason` | `status` is `allowed` | Facets of the matching `allowed_diffs` rule (`line_ranges`, `files`, `any`) and its `reason`. |
| `suggested_rule` | `status` is `failed` | An `allowed_diffs.source` entry that covers the uncovered diff. Replace its placeholder `reason` before use. |

A hunk is one `difflib.SequenceMatcher` opcode with 1-based line numbers:

```json
{ "github": { "start": 12, "count": 1 }, "explorer": { "start": 12, "count": 2 }, "tag": "replace" }
```

`tag` is `replace`, `insert`, or `delete`, read from the GitHub side to the
explorer side. `count: 0` marks the insertion point on the side without lines.

### `bytecode`

| Key | Present when | Meaning |
| --- | --- | --- |
| `status` | in every entry | `exact`, `allowed`, or `failed`. |
| `uncovered` | `status` is `failed` and the comparison ran | Labels of differences no rule covers: `offset=<n> length=<n>[ immutable]`, `cbor_metadata`, `string_literal`, `runtime_length`. |
| `error` | the comparison itself failed | Text of the compile, calldata, or deployment-simulation error. `status` is `failed`. |
| `facets`, `reason` | `status` is `allowed` | Facets of the matching rule (`immutables`, `byte_ranges`, `cbor_metadata`, `constructor_args`, `constructor_calldata`, `any`) and its `reason`. |
| `suggested_rule` | `status` is `failed` and a diff was analyzed | An `allowed_diffs.bytecode` entry: `immutables` with the observed on-chain values when only immutable slots differ, otherwise `byte_ranges`; `cbor_metadata: true` is added when metadata differs. |

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

`jq` examples:

```sh
# Overall verdict
diffyscan cfg.yaml --json | jq -r .status

# Contracts that need attention
diffyscan cfg.yaml --json | jq '.contracts[] | select(.error or .source.status=="failed" or .bytecode.status=="failed")'

# Allowlist suggestions
diffyscan cfg.yaml --json | jq '.contracts[] | {address, source: .source.suggested_rule, bytecode: .bytecode.suggested_rule} | select(.source or .bytecode)'
```
