# Hybrid Parallel And Agentic Workflow

`newbiz2` should use deterministic parallel jobs where the task is repeatable and
side-effect safe, and agentic workers only where judgement improves quality.

## Deterministic Parallel Jobs

Use script-level parallel jobs when each task can read the same input and write to
its own output file.

- Safe now: schema validation, brand asset validation, required logo manifest,
  source badge manifest, editorial QA, and campaign-art QA before render.
- Best candidate: logo acquisition. Brand, competitor, and publisher/source
  logos can be resolved in parallel as isolated jobs. Each job should write a
  candidate manifest and any downloaded favicon/logo to a unique temporary path.
  A reducer should then choose accepted assets, move them into `slide-assets`,
  update logo fields in `report-data.json`, and write `required-logo-manifest.json`.
- Safe next: independent research collectors, if each writes to a workpack file
  and a reducer builds `research-summary.json`.
- Best candidate: campaign artwork. Prompt generation and per-campaign image
  generation can fan out, but every generated image must come back through the
  deterministic importer/normaliser and the delivery-grade campaign-art audit.
  Placeholder or scaffold artwork must never be promoted by a reducer.

Do not let parallel jobs write `run-state.json` or `report-data.json` directly at
the same time. Workers should write isolated files; reducers should merge and
update canonical state.

## Agentic Workers

Use agentic workers where quality depends on synthesis, judgement, or taste.

- Research synthesis: judge source credibility, reconcile contradictory evidence,
  and decide what belongs in the client-facing argument.
- Campaign idea generation: create sharper campaign territories, names,
  activation sequences, and creative rationale.
- Source evaluation: assess whether a source is materially useful, not merely
  available.
- Artwork direction: choose surprising but theme-appropriate treatments and write
  generation prompts that avoid text, logos, and brand assets. Parallel artwork
  workers are allowed to propose or generate one campaign image each, but final
  acceptance remains deterministic: correct aspect, raster file, no scaffold
  metadata, no target logos, no text, and `final-raster-artwork` role.

Agentic workers should return structured outputs only. They should not mutate the
canonical report files directly unless a bounded worker owns that file and no
other worker is writing to it.

## Gate Pattern

1. Fan out workers or jobs into isolated work files.
2. Reduce those files into `research-summary.json`, `report-data.json`, or
   `slide-assets`.
3. Run QA gates on the canonical result.
4. Update `run-state.json` only after the reducer and gates finish.

This keeps the workflow faster without turning it into soup with a clipboard.
