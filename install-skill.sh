#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$SCRIPT_DIR"

destination_root="${1:-}"

if [[ -z "$destination_root" ]]; then
  if [[ -n "${CODEX_HOME:-}" ]]; then
    destination_root="$CODEX_HOME/skills"
  elif [[ -n "${HOME:-}" ]]; then
    destination_root="$HOME/.codex/skills"
  else
    echo "Unable to determine Codex skills directory. Pass a destination root explicitly." >&2
    exit 1
  fi
fi

destination="$destination_root/newbizintel"

mkdir -p "$destination_root"
rm -rf "$destination"
mkdir -p "$destination"

convert_to_installed_skill_metadata() {
  local skill_path="$1"

  if [[ ! -f "$skill_path" ]]; then
    return
  fi

  python3 - <<'PY' "$skill_path"
from pathlib import Path
import sys

path = Path(sys.argv[1])
content = path.read_text(encoding="utf-8")
content = content.replace(
    "name: newbizintel-dev",
    "name: newbizintel",
)
content = content.replace(
    "description: Development worktree variant of the supported newbizintel workflow. Use when working inside the canonical repo itself and you want the same modular orchestration without colliding with the installed production skill name.",
    "description: Supported default workflow for new-business intelligence. Use when you want research, assets, art, render, QA, and deploy coordinated through smaller resumable task skills instead of one monolithic run.",
)
content = content.replace(
    "# NewBizIntel Dev",
    "# NewBizIntel",
)
path.write_text(content, encoding="utf-8")
PY
}

items=(
  "SKILL.md"
  "agents"
  "assets"
  "bootstrap-runtime.ps1"
  "bootstrap-runtime.sh"
  "package.json"
  "package-lock.json"
  "README.md"
  "references"
  "scripts"
  "templates"
  "vendor"
)

installed=()
skipped=()

for item in "${items[@]}"; do
  if [[ ! -e "$SOURCE_ROOT/$item" ]]; then
    skipped+=("$item")
    continue
  fi

  cp -R "$SOURCE_ROOT/$item" "$destination/$item"
  installed+=("$item")
done

convert_to_installed_skill_metadata "$destination/SKILL.md"

if [[ -f "$destination/package.json" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js and npm are required to install the native PPTX export dependency." >&2
    exit 1
  fi
  (
    cd "$destination"
    npm install --omit=dev >/dev/null
  )
fi

python_bin="python3"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  python_bin="python"
fi

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python 3 is required to verify or refresh the NewBizIntel runtime." >&2
  exit 1
fi

runtime_bootstrapped=false
if [[ -f "$destination/scripts/qa/check_python_runtime.py" ]]; then
  if ! "$python_bin" "$destination/scripts/qa/check_python_runtime.py" --repo-root "$destination" --runtime-only --quiet; then
    "$python_bin" "$destination/scripts/bootstrap_vendor_runtime.py" --repo-root "$destination" >/dev/null
    runtime_bootstrapped=true
  fi
fi

"$python_bin" - <<'PY' "$SOURCE_ROOT" "$destination" "$runtime_bootstrapped" "${installed[@]}" --skipped "${skipped[@]}"
import json
import sys

separator = sys.argv.index("--skipped")
source = sys.argv[1]
destination = sys.argv[2]
runtime_bootstrapped = sys.argv[3].lower() == "true"
items = sys.argv[4:separator]
skipped = sys.argv[separator + 1:]

print(json.dumps({
    "source": source,
    "destination": destination,
    "installed_items": items,
    "skipped_missing_items": skipped,
    "python_runtime_bootstrapped": runtime_bootstrapped,
}, separators=(",", ":")))
PY
