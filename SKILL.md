---
name: newbiz2
description: Modular successor to newbizintel. Use when you want the same broad new-business intelligence workflow, but routed through smaller task skills coordinated by one orchestrator so research, assets, art, render, QA, and deploy can be run independently or resumed cleanly.
---

# NewBiz2

Use `newbiz2-orchestrator` first.

This root skill is only the entrypoint and routing policy. It should not absorb the whole workflow back into one monolith.

## Cross-Platform Runner

Use the Python runner by default:

```bash
python scripts/newbiz2.py run --mode full --brand-name "Brand" --website "https://www.example.com/" --brand-folder "/path/to/output"
```

PowerShell is now a Windows legacy/compatibility path only. Do not require Mac colleagues to install `pwsh`.

The Python runner must support the full modular workflow:

- intake
- research
- structure
- assets
- campaign-art
- render
- QA
- deploy handoff

It must write the same canonical artifacts as the legacy path:

- `report-data.json`
- `run-state.json`
- `workflow-task-list.json`
- `workflow-task-list.md`
- `required-logo-manifest.json`
- `source-badge-manifest.json`
- `newbizintel-report.html`
- `archive/newbizintel-report-portable.html`
- `newbizintel-report.pptx`
- `index.html`

Do not ask colleagues to install a separate Slides skill. The render path should first try the richer bundled PPTX renderer, then fall back to the no-extra-install Python OOXML writer so PPTX output still exists on a clean Mac.

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

## Canonical 10-Step Task List

The visible workflow task list, `run-state.json.task_list`, `workflow-task-list.json`, and `workflow-task-list.md` must use these same ten primary steps in this order:

1. Intake and workspace
   - Primary gate: `gate_1_intake`
   - Trust test: Brand folder, `report-data.json`, and `run-state.json` exist.
2. Competitor set
   - Primary gate: `gate_2_competitor_set`
   - Trust test: Competitor set is present in the research summary or report data.
3. Current research and source map
   - Primary gate: `gate_3_current_research`
   - Trust test: Research summary exists with news, reputation/source status, and locked sets.
4. Search and SEO evidence
   - Primary gate: `gate_4_search_seo_evidence`
   - Trust test: At least two SEO evidence points are available, with SEMrush status explicitly recorded as passed, partial, quota-limited, or blocked.
5. Report structure and data contract
   - Primary gate: `gate_5_report_structure`
   - Trust test: `report-data.json` passes schema validation and freshness is updated.
6. Brand, competitor, and source logos
   - Primary gate: `gate_6_logos_and_assets`
   - Trust test: Brand, competitor, and news/source logos resolve without generic fallbacks.
7. Creative campaign ideas and artwork
   - Primary gate: `gate_7_campaign_ideas_and_art`
   - Trust test: Campaign ideas pass editorial checks and artwork is final raster, not scaffold.
8. HTML, portable HTML, and PPTX render
   - Primary gate: `gate_8_render_outputs`
   - Trust test: Rendered HTML, portable HTML, and PPTX exist and are current.
9. Quality, trust, and presentation QA
   - Primary gate: `gate_9_quality_review`
   - Trust test: Editorial, presentation, logo, campaign-art, and PPTX audits pass.
10. Delivery handoff
    - Primary gate: `gate_10_delivery_handoff`
    - Trust test: Deploy handoff folder is refreshed from the latest report outputs.

## Rules

- Keep `report-data.json` as the canonical final payload.
- Use `run-state.json` to support resumable modular runs.
- Maintain the canonical 10-step `task_list` in `run-state.json`; each passed task must be backed by its trust test, and later tasks must not pass while earlier tasks are incomplete.
- Prefer wrapping the copied `newbizintel` scripts over rewriting them.
- Use the hybrid execution model in `references\hybrid-parallel-agentic-workflow.md`: deterministic parallel jobs for isolated repeatable work, agentic workers only for synthesis, source judgement, campaign thinking, and art direction.
- The default execution model is `hybrid`. Each run must record required fan-out and reducer events in `run-state.json`; QA must fail if a run claims to be hybrid but has not recorded the required research, asset, campaign-art, and QA fan-out/reducer evidence.
- For live research, default to cheap deterministic collectors first: Tavily Search, direct source reads, Jina extraction, SEMrush API or Composio where available. Codex performs the research synthesis and source judgement from those workpacks. Tavily Research is an explicit escalation only when cheap coverage is insufficient or the question genuinely needs deep paid research.
- The Brand Reputation / influential-news gate must prove rigour, diversity, and confidence before passing. Do not accept five convenient recent links. The final story set must be reduced from at least 12 candidate stories, use at least 4 distinct search queries, cover at least 3 source classes, use at least 3 distinct publishers, include no more than 2 stories from the same publisher, and be ordered by `influence_score` descending. Each story must include `source_type`, `sentiment`, `influence_score`, and `rank_reason`; the ranking method must include `confidence_score`, `confidence_rationale`, `limitations`, and the required ranking factors.
- Brand report outputs must live under the resolved output root, normally `C:\codex projects\output\<brand-slug>`. Do not default to a skill-local `output` folder. Deploy handoff files must remain in the brand output folder or a child of it; do not create sibling folders such as `output\vercel` for brand report artifacts.
- Proof, fixture, and disposable test artifacts are not brand report outputs. Create them through `scripts\common\resolve_proof_root.ps1`, which defaults to `C:\codex projects\tmp-newbiz2-proofs` or `NEWBIZ2_PROOF_ROOT`, and must refuse locations inside the delivery output root such as `output\skill-runs`.
- For SEMrush, favour direct API access first. If `SEMRUSH_API_KEY` is available, the research module should automatically select and run the direct SEMrush API collector without requiring a separate reminder flag. If the operator supplies `-SemrushApiKey`, use it only as an in-process runtime secret for that run and never write it to repo files, report artifacts, run state, notes, or output JSON. If direct API is unavailable, quota-limited, or blocked, use Composio MCP as the SEMrush backup before falling back to Jina/public-web context. Jina/public-web evidence must never be described as SEMrush-backed.
- Keep the gating discipline. Modularization must not lower the evidence or QA standard.
- Keep `newbiz2` self-contained and cleanly shareable with colleagues.
- Do not introduce hidden dependencies on sibling folders or local workspace-only helper paths.
- Do not require PowerShell or a separate Slides skill on macOS. Python plus optional Node is acceptable; PPTX must still have a bundled fallback when optional render dependencies are absent.
- Treat Creative Campaign artwork as a delivery-grade asset, not decoration. Production reports must use bundled final raster artwork marked `final-raster-artwork`; local scaffold, placeholder, unverified, missing, undersized, or non-raster campaign art is a fail condition.
- Use `scripts\qa\smoke_test_install.ps1` after installer or config-handoff changes so the colleague install path is proven, not assumed.
- Use `scripts\qa\release_check.ps1` before calling the repo ready to share or publish.
- Treat `Univers` as the current real-brand regression target for the full modular path.
- Prefer proving major orchestration or contract changes with `scripts\fixtures\run_univers_live_summary_proof.ps1` before claiming the modular workflow is stable.
