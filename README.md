# newbiz2

`newbiz2` is a modular successor to `newbizintel`.

It is designed to preserve the rigor of the current workflow while splitting the work into smaller, reusable modules coordinated by one orchestrator.

## Design goal

Keep `newbizintel` stable.

Use `newbiz2` to experiment with:

- orchestration
- resumable runs
- clearer module ownership
- targeted refreshes such as art-only, assets-only, render-only, or deploy-only runs

## Portability rule

`newbiz2` should be shareable with colleagues as a clean standalone repo.

That means:

- no hidden dependency on sibling folders in `C:\codex projects`
- no local-only helper path outside this repo unless it is explicitly documented as an external prerequisite
- prefer temporary duplication inside `newbiz2` over an undeclared cross-repo dependency

If shared code is extracted later, it should move into a clearly versioned and documented package or companion repo, not an implicit local workspace helper folder.

## Module set

- `newbiz2-orchestrator`
- `newbiz2-intake`
- `newbiz2-research`
- `newbiz2-structure`
- `newbiz2-assets`
- `newbiz2-campaign-art`
- `newbiz2-render`
- `newbiz2-qa`
- `newbiz2-deploy`

## Core contract

The modular workflow still revolves around one canonical structured payload:

- `report-data.json`

It also adds resumable state:

- `run-state.json`

## Current state

This repo is now minimally runnable from `newbiz2` itself.

What works today:

- module runners exist for intake, research, structure, assets, campaign art, render, QA, and deploy handoff
- the orchestrator can run `full`, `research-only`, `render-stack`, `qa-only`, `deploy-handoff`, `art-refresh`, and `assets-refresh`
- `research-summary.json` is produced in bootstrap mode from an existing `report-data.json`
- `research-summary.json` can also be imported in `live-summary` mode after Codex gathers current-web evidence with Tavily, falls back to Jina when needed, and attaches SEMrush evidence through the installed Composio MCP server
- `newbiz2-structure` now consumes `research-summary.json` when present and writes the live research layer back into `report-data.json` before validation
- `run-state.json` is updated as modules complete
- HTML, portable HTML, and deploy handoff outputs are produced from the copied stable `newbizintel` machinery
- the full modular chain is proven on the real Univers brand folder through `research -> structure -> assets -> campaign-art -> render -> qa -> deploy-handoff`
- premium Creative Campaign art now defaults to prompt-driven image-generated raster artwork, with local scaffold placeholders allowed only when a report explicitly opts into scaffold mode

## Premium campaign art

The premium Creative Campaign path is now:

1. Prepare prompts and handoff files:

```powershell
& .\scripts\campaign-art\run_module.ps1 -DataPath .\output\<brand>\report-data.json
```

2. Generate one raster image per prompt from the produced brief and manifest:

- `slide-assets/<brand>-campaign-illustration-prompts.json`
- `slide-assets/<brand>-campaign-art-brief.md`

3. Import the resulting batch and clear the campaign-art gate:

```powershell
& .\scripts\campaign-art\run_module.ps1 -DataPath .\output\<brand>\report-data.json -ImportSourceDir <folder-with-final-images>
```

Or, when the images were just created by Codex image generation:

```powershell
& .\scripts\campaign-art\run_module.ps1 -DataPath .\output\<brand>\report-data.json -ImportLatestGeneratedBatch
```

The import step normalizes the images into the expected portrait PNG outputs, marks them as `final-raster-artwork`, and lets QA distinguish true final art from placeholder scaffold output.

## Colleague install

`newbiz2` is intended to be installable on both Windows and macOS.

Prerequisites:

- Windows: PowerShell and Python available
- macOS: `pwsh` and `python3` available on `PATH`

Windows PowerShell:

```powershell
.\install-local.ps1
```

macOS or other Unix-like shells:

```bash
./install-local.sh
```

If you only want to install the skill files without updating Codex config:

Windows PowerShell:

```powershell
.\install-skill.ps1
```

macOS or other Unix-like shells:

```bash
./install-skill.sh
```

## Handoff to colleagues

If you are sharing `newbiz2` with a colleague, this is the shortest clean start path.

### Mac quick start

For a colleague on macOS, this is the shortest copy-and-run sequence:

```bash
./scripts/qa/check_prereqs.sh
./install-local.sh
# add YOUR_TAVILY_API_KEY to the written Codex config or snippet
pwsh ./scripts/run_newbiz2.ps1 -DataPath ./examples/report-data.sample.json -Mode render-stack
pwsh ./scripts/qa/audit_portability.ps1
```

### 1. Clone the repo

Place `newbiz2-skill-repo` anywhere convenient. It does not need sibling repos to work.

### 2. Run the prerequisite self-check

Windows PowerShell:

```powershell
.\scripts\qa\check_prereqs.ps1
```

macOS or other Unix-like shells:

```bash
./scripts/qa/check_prereqs.sh
```

This should report:

- a usable PowerShell runtime
- a usable Python runtime
- a writable Codex root
- the expected companion skill and config files

### 3. Install the skill

Windows PowerShell:

```powershell
.\install-local.ps1
```

macOS or other Unix-like shells:

