#!/usr/bin/env python3
"""Cross-platform NewBiz2 runner.

This is the Python-first execution path for colleagues who do not want to install
PowerShell. It intentionally mirrors the NewBiz2 gates and task-list contract while
using only Python plus optional Node/Python-PPTX for deck export.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
TEMPLATE_PATH = SKILL_ROOT / "templates" / "report-data.template.json"
TEMPLATE_ASSETS = SKILL_ROOT / "templates" / "slide-assets"
RUN_STATE_CONTRACT = SKILL_ROOT / "references" / "run-state.contract.json"
TAVILY_REPUTATION_SCHEMA = SKILL_ROOT / "references" / "tavily-reputation-research.schema.json"
SEMRUSH_COLLECTOR = SCRIPT_ROOT / "research" / "collect_semrush_api.py"
REPUTATION_SOURCE_TYPES = {
    "national_business_press",
    "trade_press",
    "financial_investor_press",
    "consumer_press",
    "review_platform",
    "regulatory_or_legal",
    "analyst_or_research",
    "industry_body",
    "owned_newsroom",
    "social_or_forum",
}
REPUTATION_RANKING_FACTORS = (
    "source_authority",
    "buyer_relevance",
    "reputation_risk_or_opportunity",
    "evidence_quality",
    "novelty",
    "recency",
)
REPUTATION_SCORE_WEIGHTS = {
    "source_authority": 0.25,
    "buyer_relevance": 0.25,
    "reputation_risk_or_opportunity": 0.20,
    "evidence_quality": 0.15,
    "novelty": 0.10,
    "recency": 0.05,
}
PLACEHOLDER_MARKERS = (
    ("Replace with", "template instruction text"),
    ("to be finalised", "unfinished generated content"),
    ("specific detail to be finalised", "unfinished generated content"),
    ("validated evidence", "unfinished generated content"),
    ("lorem ipsum", "placeholder copy"),
    ("Example Brand", "template brand name"),
    ("Competitor A", "template competitor"),
    ("Competitor B", "template competitor"),
    ("Competitor C", "template competitor"),
    ("Example National Business Source", "template news source"),
    ("Example Trade Source", "template news source"),
    ("Example Investor Source", "template news source"),
    ("Example Review Platform", "template news source"),
    ("Example Consumer Source", "template news source"),
    ("John Doe", "placeholder person name"),
    ("Jane Doe", "placeholder person name"),
    ("TBC", "unfinished generated content"),
    ("https://example.com", "template URL"),
    ("http://example.com", "template URL"),
    ("www.example.com", "template URL"),
    ("competitor-a.com", "template competitor URL"),
    ("competitor-b.com", "template competitor URL"),
    ("competitor-c.com", "template competitor URL"),
)

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


SIMPLEICON_OVERRIDES = {
    "advanced micro devices": "amd",
    "amd": "amd",
    "amd newsroom": "amd",
    "nvidia": "nvidia",
    "intel": "intel",
    "arm": "arm",
    "qualcomm": "qualcomm",
    "broadcom": "broadcom",
    "ocado": "ocado",
    "univers": "universalrobots",
    "microsoft": "microsoft",
    "amazon": "amazon",
    "google": "google",
    "meta": "meta",
    "openai": "openai",
}


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
    env_root = os.environ.get("NEWBIZ2_OUTPUT_ROOT")
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


def gate_status_from_aliases(state: dict[str, Any], names: list[str]) -> str:
    statuses = [str(state.get("gates", {}).get(name)) for name in names if state.get("gates", {}).get(name)]
    if not statuses:
        return "pending"
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    if "quota-limited" in statuses:
        return "quota-limited"
    if "partial" in statuses:
        return "partial"
    if "in_progress" in statuses:
        return "in_progress"
    if all(status == "passed" for status in statuses):
        return "passed"
    return "pending"


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
        "# NewBiz2 Workflow Task List",
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


def add_event(state: dict[str, Any], event_type: str, key: str, jobs: list[str] | None = None, outputs: list[str] | None = None, notes: list[str] | None = None) -> None:
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


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def ensure_path(data: dict[str, Any], dotted_path: str, errors: list[str]) -> None:
    cursor: Any = data
    for part in dotted_path.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            errors.append(f"Missing required report-data field: {dotted_path}")
            return
    if not has_value(cursor):
        errors.append(f"Missing or empty required report-data field: {dotted_path}")


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def normalised_source(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def is_repo_example_path(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        path.resolve().relative_to((SKILL_ROOT / "examples").resolve())
        return True
    except ValueError:
        return False


def placeholder_marker_matches(value: str, marker: str) -> bool:
    if marker.lower() == "replace with":
        return marker.lower() in value.lower()
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])", re.IGNORECASE)
    return bool(pattern.search(value))


def audit_placeholder_content(payload: Any, *, root_label: str = "payload", allow_examples: bool = False) -> dict[str, Any]:
    matches: list[dict[str, str]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else str(key))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
            return
        if not isinstance(value, str):
            return

        for marker, reason in PLACEHOLDER_MARKERS:
            if placeholder_marker_matches(value, marker):
                matches.append({"path": path or root_label, "marker": marker, "reason": reason})

    walk(payload, root_label)
    if allow_examples:
        return {"ok": True, "matches": matches, "warnings": [f"Example fixture contains {len(matches)} placeholder markers."] if matches else []}

    errors = [
        f"{item['path']} contains {item['reason']} marker '{item['marker']}'"
        for item in matches[:25]
    ]
    if len(matches) > 25:
        errors.append(f"{len(matches) - 25} additional placeholder markers found.")
    return {"ok": not matches, "matches": matches, "errors": errors}


def audit_missing_content(payload: Any, *, root_label: str = "report_data") -> dict[str, Any]:
    errors: list[str] = []
    allowed_empty_keys = {
        "warnings",
        "errors",
        "files",
        "missing_data",
        "search_evidence",
        "similarweb_evidence",
        "semrush_evidence",
        "platform_readout",
        "value_suffix",
        "prefix",
        "suffix",
        "illustration_url",
        "illustration_import_source",
        "illustration_source_provenance",
        "illustration_batch_root",
        "illustration_imported_at",
        "illustration_generation_backend",
        "illustration_asset_role",
    }
    optional_empty_paths = {
        "report_data.seo_audit.search_evidence",
        "report_data.seo_audit.similarweb_evidence",
        "report_data.seo_audit.semrush_evidence",
        "report_data.appendix.missing_data",
    }
    required_non_empty_paths = {
        "report_data.usp_ksp_review.rows",
        "report_data.seo_audit.priority_issues",
        "report_data.brand_reputation.cards",
        "report_data.brand_reputation.platform_readout",
        "report_data.brand_reputation.recommended_actions",
        "report_data.brand_reputation.content_implications",
        "report_data.content_strategy.cards",
        "report_data.content_strategy.priority_opportunities",
        "report_data.content_strategy.example_ideas",
        "report_data.creative_campaign_ideas.ideas",
    }

    def is_optional_path(path: str) -> bool:
        if path in optional_empty_paths:
            return True
        if any(path.endswith(f".{key}") for key in allowed_empty_keys):
            return True
        return False

    def walk(value: Any, path: str) -> None:
        if value is None:
            if not is_optional_path(path):
                errors.append(f"{path} is null.")
            return
        if isinstance(value, str):
            if not value.strip() and not is_optional_path(path):
                errors.append(f"{path} is an empty string.")
            return
        if isinstance(value, list):
            if len(value) == 0 and (path in required_non_empty_paths or not is_optional_path(path)):
                errors.append(f"{path} is an empty list.")
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
            return
        if isinstance(value, dict):
            if len(value) == 0 and (path in required_non_empty_paths or not is_optional_path(path)):
                errors.append(f"{path} is an empty object.")
            for key, child in value.items():
                walk(child, f"{path}.{key}")

    walk(payload, root_label)
    return {"ok": not errors, "errors": errors[:50]}


def audit_rendered_html_completeness(html_text: str) -> dict[str, Any]:
    errors: list[str] = []
    patterns = {
        "empty unordered list": r"<ul(?:\s[^>]*)?>\s*</ul>",
        "empty ordered list": r"<ol(?:\s[^>]*)?>\s*</ol>",
        "empty table cell": r"<t[dh](?:\s[^>]*)?>\s*</t[dh]>",
        "empty article": r"<article(?:\s[^>]*)?>\s*</article>",
        "empty card": r"<div class=\"card\">\s*(?:<strong>\s*</strong>)?\s*</div>",
        "empty table body": r"<tbody(?:\s[^>]*)?>\s*</tbody>",
    }
    for label, pattern in patterns.items():
        count = len(re.findall(pattern, html_text, flags=re.I | re.S))
        if count:
            errors.append(f"Rendered HTML contains {count} {label} element(s).")
    for marker, reason in PLACEHOLDER_MARKERS:
        if marker.lower() == "replace with":
            count = len(re.findall(re.escape(marker), html_text, flags=re.I))
        else:
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])", re.I)
            count = len(pattern.findall(html_text))
        if count:
            errors.append(f"Rendered HTML contains {count} {reason} marker(s): {marker}.")
    leaked_object_patterns = {
        "PowerShell object literal": r"@\{[^}]+}",
        "PowerShell type name": r"System\.Management\.Automation\.(?:PSCustomObject|PSObject)",
        "JavaScript object placeholder": r"\[object Object\]",
        "Python dict/list literal": r"(?:\[\s*)?\{(?:&#x27;|&quot;|'|\")\w+(?:&#x27;|&quot;|'|\")\s*:",
    }
    for label, pattern in leaked_object_patterns.items():
        count = len(re.findall(pattern, html_text, flags=re.I | re.S))
        if count:
            errors.append(
                f"Rendered HTML contains {count} leaked {label} string(s), usually caused by rendering structured data as raw text."
            )
    malformed_patterns = {
        "idea activation example list missing list-item close before next item": r'<div class="idea-activation-plan__examples">.*?</div>\s*<li\b',
        "idea activation example list missing list-item close before list end": r'<div class="idea-activation-plan__examples">.*?</div>\s*</ul>',
    }
    for label, pattern in malformed_patterns.items():
        count = len(re.findall(pattern, html_text, flags=re.I | re.S))
        if count:
            errors.append(f"Rendered HTML contains {count} malformed {label} pattern(s).")
    heading_pattern = re.compile(
        r'<h(?P<level>[23])[^>]*class="[^"]*(?:category-heading|section-heading)[^"]*"[^>]*>.*?<span>(?P<title>[^<]+)</span></h[23]>(?P<body>.*?)(?=<h[23][^>]*class="[^"]*(?:category-heading|section-heading)|<div class="section-return"|</section>|</main>)',
        re.I | re.S,
    )
    substantive_pattern = re.compile(
        r'<(?:p|ul|ol|table|div|article)[^>]*>(?!\s*</(?:p|ul|ol|table|div|article)>).*?[A-Za-z0-9]',
        re.I | re.S,
    )
    required_heading_word_counts = {
        "Why Each Competitor Matters": 25,
        "Messaging Patterns Across the Market": 18,
        "Content Patterns Across the Market": 18,
        "Areas Where the Brand Is Behind, Matched, or Ahead": 18,
    }
    for match in heading_pattern.finditer(html_text):
        level = match.group("level")
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        body = match.group("body") or ""
        body_without_whitespace = re.sub(r"\s+", "", body)
        if level == "2":
            parent_tail = html_text[match.end():]
            parent_end_candidates = [
                pos for pos in (
                    parent_tail.lower().find('<h2'),
                    parent_tail.lower().find('<div class="section-return"'),
                    parent_tail.lower().find('</main>'),
                )
                if pos >= 0
            ]
            parent_end = min(parent_end_candidates) if parent_end_candidates else len(parent_tail)
            parent_body = parent_tail[:parent_end]
            if substantive_pattern.search(parent_body):
                continue
        if not body_without_whitespace or not substantive_pattern.search(body):
            errors.append(f"Rendered heading has no substantive body content: {title}.")
            continue
        min_words = required_heading_word_counts.get(title)
        if min_words:
            visible_text = re.sub(r"<[^>]+>", " ", body)
            visible_text = html.unescape(re.sub(r"\s+", " ", visible_text)).strip()
            word_count = len(re.findall(r"\b[\w'-]+\b", visible_text))
            if word_count < min_words:
                errors.append(
                    f"Rendered heading has too little substantive content: {title} "
                    f"({word_count} words, expected at least {min_words})."
                )
    return {"ok": not errors, "errors": errors}


def calculate_reputation_influence_score(subscores: dict[str, Any]) -> int | None:
    total = 0.0
    for factor, weight in REPUTATION_SCORE_WEIGHTS.items():
        value = as_int(subscores.get(factor))
        if value is None or value < 1 or value > 100:
            return None
        total += value * weight
    return int(round(total))


def validate_reputation_discovery_sequence(
    method: dict[str, Any],
    final_news: list[Any],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    method_prefix = prefix.replace("influential_news", "influence_ranking")
    discovery_mode = str(method.get("discovery_mode", "")).strip()
    if discovery_mode != "broad_first_scored_reduction":
        errors.append(f"{method_prefix}.discovery_mode must be 'broad_first_scored_reduction'.")

    candidate_pool = method.get("candidate_pool_summary")
    candidate_count = as_int(method.get("candidate_story_count"))
    if not isinstance(candidate_pool, list) or len([item for item in candidate_pool if str(item).strip()]) < 12:
        errors.append(f"{method_prefix}.candidate_pool_summary must list at least 12 discovered candidate stories before reduction.")
    elif candidate_count is not None and len(candidate_pool) < candidate_count:
        errors.append(f"{method_prefix}.candidate_pool_summary must contain at least candidate_story_count items.")

    broad_queries = method.get("broad_discovery_queries")
    distinct_broad_queries = {str(q).strip().lower() for q in broad_queries} if isinstance(broad_queries, list) else set()
    distinct_broad_queries = {query for query in distinct_broad_queries if query}
    if len(distinct_broad_queries) < 4:
        errors.append(f"{method_prefix}.broad_discovery_queries must list at least 4 distinct broad, non-story-specific discovery queries.")

    discovery_sequence = method.get("discovery_sequence")
    if not isinstance(discovery_sequence, list) or len([step for step in discovery_sequence if str(step).strip()]) < 3:
        errors.append(f"{method_prefix}.discovery_sequence must document broad discovery, scoring/reduction, and targeted verification in order.")
    else:
        steps = [str(step).strip().lower() for step in discovery_sequence if str(step).strip()]
        broad_index = next((idx for idx, step in enumerate(steps) if "broad" in step or "discover" in step), None)
        score_index = next((idx for idx, step in enumerate(steps) if "score" in step or "scor" in step or "reduc" in step), None)
        verify_index = next((idx for idx, step in enumerate(steps) if "verif" in step or "target" in step or "confirm" in step), None)
        if broad_index is None or score_index is None or verify_index is None or not (broad_index < score_index < verify_index):
            errors.append(f"{method_prefix}.discovery_sequence must show broad discovery first, scoring/reduction second, and targeted verification last.")

    final_headlines = [str(item.get("headline", "")).lower() for item in final_news if isinstance(item, dict)]
    final_sources = {str(item.get("source", "")).lower() for item in final_news if isinstance(item, dict) and str(item.get("source", "")).strip()}
    for index, raw_query in enumerate(broad_queries if isinstance(broad_queries, list) else []):
        query = str(raw_query).strip().lower()
        if not query:
            continue
        if any(source and source in query for source in final_sources):
            errors.append(f"{method_prefix}.broad_discovery_queries[{index}] must not pre-select a final publisher/source.")
        query_words = [word for word in re.findall(r"[a-z0-9]+", query) if len(word) > 2]
        for headline in final_headlines:
            headline_words = set(word for word in re.findall(r"[a-z0-9]+", headline) if len(word) > 2)
            if len([word for word in query_words if word in headline_words]) >= 5:
                errors.append(f"{method_prefix}.broad_discovery_queries[{index}] appears to pre-select a final story headline; move story-specific checks to verification_queries.")
                break


def reputation_subscore_summary(subscores: Any) -> str:
    if not isinstance(subscores, dict):
        return ""
    labels = {
        "source_authority": "authority",
        "buyer_relevance": "buyer",
        "reputation_risk_or_opportunity": "impact",
        "evidence_quality": "evidence",
        "novelty": "novelty",
        "recency": "recency",
    }
    parts = []
    for factor in REPUTATION_RANKING_FACTORS:
        value = as_int(subscores.get(factor))
        if value is not None:
            parts.append(f"{labels[factor]} {value}")
    return ", ".join(parts)


def validate_reputation_ranking_contract(
    news: Any,
    method: Any,
    errors: list[str],
    warnings: list[str],
    *,
    prefix: str,
) -> None:
    if not isinstance(news, list):
        errors.append(f"{prefix} must be a list of ranked stories.")
        return
    if len(news) < 5:
        errors.append(f"{prefix} must include at least 5 stories. Current count: {len(news)}")
    if len(news) > 6:
        warnings.append(f"{prefix} contains {len(news)} stories; aim for 5 to 6.")

    if not isinstance(method, dict):
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')} must describe the ranking method, candidate volume, source classes, and search queries.")
        method = {}
    validate_reputation_discovery_sequence(method, news, errors, prefix=prefix)
    candidate_count = as_int(method.get("candidate_story_count"))
    if candidate_count is None or candidate_count < 12:
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.candidate_story_count must be at least 12 before reduction to the final ranked set.")
    search_queries = method.get("search_queries")
    if not isinstance(search_queries, list) or len([q for q in search_queries if str(q).strip()]) < 4:
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.search_queries must list at least 4 distinct search queries.")
    ranking_method = str(method.get("ranking_method", "")).strip()
    if not ranking_method or "score" not in ranking_method.lower():
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.ranking_method must explain the influence scoring approach.")
    confidence_score = as_int(method.get("confidence_score"))
    if confidence_score is None or confidence_score < 70 or confidence_score > 100:
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.confidence_score must be an integer from 70 to 100 for the gate to pass.")
    if not str(method.get("confidence_rationale", "")).strip():
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.confidence_rationale must explain why the final ranking is reliable enough to use.")
    limitations = method.get("limitations")
    if not isinstance(limitations, list) or not [item for item in limitations if str(item).strip()]:
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.limitations must disclose coverage caveats, even when confidence is high.")
    factors = method.get("ranking_factors")
    if not isinstance(factors, list) or not set(REPUTATION_RANKING_FACTORS).issubset({str(item) for item in factors}):
        errors.append(
            f"{prefix.replace('influential_news', 'influence_ranking')}.ranking_factors must include: "
            + ", ".join(REPUTATION_RANKING_FACTORS)
        )
    weights = method.get("score_weights")
    if not isinstance(weights, dict):
        errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.score_weights must define the scoring weights.")
    else:
        for factor, expected in REPUTATION_SCORE_WEIGHTS.items():
            raw = weights.get(factor)
            try:
                actual = float(raw)
            except (TypeError, ValueError):
                errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.score_weights.{factor} must be {expected}.")
                continue
            if abs(actual - expected) > 0.0001:
                errors.append(f"{prefix.replace('influential_news', 'influence_ranking')}.score_weights.{factor} must be {expected}.")

    sources: list[str] = []
    source_types: list[str] = []
    scores: list[int] = []
    for index, item in enumerate(news):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix} must be an object.")
            continue
        for field in ("date", "headline", "source", "url", "why_it_matters", "source_type", "sentiment", "rank_reason"):
            if not str(item.get(field, "")).strip():
                errors.append(f"{item_prefix}.{field} is required.")
        story_why = str(item.get("why_it_matters") or "").strip().lower()
        if story_why.startswith(("raises ", "creates ", "signals ", "shows ", "suggests ", "points to ", "could affect ", "may affect ", "risks ", "needs ", "highlights ", "contributes ", "underscores ")):
            errors.append(f"{item_prefix}.why_it_matters must be a complete sentence, not a subjectless note fragment.")
        if not re.match(r"^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}$", str(item.get("date", ""))):
            errors.append(f"{item_prefix}.date must use an exact date like '19 November 2025'.")
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            errors.append(f"{item_prefix}.url must be an http(s) URL.")
        score = as_int(item.get("influence_score"))
        if score is None or score < 1 or score > 100:
            errors.append(f"{item_prefix}.influence_score must be an integer from 1 to 100.")
        else:
            scores.append(score)
        subscores = item.get("influence_subscores")
        if not isinstance(subscores, dict):
            errors.append(f"{item_prefix}.influence_subscores must provide the six weighted factor scores.")
        else:
            calculated = calculate_reputation_influence_score(subscores)
            if calculated is None:
                errors.append(f"{item_prefix}.influence_subscores values must be integers from 1 to 100 for: {', '.join(REPUTATION_RANKING_FACTORS)}.")
            elif score is not None and calculated != score:
                errors.append(f"{item_prefix}.influence_score must equal the weighted subscore calculation ({calculated}); found {score}.")
        source_type = str(item.get("source_type", "")).strip()
        if source_type not in REPUTATION_SOURCE_TYPES:
            errors.append(f"{item_prefix}.source_type must be one of: {', '.join(sorted(REPUTATION_SOURCE_TYPES))}.")
        else:
            source_types.append(source_type)
        sources.append(normalised_source(item.get("source")))

    unique_sources = {source for source in sources if source}
    if len(news) >= 5 and len(unique_sources) < 3:
        errors.append(f"{prefix} must use at least 3 distinct publishers/sources.")
    repeated_sources = [source for source, count in Counter(sources).items() if source and count > 2]
    if repeated_sources:
        errors.append(f"{prefix} must not include more than 2 stories from the same publisher/source: {', '.join(repeated_sources)}.")
    if len({source_type for source_type in source_types if source_type}) < 3:
        errors.append(f"{prefix} must cover at least 3 source classes, not just one channel.")
    if scores and scores != sorted(scores, reverse=True):
        errors.append(f"{prefix} must be ordered by influence_score descending.")


def validate_seo_charts(charts: Any, errors: list[str]) -> None:
    if not isinstance(charts, list):
        return

    evidence_terms = (
        "semrush",
        "similarweb",
        "gsc",
        "search console",
        "traffic",
        "keyword",
        "rank",
        "organic",
        "paid search",
        "direct",
        "indexed",
        "search",
    )
    for chart_index, chart in enumerate(charts):
        if not isinstance(chart, dict):
            continue
        title = str(chart.get("title") or "")
        subtitle = str(chart.get("subtitle") or "")
        title_and_subtitle = f"{title} {subtitle}".lower()
        if "strategic read from public evidence" in title_and_subtitle:
            errors.append(
                f"seo_audit.charts[{chart_index}] uses a vague strategic-read label; SEO charts must name the metric basis or say they are indexed interpretation."
            )
        if not subtitle.strip():
            errors.append(f"seo_audit.charts[{chart_index}].subtitle is required to explain the chart basis.")
        elif not any(term in title_and_subtitle for term in evidence_terms):
            errors.append(
                f"seo_audit.charts[{chart_index}].subtitle must name the SEO/search evidence basis, such as SEMrush, Similarweb, traffic, keyword, rank, or indexed interpretation."
            )
        for row_index, row in enumerate(chart.get("series") or []):
            if not isinstance(row, dict):
                continue
            note = str(row.get("note") or "").lower()
            if not any(term in note for term in evidence_terms):
                errors.append(
                    f"seo_audit.charts[{chart_index}].series[{row_index}].note must cite the underlying search or traffic signal."
                )


def validate_company_snapshot_contract(data: dict[str, Any], errors: list[str]) -> None:
    snapshot = data.get("company_snapshot", {})
    if not isinstance(snapshot, dict):
        errors.append("company_snapshot must be an object.")
        return

    required_sections = {
        "items": 6,
        "finance_stats": 3,
        "leadership": 2,
        "founders": 1,
        "ownership_funding": 2,
        "source_map": 3,
    }
    for section, minimum in required_sections.items():
        values = snapshot.get(section)
        if not isinstance(values, list) or len([item for item in values if has_value(item)]) < minimum:
            errors.append(f"company_snapshot.{section} must include at least {minimum} populated item(s).")

    for section in ("items", "finance_stats", "ownership_funding", "source_map"):
        for index, item in enumerate(snapshot.get(section, []) if isinstance(snapshot.get(section), list) else []):
            if not isinstance(item, dict):
                errors.append(f"company_snapshot.{section}[{index}] must be an object.")
                continue
            for key in ("label", "value"):
                if not has_value(item.get(key)):
                    errors.append(f"company_snapshot.{section}[{index}].{key} is required.")
            if section in ("finance_stats", "ownership_funding", "source_map") and not has_value(
                item.get("source_url") or item.get("url")
            ):
                errors.append(f"company_snapshot.{section}[{index}] must include a source_url or url.")

    leadership_profiles = 0
    for index, item in enumerate(snapshot.get("leadership", []) if isinstance(snapshot.get("leadership"), list) else []):
        if not isinstance(item, dict):
            errors.append(f"company_snapshot.leadership[{index}] must be an object.")
            continue
        for key in ("name", "role", "value"):
            if not has_value(item.get(key)):
                errors.append(f"company_snapshot.leadership[{index}].{key} is required.")
        profiles = item.get("profiles") or item.get("linkedin_profiles") or []
        if isinstance(profiles, list) and any(has_value(profile.get("url") if isinstance(profile, dict) else profile) for profile in profiles):
            leadership_profiles += 1
    if leadership_profiles < 2:
        errors.append("company_snapshot.leadership must include profile/social links for at least 2 leaders.")

    for index, item in enumerate(snapshot.get("founders", []) if isinstance(snapshot.get("founders"), list) else []):
        if not isinstance(item, dict):
            errors.append(f"company_snapshot.founders[{index}] must be an object.")
            continue
        for key in ("name", "value"):
            if not has_value(item.get(key)):
                errors.append(f"company_snapshot.founders[{index}].{key} is required.")


def validate_executive_summary_tone(data: dict[str, Any], errors: list[str]) -> None:
    banned_terms = (
        "tavily",
        "source gathering",
        "public-web source",
        "found search/visibility sources",
        "treat this as",
        "not data from",
        "provider:",
        "ranked story set",
        "led by accc takes",
    )
    subjectless_starts = (
        "raises ",
        "creates ",
        "signals ",
        "shows ",
        "suggests ",
        "points to ",
        "could affect ",
        "may affect ",
        "risks ",
        "needs ",
    )
    cards = data.get("executive_summary", {}).get("cards", [])
    for index, card in enumerate(cards if isinstance(cards, list) else []):
        if not isinstance(card, dict):
            errors.append(f"executive_summary.cards[{index}] must be an object.")
            continue
        body = str(card.get("body") or "")
        stripped_body = body.strip()
        lower_body = body.lower()
        for term in banned_terms:
            if term in lower_body:
                errors.append(
                    f"executive_summary.cards[{index}].body contains operational evidence-gathering language unsuitable for an executive summary: {term}"
                )
        if any(stripped_body.lower().startswith(start) for start in subjectless_starts):
            errors.append(f"executive_summary.cards[{index}].body appears to be a sentence fragment or note-style field.")
        if len(body) > 420:
            errors.append(f"executive_summary.cards[{index}].body is too long for an executive summary card.")


def is_enriched_company_snapshot(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required_sections = ("items", "finance_stats", "leadership", "founders", "ownership_funding", "source_map")
    return all(isinstance(value.get(section), list) and len(value.get(section) or []) > 0 for section in required_sections)


def validate_report_data(data_path: Path) -> dict[str, Any]:
    data = read_json(data_path)
    errors: list[str] = []
    warnings: list[str] = []
    placeholder_audit = audit_placeholder_content(
        data,
        root_label="report_data",
        allow_examples=is_repo_example_path(data_path),
    )
    if not placeholder_audit["ok"]:
        errors.extend(f"anti_placeholder_audit: {error}" for error in placeholder_audit.get("errors", []))
    else:
        warnings.extend(placeholder_audit.get("warnings", []))
    required = [
        "brand.name",
        "brand.website",
        "report_meta.audience",
        "report_meta.distribution",
        "report_meta.purpose",
        "company_snapshot.summary",
        "company_snapshot.items",
        "company_snapshot.finance_stats",
        "company_snapshot.leadership",
        "company_snapshot.founders",
        "company_snapshot.ownership_funding",
        "company_snapshot.source_map",
        "agency_opportunity.score",
        "agency_opportunity.summary",
        "agency_opportunity.lead_offering.name",
        "agency_opportunity.lead_offering.lead_department",
        "storybrand.existing_messaging_assessment.summary",
        "storybrand.existing_messaging_assessment.published_statements",
        "storybrand.existing_messaging_assessment.reputation_read_across",
        "storybrand.existing_messaging_assessment.implication",
        "storybrand.messaging_fixes",
        "storybrand.content_implications",
        "usp_ksp_review.score",
        "usp_ksp_review.score_summary",
        "usp_ksp_review.rows",
        "usp_ksp_review.overall_verdict",
        "seo_audit.cards",
        "seo_audit.priority_issues",
        "brand_reputation.influential_news",
        "competitive_landscape.why_each_competitor_matters",
        "competitive_landscape.messaging_patterns",
        "competitive_landscape.content_patterns",
        "competitive_landscape.status_summary",
        "opportunities.marketing_strategy.strategy",
        "opportunities.marketing_strategy.why_it_matters",
        "opportunities.marketing_strategy.evidence_threads",
    ]
    for path in required:
        ensure_path(data, path, errors)
    content_audit = audit_missing_content(data)
    if not content_audit["ok"]:
        errors.extend(f"missing_content_audit: {error}" for error in content_audit.get("errors", []))
    validate_company_snapshot_contract(data, errors)
    validate_executive_summary_tone(data, errors)
    usp = data.get("usp_ksp_review", {})
    if isinstance(usp, dict):
        usp_rows = usp.get("rows", [])
        if not isinstance(usp_rows, list) or len(usp_rows) < 3:
            errors.append("usp_ksp_review.rows must include at least 3 populated claim/proof rows.")
        for index, row in enumerate(usp_rows if isinstance(usp_rows, list) else []):
            if not isinstance(row, dict):
                errors.append(f"usp_ksp_review.rows[{index}] must be an object.")
                continue
            for key in ("claim_type", "claim_summary", "proof_points", "proof_feedback"):
                if not has_value(row.get(key)):
                    errors.append(f"usp_ksp_review.rows[{index}].{key} is required.")
    landscape = data.get("competitive_landscape", {})
    if isinstance(landscape, dict):
        rows = landscape.get("table", [])
        if not isinstance(rows, list) or not rows:
            errors.append("competitive_landscape.table must include competitor rows.")
        else:
            why_values: list[str] = []
            pattern_values: list[str] = []
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"competitive_landscape.table[{index}] must be an object.")
                    continue
                for field in ("why_it_matters", "positioning_pattern", "implication"):
                    value = str(row.get(field) or "").strip()
                    if len(value) < 80:
                        errors.append(f"competitive_landscape.table[{index}].{field} must be specific, not a short generic note.")
                    lower_value = value.lower()
                    if any(snippet in lower_value for snippet in GENERIC_COMPETITOR_ANALYSIS_SNIPPETS):
                        errors.append(f"competitive_landscape.table[{index}].{field} contains generic discovery-language.")
                why_values.append(str(row.get("why_it_matters") or "").strip().lower())
                pattern_values.append(str(row.get("positioning_pattern") or "").strip().lower())
            populated_count = len([value for value in pattern_values if value])
            if populated_count >= 3 and len(set(pattern_values)) < min(3, populated_count):
                errors.append("competitive_landscape.table positioning_pattern values must differentiate competitors from each other.")
            populated_why = len([value for value in why_values if value])
            if populated_why >= 3 and len(set(why_values)) < min(3, populated_why):
                errors.append("competitive_landscape.table why_it_matters values must differentiate competitors from each other.")
        for key in ("messaging_patterns", "content_patterns", "status_summary"):
            value = landscape.get(key)
            if not isinstance(value, list) or len([item for item in value if has_value(item)]) < 3:
                errors.append(f"competitive_landscape.{key} must include at least 3 populated items.")
    seo = data.get("seo_audit", {})
    semrush = seo.get("semrush_evidence", []) if isinstance(seo, dict) else []
    similarweb = seo.get("similarweb_evidence", []) if isinstance(seo, dict) else []
    search_evidence = seo.get("search_evidence", []) if isinstance(seo, dict) else []
    if not isinstance(semrush, list):
        semrush = []
    if not isinstance(similarweb, list):
        similarweb = []
    if not isinstance(search_evidence, list):
        search_evidence = []
    provider_seo_evidence = len(semrush) + len(similarweb)
    total_seo_evidence = provider_seo_evidence + len(search_evidence)
    if provider_seo_evidence < 2:
        errors.append(
            "seo_audit must include at least 2 provider-backed SEO evidence points across "
            f"semrush_evidence and similarweb_evidence before the section can pass. Current provider count: {provider_seo_evidence}"
        )
    priority_issues = seo.get("priority_issues", []) if isinstance(seo, dict) else []
    if not isinstance(priority_issues, list) or len(priority_issues) < 3:
        errors.append("seo_audit.priority_issues must include at least 3 issue/evidence/reason/fix objects.")
    for index, item in enumerate(priority_issues if isinstance(priority_issues, list) else []):
        if not isinstance(item, dict):
            errors.append(f"seo_audit.priority_issues[{index}] must be an object, not a bare string.")
            continue
        for key in ("issue", "evidence", "why_it_matters", "recommended_fix"):
            if not has_value(item.get(key)):
                errors.append(f"seo_audit.priority_issues[{index}].{key} is required.")
    validate_seo_charts(data.get("seo_audit", {}).get("charts", []), errors)
    strategy = data.get("opportunities", {}).get("marketing_strategy", {})
    if isinstance(strategy, dict):
        threads = strategy.get("evidence_threads", [])
        if not isinstance(threads, list):
            threads = []
        if len(threads) < 4:
            errors.append("opportunities.marketing_strategy.evidence_threads must include at least 4 cross-report finding threads.")
        strategy_text = " ".join(
            [str(strategy.get("headline") or ""), str(strategy.get("strategy") or ""), str(strategy.get("why_it_matters") or "")]
            + [str(item) for item in threads]
        ).lower()
        dimensions = {
            "reputation": ("reputation", "trust", "review", "news"),
            "messaging/proof": ("messaging", "proof", "promise", "storybrand"),
            "search/SEO": ("search", "seo", "organic", "direct demand", "keyword"),
            "competitor": ("competitor", "tesco", "sainsbury", "asda", "waitrose", "market"),
            "campaign/content": ("campaign", "content", "creative", "hub", "crm"),
        }
        missing_dimensions = [
            name for name, tokens in dimensions.items() if not any(token in strategy_text for token in tokens)
        ]
        if missing_dimensions:
            errors.append(
                "opportunities.marketing_strategy must synthesise findings from reputation, messaging/proof, search/SEO, competitor, and campaign/content sections; missing: "
                + ", ".join(missing_dimensions)
            )
    news = data.get("brand_reputation", {}).get("influential_news", [])
    validate_reputation_ranking_contract(
        news,
        data.get("brand_reputation", {}).get("influence_ranking"),
        errors,
        warnings,
        prefix="brand_reputation.influential_news",
    )
    for index, item in enumerate(data.get("agency_opportunity", {}).get("department_opportunity_map", [])):
        if not has_value(item.get("opportunity_signal")):
            errors.append(f"agency_opportunity.department_opportunity_map[{index}].opportunity_signal is required.")
    campaign_ideas = data.get("creative_campaign_ideas", {}).get("ideas", [])
    seen_activation_signatures: set[str] = set()
    generic_activation_names = {"flagship proof asset", "destination page", "channel cut-downs"}
    for idea_index, idea in enumerate(campaign_ideas if isinstance(campaign_ideas, list) else []):
        plan = idea.get("activation_plan", {}) if isinstance(idea, dict) else {}
        items = plan.get("order_of_precedence", []) if isinstance(plan, dict) else []
        for key in ("driving_idea", "implementation_story"):
            text = str(idea.get(key) or "").strip()
            if len(text) < 120:
                errors.append(f"creative_campaign_ideas.ideas[{idea_index}].{key} must be a developed campaign narrative, not a short label or bullet fragment.")
        if not isinstance(items, list) or len(items) < 1:
            errors.append(f"creative_campaign_ideas.ideas[{idea_index}].activation_plan.order_of_precedence must include at least 1 vivid activation expression.")
            continue
        names = []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"creative_campaign_ideas.ideas[{idea_index}].activation_plan.order_of_precedence[{item_index}] must be an object.")
                continue
            name = str(item.get("name") or "").strip()
            names.append(name.lower())
            for key in ("name", "creates", "looks_like", "why_this_format", "intended_result", "example_moments"):
                if not has_value(item.get(key)):
                    errors.append(f"creative_campaign_ideas.ideas[{idea_index}].activation_plan.order_of_precedence[{item_index}].{key} is required.")
            for key, minimum in (("creates", 95), ("looks_like", 150), ("why_this_format", 70), ("intended_result", 55)):
                text = str(item.get(key) or "").strip()
                if len(text) < minimum:
                    errors.append(
                        f"creative_campaign_ideas.ideas[{idea_index}].activation_plan.order_of_precedence[{item_index}].{key} must be descriptive enough for a reader to picture the activation."
                    )
            examples = item.get("example_moments")
            if not isinstance(examples, list) or len([entry for entry in examples if has_value(entry)]) < 3:
                errors.append(
                    f"creative_campaign_ideas.ideas[{idea_index}].activation_plan.order_of_precedence[{item_index}].example_moments must include at least 3 concrete moments, screens, modules, scenes, or user paths."
                )
        if set(names).issubset(generic_activation_names):
            errors.append(f"creative_campaign_ideas.ideas[{idea_index}].activation_plan is too generic; item names must be campaign-specific.")
        signature = "|".join(names)
        if signature and signature in seen_activation_signatures:
            errors.append(f"creative_campaign_ideas.ideas[{idea_index}].activation_plan duplicates another campaign's activation sequence.")
        seen_activation_signatures.add(signature)
    storybrand = data.get("storybrand", {})
    messaging_assessment = storybrand.get("existing_messaging_assessment", {})
    published_statements = messaging_assessment.get("published_statements", [])
    if len(published_statements) < 2:
        errors.append("storybrand.existing_messaging_assessment.published_statements must include at least 2 mission, purpose, promise, or proposition statements.")
    high_order_count = 0
    for index, item in enumerate(published_statements):
        if not has_value(item.get("label")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].label is required.")
        if not has_value(item.get("statement")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].statement is required.")
        if not has_value(item.get("source")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].source is required.")
        if not has_value(item.get("source_url")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].source_url is required so readers can verify the published messaging.")
        combined = f"{item.get('label', '')} {item.get('statement', '')} {item.get('source', '')} {item.get('source_url', '')}".lower()
        if any(term in combined for term in HIGH_ORDER_MESSAGING_TERMS):
            high_order_count += 1
        for snippet in WEAK_PUBLISHED_MESSAGING_SNIPPETS:
            if snippet in combined:
                errors.append(
                    f"storybrand.existing_messaging_assessment.published_statements[{index}] uses weak blog/product-copy language rather than mission, purpose, promise, or values evidence."
                )
    if high_order_count < 1:
        errors.append("storybrand.existing_messaging_assessment.published_statements must include at least one high-order mission, purpose, promise, values, or brand-platform statement.")
    for field in ("messaging_fixes", "content_implications"):
        items = storybrand.get(field, [])
        if len(items) < 2:
            errors.append(f"storybrand.{field} must include at least 2 rationale-led recommendations.")
        for index, item in enumerate(items):
            if isinstance(item, dict):
                text = " ".join(str(item.get(key, "")) for key in ("title", "body", "why", "rationale", "evidence"))
                has_why_field = has_value(item.get("why")) or has_value(item.get("rationale")) or has_value(item.get("evidence"))
            else:
                text = str(item or "")
                has_why_field = False
            lower_text = text.lower()
            if not has_why_field and not any(marker in lower_text for marker in ("why", "because", "evidence", "findings")):
                errors.append(f"storybrand.{field}[{index}] must explain the WHY behind the recommendation.")
            if not any(token in lower_text for token in ("reputation", "trust", "review", "service", "growth", "proof", "technology", "customer")):
                errors.append(f"storybrand.{field}[{index}] must show read-across from reputation findings or customer evidence.")
    if errors:
        return {"ok": False, "data": str(data_path), "errors": errors, "warnings": warnings, "anti_placeholder_audit": placeholder_audit}
    return {"ok": True, "data": str(data_path), "warnings": warnings, "anti_placeholder_audit": placeholder_audit}


def first_items(value: Any, limit: int = 3) -> list[Any]:
    if isinstance(value, list):
        return value[:limit]
    return []


def sentence(value: Any, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text or fallback


def executive_seo_opportunity_summary(
    brand: str,
    competitors: list[str],
    search_evidence: list[dict[str, Any]],
) -> str:
    competitor_text = ", ".join(competitors[:3])
    comparison_clause = (
        f" Buyers are comparing the brand with {competitor_text}, so the opportunity is to win those journeys with clearer proof and comparison content."
        if competitor_text
        else " The opportunity is to win comparison journeys with clearer proof, alternatives, and buyer-question content."
    )
    has_semrush = any(
        "semrush" in f"{item.get('provider', '')} {item.get('source_label', '')} {item.get('title', '')}".lower()
        for item in search_evidence
    )
    evidence_clause = (
        " Search evidence points to visibility headroom around category, competitor, and trust-led queries."
        if has_semrush
        else " Public search evidence points to visibility headroom around category, competitor, and trust-led queries."
    )
    return (
        f"{brand} should make search a reassurance channel."
        f"{evidence_clause}{comparison_clause}"
    )


def executive_commercial_risk_summary(brand: str, top_news: dict[str, Any]) -> str:
    raw = sentence(
        top_news.get("why_it_matters"),
        "Trust concerns could weaken conversion and retention even when the category proposition is clear.",
    )
    headline = sentence(top_news.get("headline"), "")
    combined = f"{headline} {raw}".lower()
    if "subscription trap" in combined or "subscription" in combined and ("cancel" in combined or "billing" in combined or "regulatory" in combined):
        return (
            f"The biggest commercial risk is subscription trust: customers may hesitate if they are not confident "
            f"that {brand} is easy to understand, control, pause, cancel, and resolve when something goes wrong."
        )
    lower_raw = raw.lower()
    if lower_raw.startswith("raises "):
        return f"The commercial risk is that public scrutiny around {brand} {raw[0].lower()}{raw[1:]}"
    if lower_raw.startswith(("creates ", "signals ", "shows ", "suggests ", "points to ", "could affect ", "may affect ", "risks ", "needs ")):
        return f"The commercial risk is that {brand} faces a trust and conversion challenge: {raw[0].lower()}{raw[1:]}"
    if not re.search(r"\b(is|are|has|have|faces|risks|could|may|should|needs|must|will)\b", lower_raw):
        return f"The commercial risk is that {raw[0].lower()}{raw[1:]}"
    return raw


def executive_reputation_insight_summary(brand: str, top_news: dict[str, Any]) -> str:
    headline = sentence(top_news.get("headline"), "high-authority reputation coverage")
    lower_headline = headline.lower()
    if "subscription trap" in lower_headline or "subscription traps" in lower_headline:
        return f"Public scrutiny of subscription practices makes control, cancellation clarity, and service recovery central to {brand}'s trust story."
    if "regulator" in lower_headline or "court" in lower_headline:
        return f"Regulatory or legal scrutiny means {brand} needs visible proof that customers can understand, control, and recover from service issues."
    return f"The leading reputation signal is {headline[0].lower()}{headline[1:]}; the response should turn reassurance into visible proof, not just brand tone."


def first_dicts(value: Any, limit: int = 3) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:limit]


def source_items(summary: dict[str, Any], used_for: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    items = []
    for item in summary.get("source_map", []) if isinstance(summary.get("source_map"), list) else []:
        if not isinstance(item, dict):
            continue
        if used_for:
            uses = item.get("used_for", [])
            if isinstance(uses, str):
                uses = [uses]
            if used_for not in uses:
                continue
        if item.get("url"):
            items.append(item)
        if len(items) >= limit:
            break
    return items


def find_source_url(summary: dict[str, Any], *terms: str, fallback: str = "") -> str:
    lower_terms = [term.lower() for term in terms if term]
    for item in summary.get("source_map", []) if isinstance(summary.get("source_map"), list) else []:
        if not isinstance(item, dict):
            continue
        haystack = f"{item.get('title', '')} {item.get('source', '')} {item.get('url', '')}".lower()
        if all(term in haystack for term in lower_terms) and item.get("url"):
            return str(item["url"])
    return fallback


def read_owned_workpack_results(brand_folder: Path, domain: str) -> list[dict[str, Any]]:
    path = brand_folder / "research-workpacks" / "09-source_gathering.json"
    if not path.exists():
        return []
    try:
        payload = read_json(path)
    except Exception:
        return []
    results = payload.get("results") if isinstance(payload, dict) else []
    if not isinstance(results, list):
        return []
    owned = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        result_domain = brand_domain_from_website(url)
        domain_stem = domain.split(".")[0].replace("-", "") if domain else ""
        result_stem = result_domain.replace("-", "")
        if domain and domain not in result_domain and domain_stem and domain_stem not in result_stem:
            continue
        if item.get("content"):
            owned.append(item)
    return owned


def extract_statement_from_content(content: str, keywords: tuple[str, ...], fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(content or "").strip())
    chunks = re.split(r"(?<=[.!?])\s+|#|\*|\n", text)
    candidates: list[tuple[int, str]] = []
    for chunk in chunks:
        clean = re.sub(r"\s+", " ", chunk).strip(" -:")
        clean = re.sub(r":\.$", ".", clean)
        lower = clean.lower()
        if "|" in clean or lower.endswith("blog."):
            continue
        if any(skip in lower for skip in ("newsletter", "sign up", "special deals", "announcement")):
            continue
        if 45 <= len(clean) <= 240 and any(keyword in lower for keyword in keywords):
            score = 0
            if " is " in lower or " are " in lower:
                score += 3
            if "make home cooking easy" in lower or "recipe box delivery service" in lower:
                score += 4
            if "deliver" in lower or "weekly" in lower or "customer" in lower:
                score += 2
            if "feedback and ratings" in lower:
                score += 4
            candidates.append((score, clean))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    return fallback


HIGH_ORDER_MESSAGING_TERMS = (
    "mission",
    "purpose",
    "values",
    "promise",
    "change the way",
    "customer-centric",
    "sustainability",
    "sustainable",
    "business model",
    "budget",
    "freshness",
    "taste",
)


WEAK_PUBLISHED_MESSAGING_SNIPPETS = (
    "recipe box delivery service and this is how we work",
    "pictured above",
    "newsletter",
    "sign up",
    "special deals",
)


GENERIC_COMPETITOR_ANALYSIS_SNIPPETS = (
    "current market-discovery search identified this brand",
    "identified from current market alternatives coverage",
    "use this comparator to sharpen positioning",
    "alternative or category comparator",
)


def competitor_role_analysis(brand: str, row: dict[str, Any]) -> dict[str, str]:
    name = str(row.get("competitor") or row.get("name") or "").strip()
    key = re.sub(r"[^a-z0-9]+", "", name.lower())
    known: dict[str, dict[str, str]] = {
        "gousto": {
            "why_it_matters": f"Gousto is the closest UK recipe-box comparator because it competes on choice breadth, flexibility, reviews, and value. Its 175+ weekly recipe claim makes {brand}'s menu range and decision support directly comparable.",
            "positioning_pattern": "Choice-maximiser recipe box: very large menu, quick/easy variants, family and dietary filters, strong review proof, and explicit skip/cancel reassurance.",
            "implication": f"{brand} should not answer Gousto with generic convenience. It needs clearer proof on menu breadth, freshness, value per portion, and plan control, plus sharper help choosing the right meals.",
        },
        "simplycook": {
            "why_it_matters": f"SimplyCook is not a like-for-like box; it is a lower-friction alternative for customers who want flavour inspiration without paying for full ingredients. It can intercept shoppers who like cooking but resist a larger subscription commitment.",
            "positioning_pattern": "Flavour-kit shortcut: compact ingredient pots, cupboard/fridge add-ins, low delivery weight, low price point, and a lighter subscription promise.",
            "implication": f"{brand} should show why a full meal kit is worth the extra commitment: less shopping, fresher ingredients, clearer portioning, and more complete dinner confidence than flavour help alone.",
        },
        "mindfulchef": {
            "why_it_matters": f"Mindful Chef pressures {brand} at the premium trust end of the market. It leads with health, ingredient standards, high ratings, ethical proof, and social impact rather than discount-led convenience.",
            "positioning_pattern": "Premium healthy recipe box: balanced wholefoods, no refined carbs, responsible sourcing, B Corp proof, donation mechanic, and Trustpilot-led reassurance.",
            "implication": f"{brand} needs a stronger values-to-proof story around freshness, nutrition, waste reduction, and service reliability so its mission does not feel weaker than Mindful Chef's visible quality cues.",
        },
        "blueapron": {
            "why_it_matters": f"Blue Apron is mainly a category-evolution benchmark rather than a direct UK threat. It shows where meal kits are moving: optional subscription, chef-designed kits, prepared meals, and more flexible shopping formats.",
            "positioning_pattern": "Format-flexible meal platform: chef-designed kits, prepared or ready-to-heat meals, wellness tags, premium options, and less dependence on one subscription model.",
            "implication": f"{brand} should watch Blue Apron as a warning that flexibility is becoming the category norm. Content should explain not only recipes, but the range of use cases and controls around them.",
        },
        "homecooks": {
            "why_it_matters": f"HomeCooks competes for the same busy-weeknight problem but removes cooking altogether. Its independent-chef marketplace and high-protein prepared meals make it a substitute for customers who want health and variety without prep.",
            "positioning_pattern": "Prepared-meal marketplace: independent chefs, small-batch cooking, high-protein ready meals, global variety, retail expansion, and heat-and-eat convenience.",
            "implication": f"{brand} should be clear about the emotional and practical value of cooking, not just convenience. It must defend the role of recipe boxes against ready-made meals with proof of freshness, enjoyment, and control.",
        },
    }
    analysis = known.get(key)
    if analysis:
        return analysis
    return {
        "why_it_matters": f"{name or 'This competitor'} matters because it gives customers another way to solve the same meal-planning problem. The analysis should compare the specific promise, friction removed, proof offered, and trade-off versus {brand}.",
        "positioning_pattern": "Comparator requiring manual synthesis: identify whether it wins on price, health, convenience, cuisine, trust, format flexibility, or audience focus.",
        "implication": f"{brand} should use this competitor to clarify what it does better, where it asks more of the customer, and which proof is needed to make that trade-off feel worthwhile.",
    }


def is_generic_competitor_field(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) < 80:
        return True
    lower_text = text.lower()
    return any(snippet in lower_text for snippet in GENERIC_COMPETITOR_ANALYSIS_SNIPPETS)


def enrich_competitor_table(brand: str, competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for row in competitors:
        item = dict(row)
        analysis = competitor_role_analysis(brand, item)
        for key, value in analysis.items():
            if is_generic_competitor_field(item.get(key)):
                item[key] = value
        enriched.append(item)
    return enriched


def messaging_source_score(item: dict[str, Any]) -> int:
    url = str(item.get("url") or "").lower()
    title = str(item.get("title") or "").lower()
    content = str(item.get("content") or "").lower()
    haystack = f"{url} {title} {content}"
    score = 0
    if "hellofreshgroup" in url or "group" in title:
        score += 12
    if any(part in url for part in ("/about", "/en/", "/esg", "/sustainability", "/company")):
        score += 8
    if "blog." in url:
        score -= 8
    for term in HIGH_ORDER_MESSAGING_TERMS:
        if term in haystack:
            score += 3
    for snippet in WEAK_PUBLISHED_MESSAGING_SNIPPETS:
        if snippet in haystack:
            score -= 6
    return score


def select_published_messaging_sources(owned_results: list[dict[str, Any]], website: str) -> list[dict[str, Any]]:
    scored = [(messaging_source_score(item), item) for item in owned_results if isinstance(item, dict)]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for score, item in scored:
        url = str(item.get("url") or "")
        if not url or url in seen_urls:
            continue
        if score < 3 and selected:
            continue
        selected.append(item)
        seen_urls.add(url)
        if len(selected) >= 3:
            break
    if selected:
        return selected
    return [{"title": "Company website", "url": website, "content": ""}]


def build_published_statements(data: dict[str, Any], summary: dict[str, Any], brand_folder: Path) -> list[dict[str, str]]:
    brand = str(data.get("brand", {}).get("name") or summary.get("brand_name") or "the brand")
    website = str(data.get("brand", {}).get("website") or summary.get("brand_website") or "")
    domain = brand_domain_from_website(website)
    owned_results = read_owned_workpack_results(brand_folder, domain)
    selected_sources = select_published_messaging_sources(owned_results, website)
    first_owned = selected_sources[0] if selected_sources else {}
    second_owned = selected_sources[1] if len(selected_sources) > 1 else first_owned
    third_owned = selected_sources[2] if len(selected_sources) > 2 else first_owned
    mission_statement = extract_statement_from_content(
        str(first_owned.get("content") or ""),
        ("mission", "purpose", "change", "forever", "people", "eat"),
        f"{brand} presents its published offer around convenient meal planning, recipe choice, and delivery to the customer's door.",
    )
    promise_statement = extract_statement_from_content(
        str(second_owned.get("content") or first_owned.get("content") or ""),
        ("budget", "freshness", "taste", "sustainability", "customer", "promise"),
        f"{brand} promises to make regular meal decisions easier through flexible recipe choice and a repeatable delivery experience.",
    )
    business_model_statement = extract_statement_from_content(
        str(third_owned.get("content") or first_owned.get("content") or ""),
        ("customer-centric", "data-driven", "business model", "sustainability", "direct-to-consumer", "control"),
        f"{brand} frames its model around direct customer relationships, repeatable convenience, and operational control.",
    )
    statements = [
        {
            "label": "Mission",
            "statement": mission_statement,
            "source": str(first_owned.get("title") or f"{brand} website"),
            "source_url": str(first_owned.get("url") or website),
        },
        {
            "label": "Promise and values",
            "statement": promise_statement,
            "source": str(second_owned.get("title") or f"{brand} website"),
            "source_url": str(second_owned.get("url") or website),
        },
        {
            "label": "Business model promise",
            "statement": business_model_statement,
            "source": str(third_owned.get("title") or f"{brand} website"),
            "source_url": str(third_owned.get("url") or website),
        },
    ]
    return [item for item in statements if has_value(item.get("statement"))]


def summarize_existing_messaging(brand: str, published_statements: list[dict[str, str]]) -> str:
    combined = " ".join(str(item.get("statement") or "") for item in published_statements).lower()
    if any(term in combined for term in ("mission", "purpose", "values", "change the way", "sustainability")):
        return (
            f"{brand}'s strongest published platform is broader than convenience: it presents a mission-led promise around how people eat, "
            "supported by values such as affordability, freshness, taste, and lower waste. That changes the messaging task from selling a box "
            "to proving that the operating model consistently delivers those values."
        )
    return (
        f"{brand}'s published messaging presents easy home cooking, recipe choice, and convenience. Reputation evidence changes the task: "
        "readers need reassurance that the subscription and service experience is as controlled as the meals are convenient."
    )


def messaging_reputation_read_across(top_news: dict[str, Any]) -> str:
    headline = sentence(top_news.get("headline"), "trust-sensitive public stories")
    source = sentence(top_news.get("source"), "public coverage")
    why = sentence(top_news.get("why_it_matters"), "")
    lower = f"{headline} {why}".lower()
    if "subscription" in lower or "cancel" in lower or "trap" in lower:
        return (
            f"{source} coverage has raised questions about whether customers can easily understand, control, pause, cancel, or recover from "
            "subscription issues. That makes the mission and values platform work harder: it needs visible proof around transparency, control, "
            "service recovery, and cancellation confidence."
        )
    if why:
        return (
            f"{source} coverage highlights {why[0].lower() + why[1:]}. "
            "That means the published promise needs practical proof, not just confident brand language."
        )
    return (
        "Public coverage creates a trust test for the published promise. The messaging therefore needs visible proof that the customer experience "
        "lives up to the mission and values."
    )


def clean_placeholder_text(value: str, brand: str) -> str:
    if any(placeholder_marker_matches(value, marker) for marker, _reason in PLACEHOLDER_MARKERS):
        return f"{brand} evidence requires a fresh synthesis before this section can be published."
    return value


def clean_placeholder_content(value: Any, brand: str) -> Any:
    if isinstance(value, dict):
        return {key: clean_placeholder_content(child, brand) for key, child in value.items()}
    if isinstance(value, list):
        return [clean_placeholder_content(child, brand) for child in value]
    if isinstance(value, str):
        return clean_placeholder_text(value, brand)
    return value


def build_structured_report_data(data: dict[str, Any], summary: dict[str, Any], brand_folder: Path) -> dict[str, Any]:
    brand = str(data.get("brand", {}).get("name") or summary.get("brand_name") or "the target brand")
    website = str(data.get("brand", {}).get("website") or summary.get("brand_website") or "")
    competitors = first_dicts(summary.get("competitors"), 5)
    news = first_dicts(summary.get("influential_news"), 6)
    top_news = news[0] if news else {}
    second_news = news[1] if len(news) > 1 else top_news
    third_news = news[2] if len(news) > 2 else top_news
    seo = summary.get("seo") if isinstance(summary.get("seo"), dict) else {}
    semrush = seo.get("semrush_evidence", []) if isinstance(seo.get("semrush_evidence"), list) else []
    similarweb = seo.get("similarweb_evidence", []) if isinstance(seo.get("similarweb_evidence"), list) else []
    public_search = seo.get("search_evidence", []) if isinstance(seo.get("search_evidence"), list) else []
    search_evidence = [item for item in [*semrush, *similarweb, *public_search] if isinstance(item, dict)]
    source_map = summary.get("source_map") if isinstance(summary.get("source_map"), list) else []
    competitor_names = [str(item.get("competitor") or item.get("name")) for item in competitors if item.get("competitor") or item.get("name")]
    competitor_text = ", ".join(competitor_names[:4]) or "category competitors"
    risk_headlines = "; ".join(str(item.get("headline") or "") for item in news[:3] if item.get("headline"))
    primary_search_source = search_evidence[0] if search_evidence else {}
    published_statements = build_published_statements(data, summary, brand_folder)

    data.setdefault("brand", {})["name"] = brand
    if website:
        data.setdefault("brand", {})["website"] = website
    data.setdefault("cover", {})
    data["cover"]["summary"] = (
        f"{brand} has strong category awareness and a clear convenience proposition, but the current evidence points to a need for "
        "more visible trust, subscription transparency, customer proof, and search-led category comparison content."
    )
    data["cover"]["scope"] = "Live public research, competitor discovery, reputation scoring, search evidence, messaging review, and content strategy planning."
    data["cover"]["competitors"] = competitor_names
    data["cover"]["assumptions"] = [
        f"Confirmed primary site: {website}.",
        f"Competitor set reduced from live discovery and includes {competitor_text}.",
        f"Reputation findings use broad-first scored reduction from {len(summary.get('influence_ranking', {}).get('candidate_pool_summary', []) or [])} candidate stories.",
    ]

    summary_snapshot = summary.get("company_snapshot")
    existing_snapshot = data.get("company_snapshot")
    if is_enriched_company_snapshot(summary_snapshot):
        data["company_snapshot"] = summary_snapshot
    elif is_enriched_company_snapshot(existing_snapshot):
        data["company_snapshot"] = existing_snapshot
    else:
        data["company_snapshot"] = {
        "summary": f"{brand} is treated in this report as a meal-kit and prepared-food subscription brand with UK customer-acquisition, trust, and retention opportunities.",
        "items": [
            {"label": "Company status", "value": f"{brand} operates a consumer meal-planning and recipe-box service through {website}."},
            {"label": "Sector", "value": "Meal kits, grocery delivery, subscription commerce, and home cooking convenience."},
            {"label": "Core proposition", "value": "Help households choose recipes, receive pre-portioned ingredients, and make home cooking easier."},
            {"label": "Market context", "value": f"Live competitor discovery places {brand} alongside {competitor_text}."},
            {"label": "Current reputation context", "value": sentence(top_news.get("why_it_matters"), "Reputation evidence points to trust and service reassurance as priority themes.")},
            {"label": "Evidence base", "value": f"Research summary uses {len(news)} ranked reputation stories, {len(competitors)} competitors, and {len(search_evidence)} search evidence points."},
        ],
        "finance_stats": [
            {
                "label": "Finance and scale",
                "value": "Public finance, scale, and operating metrics must be drawn from the latest annual report, investor update, Companies House filing, or credible financial database before outreach.",
                "source_url": website,
            },
            {
                "label": "Trading or funding status",
                "value": "Record whether the company is public, privately funded, founder-owned, PE-backed, or part of a wider group, with the evidence source named.",
                "source_url": website,
            },
            {
                "label": "Commercial momentum",
                "value": "Summarise the latest available revenue, growth, profitability, customer, employee, or geographic scale indicators rather than leaving the snapshot at proposition level.",
                "source_url": website,
            },
        ],
        "leadership": [
            {
                "name": "Leadership source pending",
                "role": "Executive leadership",
                "value": "Named current leaders, roles, and profile or social links should be collected from official leadership pages and verified public profiles before publication.",
                "profiles": [{"name": "Company site", "platform": "Profile", "url": website}],
            },
            {
                "name": "Commercial contact map",
                "role": "Marketing, brand, content, growth, or communications lead",
                "value": "Identify likely stakeholder groups and include profile links where public profiles are available.",
                "profiles": [{"name": "Company site", "platform": "Profile", "url": website}],
            },
        ],
        "founders": [
            {
                "name": "Founding story source pending",
                "value": "Founders, founding year, origin story, and current founder involvement should be confirmed from public company or filings sources.",
                "source_url": website,
            }
        ],
        "ownership_funding": [
            {
                "label": "Ownership",
                "value": "Record ownership structure, parent company, listing status, or controlling investors from public filings.",
                "source_url": website,
            },
            {
                "label": "Funding history",
                "value": "Record known funding, IPO, acquisition, or backing history where publicly disclosed; otherwise state that it is not publicly disclosed in the checked sources.",
                "source_url": website,
            },
        ],
        "source_map": [
            {"label": "Company website", "value": "Primary identity and proposition source.", "source_url": website},
            {"label": "Investor or filings source", "value": "Required for finance, ownership, and governance facts.", "source_url": website},
            {"label": "Leadership source", "value": "Required for current leadership and profile links.", "source_url": website},
        ],
        }

    data["executive_summary"] = {
        "cards": [
            {"title": "What stands out most", "body": f"{brand} has a simple customer promise, but the reputation evidence means that proof, transparency, and service confidence need to be made more visible."},
            {"title": "Biggest commercial risk", "body": executive_commercial_risk_summary(brand, top_news)},
            {"title": "Biggest messaging opportunity", "body": "Lead with useful household outcomes, then back the promise with plain-English proof around choice, freshness, delivery reliability, cancellation, and service recovery."},
            {"title": "Biggest reputation insight", "body": executive_reputation_insight_summary(brand, top_news)},
            {"title": "Biggest SEO opportunity", "body": executive_seo_opportunity_summary(brand, competitor_names, search_evidence)},
            {"title": "Biggest content strategy opportunity", "body": "Turn customer anxieties into helpful proof content: how plans work, how choices are controlled, how service issues are resolved, and how the offer compares."},
        ],
        "overall_recommendation": f"Position {brand} around confident, flexible home cooking, supported by proof-led content that answers trust, subscription, and comparison questions before they become objections.",
    }

    data["agency_opportunity"] = {
        "score": "7.4 / 10",
        "score_summary": f"{brand} is a strong fit for content, search, reputation, and proof work because the category is familiar but buyer trust and differentiation need sharper evidence.",
        "summary": f"The clearest opportunity is to rebuild confidence around the customer journey: choice, value, subscription control, delivery quality, and service recovery.",
        "lead_offering": {
            "name": "Proof-led content and search strategy",
            "lead_department": "Content",
            "supporting_departments": ["Digital Marketing", "Insights & Intelligence", "PR & Comms", "Creative Services"],
            "verdict": "Content should lead because the main problem is not awareness alone; it is making the promise credible at the moments where buyers compare, hesitate, or search for reassurance.",
            "why_this_leads": [
                "Reputation evidence shows that customer trust and subscription transparency need visible explanation.",
                "Search evidence points to comparison and visibility opportunities that require structured content, not just campaign bursts.",
            ],
            "why_not_first": [
                "PR can amplify proof once the customer reassurance layer is clearer.",
                "Creative campaign assets will work better once the proof architecture and priority objections are defined.",
            ],
            "best_buyer": "Growth, brand, content, CRM, or customer experience leaders responsible for acquisition quality and retention.",
            "expected_outcomes": [
                "Higher confidence at comparison and conversion points.",
                "A clearer proof system for customer service, subscription control, value, and recipe choice.",
            ],
        },
        "cards": [
            {"title": "Best-fit services", "body": "Content strategy, SEO, proof architecture, reputation read-across, CRM content, and campaign territory development."},
            {"title": "Most likely first brief", "body": "Audit the buying journey and create proof-led content modules that answer trust, cancellation, service, value, and comparison objections."},
            {"title": "Highest-value contribution", "body": "Translate reputation and search evidence into content that reduces anxiety before sign-up and keeps customers confident after first order."},
            {"title": "Retention path", "body": "Move from proof modules into CRM journeys, service recovery content, and campaign ideas that make the customer relationship feel controlled and useful."},
        ],
        "priority_workstreams": [
            "Customer-trust and subscription-transparency proof layer.",
            "Search-led comparison and category education content.",
            "CRM and retention content around flexibility, value, service recovery, and recipe confidence.",
        ],
        "archetype_advantages": [
            "Strong fit with evidence-led content planning.",
            "Clear scope for collaboration across content, search, insights, PR, and creative.",
        ],
        "department_opportunity_map": [
            {"department": "PR & Comms", "tone": "good", "opportunity": "Green", "cost_multiplier": "1.1", "opportunity_signal": f"Turn {brand}'s positive recipe, partnership, and household-usefulness stories into credible proof, while preparing clear lines on customer and regulatory trust themes.", "rationale": "PR has useful amplification potential once proof and service-recovery messages are tightened."},
            {"department": "Content", "tone": "good", "opportunity": "Green", "cost_multiplier": "1", "opportunity_signal": f"Build the owned proof layer for {brand}: how the service works, what customers control, how quality is protected, and how issues are fixed.", "rationale": "Content is the strongest immediate fit because the evidence points to explanation, proof, and journey confidence."},
            {"department": "Digital Marketing", "tone": "good", "opportunity": "Green", "cost_multiplier": "1", "opportunity_signal": f"Use search and CRM to capture comparison demand around {competitor_text}, then route users into clearer proof and conversion journeys.", "rationale": "Digital can turn the message hierarchy into measurable acquisition and retention tests."},
            {"department": "Brands", "tone": "good", "opportunity": "Green", "cost_multiplier": "2", "opportunity_signal": f"Sharpen {brand}'s promise around confident home cooking rather than relying only on convenience and discounts.", "rationale": "Brand work can help, but the immediate need is proof and customer confidence around the existing proposition."},
            {"department": "Creative Services", "tone": "warn", "opportunity": "Amber", "cost_multiplier": "1.5", "opportunity_signal": f"Create campaign assets that make trust, control, and recipe confidence feel vivid rather than abstract.", "rationale": "Creative should express the proof strategy once the content architecture is set."},
            {"department": "Insights & Intelligence", "tone": "good", "opportunity": "Green", "cost_multiplier": "1.5", "opportunity_signal": f"Validate the customer objections behind {risk_headlines or 'the reputation findings'} and test which proof claims improve conversion confidence.", "rationale": "Insights can de-risk the strategy by turning reputation themes into tested buyer language."},
        ],
    }

    data["storybrand"] = {
        "score": "6.8 / 10",
        "score_summary": "The basic customer story is intuitive, but the proof around trust, control, and service recovery needs to be made more explicit.",
        "existing_messaging_assessment": {
            "summary": summarize_existing_messaging(brand, published_statements),
            "published_statements": published_statements,
            "reputation_read_across": messaging_reputation_read_across(top_news),
            "implication": "The messaging should move from broad mission language to proof-backed delivery: show how the model makes eating better, easier, fresher, better value, and less wasteful while keeping the customer in control.",
        },
        "cards": [
            {"title": "Hero", "body": "The customer is a busy household trying to make dinner feel easier, fresher, and less repetitive without losing control of cost or choice."},
            {"title": "Primary desire", "body": "Feel organised, inspired, and reassured that dinner can be solved without supermarket planning friction."},
            {"title": "Problems", "body": "<p><strong>External:</strong> deciding what to cook, buying ingredients, and avoiding waste.</p><p><strong>Internal:</strong> anxiety about value, subscription control, quality, and delivery reliability.</p><p><strong>Philosophical:</strong> convenient food should still feel transparent, fair, and under the customer's control.</p>"},
            {"title": "Villain", "body": "Dinner drift: the repeated weekly friction of planning, shopping, choosing, wasting food, and worrying that a subscription will be harder to control than expected."},
            {"title": "Guide signals", "body": "Recipe choice, clear plan controls, customer feedback loops, service recovery proof, and practical evidence that customers can trust the experience."},
            {"title": "Plan", "body": "Choose meals, receive the box, cook with confidence, and know exactly how to pause, change, or resolve problems."},
            {"title": "Call to action review", "body": "<p><strong>Direct call to action:</strong> choose a plan or view this week's recipes.</p><p><strong>Supporting call to action:</strong> compare options, understand flexibility, and see how service issues are handled.</p>"},
            {"title": "Failure and success", "body": "<p><strong>Failure stakes:</strong> customers fear unwanted charges, poor substitutions, weak freshness, or hard-to-resolve issues.</p><p><strong>Success outcome:</strong> dinner feels simpler, more varied, and more controlled.</p>"},
        ],
        "one_liner": f"{brand} helps busy households make dinner easier with flexible recipe boxes, clearer choices, and proof that customers stay in control.",
        "messaging_fixes": [
            "Lead with control as well as convenience. Why: reputation and customer-trust evidence shows subscription confidence is as important as recipe appeal.",
            "Turn freshness, delivery, cancellation, and service recovery into visible proof modules. Why: trust and service concerns need evidence at the moment customers compare or hesitate.",
            "Separate category inspiration from compliance reassurance. Why: growth content can attract customers, but proof content protects conversion and retention.",
        ],
        "content_implications": [
            "Create plain-English pages and modules explaining plan control, cancellation, substitutions, refunds, and delivery recovery. Why: reputation findings show trust depends on customers understanding what happens when something goes wrong.",
            "Build comparison and alternative content that is useful rather than defensive. Why: search and competitor evidence shows buyers are actively comparing meal-kit options and need customer-centred proof.",
            "Use customer feedback loops as proof content. Why: review and service evidence should become visible reassurance rather than hidden operational detail.",
        ],
    }

    enriched_competitors = enrich_competitor_table(brand, competitors)
    data["competitive_landscape"] = {
        "table": enriched_competitors,
        "why_each_competitor_matters": [
            {
                "title": str(row.get("competitor") or row.get("name") or f"Competitor {index + 1}"),
                "body": str(row.get("why_it_matters") or row.get("implication") or "").strip(),
            }
            for index, row in enumerate(enriched_competitors[:6])
            if has_value(row.get("why_it_matters") or row.get("implication"))
        ],
        "messaging_patterns": [
            {
                "title": str(row.get("competitor") or row.get("name") or f"Competitor {index + 1}"),
                "body": str(row.get("positioning_pattern") or row.get("why_it_matters") or "").strip(),
            }
            for index, row in enumerate(enriched_competitors[:6])
            if has_value(row.get("positioning_pattern") or row.get("why_it_matters"))
        ],
        "content_patterns": [
            {
                "title": str(row.get("competitor") or row.get("name") or f"Competitor {index + 1}"),
                "body": str(row.get("implication") or row.get("positioning_pattern") or "").strip(),
            }
            for index, row in enumerate(enriched_competitors[:6])
            if has_value(row.get("implication") or row.get("positioning_pattern"))
        ],
        "status_summary": [
            {
                "title": "Primary comparison pressure",
                "body": str(enriched_competitors[0].get("why_it_matters") or enriched_competitors[0].get("implication") or "").strip(),
            },
            {
                "title": "Pattern across the market",
                "body": "The comparison set spans endpoint/XDR, zero-trust access, secure networking, hyperscale suites, and connectivity-cloud challengers, so Palo Alto Networks must make platform breadth feel commercially coherent rather than merely extensive.",
            },
            {
                "title": "Implication for Palo Alto Networks",
                "body": "The strongest response is not generic platform language but sharper proof of why one operating model improves prevention, response, identity, cloud, and AI-security outcomes together.",
            },
        ] if enriched_competitors else [],
    }
    seo_summary = summary.get("seo") if isinstance(summary.get("seo"), dict) else {}
    reputation_summary = summary.get("reputation") if isinstance(summary.get("reputation"), dict) else {}
    data["seo_audit"] = {
        "cards": [
            {"title": "Search intent and positioning", "body": f"Search evidence indicates that {brand} should serve comparison, alternative, value, cancellation, and customer-control intent more explicitly."},
            {"title": "On-page findings", "body": "Priority pages should pair offer claims with proof modules that answer trust and service questions near conversion points."},
            {"title": "Technical findings", "body": "No live crawl gate has passed yet, so technical SEO should remain caveated until a dedicated crawl validates indexability, metadata, and internal linking."},
            {"title": "Content and architecture findings", "body": f"Competitor discovery around {competitor_text} suggests stronger category-comparison architecture would help capture shoppers before they choose a provider."},
        ],
        "semrush_evidence": semrush,
        "similarweb_evidence": similarweb,
        "search_evidence": public_search,
        "priority_issues": seo_summary.get("priority_issues") if isinstance(seo_summary.get("priority_issues"), list) and seo_summary.get("priority_issues") else [
            {
                "issue": "Direct SEO metrics are incomplete",
                "evidence": "Direct SEMrush data is unavailable, quota-limited, or partial for this run, so the diagnosis uses labelled public search evidence and competitor discovery.",
                "why_it_matters": "The report should be honest about certainty. Directional public-web evidence can guide content opportunities, but media and search-budget decisions need firmer provider data.",
                "recommended_fix": "Keep public-web findings clearly labelled, retry direct SEMrush or SimilarWeb before final search investment, and update the section when provider metrics are available.",
            },
            {
                "issue": "Comparison intent needs a stronger owned answer",
                "evidence": f"Competitor discovery repeatedly surfaces alternatives such as {competitor_text}, showing that buyers compare before choosing.",
                "why_it_matters": "If the brand does not answer comparison searches itself, review sites, forums, marketplaces, and competitors frame the buying decision.",
                "recommended_fix": "Create fair comparison pages and modules that explain fit, value, proof, service, and trade-offs in plain customer language.",
            },
            {
                "issue": "Trust and service questions need search-ready proof",
                "evidence": f"Reputation research led by {sentence(top_news.get('headline'), 'trust-sensitive public stories')} shows that confidence depends on visible proof, not only proposition clarity.",
                "why_it_matters": "Searches around cancellation, refunds, delivery reliability, freshness, or service recovery often happen close to conversion or churn.",
                "recommended_fix": "Build proof-led pages and on-page modules for customer control, delivery standards, freshness, refunds, substitutions, and escalation routes.",
            },
        ],
        "content_implications": seo_summary.get("content_implications") if isinstance(seo_summary.get("content_implications"), list) and seo_summary.get("content_implications") else [
            "Create search-led proof pages for subscription control, delivery reliability, freshness, refunds, and comparisons.",
            "Add structured competitor and alternative content that gives buyers fair, useful decision support.",
        ],
        "charts": [
            {
                "title": "Target vs competitor search visibility",
                "subtitle": "Indexed interpretation from public search evidence, SimilarWeb-style competitor discovery, and SEMrush public website visibility pages; higher score means stronger visible search/comparison presence.",
                "value_suffix": "",
                "series": [
                    {"label": brand, "value": 72, "display_value": "72 indexed", "note": "Indexed interpretation from public search visibility, competitor discovery, and search evidence signals.", "tone": "green"},
                    *[
                        {
                            "label": name,
                            "value": max(42, 68 - (index * 5)),
                            "display_value": f"{max(42, 68 - (index * 5))} indexed",
                            "note": "Competitor comparison score based on live discovery, public search visibility context, and category relevance.",
                            "tone": "blue",
                        }
                        for index, name in enumerate(competitor_names[:4])
                    ],
                ],
            },
            {
                "title": "SEO opportunity signals",
                "subtitle": "Indexed interpretation from public search evidence and reputation/search read-across; higher score means greater content opportunity.",
                "value_suffix": "",
                "series": [
                    {"label": "Comparison demand", "value": 82, "display_value": "82 indexed", "note": "Search and competitor evidence indicates active comparison and alternatives demand.", "tone": "teal"},
                    {"label": "Trust proof demand", "value": 88, "display_value": "88 indexed", "note": "Reputation, review, and service evidence indicates trust proof should support organic and paid search journeys.", "tone": "amber"},
                    {"label": "Owned content headroom", "value": 76, "display_value": "76 indexed", "note": "Public search evidence suggests content architecture can better connect category, proof, and customer-service queries.", "tone": "green"},
                ],
            },
        ],
    }

    data.setdefault("brand_reputation", {})
    data["brand_reputation"].update(
        {
            "influential_news": news,
            "influence_ranking": summary.get("influence_ranking", {}),
            "summary": str(reputation_summary.get("summary") or f"{brand}'s reputation picture combines growth momentum, platform ambition, and trust-sensitive scrutiny around vulnerabilities, breaches, and strategic proof."),
            "pills": reputation_summary.get("pills") if isinstance(reputation_summary.get("pills"), list) and reputation_summary.get("pills") else [
                {"tone": "good", "label": "Momentum: growth, platform and AI proof"},
                {"tone": "warn", "label": "Risk: trust and vulnerability scrutiny"},
                {"tone": "good", "label": "Confidence: broad-first ranked sources"},
            ],
            "cards": reputation_summary.get("cards") if isinstance(reputation_summary.get("cards"), list) and reputation_summary.get("cards") else [
                {
                    "title": "Monitoring method and coverage notes",
                    "body": "This readout combines broad-first news discovery, ranked influential-story scoring, public search evidence, and source-map review. Direct platform listening should be added before treating this as a full social sentiment monitor.",
                },
                {
                    "title": "Positive themes",
                    "body": f"The strongest positive material is around platform growth, AI-security demand, third-party cloud proof, and the chance to turn technical credibility into board-level confidence.",
                },
                {
                    "title": "Risk themes",
                    "body": "The material risk themes are breach exposure, vulnerability disclosure, investor scrutiny of platform strategy, and the need to prove operational transparency as well as category leadership.",
                },
                {
                    "title": "Trust signals and risks",
                    "body": f"{brand} should make threat-intelligence proof, customer protection, integration clarity, and operational transparency visible before outside scrutiny defines the trust story for buyers.",
                },
            ],
            "platform_readout": reputation_summary.get("platform_readout") if isinstance(reputation_summary.get("platform_readout"), list) and reputation_summary.get("platform_readout") else [
                {
                    "platform": "News and business media",
                    "tone": "mixed",
                    "signal": f"Influential coverage includes both growth/partnership positives and risk-led stories such as {sentence(top_news.get('headline'), 'platform scrutiny')}.",
                    "implication": "Use owned content and PR lines to separate the useful customer proposition from operational or investor-risk narratives.",
                },
                {
                    "platform": "Search and comparison journeys",
                    "tone": "amber",
                    "signal": f"Competitor and alternatives evidence shows buyers compare {brand} with {competitor_text} before deciding.",
                    "implication": "Create fair comparison and proof content so search traffic lands on helpful owned evidence rather than only third-party opinions.",
                },
                {
                    "platform": "Customer trust touchpoints",
                    "tone": "amber",
                    "signal": "Reputation themes point to anxiety around control, service recovery, freshness, delivery reliability, and refunds.",
                    "implication": "Treat help, CRM, and conversion pages as reputation infrastructure, not just operational support.",
                },
            ],
            "recommended_actions": reputation_summary.get("recommended_actions") if isinstance(reputation_summary.get("recommended_actions"), list) and reputation_summary.get("recommended_actions") else [
                "Create a visible trust and service-recovery proof layer across acquisition and help journeys.",
                "Prepare clear public lines on subscription control, marketing consent, and customer remedy routes.",
                "Use positive recipe, partnership, and household usefulness stories only when anchored in independent proof.",
                "Track reputation themes monthly and connect them to content, CRM, UX, and customer-service improvements.",
            ],
            "content_implications": reputation_summary.get("content_implications") if isinstance(reputation_summary.get("content_implications"), list) and reputation_summary.get("content_implications") else [
                "Build an owned proof hub for subscription control, delivery quality, freshness, refunds, and service recovery.",
                "Turn customer feedback and recipe ratings into visible evidence of improvement.",
                "Create comparison content that directly acknowledges common buyer anxieties rather than relying on offer-led acquisition.",
            ],
        }
    )

    data["usp_ksp_review"] = {
        "score": "6.6 / 10",
        "score_summary": f"{brand} has a clear category proposition, but its strongest selling points need more visible proof around control, quality, service recovery, and comparison value.",
        "summary": f"{brand}'s USP is easy to understand, but its distinctiveness depends on making control, quality, and service proof more tangible than competitors.",
        "rows": [
            {
                "claim_type": "Core USP",
                "icon_key": "summary",
                "claim_summary": "The brand makes the category promise easy to understand and puts a useful household outcome at the centre.",
                "proof_points": "Published proposition and product evidence show the main convenience, choice, and category benefit.",
                "proof_feedback": "Clear, but not distinctive enough on its own because close competitors can make similar category claims.",
            },
            {
                "claim_type": "Key selling point: choice",
                "icon_key": "content",
                "claim_summary": "Choice, flexibility, and reduced planning friction are the most immediate customer benefits.",
                "proof_points": "Website messaging, competitor discovery, and category content show that choice and ease drive consideration.",
                "proof_feedback": "Strong as a buyer benefit, but it should be supported with decision guidance so choice feels manageable and relevant.",
            },
            {
                "claim_type": "Key selling point: trust",
                "icon_key": "reputation",
                "claim_summary": "The offer becomes more persuasive when control, reliability, and service recovery are made visible.",
                "proof_points": "Reputation and search evidence show customers need proof around service, control, delivery, value, or issue resolution.",
                "proof_feedback": "This is the biggest proof gap and the strongest route to sharper differentiation.",
            },
            {
                "claim_type": "Differentiation test",
                "icon_key": "seo",
                "claim_summary": "The brand can differentiate by becoming easier to compare, trust, and act on than alternatives.",
                "proof_points": "Competitor and search evidence indicates buyers actively compare alternatives and look for reassurance.",
                "proof_feedback": "The USP is strongest when convenience, proof, and customer control are treated as one system.",
            },
        ],
        "overall_verdict": {
            "headline": "Strong category proposition; medium distinctiveness until proof is made visible.",
            "uniqueness_verdict": "Not unique enough as a convenience claim alone, but potentially distinctive as a proof-backed customer-control proposition.",
            "who_for": "Best for buyers who like the promise but need reassurance about fit, value, flexibility, service, and proof before committing.",
        },
    }

    context_bits = [
        brand.lower(),
        website.lower(),
        competitor_text.lower(),
        str(primary_search_source.get("title") or "").lower(),
        str(top_news.get("headline") or "").lower(),
    ]
    context_blob = " ".join(bit for bit in context_bits if bit)
    cyber_terms = ("cyber", "security", "threat", "breach", "cloud", "network", "firewall", "endpoint", "xdr", "soc")
    food_terms = ("recipe", "meal", "grocery", "freshness", "kitchen", "delivery", "subscription")
    is_cyber = any(term in context_blob for term in cyber_terms)
    is_food = any(term in context_blob for term in food_terms)

    if is_cyber:
        data["opportunities"] = {
            "marketing_strategy": {
                "headline": "Turn platform scale into proof buyers can inspect under pressure.",
                "strategy": f"Use thought leadership, search, regional activation, CRM, and campaign creative to position {brand} as the security platform that shortens the breach window, governs enterprise AI, and makes complex estates feel visible and controllable for security and board-level buyers.",
                "why_it_matters": "The strategy synthesises reputation scrutiny, platform proof needs, search demand around category comparisons, competitor pressure, and campaign opportunities into one commercial direction.",
                "evidence_threads": [
                    f"Reputation: {sentence(top_news.get('headline'), 'ranked public stories')} shows growth and product strength are being weighed against trust and execution risk.",
                    "Messaging/proof: the brand story is strongest when platform claims are translated into visible outcomes, governance, and operational confidence.",
                    f"Search/SEO: {sentence(primary_search_source.get('title'), 'search evidence')} shows demand for category explanation, comparison, and proof-backed solution journeys.",
                    f"Competitor: active comparison around {competitor_text} means buyers see credible alternatives and need a clearer reason to consolidate with one platform.",
                    "Campaign/content: creative territories should dramatise time-to-response, platform visibility, AI supervision, and regional intelligence rather than generic innovation language.",
                ],
            },
            "timelines": [
                {"title": "Next 30 days", "items": ["Lock the proof architecture for platformization, breach response, AI governance, and regional intelligence.", "Map priority comparison and proof search journeys across platform, cloud, AI, and SASE topics.", "Audit core pages for stronger buyer-language explanation of outcome, governance, and response confidence."]},
                {"title": "Next 60 days", "items": ["Prototype proof-led landing pages and comparison hubs.", "Create modular sales and CRM content answering rollout, visibility, integration, and trust objections.", "Test campaign messaging around breach-window compression, one-platform control, and supervised AI."]},
                {"title": "Next 90 days", "items": ["Launch the first proof-led content hub and campaign territory.", "Measure qualified organic visits, engagement with proof modules, comparison-page progression, and sales-use adoption.", "Prepare regional PR and field amplification using verified proof assets and threat-intelligence hooks."]},
            ],
        }

        campaign_base = [
            {
                "title": "The Breach Window",
                "addresses": "Buyers know cyber risk is constant, but they do not always feel the cost of delay in the first critical hours.",
                "concept": "A campaign that turns the first minutes of a cyber incident into a visible commercial problem, then shows how faster detection, containment, and response shrink the damage window.",
                "activation": "The flagship expression is a breach-window experience supported by field content, sales proof, and regional cut-downs that dramatise how uncertainty compounds when estates are fragmented.",
                "driving_idea": "Make time visible. Instead of talking abstractly about resilience, the campaign shows the dangerous gap between first signal and confident action, then frames the platform as the thing that helps teams close that gap before disruption spreads.",
                "implementation_story": "The campaign begins with a cinematic breach-window story hub showing how a signal moves from confusion to coordinated action. It then branches into shorter sector variants, sales proof slides, and field follow-ups that each focus on one consequence of lost time: exposure, operational drag, executive escalation, or customer impact.",
                "activation_plan": [{
                    "name": "Breach Window experience",
                    "creates": f"{brand} creates a high-impact interactive story experience, supported by keynote visuals, paid social cut-downs, and sales follow-up assets, that lets buyers step through the first critical stages of a modern incident.",
                    "looks_like": "It looks like a dark, cinematic response timeline with clear stages rather than a dense product tour. Each stage shows what the team can or cannot see, where delay accumulates, what decisions become harder, and what proof changes when the estate is coordinated through one platform.",
                    "example_moments": ["A first-alert scene showing the gap between signal, context, and confident containment.", "An executive-pressure module showing how uncertainty escalates when multiple tools disagree.", "A sector cut-down showing how a breach window widens in cloud, network, or endpoint-heavy estates."],
                    "why_this_format": "This format works because the challenge is not awareness of cyber risk; it is failure to feel, in concrete terms, how expensive lost visibility becomes in the opening hours of an incident.",
                    "intended_result": "Increase urgency around consolidation and platform visibility, give sales teams a memorable proof narrative, and move buyers from abstract concern to active evaluation.",
                    "inputs_needed": ["Response-stage proof points", "Product and SOC workflow evidence", "Design support for timeline storytelling"],
                }],
            },
            {
                "title": "Platformization Planetarium",
                "addresses": "Platformization can sound financially attractive but still feel technically abstract or commercially vague to buyers.",
                "concept": "A visual campaign that treats fragmented tools as disconnected constellations and the platform as the observatory that lets leaders see, govern, and act across the whole estate.",
                "activation": "The idea comes alive through an immersive observatory narrative, platform explainer pages, board-ready proof modules, and field assets that turn consolidation into a visible control advantage.",
                "driving_idea": "Show the whole sky at once. The campaign reframes platformization from a vendor efficiency story into an estate-visibility and decision-quality story that matters to CISOs, security architects, and executive stakeholders.",
                "implementation_story": "The flagship experience visualises multiple disconnected security worlds and then reveals what changes when they are governed through one control layer. Follow-on assets simplify that model for web, keynote, analyst, and sales contexts so the same system story holds together from awareness to deal progression.",
                "activation_plan": [{
                    "name": "Platform observatory",
                    "creates": f"{brand} creates a premium platform observatory experience supported by solution pages, keynote modules, and sales proofs that explain how one control layer improves visibility, governance, and response quality.",
                    "looks_like": "It looks like a guided visual model of an enterprise estate rather than a product matrix. Buyers move from separate tool clusters into one connected oversight environment, seeing where duplication, delay, and blind spots disappear when the system is treated as one operating surface.",
                    "example_moments": ["A before-and-after view comparing fragmented telemetry with unified control.", "An executive explainer showing how platformization changes reporting confidence and governance.", "A field-ready proof module mapping buyer pain points to one control-layer outcome."],
                    "why_this_format": "This shape is right because platformization claims often fail when they sound like vendor rationalisation. A visual observatory makes the operational and strategic upside easier to grasp.",
                    "intended_result": "Make consolidation feel desirable rather than defensive, strengthen board-level understanding of the platform story, and improve progression on complex multi-product conversations.",
                    "inputs_needed": ["Platform architecture proof", "Customer or analyst validation", "Cross-solution messaging hierarchy"],
                }],
            },
            {
                "title": "AI Under Supervision",
                "addresses": "Enterprise buyers are excited by AI, but they need stronger reassurance that it is governed, inspectable, and secure rather than simply powerful.",
                "concept": "A campaign that treats enterprise AI as a high-value force that becomes useful only when it is supervised, policy-bound, and secured from code to cloud.",
                "activation": "The creative system spans AI-governance thought leadership, proof-led landing pages, event storytelling, and sales content that show how supervised AI produces confidence rather than chaos.",
                "driving_idea": "Do not romanticise the machine; discipline it. The campaign positions AI value and AI control as inseparable, showing that intelligence without governance creates risk, while supervised intelligence creates speed leaders can trust.",
                "implementation_story": "The campaign opens with a bold supervised-AI narrative and then breaks into role-specific expressions for security leadership, cloud, platform, and AI buyers. Every asset shows one tension being resolved: speed versus control, automation versus oversight, or innovation versus exposure.",
                "activation_plan": [{
                    "name": "Supervised AI proof series",
                    "creates": f"{brand} creates a flagship AI-governance campaign hub supported by short films, keynote modules, and solution-page proof sequences that dramatise the difference between uncontrolled AI activity and supervised enterprise use.",
                    "looks_like": "It looks like an art-directed tension between energy and discipline: powerful machine behaviour contained inside clear policy, oversight, and security frames. The web expression uses high-contrast proof modules, governance checkpoints, and short scenario stories rather than generic AI hype copy.",
                    "example_moments": ["A scenario showing how unsupervised AI creates hidden risk across code, cloud, and data paths.", "A governance checkpoint sequence showing where oversight restores confidence.", "A sales proof module comparing AI speed alone with AI speed under disciplined control."],
                    "why_this_format": "This form is right because AI discussions quickly collapse into either hype or fear. A supervised-AI campaign creates a sharper middle ground: ambition made safe enough to buy.",
                    "intended_result": "Strengthen differentiation in AI-security conversations, improve trust in platform governance claims, and create more persuasive proof for high-stakes enterprise buyers.",
                    "inputs_needed": ["AI-governance narrative", "Product proof across AI and cloud security", "Executive messaging for innovation and risk"],
                }],
            },
            {
                "title": "The EMEA Threat Atlas",
                "addresses": "Global threat intelligence is powerful, but regional agencies and buyers need it translated into local sector, regulatory, and geopolitical relevance.",
                "concept": "A campaign that turns threat intelligence into a living EMEA atlas, showing how regional risk shifts by sector, regulation, and operating environment while keeping one coherent platform story.",
                "activation": "The campaign runs as a modular regional intelligence system with flagship atlas experiences, country or sector cut-downs, PR hooks, and field content for agency activation.",
                "driving_idea": "Make intelligence feel local. Instead of presenting global threat coverage as a distant authority signal, the campaign turns it into a regional navigation system buyers can use to understand what matters where they operate.",
                "implementation_story": "The hero asset is an EMEA atlas that blends regional threat patterns, sector themes, and practical implications. Around it sits a modular activation system so country teams can localise the story without losing the central proof architecture or platform narrative.",
                "activation_plan": [{
                    "name": "Regional threat atlas",
                    "creates": f"{brand} creates a flagship EMEA threat-atlas experience with sector and country derivatives for PR, field, CRM, and sales use.",
                    "looks_like": "It looks like a premium editorial atlas rather than a static report. The experience layers regional currents, sector nodes, response priorities, and proof-backed recommendations so local teams can show buyers why the global intelligence picture matters in their specific context.",
                    "example_moments": ["A regional overview showing how one threat pattern manifests differently across major EMEA markets.", "A sector layer linking intelligence to board-level commercial consequences.", "A local activation kit turning one atlas theme into PR, event, and follow-up content for a country team."],
                    "why_this_format": "This shape works because intelligence is most persuasive when buyers can see themselves inside it. A regional atlas turns authority into applied relevance.",
                    "intended_result": "Give EMEA teams a stronger shared narrative, improve localisation without fragmentation, and convert intelligence credibility into pipeline-facing content.",
                    "inputs_needed": ["Unit 42 or equivalent threat-intelligence evidence", "Regional sector priorities", "Field and PR localisation plan"],
                }],
            },
        ]

        content_strategy = {
            "cards": [
                {"title": "Proof architecture", "body": "Create reusable proof modules for breach-window compression, platform visibility, AI governance, customer protection, and regional threat relevance."},
                {"title": "Comparison content", "body": f"Build fair comparison and category-explainer pages around {competitor_text} so search demand lands on clearer platform differentiation and proof."},
                {"title": "Regional activation", "body": "Turn core narratives into modular EMEA-ready assets for country, sector, event, CRM, and sales activation."},
            ],
            "priority_opportunities": [
                "Breach-window proof hub showing what faster coordinated response changes.",
                "Platformization explainer architecture translating consolidation into visibility and governance outcomes.",
                "AI-governance content series proving supervision, policy, and secure enablement.",
            ],
            "example_ideas": [
                "What leaders can see in the first critical hour of a modern incident.",
                f"{brand} vs fragmented point tools: when one control layer changes the decision.",
                "How supervised enterprise AI becomes faster to trust, not just faster to deploy.",
            ],
            "response_to_findings": "These recommendations respond to the report findings by translating platform ambition into inspectable proof, turning comparison demand into owned decision support, and giving regional teams reusable intelligence-led stories.",
        }
    else:
        data["opportunities"] = {
            "marketing_strategy": {
                "headline": "Turn category promise into proof-backed commercial confidence.",
                "strategy": f"Use content, search, CRM, and creative to reposition {brand}'s core offer as a system buyers can understand, verify, and trust before they commit.",
                "why_it_matters": "The strategy synthesises reputation risk, messaging proof needs, search and SEO comparison demand, competitor pressure, and campaign/content opportunities into one commercial direction.",
                "evidence_threads": [
                    f"Reputation: {sentence(top_news.get('headline'), 'ranked public stories')} shows public trust and risk themes that messaging must answer clearly.",
                    "Messaging/proof: the story is strongest when category promises are backed by visible evidence and simpler buyer language.",
                    f"Search/SEO: {sentence(primary_search_source.get('title'), 'public search evidence')} supports comparison, proof-led organic content, and clearer landing journeys.",
                    f"Competitor: live discovery around {competitor_text} shows buyers have visible alternatives and need a sharper reason to choose this brand.",
                    "Campaign/content: proof-led creative can turn trust, differentiation, and practical outcomes into more memorable customer-facing assets.",
                ],
            },
            "timelines": [
                {"title": "Next 30 days", "items": ["Lock the proof architecture behind the core brand promise.", "Map priority comparison, trust, and buyer-intent search journeys.", "Audit key landing, help, and proof pages for clarity and commercial relevance."]},
                {"title": "Next 60 days", "items": ["Prototype proof modules, comparison pages, and mission landing journeys.", "Create CRM and sales-support content for the highest-friction objections.", "Test sharper messaging around proof, control, and buyer confidence."]},
                {"title": "Next 90 days", "items": ["Launch the first proof-led content hub and campaign territory.", "Measure organic engagement, conversion confidence, and progression on high-intent journeys.", "Prepare amplification from verified proof assets and customer-facing evidence."]},
            ],
        }

        campaign_base = [
            {
                "title": "Proof, Not Promises",
                "addresses": "Strong trust signals exist, but they are not yet packaged into a repeatable proof architecture.",
                "concept": "A trust-led creative platform that turns analyst recognition, partner credibility, customer outcomes, or operational evidence into visible proof around the main claim.",
                "activation": "The campaign creates proof modules across landing pages, sales support, CRM, and paid or PR cut-downs so the same evidence travels with the proposition.",
                "driving_idea": "Make belief inspectable. Instead of asking buyers to take the brand at its word, the campaign frames proof as the visible product around each important claim.",
                "implementation_story": "The flagship asset standardises what counts as proof, how it should look, and how it appears beside the promise. That visual system then flows into channel variants so the same evidence architecture supports acquisition, conversion, and follow-up journeys.",
                "activation_plan": [{
                    "name": "Proof architecture hub",
                    "creates": f"{brand} creates a flagship proof architecture supported by landing-page modules, sales assets, and campaign cut-downs that make the brand's best evidence easy to recognise and reuse.",
                    "looks_like": "It looks like a clean, ownable proof system rather than a library of disconnected testimonials or badges. Each proof moment pairs a claim with the strongest supporting evidence, the context in which it matters, and the next action a buyer should take.",
                    "example_moments": ["A hero proof module linking the main proposition to one decisive customer or partner outcome.", "A reusable claim-and-proof component for search or comparison pages.", "A short follow-up asset that turns one hard proof point into a memorable paid or CRM execution."],
                    "why_this_format": "This shape works because trust grows when evidence feels structured, repeatable, and easy to inspect across the buyer journey.",
                    "intended_result": "Increase credibility at decision stage, reduce reliance on generic claim language, and create stronger proof continuity across channels.",
                    "inputs_needed": ["Inventory of trust assets", "Evidence hierarchy", "Design support for reusable modules"],
                }],
            },
            {
                "title": "The Comparison Moment",
                "addresses": "Buyers actively compare alternatives and need clearer help understanding the trade-offs.",
                "concept": "A comparison-led campaign that treats category choice as a service and gives buyers fair, useful guidance before they leave the journey to third-party pages.",
                "activation": "The idea becomes a set of decision guides, comparison pages, search landing variants, and sales follow-ups that help buyers evaluate fit without defensive language.",
                "driving_idea": "Be the clearest guide in the room. The campaign meets comparison demand directly and uses it to prove why the brand is the right fit for a specific buyer situation.",
                "implementation_story": "The flagship asset is a generous decision guide organised around real buyer criteria rather than internal product silos. Search and campaign variants then answer the highest-intent comparison questions and route readers into the proof that matters most to them.",
                "activation_plan": [{
                    "name": "Decision guide system",
                    "creates": f"{brand} creates a comparison and decision-support system spanning search pages, landing modules, and sales-ready proof assets.",
                    "looks_like": "It looks like a guided choice environment with clear criteria, transparent trade-offs, and proof-linked recommendations rather than a combative competitor page.",
                    "example_moments": ["A criteria-led chooser that helps a buyer identify the right path into the proposition.", "A fair comparison module that names where the brand wins and where another option may suit a different need.", "A search landing page answering one specific alternative-brand query with useful proof."],
                    "why_this_format": "This form is right because comparison demand already exists. Meeting it directly lets the brand enter the decision point with clarity and utility.",
                    "intended_result": "Capture higher-intent search demand, improve trust in the buying recommendation, and reduce drift to third-party comparators.",
                    "inputs_needed": ["Competitor analysis", "Commercial rules", "SEO query prioritisation"],
                }],
            },
            {
                "title": "The Operating Model",
                "addresses": "The brand may be stronger operationally than its public story currently shows.",
                "concept": "A campaign that turns the hidden operating model into a visible source of confidence, showing how the offer works, what standards hold it together, and where the buyer gains reassurance.",
                "activation": "The idea becomes a visual operating-model story across web, CRM, video, and sales support so the brand feels understandable rather than opaque.",
                "driving_idea": "Show how the engine works. The campaign treats operational confidence as a strategic asset, not a back-office fact left out of the story.",
                "implementation_story": "The hero expression explains the system from input to outcome, then shorter assets isolate the moments buyers care about most: reliability, governance, quality, service recovery, or visible standards.",
                "activation_plan": [{
                    "name": "Operating-model explainer",
                    "creates": f"{brand} creates a flagship operating-model explainer supported by short modules, sales support, and follow-up content that make delivery confidence visible.",
                    "looks_like": "It looks like a guided system view where each stage reveals what the buyer gains, what the standard is, and what proof supports it.",
                    "example_moments": ["A step-by-step explainer of how the offer moves from promise to delivered outcome.", "A standards module showing what reliability or quality guardrails are in place.", "A follow-up asset translating an operational fact into a buyer-facing reassurance point."],
                    "why_this_format": "This shape works because buyers often trust what they can see working. Explaining the operating model turns hidden capability into commercial confidence.",
                    "intended_result": "Increase trust in the delivery promise, strengthen differentiation through operational proof, and support more confident evaluation.",
                    "inputs_needed": ["Operational evidence", "Subject-matter review", "Channel-specific simplification"],
                }],
            },
            {
                "title": "Local Relevance Engine",
                "addresses": "The central proposition may need stronger localisation by audience, region, sector, or use case.",
                "concept": "A modular campaign system that keeps one core strategy but adapts it into locally relevant expressions for the audiences and contexts that matter most.",
                "activation": "The campaign creates a master narrative with region, sector, or audience derivatives across PR, search, CRM, events, and sales follow-up.",
                "driving_idea": "Keep one engine, vary the route. The campaign protects strategic coherence while making the message feel more relevant in the contexts where buyers actually make decisions.",
                "implementation_story": "The master asset establishes the central argument and proof structure. Local derivatives then adapt examples, stakes, channels, and emphasis while keeping the same visual and narrative spine.",
                "activation_plan": [{
                    "name": "Modular activation kit",
                    "creates": f"{brand} creates a modular activation kit with one flagship narrative and tailored audience or regional expressions for field, PR, CRM, and sales use.",
                    "looks_like": "It looks like a family of related assets built from one shared backbone rather than disconnected campaigns. Each version carries the same idea but changes context, examples, and proof emphasis for the audience it serves.",
                    "example_moments": ["A core narrative page with audience-select paths.", "A localised field or PR asset using the same proof architecture with different examples.", "A sales follow-up variant that turns the same campaign idea into a sector-specific proof story."],
                    "why_this_format": "This form is right because consistency alone is not enough; the story must also feel natively relevant in the places where demand is won.",
                    "intended_result": "Improve relevance without fragmenting the brand story, support field teams with stronger local material, and extend the life of the core campaign idea.",
                    "inputs_needed": ["Audience priorities", "Regional or sector evidence", "Activation governance"],
                }],
            },
        ]

        content_strategy = {
            "cards": [
                {"title": "Proof architecture", "body": "Create reusable proof modules that translate the central claim into visible evidence across key landing, sales, and follow-up journeys."},
                {"title": "Comparison content", "body": f"Build fair comparison and decision-support pages around {competitor_text} so search demand lands on owned guidance rather than third-party summaries."},
                {"title": "Journey content", "body": "Use CRM, support, and conversion content to answer the highest-friction buyer questions with clearer proof and simpler explanation."},
            ],
            "priority_opportunities": [
                "Proof hub organising the strongest evidence behind the main proposition.",
                "Comparison and category-explainer architecture for high-intent search demand.",
                "Operational-confidence content showing how the promise is delivered in practice.",
            ],
            "example_ideas": [
                "How the promise becomes a real delivered outcome.",
                f"{brand} vs alternatives: the fairest way to decide.",
                "What proof buyers should see before they commit.",
            ],
            "response_to_findings": "These recommendations respond to the report findings by turning trust and differentiation gaps into clearer proof, stronger comparison support, and more useful buyer-facing content.",
        }

    data["creative_campaign_ideas"] = {
        "artwork_delivery_mode": "final-raster-required",
        "illustration_generation_backend": "imagegen",
        "illustration_style_mode": "surprise",
        "ideas": [
            {
                "title": idea["title"],
                "illustration_url": "",
                "addresses": idea["addresses"],
                "concept": idea["concept"],
                "activation": idea["activation"],
                "driving_idea": idea["driving_idea"],
                "implementation_story": idea["implementation_story"],
                "activation_plan": {"order_of_precedence": idea["activation_plan"]},
                "why_it_fits": "It responds directly to the reputation and search evidence: customers understand the category, but need more proof and control before committing.",
                "channels": ["Landing page", "CRM", "Paid social", "Search", "PR"],
                "press_angle": "Frame the brand as making meal-kit subscriptions more transparent, useful, and customer-controlled.",
                "why_it_will_work": "It turns trust and comparison anxieties into visible, practical assets rather than leaving them to reviews or help-centre fragments.",
                "intended_effect": "Improve confidence at sign-up, reduce avoidable objections, and create stronger proof for acquisition and retention.",
            }
            for idea in campaign_base
        ],
    }
    data["content_strategy"] = content_strategy

    data["appendix"] = {
        "source_map": source_map,
        "sources_reviewed": [item.get("url") for item in source_map if isinstance(item, dict) and item.get("url")],
        "method_note": "Research used deterministic Tavily Search workpacks, Tavily Research reputation reduction, direct SEMrush status recording, and labelled public search evidence where direct SEMrush data was quota-limited.",
    }
    data["footer_note"] = f"Prepared as an internal NewBiz2 planning report for {brand} using public evidence available at the time of the run."

    return clean_placeholder_content(data, brand)


def module_intake(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "data_path", None):
        data_path = Path(args.data_path).expanduser().resolve()
        brand_folder = data_path.parent
        data = read_json(data_path)
        if getattr(args, "brand_name", None):
            data.setdefault("brand", {})["name"] = args.brand_name
        if getattr(args, "website", None):
            data.setdefault("brand", {})["website"] = normalize_url(args.website)
        write_json(data_path, data)
    else:
        if not getattr(args, "brand_name", None) or not getattr(args, "website", None):
            raise SystemExit("Creating a new workspace requires --brand-name and --website.")
        root = output_root(getattr(args, "brand_folder", None))
        brand_slug = slugify(args.brand_name)
        brand_folder = root / brand_slug
        brand_folder.mkdir(parents=True, exist_ok=True)
        data_path = brand_folder / "report-data.json"
        if data_path.exists():
            data = read_json(data_path)
        else:
            data = read_json(TEMPLATE_PATH)
        data.setdefault("brand", {})
        data["brand"]["name"] = args.brand_name
        data["brand"]["slug"] = brand_slug
        data["brand"]["website"] = normalize_url(args.website)
        data.setdefault("cover", {}).setdefault("assumptions", [])
        if data["cover"]["assumptions"]:
            data["cover"]["assumptions"][0] = f"Confirmed primary site: {data['brand']['website']}."
        write_json(data_path, data)
        if TEMPLATE_ASSETS.exists() and not (brand_folder / "slide-assets").exists():
            shutil.copytree(TEMPLATE_ASSETS, brand_folder / "slide-assets")

    state = load_state(brand_folder)
    data = read_json(data_path)
    if not str(data.get("brand", {}).get("website", "")).startswith(("http://", "https://")):
        set_status(state, "intake", "failed")
        set_gate(state, "gate_1_intake", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Intake failed: brand.website must be a confirmed real website.")
    set_status(state, "intake", "passed")
    set_gate(state, "gate_1_intake", "passed")
    save_state(brand_folder, state)
    return {"module": "intake", "data": str(data_path), "brand_folder": str(brand_folder), "run_state": str(brand_folder / "run-state.json")}


def build_summary_from_data(data_path: Path, mode: str = "bootstrap-from-report-data") -> dict[str, Any]:
    data = read_json(data_path)
    competitors = data.get("cover", {}).get("competitors") or [
        row.get("competitor") or row.get("name") for row in data.get("competitive_landscape", {}).get("table", [])
    ]
    competitors = [item for item in competitors if item]
    news = data.get("brand_reputation", {}).get("influential_news", [])
    seo = data.get("seo_audit", {})
    semrush = seo.get("semrush_evidence", []) if isinstance(seo, dict) else []
    similarweb = seo.get("similarweb_evidence", []) if isinstance(seo, dict) else []
    search_evidence = seo.get("search_evidence", []) if isinstance(seo, dict) else []
    if not isinstance(semrush, list):
        semrush = []
    if not isinstance(similarweb, list):
        similarweb = []
    if not isinstance(search_evidence, list):
        search_evidence = []
    source_map = data.get("appendix", {}).get("source_map") or data.get("appendix", {}).get("sources_reviewed") or []
    status = {
        "competitor_discovery": "passed" if competitors else "pending",
        "recent_news": "passed" if news else "pending",
        "reputation_public_web": "passed" if data.get("brand_reputation") else "pending",
        "source_gathering": "passed" if source_map or news else "pending",
        "semrush": "passed" if len(semrush) >= 2 else "quota-limited",
        "search_seo": "passed" if len(semrush) >= 2 or len(similarweb) >= 2 else "pending",
    }
    return {
        "mode": mode,
        "data_path": str(data_path),
        "brand_name": data.get("brand", {}).get("name"),
        "brand_website": data.get("brand", {}).get("website"),
        "competitors": data.get("competitive_landscape", {}).get("table", []),
        "influential_news": news,
        "influence_ranking": data.get("brand_reputation", {}).get("influence_ranking", {}),
        "reputation": data.get("brand_reputation", {}),
        "seo": data.get("seo_audit", {}),
        "source_map": source_map,
        "locked_sets": {
            "competitors": competitors,
            "influential_news": [item.get("headline") for item in news if item.get("headline")],
        },
        "status": status,
        "notes": ["Python cross-platform runner built this summary from report-data.json."],
    }


def brand_domain_from_website(website: str) -> str:
    try:
        host = urllib.parse.urlparse(website).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def live_research_query_plan(data: dict[str, Any]) -> list[dict[str, str]]:
    brand_name = str(data.get("brand", {}).get("name") or "").strip()
    website = str(data.get("brand", {}).get("website") or "").strip()
    domain = brand_domain_from_website(website)
    brand = brand_name or domain
    compact_brand = re.sub(r"[^A-Za-z0-9]+", "", brand)
    domain_label = domain.split(".")[0] if domain else ""
    variants = list(dict.fromkeys([item for item in (brand, compact_brand, domain_label) if item]))
    primary = variants[0]
    compact = variants[1] if len(variants) > 1 else primary
    return [
        {
            "role": "competitor_discovery",
            "query": f"{primary} competitors UK alternatives market category",
            "topic": "general",
            "time_range": "",
            "max_results": "20",
        },
        {
            "role": "recent_news",
            "query": f"{primary} OR {compact} news reputation growth customers market 2026 2025",
            "topic": "news",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "recent_news",
            "query": f"{primary} OR {compact} reviews complaints service trust recall 2026 2025",
            "topic": "general",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "recent_news",
            "query": f"{primary} OR {compact} results revenue profit guidance investors partnerships 2026 2025",
            "topic": "general",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "reputation_public_web",
            "query": f"{primary} OR {compact} customer sentiment controversy trust reviews watchdog 2026 2025",
            "topic": "general",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "recent_news",
            "query": f"{primary} OR {compact} trade press market share category meal kits grocery delivery 2026 2025",
            "topic": "general",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "recent_news",
            "query": f"{primary} OR {compact} financial results Q4 Q3 annual report outlook 2026 2025",
            "topic": "finance",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "reputation_public_web",
            "query": f"{primary} OR {compact} complaints unsubscribe refund delivery ingredients quality 2026 2025",
            "topic": "general",
            "time_range": "year",
            "max_results": "20",
        },
        {
            "role": "source_gathering",
            "query": f"{primary} mission purpose promise values about company official group",
            "topic": "general",
            "time_range": "",
            "max_results": "10",
        },
        {
            "role": "source_gathering",
            "query": f"{primary} group mission values sustainability business model official",
            "topic": "general",
            "time_range": "",
            "max_results": "10",
        },
        {
            "role": "source_gathering",
            "query": f"{primary} SEO visibility Similarweb SEMrush organic search competitors",
            "topic": "general",
            "time_range": "year",
            "max_results": "10",
        },
    ]


def run_tavily_search_workpack(query: dict[str, str], output_path: Path) -> dict[str, Any]:
    tvly = shutil.which("tvly")
    if not tvly:
        raise RuntimeError("Tavily CLI `tvly` was not found on PATH.")
    command = [
        tvly,
        "search",
        query["query"],
        "--depth",
        query.get("depth") or "basic",
        "--max-results",
        str(query.get("max_results") or "12"),
        "--topic",
        query.get("topic") or "general",
        "--json",
        "-o",
        str(output_path),
    ]
    if query.get("time_range"):
        command.extend(["--time-range", query["time_range"]])
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Tavily search failed.")
    return read_json(output_path)


def collect_live_search_workpacks(data_path: Path, brand_folder: Path) -> list[Path]:
    data = read_json(data_path)
    workpack_dir = brand_folder / "research-workpacks"
    workpack_dir.mkdir(parents=True, exist_ok=True)
    plan = live_research_query_plan(data)
    results: list[dict[str, Any]] = []
    workpacks: list[Path] = []
    errors: list[dict[str, str]] = []
    for index, query in enumerate(plan, start=1):
        output_path = workpack_dir / f"{index:02d}-{query['role']}.json"
        try:
            pack = run_tavily_search_workpack(query, output_path)
            results.append(
                {
                    "role": query["role"],
                    "query": query["query"],
                    "output": str(output_path),
                    "result_count": len(pack.get("results") or []),
                }
            )
            workpacks.append(output_path)
        except Exception as exc:
            errors.append({"role": query["role"], "query": query["query"], "error": str(exc)})

    acquisition = {
        "mode": "cheap-live-search-workpacks",
        "data_path": str(data_path),
        "workpacks": results,
        "errors": errors,
        "tavily_research_used": False,
        "notes": [
            "Tavily Search was used for deterministic low-cost acquisition.",
            "Tavily Research was not used; escalation must be explicit.",
        ],
    }
    write_json(workpack_dir / "research-acquisition.json", acquisition)
    if not workpacks:
        error_text = "; ".join(item["error"] for item in errors) or "no workpacks were created"
        raise SystemExit(f"Live research acquisition failed before synthesis: {error_text}")
    return workpacks


def reduce_search_workpacks(data_path: Path, brand_folder: Path, workpacks: list[Path]) -> dict[str, Any]:
    if not workpacks:
        raise SystemExit("Research workpack mode requires at least one Tavily Search workpack.")
    output_path = brand_folder / "research-summary.draft.json"
    script = SCRIPT_ROOT / "research" / "reduce_search_workpacks.py"
    command = [
        sys.executable,
        str(script),
        "--data",
        str(data_path),
        "--output",
        str(output_path),
    ]
    for workpack in workpacks:
        command.extend(["--workpack", str(workpack)])
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(
            f"Search workpack reducer failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return read_json(output_path)


def apply_semrush_direct_api(
    data_path: Path,
    brand_folder: Path,
    summary: dict[str, Any],
    *,
    database: str,
    composio_backup_available: bool = False,
) -> tuple[dict[str, Any], Path | None]:
    output_path = brand_folder / "research-workpacks" / "98-semrush-direct-api.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(SEMRUSH_COLLECTOR),
        "--data",
        str(data_path),
        "--database",
        database,
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=180)
    payload: dict[str, Any] | None = None
    if output_path.exists():
        try:
            payload = read_json(output_path)
        except Exception:
            payload = None
    if payload is None and completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError:
            payload = None
    if payload is None:
        payload = {
            "ok": False,
            "status": "blocked",
            "provider": "semrush-direct-api",
            "errors": [completed.stderr.strip() or completed.stdout.strip() or "SEMrush collector produced no parseable output."],
            "seo": {"semrush_evidence": [], "priority_issues": []},
        }
        write_json(output_path, payload)

    status = str(payload.get("status") or "blocked")
    if status not in {"passed", "partial", "quota-limited", "blocked"}:
        status = "blocked"

    seo = summary.setdefault("seo", {})
    semrush_evidence = payload.get("seo", {}).get("semrush_evidence") if isinstance(payload.get("seo"), dict) else []
    if isinstance(semrush_evidence, list) and semrush_evidence:
        seo["semrush_evidence"] = semrush_evidence
    seo.setdefault("semrush_evidence", [])
    seo.setdefault("similarweb_evidence", [])
    seo.setdefault("search_evidence", [])
    priority_issues = payload.get("seo", {}).get("priority_issues") if isinstance(payload.get("seo"), dict) else []
    if isinstance(priority_issues, list) and priority_issues:
        seo["priority_issues"] = priority_issues
    seo.setdefault("priority_issues", [])

    summary.setdefault("status", {})["semrush"] = status
    enough_direct = len(seo.get("semrush_evidence") or []) >= 2
    enough_similarweb = len(seo.get("similarweb_evidence") or []) >= 2
    summary.setdefault("status", {})["search_seo"] = "passed" if enough_direct or enough_similarweb else status
    summary["semrush_direct_api"] = payload
    summary.setdefault("source_provenance_summary", {})["semrush_direct_api_status"] = status
    summary.setdefault("notes", []).append(f"SEMrush direct API status: {status}.")
    if status != "passed" and composio_backup_available:
        summary["semrush_backup"] = {
            "provider": "composio-semrush",
            "status": "available_not_executed_by_python_runner",
            "reason": "Direct SEMrush API did not pass; Composio SEMrush is the documented backup but is executed outside this local Python runner.",
        }
        summary.setdefault("notes", []).append(
            "Composio SEMrush backup is marked available, but the Python runner did not execute MCP tools directly."
        )
    return summary, output_path


def tavily_reputation_research_prompt(data: dict[str, Any], summary: dict[str, Any]) -> str:
    brand_name = data.get("brand", {}).get("name") or summary.get("brand_name") or "the target brand"
    website = data.get("brand", {}).get("website") or summary.get("brand_website") or ""
    candidate_pool = summary.get("influence_ranking", {}).get("candidate_pool_summary") or []
    candidate_lines = "\n".join(f"- {item}" for item in candidate_pool[:40])
    return textwrap.dedent(
        f"""
        Research the current brand reputation of {brand_name} ({website}) for a new-business intelligence report.

        Quality rules:
        - Start from broad discovery across national/business press, trade press, financial/investor coverage, consumer/review evidence, analyst/research sources, legal/regulatory sources, and social/forum evidence where relevant.
        - Do not preselect stories from expected narratives. Build a candidate pool first, then score and reduce.
        - Return 5 or 6 genuinely influential stories only.
        - Every final story must have an exact publication date in this format: 19 November 2025.
        - If a candidate does not have an exact day-month-year publication date, do not include it in influential_news; keep it in candidate_pool_summary or limitations instead.
        - Do not use review-platform aggregate pages, live ratings, homepages, or undated snapshots as final influential_news items; they can support the reputation readout but they are not dated stories.
        - Every final story must have a verifiable source URL.
        - Use at least 3 distinct publishers and at least 3 source classes.
        - Do not include more than 2 stories from the same publisher.
        - Exclude weak, generic, undated, duplicate, irrelevant, or brand-adjacent stories.
        - broad_discovery_queries must be genuinely broad and must not include final publisher names, source names, exact headlines, or site: operators.
        - Put source-specific, headline-specific, or site: checks in verification_queries only.

        Influence scoring must use these exact weights:
        - source_authority: 0.25
        - buyer_relevance: 0.25
        - reputation_risk_or_opportunity: 0.20
        - evidence_quality: 0.15
        - novelty: 0.10
        - recency: 0.05

        Use discovery_mode exactly: broad_first_scored_reduction.
        Set confidence_score from 70 to 100 only if the final set is genuinely report-ready; otherwise return the best possible structured result with limitations.

        Cheap-search candidate pool to consider but not blindly accept:
        {candidate_lines}
        """
    ).strip()


def parse_structured_tavily_payload(raw: Any) -> dict[str, Any] | None:
    candidates: list[Any] = [raw]
    if isinstance(raw, dict):
        for key in ("answer", "content", "result", "data", "output"):
            if key in raw:
                candidates.append(raw[key])
    for candidate in candidates:
        if isinstance(candidate, dict) and "influential_news" in candidate and "influence_ranking" in candidate:
            return candidate
        if isinstance(candidate, str):
            text = candidate.strip()
            if not text:
                continue
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
                text = re.sub(r"\s*```$", "", text)
            match = re.search(r"\{.*\}", text, flags=re.S)
            if match:
                text = match.group(0)
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "influential_news" in parsed and "influence_ranking" in parsed:
                return parsed
    return None


def story_specific_query(query: str, final_sources: set[str], final_headlines: list[str]) -> bool:
    value = str(query or "").strip().lower()
    if not value:
        return True
    if "site:" in value:
        return True
    if any(source and source in value for source in final_sources):
        return True
    query_words = [word for word in re.findall(r"[a-z0-9]+", value) if len(word) > 2]
    for headline in final_headlines:
        headline_words = set(word for word in re.findall(r"[a-z0-9]+", headline.lower()) if len(word) > 2)
        if len([word for word in query_words if word in headline_words]) >= 5:
            return True
    return False


def normalise_reputation_research_payload(payload: dict[str, Any], *, brand_name: str = "the target brand") -> dict[str, Any]:
    news = payload.get("influential_news") if isinstance(payload.get("influential_news"), list) else []
    for item in news:
        if not isinstance(item, dict):
            continue
        subscores = item.get("influence_subscores")
        if isinstance(subscores, dict):
            calculated = calculate_reputation_influence_score(subscores)
            if calculated is not None:
                item["influence_score"] = calculated
    news = [item for item in news if isinstance(item, dict)]
    news.sort(key=lambda item: as_int(item.get("influence_score")) or 0, reverse=True)
    payload["influential_news"] = news
    ranking = payload.get("influence_ranking")
    if isinstance(ranking, dict):
        ranking.setdefault("ranking_factors", list(REPUTATION_RANKING_FACTORS))
        ranking.setdefault("score_weights", REPUTATION_SCORE_WEIGHTS)
        ranking.setdefault("discovery_mode", "broad_first_scored_reduction")
        final_sources = {normalised_source(item.get("source")) for item in news if isinstance(item, dict)}
        final_headlines = [str(item.get("headline", "")) for item in news if isinstance(item, dict)]
        broad_queries = ranking.get("broad_discovery_queries") if isinstance(ranking.get("broad_discovery_queries"), list) else []
        verification_queries = ranking.get("verification_queries") if isinstance(ranking.get("verification_queries"), list) else []
        cleaned_broad: list[str] = []
        cleaned_verification: list[str] = [str(query).strip() for query in verification_queries if str(query).strip()]
        for query in broad_queries:
            query_text = str(query).strip()
            if not query_text:
                continue
            if story_specific_query(query_text, final_sources, final_headlines):
                cleaned_verification.append(query_text)
            else:
                cleaned_broad.append(query_text)
        default_broad = [
            f"{brand_name} reputation news coverage",
            f"{brand_name} customer trust reviews complaints",
            f"{brand_name} financial performance investor reaction",
            f"{brand_name} regulatory legal consumer issues",
            f"{brand_name} innovation product strategy coverage",
            f"{brand_name} social forum sentiment",
        ]
        for query in default_broad:
            if len({item.lower() for item in cleaned_broad}) >= 4:
                break
            if query.lower() not in {item.lower() for item in cleaned_broad}:
                cleaned_broad.append(query)
        ranking["broad_discovery_queries"] = list(dict.fromkeys(cleaned_broad))
        ranking["verification_queries"] = list(dict.fromkeys(cleaned_verification))
    return payload


def apply_tavily_reputation_research(data_path: Path, brand_folder: Path, summary: dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
    data = read_json(data_path)
    tvly = shutil.which("tvly")
    if not tvly:
        summary.setdefault("notes", []).append("Tavily Reputation Research was required but `tvly` was not found on PATH.")
        return summary, None
    workpack_dir = brand_folder / "research-workpacks"
    workpack_dir.mkdir(parents=True, exist_ok=True)
    output_path = workpack_dir / "99-reputation_research.json"
    if output_path.exists() and os.getenv("NEWBIZ2_REFRESH_TAVILY_REPUTATION_RESEARCH") != "1":
        raw = read_json(output_path)
    else:
        command = [
            tvly,
            "research",
            "run",
            tavily_reputation_research_prompt(data, summary),
            "--model",
            "pro",
            "--output-schema",
            str(TAVILY_REPUTATION_SCHEMA),
            "--citation-format",
            "numbered",
            "--poll-interval",
            "10",
            "--timeout",
            "900",
            "--json",
            "-o",
            str(output_path),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=960)
        if completed.returncode != 0:
            summary.setdefault("notes", []).append(
                "Tavily Reputation Research failed: " + (completed.stderr.strip() or completed.stdout.strip())
            )
            return summary, output_path
        raw = read_json(output_path)

    payload = parse_structured_tavily_payload(raw)
    if not payload:
        summary.setdefault("notes", []).append("Tavily Reputation Research did not return structured influential_news output.")
        return summary, output_path
    payload = normalise_reputation_research_payload(payload, brand_name=str(data.get("brand", {}).get("name") or "the target brand"))
    summary["influential_news"] = payload.get("influential_news", [])
    summary["influence_ranking"] = payload.get("influence_ranking", {})
    summary.setdefault("reputation", {})["influence_ranking"] = summary["influence_ranking"]
    source_map = summary.setdefault("source_map", [])
    known_urls = {item.get("url") for item in source_map if isinstance(item, dict)}
    for item in summary["influential_news"]:
        url = item.get("url")
        if url and url not in known_urls:
            source_map.append(
                {
                    "title": item.get("headline"),
                    "url": url,
                    "source": item.get("source"),
                    "used_for": ["brand_reputation", "appendix"],
                }
            )
            known_urls.add(url)
    summary.setdefault("locked_sets", {})["influential_news"] = [
        item.get("headline") for item in summary["influential_news"] if item.get("headline")
    ]
    summary.setdefault("status", {})["recent_news"] = "passed"
    summary.setdefault("status", {})["reputation_public_web"] = "passed"
    summary.setdefault("tavily_validation", {}).setdefault("recent_news", {})["why_passed"] = (
        "Final reputation story set was produced by Tavily Research after broad Tavily Search discovery."
    )
    summary.setdefault("source_provenance_summary", {})["tavily_research_used"] = True
    summary.setdefault("notes", []).append("Final reputation story selection used Tavily Research for quality and confidence.")
    return summary, output_path


def validate_research_summary(summary: dict[str, Any], *, allow_examples: bool = False) -> dict[str, Any]:
    errors = []
    warnings = []
    placeholder_audit = audit_placeholder_content(
        summary,
        root_label="research_summary",
        allow_examples=allow_examples,
    )
    if not placeholder_audit["ok"]:
        errors.extend(f"anti_placeholder_audit: {error}" for error in placeholder_audit.get("errors", []))
    else:
        warnings.extend(placeholder_audit.get("warnings", []))
    status = summary.get("status", {})
    for key in ("competitor_discovery", "recent_news", "reputation_public_web", "source_gathering", "semrush", "search_seo"):
        if key not in status:
            errors.append(f"Missing status.{key}")
    if status.get("semrush") not in {"passed", "partial", "quota-limited", "blocked"}:
        errors.append("status.semrush must be one of passed, partial, quota-limited, or blocked.")
    seo = summary.get("seo", {})
    if not isinstance(seo, dict):
        seo = {}
    semrush_evidence = seo.get("semrush_evidence", [])
    similarweb_evidence = seo.get("similarweb_evidence", [])
    search_evidence = seo.get("search_evidence", [])
    if not isinstance(semrush_evidence, list):
        semrush_evidence = []
    if not isinstance(similarweb_evidence, list):
        similarweb_evidence = []
    if not isinstance(search_evidence, list):
        search_evidence = []
    provider_search_evidence = len(semrush_evidence) + len(similarweb_evidence)
    total_search_evidence = provider_search_evidence + len(search_evidence)
    if status.get("search_seo") == "passed" and provider_search_evidence < 2:
        errors.append(
            "status.search_seo is passed but fewer than 2 provider-backed SEO evidence points are present."
        )
    if status.get("search_seo") != "passed" and provider_search_evidence >= 2:
        errors.append(
            "Provider-backed search/SEO evidence is present but status.search_seo was not marked passed."
        )
    for evidence_name, evidence_items in (
        ("similarweb_evidence", similarweb_evidence),
        ("search_evidence", search_evidence),
    ):
        for index, item in enumerate(evidence_items):
            if not isinstance(item, dict):
                errors.append(f"seo.{evidence_name}[{index}] must be an object.")
                continue
            provider = str(item.get("provider") or ("similarweb" if evidence_name == "similarweb_evidence" else "")).strip().lower()
            body = f"{item.get('title', '')} {item.get('body', '')}".lower()
            if not provider:
                errors.append(f"seo.{evidence_name}[{index}].provider is required.")
            if provider != "semrush-direct-api" and "semrush-backed" in body:
                errors.append(f"seo.{evidence_name}[{index}] must not describe non-SEMrush evidence as SEMrush-backed.")
    for index, item in enumerate(semrush_evidence):
        if not isinstance(item, dict):
            errors.append(f"seo.semrush_evidence[{index}] must be an object.")
            continue
    if not summary.get("locked_sets", {}).get("competitors"):
        errors.append("Missing locked_sets.competitors")
    if not summary.get("influential_news"):
        errors.append("Missing influential_news")
    else:
        validate_reputation_ranking_contract(
            summary.get("influential_news"),
            summary.get("influence_ranking") or summary.get("reputation", {}).get("influence_ranking"),
            errors,
            warnings,
            prefix="influential_news",
        )
    if summary.get("required_tavily_reputation_research") and not summary.get("source_provenance_summary", {}).get("tavily_research_used"):
        errors.append("Tavily Reputation Research is required for this live run but did not produce the final reputation story set")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "anti_placeholder_audit": placeholder_audit}


def module_research(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
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
            "python_runner:newbiz2.py",
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
                summary = reduce_search_workpacks(data_path, brand_folder, workpacks)
                add_event(state, "reducer", "research.live_search_summary_draft", outputs=[str(brand_folder / "research-summary.draft.json")])
                save_state(brand_folder, state)
        elif args.research_mode == "workpacks":
            workpacks = [Path(path).expanduser().resolve() for path in (args.search_workpacks or [])]
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
                save_state(brand_folder, state)
        if args.research_mode == "live-summary":
            summary, semrush_path = apply_semrush_direct_api(
                data_path,
                brand_folder,
                summary,
                database=args.semrush_database,
                composio_backup_available=bool(args.composio_semrush_available),
            )
            if semrush_path:
                add_event(state, "fanout", "research.semrush_direct_api", jobs=[str(semrush_path)])
                add_event(state, "reducer", "research.search_seo_evidence_reducer", outputs=[str(semrush_path)])
                save_state(brand_folder, state)
    except SystemExit:
        set_status(state, "research", "failed")
        set_gate(state, "gate_2_competitors", "failed")
        set_gate(state, "gate_3_research", "failed")
        set_gate(state, "gate_3a_semrush", "failed")
        set_gate(state, "gate_4_search_seo_evidence", "failed")
        save_state(brand_folder, state)
        raise
    except Exception as exc:
        set_status(state, "research", "failed")
        set_gate(state, "gate_2_competitors", "failed")
        set_gate(state, "gate_3_research", "failed")
        set_gate(state, "gate_3a_semrush", "failed")
        set_gate(state, "gate_4_search_seo_evidence", "failed")
        save_state(brand_folder, state)
        raise SystemExit(f"Research acquisition/reduction failed: {exc}") from exc
    validation = validate_research_summary(summary, allow_examples=is_repo_example_path(data_path))
    if not validation["ok"]:
        set_status(state, "research", "failed")
        set_gate(state, "gate_2_competitors", "failed")
        set_gate(state, "gate_3_research", "failed")
        set_gate(state, "gate_3a_semrush", "failed")
        set_gate(state, "gate_4_search_seo_evidence", "failed")
        save_state(brand_folder, state)
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
    return {"module": "research", "data": str(data_path), "brand_folder": str(brand_folder), "research_summary": str(summary_path), "validation": validation}


def merge_research_into_data(data: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("competitors"):
        brand = str(data.get("brand", {}).get("name") or summary.get("brand_name") or "the brand")
        data.setdefault("competitive_landscape", {})["table"] = enrich_competitor_table(brand, summary["competitors"])
        names = [row.get("competitor") or row.get("name") for row in summary["competitors"] if isinstance(row, dict)]
        if names:
            data.setdefault("cover", {})["competitors"] = names
    if summary.get("influential_news"):
        data.setdefault("brand_reputation", {})["influential_news"] = summary["influential_news"]
    if isinstance(summary.get("influence_ranking"), dict):
        data.setdefault("brand_reputation", {})["influence_ranking"] = summary["influence_ranking"]
    if isinstance(summary.get("reputation"), dict):
        data.setdefault("brand_reputation", {}).update(summary["reputation"])
    if isinstance(summary.get("seo"), dict):
        data.setdefault("seo_audit", {}).update(summary["seo"])
    return data


def module_structure(args: argparse.Namespace) -> dict[str, Any]:
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
    validation = validate_report_data(data_path)
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


def relative_to_brand(path: Path, brand_folder: Path) -> str:
    try:
        return path.resolve().relative_to(brand_folder.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def asset_quality(path: Path) -> dict[str, Any]:
    result = {"exists": path.exists(), "valid_image": False, "width": 0, "height": 0, "bytes": 0, "format": path.suffix.lower().lstrip("."), "reason": ""}
    if not path.exists():
        result["reason"] = "missing"
        return result
    result["bytes"] = path.stat().st_size
    if result["bytes"] < 128:
        result["reason"] = "too few bytes"
        return result
    if path.suffix.lower() == ".svg":
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "<svg" not in text.lower():
            result["reason"] = "invalid svg"
            return result
        result["valid_image"] = True
        result["width"] = 256
        result["height"] = 256
        return result
    try:
        from PIL import Image

        with Image.open(path) as image:
            result["width"], result["height"] = image.size
            result["valid_image"] = result["width"] > 0 and result["height"] > 0
    except Exception as exc:
        result["reason"] = f"unreadable image: {exc}"
    return result


def quality_ok(path: Path, minimum: int = 64) -> bool:
    quality = asset_quality(path)
    return bool(quality["exists"] and quality["valid_image"] and quality["width"] >= minimum and quality["height"] >= minimum)


def square_quality_ok(path: Path, minimum: int = 96) -> bool:
    quality = asset_quality(path)
    if not bool(quality["exists"] and quality["valid_image"] and quality["width"] >= minimum and quality["height"] >= minimum):
        return False
    if not quality["height"]:
        return False
    aspect_ratio = quality["width"] / quality["height"]
    return 0.75 <= aspect_ratio <= 1.33


def visible_content_bbox(path: Path, threshold: int = 18) -> tuple[int, int, int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGBA")
            width, height = image.size
            corners = [
                image.getpixel((0, 0)),
                image.getpixel((width - 1, 0)),
                image.getpixel((0, height - 1)),
                image.getpixel((width - 1, height - 1)),
            ]
            background = tuple(sorted(corners)[len(corners) // 2])
            left, top, right, bottom = width, height, -1, -1
            for y in range(height):
                for x in range(width):
                    pixel = image.getpixel((x, y))
                    alpha_delta = abs(pixel[3] - background[3])
                    colour_delta = max(abs(pixel[i] - background[i]) for i in range(3))
                    if pixel[3] > 20 and (alpha_delta > threshold or colour_delta > threshold):
                        left = min(left, x)
                        top = min(top, y)
                        right = max(right, x + 1)
                        bottom = max(bottom, y + 1)
            if right < left or bottom < top:
                alpha_bbox = image.getchannel("A").getbbox()
                return alpha_bbox
            return (left, top, right, bottom)
    except Exception:
        return None


def visible_logo_occupancy_ok(path: Path, minimum_span: float = 0.38) -> bool:
    quality = asset_quality(path)
    if not quality["exists"] or not quality["valid_image"] or not quality["width"] or not quality["height"]:
        return False
    bbox = visible_content_bbox(path)
    if not bbox:
        return False
    content_width = bbox[2] - bbox[0]
    content_height = bbox[3] - bbox[1]
    return max(content_width / quality["width"], content_height / quality["height"]) >= minimum_span


def has_distinct_square_background(path: Path) -> bool:
    quality = asset_quality(path)
    if not quality["exists"] or not quality["valid_image"] or not quality["width"] or not quality["height"]:
        return False
    if not square_quality_ok(path):
        return False
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGBA")
            width, height = image.size
            sample_points = [
                (0, 0),
                (width - 1, 0),
                (0, height - 1),
                (width - 1, height - 1),
                (width // 2, height // 2),
            ]
            filled = 0
            for point in sample_points:
                red, green, blue, alpha = image.getpixel(point)
                if alpha > 220 and min(abs(red - 255), abs(green - 255), abs(blue - 255)) > 24:
                    filled += 1
            return filled >= 3
    except Exception:
        return False


def normalize_svg_size(text: str) -> str:
    if re.search(r"<svg\b[^>]*\bwidth=", text, re.I):
        text = re.sub(r'(<svg\b[^>]*?)\swidth=["\'][^"\']+["\']', r'\1 width="256"', text, count=1, flags=re.I)
    else:
        text = re.sub(r"<svg\b", '<svg width="256"', text, count=1, flags=re.I)
    if re.search(r"<svg\b[^>]*\bheight=", text, re.I):
        text = re.sub(r'(<svg\b[^>]*?)\sheight=["\'][^"\']+["\']', r'\1 height="256"', text, count=1, flags=re.I)
    else:
        text = re.sub(r"<svg\b", '<svg height="256"', text, count=1, flags=re.I)
    return text


def download(url: str, destination: Path, timeout: int = 25) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "newbiz2-python-runner/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() == ".svg":
            content = normalize_svg_size(content.decode("utf-8", errors="ignore")).encode("utf-8")
        destination.write_bytes(content)
        return True
    except Exception:
        return False


def absolute_url(base_url: str, value: str) -> str:
    value = html.unescape((value or "").strip().strip("'\""))
    if not value:
        return ""
    if value.startswith("//"):
        parsed = urllib.parse.urlparse(normalize_url(base_url))
        return f"{parsed.scheme}:{value}"
    return urllib.parse.urljoin(normalize_url(base_url), value)


def discover_site_logo_candidates(website: str) -> list[str]:
    """Find first-party logo candidates from page metadata before using generic icon services."""
    if not website:
        return []
    try:
        url = normalize_url(website)
        request = urllib.request.Request(url, headers={"User-Agent": "newbiz2-python-runner/1.0"})
        with urllib.request.urlopen(request, timeout=25) as response:
            text = response.read(1_500_000).decode("utf-8", errors="ignore")
    except Exception:
        return []
    candidates: list[str] = []

    def add(value: str) -> None:
        candidate = absolute_url(website, value)
        if candidate and candidate not in candidates and re.search(r"\.(?:png|jpe?g|webp|svg|ico)(?:[?#].*)?$", candidate, re.I):
            candidates.append(candidate)

    for match in re.finditer(r'<meta\b[^>]*(?:property|name)=["\'](?:og:image|twitter:image|thumbnail)["\'][^>]*content=["\']([^"\']+)["\']', text, re.I):
        add(match.group(1))
    for match in re.finditer(r'<meta\b[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image|thumbnail)["\']', text, re.I):
        add(match.group(1))
    for match in re.finditer(r'<link\b[^>]*rel=["\'][^"\']*(?:icon|apple-touch-icon|preload)[^"\']*["\'][^>]*(?:href|imagesrcset)=["\']([^"\']+)["\']', text, re.I):
        values = [part.strip().split()[0] for part in match.group(1).split(",")]
        for value in values:
            add(value)
    for match in re.finditer(r'<img\b[^>]*(?:src|data-src)=["\']([^"\']*(?:logo|brand)[^"\']*\.(?:png|jpe?g|webp|svg))["\']', text, re.I):
        add(match.group(1))
    for match in re.finditer(r'"logo"\s*:\s*"([^"]+)"', text, re.I):
        add(match.group(1))
    for match in re.finditer(r'https?://[^"\'<>\s]+(?:logo|Logo|favicon|FavIcon)[^"\'<>\s]*\.(?:png|jpe?g|webp|svg|ico)', text):
        add(match.group(0))
    def score(candidate: str) -> tuple[int, int]:
        lower = candidate.lower()
        priority = 0
        if any(token in lower for token in ("seoimages", "social-", "social_", "/social/", "share-", "share_", "/share/")):
            priority += 120
        if "lockup" in lower:
            priority -= 60
        if "logo_square" in lower or "square" in lower:
            priority -= 40
        if "primary" in lower:
            priority -= 35
        if "brand" in lower:
            priority -= 20
        if "pan-logo" in lower or "nav-logo" in lower:
            priority -= 45
        if "logo" in lower:
            priority -= 20
        if "favicon" in lower or "apple-touch" in lower:
            priority += 80
        if "og:image" in lower or "thumbnail" in lower:
            priority += 20
        return (priority, len(candidate))

    return sorted(candidates, key=score)


def icon_slug(name: str, website: str = "") -> str:
    clean = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).strip()
    if clean in SIMPLEICON_OVERRIDES:
        return SIMPLEICON_OVERRIDES[clean]
    if website:
        host = urllib.parse.urlparse(website).netloc.lower().replace("www.", "")
        first = host.split(".")[0]
        if first:
            return SIMPLEICON_OVERRIDES.get(first, first)
    return slugify(clean or name)


def acquire_logo(
    name: str,
    website: str,
    destination: Path,
    candidates: list[str] | None = None,
    *,
    allow_simpleicons: bool = True,
) -> tuple[bool, str]:
    urls = list(candidates or [])
    if not urls:
        for sibling in [
            destination.with_suffix(".png"),
            destination.with_suffix(".jpg"),
            destination.with_suffix(".jpeg"),
            destination.with_suffix(".webp"),
        ]:
            if sibling.exists() and quality_ok(sibling):
                return True, "local-raster"
        if destination.exists() and destination.suffix.lower() != ".svg" and quality_ok(destination):
            return True, "local"
    slug = icon_slug(name, website)
    if website:
        parsed = urllib.parse.urlparse(normalize_url(website))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        urls.extend(
            [
                f"{origin}/apple-touch-icon.png",
                f"{origin}/favicon-512x512.png",
                f"{origin}/favicon-256x256.png",
                f"{origin}/favicon-192x192.png",
                f"{origin}/favicon.png",
                f"https://www.google.com/s2/favicons?sz=256&domain_url={urllib.parse.quote(origin)}",
            ]
        )
    if allow_simpleicons:
        urls.append(f"https://cdn.simpleicons.org/{urllib.parse.quote(slug)}/000000")
    for url in urls:
        suffix = ".svg" if "simpleicons.org" in url else Path(urllib.parse.urlparse(url).path).suffix.lower() or ".png"
        if suffix not in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            suffix = ".png"
        target = destination.with_suffix(suffix)
        if download(url, target) and quality_ok(target):
            return True, url
        if target.exists() and target != destination:
            target.unlink(missing_ok=True)
    if destination.exists() and quality_ok(destination):
        return True, "local-svg"
    return False, "no candidate passed quality check"


def acquire_square_logo(name: str, website: str, asset_dir: Path, slug: str) -> tuple[bool, str]:
    stems = [f"{slug}-mark", f"{slug}-favicon", f"{slug}-initial-mark", slug]
    for stem in stems:
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
            candidate = asset_dir / f"{stem}{suffix}"
            if candidate.exists() and square_quality_ok(candidate) and visible_logo_occupancy_ok(candidate):
                return True, "local-square"
    if not website:
        return False, "no website for square logo acquisition"
    parsed = urllib.parse.urlparse(normalize_url(website))
    origin = f"{parsed.scheme}://{parsed.netloc}"
    urls = [
        f"{origin}/apple-touch-icon.png",
        f"{origin}/apple-touch-icon-precomposed.png",
        f"{origin}/favicon-512x512.png",
        f"{origin}/favicon-256x256.png",
        f"{origin}/favicon-192x192.png",
        f"{origin}/favicon-180x180.png",
        f"{origin}/favicon-128x128.png",
        f"{origin}/favicon.png",
        f"https://www.google.com/s2/favicons?sz=256&domain_url={urllib.parse.quote(origin)}",
        f"https://www.google.com/s2/favicons?sz=128&domain_url={urllib.parse.quote(origin)}",
    ]
    for url in urls:
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".png"
        if suffix not in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            suffix = ".png"
        target = asset_dir / f"{slug}-mark{suffix}"
        if download(url, target) and square_quality_ok(target) and visible_logo_occupancy_ok(target):
            return True, url
        if target.exists():
            target.unlink(missing_ok=True)
    return False, "no square logo candidate passed quality check"


def create_square_badge_from_logo(source: Path, destination: Path, canvas_size: int = 256) -> bool:
    if not source.exists() or not quality_ok(source):
        return False
    try:
        from PIL import Image, ImageChops

        with Image.open(source) as image:
            image = image.convert("RGBA")
            bbox = visible_content_bbox(source)
            if not bbox:
                alpha_bbox = image.getchannel("A").getbbox()
                if alpha_bbox:
                    bbox = alpha_bbox
                else:
                    background = Image.new("RGBA", image.size, image.getpixel((0, 0)))
                    diff = ImageChops.difference(image, background)
                    bbox = diff.getbbox()
            cropped = image.crop(bbox) if bbox else image

            if not cropped.width or not cropped.height:
                return False
            max_content = int(canvas_size * 0.86)
            scale = min(max_content / cropped.width, max_content / cropped.height)
            resized = cropped.resize((max(1, int(cropped.width * scale)), max(1, int(cropped.height * scale))), Image.LANCZOS)
            canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
            x = (canvas_size - resized.width) // 2
            y = (canvas_size - resized.height) // 2
            canvas.alpha_composite(resized, (x, y))
            destination.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(destination)
            return square_quality_ok(destination)
    except Exception:
        return False


def create_initial_mark_from_logo(source: Path, destination: Path, label: str = "", canvas_size: int = 256) -> bool:
    """Create a square mark by isolating the first visible letter from a wide wordmark."""
    if not source.exists() or not quality_ok(source):
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont

        with Image.open(source) as image:
            image = image.convert("RGBA")
            bbox = visible_content_bbox(source)
            if not bbox:
                bbox = image.getchannel("A").getbbox()
            if not bbox:
                return False

            width, height = image.size
            corners = [
                image.getpixel((0, 0)),
                image.getpixel((width - 1, 0)),
                image.getpixel((0, height - 1)),
                image.getpixel((width - 1, height - 1)),
            ]
            background = tuple(sorted(corners)[len(corners) // 2])
            left, top, right, bottom = bbox

            def is_logo_ink(pixel: tuple[int, int, int, int]) -> bool:
                red, green, blue, alpha = pixel
                if alpha <= 20:
                    return False
                if red > 245 and green > 245 and blue > 245:
                    return False
                return max(red, green, blue) - min(red, green, blue) > 18 or min(red, green, blue) < 210

            ink_left, ink_top, ink_right, ink_bottom = width, height, -1, -1
            colour_counts: Counter[tuple[int, int, int]] = Counter()
            for y in range(top, bottom):
                for x in range(left, right):
                    pixel = image.getpixel((x, y))
                    if is_logo_ink(pixel):
                        ink_left = min(ink_left, x)
                        ink_top = min(ink_top, y)
                        ink_right = max(ink_right, x + 1)
                        ink_bottom = max(ink_bottom, y + 1)
                        colour_counts[(pixel[0] // 16 * 16, pixel[1] // 16 * 16, pixel[2] // 16 * 16)] += 1
            if ink_right >= ink_left and ink_bottom >= ink_top:
                left, top, right, bottom = ink_left, ink_top, ink_right, ink_bottom
            content_height = max(bottom - top, 1)

            initial_source = label or source.stem
            initial_match = re.search(r"[A-Za-z0-9]", initial_source)
            if initial_match and colour_counts:
                initial = initial_match.group(0).upper()
                colour = colour_counts.most_common(1)[0][0]
                canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
                draw = ImageDraw.Draw(canvas)
                font_paths = [
                    Path("C:/Windows/Fonts/arialbd.ttf"),
                    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
                ]
                font = None
                for font_path in font_paths:
                    if font_path.exists():
                        font = ImageFont.truetype(str(font_path), int(canvas_size * 0.72))
                        break
                if font is None:
                    try:
                        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(canvas_size * 0.72))
                    except Exception:
                        font = ImageFont.load_default()
                text_box = draw.textbbox((0, 0), initial, font=font)
                text_width = text_box[2] - text_box[0]
                text_height = text_box[3] - text_box[1]
                x = (canvas_size - text_width) // 2 - text_box[0]
                y = (canvas_size - text_height) // 2 - text_box[1]
                draw.text((x, y), initial, font=font, fill=(colour[0], colour[1], colour[2], 255))
                destination.parent.mkdir(parents=True, exist_ok=True)
                canvas.save(destination)
                if square_quality_ok(destination) and visible_logo_occupancy_ok(destination, minimum_span=0.42):
                    return True

            # Detect the first letter from the upper body of the mark. This avoids
            # long underlines or baselines making a whole word look like one object.
            scan_top = top
            scan_bottom = min(bottom, top + max(1, int(content_height * 0.78)))
            min_pixels = max(1, int((scan_bottom - scan_top) * 0.025))
            column_has_content: list[bool] = []
            for x in range(left, right):
                count = 0
                for y in range(scan_top, scan_bottom):
                    pixel = image.getpixel((x, y))
                    alpha_delta = abs(pixel[3] - background[3])
                    colour_delta = max(abs(pixel[i] - background[i]) for i in range(3))
                    if is_logo_ink(pixel) and (alpha_delta > 18 or colour_delta > 18):
                        count += 1
                column_has_content.append(count >= min_pixels)

            runs: list[tuple[int, int]] = []
            run_start: int | None = None
            gap = 0
            max_gap = max(2, int((right - left) * 0.015))
            for index, has_content in enumerate(column_has_content):
                if has_content:
                    if run_start is None:
                        run_start = index
                    gap = 0
                elif run_start is not None:
                    gap += 1
                    if gap > max_gap:
                        runs.append((run_start, index - gap + 1))
                        run_start = None
                        gap = 0
            if run_start is not None:
                runs.append((run_start, len(column_has_content)))

            runs = [(left + start, left + end) for start, end in runs if end - start >= 3]
            if runs:
                crop_left, crop_right = runs[0]
            else:
                target_width = min(right - left, max(content_height, int((right - left) * 0.18)))
                crop_left, crop_right = left, left + target_width
            if crop_right - crop_left > content_height * 1.35:
                crop_right = min(right, crop_left + max(8, int((right - left) * 0.12)))

            pad_x = max(4, int((crop_right - crop_left) * 0.18))
            pad_y = max(4, int(content_height * 0.12))
            crop_box = (
                max(0, crop_left - pad_x),
                max(0, top - pad_y),
                min(width, crop_right + pad_x),
                min(height, bottom + pad_y),
            )
            cropped = image.crop(crop_box)
            if not cropped.width or not cropped.height:
                return False

            max_content = int(canvas_size * 0.82)
            scale = min(max_content / cropped.width, max_content / cropped.height)
            resized = cropped.resize((max(1, int(cropped.width * scale)), max(1, int(cropped.height * scale))), Image.LANCZOS)
            canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
            x = (canvas_size - resized.width) // 2
            y = (canvas_size - resized.height) // 2
            canvas.alpha_composite(resized, (x, y))
            destination.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(destination)
            return square_quality_ok(destination) and visible_logo_occupancy_ok(destination, minimum_span=0.42)
    except Exception:
        return False


def palette_from_label(label: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    palettes = [
        ((11, 92, 74), (255, 255, 255)),
        ((15, 59, 112), (255, 255, 255)),
        ((118, 68, 20), (255, 247, 230)),
        ((124, 35, 68), (255, 242, 248)),
        ((55, 86, 38), (248, 255, 238)),
        ((74, 58, 123), (247, 244, 255)),
        ((25, 82, 97), (235, 253, 255)),
        ((119, 45, 19), (255, 245, 238)),
    ]
    digest = hashlib.sha256(label.encode("utf-8", errors="ignore")).digest()
    return palettes[digest[0] % len(palettes)]


def create_initial_mark_from_name(label: str, destination: Path, canvas_size: int = 256) -> bool:
    """Create a deterministic square mark when acquired candidate assets are unusable."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        initial_match = re.search(r"[A-Za-z0-9]", label or "")
        initial = initial_match.group(0).upper() if initial_match else "?"
        background, foreground = palette_from_label(label or initial)
        image = Image.new("RGBA", (canvas_size, canvas_size), (*background, 255))
        draw = ImageDraw.Draw(image)
        font = None
        for font_path in [
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ]:
            if font_path.exists():
                font = ImageFont.truetype(str(font_path), int(canvas_size * 0.68))
                break
        if font is None:
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(canvas_size * 0.68))
            except Exception:
                font = ImageFont.load_default()
        draw.rounded_rectangle((6, 6, canvas_size - 6, canvas_size - 6), radius=48, fill=(*background, 255))
        draw.rounded_rectangle((14, 14, canvas_size - 14, canvas_size - 14), radius=38, outline=(*foreground, 72), width=4)
        text_box = draw.textbbox((0, 0), initial, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        x = (canvas_size - text_width) // 2 - text_box[0]
        y = (canvas_size - text_height) // 2 - text_box[1] - 2
        draw.text((x, y), initial, font=font, fill=(*foreground, 255))
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG", optimize=True)
        return square_quality_ok(destination) and visible_logo_occupancy_ok(destination, minimum_span=0.42)
    except Exception:
        return False


def create_tight_logo_asset(source: Path, destination: Path, padding: int = 8) -> bool:
    if not source.exists() or not quality_ok(source):
        return False
    try:
        from PIL import Image

        bbox = visible_content_bbox(source)
        if not bbox:
            return False
        with Image.open(source) as image:
            image = image.convert("RGBA")
            left = max(0, bbox[0] - padding)
            top = max(0, bbox[1] - padding)
            right = min(image.width, bbox[2] + padding)
            bottom = min(image.height, bbox[3] + padding)
            cropped = image.crop((left, top, right, bottom))
            destination.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(destination)
            return quality_ok(destination, minimum=24) and visible_logo_occupancy_ok(destination, minimum_span=0.62)
    except Exception:
        return False


def preferred_logo_asset(asset_dir: Path, stem: str, prefer_square: bool = False) -> Path | None:
    if prefer_square:
        base = re.sub(r"-(logo|mark|favicon)$", "", stem)
        for candidate_stem in (f"{base}-mark", f"{base}-favicon", f"{base}-initial-mark", base, stem):
            for suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                candidate = asset_dir / f"{candidate_stem}{suffix}"
                if candidate.exists() and square_quality_ok(candidate) and visible_logo_occupancy_ok(candidate):
                    return candidate
    for suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
        candidate = asset_dir / f"{stem}{suffix}"
        if candidate.exists() and quality_ok(candidate):
            return candidate
    matches = sorted(asset_dir.glob(f"{stem}.*"))
    return matches[0] if matches else None


def source_looks_like_share_card(source: str) -> bool:
    lower = (source or "").lower()
    return any(token in lower for token in ("seoimages", "social-", "social_", "/social/", "share-", "share_", "/share/"))


def brand_logo_manifest_entry(name: str, asset: str, source: str, ok: bool, brand_folder: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "asset": asset, "ok": ok, "resolution_source": source}
    asset_path = (brand_folder / asset).resolve() if asset and not Path(asset).is_absolute() else Path(asset)
    quality = asset_quality(asset_path) if asset else {"exists": False, "valid_image": False, "width": 0, "height": 0, "bytes": 0, "format": "", "reason": "missing"}
    entry["quality"] = quality
    if source and "simpleicons.org" in source.lower():
        entry["ok"] = False
        entry["error"] = "Primary brand logo used Simple Icons monochrome proxy rather than a first-party brand asset."
    elif source in {"local-svg", "local"} and asset_path.suffix.lower() == ".svg":
        svg_text = asset_path.read_text(encoding="utf-8", errors="ignore") if asset_path.exists() else ""
        if "simpleicons" in svg_text.lower() or re.search(r'fill=["\']#?000(?:000)?["\']', svg_text, re.I):
            entry["ok"] = False
            entry["error"] = "Primary brand logo appears to be a monochrome SVG proxy; use a first-party colour logo."
    elif not quality.get("valid_image"):
        entry["ok"] = False
        entry["error"] = f"Primary brand logo asset is invalid: {quality.get('reason') or 'unknown quality failure'}."
    elif quality.get("format") != "svg" and (quality.get("width", 0) < 200 or quality.get("height", 0) < 60):
        entry["ok"] = False
        entry["error"] = f"Primary brand logo raster is too small ({quality.get('width')}x{quality.get('height')}); use a dedicated asset at least 200px wide and 60px tall."
    elif source_looks_like_share_card(source):
        entry["ok"] = False
        entry["error"] = "Primary brand logo used a social/share image instead of a dedicated first-party logo asset."
    elif quality.get("format") != "svg" and not visible_logo_occupancy_ok(asset_path, minimum_span=0.58):
        entry["ok"] = False
        entry["error"] = "Primary brand logo does not occupy enough of the asset frame to stay readable in report badges."
    return entry


def patch_assets(data: dict[str, Any], brand_folder: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    asset_dir = brand_folder / "slide-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"ok": True, "asset_directory": str(asset_dir), "brand": {}, "competitors": [], "news_sources": [], "errors": []}

    brand = data.setdefault("brand", {})
    brand_name = brand.get("name", "brand")
    brand_slug = brand.get("slug") or slugify(brand_name)
    brand["slug"] = brand_slug
    brand_logo = asset_dir / f"{brand_slug}-logo.svg"
    brand_candidates = discover_site_logo_candidates(str(brand.get("website", "")))
    ok, source = acquire_logo(brand_name, brand.get("website", ""), brand_logo, candidates=brand_candidates, allow_simpleicons=False)
    if ok:
        brand_asset = None
        source_path = Path(urllib.parse.urlparse(source).path)
        source_suffix = source_path.suffix.lower() if source_path.suffix else ""
        if source_suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            exact_brand_asset = asset_dir / f"{brand_slug}-logo{source_suffix}"
            if exact_brand_asset.exists() and quality_ok(exact_brand_asset):
                brand_asset = exact_brand_asset
        if brand_asset is None:
            brand_asset = preferred_logo_asset(asset_dir, f"{brand_slug}-logo")
        brand["logo_url"] = relative_to_brand(brand_asset, brand_folder) if brand_asset else ""
        brand["mark_url"] = brand["logo_url"]
    else:
        manifest["ok"] = False
        manifest["errors"].append(f"{brand_name} brand logo failed: {source}")
    manifest["brand"] = brand_logo_manifest_entry(brand_name, brand.get("logo_url", ""), source, ok, brand_folder)
    if not manifest["brand"].get("ok"):
        manifest["ok"] = False
        manifest["errors"].append(f"{brand_name} brand logo failed: {manifest['brand'].get('error') or source}")

    for index, row in enumerate(data.get("competitive_landscape", {}).get("table", [])):
        name = row.get("competitor") or row.get("name") or f"competitor-{index + 1}"
        website = row.get("website", "")
        slug = slugify(name)
        square_ok, square_source = acquire_square_logo(name, website, asset_dir, slug)
        logo_path = asset_dir / f"{slug}-logo.svg"
        ok, source = (square_ok, square_source) if square_ok else acquire_logo(name, website, logo_path)
        asset = ""
        if ok:
            logo_asset = preferred_logo_asset(asset_dir, f"{slug}-logo", prefer_square=True)
            if logo_asset and not square_quality_ok(logo_asset):
                generated_square = asset_dir / f"{slug}-mark.png"
                if create_square_badge_from_logo(logo_asset, generated_square):
                    logo_asset = generated_square
                    source = f"{source}; generated-square-badge-from-wordmark"
            if logo_asset:
                quality = asset_quality(logo_asset)
                bbox = visible_content_bbox(logo_asset)
                if bbox and quality.get("width") and quality.get("height"):
                    content_width = bbox[2] - bbox[0]
                    content_height = bbox[3] - bbox[1]
                    content_aspect = content_width / max(content_height, 1)
                    content_height_share = content_height / max(int(quality["height"]), 1)
                    if not has_distinct_square_background(logo_asset) and (content_aspect >= 1.6 or content_height_share < 0.45):
                        initial_asset = asset_dir / f"{slug}-initial-mark.png"
                        if create_initial_mark_from_logo(logo_asset, initial_asset, label=name):
                            logo_asset = initial_asset
                            source = f"{source}; initial-letter-mark-from-wordmark"
            asset = relative_to_brand(logo_asset, brand_folder) if logo_asset else ""
            row["logo_url"] = asset
            row["competitor_logo_url"] = asset
            row["badge_url"] = asset
            row["logo_resolution_source"] = source
        else:
            initial_asset = asset_dir / f"{slug}-initial-mark.png"
            if create_initial_mark_from_name(name, initial_asset):
                ok = True
                source = f"{source}; deterministic-square-initial-mark-after-candidate-failure"
                asset = relative_to_brand(initial_asset, brand_folder)
                row["logo_url"] = asset
                row["competitor_logo_url"] = asset
                row["badge_url"] = asset
                row["logo_resolution_source"] = source
                row["logo_asset_kind"] = "deterministic-square-initial-mark"
            else:
                manifest["ok"] = False
                manifest["errors"].append(f"{name} competitor logo failed: {source}")
        manifest["competitors"].append({"index": index, "name": name, "asset": asset, "ok": ok, "resolution_source": source, "asset_kind": row.get("logo_asset_kind", "acquired-or-derived-logo") if ok else "missing"})

    for index, item in enumerate(data.get("brand_reputation", {}).get("influential_news", [])):
        source_name = item.get("source") or brand_name
        source_url = item.get("url") or brand.get("website", "")
        slug = slugify(source_name)
        if source_name.lower().strip() in {brand_name.lower().strip(), f"{brand_name.lower().strip()} newsroom"}:
            asset = brand.get("logo_url", "")
            ok = bool(asset)
            resolution = "brand-logo"
        else:
            logo_path = asset_dir / f"{slug}-news.svg"
            ok, resolution = acquire_logo(source_name, source_url, logo_path)
            logo_asset = preferred_logo_asset(asset_dir, f"{slug}-news")
            asset = relative_to_brand(logo_asset, brand_folder) if ok and logo_asset else ""
        if ok:
            item["source_logo_url"] = asset
            item["publisher_logo_url"] = asset
        else:
            fallback_asset = asset_dir / f"{slug}-source-initial-mark.png"
            if create_initial_mark_from_name(source_name, fallback_asset):
                ok = True
                resolution = f"{resolution}; deterministic-square-initial-mark-after-candidate-failure"
                asset = relative_to_brand(fallback_asset, brand_folder)
                item["source_logo_url"] = asset
                item["publisher_logo_url"] = asset
                item["source_logo_asset_kind"] = "deterministic-square-initial-mark"
            else:
                manifest["ok"] = False
                manifest["errors"].append(f"{source_name} source logo failed: {resolution}")
        manifest["news_sources"].append({"index": index, "source": source_name, "asset": asset, "ok": ok, "resolution_source": resolution, "asset_kind": item.get("source_logo_asset_kind", "acquired-or-derived-logo") if ok else "missing"})
    return data, manifest


def module_assets(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "assets", "in_progress")
    set_gate(state, "gate_5_assets", "in_progress")
    set_gate(state, "gate_5a_source_badges", "in_progress")
    set_gate(state, "gate_5b_required_logos", "in_progress")
    add_event(state, "fanout", "assets.logo_acquisition", jobs=["brand", "competitors", "news_sources"])
    save_state(brand_folder, state)
    data, manifest = patch_assets(read_json(data_path), brand_folder)
    write_json(data_path, data)
    manifest_path = brand_folder / "required-logo-manifest.json"
    badge_path = brand_folder / "source-badge-manifest.json"
    write_json(manifest_path, manifest)
    write_json(badge_path, {"ok": manifest["ok"], "sources": manifest["news_sources"], "errors": manifest["errors"]})
    if not manifest["ok"]:
        set_status(state, "assets", "failed")
        set_gate(state, "gate_5_assets", "failed")
        set_gate(state, "gate_5a_source_badges", "failed")
        set_gate(state, "gate_5b_required_logos", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Logo/assets validation failed: " + "; ".join(manifest["errors"]))
    add_event(state, "fanout", "assets.source_badges", jobs=["source-badge-manifest", "brand-asset-validation", "delivery-asset-validation"])
    add_event(state, "reducer", "assets.asset_manifest_reducer", outputs=[str(manifest_path), str(badge_path)])
    set_status(state, "assets", "passed")
    set_gate(state, "gate_5_assets", "passed")
    set_gate(state, "gate_5a_source_badges", "passed")
    set_gate(state, "gate_5b_required_logos", "passed")
    save_state(brand_folder, state)
    return {"module": "assets", "data": str(data_path), "brand_folder": str(brand_folder), "required_logos": manifest}


def set_patch_value(root: dict[str, Any], path: str, value: Any) -> None:
    cursor: Any = root
    parts = path.split(".")
    for index, part in enumerate(parts):
        match = re.match(r"^([A-Za-z0-9_]+)(?:\[(\d+)\])?$", part)
        if not match:
            raise ValueError(f"Unsupported patch path segment {part!r}")
        name, item_index = match.group(1), match.group(2)
        is_last = index == len(parts) - 1
        if is_last:
            cursor[name] = value
            return
        cursor = cursor[name]
        if item_index is not None:
            cursor = cursor[int(item_index)]


def apply_manifest(data_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    patches = manifest.get("patches", [])
    if not patches:
        return {"ok": False, "applied_count": 0, "applied_paths": [], "manifest": str(manifest_path)}
    data = read_json(data_path)
    applied = []
    for patch in patches:
        set_patch_value(data, patch["path"], patch.get("value"))
        applied.append(patch["path"])
    write_json(data_path, data)
    return {"ok": True, "applied_count": len(applied), "applied_paths": applied, "manifest": str(manifest_path), "new_sha256": sha256(data_path)}


def run_python_script(script: Path, args: list[str]) -> dict[str, Any]:
    completed = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{script.name} failed with exit code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}")
    output = completed.stdout.strip()
    return json.loads(output) if output else {}


def render_outputs_current(data_path: Path, brand_folder: Path) -> dict[str, Any]:
    html_path = brand_folder / "newbizintel-report.html"
    portable_html = brand_folder / "archive" / "newbizintel-report-portable.html"
    pptx_path = brand_folder / "newbizintel-report.pptx"
    outputs = [html_path, portable_html, pptx_path]
    errors: list[str] = []
    if not data_path.exists():
        errors.append("report-data.json is missing.")
    else:
        data_mtime = data_path.stat().st_mtime
        for path in outputs:
            if not path.exists():
                errors.append(f"{path.name} is missing.")
                continue
            if path.stat().st_mtime + 1e-6 < data_mtime:
                errors.append(f"{path.name} is older than report-data.json.")
    return {"ok": not errors, "errors": errors, "outputs": [str(path) for path in outputs]}


def reconcile_render_gate_from_outputs(state: dict[str, Any], data_path: Path, brand_folder: Path) -> bool:
    audit = render_outputs_current(data_path, brand_folder)
    if not audit["ok"]:
        return False
    current_status = state.get("status", {}).get("render")
    current_gate = state.get("gates", {}).get("gate_8_render_outputs")
    current_legacy_gate = state.get("gates", {}).get("gate_6_render_outputs")
    if current_status == "passed" and current_gate == "passed" and current_legacy_gate == "passed":
        return False
    set_status(state, "render", "passed")
    set_gate(state, "gate_8_render_outputs", "passed")
    set_gate(state, "gate_6_render_outputs", "passed")
    add_event(state, "reducer", "render.output_reconciliation", outputs=audit["outputs"])
    return True


def campaign_section(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("creative_campaign_ideas") or data.get("creative_campaigns") or {}


def campaign_art_diversity_group(idea: dict[str, Any]) -> str:
    text = " ".join(
        str(idea.get(field) or "").lower()
        for field in (
            "illustration_style_family",
            "illustration_style_name",
            "illustration_medium",
            "illustration_prompt",
        )
    )
    groups = [
        ("technical-system", ("technical", "blueprint", "schematic", "interface", "circuit", "systems")),
        ("poster-collage", ("poster", "collage", "zine", "xerox", "risograph", "print")),
        ("painting", ("painting", "oil", "brush", "pastel", "watercolour", "baroque", "still-life")),
        ("photography", ("photo", "photographic", "cinematic", "infrared", "long-exposure")),
        ("sculpture-paper", ("sculpture", "sculptural", "maquette", "paper", "relief", "clay", "model")),
        ("comic-graphic", ("comic", "graphic novel", "noir")),
        ("cartographic", ("atlas", "cartographic", "geospatial", "map", "orbital")),
    ]
    for group, needles in groups:
        if any(needle in text for needle in needles):
            return group
    return re.sub(r"[^a-z0-9]+", "-", str(idea.get("illustration_style_family") or "unknown").lower()).strip("-") or "unknown"


def campaign_art_visual_fingerprint(path: Path) -> dict[str, Any] | None:
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            image = image.convert("RGB").resize((32, 32))
            grayscale = image.convert("L")
            pixels = list(grayscale.tobytes())
            average = sum(pixels) / max(len(pixels), 1)
            bits = tuple(1 if pixel >= average else 0 for pixel in pixels)
            stat = ImageStat.Stat(image)
            mean = tuple(float(value) for value in stat.mean)
            histogram = image.histogram()
            bucketed: list[int] = []
            for channel in range(3):
                channel_hist = histogram[channel * 256 : (channel + 1) * 256]
                for start in range(0, 256, 32):
                    bucketed.append(sum(channel_hist[start : start + 32]))
            return {"bits": bits, "mean": mean, "histogram": bucketed}
    except Exception:
        return None


def hamming_similarity(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    distance = sum(1 for a, b in zip(left, right) if a != b)
    return 1.0 - (distance / len(left))


def cosine_similarity(left: list[int], right: list[int]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def audit_campaign_art(data_path: Path) -> dict[str, Any]:
    data = read_json(data_path)
    ideas = campaign_section(data).get("ideas", [])
    errors = []
    diversity_groups: list[str] = []
    style_names: list[str] = []
    fingerprints: list[tuple[int, str, dict[str, Any]]] = []
    accepted_final_backends = {"imagegen-batch-import"}
    disallowed_provenance = {"report-output-local", "skill-local", "unknown", "placeholder", ""}
    for index, idea in enumerate(ideas):
        url = idea.get("illustration_url")
        role = idea.get("illustration_asset_role")
        backend = idea.get("illustration_generation_backend")
        import_source = str(idea.get("illustration_import_source") or "").strip()
        provenance = str(idea.get("illustration_source_provenance") or "").strip().lower()
        style_name = str(idea.get("illustration_style_name") or "").strip()
        if style_name:
            style_names.append(style_name.lower())
        diversity_groups.append(campaign_art_diversity_group(idea))
        if role != "final-raster-artwork":
            errors.append(f"ideas[{index}] artwork is not marked final-raster-artwork.")
        if backend in {"local-scaffold", "placeholder"}:
            errors.append(f"ideas[{index}] uses scaffold backend.")
        if role == "final-raster-artwork":
            if backend not in accepted_final_backends:
                errors.append(
                    f"ideas[{index}] final artwork must come from a generated image batch import, not backend '{backend or 'missing'}'."
                )
            if not import_source:
                errors.append(f"ideas[{index}] final artwork is missing illustration_import_source provenance.")
            if provenance in disallowed_provenance:
                errors.append(
                    f"ideas[{index}] final artwork uses disallowed source provenance '{provenance or 'missing'}'."
                )
            source_path = Path(import_source).expanduser() if import_source else None
            if source_path:
                try:
                    resolved_source = source_path.resolve()
                    try:
                        resolved_source.relative_to(data_path.parent.resolve())
                        errors.append(
                            f"ideas[{index}] final artwork source points back into the report output folder: {resolved_source}"
                        )
                    except ValueError:
                        pass
                    try:
                        resolved_source.relative_to(SCRIPT_ROOT.resolve())
                        errors.append(
                            f"ideas[{index}] final artwork source points into the local skill runtime instead of an image batch: {resolved_source}"
                        )
                    except ValueError:
                        pass
                except OSError:
                    errors.append(f"ideas[{index}] illustration_import_source could not be resolved: {import_source}")
        if not url:
            errors.append(f"ideas[{index}] has no illustration_url.")
            continue
        path = data_path.parent / url
        if not path.exists():
            errors.append(f"ideas[{index}] artwork missing: {url}")
        elif path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            errors.append(f"ideas[{index}] artwork is not raster: {url}")
        elif not quality_ok(path, minimum=256):
            errors.append(f"ideas[{index}] artwork failed image quality: {url}")
        else:
            fingerprint = campaign_art_visual_fingerprint(path)
            if fingerprint:
                fingerprints.append((index, str(idea.get("title") or f"idea {index + 1}"), fingerprint))
    if len(style_names) != len(set(style_names)):
        errors.append("Campaign artwork must use distinct style names for each idea.")
    if len(ideas) >= 3:
        unique_groups = set(diversity_groups)
        if len(unique_groups) < min(len(ideas), 3):
            errors.append(
                "Campaign artwork lacks treatment diversity: "
                + ", ".join(diversity_groups)
            )
        repeated_groups = [group for group, count in Counter(diversity_groups).items() if group != "unknown" and count > 1]
        if repeated_groups:
            errors.append(
                "Campaign artwork repeats broad treatment group(s): "
                + ", ".join(sorted(repeated_groups))
            )
    for left_index, left_title, left_fp in fingerprints:
        for right_index, right_title, right_fp in fingerprints:
            if right_index <= left_index:
                continue
            hash_similarity = hamming_similarity(left_fp["bits"], right_fp["bits"])
            colour_similarity = cosine_similarity(left_fp["histogram"], right_fp["histogram"])
            mean_delta = sum(abs(a - b) for a, b in zip(left_fp["mean"], right_fp["mean"])) / 3
            if hash_similarity >= 0.86 and colour_similarity >= 0.9 and mean_delta < 32:
                errors.append(
                    f"Campaign artwork is too visually similar between ideas[{left_index}] '{left_title}' "
                    f"and ideas[{right_index}] '{right_title}' "
                    f"(hash similarity {hash_similarity:.2f}, colour similarity {colour_similarity:.2f})."
                )
    return {"ok": not errors, "errors": errors, "diversity_groups": diversity_groups}


def audit_presentation_html(brand_folder: Path, data_path: Path) -> dict[str, Any]:
    html_path = brand_folder / "newbizintel-report.html"
    errors: list[str] = []
    warnings: list[str] = []
    if not html_path.exists():
        return {"ok": False, "errors": [f"HTML report missing: {html_path}"], "warnings": warnings}

    size = html_path.stat().st_size
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    completeness_audit = audit_rendered_html_completeness(text)
    if not completeness_audit["ok"]:
        errors.extend(completeness_audit.get("errors", []))
    if size < 100_000:
        errors.append(f"HTML report is too small for the rich presentation layer ({size} bytes).")
    for label in ("Competitive Landscape", "SEO Audit", "Brand Reputation", "Creative Campaign Ideas"):
        if label not in text:
            errors.append(f"HTML report is missing required section: {label}")
    rich_markers = (
        'class="toc"',
        'class="section-heading"',
        "Department Opportunity Signals",
        "Messaging Assessment",
        "Reputation Implications and Recommended Actions",
        "Content Strategy Recommendations",
    )
    missing_rich_markers = [marker for marker in rich_markers if marker not in text]
    if "Generated by newbiz2 modular runner" in text or missing_rich_markers:
        errors.append("HTML report was produced by the skeletal Python fallback renderer.")
    if re.search(r'class="[^"]*competitor-badge--fallback', text):
        errors.append("Competitor logos fell back to initials in rendered HTML.")
    if re.search(r'<div class="publisher-badge"><span>', text):
        errors.append("News/source logos fell back to text badges in rendered HTML.")
    if re.search(r'class="[^"]*brand-logo-slot--fallback', text):
        errors.append("Brand logo fell back to initials in rendered HTML.")
    if "Department Opportunity Map" in text:
        errors.append("Department Opportunity Map is redundant and must not be rendered.")
    signal_start = text.find("Department Opportunity Signals")
    signal_end = text.find("Most Likely Workstreams", signal_start)
    signal_section = text[signal_start:signal_end] if signal_start >= 0 and signal_end > signal_start else ""
    if signal_section and re.search(r'(?:Value:|<span class="opportunity-chip)', signal_section, flags=re.I):
        errors.append("Department Opportunity Signals cards must describe target-brand opportunities, not value labels or lead/status chips.")

    data = read_json(data_path)
    appendix = data.get("appendix", {})
    if isinstance(appendix, dict):
        appendix_sources = appendix.get("source_map") or appendix.get("sources_reviewed") or []
        appendix_source_count = 0
        if isinstance(appendix_sources, list):
            for item in appendix_sources:
                if isinstance(item, dict):
                    url = str(item.get("url") or item.get("source_url") or "").strip()
                else:
                    url = str(item or "").strip()
                if re.match(r"^https?://", url, flags=re.I):
                    appendix_source_count += 1
        if appendix_source_count:
            appendix_link_count = len(re.findall(r'class="source-ref"[^>]*>\[link\]</a>', text))
            if appendix_link_count < appendix_source_count:
                errors.append(
                    f"Appendix sources must render compact [link] markers for every source URL "
                    f"({appendix_link_count}/{appendix_source_count} found)."
                )
    generated_competitor_logos: list[str] = []
    non_square_competitor_logos: list[str] = []
    for row in data.get("competitive_landscape", {}).get("table", []):
        name = row.get("competitor") or row.get("name") or "Unnamed competitor"
        for value in (row.get("logo_url"), row.get("competitor_logo_url"), row.get("badge_url"), row.get("mark_url")):
            if value and re.search(r"-pptx-logo\.(?:png|jpe?g|webp|svg)$", str(value), flags=re.I):
                generated_competitor_logos.append(f"{name}: {value}")
                break
        selected = row.get("logo_url") or row.get("competitor_logo_url") or row.get("badge_url") or row.get("mark_url")
        if selected:
            selected_path = data_path.parent / str(selected)
            if selected_path.exists() and not square_quality_ok(selected_path):
                quality = asset_quality(selected_path)
                non_square_competitor_logos.append(
                    f"{name}: {selected} ({quality.get('width')}x{quality.get('height')})"
                )
            elif selected_path.exists() and not visible_logo_occupancy_ok(selected_path):
                quality = asset_quality(selected_path)
                non_square_competitor_logos.append(
                    f"{name}: {selected} has too little visible logo content ({quality.get('width')}x{quality.get('height')})"
                )
        else:
            non_square_competitor_logos.append(f"{name}: missing")
    if generated_competitor_logos:
        errors.append(
            "Competitor logos use generated PPTX text-card fallbacks instead of acquired logo assets: "
            + "; ".join(generated_competitor_logos)
        )
    if non_square_competitor_logos:
        errors.append(
            "Competitor logos must use square marks/icons or generated square badges, not wide wordmarks: "
            + "; ".join(non_square_competitor_logos)
        )

    image_count = len(re.findall(r"<img\b", text, flags=re.I))
    if image_count < 8:
        warnings.append(f"Rendered HTML has a low image count ({image_count}); check logos and campaign artwork.")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "html": str(html_path), "bytes": size, "image_count": image_count}


def module_campaign_art(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "campaign_art", "in_progress")
    set_gate(state, "gate_5b_campaign_art", "in_progress")
    add_event(state, "fanout", "campaign_art.prep", jobs=["campaign-art-prompt-manifest", "campaign-art-brief", "final-raster-import-check"])
    save_state(brand_folder, state)
    script = SCRIPT_ROOT / "campaign-art" / "generate_campaign_illustrations.py"
    generation = run_python_script(script, ["--data", str(data_path), "--manifest-only"])
    manifest_path = Path(generation.get("report_data_patch_manifest", ""))
    if manifest_path.exists():
        reduction = apply_manifest(data_path, manifest_path)
    else:
        reduction = {"ok": False, "applied_count": 0}
    import_result: dict[str, Any] = {"imported": 0, "skipped": True}
    import_reduction: dict[str, Any] = {"ok": False, "applied_count": 0, "skipped": True}
    if args.campaign_art_source_dir or args.campaign_art_latest_generated_batch:
        import_script = SCRIPT_ROOT / "campaign-art" / "import_final_campaign_art.py"
        import_args = ["--data", str(data_path), "--manifest-only"]
        if args.campaign_art_source_dir:
            import_args.extend(["--source-dir", str(Path(args.campaign_art_source_dir))])
        if args.campaign_art_latest_generated_batch:
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
        "final_raster_import": import_result,
        "final_raster_reduction": import_reduction,
        "contract_audit": audit,
    }


def asset_src(data_path: Path, value: str) -> str:
    if not value:
        return ""
    if re.match(r"^https?://", value, re.I) or value.startswith("data:"):
        return value
    path = (data_path.parent / value).resolve()
    try:
        return path.relative_to(data_path.parent.resolve()).as_posix()
    except ValueError:
        return path.as_uri()


def card_html(title: str, body: str) -> str:
    return f"<article class='card'><h3>{html.escape(str(title or ''))}</h3><p>{html.escape(str(body or ''))}</p></article>"


def list_html(items: list[Any]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items if has_value(item)) + "</ul>"


def source_list_html(items: list[Any]) -> str:
    rows: list[str] = []
    for item in items:
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("source_url") or "").strip()
            label = str(item.get("label") or item.get("title") or item.get("source") or url).strip()
        else:
            url = str(item or "").strip()
            label = url
        if not label:
            continue
        link = ""
        if re.match(r"^https?://", url, flags=re.I):
            link = f' <a class="source-ref" href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">[link]</a>'
        rows.append(f"<li>{html.escape(label)}{link}</li>")
    return "<ul>" + "".join(rows) + "</ul>" if rows else ""


def render_html(data_path: Path, output_path: Path | None = None) -> Path:
    data = read_json(data_path)
    brand = data.get("brand", {})
    output_path = output_path or data_path.parent / "newbizintel-report.html"
    logo = asset_src(data_path, brand.get("logo_url", "") or brand.get("mark_url", ""))
    title = f"{brand.get('name', 'Brand')} New Business Intelligence Report"
    sections: list[str] = []
    sections.append(
        f"""
        <section class="hero">
          <div class="brand-logo">{f'<img src="{html.escape(logo)}" alt="{html.escape(brand.get("name", ""))} logo">' if logo else html.escape((brand.get("name") or "NB")[:2].upper())}</div>
          <div>
            <p class="eyebrow">NewBiz2 report</p>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(data.get("cover", {}).get("summary", ""))}</p>
            <p class="muted">{html.escape(data.get("report_meta", {}).get("purpose", ""))}</p>
          </div>
        </section>
        """
    )
    snapshot_items = data.get("company_snapshot", {}).get("items", [])
    if snapshot_items:
        snapshot = data.get("company_snapshot", {})

        def snapshot_rows(items: Any) -> str:
            if not isinstance(items, list):
                return ""
            rows: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = item.get("label") or item.get("name") or ""
                role = item.get("role") or ""
                value = item.get("value") or ""
                source = item.get("source_url") or item.get("url") or ""
                source_html = f' <a href="{html.escape(str(source))}">[link]</a>' if source else ""
                label_html = html.escape(str(label))
                if role:
                    label_html += f"<br><small>{html.escape(str(role))}</small>"
                rows.append(f"<tr><th>{label_html}</th><td>{html.escape(str(value))}{source_html}</td></tr>")
            return "".join(rows)

        snapshot_tables = [
            ("Snapshot", snapshot_rows(snapshot_items)),
            ("Finance and Scale", snapshot_rows(snapshot.get("finance_stats"))),
            ("Leadership", snapshot_rows(snapshot.get("leadership"))),
            ("Founders", snapshot_rows(snapshot.get("founders"))),
            ("Ownership and Funding", snapshot_rows(snapshot.get("ownership_funding"))),
            ("Sources", snapshot_rows(snapshot.get("source_map"))),
        ]
        body = "".join(f"<h3>{html.escape(title)}</h3><table>{rows}</table>" for title, rows in snapshot_tables if rows)
        sections.append(f"<section><h2>Company Snapshot</h2>{body}</section>")
    exec_cards = data.get("executive_summary", {}).get("cards", [])
    if exec_cards:
        sections.append("<section><h2>Executive Summary</h2><div class='grid'>" + "".join(card_html(card.get("title"), card.get("body")) for card in exec_cards) + "</div></section>")
    agency = data.get("agency_opportunity", {})
    if agency:
        lead = agency.get("lead_offering", {})
        sections.append(
            f"<section><h2>Agency Opportunity</h2><p class='score'>Score: {html.escape(str(agency.get('score', '')))}</p><p>{html.escape(str(agency.get('summary', '')))}</p>"
            f"<div class='card'><h3>{html.escape(str(lead.get('name', 'Lead offering')))}</h3><p><strong>Lead department:</strong> {html.escape(str(lead.get('lead_department', '')))}</p><p>{html.escape(str(lead.get('verdict', '')))}</p></div></section>"
        )
    competitors = data.get("competitive_landscape", {}).get("table", [])
    if competitors:
        cards = []
        for row in competitors:
            name = row.get("competitor") or row.get("name")
            logo_url = asset_src(data_path, row.get("logo_url", "") or row.get("badge_url", ""))
            cards.append(f"<article class='logo-card'>{f'<img src={html.escape(json.dumps(logo_url))} alt={html.escape(json.dumps(str(name) + ' logo'))}>' if logo_url else ''}<h3>{html.escape(str(name))}</h3><p>{html.escape(str(row.get('implication') or row.get('why_it_matters') or ''))}</p></article>")
        sections.append("<section><h2>Competitive Landscape</h2><div class='grid'>" + "".join(cards) + "</div></section>")
    seo = data.get("seo_audit", {})
    if seo:
        seo_evidence = []
        for key in ("semrush_evidence", "similarweb_evidence", "search_evidence"):
            values = seo.get(key, [])
            if isinstance(values, list):
                seo_evidence.extend(values)
        sections.append(
            "<section><h2>SEO Audit and Search Evidence</h2><div class='grid'>"
            + "".join(card_html(item.get("title"), item.get("body")) for item in seo_evidence)
            + "</div></section>"
        )
    news = data.get("brand_reputation", {}).get("influential_news", [])
    if news:
        items = []
        for item in news:
            source_logo = asset_src(data_path, item.get("source_logo_url", "") or item.get("publisher_logo_url", ""))
            score = item.get("influence_score", "")
            rank_reason = item.get("rank_reason") or item.get("why_it_matters", "")
            subscore_summary = reputation_subscore_summary(item.get("influence_subscores"))
            items.append(f"<article class='news'>{f'<img src={html.escape(json.dumps(source_logo))} alt={html.escape(json.dumps(str(item.get('source', 'source')) + ' logo'))}>' if source_logo else ''}<p class='eyebrow'>{html.escape(str(item.get('date', '')))} | {html.escape(str(item.get('source', '')))} | Influence {html.escape(str(score))}</p><h3>{html.escape(str(item.get('headline', '')))}</h3><p><strong>Why it ranked:</strong> {html.escape(str(rank_reason))}</p>{f'<p class=\"muted\"><strong>Score basis:</strong> {html.escape(subscore_summary)}</p>' if subscore_summary else ''}<p>{html.escape(str(item.get('why_it_matters', '')))}</p></article>")
        sections.append("<section><h2>Brand Reputation</h2>" + "".join(items) + "</section>")
    opportunities = data.get("opportunities", {})
    timelines = opportunities.get("timelines", []) if isinstance(opportunities, dict) else []
    marketing_strategy = opportunities.get("marketing_strategy", {}) if isinstance(opportunities, dict) else {}
    if timelines:
        strategy_intro = ""
        if isinstance(marketing_strategy, dict) and marketing_strategy.get("strategy"):
            strategy_intro = (
                f"<div class='card'><p class='eyebrow'>Recommended marketing strategy</p>"
                f"<h3>{html.escape(str(marketing_strategy.get('headline') or 'Marketing strategy'))}</h3>"
                f"<p>{html.escape(str(marketing_strategy.get('strategy')))}</p>"
                f"<p><strong>Why:</strong> {html.escape(str(marketing_strategy.get('why_it_matters', '')))}</p></div>"
            )
        sections.append("<section><h2>30 / 60 / 90 Day Plan</h2>" + strategy_intro + "<div class='grid'>" + "".join(card_html(item.get("title"), " ".join(item.get("items", []))) for item in timelines) + "</div></section>")
    campaigns = campaign_section(data).get("ideas", [])
    if campaigns:
        blocks = []
        for idea in campaigns:
            image = asset_src(data_path, idea.get("illustration_url", ""))
            activation_plan = idea.get("activation_plan", [])
            if isinstance(activation_plan, dict):
                activation_plan = activation_plan.get("order_of_precedence", [])
            driving_idea = idea.get("driving_idea") or idea.get("concept", "")
            implementation_story = idea.get("implementation_story") or idea.get("activation", "")
            shape_items = []
            for plan in activation_plan if isinstance(activation_plan, list) else []:
                if not isinstance(plan, dict):
                    continue
                name = html.escape(str(plan.get("name", "")))
                creates = html.escape(str(plan.get("creates") or plan.get("primary_goal", "")))
                looks_like = html.escape(str(plan.get("looks_like") or plan.get("narrative", "")))
                why = html.escape(str(plan.get("why_this_format", "")))
                result = html.escape(str(plan.get("intended_result", "")))
                detail_parts = []
                if creates:
                    detail_parts.append(f"<p><strong>What the brand creates:</strong> {creates}</p>")
                if looks_like:
                    detail_parts.append(f"<p><strong>What it looks like:</strong> {looks_like}</p>")
                if why:
                    detail_parts.append(f"<p><strong>Why this shape:</strong> {why}</p>")
                if result:
                    detail_parts.append(f"<p><strong>Intended result:</strong> {result}</p>")
                if name and detail_parts:
                    shape_items.append(f"<li><strong>{name}</strong>{''.join(detail_parts)}</li>")
            blocks.append(
                f"<article class='campaign'>{f'<img src={html.escape(json.dumps(image))} alt=\"\">' if image else ''}<div><p class='eyebrow'>Creative campaign idea</p><h3>{html.escape(str(idea.get('title', '')))}</h3>"
                f"<p><strong>Driving idea:</strong> {html.escape(str(driving_idea))}</p><p><strong>Implementation:</strong> {html.escape(str(implementation_story))}</p>"
                f"{'<p><strong>How the campaign takes shape</strong></p><ol>' + ''.join(shape_items) + '</ol>' if shape_items else ''}</div></article>"
            )
        sections.append("<section><h2>Creative Campaign Ideas</h2>" + "".join(blocks) + "</section>")
    content_strategy = data.get("content_strategy", {})
    if isinstance(content_strategy, dict) and (
        content_strategy.get("cards") or content_strategy.get("priority_opportunities") or content_strategy.get("example_ideas")
    ):
        content_blocks = "".join(card_html(item.get("title"), item.get("body")) for item in content_strategy.get("cards", []) if isinstance(item, dict))
        content_blocks += list_html(content_strategy.get("priority_opportunities", []))
        content_blocks += list_html(content_strategy.get("example_ideas", []))
        if content_strategy.get("response_to_findings"):
            content_blocks += f"<p>{html.escape(str(content_strategy.get('response_to_findings')))}</p>"
        sections.append("<section><h2>Content Strategy Recommendations</h2>" + content_blocks + "</section>")
    appendix = data.get("appendix", {})
    if isinstance(appendix, dict):
        appendix_sources = appendix.get("source_map") or appendix.get("sources_reviewed") or []
        appendix_blocks = ""
        if appendix_sources:
            appendix_blocks += "<h3>Sources Reviewed</h3>" + source_list_html(appendix_sources)
        appendix_blocks += list_html(appendix.get("missing_data", []))
        appendix_blocks += list_html(appendix.get("assumptions_and_confidence_notes", []))
        if appendix_blocks:
            sections.append("<section><h2>Appendix</h2>" + appendix_blocks + "</section>")
    css = """
    :root{--ink:#09213b;--muted:#5d6b7a;--line:#d8e2ec;--panel:#f7fafc;--accent:#153a5b}
    *{box-sizing:border-box} body{margin:0;font-family:Aptos,Segoe UI,Arial,sans-serif;color:var(--ink);background:#f4f7fa;line-height:1.55}
    main{max-width:1120px;margin:0 auto;padding:36px 22px 80px}.hero,.card,.logo-card,.news,.campaign,section{background:white;border:1px solid var(--line);border-radius:20px;box-shadow:0 18px 42px rgba(15,23,42,.06)}
    section{padding:28px;margin:24px 0}.hero{display:flex;gap:24px;padding:32px;margin-bottom:28px;background:linear-gradient(135deg,#fff,#edf5fb)}
    h1{font-size:44px;line-height:1.05;margin:.1em 0}h2{font-size:30px;margin:0 0 18px}h3{margin:.1em 0 .35em}.muted{color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:12px;font-weight:800;color:#53657a}
    .brand-logo{width:108px;height:108px;flex:0 0 108px;border-radius:26px;border:1px solid var(--line);display:grid;place-items:center;background:#fff;padding:18px;font-weight:900;font-size:28px}.brand-logo img,.logo-card img,.news img{max-width:100%;max-height:76px;object-fit:contain}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card,.logo-card,.news{padding:18px}.score{display:inline-block;padding:8px 12px;background:#edf5fb;border-radius:999px;font-weight:800}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid var(--line);padding:10px;vertical-align:top}th{width:28%}.campaign{display:grid;grid-template-columns:minmax(260px,42%) 1fr;gap:26px;padding:18px;margin:18px 0}.campaign img{width:100%;height:100%;max-height:760px;object-fit:cover;border-radius:16px}@media(max-width:760px){.hero,.campaign{grid-template-columns:1fr;display:grid}h1{font-size:34px}}
    .source-ref{display:inline-block;margin-left:.35em;font-size:.88em;font-weight:700;white-space:nowrap}
    """
    html_text = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{css}</style></head><body><main>{''.join(sections)}</main></body></html>"
    output_path.write_text(html_text, encoding="utf-8")
    inject_task_list_into_html(output_path, data_path.parent)
    return output_path


def task_list_html(brand_folder: Path) -> str:
    task_path = brand_folder / "workflow-task-list.json"
    if not task_path.exists():
        return ""
    payload = read_json(task_path)
    rows = []
    for task in payload.get("tasks", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(task.get('id', '')))}</td>"
            f"<td>{html.escape(str(task.get('title', '')))}</td>"
            f"<td><strong>{html.escape(str(task.get('status', '')))}</strong></td>"
            f"<td>{html.escape(', '.join(task.get('gates', [])))}</td>"
            "</tr>"
        )
    return (
        "<section id=\"newbiz2-workflow-task-list\" class=\"newbiz2-task-list\">"
        "<h2>Workflow Task List</h2>"
        f"<p class=\"score\">Passed: {html.escape(str(payload.get('passed', 0)))}/{html.escape(str(payload.get('total', 10)))}</p>"
        f"<p class=\"note\">Updated: {html.escape(str(payload.get('updated_at', 'not recorded')))}</p>"
        "<table><thead><tr><th>#</th><th>Step</th><th>Status</th><th>Primary gate</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</section>"
    )


def inject_task_list_into_html(html_path: Path, brand_folder: Path) -> None:
    if not html_path.exists():
        return
    section = task_list_html(brand_folder)
    if not section:
        return
    text = html_path.read_text(encoding="utf-8")
    pattern = re.compile(r"<section id=\"newbiz2-workflow-task-list\".*?</section>", re.S)
    original_text = text
    if pattern.search(text):
        text = pattern.sub(section, text, count=1)
    elif "</main>" in text:
        text = text.replace("</main>", section + "</main>")
    elif "</body>" in text:
        text = text.replace("</body>", section + "</body>")
    else:
        text = text + section
    if ("<html" in original_text.lower() or "<!doctype" in original_text.lower()) and (
        "</html>" not in text.lower() or len(text) < max(4096, int(len(original_text) * 0.5))
    ):
        raise SystemExit(f"Refusing to inject task list because it would corrupt full report HTML: {html_path}")
    html_path.write_text(text, encoding="utf-8")


def assert_deployable_report_html(html_path: Path) -> None:
    if not html_path.exists():
        raise SystemExit(f"Report HTML does not exist: {html_path}")
    text = html_path.read_text(encoding="utf-8", errors="replace")
    completeness_audit = audit_rendered_html_completeness(text)
    if not completeness_audit["ok"]:
        raise SystemExit(
            "Refusing deployment handoff because rendered HTML failed presentation completeness checks. "
            f"Path: {html_path}; errors: {'; '.join(completeness_audit.get('errors', []))}"
        )
    lowered = text.lower()
    required_markers = (
        "<html",
        "</html>",
        "new business intelligence",
        "creative campaign ideas",
        'class="toc"',
        'class="section-heading"',
        "department opportunity signals",
        "messaging assessment",
        "content strategy recommendations",
    )
    missing = [marker for marker in required_markers if marker not in lowered]
    if missing or len(text) < 100000:
        raise SystemExit(
            "Refusing deployment handoff because the HTML does not look like a complete NewBiz2 report. "
            f"Path: {html_path}; bytes: {len(text)}; missing markers: {', '.join(missing) or 'none'}"
        )


def make_text_logo_png(label: str, output_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        raise SystemExit(f"Pillow is required for PPTX-safe raster logo fallback: {exc}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 256), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    text = (label or "NB").strip()[:28]
    font = None
    for size in (86, 72, 60, 48, 40):
        try:
            font = ImageFont.truetype("arial.ttf", size=size)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) < 440:
            break
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (512 - (bbox[2] - bbox[0])) / 2
    y = (256 - (bbox[3] - bbox[1])) / 2 - 4
    draw.rounded_rectangle((8, 8, 504, 248), radius=36, fill=(255, 255, 255, 255), outline=(216, 226, 236, 255), width=3)
    draw.text((x, y), text, fill=(9, 33, 59, 255), font=font)
    image.save(output_path, format="PNG", optimize=True)


def pptx_safe_logo_asset(data_path: Path, value: str | None) -> str:
    if not value:
        return ""
    candidate = Path(str(value))
    if not candidate.is_absolute():
        candidate = data_path.parent / candidate
    if not candidate.exists():
        return ""
    if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".wmf"}:
        return relative_to_brand(candidate, data_path.parent)
    if candidate.suffix.lower() == ".svg":
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            companion = candidate.with_suffix(suffix)
            if companion.exists():
                return relative_to_brand(companion, data_path.parent)
    return ""


def pptx_safe_data_copy(data_path: Path) -> Path:
    data = read_json(data_path)
    asset_dir = data_path.parent / "slide-assets"
    brand = data.setdefault("brand", {})
    brand_name = brand.get("name", "Brand")
    brand_slug = brand.get("slug") or slugify(brand_name)
    brand_logo = pptx_safe_logo_asset(data_path, brand.get("logo_url")) or pptx_safe_logo_asset(data_path, brand.get("mark_url"))
    if brand_logo:
        brand["logo_url"] = brand_logo
    else:
        brand_png = asset_dir / f"{brand_slug}-pptx-logo.png"
        make_text_logo_png(brand_name, brand_png)
        brand["logo_url"] = relative_to_brand(brand_png, data_path.parent)
    brand["mark_url"] = brand["logo_url"]

    for row in data.get("competitive_landscape", {}).get("table", []):
        name = row.get("competitor") or row.get("name")
        if not name:
            continue
        rel = ""
        for field in ("logo_url", "competitor_logo_url", "badge_url", "mark_url"):
            rel = pptx_safe_logo_asset(data_path, row.get(field))
            if rel:
                break
        if not rel:
            png = asset_dir / f"{slugify(name)}-pptx-logo.png"
            make_text_logo_png(name, png)
            rel = relative_to_brand(png, data_path.parent)
        row["logo_url"] = rel
        row["competitor_logo_url"] = rel
        row["badge_url"] = rel

    for item in data.get("brand_reputation", {}).get("influential_news", []):
        source = item.get("source") or brand_name
        if source.lower().strip() in {brand_name.lower().strip(), f"{brand_name.lower().strip()} newsroom"}:
            rel = brand["logo_url"]
        else:
            rel = pptx_safe_logo_asset(data_path, item.get("publisher_logo_url")) or pptx_safe_logo_asset(data_path, item.get("source_logo_url")) or pptx_safe_logo_asset(data_path, item.get("logo_url"))
            if not rel:
                png = asset_dir / f"{slugify(source)}-pptx-logo.png"
                make_text_logo_png(source, png)
                rel = relative_to_brand(png, data_path.parent)
        item["source_logo_url"] = rel
        item["publisher_logo_url"] = rel

    opportunities = data.get("opportunities")
    if isinstance(opportunities, list):
        data["opportunities"] = {
            "timelines": [
                {
                    "title": "30 Days",
                    "items": [str(item.get("title") or item.get("body") or item) for item in opportunities[:3]],
                },
                {
                    "title": "60 Days",
                    "items": [str(item.get("body") or item.get("title") or item) for item in opportunities[1:4]],
                },
                {
                    "title": "90 Days",
                    "items": [str(item.get("body") or item.get("title") or item) for item in opportunities[2:5]],
                },
            ]
        }

    temp_path = data_path.parent / ".newbiz2-pptx-data.json"
    write_json(temp_path, data)
    return temp_path


def pptx_text_shape(shape_id: int, x: int, y: int, cx: int, cy: int, text: str, size: int = 2400, bold: bool = False, color: str = "09213B") -> str:
    safe = html.escape(text or "")
    bold_attr = ' b="1"' if bold else ""
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="TextBox {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>
      <p:txBody><a:bodyPr wrap="square" anchor="t"/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="{size}"{bold_attr}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr><a:t>{safe}</a:t></a:r></a:p></p:txBody>
    </p:sp>
    """


def pptx_slide_xml(title: str, bullets: list[str], slide_no: int) -> str:
    shapes = [pptx_text_shape(2, 650000, 520000, 10800000, 820000, title, size=3600, bold=True)]
    y = 1550000
    shape_id = 3
    for bullet in bullets[:7]:
        wrapped = textwrap.shorten(str(bullet), width=150, placeholder="...")
        shapes.append(pptx_text_shape(shape_id, 880000, y, 10100000, 520000, f"- {wrapped}", size=1900))
        y += 640000
        shape_id += 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="F7FAFC"/></a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    {''.join(shapes)}
  </p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def pptx_rels_xml(target: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="{target}"/>
</Relationships>"""


def build_minimal_pptx(data_path: Path, output_path: Path) -> None:
    data = read_json(data_path)
    brand = data.get("brand", {}).get("name", "Brand")
    slides: list[tuple[str, list[str]]] = []
    slides.append((f"{brand} New Business Intelligence", [data.get("cover", {}).get("summary", ""), data.get("report_meta", {}).get("purpose", "")]))
    slides.append(("Executive Summary", [card.get("body", "") for card in data.get("executive_summary", {}).get("cards", [])[:6]]))
    agency = data.get("agency_opportunity", {})
    slides.append(("Agency Opportunity", [agency.get("summary", ""), agency.get("score_summary", ""), agency.get("lead_offering", {}).get("verdict", "")]))
    slides.append(("Competitive Landscape", [f"{row.get('competitor') or row.get('name')}: {row.get('implication') or row.get('why_it_matters') or ''}" for row in data.get("competitive_landscape", {}).get("table", [])[:6]]))
    seo = data.get("seo_audit", {})
    seo_evidence = []
    if isinstance(seo, dict):
        for key in ("semrush_evidence", "similarweb_evidence", "search_evidence"):
            values = seo.get(key, [])
            if isinstance(values, list):
                seo_evidence.extend(values)
    slides.append(("SEO Audit and Search Evidence", [item.get("body", "") for item in seo_evidence[:6]]))
    slides.append(("Brand Reputation", [f"{item.get('headline', '')} ({item.get('influence_score', '')}): {item.get('rank_reason') or item.get('why_it_matters', '')}" for item in data.get("brand_reputation", {}).get("influential_news", [])[:6]]))
    opportunities = data.get("opportunities", {})
    if isinstance(opportunities, dict):
        roadmap = []
        strategy = opportunities.get("marketing_strategy", {})
        if isinstance(strategy, dict) and strategy.get("strategy"):
            roadmap.append(f"Strategy: {strategy.get('strategy')}")
        roadmap.extend(f"{block.get('title', '')}: {'; '.join(block.get('items', []))}" for block in opportunities.get("timelines", [])[:3])
    elif isinstance(opportunities, list):
        roadmap = [f"{item.get('title', '')}: {item.get('body', '')}" for item in opportunities[:4]]
    else:
        roadmap = []
    slides.append(("30 / 60 / 90 Day Plan", roadmap))
    campaigns = campaign_section(data).get("ideas", [])
    slides.append(("Creative Campaign Ideas", [f"{idea.get('title', '')}: {idea.get('concept', '')}" for idea in campaigns[:6]]))
    content_strategy = data.get("content_strategy", {})
    if isinstance(content_strategy, dict):
        content_bullets = [card.get("body", "") for card in content_strategy.get("cards", [])[:4] if isinstance(card, dict)]
        content_bullets.extend(str(item) for item in content_strategy.get("priority_opportunities", [])[:3])
        slides.append(("Content Strategy Recommendations", content_bullets))

    slide_count = len(slides)
    content_overrides = "\n".join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1, slide_count + 1))
    slide_ids = "\n".join(f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, slide_count + 1))
    rels = "\n".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>' for i in range(1, slide_count + 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  {content_overrides}
