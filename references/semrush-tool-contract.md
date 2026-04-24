# SEMrush Tool Contract

Use Composio MCP for SEMrush evidence. Do not use Rube for SEMrush access.

## Priority Ladder

1. `SEMRUSH_DOMAIN_ORGANIC_SEARCH_KEYWORDS`
   - Purpose: find keyword demand, ranking gaps, and topic clusters.
   - Parameters: `{ "domain": "example.com", "database": "uk" }`
2. `SEMRUSH_COMPETITORS_IN_ORGANIC_SEARCH`
   - Purpose: validate the organic competitor set before report structure is locked.
   - Parameters: `{ "domain": "example.com", "database": "uk" }`
3. `SEMRUSH_INDEXED_PAGES`
   - Purpose: sanity-check index footprint and important page availability.
   - Parameters: `{ "target": "example.com", "target_type": "root_domain" }`
4. `SEMRUSH_BACKLINKS_OVERVIEW`
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
- `scripts\research\prepare_semrush_requests.ps1` should be run or recreated before live SEMrush collection so the exact Composio request set is inspectable.
