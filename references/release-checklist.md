# Release Checklist

Use this checklist before sharing `newbiz2` with colleagues or publishing it to GitHub.

## Required

- Run [audit_portability.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\audit_portability.ps1) and confirm `ok: true`
- Run [smoke_test_install.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\smoke_test_install.ps1) and confirm `ok: true`
- Run a sample gated proof with the cross-platform Python runner:
  - [newbiz2.py](C:\codex projects\newbiz2-skill-repo\scripts\newbiz2.py)
  - `run --mode render-stack --data-path .\examples\report-data.sample.json`
  - `qa --data-path .\examples\report-data.sample.json`
- On Windows, run a sample full gated proof with the legacy PowerShell runner:
  - [run_newbiz2.ps1](C:\codex projects\newbiz2-skill-repo\scripts\run_newbiz2.ps1)
  - `-DataPath .\examples\report-data.sample.json -Mode full`
- Confirm the QA smoke test still uses the hybrid parallel path, with deterministic jobs only writing isolated audit outputs before render.
- Confirm `scripts\qa\audit_task_list.ps1` passes and reports the 10 primary workflow steps in order.
- Confirm fresh sample outputs exist:
  - `examples\newbizintel-report.html`
  - `examples\archive\newbizintel-report-portable.html`
  - `examples\run-state.json`
- Confirm full-run delivery output includes the Vercel deployment prompt and that any Vercel upload path is prepared with `vercel-stage`, using a random staging folder rather than the brand output folder.
- Confirm production Creative Campaign artwork is final bundled raster art, not local scaffold or placeholder output. The campaign-art QA gate must fail any delivered report with `scaffold-allowed`, `local-scaffold`, `placeholder-scaffold`, `unverified-existing-artwork`, missing files, external image URLs, unsupported formats, or undersized/non-portrait images.
- Confirm the README install path still matches the actual scripts:
  - Windows Python-first plus optional PowerShell compatibility
  - macOS Python-first with no `pwsh` requirement
- Confirm no hidden sibling-repo dependency has been introduced
- Confirm research evidence routing is documented accurately: direct SEMrush API first, Composio-backed SEMrush as backup, Jina/direct web as current-web fallback, and explicitly labelled Similarweb evidence only when SEMrush is blocked, quota-limited, or too thin.

## Recommended

- Run the Univers gold-path proof if the real-brand inputs are available:
  - [run_univers_live_summary_proof.ps1](C:\codex projects\newbiz2-skill-repo\scripts\fixtures\run_univers_live_summary_proof.ps1)
- Keep disposable proof artifacts outside the delivery output root. Use [resolve_proof_root.ps1](C:\codex projects\newbiz2-skill-repo\scripts\common\resolve_proof_root.ps1) rather than creating sibling folders such as `output\skill-runs`.
- Optionally run [audit_output_cleanliness.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\audit_output_cleanliness.ps1) to identify historical proof or handoff folders that should be quarantined after operator approval.
- Review `references\duplication-map.md` before extracting shared code
- Recheck installer and config wording if MCP setup changed

## Release note prompt

When you share a release, include:

- what changed
- whether the installer path changed
- whether colleagues need to update Codex config
- whether any known limitation remains, especially around live MCP research or optional PPTX dependencies
