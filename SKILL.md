---
name: newbiz2
description: Modular successor to newbizintel. Use when you want the same broad new-business intelligence workflow, but routed through smaller task skills coordinated by one orchestrator so research, assets, art, render, QA, and deploy can be run independently or resumed cleanly.
---

# NewBiz2

Use `newbiz2-orchestrator` first.

This root skill is only the entrypoint and routing policy. It should not absorb the whole workflow back into one monolith.

## Modules

- `newbiz2-orchestrator`: route work and manage gate state
- `newbiz2-intake`: create the working folder and settle identity assumptions
- `newbiz2-research`: gather Tavily and SEMrush-backed evidence
- `newbiz2-structure`: build and validate `report-data.json`
- `newbiz2-assets`: build and validate logos, marks, competitor badges, and source badges
- `newbiz2-campaign-art`: create or refresh Creative Campaign illustration prompts and final raster assets
- `newbiz2-render`: render HTML, portable HTML, PPTX, and bundle outputs
- `newbiz2-qa`: run presentation and smoke-test checks
- `newbiz2-deploy`: refresh handoff and deploy to Vercel

## Rules

- Keep `report-data.json` as the canonical final payload.
- Use `run-state.json` to support resumable modular runs.
- Prefer wrapping the copied `newbizintel` scripts over rewriting them.
- Keep the gating discipline. Modularization must not lower the evidence or QA standard.
- Keep `newbiz2` self-contained and cleanly shareable with colleagues.
- Do not introduce hidden dependencies on sibling folders or local workspace-only helper paths.
- Treat Creative Campaign artwork as a delivery-grade asset, not decoration. Production reports must use bundled final raster artwork marked `final-raster-artwork`; local scaffold, placeholder, unverified, missing, undersized, or non-raster campaign art is a fail condition.
- Use `scripts\qa\smoke_test_install.ps1` after installer or config-handoff changes so the colleague install path is proven, not assumed.
- Use `scripts\qa\release_check.ps1` before calling the repo ready to share or publish.
- Treat `Univers` as the current real-brand regression target for the full modular path.
- Prefer proving major orchestration or contract changes with `scripts\fixtures\run_univers_live_summary_proof.ps1` before claiming the modular workflow is stable.
