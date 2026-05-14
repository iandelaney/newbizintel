from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import add_event, load_state, read_json, record_token_usage, save_state, set_gate, set_status, write_json


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
        appendix_source_map = data.get("appendix", {}).get("source_map")
        competitor_table = data.get("competitive_landscape", {}).get("table")
        seo_section = data.get("search_engine_optimization")
        summary_seo = summary.get("seo")
        if isinstance(appendix_source_map, list):
            summary["source_map"] = appendix_source_map
        if isinstance(competitor_table, list) and competitor_table:
            normalized_competitors = []
            for item in competitor_table:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("competitor") or item.get("name") or "").strip()
                if not name:
                    continue
                normalized_competitors.append(
                    {
                        "competitor": name,
                        "website": str(item.get("website") or item.get("url") or "").strip(),
                        "why_it_matters": str(item.get("why_it_matters") or "").strip(),
                        "positioning_pattern": str(item.get("positioning_pattern") or "").strip(),
                        "implication": str(item.get("implication") or "").strip(),
                    }
                )
            if normalized_competitors:
                summary["competitors"] = normalized_competitors
                summary.setdefault("locked_sets", {})["competitors"] = [
                    item["competitor"] for item in normalized_competitors
                ]
                summary.setdefault("status", {})["competitor_discovery"] = "passed"
        if isinstance(seo_section, dict) and seo_section:
            summary["search_engine_optimization"] = seo_section
            if isinstance(summary_seo, dict):
                summary_seo["priority_issues"] = seo_section.get("priority_issues", [])
        write_json(summary_path, summary)
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
    record_token_usage(
        state,
        "structure.report_data_reducer",
        None,
        provider="local-python",
        model="deterministic",
        status="deterministic",
        note="Current structure build merges research into report-data.json with deterministic local logic.",
    )
    save_state(brand_folder, state)
    return {"module": "structure", "data": str(data_path), "brand_folder": str(brand_folder), "validation": validation}
