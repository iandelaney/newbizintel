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
- `research-summary.json` can also be imported in `live-summary` mode after Codex gathers current-web evidence with Tavily or direct web methods, uses direct SEMrush API evidence first, falls back to Composio-backed SEMrush when needed, uses Jina as a current-web backup, and may use clearly labelled Similarweb evidence when SEMrush routes are blocked or quota-limited
- `newbiz2-structure` now consumes `research-summary.json` when present and writes the live research layer back into `report-data.json` before validation
- `run-state.json` is updated as modules complete
- `scripts/newbiz2.py` is the default cross-platform runner for colleagues; the PowerShell runner remains available for Windows compatibility and legacy module wrappers
- HTML, portable HTML, native PPTX, and deploy handoff outputs are produced from the copied stable `newbizintel` machinery plus a PptxGenJS deck path aligned to the `slides` skill
- the full modular chain is proven on the real Univers brand folder through `research -> structure -> assets -> campaign-art -> render -> qa -> deploy-handoff`
- premium Creative Campaign art now defaults to prompt-driven image-generated raster artwork, with local scaffold placeholders allowed only when a report explicitly opts into scaffold mode

## Premium campaign art

The premium Creative Campaign path is now:

1. Prepare prompts and handoff files:

```bash
python scripts/newbiz2.py campaign-art --data-path ./output/<brand>/report-data.json
```

2. Generate one raster image per prompt from the produced brief and manifest:

- `slide-assets/<brand>-campaign-illustration-prompts.json`
- `slide-assets/<brand>-campaign-art-brief.md`

3. Import the resulting batch and clear the campaign-art gate:

```bash
python scripts/newbiz2.py campaign-art --data-path ./output/<brand>/report-data.json --campaign-art-source-dir <folder-with-final-images> --campaign-art-overwrite-final
```

Or, when the images were just created by Codex image generation:

```bash
python scripts/newbiz2.py campaign-art --data-path ./output/<brand>/report-data.json --campaign-art-latest-generated-batch --campaign-art-overwrite-final
```

The Python runner now applies the prompt manifest, imports the final imagegen raster batch, then audits the actual final files in one gate. The import step normalizes the images into the expected portrait PNG outputs, marks them as `final-raster-artwork`, and lets QA distinguish true final art from placeholder scaffold output. The PowerShell wrapper remains available as a Windows compatibility path, but it is not required for macOS users.

## Colleague install

`newbiz2` is intended to be installable on both Windows and macOS.

Prerequisites:

- Windows: Python 3.10+, Node.js, npm, and PowerShell or `pwsh` available.
- macOS: `python3`, `node`, and `npm` available on `PATH`.

Current production-render caveat: the runner is Python-first, but the rich HTML renderer still calls `scripts/render/render_report.ps1`. That means a full production render currently needs PowerShell or `pwsh`; removing this is the remaining dependency gap before macOS is truly no-PowerShell end to end.

The Python runtime also needs platform-native packages for image/logo QA and PPTX generation:

- `Pillow`
- `python-pptx`
- `lxml`
- `typing_extensions`
- `XlsxWriter`

The installer copies the vendored runtime and refreshes it automatically when the bundled runtime does not match the current platform or Python version. You can run the refresh manually with `./bootstrap-runtime.sh` on macOS/Linux or `.\bootstrap-runtime.ps1` on Windows.

Windows PowerShell:

```powershell
.\install-local.ps1
```

macOS or other Unix-like shells:

```bash
./install-local.sh
```

The install path also runs `npm install --omit=dev` inside the installed `newbiz2` skill so the native PptxGenJS deck exporter is ready for PPTX generation. It also verifies the Python runtime modules and rebuilds `vendor/pptx_runtime` when the checked-in runtime is for a different OS or Python version.

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
python3 ./scripts/newbiz2.py run --mode render-stack --data-path ./examples/report-data.sample.json
python3 ./scripts/newbiz2.py qa --data-path ./examples/report-data.sample.json
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

