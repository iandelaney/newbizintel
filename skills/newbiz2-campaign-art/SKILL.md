---
name: newbiz2-campaign-art
description: Create or refresh Creative Campaign illustration prompts, manifests, placeholder assets, and final raster art for newbiz2. Use when campaign visuals need to be generated, replaced, art-directed, or validated as distinct from one another.
---

# NewBiz2 Campaign Art

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
