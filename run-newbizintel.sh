#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
runner="$repo_root/scripts/newbizintel.py"

if [[ ! -f "$runner" ]]; then
  echo "Unable to find runner at $runner" >&2
  exit 1
fi

if [[ -n "${CODEX_BUNDLED_PYTHON:-}" && -x "${CODEX_BUNDLED_PYTHON:-}" ]]; then
  python_bin="$CODEX_BUNDLED_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  python_bin="$(command -v python)"
else
  echo "No usable Python interpreter was found." >&2
  exit 1
fi

"$python_bin" "$runner" "$@"