```bash
./install-local.sh
```

### 4. Add the Tavily key

The installer writes or updates Codex config using:

- [codex-config.example.toml](C:\codex projects\newbiz2-skill-repo\codex-config.example.toml)

Replace `YOUR_TAVILY_API_KEY` in the written Codex config or snippet file with a real Tavily key.

### 5. Restart Codex

Restart Codex so the installed skill and MCP config are picked up cleanly.

### 6. Run a first safe proof

Start with the sample data:

Windows PowerShell:

```powershell
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode render-stack
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/run_newbiz2.ps1 -DataPath ./examples/report-data.sample.json -Mode render-stack
```

Then check portability before sharing onward:

Windows PowerShell:

```powershell
.\scripts\qa\audit_portability.ps1
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/qa/audit_portability.ps1
```

Then run the repo-local install smoke test to prove the colleague install path still works:

Windows PowerShell:

```powershell
.\scripts\qa\smoke_test_install.ps1
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/qa/smoke_test_install.ps1
```

### 7. Prove the real gold path when available

If the Univers proof inputs exist locally, run:

Windows PowerShell:

```powershell
.\scripts\fixtures\run_univers_live_summary_proof.ps1
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/fixtures/run_univers_live_summary_proof.ps1
```

Expected result:

- all statuses in `run-state.json` are `passed`
- all gates are `passed`
- fresh HTML, portable HTML, and handoff outputs are produced

## Gold-path regression target

`Univers` is the current real-brand proof case for `newbiz2`.

Use this fixture when you want to prove the full live-summary path end to end:

```powershell
.\scripts\fixtures\run_univers_live_summary_proof.ps1
```

This fixture expects these existing real-brand inputs:

- `C:\codex projects\output\univers\report-data.json`
- `C:\codex projects\output\univers\research-summary.json`

Expected outcome:

- all module statuses in `output\univers\run-state.json` are `passed`
- all gates from `gate_1_intake` through `gate_7_delivery` are `passed`
- fresh outputs exist in:
  - `output\univers\newbizintel-report.html`
  - `output\univers\archive\newbizintel-report-portable.html`
  - `output\vercel\`

What is still intentionally incomplete:

- the local PowerShell runner does not call MCP tools directly; live research is gathered in Codex through Tavily, Jina as backup, and the installed Composio MCP server, then imported through `live-summary` mode
- PPTX export depends on Python packages that may not exist in the active runtime

## Shareability guardrails

Use these checks before sharing installer changes with colleagues:

- [audit_portability.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\audit_portability.ps1) to catch hidden workspace dependencies
- [check_prereqs.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\check_prereqs.ps1) or [check_prereqs.sh](C:\codex projects\newbiz2-skill-repo\scripts\qa\check_prereqs.sh) to verify a target machine is ready
- [smoke_test_install.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\smoke_test_install.ps1) to prove the repo-local install path still works cleanly and does not duplicate config blocks on rerun
- [release_check.ps1](C:\codex projects\newbiz2-skill-repo\scripts\qa\release_check.ps1) to run the current release gate in one command

## Release readiness

Before publishing or handing the repo to colleagues, run:

Windows PowerShell:

```powershell
.\scripts\qa\release_check.ps1
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/qa/release_check.ps1
```

This rolls up the current required checks:

- portability audit
- repo-local install smoke test
- sample `render-stack` proof

The human-readable checklist lives at:

- [release-checklist.md](C:\codex projects\newbiz2-skill-repo\references\release-checklist.md)

## Known duplication to reduce next

`newbiz2` is now modular in orchestration, but it still deliberately duplicates stable machinery from `newbizintel`.

The highest-value duplication still present is:

- render and export scripts copied into `scripts\render\`
- QA scripts copied into `scripts\qa\`
- templates copied into `templates\`
- campaign-art fallback generator copied into `scripts\campaign-art\`

The next refactor should reduce duplication only in a way that preserves repo portability for colleagues. Until a shared layer is versioned and documented properly, self-contained duplication is preferred.

## Portability check

Use this repo-local audit to catch hidden machine-specific path dependencies before sharing the repo:

```powershell
.\scripts\qa\audit_portability.ps1
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/qa/audit_portability.ps1
```

## Useful commands

From the repo root:

```powershell
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode full
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode research-only
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode render-stack
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode research-only -ResearchMode live-summary -ResearchSummaryPath .\examples\research-summary.json
.\scripts\fixtures\run_univers_live_summary_proof.ps1
```

macOS or other Unix-like shells:

```bash
pwsh ./scripts/run_newbiz2.ps1 -DataPath ./examples/report-data.sample.json -Mode full
pwsh ./scripts/run_newbiz2.ps1 -DataPath ./examples/report-data.sample.json -Mode research-only
pwsh ./scripts/run_newbiz2.ps1 -DataPath ./examples/report-data.sample.json -Mode render-stack
pwsh ./scripts/run_newbiz2.ps1 -DataPath ./examples/report-data.sample.json -Mode research-only -ResearchMode live-summary -ResearchSummaryPath ./examples/research-summary.json
pwsh ./scripts/fixtures/run_univers_live_summary_proof.ps1
```
