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
            tone_class = f" pill--{esc(tone)}" if tone else ""
            if has_value(label):
                rows.append(f'<span class="pill{tone_class}">{esc(label)}</span>')
        else:
            rows.append(f'<span class="pill">{esc(item)}</span>')
    return "".join(rows)


def section_heading(level: str, title: str, section_id: str = "", css_class: str = "section-heading") -> str:
    id_attr = f' id="{esc(section_id)}"' if section_id else ""
    return (
        f'<{level}{id_attr} class="{esc(css_class)}">'
        '<span class="section-icon" aria-hidden="true">⌁</span>'
        f"<span>{esc(title)}</span>"
        f"</{level}>"
    )


def back_to_contents() -> str:
    return '<p class="back-link"><a href="#contents">Back to contents</a></p>'


def card_grid(cards: Any) -> str:
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
    return f'<div class="card-grid">{"".join(rows)}</div>' if rows else ""


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
        label = item.get("label") or item.get("name") or item.get("title") or ""
        role = item.get("role") or ""
        value = item.get("value") or item.get("body") or item.get("note") or item.get("summary") or ""
        url = item.get("source_url") or item.get("url")
        profiles = item.get("profiles") or item.get("linkedin_profiles") or []
        profile_links = ""
        if isinstance(profiles, list):
            links = []
            for profile in profiles:
                if isinstance(profile, dict) and safe_href(profile.get("url")):
                    links.append(f'<a class="profile-link" href="{esc(profile.get("url"))}" target="_blank" rel="noreferrer noopener">{esc(profile.get("name") or profile.get("platform") or "Profile")}</a>')
            profile_links = f'<div class="profile-links">{"".join(links)}</div>' if links else ""
        source = f' <a class="source-ref" href="{esc(url)}" target="_blank" rel="noreferrer noopener">[link]</a>' if safe_href(url) else ""
        if has_value(label) or has_value(value):
            rows.append(
                '<article class="card snapshot-card">'
                f"<strong>{esc(label)}</strong>"
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
    image = f'<span class="competitor-badge"><img src="{esc(logo)}" alt="{esc(name)} logo"></span>' if logo else '<span class="competitor-badge">?</span>'
    href = safe_href(website)
    site = f'<a href="{esc(href)}">{esc(website)}</a>' if href else esc(website)
    return f'<div class="competitor-cell">{image}<span><strong>{esc(name)}</strong><br><small>{site}</small></span></div>'


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
        rows = chart.get("rows") or chart.get("items") or []
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
        cards.append(
            f'<article class="opportunity-signal opportunity-signal--{esc(tone)}{lead}">'
            f'<div class="department-label"><span class="department-label__icon">•</span><span class="department-label__text">{esc(dept)}</span></div>'
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
                    activation_items.append(f'<li class="idea-activation-plan__item"><div class="idea-activation-plan__title">{esc(item.get("name") or item.get("title"))}</div>{"".join(parts)}</li>')
        activation_html = ""
        if len(activation_items) == 1:
            activation_html = f'<div class="idea-activation-plan"><p><strong>Activation expression</strong></p><div class="idea-activation-plan__single">{activation_items[0].replace("<li", "<div", 1).replace("</li>", "</div>")}</div></div>'
        elif activation_items:
            activation_html = f'<div class="idea-activation-plan"><p><strong>Activation expressions</strong></p><ol class="idea-activation-plan__list">{"".join(activation_items)}</ol></div>'
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
    brand_website_html = f'<a href="{esc(brand_website)}">{esc(brand.get("website"))}</a>' if brand_website else esc(brand.get("website"))
    competitor_list = ", ".join(str(item) for item in cover.get("competitors", []) if has_value(item)) if isinstance(cover.get("competitors"), list) else ""
    assumptions = " ".join(str(item) for item in cover.get("assumptions", []) if has_value(item)) if isinstance(cover.get("assumptions"), list) else ""

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
        f'<p>{pill_html([report_meta.get("distribution"), report_meta.get("audience")])}</p>',
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
        card_grid(landscape.get("why_each_competitor_matters")),
        section_heading("h3", "Messaging Patterns Across the Market", css_class="category-heading"),
        list_html(landscape.get("messaging_patterns")),
        section_heading("h3", "Content Patterns Across the Market", css_class="category-heading"),
        list_html(landscape.get("content_patterns")),
        section_heading("h3", "Areas Where the Brand Is Behind, Matched, or Ahead", css_class="category-heading"),
        list_html(landscape.get("status_summary")),
        back_to_contents(),
    ])

    seo = data.get("seo_audit", {})
    body.extend([
        section_heading("h2", "SEO Audit", "seo-audit"),
        card_grid(seo.get("cards")),
        section_heading("h3", "SEMrush Evidence Behind the Diagnosis", css_class="category-heading"),
        card_grid(seo.get("semrush_evidence") or seo.get("search_evidence") or seo.get("similarweb_evidence")),
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
