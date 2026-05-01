#!/usr/bin/env python3
import argparse
import html
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


def parse_args():
    parser = argparse.ArgumentParser(description="Render the NewBiz2 rich HTML report without PowerShell.")
    parser.add_argument("--data", "--data-path", dest="data_path", required=True)
    parser.add_argument("--template", "--template-path", dest="template_path")
    parser.add_argument("--output", "--output-path", dest="output_path")
    parser.add_argument("--skip-validation", action="store_true")
    return parser.parse_args()


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def esc(value: Any) -> str:
    return html.escape(text(value), quote=True).replace("&#x27;", "'")


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def safe_href(value: Any, allow_fragment: bool = False) -> str:
    raw = text(value)
    if not raw:
        return ""
    if allow_fragment and raw.startswith("#"):
        return raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    return ""


def compact_url_label(value: Any) -> str:
    href = safe_href(value)
    if not href:
        return text(value)
    parsed = urllib.parse.urlparse(href)
    host = parsed.netloc.replace("www.", "")
    path = parsed.path.rstrip("/")
    if path and path != "/":
        return f"{host}{path}"
    return host


def asset_src(data_dir: Path, value: Any) -> str:
    raw = text(value)
    if not raw:
        return ""
    if safe_href(raw) or raw.startswith("data:"):
        return raw
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = data_dir / raw
    if candidate.exists():
        try:
            return candidate.resolve().relative_to(data_dir.resolve()).as_posix()
        except ValueError:
            return candidate.resolve().as_uri()
    return ""


def rich(value: Any) -> str:
    raw = esc(value)
    if not raw:
        return ""
    allowed = (
        (r"&lt;(\/)?(p|strong|em|b|i|ul|ol|li)&gt;", r"<\1\2>"),
        (r"&lt;br\s*/?&gt;", "<br>"),
    )
    for pattern, replacement in allowed:
        raw = re.sub(pattern, replacement, raw, flags=re.I)
    if raw.startswith("<p") or raw.startswith("<ul") or raw.startswith("<ol"):
        return raw
    return f"<p>{raw}</p>"


