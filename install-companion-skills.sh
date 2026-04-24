#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$SCRIPT_DIR/companion-skills"

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "No companion-skills folder found at $SOURCE_ROOT" >&2
  exit 1
fi

force="false"
destination_root=""

for arg in "$@"; do
  case "$arg" in
    --force)
      force="true"
      ;;
    *)
      if [[ -z "$destination_root" ]]; then
        destination_root="$arg"
      fi
      ;;
  esac
done

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

mkdir -p "$destination_root"

installed=()
skipped=()
for skill_dir in "$SOURCE_ROOT"/*; do
  [[ -d "$skill_dir" ]] || continue
  skill_name="$(basename "$skill_dir")"
  if [[ -d "$destination_root/$skill_name" && "$force" != "true" ]]; then
    skipped+=("$skill_name")
    continue
  fi
  rm -rf "$destination_root/$skill_name"
  cp -R "$skill_dir" "$destination_root/$skill_name"
  installed+=("$skill_name")
done

python3 - <<'PY' "$SOURCE_ROOT" "$destination_root" "$force" "${installed[@]}" --skipped "${skipped[@]}"
import json
import sys

separator = sys.argv.index("--skipped")
print(json.dumps({
    "source": sys.argv[1],
    "destination_root": sys.argv[2],
    "force": sys.argv[3] == "true",
    "installed_skills": sys.argv[4:separator],
    "skipped_existing_skills": sys.argv[separator + 1:],
}, separators=(",", ":")))
PY
