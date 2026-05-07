---
name: newbizintel-campaign-art
description: Create or refresh Creative Campaign illustration prompts, manifests, placeholder assets, and final raster art for newbizintel. Use when campaign visuals need to be generated, replaced, art-directed, or validated as distinct from one another.
---

# NewBizIntel Campaign Art

Default to true raster artwork.

For premium runs, the default backend is image-generated raster art, not the local scaffold renderer.

The bundled Python generator is a scaffold and fallback path, not the premium end state.
Only use scaffold output when the report explicitly opts into `artwork_delivery_mode: "scaffold-allowed"` or an equivalent local-scaffold backend.

Own:

- illustration prompts
- prompt manifest
- medium selection
- final raster campaign assets
- placeholder assets only when needed for layout-safe scaffolding

Rules:

- treat surprise as a feature
- push the 4 campaign visuals apart when the brief calls for contrast
- do not accept one repeated house style with mild variation as final premium art
- treat `illustration_generation_backend: "imagegen"` as the premium default
- do not overwrite existing campaign artwork by default when a report may already contain approved final raster assets
- mark scaffold output honestly so QA can distinguish placeholder art from final artwork

Premium workflow:

1. Run the campaign-art module once to generate:
   - `illustration_prompt_manifest`
   - `illustration_prompt_brief`
   - expected output filenames
2. Generate one real raster image per prompt.
3. Import those images back into the report with:
   - `run_module.ps1 -ImportSourceDir <folder>`
   - or `run_module.ps1 -ImportLatestGeneratedBatch`
4. Only treat the campaign-art gate as passed when ideas are marked `final-raster-artwork`.
