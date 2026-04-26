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
- `newbiz2-deploy`: refresh handoff and prepare optional Vercel deployment

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
   - Trust test: Brand, competitor, and news/source logos resolve without generic fallbacks. Competitor logos must prefer real square marks, favicons, or app icons over wide wordmarks; if no real square mark exists, create a square badge by trimming and centring the real acquired wordmark rather than using a generic text card. A square asset is not enough on its own: the visible logo content must occupy enough of the badge to be legible in the competitor table. Wide wordmarks must be converted into square initial-letter marks, not rectangular table logo assets or tiny square-padded wordmarks.
7. Creative campaign ideas and artwork
   - Primary gate: `gate_7_campaign_ideas_and_art`
   - Trust test: Campaign ideas must have a developed driving idea, descriptive implementation story, narrative activation sequence, and final raster artwork rather than scaffold, generic bullet-only plans, or component shopping lists. The artwork set must be diverse. The gate must fail if multiple campaign images repeat the same broad treatment family such as technical/interface, poster/collage, photography, painting, sculpture/paper, comic/graphic, or cartographic, or if image fingerprint checks find two raster assets that are visually too similar.

## Department Opportunity Signals

The `agency_opportunity.department_opportunity_map` items are an external-facing opportunity section, not an internal department-selection rubric.

- The rendered cards must describe the actual opportunity each department has with the target brand.
- Do not render `value_note`, "Value:", lead-selection rules, sequencing rules, "best when", "only when", or "should lead/follow" language inside the card grid.
- Use `opportunity_signal` as the card body. `rationale` may support downstream tables, but should still explain the concrete brand opportunity rather than internal agency rules.
- Status fields such as `tone`, `opportunity`, `cost_multiplier`, and `lead_department` may remain in the data for scoring, ordering, and later workflow decisions, but must not be the visible lead content of the cards.
- Do not render a separate `Department Opportunity Map` table. It duplicates the cards and tends to expose internal scoring/rubric language.
8. HTML, portable HTML, and PPTX render
   - Primary gate: `gate_8_render_outputs`
   - Trust test: Rendered HTML, portable HTML, and PPTX exist and are current.
9. Quality, trust, and presentation QA
   - Primary gate: `gate_9_quality_review`
   - Trust test: Editorial, presentation, logo, campaign-art, and PPTX audits pass.
10. Delivery handoff
    - Primary gate: `gate_10_delivery_handoff`
    - Trust test: Deploy handoff folder is refreshed from the latest report outputs and the user is asked whether they want a random-url Vercel deployment.

## Rules