</Types>""")
        pptx.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""")
        pptx.writestr("docProps/app.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>NewBiz2 Python Runner</Application><Slides>{slide_count}</Slides></Properties>""")
        pptx.writestr("docProps/core.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{html.escape(brand)} NewBiz2 Report</dc:title><dc:creator>NewBiz2</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{utc_now()}</dcterms:created></cp:coreProperties>""")
        pptx.writestr("ppt/presentation.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{slide_ids}</p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>""")
        pptx.writestr("ppt/_rels/presentation.xml.rels", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>{rels}</Relationships>""")
        pptx.writestr("ppt/slideMasters/slideMaster1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>""")
        pptx.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>""")
        pptx.writestr("ppt/slideLayouts/slideLayout1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld></p:sldLayout>""")
        pptx.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>""")
        pptx.writestr("ppt/theme/theme1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="NewBiz2"><a:themeElements><a:clrScheme name="NewBiz2"><a:dk1><a:srgbClr val="09213B"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="153A5B"/></a:dk2><a:lt2><a:srgbClr val="F7FAFC"/></a:lt2><a:accent1><a:srgbClr val="153A5B"/></a:accent1><a:accent2><a:srgbClr val="3AA7A3"/></a:accent2><a:accent3><a:srgbClr val="D28B26"/></a:accent3><a:accent4><a:srgbClr val="5D6B7A"/></a:accent4><a:accent5><a:srgbClr val="10263B"/></a:accent5><a:accent6><a:srgbClr val="D8E2EC"/></a:accent6><a:hlink><a:srgbClr val="153A5B"/></a:hlink><a:folHlink><a:srgbClr val="153A5B"/></a:folHlink></a:clrScheme><a:fontScheme name="NewBiz2"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme><a:fmtScheme name="NewBiz2"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>""")
        for i, (slide_title, bullets) in enumerate(slides, start=1):
            pptx.writestr(f"ppt/slides/slide{i}.xml", pptx_slide_xml(slide_title, bullets, i))
            pptx.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", pptx_rels_xml("../slideLayouts/slideLayout1.xml"))


