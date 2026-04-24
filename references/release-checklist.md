# Release Checklist

Use this checklist before sharing `newbiz2` with colleagues or publishing it to GitHub.

## Required

- Run [audit_portability.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\audit_portability.ps1) and confirm `ok: true`
- Run [smoke_test_install.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\smoke_test_install.ps1) and confirm `ok: true`
- Run a sample render stack proof with:
  - [run_newbiz2.ps1](C:\codex projects\newbiz2-skill-repo\scripts\run_newbiz2.ps1)
  - `-DataPath .\examples\report-data.sample.json -Mode render-stack`
- Confirm fresh sample outputs exist:
  - `examples\newbizintel-report.html`
  - `examples\archive\newbizintel-report-portable.html`
  - `examples\run-state.json`
- Confirm the README install path still matches the actual scripts:
  - Windows PowerShell
  - macOS / `pwsh`
- Confirm no hidden sibling-repo dependency has been introduced

## Recommended

- Run the Univers gold-path proof if the real-brand inputs are available:
  - [run_univers_live_summary_proof.ps1](C:\codex projects\newbiz2-skill-repo\scripts\fixtures\run_univers_live_summary_proof.ps1)
- Review `references\duplication-map.md` before extracting shared code
- Recheck installer and config wording if MCP setup changed

## Release note prompt

When you share a release, include:

- what changed
- whether the installer path changed
- whether colleagues need to update Codex config
- whether any known limitation remains, especially around live MCP research or optional PPTX dependencies
