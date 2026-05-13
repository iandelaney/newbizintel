from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import (
    add_event,
    extract_token_usage,
    load_state,
    merge_token_usage,
    read_json,
    record_token_usage,
    save_state,
    set_gate,
    set_status,
    write_json,
)


def _fail_research(state: dict[str, Any], brand_folder: Path) -> None:
    set_status(state, "research", "failed")
    set_gate(state, "gate_2_competitors", "failed")
    set_gate(state, "gate_3_research", "failed")
    set_gate(state, "gate_3a_semrush", "failed")
    set_gate(state, "gate_4_search_seo_evidence", "failed")
    save_state(brand_folder, state)


def _usage_from_json_path(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    try:
        return extract_token_usage(read_json(path))
    except Exception:
        return None


def module_research(
    args: argparse.Namespace,
    *,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    reset_tasks_from: Callable[[dict[str, Any], int], None],
    collect_live_search_workpacks: Callable[[Path, Path], list[Path]],
    reduce_search_workpacks: Callable[[Path, Path, list[Path]], dict[str, Any]],
    build_summary_from_data: Callable[[Path], dict[str, Any]],
    apply_tavily_reputation_research: Callable[[Path, Path, dict[str, Any]], tuple[dict[str, Any], Path | None]],
    apply_semrush_direct_api: Callable[[Path, Path, dict[str, Any]], tuple[dict[str, Any], Path | None]],
    validate_research_summary: Callable[[dict[str, Any], bool], dict[str, Any]],
    is_repo_example_path: Callable[[Path | None], bool],
    sha256: Callable[[Path], str],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    if (
        args.research_mode == "bootstrap"
        and not args.research_summary_path
        and not (args.search_workpacks or [])
        and not is_repo_example_path(data_path)
    ):
        args.research_mode = "live-summary"
    state = load_state(brand_folder)
    set_status(state, "research", "in_progress")
    set_gate(state, "gate_2_competitors", "in_progress")
    set_gate(state, "gate_3_research", "in_progress")
    set_gate(state, "gate_3a_semrush", "in_progress")
    set_gate(state, "gate_4_search_seo_evidence", "in_progress")
    reset_tasks_from(state, 5)
    for module in ("structure", "assets", "campaign_art", "render", "qa", "deploy"):
        set_status(state, module, "pending")
    add_event(
        state,
        "fanout",
        "research.evidence_collection",
        jobs=[
            f"research_mode:{args.research_mode}",
            "python_runner:newbizintel.py",
            f"search_workpacks:{len(args.search_workpacks or [])}",
            f"composio_semrush_available:{bool(args.composio_semrush_available)}",
            f"jina_fallback_available:{bool(args.jina_fallback_available)}",
        ],
        notes=["Python runner uses isolated research-summary.json before structure updates report-data.json."],
    )
    save_state(brand_folder, state)

    try:
        if args.research_mode == "live-summary":
            if args.research_summary_path:
                summary = read_json(Path(args.research_summary_path).expanduser().resolve())
            else:
                workpacks = collect_live_search_workpacks(data_path, brand_folder)
                add_event(state, "fanout", "research.live_search_workpacks", jobs=[str(path) for path in workpacks])
                workpack_usage: dict[str, Any] | None = None
                for path in workpacks:
                    workpack_usage = merge_token_usage(workpack_usage, _usage_from_json_path(path))
                record_token_usage(
                    state,
                    "research.live_search_workpacks",
                    workpack_usage,
                    provider="tavily",
                )
                summary = reduce_search_workpacks(data_path, brand_folder, workpacks)
                add_event(state, "reducer", "research.live_search_summary_draft", outputs=[str(brand_folder / "research-summary.draft.json")])
                save_state(brand_folder, state)
        elif args.research_mode == "workpacks":
            workpacks = [Path(path).expanduser().resolve() for path in (args.search_workpacks or [])]
            workpack_usage: dict[str, Any] | None = None
            for path in workpacks:
                workpack_usage = merge_token_usage(workpack_usage, _usage_from_json_path(path))
            record_token_usage(
                state,
                "research.input_workpacks",
                workpack_usage,
                provider="tavily",
            )
            summary = reduce_search_workpacks(data_path, brand_folder, workpacks)
        elif args.research_summary_path:
            summary = read_json(Path(args.research_summary_path).expanduser().resolve())
        else:
            summary = build_summary_from_data(data_path)
        if args.research_mode == "live-summary" and getattr(args, "tavily_reputation_research", True):
            summary["required_tavily_reputation_research"] = True
            summary, reputation_research_path = apply_tavily_reputation_research(data_path, brand_folder, summary)
            if reputation_research_path:
                add_event(state, "fanout", "research.tavily_reputation_research", jobs=[str(reputation_research_path)])
                add_event(state, "reducer", "research.tavily_reputation_reducer", outputs=[str(reputation_research_path)])
                record_token_usage(
                    state,
                    "research.tavily_reputation_research",
                    _usage_from_json_path(reputation_research_path),
                    provider="tavily",
                )
                save_state(brand_folder, state)
        if args.research_mode == "live-summary":
            summary, semrush_path = apply_semrush_direct_api(data_path, brand_folder, summary)
            if semrush_path:
                add_event(state, "fanout", "research.semrush_direct_api", jobs=[str(semrush_path)])
                add_event(state, "reducer", "research.search_seo_evidence_reducer", outputs=[str(semrush_path)])
                record_token_usage(
                    state,
                    "research.semrush_direct_api",
                    _usage_from_json_path(semrush_path),
                    provider="semrush",
                )
                save_state(brand_folder, state)
    except SystemExit:
        _fail_research(state, brand_folder)
        raise
    except Exception as exc:
        _fail_research(state, brand_folder)
        raise SystemExit(f"Research acquisition/reduction failed: {exc}") from exc

    validation = validate_research_summary(summary, is_repo_example_path(data_path))
    if not validation["ok"]:
        _fail_research(state, brand_folder)
        raise SystemExit("Research summary validation failed: " + "; ".join(validation["errors"]))

    summary_path = brand_folder / "research-summary.json"
    write_json(summary_path, summary)
    add_event(state, "reducer", "research.summary_reducer", outputs=[str(summary_path)])
    state.setdefault("freshness", {})["research_summary_hash"] = sha256(summary_path)
    state.setdefault("locked_sets", {})["competitors"] = summary.get("locked_sets", {}).get("competitors", [])
    state.setdefault("locked_sets", {})["influential_news"] = summary.get("locked_sets", {}).get("influential_news", [])
    status = summary.get("status", {})
    research_statuses = [status.get(key, "pending") for key in ("competitor_discovery", "recent_news", "reputation_public_web", "source_gathering")]
    research_status = "failed" if "failed" in research_statuses else "blocked" if "blocked" in research_statuses else "pending" if "pending" in research_statuses else "passed"
    set_status(state, "research", research_status)
    set_gate(state, "gate_2_competitors", status.get("competitor_discovery", "pending"))
    set_gate(state, "gate_3_research", research_status)
    set_gate(state, "gate_3a_semrush", status.get("semrush", "quota-limited"))
    set_gate(state, "gate_4_search_seo_evidence", status.get("search_seo", "pending"))
    save_state(brand_folder, state)
    return {
        "module": "research",
        "data": str(data_path),
        "brand_folder": str(brand_folder),
        "research_summary": str(summary_path),
        "validation": validation,
    }
