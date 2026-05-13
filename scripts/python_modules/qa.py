from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from python_modules.common import add_event, load_state, read_json, record_token_usage, save_state, set_gate, set_status, write_json


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


def audit_pptx_package(
    pptx_path: Path,
    *,
    min_slide_count: int = 6,
    min_size_kb: int = 100,
    min_rich_slide_count: int = 12,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    slide_names: list[str] = []
    media_names: list[str] = []
    application = ""
    fallback_signature_detected = False
    rich_deck_likely = False

    if not pptx_path.exists():
        return {"ok": False, "errors": [f"PPTX output is missing: {pptx_path}"], "warnings": []}

    size_kb = round(pptx_path.stat().st_size / 1024, 1)
    if pptx_path.stat().st_size < (min_size_kb * 1024):
        errors.append(f"PPTX file is smaller than expected ({size_kb} KB). Minimum: {min_size_kb} KB.")

    try:
        with zipfile.ZipFile(pptx_path) as archive:
            entry_names = archive.namelist()
            for required in ("[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"):
                if required not in entry_names:
                    errors.append(f"PPTX package is missing required entry: {required}")

            slide_names = sorted(name for name in entry_names if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            media_names = sorted(name for name in entry_names if name.startswith("ppt/media/"))

            if len(slide_names) < min_slide_count:
                errors.append(f"PPTX should contain at least {min_slide_count} slides. Current count: {len(slide_names)}")

            if not media_names:
                warnings.append("PPTX package contains no media assets; check whether logos, charts, or campaign art were dropped.")

            for slide_name in slide_names:
                entry = archive.getinfo(slide_name)
                if entry.file_size < 200:
                    errors.append(f"{slide_name} is unexpectedly small or unreadable.")

            try:
                app_xml = archive.read("docProps/app.xml").decode("utf-8", errors="ignore")
                marker = "<Application>"
                if marker in app_xml and "</Application>" in app_xml:
                    application = app_xml.split(marker, 1)[1].split("</Application>", 1)[0].strip()
            except KeyError:
                warnings.append("PPTX package is missing docProps/app.xml, so fallback-signature detection could not run.")

    except zipfile.BadZipFile:
        errors.append("PPTX package is unreadable or corrupt.")

    fallback_signature_detected = application == "NewBizIntel Python Runner"
    if fallback_signature_detected:
        errors.append("PPTX matches the fallback deck signature (`NewBizIntel Python Runner`) instead of the intended rich renderer output.")
    elif slide_names and len(slide_names) < min_rich_slide_count:
        errors.append(
            f"PPTX appears shorter than the expected rich deck ({len(slide_names)} slides found; expected at least {min_rich_slide_count})."
        )

    rich_deck_likely = not fallback_signature_detected and len(slide_names) >= min_rich_slide_count

    return {
        "ok": not errors,
        "pptx": str(pptx_path),
        "size_kb": size_kb,
        "slide_count": len(slide_names),
        "media_count": len(media_names),
        "application": application,
        "fallback_signature_detected": fallback_signature_detected,
        "rich_deck_likely": rich_deck_likely,
        "warnings": warnings,
        "errors": errors,
    }


GENERIC_STORYBRAND_PHRASES = (
    "simpler, more confident path",
    "feel reassured that the promise is credible",
    "choosing between alternatives",
    "anxiety about value, control, reliability",
    "strong promise should also be transparent",
    "clear proof points, visible controls",
    "understand the offer, compare the options fairly",
    "take the next high-intent step with confidence",
    "customers fear overclaiming",
    "clearer path to the outcome",
    "enough proof to trust the decision",
    "understand why salesforce is credible, how the offer works",
    "message drift: broad claims that sound plausible",
)

GENERIC_USP_PHRASES = (
    "clear category proposition",
    "easy to understand",
    "control, quality, and service proof",
    "choice, flexibility, and reduced decision friction",
    "the brand makes the category promise easy to understand",
    "becoming easier to compare, trust, and act on than alternatives",
)

STALE_SEO_TECHNICAL_PHRASES = (
    "no live crawl gate has passed yet",
    "technical seo remains partially evidenced here",
    "this run passed search and semrush evidence gates, but it did not include a dedicated crawl-level technical validation",
)

CONTAMINATION_TERMS = (
    "paddlepals",
    "montana",
    "movie",
    "film",
    "recipe box",
    "meal kit",
    "hellofresh",
    "gousto",
    "mindful chef",
    "simplycook",
)


def _parse_exact_human_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d %B %Y").date()
    except ValueError:
        return None


def _subtract_calendar_months(anchor: date, months: int) -> date:
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


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values() if item is not None)
    return str(value)


def _collect_storybrand_text(data: dict[str, Any]) -> str:
    storybrand = data.get("storybrand", {})
    return _flatten_text(storybrand).lower()


def _collect_usp_text(data: dict[str, Any]) -> str:
    usp = data.get("usp_ksp_review", {})
    return _flatten_text(usp).lower()


def _collect_seo_text(data: dict[str, Any]) -> str:
    seo = data.get("seo_audit", {})
    return _flatten_text(seo).lower()


def _collect_scope_tokens(data: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()

    def add_tokens(value: Any) -> None:
        for token in re.findall(r"[a-z0-9][a-z0-9\-\+\.]{2,}", _flatten_text(value).lower()):
            if token.startswith("http"):
                continue
            tokens.add(token)

    brand = data.get("brand", {})
    add_tokens(brand.get("name"))
    add_tokens(brand.get("website"))
    add_tokens(data.get("company_snapshot"))
    add_tokens(data.get("competitors"))
    add_tokens(data.get("brand_reputation", {}).get("influential_news"))
    add_tokens(data.get("seo_audit"))
    return tokens


def audit_research_quality(data_path: Path) -> dict[str, Any]:
    data = read_json(data_path)
    brand_folder = data_path.resolve().parent
    summary_path = brand_folder / "research-summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    reputation = data.get("brand_reputation", {}) if isinstance(data.get("brand_reputation"), dict) else {}
    ranking = reputation.get("influence_ranking", {}) if isinstance(reputation.get("influence_ranking"), dict) else {}
    news = reputation.get("influential_news", []) if isinstance(reputation.get("influential_news"), list) else []
    competitors = data.get("competitors", []) if isinstance(data.get("competitors"), list) else summary.get("competitors", [])
    broad_queries = ranking.get("broad_discovery_queries", []) if isinstance(ranking.get("broad_discovery_queries"), list) else []
    verification_queries = ranking.get("verification_queries", []) if isinstance(ranking.get("verification_queries"), list) else []
    candidate_pool = ranking.get("candidate_pool_summary", []) if isinstance(ranking.get("candidate_pool_summary"), list) else []
    today = datetime.now().date()
    cutoff = _subtract_calendar_months(today, 6)

    categories: dict[str, dict[str, Any]] = {}

    breadth_errors: list[str] = []
    competitor_count = len([item for item in competitors if isinstance(item, dict) and str(item.get("competitor") or item.get("name") or "").strip()])
    if competitor_count < 4:
        breadth_errors.append(f"Competitor set is too thin ({competitor_count}); expected at least 4 for a normal-category run.")
    if len([item for item in candidate_pool if str(item).strip()]) < 12:
        breadth_errors.append("Influential-news candidate pool is too thin; expected at least 12 candidates before reduction.")
    if len({str(item).strip().lower() for item in broad_queries if str(item).strip()}) < 4:
        breadth_errors.append("Broad discovery query set is too thin; expected at least 4 distinct broad queries.")
    if len({str(item).strip().lower() for item in verification_queries if str(item).strip()}) < 3:
        breadth_errors.append("Verification query set is too thin; expected at least 3 distinct verification queries.")
    if len(news) not in (5, 6):
        breadth_errors.append(f"Influential-news shortlist should contain 5 or 6 items, not {len(news)}.")
    categories["breadth"] = {"ok": not breadth_errors, "errors": breadth_errors}

    freshness_errors: list[str] = []
    for index, item in enumerate(news):
        if not isinstance(item, dict):
            freshness_errors.append(f"influential_news[{index}] is not a story object.")
            continue
        parsed = _parse_exact_human_date(item.get("date"))
        if parsed is None:
            freshness_errors.append(f"influential_news[{index}] lacks an exact date in DD Month YYYY format.")
            continue
        if parsed < cutoff:
            freshness_errors.append(
                f"influential_news[{index}] is outside the rolling six-month window ({item.get('date')} < {cutoff.strftime('%d %B %Y')})."
            )
        if parsed > today:
            freshness_errors.append(f"influential_news[{index}] is future-dated ({item.get('date')}).")
    categories["freshness"] = {
        "ok": not freshness_errors,
        "errors": freshness_errors,
        "window_start": cutoff.strftime("%d %B %Y"),
        "window_end": today.strftime("%d %B %Y"),
    }

    source_errors: list[str] = []
    publishers: set[str] = set()
    source_types: set[str] = set()
    publisher_counts: dict[str, int] = {}
    for index, item in enumerate(news):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        url = str(item.get("url") or "").strip()
        source_type = str(item.get("source_type") or "").strip()
        if not source:
            source_errors.append(f"influential_news[{index}] is missing a publisher/source name.")
        if not url:
            source_errors.append(f"influential_news[{index}] is missing a source URL.")
        if not source_type:
            source_errors.append(f"influential_news[{index}] is missing a source_type.")
        if source:
            key = source.lower()
            publishers.add(key)
            publisher_counts[key] = publisher_counts.get(key, 0) + 1
        if source_type:
            source_types.add(source_type.lower())
    if len(publishers) < 3:
        source_errors.append(f"Influential-news shortlist uses only {len(publishers)} distinct publishers; expected at least 3.")
    if len(source_types) < 3:
        source_errors.append(f"Influential-news shortlist uses only {len(source_types)} distinct source classes; expected at least 3.")
    for publisher, count in publisher_counts.items():
        if count > 2:
            source_errors.append(f"Publisher '{publisher}' appears {count} times in the final shortlist; expected no more than 2.")
    categories["source_quality"] = {"ok": not source_errors, "errors": source_errors}

    specificity_errors: list[str] = []
    storybrand_text = _collect_storybrand_text(data)
    usp_text = _collect_usp_text(data)
    seo_text = _collect_seo_text(data)
    if not storybrand_text.strip():
        specificity_errors.append("StoryBrand content is missing.")
    generic_hits = [phrase for phrase in GENERIC_STORYBRAND_PHRASES if phrase in storybrand_text]
    if generic_hits:
        specificity_errors.append(f"StoryBrand content contains generic canned phrasing: {', '.join(generic_hits)}.")
    brand_name = str((data.get("brand") or {}).get("name") or "").strip().lower()
    if brand_name and brand_name not in storybrand_text:
        specificity_errors.append("StoryBrand content does not mention the target brand explicitly.")
    overlap_tokens = _collect_scope_tokens(data)
    storybrand_tokens = {token for token in re.findall(r"[a-z0-9][a-z0-9\-\+\.]{2,}", storybrand_text) if not token.startswith("http")}
    meaningful_overlap = sorted(token for token in storybrand_tokens if token in overlap_tokens)
    if len(meaningful_overlap) < 8:
        specificity_errors.append(
            f"StoryBrand content has weak overlap with current run evidence ({len(meaningful_overlap)} shared scope tokens; expected at least 8)."
        )
    generic_usp_hits = [phrase for phrase in GENERIC_USP_PHRASES if phrase in usp_text]
    if generic_usp_hits:
        specificity_errors.append(f"USP/KSP content contains generic canned phrasing: {', '.join(generic_usp_hits)}.")
    usp_tokens = {token for token in re.findall(r"[a-z0-9][a-z0-9\-\+\.]{2,}", usp_text) if not token.startswith("http")}
    usp_overlap = sorted(token for token in usp_tokens if token in overlap_tokens)
    if len(usp_overlap) < 8:
        specificity_errors.append(
            f"USP/KSP content has weak overlap with current run evidence ({len(usp_overlap)} shared scope tokens; expected at least 8)."
        )
    stale_seo_hits = [phrase for phrase in STALE_SEO_TECHNICAL_PHRASES if phrase in seo_text]
    semrush_evidence = ((data.get("seo_audit") or {}).get("semrush_evidence") or []) if isinstance(data.get("seo_audit"), dict) else []
    search_evidence = ((data.get("seo_audit") or {}).get("search_evidence") or []) if isinstance(data.get("seo_audit"), dict) else []
    if stale_seo_hits and (len(semrush_evidence) >= 1 or len(search_evidence) >= 2):
        specificity_errors.append(
            "SEO technical findings still use stale crawl-gate wording despite passed search/provider evidence."
        )
    categories["anti_generic_specificity"] = {
        "ok": not specificity_errors,
        "errors": specificity_errors,
        "overlap_token_count": len(meaningful_overlap),
        "usp_overlap_token_count": len(usp_overlap),
    }

    contamination_errors: list[str] = []
    haystack = json.dumps(data, ensure_ascii=False).lower()
    hits = [term for term in CONTAMINATION_TERMS if term in haystack]
    if hits:
        contamination_errors.append(f"Detected contamination/noise terms in final report data: {', '.join(sorted(set(hits)))}.")
    appendix = data.get("appendix", {}) if isinstance(data.get("appendix"), dict) else {}
    appendix_blob = _flatten_text(appendix).lower()
    for disallowed in ("site:", "view this week's recipes"):
        if disallowed in appendix_blob:
            contamination_errors.append(f"Appendix/source layer still contains suspicious discovery residue: {disallowed}.")
    categories["contamination_protection"] = {"ok": not contamination_errors, "errors": contamination_errors}

    errors = [f"{name}: {error}" for name, result in categories.items() for error in result.get("errors", [])]
    return {
        "ok": not errors,
        "categories": categories,
        "errors": errors,
        "summary_path": str(summary_path) if summary_path.exists() else None,
    }


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
    audit_pptx: Callable[[Path], dict[str, Any]],
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
    add_event(state, "fanout", "qa.initial_audits", jobs=["report-data", "task-list", "hybrid", "logos", "campaign-art", "outputs", "pptx"])
    save_state(brand_folder, state)
    latest_stage_audit: dict[str, Any] = {"ok": True, "warnings": ["Deploy stage has not been prepared yet."], "errors": []}
    latest_handoff_path = brand_folder / "vercel-random-handoff-latest.json"
    if latest_handoff_path.exists():
        try:
            latest_handoff = read_json(latest_handoff_path)
            deploy_path = Path(str(latest_handoff.get("deploy_path") or ""))
            if deploy_path.exists() and deploy_path.is_dir():
                latest_stage_audit = audit_deploy_stage(deploy_path)
                if latest_stage_audit.get("ok"):
                    set_status(state, "deploy", "passed")
                    set_gate(state, "gate_10_delivery_handoff", "passed")
            else:
                latest_stage_audit = {"ok": False, "errors": [f"Latest Vercel stage path is missing: {deploy_path}"], "warnings": []}
        except Exception as exc:
            latest_stage_audit = {"ok": False, "errors": [f"Could not audit latest Vercel stage: {exc}"], "warnings": []}
    checks = {
        "report_data": validate_report_data(data_path),
        "research_quality": audit_research_quality(data_path),
        "hybrid": audit_hybrid(state),
        "campaign_art": audit_campaign_art(data_path),
        "required_logos": read_json(brand_folder / "required-logo-manifest.json") if (brand_folder / "required-logo-manifest.json").exists() else {"ok": False, "errors": ["required-logo-manifest.json missing"]},
        "source_badges": read_json(brand_folder / "source-badge-manifest.json") if (brand_folder / "source-badge-manifest.json").exists() else {"ok": False, "errors": ["source-badge-manifest.json missing"]},
        "presentation_html": audit_presentation_html(brand_folder, data_path),
        "pptx": audit_pptx(brand_folder / "newbizintel-report.pptx"),
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
    record_token_usage(
        state,
        "qa.bundle_review",
        None,
        provider="local-python",
        model="deterministic",
        status="deterministic",
        note="Current QA bundle checks are deterministic local audits over canonical outputs.",
    )
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
