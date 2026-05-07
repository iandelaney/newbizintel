from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def current_renderer_fingerprint(*, rich_render_script: Path, rich_render_template: Path) -> str:
    digest = hashlib.sha256()
    for label, path in (
        ("render_report.py", rich_render_script),
        ("report-template.html", rich_render_template),
    ):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def extract_renderer_fingerprint(rendered_html: str, *, renderer_fingerprint_prefix: str) -> str:
    match = re.search(
        rf"{re.escape(renderer_fingerprint_prefix)}\s+([0-9a-fA-F]{{16,64}})",
        rendered_html,
    )
    return (match.group(1) if match else "").lower()


def audit_rendered_html_completeness(
    html_text: str,
    *,
    placeholder_markers: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    errors: list[str] = []
    sanitized_html = re.sub(
        r"data:[^\"']+;base64,[A-Za-z0-9+/=]+",
        "data:image/embedded",
        html_text,
        flags=re.I,
    )
    patterns = {
        "empty unordered list": r"<ul(?:\s[^>]*)?>\s*</ul>",
        "empty ordered list": r"<ol(?:\s[^>]*)?>\s*</ol>",
        "empty table cell": r"<t[dh](?:\s[^>]*)?>\s*</t[dh]>",
        "empty article": r"<article(?:\s[^>]*)?>\s*</article>",
        "empty card": r"<div class=\"card\">\s*(?:<strong>\s*</strong>)?\s*</div>",
        "empty table body": r"<tbody(?:\s[^>]*)?>\s*</tbody>",
    }
    for label, pattern in patterns.items():
        count = len(re.findall(pattern, sanitized_html, flags=re.I | re.S))
        if count:
            errors.append(f"Rendered HTML contains {count} {label} element(s).")
    for marker, reason in placeholder_markers:
        if marker.lower() == "replace with":
            count = len(re.findall(re.escape(marker), sanitized_html, flags=re.I))
        else:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9]){re.escape(marker)}(?![A-Za-z0-9])",
                re.I,
            )
            count = len(pattern.findall(sanitized_html))
        if count:
            errors.append(f"Rendered HTML contains {count} {reason} marker(s): {marker}.")
    leaked_object_patterns = {
        "PowerShell object literal": r"@\{[^}]+}",
        "PowerShell type name": r"System\.Management\.Automation\.(?:PSCustomObject|PSObject)",
        "JavaScript object placeholder": r"\[object Object\]",
        "Python dict/list literal": r"(?:\[\s*)?\{(?:&#x27;|&quot;|'|\")\w+(?:&#x27;|&quot;|'|\")\s*:",
    }
    for label, pattern in leaked_object_patterns.items():
        count = len(re.findall(pattern, sanitized_html, flags=re.I | re.S))
        if count:
            errors.append(
                f"Rendered HTML contains {count} leaked {label} string(s), usually caused by rendering structured data as raw text."
            )
    malformed_patterns = {
        "idea activation example list missing list-item close before next item": r'<div class="idea-activation-plan__examples">.*?</div>\s*<li\b',
        "idea activation example list missing list-item close before list end": r'<div class="idea-activation-plan__examples">.*?</div>\s*</ul>',
    }
    for label, pattern in malformed_patterns.items():
        count = len(re.findall(pattern, sanitized_html, flags=re.I | re.S))
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
            parent_tail = html_text[match.end() :]
            parent_end_candidates = [
                pos
                for pos in (
                    parent_tail.lower().find("<h2"),
                    parent_tail.lower().find('<div class="section-return"'),
                    parent_tail.lower().find("</main>"),
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


def render_outputs_current(
    data_path: Path,
    brand_folder: Path,
    *,
    current_renderer_fingerprint: Any,
    extract_renderer_fingerprint: Any,
) -> dict[str, Any]:
    html_path = brand_folder / "newbizintel-report.html"
    portable_html = brand_folder / "archive" / "newbizintel-report-portable.html"
    pptx_path = brand_folder / "newbizintel-report.pptx"
    outputs = [html_path, portable_html, pptx_path]
    errors: list[str] = []
    expected_fingerprint = current_renderer_fingerprint()
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
        for html_candidate in (html_path, portable_html):
            if not html_candidate.exists():
                continue
            rendered_text = html_candidate.read_text(encoding="utf-8", errors="ignore")
            embedded_fingerprint = extract_renderer_fingerprint(rendered_text)
            if not embedded_fingerprint:
                errors.append(f"{html_candidate.name} is missing the renderer fingerprint and must be rebuilt.")
            elif embedded_fingerprint != expected_fingerprint:
                errors.append(
                    f"{html_candidate.name} was rendered by an older renderer/template build "
                    f"({embedded_fingerprint} != {expected_fingerprint})."
                )
    return {
        "ok": not errors,
        "errors": errors,
        "outputs": [str(path) for path in outputs],
        "expected_renderer_fingerprint": expected_fingerprint,
    }


def audit_presentation_html(
    brand_folder: Path,
    data_path: Path,
    *,
    current_renderer_fingerprint: Any,
    extract_renderer_fingerprint: Any,
    audit_rendered_html_completeness: Any,
    read_json: Any,
    square_quality_ok: Any,
    asset_quality: Any,
    visible_logo_occupancy_ok: Any,
    has_value: Any,
    audit_cross_client_leakage: Any,
) -> dict[str, Any]:
    html_path = brand_folder / "newbizintel-report.html"
    errors: list[str] = []
    warnings: list[str] = []
    if not html_path.exists():
        return {"ok": False, "errors": [f"HTML report missing: {html_path}"], "warnings": warnings}

    size = html_path.stat().st_size
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    expected_fingerprint = current_renderer_fingerprint()
    embedded_fingerprint = extract_renderer_fingerprint(text)
    if not embedded_fingerprint:
        errors.append("Rendered HTML is missing the current renderer fingerprint and must be rebuilt.")
    elif embedded_fingerprint != expected_fingerprint:
        errors.append(
            "Rendered HTML was produced by an older renderer/template build "
            f"({embedded_fingerprint} != {expected_fingerprint})."
        )
    completeness_audit = audit_rendered_html_completeness(text)
    if not completeness_audit["ok"]:
        errors.extend(completeness_audit.get("errors", []))
    if size < 100_000:
        errors.append(f"HTML report is too small for the rich presentation layer ({size} bytes).")
    data = read_json(data_path)
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
    if "Generated by newbizintel modular runner" in text or missing_rich_markers:
        errors.append("HTML report was produced by the skeletal Python fallback renderer.")
    if re.search(r'class="[^"]*competitor-badge--fallback', text):
        errors.append("Competitor logos fell back to initials in rendered HTML.")
    if re.search(r'<div class="publisher-badge"><span>', text):
        errors.append("News/source logos fell back to text badges in rendered HTML.")
    if re.search(r'<span class="publisher-badge[^"]*">\s*<img[^>]+src="https?://[^"]*favicon', text, flags=re.I):
        errors.append("News/source logos are still using remote favicon URLs in rendered HTML.")
    if re.search(r'class="[^"]*brand-logo-slot--fallback', text):
        errors.append("Brand logo fell back to initials in rendered HTML.")
    if not re.search(r'<link[^>]+rel="icon"[^>]+href="(?:assets|slide-assets)/', text, flags=re.I):
        errors.append("Rendered HTML is missing a local favicon link.")
    if "Department Opportunity Map" in text:
        errors.append("Department Opportunity Map is redundant and must not be rendered.")
    usp = data.get("usp_ksp_review", {})
    if isinstance(usp, dict):
        usp_rows = usp.get("rows", [])
        if isinstance(usp_rows, list) and len(usp_rows) >= 3:
            rendered_claims = 0
            for row in usp_rows:
                if not isinstance(row, dict):
                    continue
                claim_type = str(row.get("claim_type") or "").strip()
                proof_feedback = str(row.get("proof_feedback") or "").strip()
                if claim_type and claim_type in text:
                    rendered_claims += 1
                elif proof_feedback and proof_feedback in text:
                    rendered_claims += 1
            if rendered_claims < 3:
                errors.append("USP/KSP rendered section is incomplete: structured claim/proof rows were not rendered into the HTML presentation.")
        verdict = usp.get("overall_verdict", {})
        if isinstance(verdict, dict) and has_value(verdict.get("headline")) and str(verdict.get("headline")) not in text:
            errors.append("USP/KSP rendered section is incomplete: overall verdict is missing from the HTML presentation.")
    signal_start = text.find("Department Opportunity Signals")
    signal_end = text.find("Most Likely Workstreams", signal_start)
    signal_section = text[signal_start:signal_end] if signal_start >= 0 and signal_end > signal_start else ""
    if signal_section and re.search(r"(?:Value:|<span class=\"opportunity-chip)", signal_section, flags=re.I):
        errors.append("Department Opportunity Signals cards must describe target-brand opportunities, not value labels or lead/status chips.")

    leakage_audit = audit_cross_client_leakage(
        {"report_data": data, "rendered_html": text},
        root_label="presentation_html",
    )
    if not leakage_audit["ok"]:
        errors.extend(leakage_audit.get("errors", []))
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
        for value in (
            row.get("logo_url"),
            row.get("competitor_logo_url"),
            row.get("badge_url"),
            row.get("mark_url"),
        ):
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

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "html": str(html_path),
        "bytes": size,
        "image_count": image_count,
    }


def task_list_html(brand_folder: Path, *, read_json: Any) -> str:
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
        "<section id=\"newbizintel-workflow-task-list\" class=\"newbizintel-task-list\">"
        "<h2>Workflow Task List</h2>"
        f"<p class=\"score\">Passed: {html.escape(str(payload.get('passed', 0)))}/{html.escape(str(payload.get('total', 10)))}</p>"
        f"<p class=\"note\">Updated: {html.escape(str(payload.get('updated_at', 'not recorded')))}</p>"
        "<table><thead><tr><th>#</th><th>Step</th><th>Status</th><th>Primary gate</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</section>"
    )