def list_html(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    rows: list[str] = []
    for item in items:
        if not has_value(item):
            continue
        if isinstance(item, dict):
            title = item.get("title") or item.get("label") or item.get("name") or item.get("platform") or ""
            body = item.get("body") or item.get("value") or item.get("summary") or item.get("signal") or ""
            detail_parts = []
            for label, key in [("Tone", "tone"), ("Signal", "signal"), ("Implication", "implication")]:
                value = item.get(key)
                if has_value(value) and value != body:
                    detail_parts.append(f"<strong>{esc(label)}</strong> {esc(value)}")
            detail = "; ".join(detail_parts)
            if has_value(title) and (has_value(body) or has_value(detail)):
                separator = ": " if has_value(body) else " "
                extra = f" {detail}" if detail else ""
                rows.append(f"<li><strong>{esc(title)}</strong>{separator}{rich(body) if has_value(body) else ''}{extra}</li>")
            elif has_value(title) or has_value(body):
                rows.append(f"<li>{rich(body or title)}</li>")
        else:
            rows.append(f"<li>{rich(item) if isinstance(item, str) and '<' in item else esc(item)}</li>")
    return f"<ul>{''.join(rows)}</ul>" if rows else ""


def pill_html(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    rows: list[str] = []
    for item in items:
        if not has_value(item):
            continue
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or item.get("name") or item.get("value") or ""
            tone = text(item.get("tone") or "")
            tone_class = f" {esc(tone)}" if tone else ""
            if has_value(label):
                rows.append(f'<span class="pill{tone_class}">{esc(label)}</span>')
        else:
            rows.append(f'<span class="pill">{esc(item)}</span>')
    return "".join(rows)


SECTION_ICONS = {
    "Company Snapshot": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M9 20V9"></path><path d="M15 20V13"></path><path d="M4 10H20"></path></svg>',
    "Executive Summary": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3L13.9 8.1L19 10L13.9 11.9L12 17L10.1 11.9L5 10L10.1 8.1Z"></path><path d="M19 3V7"></path><path d="M21 5H17"></path></svg>',
    "Archetype Opportunity Assessment": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"></circle><circle cx="12" cy="12" r="3"></circle><path d="M12 2V5"></path><path d="M12 19V22"></path><path d="M2 12H5"></path><path d="M19 12H22"></path></svg>',
    "Messaging Assessment": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19H19"></path><path d="M7 16C10 16 12.5 13.5 12.5 10.5C12.5 8.3 11 6.5 9 5.8"></path><path d="M14 5L18 9"></path><path d="M18 5L14 9"></path></svg>',
    "USP and KSP Review": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3L14.7 8.5L20.8 9.3L16.4 13.5L17.5 19.5L12 16.5L6.5 19.5L7.6 13.5L3.2 9.3L9.3 8.5Z"></path></svg>',
    "Competitive Landscape": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 18H17"></path><path d="M8 18V8L12 5L16 8V18"></path><path d="M9 8H15"></path></svg>',
    "SEO Audit": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"></circle><path d="M20 20L15.5 15.5"></path></svg>',
    "Brand Reputation Snapshot": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 12L10 15L17 8"></path><circle cx="12" cy="12" r="9"></circle></svg>',
    "Opportunities": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5"></path><path d="M6 11L12 5L18 11"></path><path d="M5 19H19"></path></svg>',
    "Creative Campaign Ideas": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18H15"></path><path d="M10 22H14"></path><path d="M12 2C8.7 2 6 4.7 6 8C6 10.1 7 11.9 8.5 13.1C9.5 13.9 10 15 10 16H14C14 15 14.5 13.9 15.5 13.1C17 11.9 18 10.1 18 8C18 4.7 15.3 2 12 2Z"></path></svg>',
    "Content Strategy Recommendations": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4H17"></path><path d="M7 9H17"></path><path d="M7 14H13"></path><rect x="5" y="2" width="14" height="20" rx="2"></rect></svg>',
    "Appendix": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7H16"></path><path d="M8 11H16"></path><path d="M8 15H13"></path><rect x="6" y="3" width="12" height="18" rx="2"></rect></svg>',
    "Finance and Scale": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19H20"></path><path d="M7 16V10"></path><path d="M12 16V6"></path><path d="M17 16V12"></path></svg>',
    "Leadership": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="9" r="3"></circle><circle cx="17" cy="10" r="2.5"></circle><path d="M4.5 19C5.3 16.4 7.3 15 9.8 15C12.3 15 14.3 16.4 15.1 19"></path><path d="M15.5 18C16.1 16.4 17.4 15.4 19 15"></path></svg>',
    "Founders": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 20V4"></path><path d="M6 5H16L14 9L16 13H6"></path></svg>',
    "Ownership and Funding": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 12H17"></path><path d="M12 7V17"></path><circle cx="12" cy="12" r="8"></circle></svg>',
    "Snapshot Sources": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13A4 4 0 0 1 10 7L12 5A4 4 0 0 1 18 11L17 12"></path><path d="M14 11A4 4 0 0 1 14 17L12 19A4 4 0 0 1 6 13L7 12"></path></svg>',
    "Department Opportunity Signals": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 6H17"></path><path d="M7 12H14"></path><path d="M7 18H12"></path><circle cx="18" cy="18" r="2"></circle></svg>',
    "Most Likely Workstreams": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="6" height="6" rx="1"></rect><rect x="14" y="5" width="6" height="6" rx="1"></rect><rect x="9" y="13" width="6" height="6" rx="1"></rect><path d="M10 8H14"></path><path d="M12 11V13"></path></svg>',
    "Why Archetype Is Well Matched": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21S5 17.2 5 11A4 4 0 0 1 12 8A4 4 0 0 1 19 11C19 17.2 12 21 12 21Z"></path></svg>',
    "Recommended One-Liner": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7H19"></path><path d="M5 12H15"></path><path d="M5 17H12"></path></svg>',
    "Biggest Messaging Fixes": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20L10 14"></path><path d="M14 10L20 4"></path><path d="M13 4H20V11"></path><path d="M4 13V20H11"></path></svg>',
    "Content Implications of the Messaging Findings": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4H14L18 8V20H6Z"></path><path d="M14 4V8H18"></path><path d="M9 12H15"></path><path d="M9 16H15"></path></svg>',
    "Why Each Competitor Matters": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 16L4 12L8 8"></path><path d="M16 8L20 12L16 16"></path><path d="M14 5L10 19"></path></svg>',
    "Messaging Patterns Across the Market": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8H19"></path><path d="M5 12H16"></path><path d="M5 16H13"></path></svg>',
    "Content Patterns Across the Market": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="4" width="14" height="16" rx="2"></rect><path d="M8 9H16"></path><path d="M8 13H16"></path></svg>',
    "Areas Where the Brand Is Behind, Matched, or Ahead": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17L12 12L17 7"></path><path d="M7 7H17V17"></path></svg>',
    "Priority Issues with Evidence, Reason, and Recommended Fix": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 9V13"></path><path d="M12 17H12.01"></path><path d="M10.3 3.8L2.8 17A2 2 0 0 0 4.5 20H19.5A2 2 0 0 0 21.2 17L13.7 3.8A2 2 0 0 0 10.3 3.8Z"></path></svg>',
    "Content Implications of the SEO Findings": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4H17"></path><path d="M7 9H17"></path><path d="M7 14H13"></path><path d="M17 14L19 16L17 18"></path></svg>',
    "Platform-Level Readout": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7H20"></path><path d="M4 12H20"></path><path d="M4 17H14"></path></svg>',
    "Most Influential News Stories in the Last Six Months": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="M8 9H16"></path><path d="M8 13H16"></path><path d="M8 17H12"></path></svg>',
    "Reputation Implications and Recommended Actions": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5V19"></path><path d="M5 12H19"></path><circle cx="12" cy="12" r="8"></circle></svg>',
    "Content Implications of the Reputation Findings": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6H18"></path><path d="M6 12H18"></path><path d="M6 18H14"></path></svg>',
    "Priority Content Opportunities": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12H20"></path><path d="M12 4V20"></path></svg>',
    "Example Article, Guide, or Asset Ideas": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4H14L18 8V20H6Z"></path><path d="M14 4V8H18"></path></svg>',
    "How This Strategy Responds to the Findings": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 12L11 15L16 9"></path><circle cx="12" cy="12" r="8"></circle></svg>',
    "Sources Reviewed": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5H17"></path><path d="M7 10H17"></path><path d="M7 15H12"></path><rect x="5" y="3" width="14" height="18" rx="2"></rect></svg>',
    "Missing Data": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8V12"></path><path d="M12 16H12.01"></path><circle cx="12" cy="12" r="9"></circle></svg>',
    "Assumptions and Confidence Notes": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 7V12"></path><path d="M12 16H12.01"></path><path d="M12 3A9 9 0 1 1 3 12"></path></svg>',
}


def section_icon_svg(title: str) -> str:
    return SECTION_ICONS.get(title) or '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"></circle><path d="M12 8V12"></path><path d="M12 16H12.01"></path></svg>'


DEPARTMENT_ICONS = {
    "pr & comms": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 16H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1"></path><path d="M7 8l8-3v14l-8-3Z"></path><path d="M15 10h2a3 3 0 0 1 0 6h-2"></path></svg>',
    "content": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="4" width="12" height="16" rx="2"></rect><path d="M9 9H15"></path><path d="M9 13H15"></path><path d="M9 17H13"></path></svg>',
    "digital marketing": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="5"></circle><path d="M20 20l-4.2-4.2"></path><path d="M11 8v6"></path><path d="M8 11h6"></path></svg>',
    "brands": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l2.1 4.2 4.6.7-3.3 3.2.8 4.6-4.2-2.2-4.2 2.2.8-4.6-3.3-3.2 4.6-.7Z"></path></svg>',
    "creative services": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7"></path><path d="M14 6h4v4"></path><path d="M6 14v4h4"></path></svg>',
    "insights & intelligence": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18V9"></path><path d="M12 18V5"></path><path d="M18 18v-7"></path></svg>',
}


def department_icon_svg(department: Any) -> str:
    normalized = text(department).strip().lower()
    return DEPARTMENT_ICONS.get(normalized) or '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"></circle><path d="M12 9v3"></path><path d="M12 15h.01"></path></svg>'


def section_heading(level: str, title: str, section_id: str = "", css_class: str = "section-heading") -> str:
    id_attr = f' id="{esc(section_id)}"' if section_id else ""
    return (
        f'<{level}{id_attr} class="{esc(css_class)}">'
        f'<span class="heading-icon" aria-hidden="true">{section_icon_svg(title)}</span>'
        f"<span>{esc(title)}</span>"
        f"</{level}>"
    )


def back_to_contents() -> str:
    return '<p class="back-link"><a href="#contents"><span aria-hidden="true">↩</span><span>Back to contents</span></a></p>'


def linkedin_icon_svg() -> str:
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.8 8.5v8.7M6.8 5.8h.01M10.5 17.2V8.5h4.1c2.1 0 3.4 1.4 3.4 3.8v4.9M10.5 12.2c0-2.3 1.4-3.7 3.3-3.7" /></svg>'


def x_icon_svg() -> str:
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>'


def bluesky_icon_svg() -> str:
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7.5c1.8 1.4 3.1 3 5 5.5 1.9-2.5 3.2-4.1 5-5.5.7-.6 2-.9 2 1 0 1.1-.6 2.4-1.5 3.6-.8 1.1-1.9 2.2-3 2.9 1.2-.2 2.5 0 3.4.6 1 .6 1.4 1.6.7 2.5-.6.8-1.8 1.1-3 .9-1.4-.2-2.7-1-3.6-2.2-.9 1.2-2.2 2-3.6 2.2-1.2.2-2.4-.1-3-.9-.7-.9-.3-1.9.7-2.5.9-.6 2.2-.8 3.4-.6-1.1-.7-2.2-1.8-3-2.9C5.6 11 5 9.7 5 8.6c0-1.9 1.3-1.6 2-1.1Z" /></svg>'


def profile_platform_meta(platform: Any, url: Any) -> dict[str, str]:
    normalized_platform = text(platform).strip().lower()
    normalized_url = text(url).strip().lower()
    if normalized_platform in {"company", "official", "website"}:
        return {"key": "company", "label": "Company", "icon": linkedin_icon_svg()}
    if normalized_platform == "linkedin" or "linkedin.com" in normalized_url:
        return {"key": "linkedin", "label": "LinkedIn", "icon": linkedin_icon_svg()}
    if normalized_platform in {"x", "twitter"} or re.search(r"(^https?://)?(www\.)?(x\.com|twitter\.com)/", normalized_url):
        return {"key": "x", "label": "X", "icon": x_icon_svg()}
    if normalized_platform in {"bluesky", "bsky"} or "bsky.app" in normalized_url:
        return {"key": "bluesky", "label": "Bluesky", "icon": bluesky_icon_svg()}
    return {"key": "profile", "label": "Profile", "icon": linkedin_icon_svg()}


def is_generic_profile_label(name: Any, meta: dict[str, str]) -> bool:
    normalized = text(name).strip().lower()
    if not normalized:
        return True
    generic_labels = {
        "profile",
        "official profile",
        "leadership profile",
        "executive profile",
        "official leadership profile",
        "linkedin",
        "linkedin profile",
        "official linkedin profile",
        "x",
        "x profile",
        "twitter",
        "twitter profile",
        "bluesky",
        "bluesky profile",
    }
    meta_label = text(meta.get("label")).strip().lower()
    if meta_label:
        generic_labels.update({meta_label, f"{meta_label} profile", f"official {meta_label} profile"})
    return normalized in generic_labels


def card_grid(cards: Any, css_class: str = "") -> str:
    if not isinstance(cards, list):
        return ""
    rows: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        title = card.get("title") or card.get("label") or ""
        body = card.get("body") or card.get("value") or card.get("summary") or ""
        if not has_value(title) and not has_value(body):
            continue
        rows.append(f'<article class="card"><h3>{esc(title)}</h3>{rich(body)}</article>')
    class_attr = f"card-grid {esc(css_class)}".strip()
    return f'<div class="{class_attr}">{"".join(rows)}</div>' if rows else ""


def table_html(rows: Any, columns: list[tuple[str, str, bool]], css_class: str = "") -> str:
    if not isinstance(rows, list):
        return ""
    body_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = []
        for _, key, raw in columns:
            value = row.get(key, "")
            rendered_value = text(value) if raw else rich(value)
            if not re.sub(r"<[^>]+>", "", rendered_value).strip():
                rendered_value = '<span class="muted">Not specified</span>'
            cells.append(f"<td>{rendered_value}</td>")
        if any(re.sub(r"<[^>]+>", "", cell).strip() for cell in cells):
            body_rows.append(f"<tr>{''.join(cells)}</tr>")
    if not body_rows:
        return ""
    head = "".join(f"<th>{esc(header)}</th>" for header, _, _ in columns)
    class_attr = f' class="{esc(css_class)}"' if css_class else ""
    return f"<table{class_attr}><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def source_list(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    rows: list[str] = []
    for item in items:
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or item.get("source") or item.get("url") or item.get("source_url")
            url = item.get("url") or item.get("source_url")
        else:
            label = item
            url = item
        if not has_value(label):
            continue
        href = safe_href(url)
        link = f' <a class="source-ref" href="{esc(href)}" target="_blank" rel="noreferrer noopener">[link]</a>' if href else ""
        rows.append(f"<li>{esc(label)}{link}</li>")
    return f"<ul>{''.join(rows)}</ul>" if rows else ""


def recommendation_cards(items: Any, tone: str) -> str:
    if not isinstance(items, list):
        return ""
    rows: list[str] = []
    for index, item in enumerate(items, start=1):
        title = ""
        body = item
        why = ""
        if isinstance(item, dict):
            title = item.get("title") or item.get("action") or item.get("recommendation") or ""
            body = item.get("body") or item.get("recommendation") or item.get("action") or item.get("content") or ""
            why = item.get("why") or item.get("rationale") or item.get("why_it_matters") or ""
        if not has_value(body) and not has_value(title):
            continue
        why_html = f'<div class="recommendation-card__why"><span>Why this matters</span>{rich(why)}</div>' if has_value(why) else ""
        rows.append(
            f'<article class="recommendation-card recommendation-card--{esc(tone)}">'
            f'<div class="recommendation-card__number">{index}</div>'
            '<div class="recommendation-card__body">'
            f"{f'<h3>{esc(title)}</h3>' if title else ''}"
            f'<div class="recommendation-card__action">{rich(body)}</div>{why_html}'
            "</div></article>"
        )
    return f'<div class="recommendation-grid">{"".join(rows)}</div>' if rows else ""


def label_value_grid(items: Any, css_class: str = "snapshot-grid") -> str:
    if not isinstance(items, list):
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        card_label = item.get("label") or item.get("name") or item.get("title") or ""
        role = item.get("role") or ""
        value = item.get("value") or item.get("body") or item.get("note") or item.get("summary") or ""
        url = item.get("source_url") or item.get("url")
        profiles = item.get("profiles") or item.get("linkedin_profiles") or []
        profile_links = ""
        if isinstance(profiles, list):
            links = []
            for profile in profiles:
                if isinstance(profile, dict) and safe_href(profile.get("url")):
                    meta = profile_platform_meta(profile.get("platform"), profile.get("url"))
                    profile_label = text(profile.get("name") or profile.get("platform") or meta.get("label") or "Profile")
                    generic = is_generic_profile_label(profile_label, meta)
                    link_class = f'profile-link {esc(meta["key"])}-link'
                    visible_label = f'<span class="sr-only">{esc(meta["label"])} profile</span>' if generic else f'<span class="profile-link-label">{esc(profile_label)}</span>'
                    if generic:
                        link_class += " profile-link--badge"
                    links.append(
                        f'<a class="{link_class}" href="{esc(profile.get("url"))}" target="_blank" rel="noreferrer noopener" aria-label="{esc((meta["label"] + " profile") if generic else profile_label)}" title="{esc((meta["label"] + " profile") if generic else profile_label)}">'
                        f'<span class="profile-link-icon">{meta["icon"]}</span>{visible_label}</a>'
                    )
            profile_links = f'<div class="profile-links">{"".join(links)}</div>' if links else ""
        source = f' <a class="source-ref" href="{esc(url)}" target="_blank" rel="noreferrer noopener">[link]</a>' if safe_href(url) else ""
        if has_value(card_label) or has_value(value):
            rows.append(
                '<article class="card snapshot-card">'
                f"<strong>{esc(card_label)}</strong>"
                f"{f'<p class=\"person-role\">{esc(role)}</p>' if role else ''}"
                f"{rich(value)}{profile_links}{source}</article>"
            )
    return f'<div class="card-grid {esc(css_class)}">{"".join(rows)}</div>' if rows else ""


def published_messaging_assessment(assessment: Any) -> str:
    if not isinstance(assessment, dict):
        return ""
    statements = assessment.get("statements") or assessment.get("published_statements") or []
    rows: list[str] = []
    if isinstance(statements, list):
        for item in statements:
            if not isinstance(item, dict):
                continue
            source_label = item.get("source") or item.get("source_label") or item.get("label") or "Source"
            source_url = item.get("source_url") or item.get("url")
            source = esc(source_label)
            if safe_href(source_url):
                source = f'<a href="{esc(source_url)}" target="_blank" rel="noreferrer noopener">{source}</a>'
            statement_label = item.get("published_statement") or item.get("type") or item.get("label") or item.get("statement")
            statement_body = item.get("what_it_says") or item.get("body") or item.get("value") or item.get("statement")
            rows.append(
                "<tr>"
                f"<td>{esc(statement_label)}</td>"
                f"<td>{rich(statement_body)}</td>"
                f"<td>{source}</td>"
                "</tr>"
            )
    table = ""
    if rows:
        table = (
            '<table class="published-messaging-table"><thead><tr>'
            "<th>Published statement</th><th>What it says</th><th>Source</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    return (
        '<div class="score messaging-assessment">'
        '<span class="eyebrow">Published messaging assessment</span>'
        f"{rich(assessment.get('summary'))}{table}"
        f'<p><strong>Reputation read-across</strong> {esc(assessment.get("reputation_read_across"))}</p>'
        f'<p><strong>Messaging implication</strong> {esc(assessment.get("practical_implication") or assessment.get("messaging_implication") or assessment.get("implication"))}</p>'
        "</div>"
    )


def competitor_cell(data_dir: Path, row: dict[str, Any]) -> str:
    name = row.get("competitor") or row.get("name") or ""
    website = row.get("website") or row.get("url") or ""
    logo = asset_src(data_dir, row.get("logo_url") or row.get("competitor_logo_url") or row.get("badge_url") or row.get("mark_url"))
    href = safe_href(website)
    image_inner = f'<img src="{esc(logo)}" alt="{esc(name)} logo">' if logo else "?"
    image = (
        f'<a class="competitor-badge" href="{esc(href)}" target="_blank" rel="noreferrer noopener" aria-label="{esc(name)}">'
        f"{image_inner}</a>"
        if href
        else (f'<span class="competitor-badge">{image_inner}</span>' if not logo else f'<span class="competitor-badge"><img src="{esc(logo)}" alt="{esc(name)} logo"></span>')
    )
    name_html = (
        f'<a class="competitor-name" href="{esc(href)}" target="_blank" rel="noreferrer noopener">{esc(name)}</a>'
        if href
        else f'<span class="competitor-name">{esc(name)}</span>'
    )
    return f'<div class="competitor-cell">{image}<span>{name_html}</span></div>'


def competitive_insight_grid(items: Any, css_class: str = "") -> str:
    if not isinstance(items, list):
        return ""
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("label") or item.get("name") or ""
        body = item.get("body") or item.get("value") or item.get("summary") or ""
        if not has_value(title) and not has_value(body):
            continue
        title_html = f'<p class="insight-card__title">{esc(title)}</p>' if has_value(title) else ""
        body_html = rich(body) if has_value(body) else ""
        rows.append(f'<article class="card insight-card">{title_html}{body_html}</article>')
    if not rows:
        return ""
    class_attr = f'card-grid insight-grid {esc(css_class)}'.strip()
    return f'<div class="{class_attr}">{"".join(rows)}</div>'


def news_table(data_dir: Path, news: Any) -> str:
    if not isinstance(news, list):
        return ""
    rows: list[str] = []
    for item in news:
        if not isinstance(item, dict):
            continue
        logo = asset_src(data_dir, item.get("source_logo_url") or item.get("publisher_logo_url"))
        publisher = item.get("source") or item.get("publisher") or ""
        logo_html = f'<span class="publisher-badge publisher-badge--image"><img src="{esc(logo)}" alt="{esc(publisher)} logo"></span>' if logo else '<span class="publisher-badge publisher-badge--missing">?</span>'
        href = safe_href(item.get("url") or item.get("source_url"))
        headline = esc(item.get("headline") or item.get("title"))
        if href:
            headline = f'<a href="{esc(href)}" target="_blank" rel="noreferrer noopener">{headline}</a>'
        rows.append(
            "<tr>"
            f"<td>{logo_html}<strong>{headline}</strong><br><small>{esc(publisher)} · {esc(item.get('date'))}</small></td>"
            f"<td>{esc(item.get('sentiment'))}</td>"
            f"<td>{esc(item.get('influence_score'))}</td>"
            f"<td>{rich(item.get('rank_reason') or item.get('why_it_matters'))}</td>"
            "</tr>"
        )
    return (
        '<table class="news-table"><thead><tr><th>Story</th><th>Sentiment</th><th>Influence</th><th>Why it matters</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        if rows
        else ""
    )


def simple_charts(charts: Any) -> str:
    if not isinstance(charts, list):
        return ""
    chart_blocks = []
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        rows_html = []
        rows = chart.get("rows") or chart.get("items") or chart.get("series") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = row.get("value") or row.get("score") or row.get("index_score") or 0
                try:
                    width = max(0, min(100, float(value)))
                except Exception:
                    width = 55
                rows_html.append(
                    '<div class="chart-row">'
                    f'<strong>{esc(row.get("label") or row.get("name"))}</strong>'
                    f'<span class="chart-bar"><span style="width:{width:.0f}%"></span></span>'
                    f'<em>{esc(row.get("display_value") or row.get("status") or row.get("note"))}</em>'
                    f'{rich(row.get("note") or row.get("evidence"))}'
                    "</div>"
                )
        if rows_html:
            chart_blocks.append(
                '<div class="chart-card">'
                f'<div class="chart-card__header"><h4>{esc(chart.get("title"))}</h4>{rich(chart.get("subtitle"))}</div>'
                f'<div class="chart-card__rows">{"".join(rows_html)}</div></div>'
            )
    return f'<div class="chart-grid">{"".join(chart_blocks)}</div>' if chart_blocks else ""


def department_signals(items: Any, lead_department: str) -> str:
    if not isinstance(items, list):
        return ""
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dept = item.get("department") or item.get("name") or ""
        body = item.get("opportunity_signal") or item.get("rationale") or item.get("opportunity") or ""
        tone = text(item.get("tone") or item.get("status") or "green").lower()
        lead = " opportunity-signal--lead" if text(dept).lower() == text(lead_department).lower() else ""
        icon_tone = tone if tone in {"good", "warn", "bad"} else "good"
        cards.append(
            f'<article class="opportunity-signal opportunity-signal--{esc(tone)}{lead}">'
            f'<div class="department-label"><span class="department-label__icon department-label__icon--{esc(icon_tone)}">{department_icon_svg(dept)}</span><span class="department-label__text">{esc(dept)}</span></div>'
            f"{rich(body)}</article>"
        )
    return f'<div class="opportunity-signal-grid">{"".join(cards)}</div>' if cards else ""


def opportunity_strategy(strategy: Any) -> str:
    if not isinstance(strategy, dict):
        return ""
    headline = strategy.get("headline") or "Recommended marketing strategy"
    body = strategy.get("strategy") or strategy.get("body") or ""
    why = strategy.get("why_it_matters") or strategy.get("why") or ""
    threads = strategy.get("built_from_findings") or strategy.get("threads") or []
    return (
        '<div class="opportunity-lead opportunity-lead--strategy">'
        '<div class="opportunity-lead__hero"><div class="opportunity-lead__head">'
        f'<span class="eyebrow">Recommended marketing strategy</span><h3>{esc(headline)}</h3></div></div>'
        f'<p class="opportunity-lead__verdict">{esc(body)}</p>'
        '<div class="opportunity-lead__grid">'
        f'<div class="opportunity-lead__panel"><span class="eyebrow">Why this strategy</span>{rich(why)}</div>'
        f'<div class="opportunity-lead__panel"><span class="eyebrow">Built from report findings</span>{list_html(threads)}</div>'
        "</div></div>"
    )


def timeline(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(f'<article class="timeline-step"><h3>{esc(item.get("title"))}</h3>{list_html(item.get("items"))}</article>')
    return f'<div class="timeline">{"".join(rows)}</div>' if rows else ""


def campaign_ideas(data_dir: Path, ideas: Any) -> str:
    if not isinstance(ideas, list):
        return ""
    cards = []
    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        title = idea.get("title") or ""
        visual = asset_src(data_dir, idea.get("illustration_url") or idea.get("image_url") or idea.get("asset"))
        visual_html = f'<div class="idea-card__visual"><img src="{esc(visual)}" alt="{esc(title)} illustration"></div>' if visual else '<div class="idea-card__visual idea-card__visual--fallback"><span>NB</span></div>'
        body_parts = []
        fields = [
            ("Driving idea", idea.get("driving_idea") or idea.get("concept")),
            ("Implementation story", idea.get("implementation_story") or idea.get("activation")),
            ("Addresses", idea.get("addresses")),
            ("Why it fits", idea.get("why_it_fits")),
            ("Press angle", idea.get("press_angle")),
            ("Why it will work", idea.get("why_it_will_work")),
            ("Intended effect", idea.get("intended_effect")),
        ]
        for label, value in fields:
            if has_value(value):
                body_parts.append(f'<p><strong>{esc(label)}</strong> {esc(value)}</p>')
        activation = idea.get("activation_plan") or idea.get("activation_expressions") or []
        if isinstance(activation, dict):
            activation = activation.get("order_of_precedence") or activation.get("items") or []
        activation_items = []
        if isinstance(activation, list):
            for item in activation:
                if not isinstance(item, dict):
                    continue
                parts = []
                for label, key in [
                    ("What the brand creates", "creates"),
                    ("What it looks like", "looks_like"),
                    ("Why this shape", "why_this_format"),
                    ("Intended result", "intended_result"),
                ]:
                    value = item.get(key) or (item.get("primary_goal") if key == "creates" else "") or (item.get("narrative") if key == "looks_like" else "")
                    if has_value(value):
                        parts.append(f"<p><strong>{esc(label)}</strong> {esc(value)}</p>")
                examples = item.get("example_moments") or item.get("example_user_paths")
                if isinstance(examples, list) and examples:
                    parts.append(f'<div class="idea-activation-plan__examples"><strong>Example moments</strong>{list_html(examples)}</div>')
                if parts:
                    activation_items.append(
                        {
                            "title": esc(item.get("name") or item.get("title")),
                            "body": "".join(parts),
                        }
                    )
        activation_html = ""
        if len(activation_items) == 1:
            single = activation_items[0]
            activation_html = (
                '<div class="idea-activation-plan"><p><strong>Activation expression</strong></p>'
                '<div class="idea-activation-plan__single">'
                f'<div class="idea-activation-plan__item"><div class="idea-activation-plan__title">{single["title"]}</div>{single["body"]}</div>'
                "</div></div>"
            )
        elif activation_items:
            activation_list = "".join(
                f'<li class="idea-activation-plan__item"><div class="idea-activation-plan__title">{item["title"]}</div>{item["body"]}</li>'
                for item in activation_items
            )
            activation_html = f'<div class="idea-activation-plan"><p><strong>Activation expressions</strong></p><ol class="idea-activation-plan__list">{activation_list}</ol></div>'
        channels = idea.get("channels") or []
        channel_html = "".join(f'<span class="idea-card__channel">{esc(channel)}</span>' for channel in channels) if isinstance(channels, list) else ""
        cards.append(
            '<article class="idea-card">'
            f"{visual_html}<div class=\"idea-card__body\"><div class=\"idea-card__header\"><div class=\"idea-card__eyebrow\">Creative campaign idea</div><h3>{esc(title)}</h3></div>"
            f'<div class="idea-card__copy">{"".join(body_parts)}{activation_html}</div>'
            f'{f"<div class=\"idea-card__channels\">{channel_html}</div>" if channel_html else ""}</div></article>'
        )
    return f'<div class="idea-grid">{"".join(cards)}</div>' if cards else ""


def toc(items: list[tuple[str, str]]) -> str:
    links = "".join(f'<li><a href="#{esc(section_id)}">{esc(label)}</a></li>' for section_id, label in items)
    return f'<nav class="toc" id="contents"><div class="toc-eyebrow">Contents</div><ul>{links}</ul></nav>'


def render(data_path: Path, template_path: Path, output_path: Path) -> Path:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data_dir = data_path.parent
    brand = data.get("brand", {})
    title = f"{text(brand.get('name') or 'Brand')} New Business Intelligence Report"
    logo = asset_src(data_dir, brand.get("logo_url") or brand.get("mark_url"))
    logo_html = (
        f'<div class="brand-logo-slot"><img src="{esc(logo)}" alt="{esc(brand.get("name"))} logo"></div>'
        if logo
        else f'<div class="brand-logo-slot brand-logo-slot--fallback"><span>{esc(text(brand.get("name") or "NB")[:2].upper())}</span></div>'
    )

    toc_items = [
        ("company-snapshot", "Company Snapshot"),
        ("executive-summary", "Executive Summary"),
        ("agency-opportunity", "Archetype Opportunity Assessment"),
        ("storybrand-messaging", "Messaging Assessment"),
        ("usp-ksp-review", "USP and KSP Review"),
        ("competitive-landscape", "Competitive Landscape"),
        ("seo-audit", "SEO Audit"),
        ("brand-reputation", "Brand Reputation Snapshot"),
        ("opportunities", "Opportunities"),
        ("creative-campaign-ideas", "Creative Campaign Ideas"),
        ("content-strategy", "Content Strategy Recommendations"),
        ("appendix", "Appendix"),
    ]

    cover = data.get("cover", {})
    report_meta = data.get("report_meta", {})
    brand_website = safe_href(brand.get("website"))
    brand_website_html = f'<a href="{esc(brand_website)}">{esc(compact_url_label(brand.get("website")))}</a>' if brand_website else esc(brand.get("website"))
    competitor_list = ", ".join(str(item) for item in cover.get("competitors", []) if has_value(item)) if isinstance(cover.get("competitors"), list) else ""
    assumptions = " ".join(str(item) for item in cover.get("assumptions", []) if has_value(item)) if isinstance(cover.get("assumptions"), list) else ""
    hero_pills = []
    distribution = report_meta.get("distribution")
    audience = report_meta.get("audience")
    if isinstance(distribution, dict):
        hero_pills.append({**distribution, "tone": distribution.get("tone") or "warn"})
    elif has_value(distribution):
        hero_pills.append({"label": distribution, "tone": "warn"})
    if isinstance(audience, dict):
        hero_pills.append({**audience, "tone": audience.get("tone") or "good"})
    elif has_value(audience):
        hero_pills.append({"label": audience, "tone": "good"})

    body = [
        '<section class="hero">',
        '<div class="hero-head">',
        logo_html,
        '<div class="hero-copy">',
        '<div class="eyebrow">NewBizIntel</div>',
        f'<h1>{esc(brand.get("name"))}</h1>',
        rich(cover.get("summary")),
        "</div></div>",
        '<div class="meta">',
        f"<div><strong>Website</strong><br>{brand_website_html}</div>",
        f"<div><strong>Date</strong><br>{esc(brand.get('date'))}</div>",
        f"<div><strong>Scope</strong><br>{esc(cover.get('scope'))}</div>",
        f"<div><strong>Competitors analysed</strong><br>{esc(competitor_list)}</div>",
        "</div>",
        f'<p class="note">{esc(assumptions)}</p>' if assumptions else "",
        f'<p>{pill_html(hero_pills)}</p>',
        rich(report_meta.get("note")),
        toc(toc_items),
        "</section>",
    ]

    snapshot = data.get("company_snapshot", {})
    body.extend([
        section_heading("h2", "Company Snapshot", "company-snapshot"),
        rich(snapshot.get("summary")),
        label_value_grid(snapshot.get("items")),
        section_heading("h3", "Finance and Scale", css_class="category-heading"),
        label_value_grid(snapshot.get("finance_stats"), "snapshot-grid snapshot-grid--finance"),
        section_heading("h3", "Leadership", css_class="category-heading"),
        label_value_grid(snapshot.get("leadership"), "snapshot-grid people-grid"),
        section_heading("h3", "Founders", css_class="category-heading"),
        label_value_grid(snapshot.get("founders"), "snapshot-grid people-grid"),
        section_heading("h3", "Ownership and Funding", css_class="category-heading"),
        label_value_grid(snapshot.get("ownership_funding")),
        section_heading("h3", "Snapshot Sources", css_class="category-heading"),
        label_value_grid(snapshot.get("source_map"), "snapshot-grid snapshot-grid--sources"),
        back_to_contents(),
    ])

    executive = data.get("executive_summary", {})
    body.extend([
        section_heading("h2", "Executive Summary", "executive-summary"),
        card_grid(executive.get("cards")),
        f'<p><strong>Overall recommendation:</strong> {esc(executive.get("overall_recommendation"))}</p>' if has_value(executive.get("overall_recommendation")) else "",
        back_to_contents(),
    ])

    agency = data.get("agency_opportunity", {})
    lead = agency.get("lead_offering", {}) if isinstance(agency.get("lead_offering"), dict) else {}
    body.extend([
        section_heading("h2", "Archetype Opportunity Assessment", "agency-opportunity"),
        f'<div class="score"><span class="eyebrow">Archetype fit score</span><strong>{esc(agency.get("score"))}</strong>{rich(agency.get("score_summary"))}</div>',
        rich(agency.get("summary")),
        '<div class="opportunity-lead"><div class="opportunity-lead__hero"><div class="opportunity-lead__head"><span class="eyebrow">Recommended lead offering</span>'
        f'<h3>{esc(lead.get("name"))}</h3></div></div><p class="opportunity-lead__verdict">{esc(lead.get("verdict"))}</p>'
        f'<div class="opportunity-lead__department"><strong>Lead department:</strong> {esc(lead.get("lead_department"))}</div>'
        '<div class="opportunity-lead__grid">'
        f'<div class="opportunity-lead__panel"><span class="eyebrow">Why this should lead</span>{list_html(lead.get("why_this_leads"))}</div>'
        f'<div class="opportunity-lead__panel"><span class="eyebrow">Expected outcomes</span>{list_html(lead.get("expected_outcomes"))}</div>'
        "</div></div>",
        section_heading("h3", "Department Opportunity Signals", css_class="category-heading"),
        department_signals(agency.get("department_opportunity_map"), lead.get("lead_department")),
        card_grid(agency.get("cards")),
        section_heading("h3", "Most Likely Workstreams", css_class="category-heading"),
        list_html(agency.get("priority_workstreams")),
        section_heading("h3", "Why Archetype Is Well Matched", css_class="category-heading"),
        list_html(agency.get("archetype_advantages")),
        back_to_contents(),
    ])

    storybrand = data.get("storybrand", {})
    body.extend([
        section_heading("h2", "Messaging Assessment", "storybrand-messaging"),
        published_messaging_assessment(storybrand.get("existing_messaging_assessment")),
        f'<div class="score"><span class="eyebrow">Messaging score</span><strong>{esc(storybrand.get("score"))}</strong>{rich(storybrand.get("score_summary"))}</div>',
        card_grid(storybrand.get("cards")),
        section_heading("h3", "Recommended One-Liner", css_class="category-heading"),
        f'<p><strong>{esc(storybrand.get("one_liner"))}</strong></p>' if has_value(storybrand.get("one_liner")) else "",
        section_heading("h3", "Biggest Messaging Fixes", css_class="category-heading"),
        recommendation_cards(storybrand.get("messaging_fixes"), "teal"),
        section_heading("h3", "Content Implications of the Messaging Findings", css_class="category-heading"),
        recommendation_cards(storybrand.get("content_implications"), "gold"),
        back_to_contents(),
    ])

    usp = data.get("usp_ksp_review", {})
    body.extend([
        section_heading("h2", "USP and KSP Review", "usp-ksp-review"),
        f'<div class="score"><span class="eyebrow">USP and KSP score</span><strong>{esc(usp.get("score"))}</strong>{rich(usp.get("score_summary"))}</div>',
        table_html(usp.get("claimed_positioning"), [("Claim", "claim", False), ("Evidence", "evidence", False), ("Gap", "gap", False), ("Fix", "fix", False)]),
        back_to_contents(),
    ])

    landscape = data.get("competitive_landscape", {})
    competitor_rows = []
    for row in landscape.get("table", []) if isinstance(landscape.get("table"), list) else []:
        if isinstance(row, dict):
            row = dict(row)
            row["competitor_cell"] = competitor_cell(data_dir, row)
            competitor_rows.append(row)
    body.extend([
        section_heading("h2", "Competitive Landscape", "competitive-landscape"),
        table_html(competitor_rows, [("Competitor", "competitor_cell", True), ("Why it matters", "why_it_matters", False), ("Positioning pattern", "positioning_pattern", False), ("Implication for the brand", "implication", False)], "competitive-table"),
        simple_charts(landscape.get("charts")),
        section_heading("h3", "Why Each Competitor Matters", css_class="category-heading"),
        competitive_insight_grid(landscape.get("why_each_competitor_matters"), "insight-grid--competitors"),
        section_heading("h3", "Messaging Patterns Across the Market", css_class="category-heading"),
        competitive_insight_grid(landscape.get("messaging_patterns"), "insight-grid--market-patterns"),
        section_heading("h3", "Content Patterns Across the Market", css_class="category-heading"),
        competitive_insight_grid(landscape.get("content_patterns"), "insight-grid--market-patterns"),
        section_heading("h3", "Areas Where the Brand Is Behind, Matched, or Ahead", css_class="category-heading"),
        competitive_insight_grid(landscape.get("status_summary"), "insight-grid--summary"),
        back_to_contents(),
    ])

    seo = data.get("seo_audit", {})
    semrush_evidence = seo.get("semrush_evidence") if isinstance(seo, dict) else []
    similarweb_evidence = seo.get("similarweb_evidence") if isinstance(seo, dict) else []
    search_evidence = seo.get("search_evidence") if isinstance(seo, dict) else []
    seo_provider_evidence = semrush_evidence or similarweb_evidence or search_evidence
    if isinstance(semrush_evidence, list) and semrush_evidence:
        seo_provider_heading = "SEMrush Evidence Behind the Diagnosis"
    elif isinstance(similarweb_evidence, list) and similarweb_evidence:
        seo_provider_heading = "SimilarWeb Evidence Behind the Diagnosis"
    else:
        seo_provider_heading = "Search Evidence Behind the Diagnosis"
    body.extend([
        section_heading("h2", "SEO Audit", "seo-audit"),
        card_grid(seo.get("cards")),
        section_heading("h3", seo_provider_heading, css_class="category-heading"),
        card_grid(seo_provider_evidence),
        simple_charts(seo.get("charts")),
        section_heading("h3", "Priority Issues with Evidence, Reason, and Recommended Fix", css_class="category-heading"),
        table_html(seo.get("priority_issues"), [("Issue", "issue", False), ("Evidence", "evidence", False), ("Why it matters", "why_it_matters", False), ("Recommended fix", "recommended_fix", False)]),
        section_heading("h3", "Content Implications of the SEO Findings", css_class="category-heading"),
        list_html(seo.get("content_implications")),
        back_to_contents(),
    ])

    reputation = data.get("brand_reputation", {})
    body.extend([
        section_heading("h2", "Brand Reputation Snapshot", "brand-reputation"),
        f"<p>{pill_html(reputation.get('pills'))}</p>",
        card_grid(reputation.get("cards")),
        section_heading("h3", "Platform-Level Readout", css_class="category-heading"),
        list_html(reputation.get("platform_readout")),
        section_heading("h3", "Most Influential News Stories in the Last Six Months", css_class="category-heading"),
        news_table(data_dir, reputation.get("influential_news")),
        section_heading("h3", "Reputation Implications and Recommended Actions", css_class="category-heading"),
        recommendation_cards(reputation.get("recommended_actions"), "teal"),
        section_heading("h3", "Content Implications of the Reputation Findings", css_class="category-heading"),
        recommendation_cards(reputation.get("content_implications"), "gold"),
        back_to_contents(),
    ])

    opportunities = data.get("opportunities", {})
    body.extend([
        section_heading("h2", "Opportunities", "opportunities"),
        opportunity_strategy(opportunities.get("marketing_strategy") if isinstance(opportunities, dict) else {}),
        timeline(opportunities.get("timelines") if isinstance(opportunities, dict) else []),
        back_to_contents(),
    ])

    campaigns = data.get("creative_campaign_ideas") or data.get("creative_campaigns") or {}
    body.extend([
        section_heading("h2", "Creative Campaign Ideas", "creative-campaign-ideas"),
        campaign_ideas(data_dir, campaigns.get("ideas") if isinstance(campaigns, dict) else []),
        back_to_contents(),
    ])

    content = data.get("content_strategy", {})
    body.extend([
        section_heading("h2", "Content Strategy Recommendations", "content-strategy"),
        card_grid(content.get("cards") if isinstance(content, dict) else []),
        section_heading("h3", "Priority Content Opportunities", css_class="category-heading"),
        list_html(content.get("priority_opportunities") if isinstance(content, dict) else []),
        section_heading("h3", "Example Article, Guide, or Asset Ideas", css_class="category-heading"),
        list_html(content.get("example_ideas") if isinstance(content, dict) else []),
        section_heading("h3", "How This Strategy Responds to the Findings", css_class="category-heading"),
        rich(content.get("response_to_findings") if isinstance(content, dict) else ""),
        back_to_contents(),
    ])

    appendix = data.get("appendix", {})
    appendix_sources = []
    if isinstance(appendix, dict):
        appendix_sources = appendix.get("source_map") or appendix.get("sources_reviewed") or []
    appendix_missing = appendix.get("missing_data") if isinstance(appendix, dict) else []
    appendix_confidence = appendix.get("assumptions_and_confidence_notes") if isinstance(appendix, dict) else []
    appendix_tail = []
    if isinstance(appendix_missing, list) and appendix_missing:
        appendix_tail.extend([
            section_heading("h3", "Missing Data", css_class="category-heading"),
            list_html(appendix_missing),
        ])
    if isinstance(appendix_confidence, list) and appendix_confidence:
        appendix_tail.extend([
            section_heading("h3", "Assumptions and Confidence Notes", css_class="category-heading"),
            list_html(appendix_confidence),
        ])

    body.extend([
        section_heading("h2", "Appendix", "appendix"),
        '<div class="source-list">',
        section_heading("h3", "Sources Reviewed", css_class="category-heading"),
        source_list(appendix_sources),
        *appendix_tail,
        "</div>",
        back_to_contents(),
        f'<p class="footer">{esc(data.get("footer_note"))}</p>' if has_value(data.get("footer_note")) else "",
    ])

    template = template_path.read_text(encoding="utf-8")
    html_text = template.replace("{{PAGE_TITLE}}", esc(title)).replace("{{BODY_CONTENT}}", "\n".join(part for part in body if part).strip())
    file_uri_matches = re.findall(r"file:///[^\"'<\s)]+", html_text, flags=re.I)
    if file_uri_matches:
        raise SystemExit("Rendered HTML contains local file URIs: " + ", ".join(sorted(set(file_uri_matches))[:5]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def main():
    args = parse_args()
    data_path = Path(args.data_path).expanduser().resolve()
    script_root = Path(__file__).resolve().parents[2]
    template_path = Path(args.template_path).expanduser().resolve() if args.template_path else script_root / "templates" / "report-template.html"
    output_path = Path(args.output_path).expanduser().resolve() if args.output_path else data_path.parent / "newbizintel-report.html"
    rendered = render(data_path, template_path, output_path)
    print(json.dumps({"data": str(data_path), "template": str(template_path), "html": str(rendered)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
