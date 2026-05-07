from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = SCRIPT_ROOT.parent
RUN_STATE_CONTRACT = SKILL_ROOT / "references" / "run-state.contract.json"

DEFAULT_MODEL_ROUTING = {
    "default": "gpt-5.5",
    "orchestration": "gpt-5.5",
    "synthesis": "gpt-5.5",
    "final_report_writing": "gpt-5.5",
    "qa_sensitive_judgement": "gpt-5.5",
    "low_risk_tasks": "gpt-5.4-mini",
    "deterministic_helpers": "gpt-5.4-mini",
}

TASK_DEFINITIONS = [
    {
        "id": 1,
        "key": "intake",
        "title": "Intake and workspace",
        "gates": ["gate_1_intake"],
        "legacy_gates": [],
        "trust_test": "Brand folder, report-data.json, and run-state.json exist.",
    },
    {
        "id": 2,
        "key": "competitor_set",
        "title": "Competitor set",
        "gates": ["gate_2_competitor_set"],
        "legacy_gates": ["gate_2_competitors"],
        "trust_test": "Competitor set is present in the research summary or report data.",
    },
    {
        "id": 3,
        "key": "current_research",
        "title": "Current research and source map",
        "gates": ["gate_3_current_research"],
        "legacy_gates": ["gate_3_research"],
        "trust_test": "Research summary exists with news, reputation/source status, and locked sets.",
    },
    {
        "id": 4,
        "key": "search_seo_evidence",
        "title": "Search and SEO evidence",
        "gates": ["gate_4_search_seo_evidence"],
        "legacy_gates": ["gate_4_semrush_seo_evidence"],
        "trust_test": "At least two SEO evidence points are available, with SEMrush status explicitly recorded as passed, partial, quota-limited, or blocked.",
    },
    {
        "id": 5,
        "key": "report_structure",
        "title": "Report structure and data contract",
        "gates": ["gate_5_report_structure"],
        "legacy_gates": ["gate_4_report_data"],
        "trust_test": "report-data.json passes schema validation, freshness is updated, and the Company Snapshot includes finance, leadership/profile links, founders, ownership/funding, and source-map evidence.",
    },
    {
        "id": 6,
        "key": "logos_and_assets",
        "title": "Brand, competitor, and source logos",
        "gates": ["gate_6_logos_and_assets"],
        "legacy_gates": ["gate_5_assets", "gate_5a_source_badges", "gate_5b_required_logos"],
        "trust_test": "Brand, competitor, and news/source logos resolve without missing or generic HTML fallbacks; the primary brand logo must come from a first-party or verified colour asset, not a monochrome Simple Icons proxy; competitor badges prefer square marks/icons, with wide or unavailable candidates converted to checked square initial-letter marks.",
    },
    {
        "id": 7,
        "key": "campaign_ideas_and_art",
        "title": "Creative campaign ideas and artwork",
        "gates": ["gate_7_campaign_ideas_and_art"],
        "legacy_gates": ["gate_5b_campaign_art"],
        "trust_test": "Campaign ideas have a developed driving idea, descriptive implementation story, and at least one vivid activation expression explaining what the brand creates, what it looks like, concrete example moments or user paths, why that shape is right, and the intended result, plus final raster artwork.",
    },
    {
        "id": 8,
        "key": "render_outputs",
        "title": "HTML, portable HTML, and PPTX render",
        "gates": ["gate_8_render_outputs"],
        "legacy_gates": ["gate_6_render_outputs"],
        "trust_test": "Rendered HTML, portable HTML, and PPTX exist and are current.",
    },
    {
        "id": 9,
        "key": "quality_review",
        "title": "Quality, trust, and presentation QA",
        "gates": ["gate_9_quality_review"],
        "legacy_gates": ["gate_6a_editorial_quality"],
        "trust_test": "Editorial, presentation, logo, campaign-art, and PPTX audits pass.",
    },
    {
        "id": 10,
        "key": "delivery_handoff",
        "title": "Delivery handoff",
        "gates": ["gate_10_delivery_handoff"],
        "legacy_gates": ["gate_7_delivery"],
        "trust_test": "Deploy handoff folder is refreshed from the latest report outputs and the user is asked whether they want a random-url Vercel deployment.",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    if not slug:
        raise SystemExit(f"Cannot derive a usable slug from {value!r}.")
    return slug


def normalize_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if not parsed.netloc:
        raise SystemExit(f"Website {value!r} is not a valid URL or domain.")
    return urllib.parse.urlunparse(parsed)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def output_root(explicit_root: str | None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()
    env_root = os.environ.get("NEWBIZINTEL_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return (Path.cwd() / "output").resolve()


def brand_folder_from_data(data_path: Path) -> Path:
    return data_path.resolve().parent


def data_path_from_args(args: argparse.Namespace) -> Path:
    if getattr(args, "data_path", None):
        return Path(args.data_path).expanduser().resolve()
    if not getattr(args, "brand_name", None):
        raise SystemExit("Provide --data-path or --brand-name.")
    root = output_root(getattr(args, "brand_folder", None))
    return root / slugify(args.brand_name) / "report-data.json"


def default_state(brand_folder: Path) -> dict[str, Any]:
    if RUN_STATE_CONTRACT.exists():
        state = read_json(RUN_STATE_CONTRACT)
    else:
        state = {}
    state["brand_folder"] = str(brand_folder)
    state.setdefault("execution_model", "hybrid")
    state.setdefault("model_routing", copy.deepcopy(DEFAULT_MODEL_ROUTING))
    state.setdefault("hybrid_execution", {"required_fanouts": [], "required_reducers": [], "events": []})
    state.setdefault("status", {})
    for name in ("intake", "research", "structure", "assets", "campaign_art", "render", "qa", "deploy"):
        state["status"].setdefault(name, "pending")
    state.setdefault("gates", {})
    state.setdefault("freshness", {"research_summary_hash": "", "report_data_hash": "", "stale_reason": ""})
    state.setdefault("locked_sets", {"competitors": [], "influential_news": []})
    state.setdefault("notes", [])
    ensure_task_list(state)
    return state


def load_state(brand_folder: Path) -> dict[str, Any]:
    path = brand_folder / "run-state.json"
    state = read_json(path) if path.exists() else default_state(brand_folder)
    state["brand_folder"] = str(brand_folder)
    ensure_task_list(state)
    return state


def sync_primary_gates(state: dict[str, Any]) -> None:
    gates = state.setdefault("gates", {})
    precedence = {
        "failed": 6,
        "blocked": 5,
        "in_progress": 4,
        "partial": 3,
        "quota-limited": 3,
        "passed": 2,
        "pending": 1,
    }
    for definition in TASK_DEFINITIONS:
        primary = definition["gates"][0]
        aliases = definition.get("legacy_gates") or []
        names = [primary, *aliases]
        statuses = [str(gates.get(name) or "pending") for name in names if name in gates]
        if not statuses:
            gates[primary] = "pending"
            continue
        gates[primary] = max(statuses, key=lambda status: precedence.get(status, 0))


def ensure_task_list(state: dict[str, Any]) -> None:
    sync_primary_gates(state)
    existing = {task.get("key"): task for task in state.get("task_list", []) if isinstance(task, dict)}
    tasks = []
    for definition in TASK_DEFINITIONS:
        old = existing.get(definition["key"], {})
        task = copy.deepcopy(definition)
        task["status"] = "pending"
        task["evidence"] = []
        task["updated_at"] = old.get("updated_at")
        tasks.append(task)
    state["task_list"] = tasks


def sync_task_status_from_gates(state: dict[str, Any]) -> None:
    sync_primary_gates(state)
    gates = state.setdefault("gates", {})
    for task in state.get("task_list", []):
        statuses = [gates.get(gate, "pending") for gate in task.get("gates", [])]
        if not statuses:
            continue
        if "failed" in statuses:
            next_status = "failed"
        elif "blocked" in statuses:
            next_status = "blocked"
        elif "quota-limited" in statuses:
            next_status = "quota-limited"
        elif "partial" in statuses:
            next_status = "partial"
        elif "in_progress" in statuses:
            next_status = "in_progress"
        elif all(status == "passed" for status in statuses):
            next_status = "passed"
        else:
            next_status = "pending"
        evidence = [f"{gate}:{gates.get(gate, 'missing')}" for gate in task.get("gates", [])]
        for gate in task.get("legacy_gates", []):
            if gate in gates:
                evidence.append(f"{gate}:{gates[gate]}")
        if task.get("status") != next_status or task.get("evidence") != evidence:
            task["status"] = next_status
            task["evidence"] = evidence if next_status in {"in_progress", "passed", "partial", "quota-limited", "blocked", "failed"} else []
            task["updated_at"] = utc_now()


def save_state(brand_folder: Path, state: dict[str, Any]) -> None:
    ensure_task_list(state)
    sync_task_status_from_gates(state)
    state["updated_at"] = utc_now()
    write_json(brand_folder / "run-state.json", state)
    tasks = sorted(state["task_list"], key=lambda item: item["id"])
    payload = {
        "ok": True,
        "total": len(tasks),
        "passed": sum(1 for task in tasks if task["status"] == "passed"),
        "updated_at": state["updated_at"],
        "gates": state.get("gates", {}),
        "tasks": tasks,
    }
    write_json(brand_folder / "workflow-task-list.json", payload)
    lines = [
        "# NewBizIntel Workflow Task List",
        "",
        f"Passed: {payload['passed']}/{payload['total']}",
        f"Updated: {payload['updated_at']}",
        "",
        "| # | Step | Status | Primary gate | Trust test |",
        "|---:|---|---|---|---|",
    ]
    for task in tasks:
        gate_text = ", ".join(task["gates"])
        trust = str(task["trust_test"]).replace("|", "\\|")
        lines.append(f"| {task['id']} | {task['title']} | {task['status']} | {gate_text} | {trust} |")
    (brand_folder / "workflow-task-list.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def primary_gate_for(gate: str) -> str | None:
    for definition in TASK_DEFINITIONS:
        primary = definition["gates"][0]
        if gate == primary or gate in definition.get("legacy_gates", []):
            return primary
    return None


def add_event(
    state: dict[str, Any],
    event_type: str,
    key: str,
    jobs: list[str] | None = None,
    outputs: list[str] | None = None,
    notes: list[str] | None = None,
) -> None:
    hybrid = state.setdefault("hybrid_execution", {})
    hybrid.setdefault("events", []).append(
        {
            "timestamp": utc_now(),
            "type": event_type,
            "key": key,
            "jobs": jobs or [],
            "outputs": outputs or [],
            "notes": notes or [],
        }
    )


def set_gate(state: dict[str, Any], gate: str, status: str) -> None:
    gates = state.setdefault("gates", {})
    primary = primary_gate_for(gate)
    if primary:
        for definition in TASK_DEFINITIONS:
            if definition["gates"][0] == primary:
                for related_gate in [*definition.get("gates", []), *definition.get("legacy_gates", [])]:
                    gates[related_gate] = status
                break
    else:
        gates[gate] = status
    sync_primary_gates(state)


def set_status(state: dict[str, Any], module: str, status: str) -> None:
    state.setdefault("status", {})[module] = status


def reset_tasks_from(state: dict[str, Any], start_id: int) -> None:
    gates = state.setdefault("gates", {})
    for definition in TASK_DEFINITIONS:
        if int(definition["id"]) < start_id:
            continue
        for gate in [*definition.get("gates", []), *definition.get("legacy_gates", [])]:
            gates[gate] = "pending"
    sync_primary_gates(state)


def is_repo_example_path(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        path.resolve().relative_to((SKILL_ROOT / "examples").resolve())
        return True
    except ValueError:
        return False
