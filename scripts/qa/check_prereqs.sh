#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CODEX_ROOT="${1:-${CODEX_HOME:-${HOME:-$PWD}/.codex}}"
COMPANION_ROOT="$REPO_ROOT/companion-skills"
CONFIG_EXAMPLE="$REPO_ROOT/codex-config.example.toml"
PROBE_DIR="$CODEX_ROOT/.newbiz2-probe"
PROBE_FILE="$PROBE_DIR/write-test.tmp"

check_json_escape() {
  python3 - <<'PY' "$1"
import json
import sys
print(json.dumps(sys.argv[1]))
PY
}

python_ok=false
if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  python_ok=true
fi

node_ok=false
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  node_ok=true
fi

companion_ok=false
if [[ -d "$COMPANION_ROOT" ]]; then
  companion_ok=true
fi

config_ok=false
if [[ -f "$CONFIG_EXAMPLE" ]]; then
  config_ok=true
fi

writable=true
write_detail="Codex root is writable: $CODEX_ROOT"
mkdir -p "$PROBE_DIR" 2>/dev/null || writable=false
if [[ "$writable" == true ]]; then
  if ! printf 'ok' > "$PROBE_FILE" 2>/dev/null; then
    writable=false
    write_detail="Could not write to Codex root $CODEX_ROOT"
  fi
fi
rm -f "$PROBE_FILE" 2>/dev/null || true
rmdir "$PROBE_DIR" 2>/dev/null || true

if [[ "$writable" != true ]]; then
  write_detail="Could not write to Codex root $CODEX_ROOT"
fi

ok=true
for value in "$python_ok" "$node_ok" "$companion_ok" "$config_ok" "$writable"; do
  if [[ "$value" != true ]]; then
    ok=false
    break
  fi
done

python_bin="python3"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  python_bin="python"
fi

"$python_bin" - <<'PY' \
  "$ok" "$REPO_ROOT" "$CODEX_ROOT" \
  "$python_ok" "$node_ok" "$companion_ok" "$config_ok" "$writable" \
  "$COMPANION_ROOT" "$CONFIG_EXAMPLE" "$write_detail"
import json
import sys

print(json.dumps({
    "ok": sys.argv[1].lower() == "true",
    "repo_root": sys.argv[2],
    "codex_root": sys.argv[3],
    "checks": [
        {
            "key": "python",
            "ok": sys.argv[4].lower() == "true",
            "detail": "Requires python3 or python for runtime and export helpers.",
        },
        {
            "key": "node",
            "ok": sys.argv[5].lower() == "true",
            "detail": "Requires node and npm for native PPTX export via PptxGenJS.",
        },
        {
            "key": "companion_skills",
            "ok": sys.argv[6].lower() == "true",
            "detail": f"Expected companion-skills folder at {sys.argv[9]}.",
        },
        {
            "key": "config_example",
            "ok": sys.argv[7].lower() == "true",
            "detail": f"Expected config example at {sys.argv[10]}.",
        },
        {
            "key": "codex_root_writable",
            "ok": sys.argv[8].lower() == "true",
            "detail": sys.argv[11],
        },
    ],
}, separators=(",", ":")))
PY
