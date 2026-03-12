#!/usr/bin/env bash
set -euo pipefail

uv sync --group dev
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

cp -n .env.example .env 2>/dev/null || true

echo "Ready. Run: uv run diffyscan config_samples/..<config>"
