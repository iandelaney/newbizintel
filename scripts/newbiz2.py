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
        "legacy_gates": ["gate_3a_semrush", "gate_4_semrush_seo_evidence"],
        "trust_test": "At least two SEO evidence points are available, with SEMrush status explicitly recorded as passed, partial, quota-limited, or blocked.",
    },
    {
        "id": 5,
        "key": "report_structure",
        "title": "Report structure and data contract",
        "gates": ["gate_5_report_structure"],
        "legacy_gates": ["gate_4_report_data"],
        "trust_test": "report-data.json passes schema validation and freshness is updated.",
    },
    {
        "id": 6,
        "key": "logos_and_assets",
        "title": "Brand, competitor, and source logos",
        "gates": ["gate_6_logos_and_assets"],
        "legacy_gates": ["gate_5_assets", "gate_5a_source_badges", "gate_5b_required_logos"],
        "trust_test": "Brand, competitor, and news/source logos resolve without generic fallbacks; competitor badges prefer square marks/icons, with wide wordmarks converted to square initial-letter marks.",
    },
    {
        "id": 7,
        "key": "campaign_ideas_and_art",
        "title": "Creative campaign ideas and artwork",
        "gates": ["gate_7_campaign_ideas_and_art"],
        "legacy_gates": ["gate_5b_campaign_art"],
        "trust_test": "Campaign ideas pass editorial checks and artwork is final raster, not scaffold.",
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
        "trust_test": "Deploy handoff folder is refreshed from the latest report outputs.",
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
    for definition in TASK_DEFINITIONS:
        primary = definition["gates"][0]
        aliases = definition.get("legacy_gates") or []
        if gates.get(primary) and gates.get(primary) not in {"pending", "in_progress"}:
            names = [primary]
        else:
            names = aliases or [primary]
        gates[primary] = gate_status_from_aliases(state, names)


def ensure_task_list(state: dict[str, Any]) -> None:
    sync_primary_gates(state)
    existing = {task.get("key"): task for task in state.get("task_list", []) if isinstance(task, dict)}
    tasks = []
    for definition in TASK_DEFINITIONS:
        old = existing.get(definition["key"], {})
        task = copy.deepcopy(definition)
        task["status"] = old.get("status", "pending")
        task["evidence"] = old.get("evidence", [])
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
    write_json(brand_folder / "run-state.json", state)
    tasks = sorted(state["task_list"], key=lambda item: item["id"])
    payload = {
        "ok": True,
        "total": len(tasks),
        "passed": sum(1 for task in tasks if task["status"] == "passed"),
        "gates": state.get("gates", {}),
        "tasks": tasks,
    }
    write_json(brand_folder / "workflow-task-list.json", payload)
    lines = [
        "# NewBiz2 Workflow Task List",
        "",
        f"Passed: {payload['passed']}/{payload['total']}",
        "",
        "| # | Step | Status | Primary gate | Trust test |",
        "|---:|---|---|---|---|",
    ]
    for task in tasks:
        gate_text = ", ".join(task["gates"])
        trust = str(task["trust_test"]).replace("|", "\\|")
        lines.append(f"| {task['id']} | {task['title']} | {task['status']} | {gate_text} | {trust} |")
    (brand_folder / "workflow-task-list.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    state.setdefault("gates", {})[gate] = status
    sync_primary_gates(state)


def set_status(state: dict[str, Any], module: str, status: str) -> None:
    state.setdefault("status", {})[module] = status


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


def validate_report_data(data_path: Path) -> dict[str, Any]:
    data = read_json(data_path)
    errors: list[str] = []
    warnings: list[str] = []
    required = [
        "brand.name",
        "brand.website",
        "report_meta.audience",
        "report_meta.distribution",
        "report_meta.purpose",
        "agency_opportunity.score",
        "agency_opportunity.summary",
        "agency_opportunity.lead_offering.name",
        "agency_opportunity.lead_offering.lead_department",
        "usp_ksp_review.score",
        "seo_audit.cards",
        "seo_audit.semrush_evidence",
        "seo_audit.priority_issues",
        "brand_reputation.influential_news",
    ]
    for path in required:
        ensure_path(data, path, errors)
    semrush = data.get("seo_audit", {}).get("semrush_evidence", [])
    if len(semrush) < 2:
        errors.append(f"seo_audit.semrush_evidence must include at least 2 SEO evidence points. Current count: {len(semrush)}")
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
    if errors:
        return {"ok": False, "data": str(data_path), "errors": errors, "warnings": warnings}
    return {"ok": True, "data": str(data_path), "warnings": warnings}


def first_items(value: Any, limit: int = 3) -> list[Any]:
    if isinstance(value, list):
        return value[:limit]
    return []


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
    semrush = data.get("seo_audit", {}).get("semrush_evidence", [])
    source_map = data.get("appendix", {}).get("source_map") or data.get("appendix", {}).get("sources_reviewed") or []
    status = {
        "competitor_discovery": "passed" if competitors else "pending",
        "recent_news": "passed" if news else "pending",
        "reputation_public_web": "passed" if data.get("brand_reputation") else "pending",
        "source_gathering": "passed" if source_map or news else "pending",
        "semrush": "passed" if len(semrush) >= 2 else "quota-limited",
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


def validate_research_summary(summary: dict[str, Any]) -> dict[str, Any]:
    errors = []
    warnings = []
    status = summary.get("status", {})
    for key in ("competitor_discovery", "recent_news", "reputation_public_web", "source_gathering", "semrush"):
        if key not in status:
            errors.append(f"Missing status.{key}")
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
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def module_research(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "research", "in_progress")
    set_gate(state, "gate_2_competitors", "in_progress")
    set_gate(state, "gate_3_research", "in_progress")
    set_gate(state, "gate_3a_semrush", "in_progress")
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

    if args.research_mode == "live-summary":
        if not args.research_summary_path:
            raise SystemExit("--research-mode live-summary requires --research-summary-path.")
        summary = read_json(Path(args.research_summary_path).expanduser().resolve())
    else:
        summary = build_summary_from_data(data_path)
    validation = validate_research_summary(summary)
    if not validation["ok"]:
        set_status(state, "research", "failed")
        set_gate(state, "gate_2_competitors", "failed")
        set_gate(state, "gate_3_research", "failed")
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
    save_state(brand_folder, state)
    return {"module": "research", "data": str(data_path), "brand_folder": str(brand_folder), "research_summary": str(summary_path), "validation": validation}


def merge_research_into_data(data: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("competitors"):
        data.setdefault("competitive_landscape", {})["table"] = summary["competitors"]
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
        data = merge_research_into_data(data, read_json(summary_path))
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


def acquire_logo(name: str, website: str, destination: Path, candidates: list[str] | None = None) -> tuple[bool, str]:
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
    urls = list(candidates or [])
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


def patch_assets(data: dict[str, Any], brand_folder: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    asset_dir = brand_folder / "slide-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"ok": True, "asset_directory": str(asset_dir), "brand": {}, "competitors": [], "news_sources": [], "errors": []}

    brand = data.setdefault("brand", {})
    brand_name = brand.get("name", "brand")
    brand_slug = brand.get("slug") or slugify(brand_name)
    brand["slug"] = brand_slug
    brand_logo = asset_dir / f"{brand_slug}-logo.svg"
    ok, source = acquire_logo(brand_name, brand.get("website", ""), brand_logo)
    if ok:
        brand_asset = preferred_logo_asset(asset_dir, f"{brand_slug}-logo")
        brand["logo_url"] = relative_to_brand(brand_asset, brand_folder) if brand_asset else ""
        brand["mark_url"] = brand["logo_url"]
    else:
        manifest["ok"] = False
        manifest["errors"].append(f"{brand_name} brand logo failed: {source}")
    manifest["brand"] = {"name": brand_name, "asset": brand.get("logo_url", ""), "ok": ok, "resolution_source": source}

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
            manifest["ok"] = False
            manifest["errors"].append(f"{name} competitor logo failed: {source}")
        manifest["competitors"].append({"index": index, "name": name, "asset": asset, "ok": ok, "resolution_source": source})

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
            manifest["ok"] = False
            manifest["errors"].append(f"{source_name} source logo failed: {resolution}")
        manifest["news_sources"].append({"index": index, "source": source_name, "asset": asset, "ok": ok, "resolution_source": resolution})
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


def campaign_section(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("creative_campaign_ideas") or data.get("creative_campaigns") or {}


def audit_campaign_art(data_path: Path) -> dict[str, Any]:
    data = read_json(data_path)
    ideas = campaign_section(data).get("ideas", [])
    errors = []
    for index, idea in enumerate(ideas):
        url = idea.get("illustration_url")
        role = idea.get("illustration_asset_role")
        backend = idea.get("illustration_generation_backend")
        if role != "final-raster-artwork":
            errors.append(f"ideas[{index}] artwork is not marked final-raster-artwork.")
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
        if backend in {"local-scaffold", "placeholder"}:
            errors.append(f"ideas[{index}] uses scaffold backend.")
    return {"ok": not errors, "errors": errors}


def audit_presentation_html(brand_folder: Path, data_path: Path) -> dict[str, Any]:
    html_path = brand_folder / "newbizintel-report.html"
    errors: list[str] = []
    warnings: list[str] = []
    if not html_path.exists():
        return {"ok": False, "errors": [f"HTML report missing: {html_path}"], "warnings": warnings}

    size = html_path.stat().st_size
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    if size < 50_000:
        errors.append(f"HTML report is too small for the rich presentation layer ({size} bytes).")
    for label in ("Competitive Landscape", "SEO Audit", "Brand Reputation", "Creative Campaign Ideas"):
        if label not in text:
            errors.append(f"HTML report is missing required section: {label}")
    if "Generated by newbiz2 modular runner" in text:
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
    return {"module": "campaign-art", "data": str(data_path), "brand_folder": str(brand_folder), "generation": generation, "campaign_reduction": reduction, "contract_audit": audit}


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
        rows = "".join(f"<tr><th>{html.escape(str(item.get('label', '')))}</th><td>{html.escape(str(item.get('value', '')))}</td></tr>" for item in snapshot_items)
        sections.append(f"<section><h2>Company Snapshot</h2><table>{rows}</table></section>")
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
        sections.append("<section><h2>SEO And Search Evidence</h2><div class='grid'>" + "".join(card_html(item.get("title"), item.get("body")) for item in seo.get("semrush_evidence", [])) + "</div></section>")
    news = data.get("brand_reputation", {}).get("influential_news", [])
    if news:
        items = []
        for item in news:
            source_logo = asset_src(data_path, item.get("source_logo_url", "") or item.get("publisher_logo_url", ""))
            score = item.get("influence_score", "")
            rank_reason = item.get("rank_reason") or item.get("why_it_matters", "")
            subscore_summary = reputation_subscore_summary(item.get("influence_subscores"))
            items.append(f"<article class='news'>{f'<img src={html.escape(json.dumps(source_logo))} alt={html.escape(json.dumps(str(item.get('source', 'source')) + ' logo'))}>' if source_logo else ''}<p class='eyebrow'>{html.escape(str(item.get('date', '')))} | {html.escape(str(item.get('source', '')))} | Influence {html.escape(str(score))}</p><h3>{html.escape(str(item.get('headline', '')))}</h3><p><strong>Why it ranked:</strong> {html.escape(str(rank_reason))}</p>{f'<p class=\"muted\"><strong>Score basis:</strong> {html.escape(subscore_summary)}</p>' if subscore_summary else ''}<p>{html.escape(str(item.get('why_it_matters', '')))}</p></article>")
        sections.append("<section><h2>Influential News</h2>" + "".join(items) + "</section>")
    campaigns = campaign_section(data).get("ideas", [])
    if campaigns:
        blocks = []
        for idea in campaigns:
            image = asset_src(data_path, idea.get("illustration_url", ""))
            activation_plan = idea.get("activation_plan", [])
            blocks.append(
                f"<article class='campaign'>{f'<img src={html.escape(json.dumps(image))} alt=\"\">' if image else ''}<div><p class='eyebrow'>Creative campaign idea</p><h3>{html.escape(str(idea.get('title', '')))}</h3>"
                f"<p><strong>Concept:</strong> {html.escape(str(idea.get('concept', '')))}</p><p><strong>Activation:</strong> {html.escape(str(idea.get('activation', '')))}</p>"
                f"{list_html([plan.get('name') for plan in activation_plan if isinstance(plan, dict)])}</div></article>"
            )
        sections.append("<section><h2>Creative Campaign Ideas</h2>" + "".join(blocks) + "</section>")
    opportunities = data.get("opportunities", {})
    timelines = opportunities.get("timelines", []) if isinstance(opportunities, dict) else []
    if timelines:
        sections.append("<section><h2>30 / 60 / 90 Day Plan</h2><div class='grid'>" + "".join(card_html(item.get("title"), " ".join(item.get("items", []))) for item in timelines) + "</div></section>")
    css = """
    :root{--ink:#09213b;--muted:#5d6b7a;--line:#d8e2ec;--panel:#f7fafc;--accent:#153a5b}
    *{box-sizing:border-box} body{margin:0;font-family:Aptos,Segoe UI,Arial,sans-serif;color:var(--ink);background:#f4f7fa;line-height:1.55}
    main{max-width:1120px;margin:0 auto;padding:36px 22px 80px}.hero,.card,.logo-card,.news,.campaign,section{background:white;border:1px solid var(--line);border-radius:20px;box-shadow:0 18px 42px rgba(15,23,42,.06)}
    section{padding:28px;margin:24px 0}.hero{display:flex;gap:24px;padding:32px;margin-bottom:28px;background:linear-gradient(135deg,#fff,#edf5fb)}
    h1{font-size:44px;line-height:1.05;margin:.1em 0}h2{font-size:30px;margin:0 0 18px}h3{margin:.1em 0 .35em}.muted{color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:12px;font-weight:800;color:#53657a}
    .brand-logo{width:108px;height:108px;flex:0 0 108px;border-radius:26px;border:1px solid var(--line);display:grid;place-items:center;background:#fff;padding:18px;font-weight:900;font-size:28px}.brand-logo img,.logo-card img,.news img{max-width:100%;max-height:76px;object-fit:contain}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card,.logo-card,.news{padding:18px}.score{display:inline-block;padding:8px 12px;background:#edf5fb;border-radius:999px;font-weight:800}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid var(--line);padding:10px;vertical-align:top}th{width:28%}.campaign{display:grid;grid-template-columns:minmax(260px,42%) 1fr;gap:26px;padding:18px;margin:18px 0}.campaign img{width:100%;height:100%;max-height:760px;object-fit:cover;border-radius:16px}@media(max-width:760px){.hero,.campaign{grid-template-columns:1fr;display:grid}h1{font-size:34px}}
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
    if pattern.search(text):
        text = pattern.sub(section, text)
    else:
        text = text.replace("</main>", section + "</main>")
    html_path.write_text(text, encoding="utf-8")


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
    slides.append(("Search And SEO Evidence", [item.get("body", "") for item in data.get("seo_audit", {}).get("semrush_evidence", [])[:6]]))
    slides.append(("Influential News", [f"{item.get('headline', '')} ({item.get('influence_score', '')}): {item.get('rank_reason') or item.get('why_it_matters', '')}" for item in data.get("brand_reputation", {}).get("influential_news", [])[:6]]))
    campaigns = campaign_section(data).get("ideas", [])
    slides.append(("Creative Campaign Ideas", [f"{idea.get('title', '')}: {idea.get('concept', '')}" for idea in campaigns[:6]]))
    opportunities = data.get("opportunities", {})
    if isinstance(opportunities, dict):
        roadmap = [f"{block.get('title', '')}: {'; '.join(block.get('items', []))}" for block in opportunities.get("timelines", [])[:3]]
    elif isinstance(opportunities, list):
        roadmap = [f"{item.get('title', '')}: {item.get('body', '')}" for item in opportunities[:4]]
    else:
        roadmap = []
    slides.append(("30 / 60 / 90 Day Plan", roadmap))

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


def module_render(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "render", "in_progress")
    set_gate(state, "gate_6_render_outputs", "in_progress")
    save_state(brand_folder, state)
    validation = validate_report_data(data_path)
    if not validation["ok"]:
        set_status(state, "render", "failed")
        set_gate(state, "gate_6_render_outputs", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Render blocked by report-data validation: " + "; ".join(validation["errors"]))
    html_path = render_html(data_path, brand_folder / "newbizintel-report.html")
    archive_dir = brand_folder / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    portable_html = archive_dir / "newbizintel-report-portable.html"
    make_self_contained(html_path, data_path, portable_html)
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
        set_gate(state, "gate_6_render_outputs", "failed")
        save_state(brand_folder, state)
        raise SystemExit("PPTX output was not created. " + pptx_warning)
    shutil.copy2(pptx_path, archive_dir / pptx_path.name)
    set_status(state, "render", "passed")
    set_gate(state, "gate_6_render_outputs", "passed")
    save_state(brand_folder, state)
    return {"module": "render", "data": str(data_path), "brand_folder": str(brand_folder), "bundle": {"html": str(html_path), "pptx": str(pptx_path), "archive": {"directory": str(archive_dir), "html": str(portable_html), "pptx": str(archive_dir / pptx_path.name)}}}


def audit_task_list(data_path: Path) -> dict[str, Any]:
    brand_folder = data_path.parent
    state = load_state(brand_folder)
    sync_task_status_from_gates(state)
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
    set_status(state, "qa", "in_progress")
    set_status(state, "deploy", "pending")
    set_gate(state, "gate_6a_editorial_quality", "in_progress")
    set_gate(state, "gate_7_delivery", "pending")
    add_event(state, "fanout", "qa.initial_audits", jobs=["report-data", "task-list", "hybrid", "logos", "campaign-art", "outputs"])
    save_state(brand_folder, state)
    checks = {
        "report_data": validate_report_data(data_path),
        "task_list": audit_task_list(data_path),
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
        set_gate(state, "gate_6a_editorial_quality", "failed")
        save_state(brand_folder, state)
        write_json(brand_folder / "qa-results.json", checks)
        raise SystemExit("QA failed: " + "; ".join(errors))
    add_event(state, "reducer", "qa.bundle_reducer", outputs=[str(brand_folder / "qa-results.json")])
    set_status(state, "qa", "passed")
    set_gate(state, "gate_6a_editorial_quality", "passed")
    save_state(brand_folder, state)
    checks["task_list"] = audit_task_list(data_path)
    inject_task_list_into_html(brand_folder / "newbizintel-report.html", brand_folder)
    write_json(brand_folder / "qa-results.json", checks)
    return {"module": "qa", "data": str(data_path), "brand_folder": str(brand_folder), "checks": checks}


def module_deploy(args: argparse.Namespace) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "deploy", "in_progress")
    set_gate(state, "gate_7_delivery", "in_progress")
    save_state(brand_folder, state)
    html_path = brand_folder / "newbizintel-report.html"
    if not html_path.exists():
        set_status(state, "deploy", "failed")
        set_gate(state, "gate_7_delivery", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Cannot refresh delivery handoff because newbizintel-report.html is missing.")
    shutil.copy2(html_path, brand_folder / "index.html")
    set_status(state, "deploy", "passed")
    set_gate(state, "gate_7_delivery", "passed")
    save_state(brand_folder, state)
    inject_task_list_into_html(html_path, brand_folder)
    shutil.copy2(html_path, brand_folder / "index.html")
    return {"module": "deploy", "data": str(data_path), "brand_folder": str(brand_folder), "index": str(brand_folder / "index.html"), "task_list": str(brand_folder / "workflow-task-list.md")}


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
    parser.add_argument("--composio-semrush-available", action="store_true")
    parser.add_argument("--jina-fallback-available", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--semrush-database", choices=["uk", "us"], default="uk")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NewBiz2 without PowerShell.")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run")
    add_common_args(run_parser)
    run_parser.add_argument("--mode", choices=["full", "research-only", "render-stack", "qa-only", "deploy-handoff", "art-refresh", "assets-refresh"], default="full")
    for name in ["intake", "research", "structure", "assets", "campaign-art", "render", "qa", "deploy"]:
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
    }
    result = dispatch[args.command](args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