- Python 3.10+ and importable runtime modules: `Pillow`, `python-pptx`, and `lxml`
- a usable Node/npm runtime
- the required package manifests, `assets`, companion skills, and config example
- the current rich HTML renderer dependency on PowerShell or `pwsh`
- a writable Codex root

If the Python runtime check fails, run:

Windows PowerShell:

```powershell
.\bootstrap-runtime.ps1
```

macOS or other Unix-like shells:

```bash
./bootstrap-runtime.sh
```

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
python3 ./scripts/newbiz2.py run --mode render-stack --data-path ./examples/report-data.sample.json
```

Then check portability before sharing onward:

Windows PowerShell:

```powershell
.\scripts\qa\audit_portability.ps1
```

macOS or other Unix-like shells:

```bash
python3 ./scripts/newbiz2.py qa --data-path ./examples/report-data.sample.json
```

Then run the repo-local install smoke test to prove the colleague install path still works:

Windows PowerShell:

```powershell
.\scripts\qa\smoke_test_install.ps1
```

macOS or other Unix-like shells:

```bash
./scripts/qa/check_prereqs.sh
```

### 7. Prove the real gold path when available

If the Univers proof inputs exist locally, run:

Windows PowerShell:

```powershell
.\scripts\fixtures\run_univers_live_summary_proof.ps1
```

macOS or other Unix-like shells:

```bash
python3 ./scripts/newbiz2.py run --mode render-stack --data-path ./examples/report-data.sample.json
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

- the local runners do not call MCP tools directly; live research is gathered in Codex through direct APIs, Tavily or direct web methods, Jina as backup, direct SEMrush API first, Composio-backed SEMrush as backup, and labelled Similarweb evidence where useful, then imported through `live-summary` mode

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
python3 ./scripts/newbiz2.py run --mode render-stack --data-path ./examples/report-data.sample.json
python3 ./scripts/newbiz2.py qa --data-path ./examples/report-data.sample.json
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

Use the Python QA path as the cross-platform portability smoke test before sharing the repo:

```bash
python3 ./scripts/newbiz2.py qa --data-path ./examples/report-data.sample.json
```

On Windows, the legacy PowerShell audit can also catch machine-specific path dependencies:

```powershell
.\scripts\qa\audit_portability.ps1
```

## Useful commands

From the repo root, use the Python runner by default.

Windows:

```powershell
py .\scripts\newbiz2.py run --mode full --data-path .\examples\report-data.sample.json
py .\scripts\newbiz2.py run --mode research-only --data-path .\examples\report-data.sample.json
py .\scripts\newbiz2.py run --mode render-stack --data-path .\examples\report-data.sample.json
py .\scripts\newbiz2.py run --mode research-only --data-path .\examples\report-data.sample.json --research-mode live-summary --research-summary-path .\examples\research-summary.json
py .\scripts\newbiz2.py qa --data-path .\examples\report-data.sample.json
```

macOS or other Unix-like shells:

```bash
python3 ./scripts/newbiz2.py run --mode full --data-path ./examples/report-data.sample.json
python3 ./scripts/newbiz2.py run --mode research-only --data-path ./examples/report-data.sample.json
python3 ./scripts/newbiz2.py run --mode render-stack --data-path ./examples/report-data.sample.json
python3 ./scripts/newbiz2.py run --mode research-only --data-path ./examples/report-data.sample.json --research-mode live-summary --research-summary-path ./examples/research-summary.json
python3 ./scripts/newbiz2.py qa --data-path ./examples/report-data.sample.json
```

The PowerShell runner remains available for Windows compatibility:

```powershell
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode full
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode research-only
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode render-stack
.\scripts\run_newbiz2.ps1 -DataPath .\examples\report-data.sample.json -Mode research-only -ResearchMode live-summary -ResearchSummaryPath .\examples\research-summary.json
.\scripts\fixtures\run_univers_live_summary_proof.ps1
```
