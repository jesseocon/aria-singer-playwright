#!/usr/bin/env bash
# Scaffold a sibling vendor Meltano repo (interactive cookiecutter).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v cookiecutter >/dev/null 2>&1; then
  echo "Install cookiecutter: uv tool install cookiecutter" >&2
  exit 1
fi

cookiecutter cookiecutter-vendor-meltano -o "$(dirname "$ROOT")"

echo ""
echo "Next steps:"
echo "  cd ../aria-<vendor>"
echo "  git init && uv sync && uv run playwright install chromium"
echo "  uv run python -m singer_playwright auth --url <login> --out storage_state.json"
echo "  uv run meltano install && uv run meltano invoke tap-<vendor> --discover"
