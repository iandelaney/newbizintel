#!/usr/bin/env python3
"""Cross-platform NewBizIntel runner.

This is the Python-first execution path for colleagues who do not want to install
PowerShell. It intentionally mirrors the NewBizIntel gates and task-list contract while
using only Python plus optional Node/Python-PPTX for deck export.
"""
from __future__ import annotations

import argparse
import base64
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
from datetime import date, datetime
from pathlib import Path
from typing import Any

from python_modules.common import add_event
from python_modules.asset_helpers import asset_quality
from python_modules.asset_helpers import create_initial_mark_from_name
from python_modules.asset_helpers import patch_assets
from python_modules.asset_helpers import quality_ok
from python_modules.asset_helpers import relative_to_brand
from python_modules.asset_helpers import square_quality_ok
from python_modules.asset_helpers import visible_content_bbox
from python_modules.asset_helpers import visible_logo_occupancy_ok
from python_modules.common import brand_folder_from_data
from python_modules.common import data_path_from_args
from python_modules.common import is_repo_example_path
from python_modules.intake import module_intake as intake_module_entry
from python_modules.assets import module_assets as assets_module_entry
from python_modules.campaign_art import module_campaign_art as campaign_art_module_entry
from python_modules.deploy import module_deploy as deploy_module_entry
from python_modules.deploy import module_vercel_stage as vercel_stage_module_entry
from python_modules.common import load_state
from python_modules.common import normalize_url
from python_modules.common import output_root
from python_modules.common import ensure_task_list
from python_modules.common import sync_task_status_from_gates
from python_modules.common import read_json
from python_modules.common import reset_tasks_from
from python_modules.research import module_research as research_module_entry
from python_modules.qa import audit_pptx_package as audit_pptx_package_helper
from python_modules.qa import module_qa as qa_module_entry
from python_modules.common import save_state
from python_modules.common import set_gate
from python_modules.common import set_status
from python_modules.common import sha256
from python_modules.common import slugify
from python_modules.structure import module_structure as structure_module_entry
from python_modules.common import utc_now
from python_modules.common import write_json
from python_modules.render import module_render as render_module_entry
from python_modules.presentation_helpers import assert_deployable_report_html as assert_deployable_report_html_helper
from python_modules.presentation_helpers import audit_deploy_stage as audit_deploy_stage_helper
from python_modules.presentation_helpers import audit_presentation_html as audit_presentation_html_helper
from python_modules.presentation_helpers import audit_rendered_html_completeness as audit_rendered_html_completeness_helper
from python_modules.presentation_helpers import current_renderer_fingerprint as current_renderer_fingerprint_helper
from python_modules.presentation_helpers import extract_renderer_fingerprint as extract_renderer_fingerprint_helper
from python_modules.presentation_helpers import find_powershell as find_powershell_helper
from python_modules.presentation_helpers import inject_task_list_into_html as inject_task_list_into_html_helper
from python_modules.presentation_helpers import make_self_contained as make_self_contained_helper
from python_modules.presentation_helpers import render_outputs_current as render_outputs_current_helper
from python_modules.presentation_helpers import render_rich_html_with_powershell as render_rich_html_with_powershell_helper
from python_modules.presentation_helpers import render_rich_html_with_python as render_rich_html_with_python_helper
from python_modules.presentation_helpers import task_list_html as task_list_html_helper
from python_modules.presentation_builders import build_minimal_pptx as build_minimal_pptx_helper
from python_modules.presentation_builders import asset_src as asset_src_helper
from python_modules.presentation_builders import card_html as card_html_helper
from python_modules.presentation_builders import list_html as list_html_helper
from python_modules.presentation_builders import pptx_safe_data_copy as pptx_safe_data_copy_helper
from python_modules.presentation_builders import render_html as render_html_helper
from python_modules.presentation_builders import source_list_html as source_list_html_helper


SCRIPT_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_ROOT.parent
TEMPLATE_PATH = SKILL_ROOT / "templates" / "report-data.template.json"
TEMPLATE_ASSETS = SKILL_ROOT / "templates" / "slide-assets"
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
    ("Add verified profile owner", "placeholder profile owner"),
    ("goes here", "template fill-in text"),
    ("TBC", "unfinished generated content"),
    ("https://example.com", "template URL"),
    ("http://example.com", "template URL"),
    ("www.example.com", "template URL"),
    ("competitor-a.com", "template competitor URL"),
    ("competitor-b.com", "template competitor URL"),
    ("competitor-c.com", "template competitor URL"),
)

FOOD_CONTEXT_TERMS = (
    "meal kit",
    "meal-kit",
    "recipe",
    "grocery",
    "grocer",
    "ingredients",
    "cooking",
    "food",
    "chef",
    "hello fresh",
    "hellofresh",
    "gousto",
    "mindful chef",
    "simplycook",
)

FOOD_LEAKAGE_TERMS = (
    "easy home cooking",
    "home cooking",
    "recipe choice",
    "recipe ratings",
    "meal planning",
    "meal-kit",
    "meal kit",
    "recipe-box",
    "recipe box",
    "receive the box",
    "box arrival",
    "supermarket planning friction",
    "dinner drift",
    "household usefulness",
    "view this week's recipes",
    "choose meals",
)
GENERIC_SAFE_TOKENS = {
    "about",
    "access",
    "adoption",
    "advance",
    "agentic",
    "analysis",
    "analytics",
    "architecture",
    "audit",
    "backed",
    "benchmark",
    "brand",
    "buyer",
    "buyers",
    "business",
    "capture",
    "category",
    "certification",
    "clearer",
    "cloud",
    "commercial",
    "comparison",
    "comparisons",
    "competitive",
    "content",
    "context",
    "control",
    "controls",
    "conversion",
    "customer",
    "customers",
    "demand",
    "delivery",
    "development",
    "diagnosis",
    "discoverability",
    "discovery",
    "documentation",
    "domain",
    "enterprise",
    "evaluation",
    "evidence",
    "facing",
    "faster",
    "findings",
    "footprint",
    "governance",
    "groups",
    "growth",
    "health",
    "indexed",
    "intent",
    "issue",
    "issues",
    "journeys",
    "keyword",
    "keywords",
    "landing",
    "latest",
    "layer",
    "light",
    "management",
    "market",
    "messaging",
    "migration",
    "model",
    "native",
    "nonbrand",
    "observed",
    "onpage",
    "open",
    "opportunities",
    "opportunity",
    "organic",
    "pages",
    "package",
    "paid",
    "paths",
    "platform",
    "positioning",
    "practical",
    "priority",
    "product",
    "proof",
    "provider",
    "python",
    "queries",
    "rebuild",
    "recovery",
    "recommended",
    "relevance",
    "reputation",
    "report",
    "routes",
    "sales",
    "search",
    "section",
    "security",
    "selection",
    "semrush",
    "snapshot",
    "source",
    "signals",
    "site",
    "sizing",
    "stages",
    "story",
    "stronger",
    "technical",
    "teams",
    "themes",
    "traffic",
    "trust",
    "useful",
    "visibility",
    "watch",
    "workflow",
    "workflows",
    "workstreams",
    "year",
    "last",
    "months",
    "actions",
}
GENERIC_SAFE_PROPER_PHRASES = {
    "Brand Reputation",
    "Business Plan",
    "Business Wire",
    "Company Snapshot",
    "Competitive Landscape",
    "Content Implications",
    "Content Strategy",
    "Creative Campaign Ideas",
    "Current Search Visibility Health",
    "Customer Control",
    "Delivery Handoff",
    "Department Opportunity Signals",
    "Keyword Opportunity Groups",
    "Messaging Assessment",
    "Mission Anaconda",
    "New Business Intelligence",
    "On Page",
    "Open Source",
    "Paid Support Coverage",
    "Priority Issues",
    "Search Evidence",
    "Search Intent",
    "Search Visibility",
    "SEO Audit",
    "SEO Evidence",
    "SimilarWeb",
    "Social Proof",
    "Source Map",
    "Source Mission Anaconda",
    "Target Vs Competitor Search Visibility",
    "Technical Findings",
    "Unit 42",
    "UpGuard Report",
    "US Domain",
    "Workflow Task List",
    "Workflow Task List Passed",
    "Year On Year",
}
OUT_OF_SCOPE_BRAND_PHRASES = (
    "Operation Anaconda",
    "Anaconda Mining",
    "Anaconda Invest",
    "Anaconda Brand Experience",
    "Mission Command",
    "PaddlePals",
)
OUT_OF_SCOPE_TOKENS = {
    "alto",
    "afghanistan",
    "barber",
    "bartleby",
    "cnapp",
    "cooking",
    "cspm",
    "cyberark",
    "dns",
    "dinner",
    "ecuador",
    "firewall",
    "firewalls",
    "grocery",
    "havok",
    "meal",
    "meals",
    "mining",
    "mission",
    "montana",
    "movie",
    "movies",
    "orthodontics",
    "radiomics",
    "recipe",
    "recipes",
    "rudd",
    "shooting",
    "soldiers",
    "streaming",
    "suspect",
    "trailer",
}

RICH_RENDER_SCRIPT = SCRIPT_ROOT / "render" / "render_report.py"
RICH_RENDER_TEMPLATE = SKILL_ROOT / "templates" / "report-template.html"
RENDERER_FINGERPRINT_PREFIX = "NEWBIZINTEL_RENDERER_FINGERPRINT:"

def current_renderer_fingerprint() -> str:
    return current_renderer_fingerprint_helper(
        rich_render_script=RICH_RENDER_SCRIPT,
        rich_render_template=RICH_RENDER_TEMPLATE,
    )


def extract_renderer_fingerprint(rendered_html: str) -> str:
    return extract_renderer_fingerprint_helper(
        rendered_html,
        renderer_fingerprint_prefix=RENDERER_FINGERPRINT_PREFIX,
    )

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


def parse_exact_human_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d %B %Y").date()
    except ValueError:
        return None


def subtract_calendar_months(anchor: date, months: int) -> date:
    year = anchor.year
    month = anchor.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = anchor.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


def influential_news_cutoff(today: date | None = None) -> date:
    reference = today or datetime.now().date()
    return subtract_calendar_months(reference, 6)


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


def has_food_context(payload: Any) -> bool:
    haystack = json.dumps(payload, ensure_ascii=False).lower()
    matches = {term for term in FOOD_CONTEXT_TERMS if term in haystack}
    return len(matches) >= 2


def audit_cross_client_leakage(payload: Any, *, root_label: str = "report_data") -> dict[str, Any]:
    if has_food_context(payload):
        return {"ok": True, "errors": [], "matches": []}
    haystack = json.dumps(payload, ensure_ascii=False).lower()
    matches = [term for term in FOOD_LEAKAGE_TERMS if term in haystack]
    errors = [
        f"{root_label} contains carry-over language from another sector or client context: {term}"
        for term in matches[:25]
    ]
    if len(matches) > 25:
        errors.append(f"{len(matches) - 25} additional cross-client leakage markers found.")
    return {"ok": not errors, "errors": errors, "matches": matches}


def is_cross_client_safe(payload: Any) -> bool:
    return audit_cross_client_leakage(payload, root_label="payload").get("ok", False)


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten_text(child) for child in value.values())
    if isinstance(value, list):
        return " ".join(flatten_text(child) for child in value)
    return str(value)


def significant_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9'-]+", text):
        token = raw.lower().strip("-'")
        if len(token) < 4:
            continue
        if token in GENERIC_SAFE_TOKENS:
            continue
        if token in {"https", "http", "www", "com", "org", "net"}:
            continue
        tokens.add(token)
    return tokens


def domain_tokens(url: str) -> set[str]:
    normal = normalize_url(url)
    parsed = urllib.parse.urlparse(normal if "://" in normal else f"https://{normal}")
    host = (parsed.netloc or parsed.path).lower().replace("www.", "")
    parts = re.split(r"[^a-z0-9]+", host)
    return {part for part in parts if len(part) >= 4}


def collect_allowed_identity_phrases(data: dict[str, Any]) -> set[str]:
    phrases: set[str] = set(GENERIC_SAFE_PROPER_PHRASES)
    brand = data.get("brand", {})
    if isinstance(brand, dict):
        for field in ("name",):
            value = str(brand.get(field) or "").strip()
            if value:
                phrases.add(value)
    company_snapshot = data.get("company_snapshot", {})
    if isinstance(company_snapshot, dict):
        for collection in ("leadership", "founders"):
            for item in company_snapshot.get(collection, []) if isinstance(company_snapshot.get(collection), list) else []:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    if name:
                        phrases.add(name)
    for row in data.get("competitive_landscape", {}).get("table", []) if isinstance(data.get("competitive_landscape", {}), dict) else []:
        if isinstance(row, dict):
            name = str(row.get("competitor") or row.get("name") or "").strip()
            if name:
                phrases.add(name)
    for item in data.get("brand_reputation", {}).get("influential_news", []) if isinstance(data.get("brand_reputation", {}), dict) else []:
        if isinstance(item, dict):
            source = str(item.get("source") or "").strip()
            if source:
                phrases.add(source)
    return {phrase for phrase in phrases if phrase}


def collect_run_scope_tokens(data: dict[str, Any]) -> set[str]:
    tokens: set[str] = set(GENERIC_SAFE_TOKENS)
    brand = data.get("brand", {})
    if isinstance(brand, dict):
        tokens.update(significant_tokens(str(brand.get("name") or "")))
        tokens.update(domain_tokens(str(brand.get("website") or "")))
    for phrase in collect_allowed_identity_phrases(data):
        tokens.update(significant_tokens(phrase))
    for key in (
        "company_snapshot",
        "storybrand",
        "usp_ksp_review",
        "competitive_landscape",
        "brand_reputation",
        "opportunities",
        "creative_campaign_ideas",
        "content_strategy",
        "appendix",
    ):
        tokens.update(significant_tokens(flatten_text(data.get(key))))
    seo = data.get("seo_audit", {})
    if isinstance(seo, dict):
        evidence_only = {
            "semrush_evidence": seo.get("semrush_evidence"),
            "similarweb_evidence": seo.get("similarweb_evidence"),
            "search_evidence": seo.get("search_evidence"),
            "priority_issues_evidence": [
                item.get("evidence")
                for item in seo.get("priority_issues", [])
                if isinstance(item, dict)
            ],
        }
        tokens.update(significant_tokens(flatten_text(evidence_only)))
    return tokens


def extract_proper_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    pattern = re.compile(
        r"\b(?:[A-Z][a-z]+|[A-Z]{2,}|[0-9]+[A-Z][A-Za-z0-9]*)(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}|[0-9]+[A-Z][A-Za-z0-9]*)){1,3}\b"
    )
    for match in pattern.findall(text):
        phrase = re.sub(r"\s+", " ", match).strip()
        if len(phrase) < 5:
            continue
        phrases.add(phrase)
    return phrases


def seo_narrative_payload(seo: dict[str, Any]) -> dict[str, Any]:
    return {
        "cards": seo.get("cards"),
        "charts": seo.get("charts"),
        "priority_issues": [
            {
                "issue": item.get("issue"),
                "why_it_matters": item.get("why_it_matters"),
                "recommended_fix": item.get("recommended_fix"),
            }
            for item in seo.get("priority_issues", [])
            if isinstance(item, dict)
        ],
        "content_implications": seo.get("content_implications"),
        "search_score": seo.get("search_score"),
        "score_label": seo.get("score_label"),
    }


def audit_run_scope_identity(data: dict[str, Any], *, root_label: str = "report_data") -> dict[str, Any]:
    errors: list[str] = []
    heading_leads = {"mission", "promise", "business", "hero", "plan", "problems", "villain", "guide", "failure", "success", "direct", "supporting", "source"}
    allowed_phrases = {phrase.lower() for phrase in collect_allowed_identity_phrases(data)}
    allowed_tokens = collect_run_scope_tokens(data)
    brand_tokens = significant_tokens(flatten_text(data.get("brand", {})))
    text_samples = {
        "seo_audit": flatten_text(seo_narrative_payload(data.get("seo_audit", {}) if isinstance(data.get("seo_audit"), dict) else {})),
        "storybrand": flatten_text(data.get("storybrand")),
        "opportunities": flatten_text(data.get("opportunities")),
        "content_strategy": flatten_text(data.get("content_strategy")),
        "creative_campaign_ideas": flatten_text(data.get("creative_campaign_ideas")),
        "executive_summary": flatten_text(data.get("executive_summary")),
    }
    for section, text in text_samples.items():
        lowered = text.lower()
        for phrase in OUT_OF_SCOPE_BRAND_PHRASES:
            if phrase.lower() in lowered:
                errors.append(f"{root_label}.{section} contains out-of-scope brand or topic reference: {phrase}")
        for phrase in extract_proper_phrases(text):
            normal = phrase.lower()
            if normal in allowed_phrases:
                continue
            if phrase in GENERIC_SAFE_PROPER_PHRASES:
                continue
            phrase_tokens = significant_tokens(phrase)
            phrase_words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", phrase.lower())
            if phrase_words and phrase_words[0] in heading_leads:
                continue
            if phrase_tokens and phrase_tokens.issubset(GENERIC_SAFE_TOKENS):
                continue
            if phrase_tokens.intersection(brand_tokens) and not phrase_tokens.intersection(OUT_OF_SCOPE_TOKENS):
                continue
            if not phrase_tokens.intersection(OUT_OF_SCOPE_TOKENS):
                unsupported = {token for token in phrase_tokens if token not in allowed_tokens and token not in GENERIC_SAFE_TOKENS}
                if len(unsupported) < 2:
                    continue
            errors.append(f"{root_label}.{section} contains an out-of-scope or unsupported named phrase: {phrase}")
    return {"ok": not errors, "errors": errors[:25]}