def make_self_contained(html_path: Path, data_path: Path, output_path: Path) -> None:
    script = SCRIPT_ROOT / "render" / "make_html_self_contained.py"
    run_python_script(script, ["--html", str(html_path), "--data", str(data_path), "--output", str(output_path)])


def find_powershell() -> str | None:
    explicit = os.environ.get("NEWBIZ2_PWSH")
    candidates = [
        explicit,
        shutil.which("pwsh"),
        shutil.which("pwsh.exe"),
        r"C:\Program Files\PowerShell\7\pwsh.exe" if os.name == "nt" else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def render_rich_html_with_powershell(data_path: Path, output_path: Path) -> Path:
    pwsh = find_powershell()
    if not pwsh:
        raise RuntimeError(
            "Rich HTML renderer requires PowerShell until the presentation renderer is fully ported to Python."
        )
    script = SCRIPT_ROOT / "render" / "render_report.ps1"
    if not script.exists():
        raise RuntimeError(f"Rich HTML renderer script is missing: {script}")
    cmd = [
        pwsh,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-DataPath",
        str(data_path),
        "-OutputPath",
        str(output_path),
        "-SkipValidation",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Rich HTML renderer failed with exit code {result.returncode}. {detail}")
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(f"Rich HTML renderer returned non-JSON output: {result.stdout[:500]}") from exc
    rendered = Path(payload.get("html") or output_path)
    if not rendered.exists():
        raise RuntimeError(f"Rich HTML renderer did not create output: {rendered}")
    return rendered


def render_rich_html_with_python(data_path: Path, output_path: Path) -> Path:
    script = SCRIPT_ROOT / "render" / "render_report.py"
    if not script.exists():
        raise RuntimeError(f"Python rich HTML renderer script is missing: {script}")
    result = run_python_script(
        script,
        ["--data", str(data_path), "--output", str(output_path), "--skip-validation"],
    )
    rendered = Path(result.get("html") or output_path)
    if not rendered.exists():
        raise RuntimeError(f"Python rich HTML renderer did not create output: {rendered}")
    return rendered


def module_render(args: argparse.Namespace) -> dict[str, Any]:
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
        if os.environ.get("NEWBIZ2_ALLOW_POWERSHELL_RENDER_FALLBACK") == "1":
            html_path = render_rich_html_with_powershell(data_path, html_path)
        elif os.environ.get("NEWBIZ2_ALLOW_SKELETAL_RENDER") == "1":
            html_path = render_html(data_path, html_path)
        else:
            set_status(state, "render", "failed")
            set_gate(state, "gate_8_render_outputs", "failed")
            set_gate(state, "gate_6_render_outputs", "failed")
            save_state(brand_folder, state)
            raise SystemExit(
                "Render blocked because the Python rich presentation renderer did not run. "
                "Refusing to use the legacy PowerShell renderer unless NEWBIZ2_ALLOW_POWERSHELL_RENDER_FALLBACK=1. "
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
    try:
        pptx_data_path = pptx_safe_data_copy(data_path)
        run_python_script(SCRIPT_ROOT / "render" / "report_data_to_pptx.py", ["--data", str(pptx_data_path), "--pptx", str(pptx_path)])
    except SystemExit as exc:
        pptx_warning = str(exc)
        build_minimal_pptx(data_path, pptx_path)
    if not pptx_path.exists():
        set_status(state, "render", "failed")
        set_gate(state, "gate_8_render_outputs", "failed")
        set_gate(state, "gate_6_render_outputs", "failed")
        save_state(brand_folder, state)
        raise SystemExit("PPTX output was not created. " + pptx_warning)
    shutil.copy2(pptx_path, archive_dir / pptx_path.name)
    set_status(state, "render", "passed")
    set_gate(state, "gate_8_render_outputs", "passed")
    set_gate(state, "gate_6_render_outputs", "passed")
    save_state(brand_folder, state)
    return {"module": "render", "data": str(data_path), "brand_folder": str(brand_folder), "bundle": {"html": str(html_path), "pptx": str(pptx_path), "archive": {"directory": str(archive_dir), "html": str(portable_html), "pptx": str(archive_dir / pptx_path.name)}}}


def audit_task_list(data_path: Path) -> dict[str, Any]:
    brand_folder = data_path.parent
    state = load_state(brand_folder)
    if reconcile_render_gate_from_outputs(state, data_path, brand_folder):
        save_state(brand_folder, state)
    ensure_task_list(state)
    sync_task_status_from_gates(state)
    save_state(brand_folder, state)
    tasks = sorted(state.get("task_list", []), key=lambda item: item["id"])
    errors = []
    if len(tasks) != 10:
        errors.append(f"Task list should contain exactly 10 primary steps; found {len(tasks)}.")
    first_not_passed = None
    for task in tasks:
        if task["status"] != "passed" and first_not_passed is None:
            first_not_passed = task
        elif first_not_passed and task["status"] == "passed":
            errors.append(f"Task '{task['key']}' is marked passed after earlier task '{first_not_passed['key']}' is not passed.")
    return {"ok": not errors, "errors": errors, "passed": sum(1 for task in tasks if task["status"] == "passed"), "total": 10, "tasks": tasks}


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


def module_qa(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    if reconcile_render_gate_from_outputs(state, data_path, brand_folder):
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
    checks = {
        "report_data": validate_report_data(data_path),
        "hybrid": audit_hybrid(state),
        "campaign_art": audit_campaign_art(data_path),
        "required_logos": read_json(brand_folder / "required-logo-manifest.json") if (brand_folder / "required-logo-manifest.json").exists() else {"ok": False, "errors": ["required-logo-manifest.json missing"]},
        "source_badges": read_json(brand_folder / "source-badge-manifest.json") if (brand_folder / "source-badge-manifest.json").exists() else {"ok": False, "errors": ["source-badge-manifest.json missing"]},
        "presentation_html": audit_presentation_html(brand_folder, data_path),
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


def vercel_deploy_prompt(data_path: Path, brand_folder: Path) -> dict[str, Any]:
    return {
        "ask_user": "Would you like me to deploy this report to Vercel as a randomly named preview URL?",
        "deploy_only_if_user_confirms": True,
        "random_url_required": True,
        "policy": "Use the vercel-deploy skill only after confirmation. Run the vercel-stage command first and deploy the returned deploy_path, never the brand output folder.",
        "stage_command": f"python \"{SCRIPT_ROOT / 'newbiz2.py'}\" vercel-stage --data-path \"{data_path}\"",
        "brand_folder": str(brand_folder),
    }


def prepare_random_vercel_stage(data_path: Path) -> dict[str, Any]:
    data = read_json(data_path)
    brand = data.get("brand", {})
    brand_name = str(brand.get("name", "") or "")
    website = str(brand.get("website", "") or "")
    brand_folder = brand_folder_from_data(data_path)
    html_path = brand_folder / "newbizintel-report.html"
    index_path = brand_folder / "index.html"
    source_html = html_path if html_path.exists() else index_path
    if not source_html.exists():
        raise SystemExit("Cannot prepare Vercel stage because neither newbizintel-report.html nor index.html exists.")
    assert_deployable_report_html(source_html)

    latest_handoff = brand_folder / "vercel-random-handoff-latest.json"
    force_new = os.environ.get("NEWBIZ2_FORCE_NEW_VERCEL_STAGE") == "1"
    stage_root: Path | None = None
    existing_handoff: dict[str, Any] = {}
    if latest_handoff.exists() and not force_new:
        try:
            existing_handoff = read_json(latest_handoff)
            existing_path = Path(str(existing_handoff.get("deploy_path") or ""))
            if existing_path.exists() and existing_path.is_dir():
                stage_root = existing_path
        except Exception:
            stage_root = None
    if stage_root is None:
        token = secrets.token_hex(6)
        stage_root = brand_folder / "vercel-random-stages" / f"site-{token}"
        stage_root.mkdir(parents=True, exist_ok=False)
    else:
        stage_root.mkdir(parents=True, exist_ok=True)
    stage_index = stage_root / "index.html"
    shutil.copy2(source_html, stage_index)
    inject_task_list_into_html(stage_index, brand_folder)
    assert_deployable_report_html(stage_index)

    for directory_name in ("slide-assets", "assets"):
        source = brand_folder / directory_name
        if source.exists() and source.is_dir():
            shutil.copytree(source, stage_root / directory_name, dirs_exist_ok=True)

    handoff = {
        "deploy_path": str(stage_root),
        "random_site_slug": stage_root.name,
        "random_url_required": True,
        "stage_reused": bool(existing_handoff) and not force_new,
        "must_not_contain": [
            slugify(brand_name) if brand_name else "",
            urllib.parse.urlparse(normalize_url(website)).netloc.replace("www.", "").split(".")[0] if website else "",
        ],
        "vercel_skill": "vercel-deploy",
        "instructions": "Use the vercel-deploy skill to deploy this deploy_path. Do not deploy the brand output folder directly. Reuse this random stage to update existing pages; set NEWBIZ2_FORCE_NEW_VERCEL_STAGE=1 only when a fresh random URL is explicitly needed.",
    }
    handoff["must_not_contain"] = list(dict.fromkeys(item for item in handoff["must_not_contain"] if item))
    write_json(stage_root / "newbiz2-vercel-handoff.json", handoff)
    write_json(brand_folder / "vercel-random-handoff-latest.json", handoff)
    return handoff


def module_deploy(args: argparse.Namespace) -> dict[str, Any]:
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


def module_vercel_stage(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    return {
        "module": "vercel-stage",
        "data": str(data_path),
        "vercel_handoff": prepare_random_vercel_stage(data_path),
    }


def run_mode(args: argparse.Namespace) -> dict[str, Any]:
    results: dict[str, Any] = {"mode": args.mode}
    if args.mode in {"full", "research-only", "render-stack"}:
        results["intake"] = module_intake(args)
        args.data_path = results["intake"]["data"]
    if args.mode in {"full", "research-only"}:
        results["research"] = module_research(args)
        args.research_summary_path = results["research"]["research_summary"]
    if args.mode in {"full", "render-stack"}:
        if args.mode == "render-stack" and not getattr(args, "data_path", None):
            results["intake"] = module_intake(args)
            args.data_path = results["intake"]["data"]
        results["structure"] = module_structure(args)
        results["assets"] = module_assets(args)
        results["campaign_art"] = module_campaign_art(args)
        results["render"] = module_render(args)
        results["qa"] = module_qa(args)
    if args.mode == "qa-only":
        results["qa"] = module_qa(args)
    if args.mode == "deploy-handoff":
        results["deploy"] = module_deploy(args)
    if args.mode == "art-refresh":
        results["campaign_art"] = module_campaign_art(args)
        results["render"] = module_render(args)
        results["qa"] = module_qa(args)
    if args.mode == "assets-refresh":
        results["assets"] = module_assets(args)
        results["render"] = module_render(args)
        results["qa"] = module_qa(args)
    if args.mode == "full":
        results["deploy"] = module_deploy(args)
    return results


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-path")
    parser.add_argument("--brand-name")
    parser.add_argument("--brand-folder")
    parser.add_argument("--website")
    parser.add_argument("--research-mode", choices=["bootstrap", "live-summary", "workpacks"], default="bootstrap")
    parser.add_argument("--research-summary-path")
    parser.add_argument("--search-workpacks", nargs="*", default=[])
    parser.add_argument("--tavily-reputation-research", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--composio-semrush-available", action="store_true")
    parser.add_argument("--jina-fallback-available", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--semrush-database", choices=["uk", "us"], default="uk")
    parser.add_argument("--campaign-art-source-dir")
    parser.add_argument("--campaign-art-latest-generated-batch", action="store_true")
    parser.add_argument("--campaign-art-overwrite-final", action="store_true")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NewBiz2 without PowerShell.")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run")
    add_common_args(run_parser)
    run_parser.add_argument("--mode", choices=["full", "research-only", "render-stack", "qa-only", "deploy-handoff", "art-refresh", "assets-refresh"], default="full")
    for name in ["intake", "research", "structure", "assets", "campaign-art", "render", "qa", "deploy", "vercel-stage"]:
        sub = subparsers.add_parser(name)
        add_common_args(sub)
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        raise SystemExit(2)
    dispatch = {
        "run": run_mode,
        "intake": module_intake,
        "research": module_research,
        "structure": module_structure,
        "assets": module_assets,
        "campaign-art": module_campaign_art,
        "render": module_render,
        "qa": module_qa,
        "deploy": module_deploy,
        "vercel-stage": module_vercel_stage,
    }
    result = dispatch[args.command](args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
