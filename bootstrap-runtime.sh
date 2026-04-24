#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Python 3 was not found on PATH. Install Python 3, then rerun this script." >&2
    exit 1
  fi
fi

runtime_args=()
if [[ $# -gt 0 ]]; then
  for runtime in "$@"; do
    if [[ "$runtime" != "all" ]]; then
      runtime_args+=(--runtime "$runtime")
    fi
  done
fi

"$PYTHON_BIN" "$SCRIPT_DIR/scripts/bootstrap_vendor_runtime.py" "${runtime_args[@]}" --repo-root "$SCRIPT_DIR"
