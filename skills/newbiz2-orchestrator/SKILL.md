---
name: newbiz2-orchestrator
description: Entry point for the modular newbiz2 workflow. Use when a user wants a full new-business intelligence run or a targeted refresh and the work should be routed across intake, research, structure, assets, campaign art, render, QA, and deploy modules rather than handled as one monolith.
---

# NewBiz2 Orchestrator

Route first. Do not default to running the entire workflow.

## Route by user intent

- Full report run:
  `intake -> research -> structure -> assets -> campaign-art -> render -> qa -> deploy`
- Research refresh:
  `intake if needed -> research -> structure if the user wants data refreshed`
- Asset refresh:
  `assets -> render -> qa -> deploy if requested`
- Campaign-art refresh:
  `campaign-art -> render -> qa -> deploy if requested`
- Render-only rebuild:
  `render -> qa -> deploy if requested`
- Deploy-only request:
  `deploy` only if render outputs are already fresh

## Contracts

- Canonical output payload: `report-data.json`
- Resumable module state: `run-state.json`

## Rules

- Preserve the gate discipline inherited from `newbizintel`.
- Reuse the copied scripts before inventing new implementations.
- Treat stale handoff files as a workflow failure. Refresh outputs before deploy.
- Do not let a partial module success masquerade as a passed gate.
