from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import add_event, load_state, proof_root, save_state, set_gate, set_status


def module_campaign_art(
    args: argparse.Namespace,
    *,
    script_root: Path,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    run_python_script: Callable[[Path, list[str]], dict[str, Any]],
    apply_manifest: Callable[[Path, Path], dict[str, Any]],
    audit_campaign_art: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "campaign_art", "in_progress")
    set_gate(state, "gate_5b_campaign_art", "in_progress")
    add_event(state, "fanout", "campaign_art.prep", jobs=["campaign-art-prompt-manifest", "campaign-art-brief", "final-raster-import-check"])
    save_state(brand_folder, state)
    script = script_root / "campaign-art" / "generate_campaign_illustrations.py"
    generation = run_python_script(script, ["--data", str(data_path), "--manifest-only"])
    manifest_path = Path(generation.get("report_data_patch_manifest", ""))
    if manifest_path.exists():
        reduction = apply_manifest(data_path, manifest_path)
    else:
        reduction = {"ok": False, "applied_count": 0}
    generated_batch: dict[str, Any] = {"generated": 0, "skipped": True}
    import_result: dict[str, Any] = {"imported": 0, "skipped": True}
    import_reduction: dict[str, Any] = {"ok": False, "applied_count": 0, "skipped": True}
    source_dir = str(getattr(args, "campaign_art_source_dir", "") or "").strip()
    latest_generated_batch = bool(getattr(args, "campaign_art_latest_generated_batch", False))
    auto_generate_originals = bool(getattr(args, "campaign_art_generate_originals", True))
    generate_dry_run = bool(getattr(args, "campaign_art_generate_dry_run", False))

    if not source_dir and not latest_generated_batch and auto_generate_originals:
        generator_script = script_root / "campaign-art" / "generate_final_campaign_art.py"
        generated_batch_dir = proof_root(None) / brand_folder.name / "campaign-art-autogen"
        generator_args = [
            "--data",
            str(data_path),
            "--out-dir",
            str(generated_batch_dir),
        ]
        if args.campaign_art_overwrite_final:
            generator_args.append("--force")
        if generate_dry_run:
            generator_args.append("--dry-run")
        try:
            generated_batch = run_python_script(generator_script, generator_args)
            if not generate_dry_run:
                source_dir = str(generated_batch.get("batch_dir") or "").strip()
            add_event(
                state,
                "fanout",
                "campaign_art.original_generation",
                jobs=[f"imagegen:{name}" for name in generated_batch.get("expected_files", [])],
            )
            save_state(brand_folder, state)
        except SystemExit:
            set_status(state, "campaign_art", "blocked")
            set_gate(state, "gate_5b_campaign_art", "blocked")
            add_event(
                state,
                "note",
                "campaign_art.original_generation_failed",
                notes=["newbizintel could not generate original campaign artwork in-run."],
            )
            save_state(brand_folder, state)
            raise

    if source_dir or latest_generated_batch:
        import_script = script_root / "campaign-art" / "import_final_campaign_art.py"
        import_args = ["--data", str(data_path), "--manifest-only"]
        if source_dir:
            import_args.extend(["--source-dir", str(Path(source_dir))])
        if latest_generated_batch:
            import_args.append("--latest-generated-batch")
        if args.campaign_art_overwrite_final:
            import_args.append("--overwrite-final")
        import_result = run_python_script(import_script, import_args)
        import_manifest_path = Path(import_result.get("report_data_patch_manifest", ""))
        if import_manifest_path.exists():
            import_reduction = apply_manifest(data_path, import_manifest_path)
            add_event(
                state,
                "reducer",
                "campaign_art.final_raster_import_reducer",
                outputs=[str(import_manifest_path)],
                notes=[f"imported:{import_result.get('imported', 0)}", f"source:{import_result.get('source_dir', '')}"],
            )
        else:
            import_reduction = {"ok": False, "applied_count": 0, "manifest": str(import_manifest_path)}
    audit = audit_campaign_art(data_path)
    if not audit["ok"]:
        set_status(state, "campaign_art", "blocked")
        set_gate(state, "gate_5b_campaign_art", "blocked")
    else:
        set_status(state, "campaign_art", "passed")
        set_gate(state, "gate_5b_campaign_art", "passed")
    add_event(state, "reducer", "campaign_art.asset_manifest_reducer", outputs=[str(manifest_path) if manifest_path else "campaign-art-report-data-patch"])
    save_state(brand_folder, state)
    if not audit["ok"]:
        raise SystemExit("Campaign art gate blocked: " + "; ".join(audit["errors"]))
    return {
        "module": "campaign-art",
        "data": str(data_path),
        "brand_folder": str(brand_folder),
        "generation": generation,
        "campaign_reduction": reduction,
        "original_generation": generated_batch,
        "final_raster_import": import_result,
        "final_raster_reduction": import_reduction,
        "contract_audit": audit,
    }
