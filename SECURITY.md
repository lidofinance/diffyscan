# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in diffyscan, please report it responsibly.

**Do not open a public GitHub issue.**

Instead use [GitHub's private vulnerability reporting](https://github.com/lidofinance/diffyscan/security/advisories/new).

## Scope

diffyscan verifies smart contract source code and bytecode against on-chain deployments. Security-relevant areas include:

- Integrity of source fetched from GitHub and blockchain explorers
- Correctness of bytecode comparison (false negatives could hide malicious changes)
- Handling of API tokens and RPC URLs
- Supply chain integrity of dependencies and CI pipeline

## Supported Versions

Only the latest release on `main` is actively maintained.
