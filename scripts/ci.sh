#!/usr/bin/env bash
# Espelha o workflow .github/workflows/ci.yml — rodar antes de push.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ ruff check ."
ruff check .

echo "→ mypy ."
mypy .

echo "→ pytest"
pytest

echo "CI local OK"
