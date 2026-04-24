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

destination="$destination_root/newbiz2"

mkdir -p "$destination_root"
rm -rf "$destination"
mkdir -p "$destination"

items=(
  "SKILL.md"
  "agents"
  "package.json"
  "package-lock.json"
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

python3 - <<'PY' "$SOURCE_ROOT" "$destination" "${installed[@]}" --skipped "${skipped[@]}"
import json
import sys

separator = sys.argv.index("--skipped")
source = sys.argv[1]
destination = sys.argv[2]
items = sys.argv[3:separator]
skipped = sys.argv[separator + 1:]

print(json.dumps({
    "source": source,
    "destination": destination,
    "installed_items": items,
    "skipped_missing_items": skipped,
}, separators=(",", ":")))
PY
