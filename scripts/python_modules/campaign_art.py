from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import add_event, extract_token_usage, load_state, proof_root, record_token_usage, save_state, set_gate, set_status


def _campaign_art_handoff_details(data_path: Path, default_batch_dir: Path, generation: dict[str, Any]) -> dict[str, Any]:
    brand_folder = data_path.parent
    slide_assets = brand_folder / "slide-assets"
    slug = brand_folder.name
    prompt_manifest = Path(str(generation.get("prompt_manifest") or generation.get("prompts_manifest") or generation.get("prompt_json") or (slide_assets / f"{slug}-campaign-illustration-prompts.json"))).resolve()
    batch_request = Path(str(generation.get("batch_request") or generation.get("batch_request_json") or (slide_assets / f"{slug}-campaign-batch-request.json"))).resolve()
    expected_files = generation.get("expected_files") or []
    return {
        "prompt_manifest": str(prompt_manifest),
        "batch_request": str(batch_request),
        "default_batch_dir": str(default_batch_dir),
        "expected_files": expected_files,
        "import_command": (
            f"python scripts/newbizintel.py campaign-art --data-path \"{data_path}\" "
            f"--campaign-art-source-dir \"{default_batch_dir}\" --campaign-art-overwrite-final"
        ),
    }


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

    source_dir = str(getattr(args, "campaign_art_source_dir", "") or "").strip()
    latest_generated_batch = bool(getattr(args, "campaign_art_latest_generated_batch", False))
    auto_generate_originals = bool(getattr(args, "campaign_art_generate_originals", True))
    generate_dry_run = bool(getattr(args, "campaign_art_generate_dry_run", False))

    generation: dict[str, Any] = {"generated": 0, "skipped": True}
    reduction: dict[str, Any] = {"ok": False, "applied_count": 0, "skipped": True}
    generated_batch: dict[str, Any] = {"generated": 0, "skipped": True}
    import_result: dict[str, Any] = {"imported": 0, "skipped": True}
    import_reduction: dict[str, Any] = {"ok": False, "applied_count": 0, "skipped": True}
    manifest_path: Path | None = None

    if not source_dir and not latest_generated_batch:
        script = script_root / "campaign-art" / "generate_campaign_illustrations.py"
        generation = run_python_script(script, ["--data", str(data_path), "--manifest-only"])
        manifest_value = str(generation.get("report_data_patch_manifest", "") or "").strip()
        manifest_path = Path(manifest_value).resolve() if manifest_value else None
        if manifest_path and manifest_path.exists():
            reduction = apply_manifest(data_path, manifest_path)
        else:
            reduction = {"ok": False, "applied_count": 0, "skipped": True}

    if not source_dir and not latest_generated_batch and auto_generate_originals:
        generated_batch_dir = proof_root(None) / brand_folder.name / "campaign-art-autogen"
        handoff = _campaign_art_handoff_details(data_path, generated_batch_dir, generation)
        handoff_path = brand_folder / "campaign-art-imagegen-handoff.json"
        handoff_path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        generated_batch = {
            "skipped": True,
            "blocked": True,
            "handoff_required": True,
            "batch_dir": str(generated_batch_dir),
            "handoff": str(handoff_path),
            "expected_files": handoff.get("expected_files", []),
        }
        set_status(state, "campaign_art", "blocked")
        set_gate(state, "gate_5b_campaign_art", "blocked")
        record_token_usage(
            state,
            "campaign_art.original_generation",
            extract_token_usage(generation),
            provider="built-in-imagegen",
            model="imagegen",
            status="unavailable",
            note="Use built-in imagegen with the prepared prompt manifest, then re-import the finished raster set.",
        )
        add_event(
            state,
            "note",
            "campaign_art.imagegen_handoff_required",
            outputs=[str(handoff_path)],
            notes=[
                f"prompt_manifest:{handoff['prompt_manifest']}",
                f"batch_request:{handoff['batch_request']}",
                f"batch_dir:{handoff['default_batch_dir']}",
            ],
        )
        save_state(brand_folder, state)
        raise SystemExit(
            "Campaign art original generation now uses built-in imagegen. "
            f"Generate the raster set from {handoff['prompt_manifest']} and {handoff['batch_request']}, save it under {handoff['default_batch_dir']}, "
            "then rerun campaign-art with --campaign-art-source-dir or --campaign-art-latest-generated-batch."
        )

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
        import_manifest_value = str(import_result.get("report_data_patch_manifest", "") or "").strip()
        import_manifest_path = Path(import_manifest_value).resolve() if import_manifest_value else None
        if import_manifest_path and import_manifest_path.exists():
            import_reduction = apply_manifest(data_path, import_manifest_path)
            add_event(
                state,
                "reducer",
                "campaign_art.final_raster_import_reducer",
                outputs=[str(import_manifest_path)],
                notes=[f"imported:{import_result.get('imported', 0)}", f"source:{import_result.get('source_dir', '')}"],
            )
            record_token_usage(
                state,
                "campaign_art.final_raster_import",
                extract_token_usage(import_result),
                provider="built-in-imagegen",
                model="imagegen",
            )
        else:
            import_reduction = {"ok": False, "applied_count": 0, "manifest": str(import_manifest_path) if import_manifest_path else "", "skipped": True}

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
