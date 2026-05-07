#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CODEX_ROOT="${1:-${CODEX_HOME:-${HOME:-$PWD}/.codex}}"
COMPANION_ROOT="$REPO_ROOT/companion-skills"
CONFIG_EXAMPLE="$REPO_ROOT/codex-config.example.toml"
PROBE_DIR="$CODEX_ROOT/.newbizintel-probe"
PROBE_FILE="$PROBE_DIR/write-test.tmp"

check_json_escape() {
  python3 - <<'PY' "$1"
import json
import sys
print(json.dumps(sys.argv[1]))
PY
}

python_ok=false
python_bin=""
if command -v python3 >/dev/null 2>&1; then
  python_ok=true
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_ok=true
  python_bin="python"
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

assets_ok=false
if [[ -d "$REPO_ROOT/assets" ]]; then
  assets_ok=true
fi

package_ok=false
if [[ -f "$REPO_ROOT/package.json" && -f "$REPO_ROOT/package-lock.json" ]]; then
  package_ok=true
fi

python_runtime_ok=false
python_runtime_detail="Python runtime check was skipped because no Python interpreter was found."
if [[ "$python_ok" == true && -f "$REPO_ROOT/scripts/qa/check_python_runtime.py" ]]; then
  if runtime_json="$("$python_bin" "$REPO_ROOT/scripts/qa/check_python_runtime.py" --repo-root "$REPO_ROOT" 2>/dev/null)"; then
    python_runtime_ok=true
    python_runtime_detail="$runtime_json"
  else
    python_runtime_detail="$runtime_json"
  fi
fi

legacy_powershell_ok=false
if command -v pwsh >/dev/null 2>&1 || command -v powershell >/dev/null 2>&1; then
  legacy_powershell_ok=true
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
for value in "$python_ok" "$node_ok" "$companion_ok" "$config_ok" "$assets_ok" "$package_ok" "$python_runtime_ok" "$writable"; do
  if [[ "$value" != true ]]; then
    ok=false
    break
  fi
done

"$python_bin" - <<'PY' \
  "$ok" "$REPO_ROOT" "$CODEX_ROOT" \
  "$python_ok" "$node_ok" "$companion_ok" "$config_ok" "$assets_ok" "$package_ok" "$python_runtime_ok" "$legacy_powershell_ok" "$writable" \
  "$COMPANION_ROOT" "$CONFIG_EXAMPLE" "$write_detail" "$python_runtime_detail"
import json
import sys

try:
    runtime_payload = json.loads(sys.argv[16])
    runtime_detail = "; ".join(
        check.get("detail", "") for check in runtime_payload.get("checks", []) if not check.get("ok")
    ) or "Python runtime dependencies are importable."
except Exception:
    runtime_detail = sys.argv[16]

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
            "detail": f"Expected companion-skills folder at {sys.argv[13]}.",
        },
        {
            "key": "config_example",
            "ok": sys.argv[7].lower() == "true",
            "detail": f"Expected config example at {sys.argv[14]}.",
        },
        {
            "key": "assets",
            "ok": sys.argv[8].lower() == "true",
            "detail": "Expected repo assets folder for icons, logo helpers, and report presentation assets.",
        },
        {
            "key": "node_package_manifest",
            "ok": sys.argv[9].lower() == "true",
            "detail": "Expected package.json and package-lock.json so npm can install pinned Node dependencies.",
        },
        {
            "key": "python_runtime_modules",
            "ok": sys.argv[10].lower() == "true",
            "detail": runtime_detail,
        },
        {
            "key": "legacy_powershell_renderer",
            "ok": True,
            "detail": "Legacy PowerShell renderer is available." if sys.argv[11].lower() == "true" else "Legacy PowerShell renderer is not available; this is acceptable because Python render_report.py is the default production renderer.",
        },
        {
            "key": "codex_root_writable",
            "ok": sys.argv[12].lower() == "true",
            "detail": sys.argv[15],
        },
    ],
}, separators=(",", ":")))
PY
