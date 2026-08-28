# Bytecode Comparison

[Back to README](../README.md)

## Verification flow

For each configured contract, Diffyscan:

1. fetches the verified source and compiler metadata from the explorer;
2. replaces those sources with files from the pinned GitHub repositories;
3. compiles the GitHub sources with the explorer compiler settings;
4. compares the compiled runtime bytecode with `eth_getCode`;
5. simulates the creation bytecode with `eth_call` when constructor-set values
   prevent a direct match;
6. evaluates any `allowed_diffs` rules and reports uncovered differences.

Diffyscan reuses explorer-provided constructor calldata, linked-library
addresses, and EVM version. Add manual overrides only when that metadata is
missing or does not describe the deployment being checked.

## Manual overrides

`bytecode_comparison` accepts per-contract constructor, caller, and extra-source
overrides. `libraries` is a global mapping applied to every contract in the
config.

| Field | Scope | Purpose |
| --- | --- | --- |
| `constructor_args` | Per contract | ABI-encoded by Diffyscan and appended to creation bytecode |
| `constructor_calldata` | Per contract | Complete encoded constructor calldata |
| `deployment_from` | Per contract | Caller used for constructor simulation when `msg.sender` matters |
| `libraries` | All contracts | Linked-library addresses keyed by the file that defines each library |
| `extra_sources` | Per contract | GitHub source files absent from the explorer submission but required to compile |

```yaml
bytecode_comparison:
  constructor_args:
    "0x1111111111111111111111111111111111111111":
      - "0x2222222222222222222222222222222222222222"
  deployment_from:
    "0x1111111111111111111111111111111111111111": "0x3333333333333333333333333333333333333333"
  extra_sources:
    "0x1111111111111111111111111111111111111111":
      - src/interfaces/IMissingInterface.sol
```

`constructor_args` and `constructor_calldata` describe the same input. Configure
one of them for a contract.

## Linked libraries

Diffyscan reads linked-library addresses from explorer metadata. A manual entry
overrides that metadata:

```yaml
bytecode_comparison:
  libraries:
    src/lib/AssetRecovererLib.sol:
      AssetRecovererLib: "0x4444444444444444444444444444444444444444"
```

The outer key must name the file that defines the library. This matches the link
placeholders produced by `solc`. A consumer file that imports the library is not
a valid key.

The manual `libraries` mapping applies to every contract in the config. Use
separate config files when deployments require different addresses for the same
source path and library name.

If deployment simulation fails with `Invalid params`, or Diffyscan reports
`unlinked libraries`, check that every library address is present and keyed by
the file that defines the library.

## Allowed differences

`allowed_diffs` records expected differences without accepting unrelated drift.
Every rule needs a `reason`.

```yaml
allowed_diffs:
  bytecode:
    "0x1111111111111111111111111111111111111111":
      - reason: Proxy immutable owner differs on this deployment
        immutables:
          - offset: 320
            value: "0x0000000000000000000000003333333333333333333333333333333333333333"
        cbor_metadata: true

  source:
    "0x2222222222222222222222222222222222222222":
      - reason: Explorer submission contains a different version banner
        line_ranges:
          - file: contracts/utils/Versioned.sol
            github: { start: 17, count: 2 }
            explorer: { start: 17, count: 2 }
```

### Bytecode rules

| Facet | Scope |
| --- | --- |
| `immutables` | Exact on-chain values at compiler-derived immutable regions |
| `cbor_metadata: true` | Trailing Solidity metadata |
| `byte_ranges` | Explicit runtime byte offsets and lengths |
| `constructor_args` | Alternate constructor arguments used for a second simulation |
| `constructor_calldata` | Alternate encoded calldata used for a second simulation |
| `any: true` | Every bytecode difference or deployment simulation error for the contract |

### Source rules

| Facet | Scope |
| --- | --- |
| `line_ranges` | Exact changed hunks with 1-based `start` and `count` values |
| `files` | Every changed hunk in named files |
| `any: true` | Every source difference for the contract |

`any: true` must be the only facet in its rule. It cannot be combined with
`immutables`, `cbor_metadata`, `byte_ranges`, `constructor_args`,
`constructor_calldata`, `line_ranges`, or `files`.

Diffyscan prints a suggested rule for each uncovered difference in the final
summary. Immutable-backed differences are suggested as exact immutable values
before Diffyscan falls back to byte ranges.

## Avoid wildcard rules

`any: true` also accepts future drift for the contract. Prefer the narrowest
facet that describes the expected difference. Use a wildcard only when the
difference cannot be scoped, and record that constraint in `reason`.

To replace a wildcard:

1. remove it and run Diffyscan against the live chain;
2. copy the suggested `allowed_diffs` entry from the final summary;
3. replace the placeholder reason and rerun the check.

The regression test in
[`tests/test_no_wildcard_regression.py`](../tests/test_no_wildcard_regression.py)
checks rules under `config_samples/` and rejects new wildcards there unless the
repository records an explicit justification.

## Reports

Source comparison writes HTML diffs under
`digest/<timestamp>/diffs/<contract-address>/`. Logs are stored at
`digest/<timestamp>/logs.txt`.
