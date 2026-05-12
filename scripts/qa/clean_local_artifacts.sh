#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DRY_RUN="${DRY_RUN:-false}"

targets=(
  "dist"
  "node_modules"
  "pptx_runtime"
  "pptx_runtime_env"
  "runtime"
  "examples/archive/newbizintel-report-portable.html"
  "examples/newbizintel-report.html"
  "examples/required-logo-manifest.json"
  "examples/run-state.json"
  "examples/source-badge-manifest.json"
  "scripts/__pycache__"
  "scripts/campaign-art/__pycache__"
  "scripts/python_modules/__pycache__"
  "scripts/qa/__pycache__"
  "scripts/render/__pycache__"
  "scripts/research/__pycache__"
  "companion-skills/slides/scripts/__pycache__"
)

results=()
for target in "${targets[@]}"; do
  path="$REPO_ROOT/$target"
  [[ -e "$path" ]] || continue

  if [[ "$DRY_RUN" == "true" ]]; then
    action="would_remove"
  else
    rm -rf "$path"
    action="removed"
  fi

  results+=("{\"target\":$(python3 - <<'PY' "$target"
import json, sys
print(json.dumps(sys.argv[1]))
PY
),\"action\":\"$action\"}")
done

python3 - <<'PY' "$REPO_ROOT" "$DRY_RUN" "${results[@]}"
import json
import sys

repo_root = sys.argv[1]
dry_run = sys.argv[2].lower() == "true"
targets = [json.loads(item) for item in sys.argv[3:]]
print(json.dumps({
    "ok": True,
    "repo_root": repo_root,
    "dry_run": dry_run,
    "removed_count": len(targets),
    "targets": targets,
}, indent=2))
PY
