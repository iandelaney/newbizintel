---
name: newbiz2-research
description: Gather current-web, competitor, news, reputation, source, and SEO evidence for the modular newbiz2 workflow, using direct APIs where available. Use direct SEMrush API first, Composio-backed SEMrush as backup, Jina/direct web as current-web fallback, and clearly labelled Similarweb evidence when SEMrush is blocked or quota-limited.
---

# NewBiz2 Research

Own:

- current-web discovery through Tavily, direct web methods, or Jina fallback
- competitor set evidence
- recent news
- reputation and public-web evidence
- source gathering
- direct SEMrush API evidence first
- Composio-backed SEMrush evidence as backup
- clearly labelled Similarweb evidence when SEMrush routes are blocked, quota-limited, or unavailable

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

- Codex gathers current-web evidence with Tavily or direct web methods
- Codex uses Jina as the fallback current-web layer when Tavily is blocked, quota-limited, or too thin for the pass
- Codex uses the direct SEMrush API first when a key is available
- Codex uses the installed Composio MCP server as the SEMrush backup route when direct API access fails or is unavailable
- Codex may attach clearly labelled Similarweb public or authenticated evidence when SEMrush routes are blocked, quota-limited, or too thin
- Codex writes a structured `research-summary.json`
- the module imports that summary into the brand folder, validates it, and updates `run-state.json`

The local runners do not call MCP tools directly. Live collection happens in Codex through direct APIs, Tavily or direct web methods, Jina fallback, direct SEMrush API, Composio-backed SEMrush backup, and labelled Similarweb evidence where useful, then the summary is imported through the module contract.

The main current output is:

- `research-summary.json`

Use this module when you want to:

- inspect or refresh the normalized research layer without re-rendering the report
- populate locked competitor and influential-news sets in `run-state.json`
- prove that a `report-data.json` contains enough upstream evidence to continue through structure, render, and QA
