from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import extract_token_usage, load_state, record_token_usage, save_state, set_gate, set_status


def module_render(
    args: argparse.Namespace,
    *,
    script_root: Path,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    validate_report_data: Callable[[Path], dict[str, Any]],
    render_rich_html_with_python: Callable[[Path, Path], Path],
    render_rich_html_with_powershell: Callable[[Path, Path], Path],
    render_html: Callable[[Path, Path | None], Path],
    inject_task_list_into_html: Callable[[Path, Path], None],
    assert_deployable_report_html: Callable[[Path], None],
    make_self_contained: Callable[[Path, Path, Path], None],
    pptx_safe_data_copy: Callable[[Path], Path],
    run_python_script: Callable[[Path, list[str]], dict[str, Any]],
    build_minimal_pptx: Callable[[Path, Path], None],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "render", "in_progress")
    set_gate(state, "gate_8_render_outputs", "in_progress")
    set_gate(state, "gate_6_render_outputs", "in_progress")
    save_state(brand_folder, state)
    validation = validate_report_data(data_path)
    if not validation["ok"]:
        set_status(state, "render", "failed")
        set_gate(state, "gate_8_render_outputs", "failed")
        set_gate(state, "gate_6_render_outputs", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Render blocked by report-data validation: " + "; ".join(validation["errors"]))
    html_path = brand_folder / "newbizintel-report.html"
    try:
        html_path = render_rich_html_with_python(data_path, html_path)
    except Exception as exc:
        if os.environ.get("NEWBIZINTEL_ALLOW_POWERSHELL_RENDER_FALLBACK", "") == "1":
            html_path = render_rich_html_with_powershell(data_path, html_path)
        elif os.environ.get("NEWBIZINTEL_ALLOW_SKELETAL_RENDER", "") == "1":
            html_path = render_html(data_path, html_path)
        else:
            set_status(state, "render", "failed")
            set_gate(state, "gate_8_render_outputs", "failed")
            set_gate(state, "gate_6_render_outputs", "failed")
            save_state(brand_folder, state)
            raise SystemExit(
                "Render blocked because the Python rich presentation renderer did not run. "
                "Refusing to use the legacy PowerShell renderer unless NEWBIZINTEL_ALLOW_POWERSHELL_RENDER_FALLBACK=1. "
                f"Root cause: {exc}"
            )
    inject_task_list_into_html(html_path, brand_folder)
    try:
        assert_deployable_report_html(html_path)
    except SystemExit:
        set_status(state, "render", "failed")
        set_gate(state, "gate_6_render_outputs", "failed")
        set_gate(state, "gate_8_render_outputs", "failed")
        save_state(brand_folder, state)
        raise
    archive_dir = brand_folder / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    portable_html = archive_dir / "newbizintel-report-portable.html"
    make_self_contained(html_path, data_path, portable_html)
    try:
        assert_deployable_report_html(portable_html)
    except SystemExit:
        set_status(state, "render", "failed")
        set_gate(state, "gate_6_render_outputs", "failed")
        set_gate(state, "gate_8_render_outputs", "failed")
        save_state(brand_folder, state)
        raise
    pptx_path = brand_folder / "newbizintel-report.pptx"
    pptx_warning = ""
    pptx_result: dict[str, Any] = {}
    try:
        pptx_data_path = pptx_safe_data_copy(data_path)
        pptx_result = run_python_script(script_root / "render" / "report_data_to_pptx.py", ["--data", str(pptx_data_path), "--pptx", str(pptx_path)])
    except SystemExit as exc:
        pptx_warning = str(exc)
        build_minimal_pptx(data_path, pptx_path)
    if not pptx_path.exists():
        set_status(state, "render", "failed")
        set_gate(state, "gate_8_render_outputs", "failed")
        set_gate(state, "gate_6_render_outputs", "failed")
        save_state(brand_folder, state)
        raise SystemExit("PPTX output was not created. " + pptx_warning)
    shutil.copy2(html_path, brand_folder / "index.html")
    shutil.copy2(pptx_path, archive_dir / pptx_path.name)
    set_status(state, "render", "passed")
    set_gate(state, "gate_8_render_outputs", "passed")
    set_gate(state, "gate_6_render_outputs", "passed")
    record_token_usage(
        state,
        "render.html_bundle",
        None,
        provider="local-python",
        model="deterministic",
        status="deterministic",
        note="HTML render, portable HTML packaging, and deployable HTML checks are deterministic local operations.",
    )
    pptx_usage = extract_token_usage(pptx_result)
    record_token_usage(
        state,
        "render.pptx_builder",
        pptx_usage,
        provider="local-python",
        model="deterministic" if not pptx_usage else None,
        status="deterministic" if not pptx_usage else None,
        note="PPTX export currently runs through local render code and does not usually expose model token usage.",
    )
    save_state(brand_folder, state)
    return {
        "module": "render",
        "data": str(data_path),
        "brand_folder": str(brand_folder),
        "bundle": {
            "html": str(html_path),
            "pptx": str(pptx_path),
            "archive": {
                "directory": str(archive_dir),
                "html": str(portable_html),
                "pptx": str(archive_dir / pptx_path.name),
            },
        },
    }