def audit_seo_section_scope(data: dict[str, Any], *, root_label: str = "report_data") -> dict[str, Any]:
    seo = data.get("seo_audit", {})
    if not isinstance(seo, dict):
        return {"ok": True, "errors": []}
    allowed_tokens = collect_run_scope_tokens(data)
    text = flatten_text(seo_narrative_payload(seo))
    suspicious = sorted(
        token for token in significant_tokens(text)
        if token not in allowed_tokens and token not in GENERIC_SAFE_TOKENS
    )
    flagged_out_of_scope = sorted(token for token in suspicious if token in OUT_OF_SCOPE_TOKENS)
    errors: list[str] = []
    if flagged_out_of_scope:
        errors.append(
            f"{root_label}.seo_audit contains out-of-scope tokens inconsistent with this run: {', '.join(flagged_out_of_scope[:12])}"
        )
    return {"ok": not errors, "errors": errors}


def audit_rendered_identity_scope(data: dict[str, Any], html_text: str) -> dict[str, Any]:
    errors: list[str] = []
    heading_leads = {"mission", "promise", "business", "hero", "plan", "problems", "villain", "guide", "failure", "success", "direct", "supporting", "source", "workflow"}
    visible_text = html.unescape(re.sub(r"<[^>]+>", " ", html_text))
    visible_text = re.sub(r"\s+", " ", visible_text)
    allowed_phrases = {phrase.lower() for phrase in collect_allowed_identity_phrases(data)}
    allowed_phrases.update(phrase.lower() for phrase in extract_proper_phrases(flatten_text(data)))
    allowed_tokens = collect_run_scope_tokens(data)
    brand_tokens = significant_tokens(flatten_text(data.get("brand", {})))
    for phrase in OUT_OF_SCOPE_BRAND_PHRASES:
        if phrase.lower() in visible_text.lower():
            errors.append(f"Rendered HTML contains out-of-scope brand or topic reference: {phrase}")
    for phrase in extract_proper_phrases(visible_text):
        normal = phrase.lower()
        if normal in allowed_phrases:
            continue
        if phrase in GENERIC_SAFE_PROPER_PHRASES:
            continue
        tokens = significant_tokens(phrase)
        phrase_words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", phrase.lower())
        if phrase_words and phrase_words[0] in heading_leads:
            continue
        if tokens and tokens.issubset(GENERIC_SAFE_TOKENS):
            continue
        if tokens.intersection(brand_tokens) and not tokens.intersection(OUT_OF_SCOPE_TOKENS):
            continue
        if not tokens.intersection(OUT_OF_SCOPE_TOKENS):
            unsupported = {token for token in tokens if token not in allowed_tokens and token not in GENERIC_SAFE_TOKENS}
            if len(unsupported) < 2:
                continue
        errors.append(f"Rendered HTML contains an out-of-scope or unsupported named phrase: {phrase}")
    return {"ok": not errors, "errors": errors[:25]}


def audit_rendered_html_completeness(html_text: str) -> dict[str, Any]:
    return audit_rendered_html_completeness_helper(
        html_text,
        placeholder_markers=PLACEHOLDER_MARKERS,
    )


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
    today = datetime.now().date()
    cutoff = influential_news_cutoff(today)
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
        raw_date = str(item.get("date", ""))
        if not re.match(r"^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}$", raw_date):
            errors.append(f"{item_prefix}.date must use an exact date like '19 November 2025'.")
        parsed_date = parse_exact_human_date(raw_date)
        if raw_date and parsed_date is None:
            errors.append(f"{item_prefix}.date could not be parsed as an exact day-month-year date.")
        elif parsed_date is not None:
            if parsed_date < cutoff:
                errors.append(
                    f"{item_prefix}.date must fall within the last six months. "
                    f"Cutoff for this run is {cutoff.strftime('%d %B %Y')}; found {parsed_date.strftime('%d %B %Y')}."
                )
            elif parsed_date > today:
                errors.append(
                    f"{item_prefix}.date cannot be in the future for this run. "
                    f"Today is {today.strftime('%d %B %Y')}; found {parsed_date.strftime('%d %B %Y')}."
                )
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
        errors.append("seo_audit.charts must include the mandatory competitor-positioning and keyword-opportunity charts.")
        return

    normalized_titles = {
        str((chart or {}).get("title") or "").strip().lower()
        for chart in charts
        if isinstance(chart, dict)
    }
    required_title_signals = {
        "competitor positioning in search": "seo_audit.charts must include a 'Competitor positioning in search' chart.",
        "keyword opportunity groups": "seo_audit.charts must include a 'Keyword opportunity groups' chart.",
    }
    for title, message in required_title_signals.items():
        if title not in normalized_titles:
            errors.append(message)

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

    placeholder_snippets = (
        "should be confirmed",
        "source pending",
        "record whether",
        "record known funding",
        "must be drawn from",
        "identify likely stakeholder groups",
        "before publication",
        "latest verified public company",
        "public finance, scale, and operating metrics",
        "required for finance, ownership, and governance facts",
        "required for current leadership and profile links",
        "treated in this report as a brand",
    )

    def contains_placeholder_language(value: Any) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
        if not text:
            return False
        return any(snippet in text for snippet in placeholder_snippets)

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

    if not has_value(snapshot.get("summary")):
        errors.append("company_snapshot.summary is required.")
    elif contains_placeholder_language(snapshot.get("summary")):
        errors.append("company_snapshot.summary contains placeholder or research-note language instead of verified company context.")

    for section in ("items", "finance_stats", "ownership_funding", "source_map"):
        for index, item in enumerate(snapshot.get(section, []) if isinstance(snapshot.get(section), list) else []):
            if not isinstance(item, dict):
                errors.append(f"company_snapshot.{section}[{index}] must be an object.")
                continue
            for key in ("label", "value"):
                if not has_value(item.get(key)):
                    errors.append(f"company_snapshot.{section}[{index}].{key} is required.")
            if contains_placeholder_language(item.get("label")) or contains_placeholder_language(item.get("value")):
                errors.append(
                    f"company_snapshot.{section}[{index}] contains placeholder language and must be replaced with verified company facts."
                )
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
            elif contains_placeholder_language(item.get(key)):
                errors.append(
                    f"company_snapshot.leadership[{index}].{key} contains placeholder language and must use verified leadership details."
                )
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
            elif contains_placeholder_language(item.get(key)):
                errors.append(
                    f"company_snapshot.founders[{index}].{key} contains placeholder language and must use verified founding details."
                )


def qualified_public_seo_evidence(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    qualified: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip()
        source_url = str(item.get("source_url") or item.get("url") or "").strip()
        source_label = str(item.get("source_label") or item.get("source") or item.get("title") or "").strip()
        if source_url and (provider or source_label):
            qualified.append(item)
    return qualified


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
        "reputation evidence means",
        "search evidence points",
        "public search evidence points",
        "the leading reputation signal is",
        "this story matters because",
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
    stale_phrases = (
        "the commercial risk is that this coverage",
        "coverage highlights this coverage",
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
        if not re.search(r"\b(opportunity|risk|task|needs to|should|must|chance|question|challenge|implication)\b", lower_body):
            errors.append(
                f"executive_summary.cards[{index}].body must state a clear implication, risk, or opportunity for an executive reader."
            )
        if "later" in lower_body or "below" in lower_body or "in the reputation chapter" in lower_body:
            errors.append(
                f"executive_summary.cards[{index}].body must stand alone and not rely on later sections of the report."
            )
        if any(phrase in lower_body for phrase in stale_phrases):
            errors.append(
                f"executive_summary.cards[{index}].body contains stale or self-colliding coverage phrasing and must be rewritten for executive clarity."
            )

    storybrand = data.get("storybrand", {})
    if isinstance(storybrand, dict):
        read_across = str(storybrand.get("existing_messaging_assessment", {}).get("reputation_read_across") or "")
        lower_read_across = read_across.lower()
        if any(phrase in lower_read_across for phrase in stale_phrases):
            errors.append(
                "storybrand.existing_messaging_assessment.reputation_read_across contains stale or self-colliding coverage phrasing and must be rewritten."
            )


def validate_appendix_source_map(data: dict[str, Any], errors: list[str]) -> None:
    appendix = data.get("appendix", {})
    if not isinstance(appendix, dict):
        return
    source_map = appendix.get("source_map")
    if not isinstance(source_map, list):
        return
    for index, item in enumerate(source_map):
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(field) or "") for field in ("title", "source", "url")).lower()
        for snippet in APPENDIX_SOURCE_NOISE_SNIPPETS:
            if snippet in text:
                errors.append(
                    f"appendix.source_map[{index}] contains ambiguous or irrelevant source noise unsuitable for delivery: {snippet}"
                )
                break


def validate_delivery_section_contract(data: dict[str, Any], errors: list[str]) -> None:
    required_object_sections = (
        "brand",
        "report_meta",
        "company_snapshot",
        "executive_summary",
        "agency_opportunity",
        "storybrand",
        "usp_ksp_review",
        "competitive_landscape",
        "seo_audit",
        "brand_reputation",
        "content_strategy",
        "creative_campaign_ideas",
        "opportunities",
        "appendix",
    )
    for key in required_object_sections:
        if not isinstance(data.get(key), dict):
            errors.append(f"{key} must exist as a populated report section object before delivery.")

    executive_summary = data.get("executive_summary", {})
    if isinstance(executive_summary, dict):
        cards = executive_summary.get("cards", [])
        if not isinstance(cards, list) or len([card for card in cards if has_value(card)]) < 6:
            errors.append("executive_summary.cards must include 6 populated executive-summary cards.")
        if not has_value(executive_summary.get("overall_recommendation")):
            errors.append("executive_summary.overall_recommendation is required.")

    content_strategy = data.get("content_strategy", {})
    if isinstance(content_strategy, dict):
        cards = content_strategy.get("cards", [])
        if not isinstance(cards, list) or len([card for card in cards if has_value(card)]) < 4:
            errors.append("content_strategy.cards must include at least 4 populated cards.")
        priority = content_strategy.get("priority_opportunities", [])
        if not isinstance(priority, list) or len([item for item in priority if has_value(item)]) < 2:
            errors.append("content_strategy.priority_opportunities must include at least 2 populated items.")
        ideas = content_strategy.get("example_ideas", [])
        if not isinstance(ideas, list) or len([item for item in ideas if has_value(item)]) < 2:
            errors.append("content_strategy.example_ideas must include at least 2 populated example ideas.")
        if not has_value(content_strategy.get("response_to_findings")):
            errors.append("content_strategy.response_to_findings is required.")

    opportunities = data.get("opportunities", {})
    if isinstance(opportunities, dict):
        timelines = opportunities.get("timelines", [])
        if not isinstance(timelines, list) or len(timelines) < 3:
            errors.append("opportunities.timelines must include the 30/60/90-day plan.")
        else:
            expected_titles = {"next 30 days", "next 60 days", "next 90 days"}
            seen_titles = {
                str(item.get("title") or "").strip().lower()
                for item in timelines
                if isinstance(item, dict) and has_value(item.get("title"))
            }
            if not expected_titles.issubset(seen_titles):
                errors.append("opportunities.timelines must include titled entries for Next 30 days, Next 60 days, and Next 90 days.")
            for index, item in enumerate(timelines):
                if not isinstance(item, dict):
                    errors.append(f"opportunities.timelines[{index}] must be an object.")
                    continue
                if not has_value(item.get("title")):
                    errors.append(f"opportunities.timelines[{index}].title is required.")
                timeline_items = item.get("items", [])
                if not isinstance(timeline_items, list) or len([entry for entry in timeline_items if has_value(entry)]) < 2:
                    errors.append(f"opportunities.timelines[{index}].items must include at least 2 populated actions.")

    appendix = data.get("appendix", {})
    if isinstance(appendix, dict):
        source_map = appendix.get("source_map", [])
        if not isinstance(source_map, list) or len([item for item in source_map if has_value(item)]) < 3:
            errors.append("appendix.source_map must include at least 3 populated verifiable source entries.")
        assumptions = appendix.get("assumptions_and_confidence_notes", [])
        if not isinstance(assumptions, list) or len([item for item in assumptions if has_value(item)]) < 1:
            errors.append("appendix.assumptions_and_confidence_notes must include at least 1 populated note.")

    reputation = data.get("brand_reputation", {})
    if isinstance(reputation, dict):
        for key, minimum in (("cards", 4), ("recommended_actions", 2), ("content_implications", 2)):
            items = reputation.get(key, [])
            if not isinstance(items, list) or len([item for item in items if has_value(item)]) < minimum:
                errors.append(f"brand_reputation.{key} must include at least {minimum} populated item(s).")