- Keep `report-data.json` as the canonical final payload.
- Use `run-state.json` to support resumable modular runs.
- Maintain the canonical 10-step `task_list` in `run-state.json`; each passed task must be backed by its trust test, and later tasks must not pass while earlier tasks are incomplete.
- Run the anti-placeholder audit before research, structure, render, or QA gates can pass. Production report data and research summaries must not contain template markers such as `Example Brand`, `Competitor A`, fake example publishers, `example.com` URLs, or `Replace with...` instructions. Only repo-local fixture examples may retain intentional placeholder content, and that must be reported as a warning rather than a pass condition for real reports.
- Prefer wrapping the copied `newbizintel` scripts over rewriting them.
- Use the hybrid execution model in `references\hybrid-parallel-agentic-workflow.md`: deterministic parallel jobs for isolated repeatable work, agentic workers only for synthesis, source judgement, campaign thinking, and art direction.
- The default execution model is `hybrid`. Each run must record required fan-out and reducer events in `run-state.json`; QA must fail if a run claims to be hybrid but has not recorded the required research, asset, campaign-art, and QA fan-out/reducer evidence.
- For live research, default to deterministic fan-out first: Tavily Search, direct source reads, Jina extraction, SEMrush API or Composio where available. `--research-mode live-summary` must create Tavily Search workpacks itself when no `--research-summary-path` is supplied, reduce them into `research-summary.draft.json`, and only promote `research-summary.json` after validation passes. Codex performs the initial research synthesis and source judgement from those workpacks. For Brand Reputation, Tavily Research is the default quality layer, not a fallback: cheap search creates the broad candidate pool, then Tavily Research must produce the final influential-story set with citations, scoring, source diversity, and confidence evidence unless the operator explicitly passes `--no-tavily-reputation-research`.
- The Brand Reputation / influential-news gate must prove rigour, diversity, confidence, and objective story selection before passing. Do not accept five convenient recent links, and do not start by searching for stories you already expect to use. The required order is broad discovery first, candidate-pool scoring second, targeted verification last. The ranking method must set `discovery_mode` to `broad_first_scored_reduction`, include `candidate_pool_summary`, list at least 4 `broad_discovery_queries`, document the `discovery_sequence`, and keep story-specific checks in `verification_queries` only after scoring. The final story set must be reduced from at least 12 candidate stories, cover at least 3 source classes, use at least 3 distinct publishers, include no more than 2 stories from the same publisher, and be ordered by `influence_score` descending. Each story must include `source_type`, `sentiment`, `influence_score`, `influence_subscores`, and `rank_reason`; the ranking method must include `confidence_score`, `confidence_rationale`, `limitations`, `score_weights`, and the required ranking factors. `influence_score` must be mathematically derived from weighted subscores: source authority 25%, buyer relevance 25%, reputation risk or opportunity 20%, evidence quality 15%, novelty 10%, and recency 5%.
- The Messaging section must begin with an assessment of existing published messaging before the StoryBrand analysis. Use `storybrand.existing_messaging_assessment` with at least two published mission, purpose, promise, proposition, or brand-platform statements, their source labels and source URLs, a reputation read-across, and a practical implication. Render those source labels as hyperlinks so readers can verify the published statements. Do not change the StoryBrand cards to satisfy this requirement; instead, let the published-message assessment frame them. `storybrand.messaging_fixes` and `storybrand.content_implications` must explain the WHY behind each recommendation and must explicitly draw on reputation, trust, service, growth, proof, customer, or technology findings.
- Brand report outputs must live under the resolved output root, normally `C:\codex projects\output\<brand-slug>`. Do not default to a skill-local `output` folder. Deploy handoff files must remain in the brand output folder or a child of it; do not create sibling folders such as `output\vercel` for brand report artifacts.
- End every full report run by asking the user whether they would like the finished report deployed to Vercel. Do not deploy automatically. Ask: "Would you like me to deploy this report to Vercel as a randomly named preview URL?"
- If the user says yes to Vercel deployment, use the `vercel-deploy` skill. First run the NewBiz2 random staging command (`python scripts/newbiz2.py vercel-stage --data-path "<brand-folder>/report-data.json"`) and pass the returned `deploy_path` to `vercel-deploy`; never deploy the brand output folder directly.
- Vercel uploads from NewBiz2 must always use a random staging folder/project identity so generated URLs do not include the target brand name, brand slug, or domain. If the returned URL contains the brand name, brand slug, or domain token, treat it as a failed deployment handoff and create a fresh random stage before trying again.
- Proof, fixture, and disposable test artifacts are not brand report outputs. Create them through `scripts\common\resolve_proof_root.ps1`, which defaults to `C:\codex projects\tmp-newbiz2-proofs` or `NEWBIZ2_PROOF_ROOT`, and must refuse locations inside the delivery output root such as `output\skill-runs`.
- For SEMrush, favour direct API access first. If `SEMRUSH_API_KEY` is available, the research module should automatically select and run the direct SEMrush API collector without requiring a separate reminder flag. If the operator supplies `-SemrushApiKey`, use it only as an in-process runtime secret for that run and never write it to repo files, report artifacts, run state, notes, or output JSON. If direct API is unavailable, quota-limited, or blocked, use Composio MCP as the SEMrush backup before falling back to SimilarWeb, Jina, or other public-web context. SimilarWeb/public-web evidence can satisfy the broader Search and SEO evidence gate when clearly sourced and labelled, but must never be described as SEMrush-backed.
- SEO charts must be self-explaining. Prefer raw or clearly derived search metrics from SEMrush, Similarweb, GSC, or another named provider. If a chart uses judgement scores, the title or subtitle must say it is an indexed interpretation, the subtitle must name the evidence base, and every row note must cite the underlying search or traffic signal. Do not use vague subtitles such as "Strategic read from public evidence" in the SEO section.
- When target and competitor search visibility evidence exists, add a target-vs-competitor visibility comparison chart. Use raw metrics where possible; if using ranks, make the conversion explicit, display the original rank, and state that lower rank means stronger visibility.
- The closing Opportunities section must lead with `opportunities.marketing_strategy`: a concise articulation of the recommended marketing strategy for the target brand. It must synthesise findings from across the report, not introduce a disconnected generic plan. The strategy must explicitly draw on reputation, messaging/proof, search/SEO, competitor, and campaign/content findings before the 30/60/90 recommendations.
- Render `Creative Campaign Ideas` after `Opportunities`, not before it. The campaign ideas are examples of the recommended strategy in action, so the reader must see the strategy and 30/60/90 priorities before the creative territories.
- Render `Content Strategy Recommendations` after `Creative Campaign Ideas`. The content recommendations and asset ideas should be read as the channel/content expression of the strategy and campaign territories, not as a disconnected plan that precedes them.
- Appendix sources must be verifiable without turning the section into a sea of blue links. Render each source label as normal text followed by a compact hyperlinked `[link]` marker when a URL is available, and prefer the richer `appendix.source_map` labels over bare `appendix.sources_reviewed` URLs.
- Keep the gating discipline. Modularization must not lower the evidence or QA standard.
- Keep `newbiz2` self-contained and cleanly shareable with colleagues.
- Do not introduce hidden dependencies on sibling folders or local workspace-only helper paths.
- Do not require PowerShell or a separate Slides skill on macOS. Python plus optional Node is acceptable; PPTX must still have a bundled fallback when optional render dependencies are absent.
- Treat Creative Campaign artwork as a delivery-grade asset, not decoration. Production reports must use bundled final raster artwork marked `final-raster-artwork`; local scaffold, placeholder, unverified, missing, undersized, or non-raster campaign art is a fail condition.
- Treat Creative Campaign artwork diversity as a quality gate, not a subjective nice-to-have. If two ideas look samey, especially because they share a broad medium or treatment family, regenerate or replace one before render/QA.
- Treat Creative Campaign copy as campaign imagination, not a production checklist. Each idea must let a reader envisage the campaign as a whole: a clear driving idea, a descriptive implementation story, and a short narrative sequence for how it takes shape. Keep internal production details such as required inputs available in the data, but do not render the section as dense "should contain" / "needs as input" bullet lists.
- Use `scripts\qa\smoke_test_install.ps1` after installer or config-handoff changes so the colleague install path is proven, not assumed.
- Use `scripts\qa\release_check.ps1` before calling the repo ready to share or publish.
- Use `npm run qa:visual -- --html "<report-html>" --selector "#section-id" --out "<screenshot.png>"` for local browser visual checks; the repo declares Playwright as a dev dependency, so do not rely on ad-hoc global `require("playwright")` availability.
- Treat `Univers` as the current real-brand regression target for the full modular path.
- Prefer proving major orchestration or contract changes with `scripts\fixtures\run_univers_live_summary_proof.ps1` before claiming the modular workflow is stable.
