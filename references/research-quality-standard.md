# Research Quality Standard

Use this standard to decide whether a `newbizintel` research run is fit to move from research into structure, render, QA, and delivery.

This is a pass/fail standard, not a best-efforts aspiration.

## Purpose

The research layer must be:

- broad enough to avoid shallow or single-source conclusions
- fresh enough to support claims about recent conditions
- source-disciplined enough to survive scrutiny
- specific enough to the target brand to avoid generic filler
- protected enough against cross-client or ambiguous-brand contamination

If any required category fails, the run should be treated as blocked until repaired.

## Overall rule

A run passes only if all five categories below pass:

1. breadth
2. freshness
3. source quality
4. anti-generic specificity
5. contamination protection

Do not trade a failure in one category against strength in another.

## 1. Breadth

### Pass when

- The run has a credible competitor set, not just one or two adjacent names.
- The run has a meaningful current-research pack rather than a single-page scrape or one-source summary.
- The reputation/news shortlist is reduced from a broader candidate pool rather than chosen ad hoc.
- The run includes both owned-source evidence and external evidence where the section requires it.
- The SEO section uses structured search evidence when available, rather than generic web commentary alone.

### Minimum pass criteria

- Competitor set:
  - at least `4` real competitors for most categories
  - at least `3` only when the market is genuinely narrow
- Influential news candidate pool:
  - at least `12` discovered candidates before reduction
- Final influential-news shortlist:
  - `5` or `6` items only
- Distinct discovery paths:
  - at least `4` broad discovery queries
  - at least `3` verification queries for the final shortlist
- Research workpacks:
  - enough separate workpacks to show competitor discovery, recent-news discovery, reputation/public-web discovery, and source gathering

### Fail when

- The competitor set is thin, generic, or obviously wrong.
- The report jumps straight to a final shortlist without a visible candidate pool.
- The run depends on one publisher, one source class, or one discovery query family.
- SEO claims are made without structured SEO evidence or clearly labelled fallback status.

## 2. Freshness

### Pass when

- Time-bounded sections only contain evidence inside the declared window.
- Recent claims are tied to exact dates, not vague recency language.
- The report date and the evidence window agree with one another.

### Minimum pass criteria

- Every item in `Most Influential News Stories in the Last Six Months`:
  - must have an exact day-month-year publication date
  - must fall inside the rolling six-month window ending on the current run date
  - must not be future-dated
- Undated pages, aggregate pages, and newsroom index pages:
  - may support context
  - must not appear as final influential stories
- Time-sensitive SEO, traffic, or reputation claims:
  - must include `observed_at`, publication date, or equivalent provenance when available

### Fail when

- An out-of-window story appears in a time-bounded section.
- A dated section includes undated material as if it were a story.
- The run relies on stale evidence without explicit labelling.
- “Latest”, “current”, “recent”, or “last six months” is asserted without evidence discipline.

## 3. Source Quality

### Pass when

- The report uses source types appropriate to the claim being made.
- Strong claims are backed by verifiable URLs and identifiable publishers.
- The run distinguishes between first-party, third-party, analyst, trade, and aggregator evidence.

### Minimum pass criteria

- Every final influential story must have:
  - a verifiable source URL
  - a named publisher/source
  - an identifiable source type
- The final influential-news shortlist should include:
  - at least `3` distinct publishers
  - at least `3` source classes where the category allows it
- Owned sources:
  - may be included
  - must not dominate by default without a stated limitation
- SEO evidence:
  - must use direct SEMrush or plugin-returned SEMrush evidence when available
  - fallback evidence must be clearly labelled as fallback, not silently presented as equivalent

### Fail when

- A final story has no exact source URL.
- A source is mislabelled, duplicated, or linked to the wrong publisher.
- A review page, homepage, or aggregate page is used as if it were a dated story.
- The report presents weak, generic, or unverifiable pages as strong evidence.

## 4. Anti-Generic Specificity

### Pass when

- The messaging, company snapshot, and recommendation sections sound like this brand, not any brand.
- Claims are grounded in the current run’s actual evidence, category, and business model.
- StoryBrand and messaging sections reflect the target’s real operating context, not generic marketing language.

### Minimum pass criteria

- StoryBrand content must:
  - materially overlap with current run evidence
  - use target-specific operating themes
  - avoid canned placeholder phrases
- Company snapshot must:
  - include concrete facts about company status, leadership, ownership/funding, and scale where available
  - avoid fallback boilerplate like “source pending” or generic template prose
- SEO and recommendation sections must:
  - refer to the target’s real category, competitors, and issues
  - avoid advice that would fit almost any unrelated brand

### Fail when

- StoryBrand cards read as category-generic filler.
- The one-liner or recommendations could be swapped onto another client with little change.
- Placeholder wording, template language, or unfinished scaffold text remains in delivery output.
- The report makes broad claims with weak or no brand-specific evidence overlap.

## 5. Contamination Protection

### Pass when

- The report belongs clearly to this client, this category, and this run.
- Ambiguous-brand or cross-client residue is filtered out before delivery.
- Final content does not contain alien entities, sectors, or stale project baggage.

### Minimum pass criteria

- The final report must not contain:
  - unrelated client names
  - unrelated category-specific residue
  - obvious ambiguous-brand noise in appendix/source lists
- The competitor set, influential-news shortlist, and appendix/source map must:
  - survive identity checks against the run’s brand and category context
  - reject irrelevant broad-web noise
- Broad discovery queries must:
  - be genuinely broad
  - not pre-select exact final stories or publishers

### Fail when

- Cross-client vocabulary survives into report data or rendered output.
- Ambiguous-name noise is treated as if it belongs to the target brand.
- The appendix/source list includes irrelevant local-business, entertainment, or unrelated web noise.
- A validator only catches one known contamination pattern instead of the broader identity mismatch.

## Severity

Treat failures differently by impact:

- `Critical`
  - anything that makes the report misleading or untrustworthy
  - examples: stale time-bounded stories, wrong publisher links, generic StoryBrand filler, obvious cross-client contamination
- `Major`
  - weak but repairable evidence structure
  - examples: too-thin candidate pool, overuse of owned sources, weak source diversity
- `Minor`
  - non-blocking quality drift
  - examples: under-documented limitations, slightly thin rationale wording, mild provenance untidiness

Only `Minor` issues may ship without repair, and they must be noted explicitly.

## Release gate

Before a report is treated as delivery-ready, confirm:

- Breadth: `pass`
- Freshness: `pass`
- Source quality: `pass`
- Anti-generic specificity: `pass`
- Contamination protection: `pass`

If any category is not `pass`, the run is not delivery-ready.

## Current implementation intent

The workflow should increasingly enforce this standard through:

- report-data validation
- QA audits
- research reducer checks
- rendered-output identity checks

Where automation is not yet complete, use this document as the manual acceptance bar and backlog guide.