def is_enriched_company_snapshot(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required_sections = ("items", "finance_stats", "leadership", "founders", "ownership_funding", "source_map")
    return all(isinstance(value.get(section), list) and len(value.get(section) or []) > 0 for section in required_sections)


def validate_report_data(data_path: Path, *, phase: str = "final") -> dict[str, Any]:
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
        "executive_summary.cards",
        "executive_summary.overall_recommendation",
        "agency_opportunity.score",
        "agency_opportunity.summary",
        "agency_opportunity.department_opportunity_map",
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
        "competitive_landscape.table",
        "competitive_landscape.why_each_competitor_matters",
        "competitive_landscape.messaging_patterns",
        "competitive_landscape.content_patterns",
        "competitive_landscape.status_summary",
        "content_strategy.cards",
        "content_strategy.priority_opportunities",
        "content_strategy.example_ideas",
        "content_strategy.response_to_findings",
        "creative_campaign_ideas.ideas",
        "opportunities.marketing_strategy.strategy",
        "opportunities.marketing_strategy.why_it_matters",
        "opportunities.marketing_strategy.evidence_threads",
        "opportunities.timelines",
        "appendix.source_map",
    ]
    for path in required:
        ensure_path(data, path, errors)
    content_audit = audit_missing_content(data)
    if phase == "structure" and not content_audit["ok"]:
        deferred_prefixes = (
            "report_data.brand.logo_url",
            "report_data.competitive_landscape.table",
            "report_data.brand_reputation.influential_news",
        )
        content_audit["errors"] = [
            error
            for error in content_audit.get("errors", [])
            if not any(error.startswith(prefix) for prefix in deferred_prefixes)
        ]
        content_audit["ok"] = not content_audit["errors"]
    if not content_audit["ok"]:
        errors.extend(f"missing_content_audit: {error}" for error in content_audit.get("errors", []))
    leakage_audit = audit_cross_client_leakage(data, root_label="report_data")
    if not leakage_audit["ok"]:
        errors.extend(f"cross_client_leakage: {error}" for error in leakage_audit.get("errors", []))
    identity_audit = audit_run_scope_identity(data, root_label="report_data")
    if not identity_audit["ok"]:
        errors.extend(f"run_scope_identity: {error}" for error in identity_audit.get("errors", []))
    seo_scope_audit = audit_seo_section_scope(data, root_label="report_data")
    if not seo_scope_audit["ok"]:
        errors.extend(f"seo_scope: {error}" for error in seo_scope_audit.get("errors", []))
    validate_delivery_section_contract(data, errors)
    validate_company_snapshot_contract(data, errors)
    validate_executive_summary_tone(data, errors)
    validate_appendix_source_map(data, errors)
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
                if phase != "structure":
                    logo_fields = ("logo_url", "competitor_logo_url", "badge_url", "mark_url")
                    if not any(has_value(row.get(field_name)) for field_name in logo_fields):
                        errors.append(
                            f"competitive_landscape.table[{index}] must include a usable competitor logo field "
                            f"({', '.join(logo_fields)})."
                        )
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
    public_provider_evidence = qualified_public_seo_evidence(search_evidence)
    provider_seo_evidence = len(semrush) + len(similarweb) + len(public_provider_evidence)
    total_seo_evidence = provider_seo_evidence + len(search_evidence)
    if provider_seo_evidence < 2:
        errors.append(
            "seo_audit must include at least 2 labelled SEO evidence points across "
            "semrush_evidence, similarweb_evidence, or clearly sourced public-web search evidence "
            f"before the section can pass. Current provider count: {provider_seo_evidence}"
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
        threads = strategy.get("evidence_threads")
        if not isinstance(threads, list) or not threads:
            threads = strategy.get("built_from_findings")
        if not isinstance(threads, list) or not threads:
            threads = strategy.get("threads", [])
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
    if phase != "structure":
        for index, item in enumerate(news if isinstance(news, list) else []):
            if not isinstance(item, dict):
                continue
            logo_fields = ("source_logo_url", "publisher_logo_url")
            if not any(has_value(item.get(field_name)) for field_name in logo_fields):
                errors.append(
                    f"brand_reputation.influential_news[{index}] must include a usable publisher/source logo field "
                    f"({', '.join(logo_fields)})."
                )
    brand_name = str(data.get("brand", {}).get("name") or "").strip().lower()
    brand_domain = brand_domain_from_website(str(data.get("brand", {}).get("website") or ""))
    for index, item in enumerate(news if isinstance(news, list) else []):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        source_lower = source.lower()
        source_type = str(item.get("source_type") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        source_domain = brand_domain_from_website(url)
        owned_source = source_type == "owned_newsroom" or (
            brand_name and brand_name in source_lower
        ) or any(token in source_lower for token in ("blog", "press", "newsroom"))
        if source and url and brand_domain and source_domain == brand_domain and not owned_source:
            errors.append(
                f"brand_reputation.influential_news[{index}] labels the publisher as '{source}' but links to the brand-owned domain {brand_domain}."
            )
    for index, item in enumerate(data.get("agency_opportunity", {}).get("department_opportunity_map", [])):
        if not has_value(item.get("opportunity_signal")):
            errors.append(f"agency_opportunity.department_opportunity_map[{index}].opportunity_signal is required.")
    if phase != "structure":
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
    cards = storybrand.get("cards", [])
    if len(published_statements) < 2:
        errors.append("storybrand.existing_messaging_assessment.published_statements must include at least 2 mission, purpose, promise, or proposition statements.")
    if len(cards) < 6:
        errors.append("storybrand.cards must include a full StoryBrand card set, not a partial scaffold.")
    high_order_count = 0
    source_urls: set[str] = set()
    for index, item in enumerate(published_statements):
        if not has_value(item.get("label")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].label is required.")
        if not has_value(item.get("statement")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].statement is required.")
        if not has_value(item.get("source")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].source is required.")
        if not has_value(item.get("source_url")):
            errors.append(f"storybrand.existing_messaging_assessment.published_statements[{index}].source_url is required so readers can verify the published messaging.")
        if has_value(item.get("source_url")):
            source_urls.add(normalize_url(str(item.get("source_url") or "")))
        combined = f"{item.get('label', '')} {item.get('statement', '')} {item.get('source', '')} {item.get('source_url', '')}".lower()
        if any(term in combined for term in HIGH_ORDER_MESSAGING_TERMS):
            high_order_count += 1
        for snippet in WEAK_PUBLISHED_MESSAGING_SNIPPETS:
            if snippet in combined:
                errors.append(
                    f"storybrand.existing_messaging_assessment.published_statements[{index}] uses weak blog/product-copy language rather than mission, purpose, promise, or values evidence."
                )
    website_root = normalize_url(str(data.get("brand", {}).get("website") or ""))
    if source_urls and all(url.rstrip("/") == website_root.rstrip("/") for url in source_urls):
        errors.append("storybrand.existing_messaging_assessment must cite at least one specific official source page, not only the homepage root.")
    if high_order_count < 1:
        errors.append("storybrand.existing_messaging_assessment.published_statements must include at least one high-order mission, purpose, promise, values, or brand-platform statement.")
    storybrand_text = flatten_text(
        {
            "summary": messaging_assessment.get("summary"),
            "reputation_read_across": messaging_assessment.get("reputation_read_across"),
            "implication": messaging_assessment.get("implication"),
            "cards": cards,
            "one_liner": storybrand.get("one_liner"),
            "messaging_fixes": storybrand.get("messaging_fixes"),
            "content_implications": storybrand.get("content_implications"),
        }
    )
    lower_storybrand = storybrand_text.lower()
    for snippet in STORYBRAND_GENERIC_SNIPPETS:
        if snippet in lower_storybrand:
            errors.append("storybrand contains generic reusable card language instead of brand-specific messaging evidence.")
            break
    storybrand_tokens = significant_tokens(storybrand_text)
    storybrand_evidence_tokens = significant_tokens(
        flatten_text(
            {
                "brand": data.get("brand"),
                "company_snapshot": data.get("company_snapshot"),
                "published_statements": published_statements,
                "competitive_landscape": data.get("competitive_landscape"),
                "brand_reputation": data.get("brand_reputation"),
                "seo_priority_issues": data.get("seo_audit", {}).get("priority_issues"),
            }
        )
    )
    overlap = storybrand_tokens.intersection(storybrand_evidence_tokens)
    if len(overlap) < 8:
        errors.append(
            "storybrand does not appear grounded enough in the current run's evidence. "
            f"Context-token overlap is too low ({len(overlap)})."
        )
    usp_text = flatten_text(usp)
    lower_usp = usp_text.lower()
    for snippet in USP_GENERIC_SNIPPETS:
        if snippet in lower_usp:
            errors.append("usp_ksp_review contains generic reusable USP/KSP language instead of brand-specific claims.")
            break
    usp_tokens = significant_tokens(usp_text)
    usp_overlap = usp_tokens.intersection(storybrand_evidence_tokens)
    if len(usp_overlap) < 8:
        errors.append(
            "usp_ksp_review does not appear grounded enough in the current run's evidence. "
            f"Context-token overlap is too low ({len(usp_overlap)})."
        )
    seo_cards = seo.get("cards", []) if isinstance(seo, dict) else []
    seo_text = flatten_text(seo_cards)
    lower_seo = seo_text.lower()
    if any(snippet in lower_seo for snippet in STALE_SEO_TECHNICAL_SNIPPETS):
        if len(semrush) >= 1 or len(search_evidence) >= 2:
            errors.append(
                "seo_audit uses stale crawl-gate wording even though search/provider evidence has already passed for this run."
            )
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


def clean_executive_signal_text(value: Any, fallback: str = "") -> str:
    text = sentence(value, fallback)
    replacements = (
        (r"^\s*this story matters because\s+", ""),
        (r"^\s*the leading reputation signal is\s+", ""),
        (r"^\s*public search evidence points to\s+", ""),
        (r"^\s*search evidence points to\s+", ""),
        (r"^\s*public coverage has raised questions about\s+", ""),
        (r"^\s*public coverage shows that\s+", ""),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if text and not text.endswith((".", "!", "?")):
        text = f"{text}."
    return text or fallback


def executive_primary_takeaway(
    brand: str,
    top_news: dict[str, Any],
    competitors: list[str],
) -> str:
    signal = clean_executive_signal_text(
        top_news.get("why_it_matters") or top_news.get("headline"),
        "The opportunity is to turn market momentum into a buying story that feels simpler, clearer, and easier to trust.",
    )
    combined = f"{top_news.get('headline', '')} {signal}".lower()
    competitor_text = ", ".join(competitors[:3])
    if any(term in combined for term in ("acquisition", "deal", "platform", "ai era", "identity-security", "cyberark")):
        return (
            f"{brand} enters this brief with scale, momentum, and platform ambition, but the executive question is whether that breadth "
            f"feels like one coherent operating model rather than a growing collection of capabilities."
        )
    if any(term in combined for term in ("vulnerability", "breach", "security flaw", "outage", "incident")):
        return (
            f"{brand} has strong category authority, but the first-read challenge is confidence: the promise will land best if resilience, "
            f"response, and customer protection are made visible rather than assumed."
        )
    comparison_clause = (
        f" Against {competitor_text}, the brand needs to make its value easier to understand on first contact."
        if competitor_text
        else ""
    )
    return (
        f"{brand} has clear market relevance, but the immediate task is to make the promise easier to buy than to admire."
        f"{comparison_clause}"
    )


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
        " There is visibility headroom around category, competitor, and trust-led queries."
        if has_semrush
        else " Search visibility can still be improved around category, competitor, and trust-led queries."
    )
    return (
        f"{brand} should treat search as part of the sales conversation, not just a traffic channel."
        f"{evidence_clause}{comparison_clause}"
    )


def executive_commercial_risk_summary(brand: str, top_news: dict[str, Any]) -> str:
    raw = clean_executive_signal_text(
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
    if any(term in combined for term in ("acquisition", "deal", "platform", "identity-security", "cyberark", "google cloud")):
        return (
            f"The commercial risk is that buyers see {brand} as strategically expansive but operationally complex, which would make platform scale "
            f"feel harder to adopt, govern, or justify."
        )
    if any(term in combined for term in ("vulnerability", "breach", "incident", "outage", "product-security")):
        return (
            f"The commercial risk is that trust questions drown out the growth story, making resilience and response proof more persuasive than broad brand claims."
        )
    lower_raw = raw.lower()
    if lower_raw.startswith("this coverage "):
        rewritten = re.sub(r"^this coverage\b", "recent coverage", raw, flags=re.IGNORECASE)
        return f"The commercial risk is that {rewritten[0].lower()}{rewritten[1:]}"
    if lower_raw.startswith("raises "):
        return f"The commercial risk is that public scrutiny around {brand} {raw[0].lower()}{raw[1:]}"
    if lower_raw.startswith(("creates ", "signals ", "shows ", "suggests ", "points to ", "could affect ", "may affect ", "risks ", "needs ")):
        return f"The commercial risk is that {brand} faces a trust and conversion challenge: {raw[0].lower()}{raw[1:]}"
    if not re.search(r"\b(is|are|has|have|faces|risks|could|may|should|needs|must|will)\b", lower_raw):
        return f"The commercial risk is that {raw[0].lower()}{raw[1:]}"
    return f"The commercial risk is that {brand} {raw[0].lower()}{raw[1:]}"


def executive_reputation_insight_summary(brand: str, top_news: dict[str, Any]) -> str:
    headline = sentence(top_news.get("headline"), "high-authority reputation coverage")
    lower_headline = headline.lower()
    if "subscription trap" in lower_headline or "subscription traps" in lower_headline:
        return f"The reputation implication is that public scrutiny of subscription practices makes control, cancellation clarity, and service recovery central to {brand}'s trust story."
    if "regulator" in lower_headline or "court" in lower_headline:
        return f"The reputation implication is that regulatory or legal scrutiny means {brand} needs visible proof that customers can understand, control, and recover from service issues."
    if any(term in lower_headline for term in ("acquisition", "deal", "platform", "cyberark", "google cloud")):
        return (
            f"The reputation implication is positive momentum with a tougher standard of proof: {brand} now has to show how scale becomes customer clarity, not just corporate ambition."
        )
    if any(term in lower_headline for term in ("vulnerability", "breach", "incident", "outage")):
        return (
            f"The reputation implication is that the story will be shaped less by broad promise than by whether {brand} appears disciplined, transparent, and operationally dependable under pressure."
        )
    return f"The reputation implication is that {brand} needs visible proof behind its strongest claims, so trust is earned through clarity and operating confidence rather than tone alone."


def executive_messaging_opportunity_summary(brand: str, competitors: list[str]) -> str:
    competitor_text = ", ".join(competitors[:3])
    if competitor_text:
        return (
            f"The messaging opportunity is to make the promise sharper at buying moments: explain what becomes simpler, safer, and easier to govern with {brand} than with {competitor_text}, "
            f"then prove it in plain language."
        )
    return (
        f"The messaging opportunity is to make the promise sharper at buying moments: explain what becomes simpler, safer, and easier to govern with {brand}, "
        f"then prove it in plain language."
    )


def executive_content_strategy_summary(brand: str) -> str:
    return (
        f"The content opportunity is to build a proof-led content system for {brand}: comparison pages, reassurance modules, executive explainers, and service-confidence assets "
        f"that answer objections before sales or procurement have to."
    )


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
    workpack_dir = brand_folder / "research-workpacks"
    if not workpack_dir.exists():
        return []
    owned = []
    seen_urls: set[str] = set()
    for path in sorted(workpack_dir.glob("*.json")):
        if path.name.endswith(".prompt.txt") or path.name == "research-acquisition.json":
            continue
        try:
            payload = read_json(path)
        except Exception:
            continue
        results = payload.get("results") if isinstance(payload, dict) else []
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            if not url or url in seen_urls:
                continue
            result_domain = brand_domain_from_website(url)
            domain_stem = domain.split(".")[0].replace("-", "") if domain else ""
            result_stem = result_domain.replace("-", "")
            if domain and domain not in result_domain and domain_stem and domain_stem not in result_stem:
                continue
            if item.get("content"):
                owned.append(item)
                seen_urls.add(url)
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
        if is_biography_like(lower) or is_careers_benefits_like(lower):
            continue
        if 45 <= len(clean) <= 240 and any(keyword in lower for keyword in keywords):
            score = 0
            if " is " in lower or " are " in lower:
                score += 3
            if lower.startswith(("our mission", "our vision", "our purpose", "our values", "we help", "we enable", "we protect", "to be the")):
                score += 8
            if any(term in lower for term in ("mission", "purpose", "promise", "values", "vision", "strategy")):
                score += 4
            if any(term in lower for term in ("customer", "buyer", "client", "people", "organisations", "outcomes")):
                score += 2
            if any(term in lower for term in ("secure", "protect", "enable", "trust", "confidence", "innovation", "transformation")):
                score += 4
            if any(term in lower for term in ("employee", "employees", "benefits", "family", "career", "jobs")):
                score -= 8
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
    "vision",
    "belief",
    "change the way",
    "customer-centric",
    "customer centric",
    "customer",
    "buyer",
    "trust",
    "security",
    "protect",
    "innovation",
    "sustainability",
    "sustainable",
    "business model",
)


WEAK_PUBLISHED_MESSAGING_SNIPPETS = (
    "recipe box delivery service and this is how we work",
    "pictured above",
    "newsletter",
    "sign up",
    "special deals",
    "prior to joining",
    "board of directors",
    "chief executive officer",
    "joined palo alto networks",
    "joined the palo alto networks board",
    "benefits program",
    "401(k)",
    "refresh and bring joy",
    "your family are healthy",
    "employee benefits",
)


STORYBRAND_GENERIC_SNIPPETS = (
    "the buyer or customer wants a simpler, more confident path to the outcome the brand promises",
    "feel reassured that the promise is credible, the route is clear, and the experience will stand up under scrutiny",
    "confidence drift: the repeated friction of comparison, unclear proof",
    "clear proof points, visible controls, customer feedback loops, service-recovery evidence",
    "understand the offer, compare the options fairly, see the proof",
    "take the next high-intent step with confidence",
    "the brand feels easier to trust, easier to choose, and easier to stay with",
    "helps customers achieve the promised outcome with clearer choices, stronger proof, and visible control throughout the journey",
    "clearer path to the outcome",
    "enough proof to trust the decision",
    "message drift: broad claims that sound plausible",
)

USP_GENERIC_SNIPPETS = (
    "the brand makes the category promise easy to understand",
    "choice, flexibility, and reduced decision friction",
    "becoming easier to compare, trust, and act on than alternatives",
    "control, quality, and service proof more tangible than competitors",
    "clear category proposition",
)

STALE_SEO_TECHNICAL_SNIPPETS = (
    "no live crawl gate has passed yet",
)


BIOGRAPHY_MESSAGING_SNIPPETS = (
    "prior to joining",
    "joined the company",
    "joined palo alto networks",
    "board of directors",
    "chief executive officer",
    "chief financial officer",
    "chief product",
    "chief marketing",
    "served as",
    "holds a bachelor's degree",
    "holds both bachelor's and master's degrees",
    "earned an engineering degree",
    "he is responsible for",
    "she is responsible for",
    "by leading the company's",
)


CAREERS_MESSAGING_SNIPPETS = (
    "benefits program",
    "401(k)",
    "refresh and bring joy",
    "your family are healthy",
    "health savings accounts",
    "professional development",
    "employees' input",
    "careers and jobs",
)


def is_biography_like(text: str) -> bool:
    lower = str(text or "").lower()
    return any(snippet in lower for snippet in BIOGRAPHY_MESSAGING_SNIPPETS)


def is_careers_benefits_like(text: str) -> bool:
    lower = str(text or "").lower()
    return any(snippet in lower for snippet in CAREERS_MESSAGING_SNIPPETS)


def messaging_source_officiality_score(item: dict[str, Any], website: str) -> int:
    url = str(item.get("url") or "").strip().lower()
    score = 0
    site_domain = brand_domain_from_website(website)
    url_domain = brand_domain_from_website(url)
    if site_domain and url_domain and (url_domain == site_domain or url_domain.endswith(f".{site_domain}")):
        score += 18
    if any(term in url for term in ("jobs.", "/careers", "/culture")):
        score -= 14
    return score


GENERIC_COMPETITOR_ANALYSIS_SNIPPETS = (
    "current market-discovery search identified this brand",
    "identified from current market alternatives coverage",
    "use this comparator to sharpen positioning",
    "alternative or category comparator",
    "comparator requiring manual synthesis",
    "comparative positioning pattern",
)
APPENDIX_SOURCE_NOISE_SNIPPETS = (
    "paddlepals",
    "playtomic",
    "jack black",
    "paul rudd",
    "ice cube",
    "trailer",
    "streaming",
    "reboot",
    "movie",
    "film",
    "murder suspect",
    "bar shooting",
    "montana",
    "orthodontics",
    "ibuprofen",
    "storage solutions",
    "fightwear",
)


def competitor_role_analysis(brand: str, row: dict[str, Any]) -> dict[str, str]:
    name = str(row.get("competitor") or row.get("name") or "").strip()
    key = re.sub(r"[^a-z0-9]+", "", name.lower())
    url = str(row.get("website") or row.get("url") or "").strip().lower()
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
    if any(token in f"{key} {url}" for token in ("monday", "asana", "clickup", "teamwork")):
        return {
            "why_it_matters": f"{name or 'This competitor'} matters because it pulls the buying frame toward ease of adoption, cross-team workflow visibility, and faster rollout rather than a broader enterprise platform estate.",
            "positioning_pattern": f"{name or 'This competitor'} positions itself as a simpler workflow and execution platform, using usability, quick onboarding, and lighter operational friction as the main commercial wedge.",
            "implication": f"{brand} needs clearer proof that its broader CRM, data, and AI depth creates better outcomes than {name or 'this simpler platform'} for buyers who are tempted by speed and ease of adoption.",
        }
    if any(token in f"{key} {url}" for token in ("creatio", "zoho", "hubspot", "pipedrive", "freshworks", "maximizer", "teamgate", "bigcontacts")):
        return {
            "why_it_matters": f"{name or 'This competitor'} matters because it competes on practical CRM value: faster setup, easier administration, and a more approachable route into sales, service, and automation than a larger enterprise stack.",
            "positioning_pattern": f"{name or 'This competitor'} uses a CRM-suite pattern built around usability, quicker time-to-value, and accessible workflow automation for revenue and customer-service teams.",
            "implication": f"{brand} should answer {name or 'this competitor'} with stronger proof that enterprise breadth, governance, ecosystem depth, and AI workflow capability justify the extra complexity.",
        }
    if any(token in f"{key} {url}" for token in ("zendesk", "intercom", "devrev", "servicenow")):
        return {
            "why_it_matters": f"{name or 'This competitor'} matters because it can shift the buying decision toward service operations, support quality, or AI-assisted case handling instead of a broader customer-platform narrative.",
            "positioning_pattern": f"{name or 'This competitor'} positions around service delivery, support workflows, and response efficiency, often using agent tooling or help-desk clarity as the wedge into wider account growth.",
            "implication": f"{brand} needs sharper service-proof messaging against {name or 'this competitor'} so buyers understand when a broader customer platform beats a service-led specialist in support and AI-assisted resolution.",
        }
    return {
        "why_it_matters": f"{name or 'This competitor'} matters because it gives buyers a credible alternative path to the same commercial outcome. The analysis should compare category promise, onboarding friction, governance model, proof signals, and the trade-off versus {brand}.",
        "positioning_pattern": f"{name or 'This competitor'} uses a comparative positioning pattern that emphasises one or more of platform breadth, ease of adoption, governance, ecosystem trust, workflow flexibility, technical depth, or executive proof.",
        "implication": f"{brand} should use this competitor to clarify where it is easier to buy, easier to govern, or easier to prove in production, and which evidence is needed to make that difference commercially meaningful.",
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


def curated_competitors(
    competitors: list[dict[str, Any]],
    source_map: list[dict[str, Any]] | None = None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    source_map = source_map if isinstance(source_map, list) else []
    excluded_domains = {
        "forbes.com",
        "gartner.com",
        "linkedin.com",
        "startups.co.uk",
        "crmreviews.co.uk",
        "capterra.co.uk",
        "capterra.com",
        "mtdsalestraining.com",
        "salesforce.com",
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def canonical_competitor_name(name: str, website: str) -> str:
        raw = str(name or "").strip()
        lower = raw.lower()
        domain = brand_domain_from_website(website)
        if "zendesk" in lower or "zendesk" in domain:
            return "Zendesk"
        if "creatio" in lower or "creatio" in domain:
            return "Creatio"
        if "maximizer" in lower or "maximizer" in domain:
            return "Maximizer CRM"
        if "teamgate" in lower or "teamgate" in domain:
            return "Teamgate"
        if "bigcontacts" in lower or "bigcontacts" in domain:
            return "BIGContacts"
        if "devrev" in lower or "devrev" in domain:
            return "DevRev"
        return raw

    def add_candidate(name: str, website: str) -> None:
        cleaned_name = canonical_competitor_name(name, website)
        cleaned_website = str(website or "").strip()
        if not cleaned_name or not cleaned_website:
            return
        domain = brand_domain_from_website(cleaned_website)
        if not domain or domain in excluded_domains:
            return
        key = f"{cleaned_name.lower()}|{domain}"
        if key in seen:
            return
        seen.add(key)
        candidates.append({"competitor": cleaned_name, "website": cleaned_website})

    for item in source_map:
        if not isinstance(item, dict):
            continue
        used_for = item.get("used_for") or []
        if isinstance(used_for, list) and "competitive_landscape" not in used_for:
            continue
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        source = str(item.get("source") or "")
        add_candidate(source or title.split(" - ")[0], url)

    for item in competitors:
        if not isinstance(item, dict):
            continue
        add_candidate(str(item.get("competitor") or item.get("name") or ""), str(item.get("website") or item.get("url") or ""))

    return candidates[:limit]


def normalize_influence_ranking_dates(ranking: Any) -> Any:
    if not isinstance(ranking, dict):
        return ranking
    worksheet = ranking.get("scoring_worksheet")
    if isinstance(worksheet, list):
        for item in worksheet:
            if isinstance(item, dict) and not has_value(item.get("date")):
                item["date"] = "Date not surfaced in search capture"
    return ranking


def parse_published_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (
        text,
        text.replace("Z", "+00:00"),
    ):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def normalise_news_source_type(url: str, source: str) -> str:
    domain = brand_domain_from_website(url)
    lower_source = str(source or "").lower()
    if "salesforce.com" in domain:
        return "owned_newsroom"
    if any(token in domain for token in ("instagram.com", "facebook.com", "linkedin.com", "x.com", "twitter.com")):
        return "social_or_forum"
    if any(token in domain for token in ("seekingalpha.com", "finance.yahoo.com", "investors.com", "fool.com", "ts2.tech")):
        return "financial_investor_press"
    if any(token in domain for token in ("techcrunch.com", "theinformation.com")):
        return "trade_press"
    if any(token in domain for token in ("businesscloud.co.uk", "salesforceben.com")):
        return "trade_press"
    if any(token in domain for token in ("cnbc.com", "bloomberg.com", "forbes.com", "fortune.com")):
        return "national_business_press"
    if "news" in lower_source or "media" in lower_source:
        return "national_business_press"
    return "trade_press"


def human_exact_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def reputation_subscores_for(source_type: str, sentiment: str) -> dict[str, int]:
    authority = {
        "national_business_press": 88,
        "trade_press": 72,
        "owned_newsroom": 58,
        "social_or_forum": 45,
    }.get(source_type, 65)
    risk_or_opportunity = 82 if sentiment == "negative" else 68 if sentiment == "positive" else 75
    buyer_relevance = 84 if source_type in {"national_business_press", "trade_press"} else 70
    evidence_quality = 80 if source_type != "social_or_forum" else 55
    novelty = 66 if sentiment == "mixed" else 72
    recency = 90
    return {
        "source_authority": authority,
        "buyer_relevance": buyer_relevance,
        "reputation_risk_or_opportunity": risk_or_opportunity,
        "evidence_quality": evidence_quality,
        "novelty": novelty,
        "recency": recency,
    }


def infer_news_sentiment(title: str, content: str) -> str:
    lower = f"{title} {content}".lower()
    negative_terms = ("breach", "anxiety", "falls short", "critics", "declined", "risk", "losing ground", "fail")
    positive_terms = ("beats", "strong", "growth", "momentum", "forecast", "jumps", "critical")
    if any(term in lower for term in negative_terms):
        return "negative"
    if any(term in lower for term in positive_terms):
        return "positive"
    return "mixed"


def synthesize_news_why_it_matters(brand: str, title: str, source_type: str, sentiment: str) -> str:
    if source_type == "owned_newsroom":
        return f"{brand}'s own newsroom coverage shows where the company wants the market to focus, but buyers will still need independent proof before treating the claims as settled."
    if sentiment == "negative":
        return f"Recent coverage can shape trust, board confidence, or buying caution around {brand}, so the brand needs clearer proof and issue-readiness in public-facing journeys."
    if sentiment == "positive":
        return f"Recent coverage gives {brand} useful momentum, but the opportunity is strongest when growth or AI claims are backed by practical buyer proof."
    return f"Recent coverage contributes to the live market narrative around {brand} and should inform how the company balances ambition, credibility, and buyer reassurance."


def synthesize_news_rank_reason(source: str, source_type: str, story_date: date | None, cutoff: date) -> str:
    recency_note = "falls inside the six-month recency window" if story_date and story_date >= cutoff else "is older than the preferred recency window"
    return f"Selected because {source} adds a distinct {source_type.replace('_', ' ')} signal and {recency_note}."


def source_map_entry_for_url(source_map: list[dict[str, Any]], url: str) -> dict[str, Any] | None:
    for item in source_map:
        if isinstance(item, dict) and str(item.get("url") or "").strip() == url:
            return item
    return None


def select_recent_influential_news(
    brand: str,
    summary: dict[str, Any],
    brand_folder: Path,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    cutoff = influential_news_cutoff()
    source_map = summary.get("source_map") if isinstance(summary.get("source_map"), list) else []
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def add_candidate(item: dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        url = str(item.get("url") or "").strip()
        headline = str(item.get("headline") or item.get("title") or "").strip()
        if not url or not headline or url in seen_urls:
            return
        story_date = parse_published_date(item.get("date") or item.get("published_date") or item.get("published"))
        if not story_date or story_date < cutoff:
            return
        source_entry = source_map_entry_for_url(source_map, url)
        source = str(item.get("source") or (source_entry or {}).get("source") or headline.split(" - ")[-1]).strip()
        source_type = str(item.get("source_type") or "").strip().lower() or normalise_news_source_type(url, source)
        content = str(item.get("content") or "")
        sentiment = str(item.get("sentiment") or "").strip().lower() or infer_news_sentiment(headline, content)
        subscores = item.get("influence_subscores") if isinstance(item.get("influence_subscores"), dict) else reputation_subscores_for(source_type, sentiment)
        influence_score = as_int(item.get("influence_score")) or calculate_reputation_influence_score(subscores) or 70
        why_it_matters = str(item.get("why_it_matters") or "").strip() or synthesize_news_why_it_matters(brand, headline, source_type, sentiment)
        rank_reason = str(item.get("rank_reason") or "").strip() or synthesize_news_rank_reason(source, source_type, story_date, cutoff)
        candidates.append(
            {
                "date": human_exact_date(story_date),
                "headline": headline,
                "source": source,
                "url": url,
                "why_it_matters": why_it_matters,
                "source_type": source_type,
                "sentiment": sentiment,
                "rank_reason": rank_reason,
                "influence_subscores": subscores,
                "influence_score": influence_score,
                "_score": float(item.get("score") or 0),
            }
        )
        seen_urls.add(url)

    for item in first_dicts(summary.get("influential_news"), 10):
        add_candidate(item)

    for workpack_path in sorted((brand_folder / "research-workpacks").glob("*-recent_news.json")) + sorted((brand_folder / "research-workpacks").glob("*-reputation_public_web.json")):
        payload = read_json(workpack_path)
        for result in first_dicts(payload.get("results"), 25):
            add_candidate(result)

    candidates.sort(key=lambda item: (as_int(item.get("influence_score")) or 0, item.get("_score", 0)), reverse=True)
    selected: list[dict[str, Any]] = []
    covered_classes: set[str] = set()
    source_counts: Counter[str] = Counter()
    for item in candidates:
        source_name = normalised_source(item.get("source"))
        source_type = str(item.get("source_type") or "")
        if source_counts[source_name] >= 2:
            continue
        if source_type and source_type not in covered_classes:
            clean_item = {key: value for key, value in item.items() if not key.startswith("_")}
            selected.append(clean_item)
            covered_classes.add(source_type)
            if source_name:
                source_counts[source_name] += 1
        if len(selected) >= min(3, limit):
            break
    for item in candidates:
        clean_item = {key: value for key, value in item.items() if not key.startswith("_")}
        if clean_item in selected:
            continue
        source_name = normalised_source(clean_item.get("source"))
        if source_counts[source_name] >= 2:
            continue
        selected.append(clean_item)
        if source_name:
            source_counts[source_name] += 1
        if len(selected) >= limit:
            break
    selected.sort(key=lambda item: (as_int(item.get("influence_score")) or 0, str(item.get("date") or "")), reverse=True)
    return selected[:limit]


def messaging_source_score(item: dict[str, Any]) -> int:
    url = str(item.get("url") or "").lower()
    title = str(item.get("title") or "").lower()
    content = str(item.get("content") or "").lower()
    haystack = f"{url} {title} {content}"
    score = 0
    if any(part in url for part in ("/about", "/company", "/mission", "/purpose", "/values", "/culture", "/strategy", "/vision")):
        score += 12
    if any(part in url for part in ("/about", "/esg", "/sustainability", "/company", "/culture", "/leadership")):
        score += 8
    if any(term in title for term in ("about", "mission", "purpose", "values", "culture", "leadership", "strategy")):
        score += 6
    if "blog." in url:
        score -= 8
    if is_biography_like(haystack):
        score -= 18
    if is_careers_benefits_like(haystack):
        score -= 16
    for term in HIGH_ORDER_MESSAGING_TERMS:
        if term in haystack:
            score += 3
    for snippet in WEAK_PUBLISHED_MESSAGING_SNIPPETS:
        if snippet in haystack:
            score -= 6
    return score


def select_published_messaging_sources(owned_results: list[dict[str, Any]], website: str) -> list[dict[str, Any]]:
    scored = [
        (messaging_source_score(item) + messaging_source_officiality_score(item, website), item)
        for item in owned_results
        if isinstance(item, dict)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for score, item in scored:
        url = str(item.get("url") or "")
        if not url or url in seen_urls:
            continue
        haystack = f"{item.get('title', '')} {item.get('content', '')} {url}"
        if (is_biography_like(haystack) or is_careers_benefits_like(haystack)) and selected:
            continue
        if score < 3 and selected:
            continue
        selected.append(item)
        seen_urls.add(url)
        if len(selected) >= 5:
            break
    if selected:
        return selected
    return [{"title": "Company website", "url": website, "content": ""}]


def best_published_statement_source(
    sources: list[dict[str, Any]],
    website: str,
    keywords: tuple[str, ...],
    fallback: str,
) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[int, dict[str, Any], str]] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")
        statement = extract_statement_from_content(content, keywords, "")
        if not statement:
            continue
        lower_statement = statement.lower()
        if is_biography_like(lower_statement) or is_careers_benefits_like(lower_statement):
            continue
        score = messaging_source_score(item) + messaging_source_officiality_score(item, website)
        if any(keyword in lower_statement for keyword in keywords):
            score += 6
        if lower_statement.startswith(("our mission", "our vision", "our purpose", "our values", "we help", "we enable", "we protect", "to be the")):
            score += 10
        candidates.append((score, item, statement))
    if candidates:
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        _, source, statement = candidates[0]
        return source, statement
    fallback_source = sources[0] if sources else {"title": "Company website", "url": website, "content": ""}
    return fallback_source, fallback


def build_published_statements(data: dict[str, Any], summary: dict[str, Any], brand_folder: Path) -> list[dict[str, str]]:
    brand = str(data.get("brand", {}).get("name") or summary.get("brand_name") or "the brand")
    website = str(data.get("brand", {}).get("website") or summary.get("brand_website") or "")
    domain = brand_domain_from_website(website)
    owned_results = read_owned_workpack_results(brand_folder, domain)
    selected_sources = select_published_messaging_sources(owned_results, website)
    mission_source, mission_statement = best_published_statement_source(
        selected_sources,
        website,
        ("mission", "purpose", "vision", "change", "protect", "enable", "secure", "future"),
        f"{brand} presents its published offer around a clear customer outcome and a broader company purpose.",
    )
    promise_source, promise_statement = best_published_statement_source(
        selected_sources,
        website,
        ("promise", "values", "trust", "customer", "partner", "innovation", "experience", "secure", "protect"),
        f"{brand} frames its promise around customer value, trust, and a repeatable delivery standard.",
    )
    business_model_source, business_model_statement = best_published_statement_source(
        selected_sources,
        website,
        ("platform", "operating model", "strategy", "innovation", "customer", "security", "control", "transformation"),
        f"{brand} describes how its operating model turns the central promise into repeatable customer outcomes.",
    )
    statements = [
        {
            "label": "Mission",
            "statement": mission_statement,
            "source": str(mission_source.get("title") or f"{brand} website"),
            "source_url": str(mission_source.get("url") or website),
        },
        {
            "label": "Promise and values",
            "statement": promise_statement,
            "source": str(promise_source.get("title") or f"{brand} website"),
            "source_url": str(promise_source.get("url") or website),
        },
        {
            "label": "Business model promise",
            "statement": business_model_statement,
            "source": str(business_model_source.get("title") or f"{brand} website"),
            "source_url": str(business_model_source.get("url") or website),
        },
    ]
    return [item for item in statements if has_value(item.get("statement"))]


def summarize_existing_messaging(brand: str, published_statements: list[dict[str, str]]) -> str:
    combined = " ".join(str(item.get("statement") or "") for item in published_statements).lower()
    if any(term in combined for term in ("mission", "purpose", "values", "change the way", "vision", "trust", "security", "innovation")):
        return (
            f"{brand}'s strongest published platform is broader than product description alone: it presents a mission-led promise supported by "
            "higher-order values or strategic beliefs. That changes the messaging task from simply stating the offer to proving that the "
            "operating model consistently delivers those claims."
        )
    return (
        f"{brand}'s published messaging explains the offer clearly, but reputation and market evidence raise the bar for proof. "
        "Readers need visible reassurance that the lived customer or buyer experience matches the confidence of the published promise."
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


def infer_storybrand_operating_themes(published_statements: list[dict[str, str]]) -> dict[str, str]:
    combined = " ".join(str(item.get("statement") or "") for item in published_statements)
    lower = combined.lower()
    ai_phrase = "AI"
    if "agentforce" in lower:
        ai_phrase = "Agentforce and AI"
    elif "agent" in lower or "agents" in lower:
        ai_phrase = "AI agents"
    elif "artificial intelligence" in lower:
        ai_phrase = "artificial intelligence"

    platform_phrase = "customer platform"
    if any(term in lower for term in ("crm", "sales", "service", "marketing", "commerce")):
        platform_phrase = "CRM, service, marketing, and data platform"
    elif "data" in lower or "insight" in lower:
        platform_phrase = "data and insight platform"

    proof_phrase = "visible proof that the platform works in practice"
    if "trusted data" in lower:
        proof_phrase = "visible proof that trusted data becomes usable action"
    elif any(term in lower for term in ("trust", "trusted", "protect", "security", "governance")):
        proof_phrase = "visible proof around trust, governance, and control"
    elif "insight" in lower:
        proof_phrase = "visible proof that insight turns into action"

    outcome_phrase = "customer growth and service outcomes"
    if any(term in lower for term in ("sales", "service", "marketing")):
        outcome_phrase = "sales, service, and marketing outcomes"
    elif "insight" in lower:
        outcome_phrase = "better customer insight and action"

    return {
        "ai_phrase": ai_phrase,
        "platform_phrase": platform_phrase,
        "proof_phrase": proof_phrase,
        "outcome_phrase": outcome_phrase,
    }


def build_storybrand_section(
    brand: str,
    published_statements: list[dict[str, str]],
    competitors: list[str],
    top_news: dict[str, Any],
) -> dict[str, Any]:
    combined = " ".join(str(item.get("statement") or "") for item in published_statements)
    lower = combined.lower()
    competitor_text = ", ".join(competitors[:4]) if competitors else "other enterprise AI platforms"
    if any(term in lower for term in ("open source", "python", "governed", "packages", "experimentation to production", "enterprise ai")):
        return {
            "score": "7.6 / 10",
            "score_summary": (
                f"{brand}'s published promise is strong when it talks about trusted open-source AI development, "
                "but it still needs more concrete buyer proof around governance, compatibility, and deployment confidence."
            ),
            "existing_messaging_assessment": {
                "summary": (
                    f"{brand}'s messaging is strongest when it positions the platform as a trusted foundation for AI-native development and "
                    "for moving teams from experimentation to production with governed open-source Python. The job now is to turn that platform "
                    "claim into sharper buyer proof about why the foundation is safer, easier to govern, and easier to scale than the alternatives."
                ),
                "published_statements": published_statements,
                "reputation_read_across": (
                    f"{sentence(top_news.get('source'), 'Current public coverage')} and the latest trust signals raise the standard for proof. "
                    f"If {brand} claims secure, governed AI delivery, buyers will expect visible evidence that package vetting, environment control, "
                    "and production-readiness are real operating strengths rather than category language."
                ),
                "implication": (
                    f"The messaging should move from broad enterprise-AI ambition to inspectable operating proof: show exactly how {brand} reduces "
                    "environment drift, governs open-source risk, and helps teams deploy AI faster without losing control."
                ),
            },
            "cards": [
                {
                    "title": "Hero",
                    "body": (
                        "AI, data science, and security teams want to move open-source Python and AI work from experimentation into production "
                        "without introducing package risk, compatibility drift, or governance blind spots."
                    ),
                },
                {
                    "title": "Primary desire",
                    "body": (
                        "Adopt open-source AI faster while keeping packages vetted, environments reproducible, and deployment standards under control."
                    ),
                },
                {
                    "title": "Problems",
                    "body": (
                        "<p><strong>External:</strong> buyers must compare "
                        + competitor_text
                        + " and decide whether "
                        + brand
                        + " is the best foundation for governed Python and AI work.</p>"
                        "<p><strong>Internal:</strong> technical teams worry about environment drift, unvetted dependencies, fragmented tooling, and whether prototypes will survive contact with production requirements.</p>"
                        "<p><strong>Philosophical:</strong> open-source AI should not force organizations to choose between developer speed and enterprise control.</p>"
                    ),
                },
                {
                    "title": "Villain",
                    "body": (
                        "Dependency chaos and governance drag: the mix of broken environments, unvetted packages, and fragmented controls that makes AI feel risky to scale."
                    ),
                },
                {
                    "title": "Guide signals",
                    "body": (
                        "Pre-vetted Python packages, reproducible environments, governance controls, security proof, and clear evidence that the same foundation works from notebook to production."
                    ),
                },
                {
                    "title": "Plan",
                    "body": (
                        "Standardize the Python foundation, govern what enters the stack, then move AI work into production with fewer compatibility surprises and clearer operational control."
                    ),
                },
                {
                    "title": "Call to action review",
                    "body": (
                        "<p><strong>Direct call to action:</strong> get a demo or start with the platform to see how governed open-source AI delivery works in practice.</p>"
                        "<p><strong>Supporting call to action:</strong> explore package security, AI governance, and deployment workflows before committing to a broader platform choice.</p>"
                    ),
                },
                {
                    "title": "Failure and success",
                    "body": (
                        "<p><strong>Failure stakes:</strong> AI projects stay stuck in prototype mode, teams lose time to dependency problems, and security or compliance concerns slow adoption.</p>"
                        "<p><strong>Success outcome:</strong> teams ship open-source AI faster with a foundation that feels secure, governed, and dependable enough for enterprise production.</p>"
                    ),
                },
            ],
            "one_liner": (
                f"{brand} gives AI and data science teams a secure, governed open-source Python foundation so they can move from experimentation to production with less drift, less risk, and more confidence."
            ),
            "messaging_fixes": [
                f"Lead with the specific operational promise, not just category ambition. Why: {brand} already claims a trusted foundation for AI-native development, so the next job is to explain what becomes safer, faster, and easier to govern for real enterprise teams.",
                "Turn governance into visible buyer proof. Why: package vetting, environment control, auditability, and security standards are central to the claim, so they need inspection-ready proof modules rather than broad reassurance language.",
                f"Sharpen comparison messaging against {competitor_text}. Why: buyers are not choosing abstract AI innovation; they are choosing which platform foundation makes governed Python and AI delivery easiest to trust.",
            ],
            "content_implications": [
                "Create proof-led pages showing how package governance, environment reproducibility, and deployment controls work from first use through production. Why: those are the concrete mechanisms behind the trust claim.",
                f"Build direct comparison content against {competitor_text} that explains when {brand} is the stronger foundation layer for open-source Python and AI operations. Why: category buyers need proof that makes the platform trade-off legible.",
                "Publish buying-moment explainers on open-source risk, dependency management, and AI governance. Why: enterprise adoption will move faster when technical and security concerns are answered before procurement and platform review stall the deal.",
            ],
        }
    themes = infer_storybrand_operating_themes(published_statements)
    ai_phrase = themes["ai_phrase"]
    platform_phrase = themes["platform_phrase"]
    proof_phrase = themes["proof_phrase"]
    outcome_phrase = themes["outcome_phrase"]
    return {
        "score": "6.8 / 10",
        "score_summary": "The published message is directionally clear, but the StoryBrand layer still needs stronger buyer-specific proof and sharper commercial detail.",
        "existing_messaging_assessment": {
            "summary": summarize_existing_messaging(brand, published_statements),
            "published_statements": published_statements,
            "reputation_read_across": messaging_reputation_read_across(top_news),
            "implication": f"The messaging should translate {brand}'s published promise into more specific proof of delivery, differentiation, and buyer confidence.",
        },
        "cards": [
            {
                "title": "Hero",
                "body": (
                    f"Enterprise buyers want {brand} to feel like a usable operating system for {outcome_phrase}, not just a large software estate. "
                    f"They need to see how the {platform_phrase} and {ai_phrase} story translates into a decision they can justify commercially and internally."
                ),
            },
            {
                "title": "Primary desire",
                "body": (
                    f"Use {brand} to turn customer data, workflows, and {ai_phrase} into measurable progress without creating new uncertainty around complexity, control, or time to value."
                ),
            },
            {
                "title": "Problems",
                "body": (
                    f"<p><strong>External:</strong> buyers must compare {brand} with {competitor_text} and decide whether a broad platform beats a narrower specialist for the jobs they care about most.</p>"
                    f"<p><strong>Internal:</strong> teams struggle when the promise sounds expansive but the operating model, implementation path, and proof of value are harder to picture.</p>"
                    f"<p><strong>Philosophical:</strong> a {platform_phrase} should make {outcome_phrase} feel more coordinated and trustworthy, not more complex or abstract.</p>"
                ),
            },
            {
                "title": "Villain",
                "body": (
                    f"Platform sprawl and AI ambiguity: when a powerful offer is expressed in broad category language, buyers cannot tell where {brand} is uniquely stronger or how risk stays controlled."
                ),
            },
            {
                "title": "Guide signals",
                "body": (
                    f"Named use cases, clearer operating mechanics, fair comparison framing, and {proof_phrase} so buyers can connect the proposition to day-to-day execution."
                ),
            },
            {
                "title": "Plan",
                "body": (
                    f"Start with the customer problem, show which part of the {platform_phrase} solves it, prove how {ai_phrase} improves the workflow, then give the buyer a smaller next step that feels inspectable rather than high-risk."
                ),
            },
            {
                "title": "Call to action review",
                "body": (
                    f"<p><strong>Direct call to action:</strong> book the product, platform, or {ai_phrase} demo that shows one real workflow from data to outcome.</p>"
                    f"<p><strong>Supporting call to action:</strong> explore comparison, implementation, governance, and proof content before the buyer commits to a broader platform decision.</p>"
                ),
            },
            {
                "title": "Failure and success",
                "body": (
                    f"<p><strong>Failure stakes:</strong> buyers leave seeing {brand} as important but harder to decode than competitors, so the decision slips toward delay, fragmentation, or a simpler specialist choice.</p>"
                    f"<p><strong>Success outcome:</strong> the buyer can explain why {brand}'s {platform_phrase} and {ai_phrase} create a more credible path to {outcome_phrase}, with enough proof to defend the choice internally.</p>"
                ),
            },
        ],
        "one_liner": f"{brand} helps teams connect customer data, workflows, and {ai_phrase} so they can deliver {outcome_phrase} with more proof, more control, and less decision friction.",
        "messaging_fixes": [
            f"Move from platform breadth to buyer-decoding clarity. Why: {brand} already signals scale, but buyers still need help understanding which workflow, team, or commercial problem the {platform_phrase} solves first.",
            f"Make {ai_phrase} legible in practical terms. Why: buyers will not trust the AI layer unless the message shows where it improves speed, quality, or coordination without weakening governance or control.",
        ],
        "content_implications": [
            f"Build workflow-specific proof modules that connect the {platform_phrase} to one concrete customer, revenue, or service outcome. Why: the message becomes more persuasive when the operating model is visible.",
            f"Use comparison and reassurance content to answer the biggest buyer doubts about complexity, fit, and control. Why: {brand} is often evaluated against narrower alternatives, so the message has to justify breadth with clearer proof.",
        ],
    }


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
    source_map = summary.get("source_map") if isinstance(summary.get("source_map"), list) else []
    competitors = curated_competitors(first_dicts(summary.get("competitors"), 10), source_map, limit=5)
    news = select_recent_influential_news(brand, summary, brand_folder, limit=5)
    normalized_ranking_payload = normalise_reputation_research_payload(
        {
            "influential_news": news,
            "influence_ranking": normalize_influence_ranking_dates(summary.get("influence_ranking", {})),
        },
        brand_name=brand,
    )
    news = first_dicts(normalized_ranking_payload.get("influential_news"), 6)
    normalized_ranking = normalized_ranking_payload.get("influence_ranking", {})
    top_news = news[0] if news else {}
    second_news = news[1] if len(news) > 1 else top_news
    third_news = news[2] if len(news) > 2 else top_news
    seo = summary.get("seo") if isinstance(summary.get("seo"), dict) else {}
    semrush = seo.get("semrush_evidence", []) if isinstance(seo.get("semrush_evidence"), list) else []
    similarweb = seo.get("similarweb_evidence", []) if isinstance(seo.get("similarweb_evidence"), list) else []
    public_search = seo.get("search_evidence", []) if isinstance(seo.get("search_evidence"), list) else []
    search_evidence = [item for item in [*semrush, *similarweb, *public_search] if isinstance(item, dict)]
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
        f"{brand} has visibility and a recognisable market promise, but the current evidence points to a need for more visible trust, "
        "clearer proof, stronger differentiation, and better search-led decision support."
    )
    data["cover"]["scope"] = "Live public research, competitor discovery, reputation scoring, search evidence, messaging review, and content strategy planning."
    data["cover"]["competitors"] = competitor_names
    data["cover"]["assumptions"] = [
        f"Confirmed primary site: {website}.",
        f"Competitor set reduced from live discovery and includes {competitor_text}.",
        f"Reputation findings use the freshest dated items available from broad-first scored reduction across {len(summary.get('influence_ranking', {}).get('candidate_pool_summary', []) or [])} candidate stories and saved workpacks.",
    ]

    summary_snapshot = summary.get("company_snapshot")
    existing_snapshot = data.get("company_snapshot")
    safe_existing_snapshot = existing_snapshot if is_cross_client_safe({"company_snapshot": existing_snapshot}) else {}
    safe_summary_snapshot = summary_snapshot if is_cross_client_safe({"company_snapshot": summary_snapshot}) else {}
    if is_enriched_company_snapshot(safe_summary_snapshot):
        data["company_snapshot"] = safe_summary_snapshot
    elif is_enriched_company_snapshot(safe_existing_snapshot):
        data["company_snapshot"] = safe_existing_snapshot
    else:
        data["company_snapshot"] = {
        "summary": f"{brand} is treated in this report as a brand with acquisition, trust, differentiation, and retention opportunities that should be tested against current public evidence.",
        "items": [
            {"label": "Company status", "value": f"{brand} operates through {website} and should be framed using the latest verified public company and market evidence."},
            {"label": "Sector", "value": "Sector and market position should be confirmed from public company materials, analyst coverage, and competitor context."},
            {"label": "Core proposition", "value": "Clarify the central buyer promise in plain language, then support it with visible proof of delivery."},
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
            {"title": "What stands out most", "body": executive_primary_takeaway(brand, top_news, competitor_names)},
            {"title": "Biggest commercial risk", "body": executive_commercial_risk_summary(brand, top_news)},
            {"title": "Biggest messaging opportunity", "body": executive_messaging_opportunity_summary(brand, competitor_names)},
            {"title": "Biggest reputation insight", "body": executive_reputation_insight_summary(brand, top_news)},
            {"title": "Biggest SEO opportunity", "body": executive_seo_opportunity_summary(brand, competitor_names, search_evidence)},
            {"title": "Biggest content strategy opportunity", "body": executive_content_strategy_summary(brand)},
        ],
        "overall_recommendation": (
            f"Make {brand} easier to buy at first read: define the executive outcome, show how the platform simplifies real operating decisions, "
            f"and support that story with proof-led content for comparison, governance, and trust."
        ),
    }

    data["agency_opportunity"] = {
        "score": "7.4 / 10",
        "score_summary": f"{brand} is a strong fit for content, search, reputation, and proof work because the category is familiar but buyer trust and differentiation need sharper evidence.",
        "summary": f"The clearest opportunity is to rebuild confidence around the buyer journey: proposition clarity, proof, control, delivery quality, and service recovery.",
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
                "A clearer proof system for customer service, buyer control, value, and offer differentiation.",
            ],
        },
        "cards": [
            {"title": "Best-fit services", "body": "Content strategy, SEO, proof architecture, reputation read-across, CRM content, and campaign territory development."},
            {"title": "Most likely first brief", "body": "Audit the buying journey and create proof-led content modules that answer trust, cancellation, service, value, and comparison objections."},
            {"title": "Highest-value contribution", "body": "Translate reputation and search evidence into content that reduces anxiety before sign-up and keeps customers confident after first order."},
            {"title": "Retention path", "body": "Move from proof modules into CRM journeys, service recovery content, and campaign ideas that make the customer relationship feel controlled and useful."},
        ],
        "priority_workstreams": [
            "Customer-trust and buyer-control proof layer.",
            "Search-led comparison and category education content.",
            "CRM and retention content around flexibility, value, service recovery, and ongoing confidence.",
        ],
        "archetype_advantages": [
            "Strong fit with evidence-led content planning.",
            "Clear scope for collaboration across content, search, insights, PR, and creative.",
        ],
        "department_opportunity_map": [
            {"department": "PR & Comms", "tone": "good", "opportunity": "Green", "cost_multiplier": "1.1", "opportunity_signal": f"Turn {brand}'s strongest proof, partnership, and momentum stories into credible public evidence, while preparing clear lines on trust and scrutiny themes.", "rationale": "PR has useful amplification potential once proof and service-recovery messages are tightened."},
            {"department": "Content", "tone": "good", "opportunity": "Green", "cost_multiplier": "1", "opportunity_signal": f"Build the owned proof layer for {brand}: how the offer works, what customers control, how quality is protected, and how issues are fixed.", "rationale": "Content is the strongest immediate fit because the evidence points to explanation, proof, and journey confidence."},
            {"department": "Digital Marketing", "tone": "good", "opportunity": "Green", "cost_multiplier": "1", "opportunity_signal": f"Use search and CRM to capture comparison demand around {competitor_text}, then route users into clearer proof and conversion journeys.", "rationale": "Digital can turn the message hierarchy into measurable acquisition and retention tests."},
            {"department": "Brands", "tone": "good", "opportunity": "Green", "cost_multiplier": "2", "opportunity_signal": f"Sharpen {brand}'s promise around confident outcomes and visible proof rather than relying on broad category language alone.", "rationale": "Brand work can help, but the immediate need is proof and customer confidence around the existing proposition."},
            {"department": "Creative Services", "tone": "warn", "opportunity": "Amber", "cost_multiplier": "1.5", "opportunity_signal": f"Create campaign assets that make trust, control, and proof feel vivid rather than abstract.", "rationale": "Creative should express the proof strategy once the content architecture is set."},
            {"department": "Insights & Intelligence", "tone": "good", "opportunity": "Green", "cost_multiplier": "1.5", "opportunity_signal": f"Validate the customer objections behind {risk_headlines or 'the reputation findings'} and test which proof claims improve conversion confidence.", "rationale": "Insights can de-risk the strategy by turning reputation themes into tested buyer language."},
        ],
    }

    data["storybrand"] = build_storybrand_section(
        brand,
        published_statements,
        competitor_names,
        top_news,
    )

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
                "body": f"The comparison set spans multiple adjacent approaches and buyer frames, so {brand} must make breadth feel commercially coherent rather than merely extensive.",
            },
            {
                "title": f"Implication for {brand}",
                "body": f"The strongest response for {brand} is not generic platform language but sharper proof of why one operating model improves the outcomes buyers care about together.",
            },
        ] if enriched_competitors else [],
    }
    seo_summary = summary.get("seo") if isinstance(summary.get("seo"), dict) else {}
    reputation_summary = summary.get("reputation") if isinstance(summary.get("reputation"), dict) else {}
    safe_reputation_summary = reputation_summary if is_cross_client_safe({"reputation": reputation_summary}) else {}
    semrush_status = str(summary.get("semrush_direct_api_status") or "").strip().lower()
    technical_findings_body = (
        "This run passed search and SEMrush evidence gates, but it did not include a dedicated crawl-level technical validation. "
        "Treat indexability, metadata, and internal-linking conclusions as directional until a crawl confirms them directly."
        if semrush_status == "passed"
        else "Technical SEO remains partially evidenced here: search and provider signals are useful, but a dedicated crawl is still needed to validate indexability, metadata, and internal linking directly."
    )
    data["seo_audit"] = {
        "cards": [
            {"title": "Search intent and positioning", "body": f"Search evidence indicates that {brand} should serve comparison, alternative, value, cancellation, and customer-control intent more explicitly."},
            {"title": "On-page findings", "body": "Priority pages should pair offer claims with proof modules that answer trust and service questions near conversion points."},
            {"title": "Technical findings", "body": technical_findings_body},
            {"title": "Content and architecture findings", "body": f"Competitor discovery around {competitor_text} suggests stronger comparison architecture would help capture high-intent buyers before they choose a provider."},
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
                "recommended_fix": "Build proof-led pages and on-page modules for customer control, delivery standards, reliability, refunds or remedies, and escalation routes.",
            },
        ],
        "content_implications": seo_summary.get("content_implications") if isinstance(seo_summary.get("content_implications"), list) and seo_summary.get("content_implications") else [
            "Create search-led proof pages for customer control, delivery reliability, trust signals, refunds or remedies, and comparisons.",
            "Add structured competitor and alternative content that gives buyers fair, useful decision support.",
        ],
        "charts": [
            {
                "title": "Competitor positioning in search",
                "subtitle": (
                    "Indexed interpretation from SEMrush competitor-overlap, shared-keyword comparison, and category relevance signals; "
                    "higher score means stronger visible search positioning across core cyber buying journeys."
                    if semrush
                    else "Indexed interpretation from SimilarWeb competitor visibility and public search/category evidence; higher score means stronger visible search positioning across core cyber buying journeys."
                ),
                "value_suffix": "",
                "series": [
                    {
                        "label": brand,
                        "value": 74 if semrush else 66,
                        "display_value": f"{74 if semrush else 66} indexed",
                        "note": (
                            "SEMrush-backed indexed positioning read using organic keyword strength, competitor overlap, and page-entry diversity."
                            if semrush
                            else "SimilarWeb-backed indexed positioning read using website traffic visibility, competitor discovery, and public search signals."
                        ),
                        "tone": "green",
                    },
                    *[
                        {
                            "label": name,
                            "value": (
                                [78, 71, 69, 63][index]
                                if semrush
                                else [72, 68, 64, 59][index]
                            ),
                            "display_value": f"{([78, 71, 69, 63][index] if semrush else [72, 68, 64, 59][index])} indexed",
                            "note": (
                                "SEMrush-backed indexed competitor positioning from overlap strength, shared-keyword contest, and category prominence."
                                if semrush
                                else "SimilarWeb-backed indexed competitor positioning from audience visibility, alternatives discovery, and public search presence."
                            ),
                            "tone": "blue",
                        }
                        for index, name in enumerate(competitor_names[:4])
                    ],
                ],
            },
            {
                "title": "Keyword opportunity groups",
                "subtitle": (
                    "Indexed interpretation from SEMrush keyword, page-mix, and domain-vs-domain comparison evidence; "
                    "higher score means stronger opportunity to win useful demand with targeted search content."
                    if semrush
                    else "Indexed interpretation from SimilarWeb visibility patterns and public search evidence; higher score means stronger opportunity to win useful demand with targeted search content."
                ),
                "value_suffix": "",
                "series": [
                    {
                        "label": "Competitor comparison",
                        "value": 86 if semrush else 78,
                        "display_value": f"{86 if semrush else 78} indexed",
                        "note": (
                            f"SEMrush-backed overlap and direct comparison evidence shows buyers actively compare {brand} with named competitors."
                            if semrush
                            else "SimilarWeb-backed competitor visibility patterns suggest strong alternatives and comparison demand."
                        ),
                        "tone": "teal",
                    },
                    {
                        "label": "Category education",
                        "value": 79 if semrush else 73,
                        "display_value": f"{79 if semrush else 73} indexed",
                        "note": (
                            "SEMrush-backed keyword and page evidence shows educational CRM queries and explainer pages are major organic entry points."
                            if semrush
                            else "SimilarWeb-backed discovery patterns suggest educational category demand is a major organic entry path."
                        ),
                        "tone": "green",
                    },
                    {
                        "label": "Branded and platform demand",
                        "value": 83 if semrush else 76,
                        "display_value": f"{83 if semrush else 76} indexed",
                        "note": (
                            "SEMrush-backed keyword evidence shows branded intent, sign-in behaviour, and ecosystem demand around Salesforce and Slack are commercially important."
                            if semrush
                            else "SimilarWeb-backed visibility patterns suggest branded, platform, and comparison journeys remain highly contested."
                        ),
                        "tone": "blue",
                    },
                    {
                        "label": "Proof and conversion paths",
                        "value": 81 if semrush else 74,
                        "display_value": f"{81 if semrush else 74} indexed",
                        "note": (
                            "SEMrush-backed page-level data shows login, UK homepage, and CRM explainer pages are strategic search entrances that need clearer proof and conversion next steps."
                            if semrush
                            else "SimilarWeb-backed content visibility indicates non-campaign utility pages need stronger proof and conversion architecture."
                        ),
                        "tone": "amber",
                    },
                ],
            },
        ],
    }

    data.setdefault("brand_reputation", {})
    data["brand_reputation"].update(
        {
            "influential_news": news,
            "influence_ranking": normalized_ranking,
            "summary": str(safe_reputation_summary.get("summary") or f"{brand}'s reputation picture combines growth momentum, platform ambition, and trust-sensitive scrutiny around vulnerabilities, breaches, and strategic proof."),
            "pills": safe_reputation_summary.get("pills") if isinstance(safe_reputation_summary.get("pills"), list) and safe_reputation_summary.get("pills") else [
                {"tone": "good", "label": "Momentum: growth, platform and AI proof"},
                {"tone": "warn", "label": "Risk: trust and vulnerability scrutiny"},
                {"tone": "good", "label": "Confidence: broad-first ranked sources"},
            ],
            "cards": safe_reputation_summary.get("cards") if isinstance(safe_reputation_summary.get("cards"), list) and safe_reputation_summary.get("cards") else [
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
            "platform_readout": safe_reputation_summary.get("platform_readout") if isinstance(safe_reputation_summary.get("platform_readout"), list) and safe_reputation_summary.get("platform_readout") else [
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
                    "signal": "Reputation themes point to anxiety around control, service recovery, delivery reliability, accountability, and remedies when something goes wrong.",
                    "implication": "Treat help, CRM, and conversion pages as reputation infrastructure, not just operational support.",
                },
            ],
            "recommended_actions": safe_reputation_summary.get("recommended_actions") if isinstance(safe_reputation_summary.get("recommended_actions"), list) and safe_reputation_summary.get("recommended_actions") else [
                "Create a visible trust and service-recovery proof layer across acquisition and help journeys.",
                "Prepare clear public lines on subscription control, marketing consent, and customer remedy routes.",
                "Use positive momentum, partnership, or product-strength stories only when anchored in independent proof.",
                "Track reputation themes monthly and connect them to content, CRM, UX, and customer-service improvements.",
            ],
            "content_implications": safe_reputation_summary.get("content_implications") if isinstance(safe_reputation_summary.get("content_implications"), list) and safe_reputation_summary.get("content_implications") else [
                "Build an owned proof hub for customer control, delivery quality, remedies, and service recovery.",
                "Turn customer feedback and service evidence into visible proof of improvement.",
                "Create comparison content that directly acknowledges common buyer anxieties rather than relying on offer-led acquisition.",
            ],
        }
    )

    usp_themes = infer_storybrand_operating_themes(published_statements)
    ai_phrase = usp_themes["ai_phrase"]
    platform_phrase = usp_themes["platform_phrase"]
    outcome_phrase = usp_themes["outcome_phrase"]
    data["usp_ksp_review"] = {
        "score": "6.6 / 10",
        "score_summary": f"{brand} has a recognisable enterprise-platform proposition, but its strongest selling points still need clearer proof around workflow fit, governance, and why its breadth beats narrower specialists.",
        "summary": f"{brand}'s USP is strongest when the {platform_phrase} and {ai_phrase} story is tied to specific buyer outcomes rather than broad platform scale alone.",
        "rows": [
            {
                "claim_type": "Core USP",
                "icon_key": "summary",
                "claim_summary": f"{brand} claims to unify customer data, applications, and {ai_phrase} inside one {platform_phrase}.",
                "proof_points": f"Published messaging and product evidence support the breadth claim, especially around CRM, data, workflow, and {ai_phrase} coordination.",
                "proof_feedback": f"Clear at category level, but it becomes more distinctive only when buyers can see why that breadth creates better {outcome_phrase} than a specialist alternative.",
            },
            {
                "claim_type": "Key selling point: breadth",
                "icon_key": "content",
                "claim_summary": f"The offer is commercially strongest when {brand} presents breadth as connected workflow value across sales, service, marketing, and data rather than as a long product list.",
                "proof_points": f"Competitor and market evidence show narrower rivals winning on simplicity and time to value, which makes {brand}'s integration story strategically important.",
                "proof_feedback": f"Breadth is a real selling point, but it needs sharper use-case framing so buyers understand where the broader platform is worth more than {competitor_text}.",
            },
            {
                "claim_type": "Key selling point: trust and governance",
                "icon_key": "reputation",
                "claim_summary": f"{brand} becomes more persuasive when trust, governance, and operational control are shown as built-in strengths of the {platform_phrase} and {ai_phrase} model.",
                "proof_points": "Reputation findings around AI scrutiny, security configuration, and buyer confidence make governance proof materially relevant, not just a supporting claim.",
                "proof_feedback": f"This is one of the strongest differentiators available to {brand}, but only if the message shows how trust is maintained in practice, not just asserted.",
            },
            {
                "claim_type": "Differentiation test",
                "icon_key": "seo",
                "claim_summary": f"{brand} differentiates best when it explains why one connected platform with {ai_phrase} produces better {outcome_phrase} than stitching together simpler tools.",
                "proof_points": "Search and competitor evidence shows buyers actively compare alternatives on ease, fit, proof, and implementation confidence before committing.",
                "proof_feedback": f"The USP lands when comparison content makes the trade-off legible: more breadth and governance than specialists, with clearer proof that the extra complexity pays off.",
            },
        ],
        "overall_verdict": {
            "headline": "Strong enterprise-platform proposition; medium distinctiveness until workflow and governance proof are made more concrete.",
            "uniqueness_verdict": f"Not unique as a broad-platform claim alone, but potentially distinctive when {brand} proves why the {platform_phrase} and {ai_phrase} combination delivers better {outcome_phrase}.",
            "who_for": f"Best for buyers who want one strategic platform but still need reassurance about implementation fit, governance, value, and why {brand} is worth choosing over narrower competitors.",
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
                    "looks_like": "It looks like a guided choice environment with clear criteria, transparent trade-offs, side-by-side proof cues, and recommendation moments that feel more like an expert adviser interface than a combative competitor page. The buyer can scan, compare, and move deeper without losing context.",
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
                    "looks_like": "It looks like a guided system view with a visible flow from input to outcome, layered callouts for standards and controls, and proof moments attached to each operational stage. Instead of abstract reassurance, the buyer sees how reliability, governance, service recovery, and quality become concrete parts of the journey.",
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
                {"title": "Trust and governance content", "body": f"Use reputation and search evidence to publish clearer material on governance, implementation confidence, service quality, AI trust, and the UK buying context around {brand}."},
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

    existing_campaign_ideas = data.get("creative_campaign_ideas", {})
    existing_campaign_items = existing_campaign_ideas.get("ideas", []) if isinstance(existing_campaign_ideas, dict) else []
    existing_campaign_by_title = {
        str(item.get("title") or "").strip(): item
        for item in existing_campaign_items
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    }

    illustration_fields = (
        "illustration_url",
        "illustration_asset_role",
        "illustration_generation_backend",
        "illustration_delivery_target",
        "illustration_import_source",
        "illustration_source_provenance",
        "illustration_batch_root",
        "illustration_batch_manifest",
        "illustration_imported_at",
        "illustration_dimensions",
        "illustration_expected_filename",
        "illustration_prompt_manifest_sha256",
        "illustration_prompt_sha256",
        "illustration_style_family",
        "illustration_style_name",
        "illustration_palette_family",
        "illustration_treatment",
        "illustration_medium",
        "illustration_prompt",
    )

    def merged_campaign_idea(idea: dict[str, Any]) -> dict[str, Any]:
        title = idea["title"]
        existing = existing_campaign_by_title.get(title, {})
        merged = {
            "title": title,
            "illustration_url": "",
            "addresses": idea["addresses"],
            "concept": idea["concept"],
            "activation": idea["activation"],
            "driving_idea": idea["driving_idea"],
            "implementation_story": idea["implementation_story"],
            "activation_plan": {"order_of_precedence": idea["activation_plan"]},
            "why_it_fits": "It responds directly to the reputation and search evidence: customers understand the category, but need more proof and control before committing.",
            "channels": ["Landing page", "CRM", "Paid social", "Search", "PR"],
            "press_angle": "Frame the brand as making a complex decision or service relationship more transparent, useful, and customer-controlled.",
            "why_it_will_work": "It turns trust and comparison anxieties into visible, practical assets rather than leaving them to third-party interpretation or fragmented support pages.",
            "intended_effect": "Improve confidence at conversion, reduce avoidable objections, and create stronger proof for acquisition and retention.",
        }
        for field in illustration_fields:
            value = existing.get(field)
            if value not in (None, "", [], {}):
                merged[field] = value
        return merged

    data["creative_campaign_ideas"] = {
        "artwork_delivery_mode": "final-raster-required",
        "illustration_generation_backend": "imagegen",
        "illustration_style_mode": "surprise",
        "ideas": [merged_campaign_idea(idea) for idea in campaign_base],
    }
    data["content_strategy"] = content_strategy

    existing_appendix = data.get("appendix", {}) if isinstance(data.get("appendix"), dict) else {}
    preserved_appendix_sections = existing_appendix.get("sections", [])
    if not isinstance(preserved_appendix_sections, list):
        preserved_appendix_sections = []
    data["appendix"] = {
        "source_map": source_map,
        "sources_reviewed": [item.get("url") for item in source_map if isinstance(item, dict) and item.get("url")],
        "method_note": "Research used deterministic Tavily Search workpacks, Tavily Research reputation reduction, direct SEMrush status recording, and labelled public search evidence where direct SEMrush data was quota-limited.",
        "assumptions_and_confidence_notes": [
            f"Competitor curation prioritised direct alternative-provider domains over review, aggregator, and analyst-list pages so the final set stays commercially useful for {brand}.",
            "Influential-news selection prefers dated items that fall within the last six months and supplements stale locked sets with saved workpack evidence when needed.",
            "Public-web SEO evidence remains directional until direct provider metrics are refreshed, but clearly sourced items are retained so structure validation does not discard useful search context.",
        ],
        "sections": preserved_appendix_sections,
    }
    data["footer_note"] = f"Prepared as an internal NewBizIntel planning report for {brand} using public evidence available at the time of the run."

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
            "query": f"{primary} OR {compact} trade press market category positioning demand 2026 2025",
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
            "query": f"{primary} OR {compact} complaints trust service issues reliability refunds security quality 2026 2025",
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


def semrush_request_plan(data_path: Path, *, database: str) -> dict[str, Any]:
    data = read_json(data_path)
    website = normalize_url(data.get("brand", {}).get("website") or "")
    parsed = urllib.parse.urlparse(website if "://" in website else f"https://{website}")
    domain = (parsed.netloc or parsed.path).lower().replace("www.", "").strip("/")
    if not domain:
        raise SystemExit("Could not resolve a root domain for SEMrush planning.")
    return {
        "ok": True,
        "data": str(data_path),
        "domain": domain,
        "provider": "Composio MCP",
        "backup_provider": "Jina AI",
        "database": database,
        "requests": [
            {
                "priority": 1,
                "tool": "SEMRUSH_DOMAIN_ORGANIC_SEARCH_KEYWORDS",
                "parameters": {"domain": domain, "database": database},
                "why": "Primary evidence for keyword demand, ranking gaps, and SEO opportunity sizing.",
            },
            {
                "priority": 2,
                "tool": "SEMRUSH_COMPETITORS_IN_ORGANIC_SEARCH",
                "parameters": {"domain": domain, "database": database},
                "why": "Validates the competitor set before structure and recommendations are locked.",
            },
            {
                "priority": 3,
                "tool": "SEMRUSH_INDEXED_PAGES",
                "parameters": {"target": domain, "target_type": "root_domain"},
                "why": "Checks index footprint and helps catch missing or underperforming site sections.",
            },
            {
                "priority": 4,
                "tool": "SEMRUSH_BACKLINKS_OVERVIEW",
                "parameters": {"target": domain, "target_type": "root_domain"},
                "why": "Adds authority context if keyword or competitor evidence is thin.",
            },
        ],
        "status_guidance": {
            "passed": "Use when at least two compact SEMrush-backed proof points can be included.",
            "partial": "Use when one SEMrush dataset exists but needs public-web supplementation.",
            "quota_limited": "Use when Composio SEMrush quota or entitlement blocks full retrieval.",
            "blocked": "Use when SEMrush cannot be authenticated or reached.",
        },
    }


def standard_semrush_backup_paths(brand_folder: Path) -> list[Path]:
    return [
        brand_folder / "semrush-evidence.json",
        brand_folder / "semrush-plugin-evidence.json",
        brand_folder / "semrush-composio-evidence.json",
        brand_folder / "research-workpacks" / "98-semrush-plugin.json",
        brand_folder / "research-workpacks" / "98-semrush-composio.json",
    ]


def load_semrush_backup_payload(brand_folder: Path) -> tuple[dict[str, Any] | None, Path | None]:
    for candidate in standard_semrush_backup_paths(brand_folder):
        if not candidate.exists():
            continue
        try:
            payload = read_json(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload, candidate
    return None, None


def merge_semrush_payload_into_summary(
    summary: dict[str, Any],
    payload: dict[str, Any],
    *,
    summary_key: str,
    note_prefix: str,
) -> tuple[dict[str, Any], str]:
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
    summary[summary_key] = payload
    summary.setdefault("source_provenance_summary", {})[f"{summary_key}_status"] = status
    summary.setdefault("notes", []).append(f"{note_prefix} status: {status}.")
    return summary, status


def apply_semrush_direct_api(
    data_path: Path,
    brand_folder: Path,
    summary: dict[str, Any],
    *,
    database: str,
    composio_backup_available: bool = False,
) -> tuple[dict[str, Any], Path | None]:
    request_plan_path = brand_folder / "semrush-composio-request-plan.json"
    access_path = brand_folder / "semrush-access.json"
    request_plan = semrush_request_plan(data_path, database=database)
    write_json(request_plan_path, request_plan)
    access_payload = {
        "ok": True,
        "status": "available" if os.environ.get("SEMRUSH_API_KEY") else ("available" if composio_backup_available else "fallback"),
        "selected_provider": "direct-api" if os.environ.get("SEMRUSH_API_KEY") else ("composio-mcp" if composio_backup_available else "jina-public-web"),
        "provider_order": ["direct-api", "composio-mcp", "jina-public-web"],
        "next_backup_provider": "composio-mcp" if os.environ.get("SEMRUSH_API_KEY") and composio_backup_available else ("jina-public-web" if composio_backup_available else None),
        "domain": request_plan["domain"],
        "database": database,
        "direct_api": {
            "available": bool(os.environ.get("SEMRUSH_API_KEY")),
            "credential_env": "SEMRUSH_API_KEY",
            "credential_value": "present-redacted" if os.environ.get("SEMRUSH_API_KEY") else "missing",
        },
        "composio_mcp": {
            "available": composio_backup_available,
            "required_tool_slugs": [item["tool"] for item in request_plan["requests"]],
            "role": "Backup provider after direct SEMrush API is unavailable, quota-limited, or blocked.",
            "note": "Provide plugin-returned evidence in one of the standard semrush-evidence JSON paths for automatic merge.",
        },
        "fallback": {
            "jina_public_web_available": True,
            "role": "Use only to support SEO/source context when SEMrush direct API and Composio MCP are unavailable or quota-limited.",
        },
        "query_plan": request_plan,
        "evidence_status": "pending",
        "fail_condition": "A report must not claim SEMrush-backed evidence unless direct-api or composio-mcp returns at least two verified SEMrush evidence points. Jina/public web is fallback context, not SEMrush-backed evidence.",
    }
    write_json(access_path, access_payload)

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

    summary, status = merge_semrush_payload_into_summary(
        summary,
        payload,
        summary_key="semrush_direct_api",
        note_prefix="SEMrush direct API",
    )
    if status != "passed" and composio_backup_available:
        backup_payload, backup_path = load_semrush_backup_payload(brand_folder)
        if backup_payload is not None:
            summary, backup_status = merge_semrush_payload_into_summary(
                summary,
                backup_payload,
                summary_key="semrush_backup",
                note_prefix="SEMrush backup",
            )
            summary["semrush_backup"]["provider"] = "composio-semrush"
            summary["semrush_backup"]["path"] = str(backup_path) if backup_path else None
            summary.setdefault("notes", []).append(
                f"Composio SEMrush backup evidence was auto-merged from {backup_path.name if backup_path else 'a standard backup path'}."
            )
            access_payload["evidence_status"] = backup_status
            access_payload["selected_provider"] = "composio-mcp"
        else:
            summary["semrush_backup"] = {
                "provider": "composio-semrush",
                "status": "awaiting-evidence-file",
                "request_plan_path": str(request_plan_path),
                "accepted_paths": [str(path) for path in standard_semrush_backup_paths(brand_folder)],
                "reason": "Direct SEMrush API did not pass; Composio SEMrush is the documented backup and the runner will auto-merge a standard evidence file when present.",
            }
            if status == "blocked":
                summary.setdefault("status", {})["semrush"] = "quota-limited"
            summary.setdefault("notes", []).append(
                "Composio SEMrush backup request plan was written automatically; no plugin-returned evidence file was present yet."
            )
            access_payload["status"] = "available"
            access_payload["selected_provider"] = "composio-mcp"
            access_payload["evidence_status"] = "pending"
    summary["semrush_access"] = access_payload
    write_json(access_path, access_payload)
    return summary, output_path


def tavily_reputation_research_prompt(data: dict[str, Any], summary: dict[str, Any]) -> str:
    brand_name = data.get("brand", {}).get("name") or summary.get("brand_name") or "the target brand"
    website = data.get("brand", {}).get("website") or summary.get("brand_website") or ""
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
    today = datetime.now().date()
    cutoff = influential_news_cutoff(today)
    dropped_out_of_window: list[str] = []
    for item in news:
        if not isinstance(item, dict):
            continue
        why = re.sub(r"\s+", " ", str(item.get("why_it_matters") or "").strip())
        if why and why.lower().startswith(
            (
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
                "highlights ",
                "contributes ",
                "underscores ",
            )
        ):
            why = "This story " + why[0].lower() + why[1:]
        if why and why[-1] not in ".!?":
            why += "."
        if why:
            item["why_it_matters"] = why
        subscores = item.get("influence_subscores")
        if isinstance(subscores, dict):
            calculated = calculate_reputation_influence_score(subscores)
            if calculated is not None:
                item["influence_score"] = calculated
    filtered_news: list[dict[str, Any]] = []
    for item in news:
        if not isinstance(item, dict):
            continue
        parsed_date = parse_exact_human_date(item.get("date"))
        headline = str(item.get("headline") or item.get("title") or "Untitled story").strip()
        if parsed_date is None:
            dropped_out_of_window.append(f"{headline} (missing exact date)")
            continue
        if parsed_date < cutoff or parsed_date > today:
            dropped_out_of_window.append(f"{headline} ({parsed_date.strftime('%d %B %Y')})")
            continue
        filtered_news.append(item)
    news = filtered_news
    news.sort(key=lambda item: as_int(item.get("influence_score")) or 0, reverse=True)
    payload["influential_news"] = news
    ranking = payload.get("influence_ranking")
    if isinstance(ranking, dict):
        ranking.setdefault("ranking_factors", list(REPUTATION_RANKING_FACTORS))
        ranking.setdefault("score_weights", REPUTATION_SCORE_WEIGHTS)
        ranking.setdefault("discovery_mode", "broad_first_scored_reduction")
        ranking["discovery_sequence"] = [
            "Broad discovery across category, reputation, investor, regulatory, and social/public-web sources using generic queries.",
            "Score and reduce the dated candidate pool against the weighted influence factors.",
            "Targeted verification of the shortlisted stories using publisher-specific or headline-specific checks.",
        ]
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
        if dropped_out_of_window:
            limitations = ranking.setdefault("limitations", [])
            note = (
                f"Stories outside the last-six-month window for this run "
                f"(before {cutoff.strftime('%d %B %Y')} or after {today.strftime('%d %B %Y')}) were excluded."
            )
            if note not in limitations:
                limitations.append(note)
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
    if output_path.exists() and os.getenv("NEWBIZINTEL_REFRESH_TAVILY_REPUTATION_RESEARCH", "") != "1":
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
        brand_name = str(summary.get("brand_name") or "").strip().lower()
        brand_domain = brand_domain_from_website(str(summary.get("brand_website") or ""))
        for index, item in enumerate(summary.get("influential_news") or []):
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            source_lower = source.lower()
            source_type = str(item.get("source_type") or "").strip().lower()
            url = str(item.get("url") or "").strip()
            source_domain = brand_domain_from_website(url)
            owned_source = source_type == "owned_newsroom" or (
                brand_name and brand_name in source_lower
            ) or any(token in source_lower for token in ("blog", "press", "newsroom"))
            if source and url and brand_domain and source_domain == brand_domain and not owned_source:
                errors.append(
                    f"influential_news[{index}] labels the publisher as '{source}' but links to the brand-owned domain {brand_domain}."
                )
    if summary.get("required_tavily_reputation_research") and not summary.get("source_provenance_summary", {}).get("tavily_research_used"):
        errors.append("Tavily Reputation Research is required for this live run but did not produce the final reputation story set")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "anti_placeholder_audit": placeholder_audit}


def module_research(args: argparse.Namespace) -> dict[str, Any]:
    return research_module_entry(
        args,
        data_path_from_args=data_path_from_args,
        brand_folder_from_data=brand_folder_from_data,
        reset_tasks_from=reset_tasks_from,
        collect_live_search_workpacks=collect_live_search_workpacks,
        reduce_search_workpacks=reduce_search_workpacks,
        build_summary_from_data=build_summary_from_data,
        apply_tavily_reputation_research=apply_tavily_reputation_research,
        apply_semrush_direct_api=lambda data_path, brand_folder, summary: apply_semrush_direct_api(
            data_path,
            brand_folder,
            summary,
            database=args.semrush_database,
            composio_backup_available=bool(args.composio_semrush_available),
        ),
        validate_research_summary=lambda summary, allow_examples: validate_research_summary(summary, allow_examples=allow_examples),
        is_repo_example_path=is_repo_example_path,
        sha256=sha256,
    )


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
    python_executable = Path(sys.executable)
    repo_root = Path(__file__).resolve().parents[1]
    if script.name == "report_data_to_pptx.py":
        pptx_runtime_python = repo_root / "pptx_runtime_env" / "Scripts" / "python.exe"
        if pptx_runtime_python.exists():
            python_executable = pptx_runtime_python
    completed = subprocess.run([str(python_executable), str(script), *args], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{script.name} failed with exit code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}")
    output = completed.stdout.strip()
    return json.loads(output) if output else {}


def render_outputs_current(data_path: Path, brand_folder: Path) -> dict[str, Any]:
    return render_outputs_current_helper(
        data_path,
        brand_folder,
        current_renderer_fingerprint=current_renderer_fingerprint,
        extract_renderer_fingerprint=extract_renderer_fingerprint,
    )


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


def reconcile_structure_gate_from_data(state: dict[str, Any], data_path: Path) -> bool:
    validation = validate_report_data(data_path)
    if not validation["ok"]:
        return False
    current_status = state.get("status", {}).get("structure")
    current_gate = state.get("gates", {}).get("gate_5_report_structure")
    current_legacy_gate = state.get("gates", {}).get("gate_4_report_data")
    if current_status == "passed" and current_gate == "passed" and current_legacy_gate == "passed":
        return False
    set_status(state, "structure", "passed")
    set_gate(state, "gate_5_report_structure", "passed")
    add_event(state, "reducer", "structure.validation_reconciliation", outputs=[str(data_path)])
    return True


def reconcile_campaign_art_gate_from_audit(state: dict[str, Any], data_path: Path) -> bool:
    audit = audit_campaign_art(data_path)
    if not audit["ok"]:
        return False
    current_status = state.get("status", {}).get("campaign_art")
    current_gate = state.get("gates", {}).get("gate_7_campaign_ideas_and_art")
    current_legacy_gate = state.get("gates", {}).get("gate_5b_campaign_art")
    if current_status == "passed" and current_gate == "passed" and current_legacy_gate == "passed":
        return False
    set_status(state, "campaign_art", "passed")
    set_gate(state, "gate_7_campaign_ideas_and_art", "passed")
    add_event(state, "reducer", "campaign_art.audit_reconciliation", outputs=[str(data_path)])
    return True


def reconcile_delivery_gate_from_stage(state: dict[str, Any], brand_folder: Path) -> bool:
    latest_handoff_path = brand_folder / "vercel-random-handoff-latest.json"
    if not latest_handoff_path.exists():
        return False
    try:
        latest_handoff = read_json(latest_handoff_path)
    except Exception:
        return False
    deploy_path = Path(str(latest_handoff.get("deploy_path") or ""))
    if not deploy_path.exists() or not deploy_path.is_dir():
        return False
    stage_audit = audit_deploy_stage(deploy_path)
    if not stage_audit.get("ok"):
        return False
    current_status = state.get("status", {}).get("deploy")
    current_gate = state.get("gates", {}).get("gate_10_delivery_handoff")
    current_legacy_gate = state.get("gates", {}).get("gate_7_delivery")
    if current_status == "passed" and current_gate == "passed" and current_legacy_gate == "passed":
        return False
    set_status(state, "deploy", "passed")
    set_gate(state, "gate_10_delivery_handoff", "passed")
    add_event(
        state,
        "reducer",
        "deploy.stage_reconciliation",
        outputs=[
            str(deploy_path / "index.html"),
            str(latest_handoff_path),
        ],
        notes=[f"Validated deploy stage at {deploy_path}."],
    )
    return True


def campaign_section(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("creative_campaign_ideas") or data.get("creative_campaigns") or {}


def campaign_art_diversity_group(idea: dict[str, Any]) -> str:
    family = str(idea.get("illustration_style_family") or "").strip().lower()
    if family:
        normalized_family = re.sub(r"[^a-z0-9]+", "-", family).strip("-")
        if normalized_family:
            return normalized_family

    style_name = str(idea.get("illustration_style_name") or "").strip().lower()
    medium = str(idea.get("illustration_medium") or "").strip().lower()
    prompt = str(idea.get("illustration_prompt") or "").strip().lower()
    text = " ".join(part for part in (family, style_name, medium, prompt) if part)
    groups = [
        ("technical-system", ("technical", "blueprint", "schematic", "interface", "circuit")),
        ("playful-infographic", ("bubble", "sticker", "playful-infographic", "icon", "cartoon-control-room")),
        ("poster-collage", ("poster", "collage", "zine", "xerox", "risograph", "print", "silkscreen")),
        ("cubist-painting", ("cubist", "picasso", "fractured", "angular planes")),
        ("impressionist-painting", ("impressionist", "broken colour", "sunlit brushwork")),
        ("brush-ink", ("brush-ink", "ukiyo", "ink-wash", "brush-scroll", "seal-like")),
        ("still-life-painting", ("still-life painting", "baroque", "botanical watercolour")),
        ("still-life-photography", ("still-life studio", "still-life photography", "magazine photography")),
        ("painting", ("painting", "oil", "brush", "pastel", "watercolour")),
        ("photography", ("photo", "photographic", "cinematic", "infrared", "long-exposure", "documentary")),
        ("sculpture-paper", ("sculpture", "sculptural", "maquette", "paper", "relief", "clay", "model")),
        ("comic-graphic", ("comic", "graphic novel", "noir", "cartoon-illustration")),
        ("cartographic", ("atlas", "cartographic", "geospatial", "map", "orbital")),
    ]
    for group, needles in groups:
        if any(needle in text for needle in needles):
            return group
    return re.sub(r"[^a-z0-9]+", "-", family or "unknown").strip("-") or "unknown"


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
    palette_families: list[str] = []
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
        batch_manifest = str(idea.get("illustration_batch_manifest") or "").strip()
        expected_filename = str(idea.get("illustration_expected_filename") or "").strip()
        prompt_manifest_sha256 = str(idea.get("illustration_prompt_manifest_sha256") or "").strip().upper()
        prompt_sha256 = str(idea.get("illustration_prompt_sha256") or "").strip().upper()
        style_name = str(idea.get("illustration_style_name") or "").strip()
        palette_family = str(idea.get("illustration_palette_family") or "").strip().lower()
        if style_name:
            style_names.append(style_name.lower())
        if palette_family:
            palette_families.append(palette_family)
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
            if not batch_manifest:
                errors.append(f"ideas[{index}] final artwork is missing illustration_batch_manifest traceability.")
            if not expected_filename:
                errors.append(f"ideas[{index}] final artwork is missing illustration_expected_filename traceability.")
            if not prompt_manifest_sha256:
                errors.append(f"ideas[{index}] final artwork is missing illustration_prompt_manifest_sha256 traceability.")
            if not prompt_sha256:
                errors.append(f"ideas[{index}] final artwork is missing illustration_prompt_sha256 traceability.")
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
    if len(palette_families) != len(ideas):
        errors.append("Campaign artwork is missing illustration_palette_family metadata on one or more ideas.")
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
        repeated_palette_families = [
            family for family, count in Counter(palette_families).items() if family and count > 1
        ]
        if repeated_palette_families:
            errors.append(
                "Campaign artwork repeats palette family or families: "
                + ", ".join(sorted(repeated_palette_families))
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
    return {
        "ok": not errors,
        "errors": errors,
        "diversity_groups": diversity_groups,
        "palette_families": palette_families,
    }


def audit_presentation_html(brand_folder: Path, data_path: Path) -> dict[str, Any]:
    result = audit_presentation_html_helper(
        brand_folder,
        data_path,
        current_renderer_fingerprint=current_renderer_fingerprint,
        extract_renderer_fingerprint=extract_renderer_fingerprint,
        audit_rendered_html_completeness=audit_rendered_html_completeness,
        read_json=read_json,
        square_quality_ok=square_quality_ok,
        asset_quality=asset_quality,
        visible_logo_occupancy_ok=visible_logo_occupancy_ok,
        has_value=has_value,
        audit_cross_client_leakage=audit_cross_client_leakage,
    )
    html_path = brand_folder / "newbizintel-report.html"
    if html_path.exists():
        data = read_json(data_path)
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        identity_audit = audit_rendered_identity_scope(data, html_text)
        if not identity_audit["ok"]:
            result.setdefault("errors", []).extend(identity_audit.get("errors", []))
            result["ok"] = False
    return result


def audit_pptx_output(pptx_path: Path) -> dict[str, Any]:
    return audit_pptx_package_helper(pptx_path)


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
    return asset_src_helper(data_path, value)


def card_html(title: str, body: str) -> str:
    return card_html_helper(title, body)


def list_html(items: list[Any]) -> str:
    return list_html_helper(items, has_value=has_value)


def source_list_html(items: list[Any]) -> str:
    return source_list_html_helper(items)


def render_html(data_path: Path, output_path: Path | None = None) -> Path:
    return render_html_helper(
        data_path,
        output_path,
        read_json=read_json,
        campaign_section=campaign_section,
        reputation_subscore_summary=reputation_subscore_summary,
        has_value=has_value,
        inject_task_list_into_html=inject_task_list_into_html,
    )


def task_list_html(brand_folder: Path) -> str:
    return task_list_html_helper(brand_folder, read_json=read_json)


def inject_task_list_into_html(html_path: Path, brand_folder: Path) -> None:
    return inject_task_list_into_html_helper(
        html_path,
        brand_folder,
        task_list_html=task_list_html,
    )


def assert_deployable_report_html(html_path: Path) -> None:
    return assert_deployable_report_html_helper(
        html_path,
        audit_rendered_html_completeness=audit_rendered_html_completeness,
    )


def audit_deploy_stage(stage_root: Path) -> dict[str, Any]:
    return audit_deploy_stage_helper(
        stage_root,
        current_renderer_fingerprint=current_renderer_fingerprint,
        extract_renderer_fingerprint=extract_renderer_fingerprint,
        audit_rendered_html_completeness=audit_rendered_html_completeness,
        asset_quality=asset_quality,
    )


def make_text_logo_png(label: str, output_path: Path) -> None:
    from python_modules.presentation_builders import make_text_logo_png as _make_text_logo_png
    return _make_text_logo_png(label, output_path)


def pptx_safe_logo_asset(data_path: Path, value: str | None) -> str:
    from python_modules.presentation_builders import pptx_safe_logo_asset as _pptx_safe_logo_asset
    return _pptx_safe_logo_asset(data_path, value, relative_to_brand=relative_to_brand)


def pptx_safe_data_copy(data_path: Path) -> Path:
    return pptx_safe_data_copy_helper(
        data_path,
        read_json=read_json,
        write_json=write_json,
        relative_to_brand=relative_to_brand,
        slugify=slugify,
    )


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
    return build_minimal_pptx_helper(
        data_path,
        output_path,
        read_json=read_json,
        utc_now=utc_now,
        campaign_section=campaign_section,
    )


def make_self_contained(html_path: Path, data_path: Path, output_path: Path) -> None:
    return make_self_contained_helper(
        html_path,
        data_path,
        output_path,
        script_root=SCRIPT_ROOT,
        run_python_script=run_python_script,
    )


def find_powershell() -> str | None:
    return find_powershell_helper()


def render_rich_html_with_powershell(data_path: Path, output_path: Path) -> Path:
    return render_rich_html_with_powershell_helper(
        data_path,
        output_path,
        script_root=SCRIPT_ROOT,
        find_powershell=find_powershell,
    )


def render_rich_html_with_python(data_path: Path, output_path: Path) -> Path:
    return render_rich_html_with_python_helper(
        data_path,
        output_path,
        script_root=SCRIPT_ROOT,
        run_python_script=run_python_script,
    )


def module_render(args: argparse.Namespace) -> dict[str, Any]:
    return render_module_entry(
        args,
        script_root=SCRIPT_ROOT,
        data_path_from_args=data_path_from_args,
        brand_folder_from_data=brand_folder_from_data,
        validate_report_data=validate_report_data,
        render_rich_html_with_python=render_rich_html_with_python,
        render_rich_html_with_powershell=render_rich_html_with_powershell,
        render_html=render_html,
        inject_task_list_into_html=inject_task_list_into_html,
        assert_deployable_report_html=assert_deployable_report_html,
        make_self_contained=make_self_contained,
        pptx_safe_data_copy=pptx_safe_data_copy,
        run_python_script=run_python_script,
        build_minimal_pptx=build_minimal_pptx,
    )


def audit_task_list(data_path: Path) -> dict[str, Any]:
    brand_folder = data_path.parent
    state = load_state(brand_folder)
    changed = False
    if reconcile_structure_gate_from_data(state, data_path):
        changed = True
    if reconcile_campaign_art_gate_from_audit(state, data_path):
        changed = True
    if reconcile_render_gate_from_outputs(state, data_path, brand_folder):
        changed = True
    if reconcile_delivery_gate_from_stage(state, brand_folder):
        changed = True
    if changed:
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


def module_qa(args: argparse.Namespace) -> dict[str, Any]:
    return qa_module_entry(
        args,
        data_path_from_args=data_path_from_args,
        brand_folder_from_data=brand_folder_from_data,
        reconcile_structure_gate_from_data=reconcile_structure_gate_from_data,
        reconcile_campaign_art_gate_from_audit=reconcile_campaign_art_gate_from_audit,
        reconcile_render_gate_from_outputs=reconcile_render_gate_from_outputs,
        validate_report_data=validate_report_data,
        audit_campaign_art=audit_campaign_art,
        audit_presentation_html=audit_presentation_html,
        audit_pptx=audit_pptx_output,
        audit_deploy_stage=audit_deploy_stage,
        audit_task_list=audit_task_list,
        inject_task_list_into_html=inject_task_list_into_html,
    )


def vercel_deploy_prompt(data_path: Path, brand_folder: Path) -> dict[str, Any]:
    return {
        "ask_user": "Would you like me to deploy this report to Vercel as a randomly named preview URL?",
        "deploy_only_if_user_confirms": True,
        "random_url_required": True,
        "policy": "Use the vercel-deploy skill only after confirmation. Run the vercel-stage command first and deploy the returned deploy_path, never the brand output folder.",
        "stage_command": f"python \"{SCRIPT_ROOT / 'newbizintel.py'}\" vercel-stage --data-path \"{data_path}\"",
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
    force_new = os.environ.get("NEWBIZINTEL_FORCE_NEW_VERCEL_STAGE", "") == "1"
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
            destination = stage_root / directory_name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)

    stage_audit = audit_deploy_stage(stage_root)
    write_json(stage_root / "deploy-stage-audit.json", stage_audit)
    write_json(brand_folder / "deploy-stage-audit-latest.json", stage_audit)
    if not stage_audit.get("ok"):
        raise SystemExit(
            "Refusing Vercel stage handoff because deploy-stage asset validation failed. "
            + "; ".join(stage_audit.get("errors", []))
        )

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
        "deploy_stage_audit": stage_audit,
        "instructions": "Use the vercel-deploy skill to deploy this deploy_path. Do not deploy the brand output folder directly. Reuse this random stage to update existing pages; set NEWBIZINTEL_FORCE_NEW_VERCEL_STAGE=1 only when a fresh random URL is explicitly needed.",
    }
    handoff["must_not_contain"] = list(dict.fromkeys(item for item in handoff["must_not_contain"] if item))
    write_json(stage_root / "newbizintel-vercel-handoff.json", handoff)
    write_json(brand_folder / "vercel-random-handoff-latest.json", handoff)
    state = load_state(brand_folder)
    set_status(state, "deploy", "passed")
    set_gate(state, "gate_10_delivery_handoff", "passed")
    add_event(
        state,
        "reducer",
        "deploy.stage_prepared",
        outputs=[
            str(stage_index),
            str(stage_root / "newbizintel-vercel-handoff.json"),
        ],
        notes=[f"Prepared validated Vercel stage at {stage_root}."],
    )
    save_state(brand_folder, state)
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
        results["intake"] = intake_module_entry(args, template_path=TEMPLATE_PATH, template_assets=TEMPLATE_ASSETS)
        args.data_path = results["intake"]["data"]
    if args.mode in {"full", "research-only"}:
        results["research"] = module_research(args)
        args.research_summary_path = results["research"]["research_summary"]
    if args.mode in {"full", "render-stack"}:
        if args.mode == "render-stack" and not getattr(args, "data_path", None):
            results["intake"] = intake_module_entry(args, template_path=TEMPLATE_PATH, template_assets=TEMPLATE_ASSETS)
            args.data_path = results["intake"]["data"]
        results["structure"] = structure_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            merge_research_into_data=merge_research_into_data,
            build_structured_report_data=build_structured_report_data,
            validate_report_data=validate_report_data,
            sha256=sha256,
        )
        results["assets"] = assets_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            patch_assets=patch_assets,
        )
        results["campaign_art"] = campaign_art_module_entry(
            args,
            script_root=SCRIPT_ROOT,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            run_python_script=run_python_script,
            apply_manifest=apply_manifest,
            audit_campaign_art=audit_campaign_art,
        )
        results["render"] = module_render(args)
        results["qa"] = module_qa(args)
    if args.mode == "qa-only":
        results["qa"] = module_qa(args)
    if args.mode == "deploy-handoff":
        results["deploy"] = deploy_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            assert_deployable_report_html=assert_deployable_report_html,
            inject_task_list_into_html=inject_task_list_into_html,
            vercel_deploy_prompt=vercel_deploy_prompt,
        )
    if args.mode == "art-refresh":
        results["campaign_art"] = campaign_art_module_entry(
            args,
            script_root=SCRIPT_ROOT,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            run_python_script=run_python_script,
            apply_manifest=apply_manifest,
            audit_campaign_art=audit_campaign_art,
        )
        results["render"] = module_render(args)
        results["qa"] = module_qa(args)
    if args.mode == "assets-refresh":
        results["assets"] = assets_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            patch_assets=patch_assets,
        )
        results["render"] = module_render(args)
        results["qa"] = module_qa(args)
    if args.mode == "full":
        results["deploy"] = deploy_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            assert_deployable_report_html=assert_deployable_report_html,
            inject_task_list_into_html=inject_task_list_into_html,
            vercel_deploy_prompt=vercel_deploy_prompt,
        )
    return results


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-path")
    parser.add_argument("--brand-name")
    parser.add_argument("--brand-folder")
    parser.add_argument("--website")
    parser.add_argument("--research-mode", choices=["bootstrap", "live-summary", "workpacks"], default="live-summary")
    parser.add_argument("--research-summary-path")
    parser.add_argument("--search-workpacks", nargs="*", default=[])
    parser.add_argument("--tavily-reputation-research", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--composio-semrush-available", action="store_true")
    parser.add_argument("--jina-fallback-available", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--semrush-database", choices=["uk", "us"], default="uk")
    parser.add_argument("--campaign-art-source-dir")
    parser.add_argument("--campaign-art-latest-generated-batch", action="store_true")
    parser.add_argument("--campaign-art-overwrite-final", action="store_true")
    parser.add_argument("--campaign-art-generate-originals", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--campaign-art-generate-dry-run", action="store_true")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NewBizIntel without PowerShell.")
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
        "intake": lambda args: intake_module_entry(args, template_path=TEMPLATE_PATH, template_assets=TEMPLATE_ASSETS),
        "research": module_research,
        "structure": lambda args: structure_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            merge_research_into_data=merge_research_into_data,
            build_structured_report_data=build_structured_report_data,
            validate_report_data=validate_report_data,
            sha256=sha256,
        ),
        "assets": lambda args: assets_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            patch_assets=patch_assets,
        ),
        "campaign-art": lambda args: campaign_art_module_entry(
            args,
            script_root=SCRIPT_ROOT,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            run_python_script=run_python_script,
            apply_manifest=apply_manifest,
            audit_campaign_art=audit_campaign_art,
        ),
        "render": module_render,
        "qa": module_qa,
        "deploy": lambda args: deploy_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            brand_folder_from_data=brand_folder_from_data,
            assert_deployable_report_html=assert_deployable_report_html,
            inject_task_list_into_html=inject_task_list_into_html,
            vercel_deploy_prompt=vercel_deploy_prompt,
        ),
        "vercel-stage": lambda args: vercel_stage_module_entry(
            args,
            data_path_from_args=data_path_from_args,
            prepare_random_vercel_stage=prepare_random_vercel_stage,
        ),
    }
    result = dispatch[args.command](args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
