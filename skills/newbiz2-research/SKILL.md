---
name: newbiz2-research
description: Gather Tavily-backed current-web evidence and Composio-backed SEMrush evidence for the modular newbiz2 workflow. Use for competitor discovery, news, reputation, source gathering, and SEO evidence.
---

# NewBiz2 Research

Own:

- Tavily-backed discovery
- competitor set evidence
- recent news
- reputation and public-web evidence
- source gathering
- Composio-backed SEMrush evidence

Outputs should be structured enough for `newbiz2-structure` to map into `report-data.json` cleanly.

Do not render deliverables here.

## Current scaffold status

The current `newbiz2` research module is wired in bootstrap mode.

That means it can:

- normalize competitor, news, reputation, and SEO evidence from an existing `report-data.json`
- write `research-summary.json`
- update `run-state.json` and locked sets

It can also run in `live-summary` mode.

In that mode:

- Codex gathers current-web evidence with Tavily
- Codex uses Jina as the fallback current-web layer when Tavily is blocked, quota-limited, or too thin for the pass
- Codex attaches SEMrush evidence through the installed Composio MCP server when that connector is available in the session
- Codex writes a structured `research-summary.json`
- the module imports that summary into the brand folder, validates it, and updates `run-state.json`

The local PowerShell runner does not call MCP tools directly. Live collection happens in Codex through Tavily, Jina, and Composio, then the summary is imported through the module contract.

The main current output is:

- `research-summary.json`

Use this module when you want to:

- inspect or refresh the normalized research layer without re-rendering the report
- populate locked competitor and influential-news sets in `run-state.json`
- prove that a `report-data.json` contains enough upstream evidence to continue through structure, render, and QA
