from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import add_event, load_state, read_json, save_state, set_gate, set_status, write_json


def module_structure(
    args: argparse.Namespace,
    *,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    merge_research_into_data: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    build_structured_report_data: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    validate_report_data: Callable[[Path], dict[str, Any]],
    sha256: Callable[[Path], str],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "structure", "in_progress")
    set_gate(state, "gate_4_report_data", "in_progress")
    save_state(brand_folder, state)
    data = read_json(data_path)
    summary_path = Path(args.research_summary_path).expanduser().resolve() if args.research_summary_path else brand_folder / "research-summary.json"
    if summary_path.exists():
        summary = read_json(summary_path)
        data = merge_research_into_data(data, summary)
        data = build_structured_report_data(data, summary, brand_folder)
        write_json(data_path, data)
    validation = validate_report_data(data_path, phase="structure")
    if not validation["ok"]:
        set_status(state, "structure", "failed")
        set_gate(state, "gate_4_report_data", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Report data validation failed: " + "; ".join(validation["errors"]))
    add_event(state, "reducer", "structure.report_data_reducer", outputs=[str(data_path)])
    state.setdefault("freshness", {})["report_data_hash"] = sha256(data_path)
    set_status(state, "structure", "passed")
    set_gate(state, "gate_4_report_data", "passed")
    save_state(brand_folder, state)
    return {"module": "structure", "data": str(data_path), "brand_folder": str(brand_folder), "validation": validation}