def inject_task_list_into_html(
    html_path: Path,
    brand_folder: Path,
    *,
    task_list_html: Any,
) -> None:
    if not html_path.exists():
        return
    section = task_list_html(brand_folder)
    if not section:
        return
    text = html_path.read_text(encoding="utf-8")
    pattern = re.compile(r"<section id=\"newbizintel-workflow-task-list\".*?</section>", re.S)
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


def assert_deployable_report_html(
    html_path: Path,
    *,
    audit_rendered_html_completeness: Any,
) -> None:
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
            "Refusing deployment handoff because the HTML does not look like a complete NewBizIntel report. "
            f"Path: {html_path}; bytes: {len(text)}; missing markers: {', '.join(missing) or 'none'}"
        )


def audit_deploy_stage(
    stage_root: Path,
    *,
    current_renderer_fingerprint: Any,
    extract_renderer_fingerprint: Any,
    audit_rendered_html_completeness: Any,
    asset_quality: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    stage_index = stage_root / "index.html"
    if not stage_index.exists():
        return {
            "ok": False,
            "errors": [f"Deploy stage is missing index.html: {stage_index}"],
            "warnings": warnings,
            "stage_root": str(stage_root),
            "asset_count": 0,
            "checked_assets": [],
        }

    text = stage_index.read_text(encoding="utf-8", errors="ignore")
    expected_fingerprint = current_renderer_fingerprint()
    embedded_fingerprint = extract_renderer_fingerprint(text)
    if not embedded_fingerprint:
        errors.append("Deploy stage HTML is missing the current renderer fingerprint.")
    elif embedded_fingerprint != expected_fingerprint:
        errors.append(
            "Deploy stage HTML was produced by an older renderer/template build "
            f"({embedded_fingerprint} != {expected_fingerprint})."
        )
    completeness = audit_rendered_html_completeness(text)
    if not completeness["ok"]:
        errors.extend(f"stage_html: {error}" for error in completeness.get("errors", []))

    required_markers = (
        "Competitor positioning in search",
        "Keyword opportunity groups",
        "brand-logo-slot",
        "competitor-badge",
        "publisher-badge",
        'rel="icon"',
    )
    for marker in required_markers:
        if marker not in text:
            errors.append(f"Deploy stage HTML is missing required marker: {marker}")

    if re.search(r'class="[^"]*brand-logo-slot--fallback', text):
        errors.append("Deploy stage HTML fell back to initials for the main brand logo.")
    if re.search(r'class="[^"]*competitor-badge--fallback', text):
        errors.append("Deploy stage HTML fell back to initials for one or more competitor logos.")
    if "publisher-badge--missing" in text or re.search(r'<div class="publisher-badge"><span>', text):
        errors.append("Deploy stage HTML fell back to missing/text publisher badges.")
    if re.search(r'<span class="publisher-badge[^"]*">\s*<img[^>]+src="https?://[^"]*favicon', text, flags=re.I):
        errors.append("Deploy stage HTML is still using remote favicon URLs for publisher badges.")
    if not re.search(r'<link[^>]+rel="icon"[^>]+href="(?:assets|slide-assets)/', text, flags=re.I):
        errors.append("Deploy stage HTML is missing a local favicon link.")

    asset_paths = sorted(
        {
            match
            for match in re.findall(r'(?:src|href)=["\']((?:slide-assets|assets)/[^"\']+)["\']', text, flags=re.I)
            if not match.lower().startswith(("http://", "https://", "data:"))
        }
    )
    checked_assets: list[str] = []
    missing_assets: list[str] = []
    invalid_assets: list[str] = []
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
    for rel_path in asset_paths:
        asset_path = stage_root / rel_path.replace("/", os.sep)
        checked_assets.append(rel_path)
        if not asset_path.exists() or not asset_path.is_file():
            missing_assets.append(rel_path)
            continue
        try:
            size = asset_path.stat().st_size
        except OSError:
            invalid_assets.append(f"{rel_path}: unreadable")
            continue
        if size <= 0:
            invalid_assets.append(f"{rel_path}: empty file")
            continue
        if asset_path.suffix.lower() in image_exts:
            quality = asset_quality(asset_path)
            if not quality.get("exists"):
                invalid_assets.append(f"{rel_path}: asset_quality could not read file")
                continue
            if asset_path.suffix.lower() != ".svg" and quality.get("width") and quality.get("height"):
                if quality["width"] < 16 or quality["height"] < 16:
                    invalid_assets.append(
                        f"{rel_path}: image too small ({quality['width']}x{quality['height']})"
                    )

    if missing_assets:
        errors.append(f"Deploy stage is missing referenced assets: {missing_assets}")
    if invalid_assets:
        errors.append(f"Deploy stage has invalid referenced assets: {invalid_assets}")
    if not asset_paths:
        errors.append("Deploy stage HTML does not reference any local slide-assets or assets files.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stage_root": str(stage_root),
        "asset_count": len(asset_paths),
        "checked_assets": checked_assets,
        "missing_assets": missing_assets,
        "invalid_assets": invalid_assets,
    }


def make_self_contained(
    html_path: Path,
    data_path: Path,
    output_path: Path,
    *,
    script_root: Path,
    run_python_script: Any,
) -> None:
    script = script_root / "render" / "make_html_self_contained.py"
    run_python_script(script, ["--html", str(html_path), "--data", str(data_path), "--output", str(output_path)])


def find_powershell() -> str | None:
    explicit = os.environ.get("NEWBIZINTEL_PWSH")
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


def render_rich_html_with_powershell(
    data_path: Path,
    output_path: Path,
    *,
    script_root: Path,
    find_powershell: Any,
) -> Path:
    pwsh = find_powershell()
    if not pwsh:
        raise RuntimeError(
            "Rich HTML renderer requires PowerShell until the presentation renderer is fully ported to Python."
        )
    script = script_root / "render" / "render_report.ps1"
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


def render_rich_html_with_python(
    data_path: Path,
    output_path: Path,
    *,
    script_root: Path,
    run_python_script: Any,
) -> Path:
    script = script_root / "render" / "render_report.py"
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
