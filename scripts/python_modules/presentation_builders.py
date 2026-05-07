from __future__ import annotations

import html
import json
import re
import textwrap
import zipfile
from pathlib import Path
from typing import Any


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


def list_html(items: list[Any], *, has_value: Any) -> str:
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


def render_html(
    data_path: Path,
    output_path: Path | None = None,
    *,
    read_json: Any,
    campaign_section: Any,
    reputation_subscore_summary: Any,
    has_value: Any,
    inject_task_list_into_html: Any,
) -> Path:
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
<p class="eyebrow">NewBizIntel report</p>
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
        body = "".join(f"<h3>{html.escape(section_title)}</h3><table>{rows}</table>" for section_title, rows in snapshot_tables if rows)
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
        content_blocks += list_html(content_strategy.get("priority_opportunities", []), has_value=has_value)
        content_blocks += list_html(content_strategy.get("example_ideas", []), has_value=has_value)
        if content_strategy.get("response_to_findings"):
            content_blocks += f"<p>{html.escape(str(content_strategy.get('response_to_findings')))}</p>"
        sections.append("<section><h2>Content Strategy Recommendations</h2>" + content_blocks + "</section>")
    appendix = data.get("appendix", {})
    if isinstance(appendix, dict):
        appendix_sources = appendix.get("source_map") or appendix.get("sources_reviewed") or []
        appendix_blocks = ""
        if appendix_sources:
            appendix_blocks += "<h3>Sources Reviewed</h3>" + source_list_html(appendix_sources)
        appendix_blocks += list_html(appendix.get("missing_data", []), has_value=has_value)
        appendix_blocks += list_html(appendix.get("assumptions_and_confidence_notes", []), has_value=has_value)
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


def pptx_safe_logo_asset(data_path: Path, value: str | None, *, relative_to_brand: Any) -> str:
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


def pptx_safe_data_copy(
    data_path: Path,
    *,
    read_json: Any,
    write_json: Any,
    relative_to_brand: Any,
    slugify: Any,
) -> Path:
    data = read_json(data_path)
    asset_dir = data_path.parent / "slide-assets"
    brand = data.setdefault("brand", {})
    brand_name = brand.get("name", "Brand")
    brand_slug = brand.get("slug") or slugify(brand_name)
    brand_logo = pptx_safe_logo_asset(data_path, brand.get("logo_url"), relative_to_brand=relative_to_brand) or pptx_safe_logo_asset(
        data_path,
        brand.get("mark_url"),
        relative_to_brand=relative_to_brand,
    )
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
            rel = pptx_safe_logo_asset(data_path, row.get(field), relative_to_brand=relative_to_brand)
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
            rel = (
                pptx_safe_logo_asset(data_path, item.get("publisher_logo_url"), relative_to_brand=relative_to_brand)
                or pptx_safe_logo_asset(data_path, item.get("source_logo_url"), relative_to_brand=relative_to_brand)
                or pptx_safe_logo_asset(data_path, item.get("logo_url"), relative_to_brand=relative_to_brand)
            )
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

    temp_path = data_path.parent / ".newbizintel-pptx-data.json"
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


def build_minimal_pptx(
    data_path: Path,
    output_path: Path,
    *,
    read_json: Any,
    utc_now: Any,
    campaign_section: Any,
) -> None:
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
        pptx.writestr("docProps/app.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>NewBizIntel Python Runner</Application><Slides>{slide_count}</Slides></Properties>""")
        pptx.writestr("docProps/core.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{html.escape(brand)} NewBizIntel Report</dc:title><dc:creator>NewBizIntel</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{utc_now()}</dcterms:created></cp:coreProperties>""")
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
        pptx.writestr("ppt/theme/theme1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="NewBizIntel"><a:themeElements><a:clrScheme name="NewBizIntel"><a:dk1><a:srgbClr val="09213B"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="153A5B"/></a:dk2><a:lt2><a:srgbClr val="F7FAFC"/></a:lt2><a:accent1><a:srgbClr val="153A5B"/></a:accent1><a:accent2><a:srgbClr val="3AA7A3"/></a:accent2><a:accent3><a:srgbClr val="D28B26"/></a:accent3><a:accent4><a:srgbClr val="5D6B7A"/></a:accent4><a:accent5><a:srgbClr val="10263B"/></a:accent5><a:accent6><a:srgbClr val="D8E2EC"/></a:accent6><a:hlink><a:srgbClr val="153A5B"/></a:hlink><a:folHlink><a:srgbClr val="153A5B"/></a:folHlink></a:clrScheme><a:fontScheme name="NewBizIntel"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme><a:fmtScheme name="NewBizIntel"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>""")
        for i, (slide_title, bullets) in enumerate(slides, start=1):
            pptx.writestr(f"ppt/slides/slide{i}.xml", pptx_slide_xml(slide_title, bullets, i))
            pptx.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", pptx_rels_xml("../slideLayouts/slideLayout1.xml"))
