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
| `--support-brownie`, `--no-support-brownie` | Enable or explicitly keep Brownie import handling disabled; disabled by default |
| `-S, --skip-binary-comparison` | Run source comparison without bytecode comparison |
| `-E, --cache-explorer` | Cache verified sources and metadata from the explorer |
| `-G, --cache-github` | Cache source files fetched from GitHub |
| `--log-level <level>` | Set `info`, `okay`, `warn`, or `error`; defaults to `info` |
| `-Q, --quiet` | Use the `okay` log level |
| `-J, --json` | Print one JSON report to stdout instead of human-readable logs; implies `--yes` |
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

## JSON output

`--json` is meant for scripts and coding agents. Human-readable logs are not
written to stdout (they still go to `digest/<timestamp>/logs.txt`), prompts are
skipped, and stdout carries a single JSON document:

```sh
diffyscan path/to/config.yaml --json -E -G | jq '.summary'
```

```json
{
  "diffyscan_version": "1.0.0",
  "status": "passed | failed | error",
  "exit_code": 0,
  "error": null,
  "duration_seconds": 12.3,
  "log_file": "digest/1700000000/logs.txt",
  "summary": {
    "source":   { "total": 2, "exact": 1, "allowed": 1, "failed": 0 },
    "bytecode": { "total": 2, "exact": 2, "allowed": 0, "failed": 0 },
    "contract_errors": 0
  },
  "configs": [
    {
      "path": "path/to/config.yaml",
      "contracts": [
        {
          "address": "0x...",
          "name": "ContractName",
          "source": {
            "status": "allowed",
            "files_count": 10, "files_found": 10,
            "identical_files": 9, "files_with_diffs": 1,
            "matched_rule": { "reason": "...", "line_ranges": [...] },
            "matched_facets": ["line_ranges"],
            "diff_files": [
              {
                "path": "contracts/Foo.sol",
                "file_found": true,
                "diff_report": "digest/1700000000/diffs/0x.../Foo.sol.html",
                "hunks": [
                  { "github": { "start": 3, "count": 1 },
                    "explorer": { "start": 3, "count": 1 },
                    "tag": "replace" }
                ]
              }
            ],
            "suggested_rule": null
          },
          "bytecode": {
            "status": "failed",
            "match": false,
            "matched_rule": null,
            "matched_facets": [],
            "uncovered": ["offset=1234 length=32 immutable"],
            "error": null,
            "suggested_rule": { "reason": "TODO", "immutables": [...] }
          }
        }
      ]
    }
  ]
}
```

- `status` is `passed` when the exit code is 0, `failed` when a check failed or
  the contract filter matched nothing, and `error` when the run aborted or a
  contract was skipped because of an error. A skipped contract carries an
  `error` string and `null` for `source` and `bytecode`; with
  `fail_on_bytecode_comparison_error: false` this still exits 0, so check
  `status`, not only the exit code.
- `source` or `bytecode` is `null` when that comparison did not run.
- `diff_files` lists only files that differ or are missing on GitHub.
- `suggested_rule` is the `allowed_diffs` entry Diffyscan would propose for an
  uncovered diff; replace its placeholder `reason` before adding it to a config.
- `error` on a bytecode entry holds the compile, calldata, or simulation error
  that turned the check into a failure.
- A fatal error (missing config, bad token) still produces a report with
  `status: "error"` and the exception in the top-level `error`; the traceback
  goes to stderr.
