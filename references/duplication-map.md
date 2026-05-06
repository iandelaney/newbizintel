# Duplication Map

This file records the intentional overlap between legacy `newbizintel` machinery and the active modular `newbizintel` workflow.

The rule for now is:

- keep `newbizintel` stable
- keep the modular workflow self-contained and colleague-shareable
- keep the active path modular
- reduce duplication only when the Univers gold-path regression fixture still passes afterwards
- never replace duplication with a hidden local sibling dependency

## Current duplicated areas

### Render stack

Copied into the modular workflow:

- `scripts\render\render_report.ps1`
- `scripts\render\export_report_bundle.ps1`
- `scripts\render\build_report_bundle.ps1`
- `scripts\render\make_html_self_contained.py`
- `scripts\render\report_data_to_pptx.py`

Why duplicated:

- these scripts are stable enough to reuse immediately
- they let orchestration mature before shared-library refactoring
- keeping them local avoids creating an undeclared dependency outside the repo

### QA stack

Copied into the modular workflow:

- `scripts\qa\audit_presentation_layer.ps1`
- `scripts\qa\smoke_test_bundle.ps1`
- `scripts\structure\validate_report_data.ps1`
- `scripts\assets\validate_brand_assets.ps1`

Why duplicated:

- gate behavior must remain explicit inside the modular repo
- local copies are clearer for colleagues than a hidden shared workspace layer

### Templates

Copied into the modular workflow:

- `templates\report-template.html`
- `templates\report-data.template.json`

Why duplicated:

- modular render and QA need repo-local canonical templates
- templates should ship with the repo so a colleague can clone and run it directly

### Campaign-art fallback

Copied into the modular workflow:

- `scripts\campaign-art\generate_campaign_illustrations.py`

Why duplicated:

- The active modular workflow owns the campaign-art stage even when premium raster art is handled outside the fallback generator
- colleagues should receive one portable repo, not a repo plus an undocumented local helper tree

## Safe order for reducing duplication

1. Keep the copied versions as the working baseline.
2. Prove `scripts\fixtures\run_univers_live_summary_proof.ps1`.
3. Only extract code into a shared layer if that layer is a documented, versioned dependency.
4. Re-run the Univers fixture after every extraction.
5. Only then remove the duplicate local copy.

## First candidates for extraction

- common JSON write and path helpers
- render/export helper scripts that are byte-for-byte identical
- QA validation helpers that do not depend on module-local state
