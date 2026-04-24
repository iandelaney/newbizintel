# SEMrush Tool Contract

Use direct SEMrush API evidence when `SEMRUSH_API_KEY` is available in the
environment. Keep the key out of source files, report data, logs, and committed
artifacts.

Use Composio MCP as the managed fallback when direct API access is not configured.
Do not use Rube for SEMrush access.

## Direct API Path

Run:

```powershell
scripts\research\collect_semrush_api.ps1 -DataPath .\output\brand\report-data.json -Database uk -OutputPath .\output\brand\semrush-api-evidence.json
```

Then merge into the research summary:

```powershell
scripts\research\apply_semrush_api_evidence.ps1 -ResearchSummaryPath .\output\brand\research-summary.json -SemrushEvidencePath .\output\brand\semrush-api-evidence.json
```

The collector calls SEMrush Domain Analytics via `https://api.semrush.com/` and
currently gathers:

- `domain_organic`: organic keyword positions
- `domain_organic_organic`: organic search competitors
- `domain_organic_unique`: ranking pages

The output should include compact `seo.semrush_evidence` proof points and a raw
dataset summary for auditability.

## Priority Ladder

1. Direct API `domain_organic`
   - Purpose: find keyword demand, ranking gaps, and topic clusters.
   - Key source: `SEMRUSH_API_KEY` environment variable.
2. Direct API `domain_organic_organic`
   - Purpose: validate the organic competitor set before report structure is locked.
3. Direct API `domain_organic_unique`
   - Purpose: identify pages where organic visibility is concentrated.
4. Composio `SEMRUSH_DOMAIN_ORGANIC_SEARCH_KEYWORDS`
   - Purpose: find keyword demand, ranking gaps, and topic clusters.
   - Parameters: `{ "domain": "example.com", "database": "uk" }`
5. Composio `SEMRUSH_COMPETITORS_IN_ORGANIC_SEARCH`
   - Purpose: validate the organic competitor set before report structure is locked.
   - Parameters: `{ "domain": "example.com", "database": "uk" }`
6. Composio `SEMRUSH_INDEXED_PAGES`
   - Purpose: sanity-check index footprint and important page availability.
   - Parameters: `{ "target": "example.com", "target_type": "root_domain" }`
7. Composio `SEMRUSH_BACKLINKS_OVERVIEW`
   - Purpose: add authority/context evidence if keyword or competitor evidence is thin.
   - Parameters: `{ "target": "example.com", "target_type": "root_domain" }`

## Status Rules

- `passed`: at least two compact SEMrush-backed proof points can be used in `report-data.json`.
- `partial`: at least one SEMrush dataset is available, but evidence should be supplemented by Tavily/Jina and direct site inspection.
- `quota-limited`: the Composio SEMrush connection exists but quota or entitlement prevents full retrieval; keep the generated request plan in the workpack and use Jina/direct public web as backup.
- `blocked`: SEMrush cannot be reached or authenticated; do not fabricate SEMrush evidence.

## Fallback Discipline

- Prefer Jina AI as the first public-web backup when SEMrush is `partial`, `quota-limited`, or `blocked`.
- The SEO section can pass only when the final report contains evidence-backed claims. If SEMrush is unavailable, label the limitation in workflow notes, not in the client-facing report copy.
- `scripts\research\collect_semrush_api.ps1` should be run first when `SEMRUSH_API_KEY` is available.
- `scripts\research\prepare_semrush_requests.ps1` should be run or recreated before Composio-backed SEMrush collection so the exact request set is inspectable.
