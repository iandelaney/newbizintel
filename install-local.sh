#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINATION_ROOT="${1:-}"
CODEX_ROOT_OVERRIDE="${CODEX_ROOT_OVERRIDE:-}"
FORCE_COMPANIONS="${FORCE_COMPANIONS:-false}"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

get_codex_root() {
  if [[ -n "$CODEX_ROOT_OVERRIDE" ]]; then
    printf '%s\n' "$CODEX_ROOT_OVERRIDE"
  elif [[ -n "$DESTINATION_ROOT" ]]; then
    dirname "$DESTINATION_ROOT"
  elif [[ -n "${CODEX_HOME:-}" ]]; then
    printf '%s\n' "$CODEX_HOME"
  elif [[ -n "${HOME:-}" ]]; then
    printf '%s\n' "$HOME/.codex"
  else
    printf '%s\n' "$PWD/.codex"
  fi
}

update_codex_config() {
  local repo_root="$1"
  local codex_root
  codex_root="$(get_codex_root)"
  mkdir -p "$codex_root"

  local config_path="$codex_root/config.toml"
  local snippet_path="$codex_root/newbiz2-config-snippet.toml"
  local example_path="$repo_root/codex-config.example.toml"
  cp "$example_path" "$snippet_path"

  local marker_start="# >>> newbiz2 setup >>>"
  local marker_end="# <<< newbiz2 setup <<<"

  if [[ ! -f "$config_path" || ! -s "$config_path" ]]; then
    cp "$example_path" "$config_path"
    printf 'created|%s|%s\n' "$config_path" "$snippet_path"
    return
  fi

  if grep -Fq "$marker_start" "$config_path"; then
    printf 'snippet_only|%s|%s\n' "$config_path" "$snippet_path"
    return
  fi

  local signals=(
    '[mcp_servers.tavily]'
    '[mcp_servers.composio]'
    '[mcp_servers.playwright]'
    '[mcp_servers.openaiDeveloperDocs]'
    'YOUR_TAVILY_API_KEY'
  )

  local has_overlap="false"
  for signal in "${signals[@]}"; do
    if grep -Fq "$signal" "$config_path"; then
      has_overlap="true"
      break
    fi
  done

  if [[ "$has_overlap" == "false" ]]; then
    {
      printf '\n%s\n' "$marker_start"
      cat "$example_path"
      printf '%s\n' "$marker_end"
    } >> "$config_path"
    printf 'appended|%s|%s\n' "$config_path" "$snippet_path"
    return
  fi

  printf 'snippet_only|%s|%s\n' "$config_path" "$snippet_path"
}

main_result="$(bash "$SCRIPT_DIR/install-skill.sh" "$DESTINATION_ROOT")"

companion_args=()
if [[ -n "$DESTINATION_ROOT" ]]; then
  companion_args+=("$DESTINATION_ROOT")
fi
if [[ "$FORCE_COMPANIONS" == "true" ]]; then
  companion_args+=("--force")
fi
companion_result="$(bash "$SCRIPT_DIR/install-companion-skills.sh" "${companion_args[@]}")"

config_result="$(update_codex_config "$SCRIPT_DIR")"
config_status="${config_result%%|*}"
rest="${config_result#*|}"
config_path="${rest%%|*}"
snippet_path="${rest#*|}"

"$PYTHON_BIN" - <<'PY' "$SCRIPT_DIR" "$main_result" "$companion_result" "$config_status" "$config_path" "$snippet_path" "$FORCE_COMPANIONS"
import json
import sys

source = sys.argv[1]
main_result = json.loads(sys.argv[2])
companion_result = json.loads(sys.argv[3])

print(json.dumps({
    "installed": True,
    "source": source,
    "main_skill_destination": main_result["destination"],
    "python_runtime_bootstrapped": main_result.get("python_runtime_bootstrapped", False),
    "companion_destination_root": companion_result["destination_root"],
    "installed_companion_skills": companion_result["installed_skills"],
    "skipped_existing_companion_skills": companion_result["skipped_existing_skills"],
    "companion_force": sys.argv[7].lower() == "true",
    "config_status": sys.argv[4],
    "config_path": sys.argv[5],
    "snippet_path": sys.argv[6],
    "next_steps": [
        "Replace YOUR_TAVILY_API_KEY in your Codex config",
        "Restart Codex",
    ],
}, separators=(",", ":")))
PY
