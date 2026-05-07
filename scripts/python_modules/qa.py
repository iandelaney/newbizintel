from __future__ import annotations

import argparse
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import add_event, load_state, read_json, save_state, set_gate, set_status, write_json


def audit_hybrid(state: dict[str, Any]) -> dict[str, Any]:
    events = state.get("hybrid_execution", {}).get("events", [])
    seen = {(event.get("type"), event.get("key")) for event in events}
    required = [
        ("fanout", "research.evidence_collection"),
        ("reducer", "research.summary_reducer"),
        ("reducer", "structure.report_data_reducer"),
        ("fanout", "assets.logo_acquisition"),
        ("fanout", "assets.source_badges"),
        ("reducer", "assets.asset_manifest_reducer"),
        ("fanout", "campaign_art.prep"),
        ("reducer", "campaign_art.asset_manifest_reducer"),
    ]
    missing = [f"{kind}:{key}" for kind, key in required if (kind, key) not in seen]
    return {"ok": not missing, "missing": missing}


def module_qa(
    args: argparse.Namespace,
    *,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    reconcile_structure_gate_from_data: Callable[[dict[str, Any], Path], bool],
    reconcile_campaign_art_gate_from_audit: Callable[[dict[str, Any], Path], bool],
    reconcile_render_gate_from_outputs: Callable[[dict[str, Any], Path, Path], bool],
    validate_report_data: Callable[[Path], dict[str, Any]],
    audit_campaign_art: Callable[[Path], dict[str, Any]],
    audit_presentation_html: Callable[[Path, Path], dict[str, Any]],
    audit_deploy_stage: Callable[[Path], dict[str, Any]],
    audit_task_list: Callable[[Path], dict[str, Any]],
    inject_task_list_into_html: Callable[[Path, Path], None],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    changed = False
    if reconcile_structure_gate_from_data(state, data_path):
        changed = True
    if reconcile_campaign_art_gate_from_audit(state, data_path):
        changed = True
    if reconcile_render_gate_from_outputs(state, data_path, brand_folder):
        changed = True
    if changed:
        save_state(brand_folder, state)
    set_status(state, "qa", "in_progress")
    if state.get("status", {}).get("deploy") != "passed":
        set_status(state, "deploy", "pending")
    set_gate(state, "gate_9_quality_review", "in_progress")
    set_gate(state, "gate_6a_editorial_quality", "in_progress")
    if state.get("gates", {}).get("gate_10_delivery_handoff") != "passed" and state.get("gates", {}).get("gate_7_delivery") != "passed":
        set_gate(state, "gate_10_delivery_handoff", "pending")
        set_gate(state, "gate_7_delivery", "pending")
    add_event(state, "fanout", "qa.initial_audits", jobs=["report-data", "task-list", "hybrid", "logos", "campaign-art", "outputs"])
    save_state(brand_folder, state)
    latest_stage_audit: dict[str, Any] = {"ok": True, "warnings": ["Deploy stage has not been prepared yet."], "errors": []}
    latest_handoff_path = brand_folder / "vercel-random-handoff-latest.json"
    if latest_handoff_path.exists():
        try:
            latest_handoff = read_json(latest_handoff_path)
            deploy_path = Path(str(latest_handoff.get("deploy_path") or ""))
            if deploy_path.exists() and deploy_path.is_dir():
                latest_stage_audit = audit_deploy_stage(deploy_path)
            else:
                latest_stage_audit = {"ok": False, "errors": [f"Latest Vercel stage path is missing: {deploy_path}"], "warnings": []}
        except Exception as exc:
            latest_stage_audit = {"ok": False, "errors": [f"Could not audit latest Vercel stage: {exc}"], "warnings": []}
    checks = {
        "report_data": validate_report_data(data_path),
        "hybrid": audit_hybrid(state),
        "campaign_art": audit_campaign_art(data_path),
        "required_logos": read_json(brand_folder / "required-logo-manifest.json") if (brand_folder / "required-logo-manifest.json").exists() else {"ok": False, "errors": ["required-logo-manifest.json missing"]},
        "source_badges": read_json(brand_folder / "source-badge-manifest.json") if (brand_folder / "source-badge-manifest.json").exists() else {"ok": False, "errors": ["source-badge-manifest.json missing"]},
        "presentation_html": audit_presentation_html(brand_folder, data_path),
        "deploy_stage": latest_stage_audit,
        "outputs": {
            "ok": (brand_folder / "newbizintel-report.html").exists() and (brand_folder / "archive" / "newbizintel-report-portable.html").exists() and (brand_folder / "newbizintel-report.pptx").exists(),
            "html": str(brand_folder / "newbizintel-report.html"),
            "portable_html": str(brand_folder / "archive" / "newbizintel-report-portable.html"),
            "pptx": str(brand_folder / "newbizintel-report.pptx"),
        },
    }
    errors = []
    for name, result in checks.items():
        if not result.get("ok"):
            errors.append(f"{name}: {result.get('errors') or result.get('missing') or 'not ok'}")
    if errors:
        set_status(state, "qa", "failed")
        set_gate(state, "gate_9_quality_review", "failed")
        set_gate(state, "gate_6a_editorial_quality", "failed")
        save_state(brand_folder, state)
        checks["task_list"] = audit_task_list(data_path)
        write_json(brand_folder / "qa-results.json", checks)
        raise SystemExit("QA failed: " + "; ".join(errors))
    add_event(state, "reducer", "qa.bundle_reducer", outputs=[str(brand_folder / "qa-results.json")])
    set_status(state, "qa", "passed")
    set_gate(state, "gate_9_quality_review", "passed")
    set_gate(state, "gate_6a_editorial_quality", "passed")
    save_state(brand_folder, state)
    checks["task_list"] = audit_task_list(data_path)
    html_path = brand_folder / "newbizintel-report.html"
    index_path = brand_folder / "index.html"
    inject_task_list_into_html(html_path, brand_folder)
    if html_path.exists():
        shutil.copy2(html_path, index_path)
    elif index_path.exists():
        inject_task_list_into_html(index_path, brand_folder)
    write_json(brand_folder / "qa-results.json", checks)
    return {"module": "qa", "data": str(data_path), "brand_folder": str(brand_folder), "checks": checks}
