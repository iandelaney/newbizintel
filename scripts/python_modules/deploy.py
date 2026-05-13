from __future__ import annotations

import argparse
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import load_state, record_token_usage, save_state, set_gate, set_status


def module_deploy(
    args: argparse.Namespace,
    *,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    assert_deployable_report_html: Callable[[Path], None],
    inject_task_list_into_html: Callable[[Path, Path], None],
    vercel_deploy_prompt: Callable[[Path, Path], dict[str, Any]],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "deploy", "in_progress")
    set_gate(state, "gate_10_delivery_handoff", "in_progress")
    set_gate(state, "gate_7_delivery", "in_progress")
    save_state(brand_folder, state)
    html_path = brand_folder / "newbizintel-report.html"
    if not html_path.exists():
        set_status(state, "deploy", "failed")
        set_gate(state, "gate_10_delivery_handoff", "failed")
        set_gate(state, "gate_7_delivery", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Cannot refresh delivery handoff because newbizintel-report.html is missing.")
    assert_deployable_report_html(html_path)
    shutil.copy2(html_path, brand_folder / "index.html")
    set_status(state, "deploy", "passed")
    set_gate(state, "gate_10_delivery_handoff", "passed")
    set_gate(state, "gate_7_delivery", "passed")
    record_token_usage(
        state,
        "deploy.handoff_refresh",
        None,
        provider="local-python",
        model="deterministic",
        status="deterministic",
        note="Delivery handoff refresh and stage preparation are deterministic local operations.",
    )
    save_state(brand_folder, state)
    index_path = brand_folder / "index.html"
    inject_task_list_into_html(index_path, brand_folder)
    assert_deployable_report_html(index_path)
    return {
        "module": "deploy",
        "data": str(data_path),
        "brand_folder": str(brand_folder),
        "index": str(brand_folder / "index.html"),
        "task_list": str(brand_folder / "workflow-task-list.md"),
        "vercel_deploy_prompt": vercel_deploy_prompt(data_path, brand_folder),
    }


def module_vercel_stage(
    args: argparse.Namespace,
    *,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    prepare_random_vercel_stage: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    return {
        "module": "vercel-stage",
        "data": str(data_path),
        "vercel_handoff": prepare_random_vercel_stage(data_path),
    }
