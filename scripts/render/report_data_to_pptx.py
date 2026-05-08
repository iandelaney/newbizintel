import argparse
import importlib
import json
import os
import re
import site
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

def enable_vendor_site(runtime_name):
    vendor_site = Path(__file__).resolve().parents[2] / 'vendor' / runtime_name
    if not vendor_site.exists():
        return
    if sys.platform != "win32" and any(vendor_site.rglob("*.pyd")):
        return
    if str(vendor_site) not in sys.path:
        sys.path.insert(0, str(vendor_site))


enable_vendor_site('pptx_runtime')
runtime_site = Path(sys.executable).resolve().parent / "Lib" / "site-packages"
if runtime_site.exists() and str(runtime_site) not in sys.path:
    sys.path.append(str(runtime_site))

try:
    import lxml.etree  # noqa: F401
    from PIL import Image as _PIL_Image  # noqa: F401
except Exception:
    pass

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.append(user_site)

for module_name in [name for name in list(sys.modules) if name == "pptx" or name.startswith("pptx.")]:
    sys.modules.pop(module_name, None)

Presentation = importlib.import_module("pptx.api").Presentation
RGBColor = importlib.import_module("pptx.dml.color").RGBColor
_pptx_enum_shapes = importlib.import_module("pptx.enum.shapes")
MSO_AUTO_SHAPE_TYPE = _pptx_enum_shapes.MSO_AUTO_SHAPE_TYPE
MSO_CONNECTOR = _pptx_enum_shapes.MSO_CONNECTOR
_pptx_enum_text = importlib.import_module("pptx.enum.text")
MSO_ANCHOR = _pptx_enum_text.MSO_ANCHOR
PP_ALIGN = _pptx_enum_text.PP_ALIGN
_pptx_util = importlib.import_module("pptx.util")
Inches = _pptx_util.Inches
Pt = _pptx_util.Pt


PALETTE = {
    "navy": RGBColor(0x10, 0x26, 0x3B),
    "blue": RGBColor(0x1A, 0x4A, 0x73),
    "teal": RGBColor(0x3A, 0xA7, 0xA3),
    "sky": RGBColor(0xEE, 0xF5, 0xF8),
    "ink": RGBColor(0x1F, 0x29, 0x33),
    "muted": RGBColor(0x5B, 0x6B, 0x7A),
    "line": RGBColor(0xD7, 0xE3, 0xEC),
    "white": RGBColor(0xFF, 0xFF, 0xFF),
    "amber": RGBColor(0xD2, 0x8B, 0x26),
    "soft_amber": RGBColor(0xFA, 0xF2, 0xE7),
    "soft_blue": RGBColor(0xF3, 0xF8, 0xFC),
    "forest": RGBColor(0x1D, 0x43, 0x3A),
}

SECTION_MARKERS = {
    "snapshot": "snapshot.png",
    "executive": "executive.png",
    "messaging": "messaging.png",
    "competitors": "competitors.png",
    "seo": "seo.png",
    "reputation": "reputation.png",
    "content": "content.png",
    "roadmap": "roadmap.png",
    "closing": "closing.png",
}


DEPARTMENT_ICON_KEYS = {
    "pr & comms": "messaging",
    "content": "content",
    "digital marketing": "seo",
    "brands": "reputation",
    "creative services": "fixes",
    "insights & intelligence": "snapshot",
}

COMPETITOR_LOGOS = {
    "Q-CTRL": "q-ctrl.png",
    "Alice & Bob": "alice-bob.png",
    "SEEQC": "seeqc.png",
    "Quantinuum": "quantinuum.png",
}



def department_icon_key(department):
    return DEPARTMENT_ICON_KEYS.get(plain(department).lower(), "content")


def strip_html(value):
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def plain(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return strip_html(value)
    return str(value)


def compact(value, limit=220):
    text = plain(value)
    if len(text) <= limit:
        return text

    def fit_parts(parts, joiner, terminal=""):
        chosen = []
        for part in parts:
            part = part.strip().rstrip(".").rstrip(";").rstrip(",")
            if not part:
                continue
            candidate = joiner.join(chosen + [part])
            if len(candidate) + len(terminal) <= limit:
                chosen.append(part)
            else:
                break
        if chosen:
            return joiner.join(chosen) + terminal
        return ""

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    sentence_fit = fit_parts(sentences, " ")
    if sentence_fit:
        return sentence_fit

    semicolon_parts = [s.strip() for s in text.split(";") if s.strip()]
    semicolon_fit = fit_parts(semicolon_parts, "; ", ".")
    if semicolon_fit:
        return semicolon_fit

    comma_parts = [s.strip() for s in text.split(",") if s.strip()]
    if len(comma_parts) > 1:
        comma_fit = fit_parts(comma_parts, ", ", ".")
        if comma_fit:
            return comma_fit

    words = text.split()
    chosen_words = []
    for word in words:
        candidate = " ".join(chosen_words + [word])
        if len(candidate) <= limit:
            chosen_words.append(word)
        else:
            break
    fallback = " ".join(chosen_words).rstrip(",;:")
    return fallback + ("." if fallback and fallback[-1] not in ".!?" else "")


def numeric_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = plain(value)
    if not text:
        return None
    normalized = re.sub(r"[^0-9.\-]", "", text)
    if not normalized:
        return None
    try:
        return float(normalized)
    except Exception:
        return None


def first_card_body(cards, title_contains="", fallback_index=None):
    usable_cards = cards or []
    needle = plain(title_contains).lower()
    if needle:
        for card in usable_cards:
            title = plain(card.get("title")).lower()
            body = plain(card.get("body"))
            if needle in title and body:
                return body
    if fallback_index is not None and 0 <= fallback_index < len(usable_cards):
        return plain(usable_cards[fallback_index].get("body"))
    for card in usable_cards:
        body = plain(card.get("body"))
        if body:
            return body
    return ""


def first_priority_opportunity(section):
    opportunities = section.get("priority_opportunities") or []
    for item in opportunities:
        text = plain(item)
        if text:
            return text
    return ""


def section_subtitle(section, preferred_fields=None, card_titles=None, fallback_limit=220):
    section = section or {}
    for field in preferred_fields or []:
        value = compact(section.get(field), fallback_limit)
        if value:
            return value
    cards = section.get("cards") or []
    for title in card_titles or []:
        value = compact(first_card_body(cards, title), fallback_limit)
        if value:
            return value
    for card in cards:
        value = compact(card.get("body"), fallback_limit)
        if value:
            return value
    return ""


def claimed_positioning_summary(positioning):
    positioning = positioning or {}
    rows = positioning.get("rows") or []
    parts = []
    for row in rows[:2]:
        claim = plain(row.get("claim_summary"))
        feedback = plain(row.get("proof_feedback"))
        if claim and feedback:
            parts.append(f"{claim} Proof read: {feedback}")
        elif claim:
            parts.append(claim)
        elif feedback:
            parts.append(feedback)
    summary = " ".join(parts).strip()
    if not summary:
        summary = plain(positioning.get("summary", ""))
    return compact(summary, 220)


def competitor_risk_summary(comp):
    status = comp.get("status_summary", []) or []
    parts = []
    for item in status[:3]:
        if isinstance(item, dict):
            title = plain(item.get("title"))
            body = plain(item.get("body"))
            if title and body:
                parts.append(f"{title}: {body}")
            elif body:
                parts.append(body)
            elif title:
                parts.append(title)
            continue
        text = plain(item)
        if text:
            parts.append(text)
    if comp.get("validation_flags"):
        parts.append("Shortlist still needs human validation before client-facing use")

    summary = ". ".join(parts).strip()
    if not summary:
        summary = plain(comp.get("why_each_competitor_matters", ""))
    return compact(summary, 220)


def set_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_shape(slide, shape_type, left, top, width, height, fill, line=None, radius=None):
    shape = slide.shapes.add_shape(shape_type, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line:
        shape.line.color.rgb = line
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    if radius is not None:
        try:
            shape.adjustments[0] = radius
        except Exception:
            pass
    return shape


def add_bar(slide, left, top, width, height, color):
    return add_shape(slide, MSO_AUTO_SHAPE_TYPE.RECTANGLE, left, top, width, height, color)


def add_line(slide, x1, y1, x2, y2, color, width=2.5):
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    line.line.color.rgb = color
    line.line.width = Pt(width)
    return line


def add_textbox(slide, left, top, width, height, paragraphs, fill=None, line=None, rounded=False, valign=MSO_ANCHOR.TOP):
    if fill or line or rounded:
        shape_type = MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE if rounded else MSO_AUTO_SHAPE_TYPE.RECTANGLE
        box = add_shape(slide, shape_type, left, top, width, height, fill or PALETTE["white"], line)
    else:
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        box.fill.background()
        box.line.fill.background()
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = int(0.07 * 914400)
    tf.margin_right = int(0.07 * 914400)
    tf.margin_top = int(0.04 * 914400)
    tf.margin_bottom = int(0.04 * 914400)
    tf.vertical_anchor = valign
    fit_requested = False
    fit_font = "Aptos"
    fit_size = 18
    fit_bold = False
    for idx, spec in enumerate(paragraphs):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = spec["text"]
        p.alignment = spec.get("align", PP_ALIGN.LEFT)
        p.space_after = Pt(spec.get("space_after", 0))
        font = p.font
        font.size = Pt(spec.get("size", 18))
        font.bold = spec.get("bold", False)
        font.color.rgb = spec.get("color", PALETTE["ink"])
        font.name = spec.get("font", "Aptos")
        if spec.get("fit"):
            fit_requested = True
            fit_font = spec.get("font", "Aptos")
            fit_size = spec.get("size", 18)
            fit_bold = spec.get("bold", False)
    if fit_requested:
        try:
            tf.fit_text(font_family=fit_font, max_size=Pt(fit_size), bold=fit_bold)
        except Exception:
            pass
    return box


def add_picture(slide, path, left, top, width=None, height=None):
    path = ensure_pptx_safe_image(path)
    kwargs = {}
    if width is not None:
        kwargs["width"] = Inches(width)
    if height is not None:
        kwargs["height"] = Inches(height)
    return slide.shapes.add_picture(str(path), Inches(left), Inches(top), **kwargs)


def accent_fill(accent):
    return PALETTE["soft_amber"] if accent == "amber" else PALETTE["soft_blue"]


PPTX_SAFE_IMAGE_FORMATS = {"BMP", "GIF", "JPEG", "PNG", "TIFF", "WMF"}
TEMP_IMAGE_DIR = Path(tempfile.gettempdir()) / "newbizintel-pptx-images"


def ensure_pptx_safe_image(path):
    candidate = Path(path)
    if candidate.suffix.lower() != ".png":
        return candidate

    try:
        from PIL import Image
    except Exception:
        return candidate

    try:
        with Image.open(candidate) as img:
            image_format = (img.format or "").upper()
            if image_format in PPTX_SAFE_IMAGE_FORMATS:
                return candidate

            TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            normalized = TEMP_IMAGE_DIR / f"{candidate.stem}.png"
            img.save(normalized, format="PNG")
            return normalized
    except Exception:
        return candidate


def resolve_data_asset(base_dir, value):
    text = plain(value).strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    return candidate if candidate.exists() else None


def safe_slug(value):
    return re.sub(r"[^a-z0-9]+", "-", plain(value).lower()).strip("-")


def fetch_file(url, destination):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = response.read()
        if data:
            destination.write_bytes(data)
            return True
    except Exception:
        return False
    return False


def ensure_assets(asset_dir, data=None):
    asset_dir.mkdir(parents=True, exist_ok=True)

    if not data:
        return

    brand = data.get("brand") or {}
    brand_slug = safe_slug(plain(brand.get("slug")) or plain(brand.get("name")))
    brand_website = plain(brand.get("website"))
    if brand_slug and brand_website:
        target = asset_dir / f"{brand_slug}-favicon.png"
        if not target.exists():
            try:
                parsed = urllib.parse.urlparse(brand_website)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                favicon_url = "https://www.google.com/s2/favicons?sz=128&domain_url=" + urllib.parse.quote(origin, safe='')
                fetch_file(favicon_url, target)
            except Exception:
                pass

    competitors = (data.get("competitive_landscape") or {}).get("table") or []
    for row in competitors:
        competitor = plain(row.get("competitor"))
        website = plain(row.get("website"))
        if not competitor or not website:
            continue

        slug = safe_slug(competitor)
        target = asset_dir / f"{slug}-favicon.png"
        if target.exists():
            continue

        try:
            parsed = urllib.parse.urlparse(website)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            continue

        favicon_url = "https://www.google.com/s2/favicons?sz=128&domain_url=" + urllib.parse.quote(origin, safe='')
        fetch_file(favicon_url, target)

    news_items = (data.get("brand_reputation") or {}).get("influential_news") or []
    for item in news_items:
        source = plain(item.get("source"))
        source_url = plain(item.get("url"))
        if not source or not source_url:
            continue

        slug = safe_slug(source)
        target = asset_dir / f"{slug}-news.png"
        if target.exists():
            continue

        try:
            parsed = urllib.parse.urlparse(source_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            continue

        favicon_url = "https://www.google.com/s2/favicons?sz=128&domain_url=" + urllib.parse.quote(origin, safe='')
        fetch_file(favicon_url, target)


def find_first_existing(asset_dir, names):
    for name in names:
        if not name:
            continue
        path = asset_dir / name
        if path.exists():
            return path
    return None


def resolve_brand_badge_path(asset_dir, brand=None):
    brand = brand or {}
    mark_value = plain(brand.get("mark_url"))
    if mark_value:
        candidate = Path(mark_value)
        if not candidate.is_absolute():
            candidate = asset_dir.parent / mark_value
        if candidate.exists():
            return candidate

    logo_value = plain(brand.get("logo_url"))
    if logo_value:
        candidate = Path(logo_value)
        if not candidate.is_absolute():
            candidate = asset_dir.parent / logo_value
        if candidate.exists() and re.search(r"logo", candidate.name, re.IGNORECASE):
            mark_name = re.sub(r"logo", "mark", candidate.name, flags=re.IGNORECASE)
            mark_candidate = candidate.with_name(mark_name)
            if mark_candidate.exists():
                return mark_candidate

    return None


def header_logo_path(asset_dir, brand_slug=None, brand=None):
    brand = brand or {}
    logo_value = plain(brand.get("logo_url"))
    if logo_value:
        candidate = Path(logo_value)
        if not candidate.is_absolute():
            candidate = asset_dir.parent / logo_value
        if candidate.exists():
            return candidate

    candidates = []
    if brand_slug:
        candidates.extend([
            f"{brand_slug}-logo.png",
            f"{brand_slug}-mark.png",
            f"{brand_slug}-news.png",
            f"{brand_slug}.png",
            f"{brand_slug}-favicon.png",
        ])
    candidates.extend(["logo.png", "mark.png", "news.png", "favicon.png"])
    found = find_first_existing(asset_dir, candidates)
    if found:
        return found
    pngs = sorted(asset_dir.glob("*logo*.png")) + sorted(asset_dir.glob("*mark*.png")) + sorted(asset_dir.glob("*favicon*.png")) + sorted(asset_dir.glob("*.png"))
    return pngs[0] if pngs else None


def section_icon_asset(asset_dir, key):
    return find_first_existing(asset_dir, [SECTION_MARKERS.get(key, "")])


def pptx_safe_logo_candidate(asset_dir, value):
    candidate = resolve_data_asset(asset_dir.parent, value)
    if not candidate:
        return None
    if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".wmf"}:
        return candidate
    if candidate.suffix.lower() == ".svg":
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            companion = candidate.with_suffix(suffix)
            if companion.exists():
                return companion
    return None


def competitor_logo_path(asset_dir, competitor):
    row = competitor if isinstance(competitor, dict) else {}
    competitor_name = plain(row.get("competitor") or row.get("name")) if row else plain(competitor)
    for field in ("logo_url", "competitor_logo_url", "badge_url", "mark_url"):
        safe_candidate = pptx_safe_logo_candidate(asset_dir, row.get(field)) if row else None
        if safe_candidate:
            return safe_candidate

    generic = re.sub(r"[^a-z0-9]+", "-", competitor_name.lower()).strip("-")
    candidates = [
        COMPETITOR_LOGOS.get(competitor_name, ""),
        f"{generic}-favicon.png",
        f"{generic}-logo.png",
        f"{generic}.png",
    ]
    return find_first_existing(asset_dir, candidates)


def news_source_logo_path(asset_dir, item, brand=None):
    item = item or {}
    source = plain(item.get("source"))
    source_url = plain(item.get("url"))

    explicit_logo = plain(item.get("publisher_logo_url")) or plain(item.get("source_logo_url")) or plain(item.get("logo_url"))
    if explicit_logo:
        candidate = Path(explicit_logo)
        if candidate.exists():
            return candidate
        candidate = asset_dir / explicit_logo
        if candidate.exists():
            return candidate

    if source and brand and plain(brand.get("name")).lower() == source.lower():
        badge = resolve_brand_badge_path(asset_dir, brand)
        if badge:
            return badge

    slug = safe_slug(source)
    candidates = [
        f"{slug}-news.png" if slug else "",
        f"{slug}-favicon.png" if slug else "",
        f"{slug}-logo.png" if slug else "",
        f"{slug}.png" if slug else "",
    ]
    found = find_first_existing(asset_dir, candidates)
    if found:
        return found

    if source_url:
        try:
            parsed = urllib.parse.urlparse(source_url)
            host_slug = safe_slug(parsed.netloc.replace("www.", ""))
            found = find_first_existing(asset_dir, [
                f"{host_slug}-news.png",
                f"{host_slug}-favicon.png",
                f"{host_slug}-logo.png",
                f"{host_slug}.png",
            ])
            if found:
                return found
        except Exception:
            pass

    return None


def add_header_badge(slide, left, top, width, height, brand_name, asset_dir, brand_slug=None, brand=None):
    add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, width, height, PALETTE["white"], PALETTE["white"])
    logo = resolve_brand_badge_path(asset_dir, brand)
    if logo:
        logo_size = min(width * 0.78, height * 0.78)
        add_picture(slide, logo, left + ((width - logo_size) / 2), top + ((height - logo_size) / 2), width=logo_size, height=logo_size)
        return
    add_textbox(
        slide,
        left + 0.14,
        top + 0.19,
        width - 0.28,
        height - 0.38,
        [{
            "text": brand_name,
            "size": 16,
            "bold": True,
            "color": PALETTE["navy"],
            "align": PP_ALIGN.CENTER,
            "fit": True,
        }],
    )


def add_section_icon(slide, asset_dir, key, left, top, width, height, color):
    icon_path = section_icon_asset(asset_dir, key)
    if icon_path:
        add_picture(slide, icon_path, left, top, width=width, height=height)
        return

    if key == "snapshot":
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.RECTANGLE, left + 0.04, top + 0.16, 0.05, 0.16, color)
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.RECTANGLE, left + 0.14, top + 0.09, 0.05, 0.23, color)
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.RECTANGLE, left + 0.24, top + 0.04, 0.05, 0.28, color)
        return
    if key == "executive":
        for y in (0.02, 0.14, 0.26):
            add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, left + 0.01, top + y, 0.05, 0.05, color)
            add_line(slide, left + 0.08, top + y + 0.025, left + 0.30, top + y + 0.025, color, width=2.2)
        return
    if key == "messaging":
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left + 0.02, top + 0.02, 0.27, 0.20, PALETTE["white"], color)
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ISOSCELES_TRIANGLE, left + 0.08, top + 0.17, 0.08, 0.08, color)
        return
    if key == "competitors":
        pts = [(0.04, 0.15), (0.15, 0.04), (0.26, 0.15), (0.15, 0.26)]
        for px, py in pts:
            add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, left + px, top + py, 0.06, 0.06, PALETTE["white"], color)
        add_line(slide, left + 0.10, top + 0.18, left + 0.18, top + 0.10, color, width=2.0)
        add_line(slide, left + 0.24, top + 0.10, left + 0.32, top + 0.18, color, width=2.0)
        add_line(slide, left + 0.10, top + 0.18, left + 0.18, top + 0.26, color, width=2.0)
        add_line(slide, left + 0.24, top + 0.26, left + 0.32, top + 0.18, color, width=2.0)
        return
    if key == "seo":
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, left + 0.02, top + 0.02, 0.22, 0.22, PALETTE["white"], color)
        add_line(slide, left + 0.21, top + 0.21, left + 0.31, top + 0.31, color, width=2.6)
        return
    if key == "reputation":
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.HEXAGON, left + 0.03, top + 0.03, 0.28, 0.28, PALETTE["white"], color)
        add_line(slide, left + 0.10, top + 0.18, left + 0.15, top + 0.23, color, width=2.6)
        add_line(slide, left + 0.15, top + 0.23, left + 0.24, top + 0.12, color, width=2.6)
        return
    if key == "content":
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left + 0.06, top + 0.02, 0.23, 0.28, PALETTE["white"], color)
        for y in (0.09, 0.15, 0.21):
            add_line(slide, left + 0.11, top + y, left + 0.25, top + y, color, width=2.0)
        return
    if key == "roadmap":
        add_line(slide, left + 0.03, top + 0.25, left + 0.12, top + 0.16, color, width=2.2)
        add_line(slide, left + 0.12, top + 0.16, left + 0.20, top + 0.22, color, width=2.2)
        add_line(slide, left + 0.20, top + 0.22, left + 0.31, top + 0.08, color, width=2.2)
        add_line(slide, left + 0.24, top + 0.08, left + 0.31, top + 0.08, color, width=2.2)
        add_line(slide, left + 0.31, top + 0.08, left + 0.31, top + 0.15, color, width=2.2)
        return
    if key == "closing":
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, left + 0.03, top + 0.03, 0.28, 0.28, PALETTE["white"], color)
        add_line(slide, left + 0.10, top + 0.18, left + 0.15, top + 0.23, color, width=2.6)
        add_line(slide, left + 0.15, top + 0.23, left + 0.25, top + 0.11, color, width=2.6)
        return


def base_slide(prs, brand_name, brand_slug, asset_dir, title, subtitle=None, accent="teal", icon_key=None, brand=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, PALETTE["white"])
    add_bar(slide, 0, 0, 13.333, 0.68, PALETTE["navy"])
    header_brand = brand or {"name": brand_name, "slug": brand_slug}
    add_header_badge(slide, 11.87, 0.11, 0.78, 0.46, brand_name, asset_dir, brand_slug, header_brand)
    add_textbox(slide, 0.9, 0.16, 10.6, 0.42, [{"text": title, "size": 28, "bold": True, "color": PALETTE["white"], "font": "Aptos Display"}])
    if icon_key:
        add_section_icon(slide, asset_dir, icon_key, 0.48, 0.95, 0.34, 0.34, PALETTE[accent])
    if subtitle:
        add_textbox(slide, 0.76, 0.90, 10.7, 0.6, [{"text": subtitle, "size": 15, "color": PALETTE["muted"]}])
    add_bar(slide, 0.76, 1.67, 2.95, 0.05, PALETTE[accent])
    return slide


def add_bullet_rows(slide, items, accent="teal", left=0.96, top=2.02, width=11.0, row_height=0.94, gap=0.14, text_size=17.0, bottom=6.92):
    usable_items = [item for item in items if item]
    if not usable_items:
        return
    available_height = max(0.6, bottom - top - (gap * max(0, len(usable_items) - 1)))
    effective_row_height = max(0.52, available_height / len(usable_items))
    y = top
    for item in usable_items:
        lead, body = item if isinstance(item, tuple) else (None, item)
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, y, width, effective_row_height, accent_fill(accent), PALETTE["line"])
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, left + 0.16, y + 0.20, 0.10, 0.10, PALETTE[accent])
        paragraphs = []
        if lead:
            paragraphs.append({
                "text": plain(lead),
                "size": max(10.5, text_size - 0.4),
                "bold": True,
                "color": PALETTE["navy"],
                "font": "Aptos Display",
                "space_after": 1.5,
                "fit": True,
            })
        if plain(body):
            paragraphs.append({
                "text": plain(body),
                "size": max(10.0, text_size - 1.4 if lead else text_size),
                "color": PALETTE["ink"],
                "fit": True,
            })
        if not paragraphs:
            paragraphs.append({"text": "", "size": text_size, "color": PALETTE["ink"]})
        add_textbox(slide, left + 0.36, y + 0.06, width - 0.46, effective_row_height - 0.1, paragraphs)
        y += effective_row_height + gap


def add_compact_bar_chart(slide, chart, left, top, width, height, accent="blue"):
    title = plain(chart.get("title")) or "Chart"
    subtitle = compact(chart.get("subtitle"), 110)
    series = [item for item in (chart.get("series") or []) if plain(item.get("label"))]
    parsed = []
    for item in series[:5]:
        value = numeric_value(item.get("value"))
        if value is None:
            continue
        parsed.append((item, value))
    if not parsed:
        return

    max_value = max(value for _, value in parsed) or 1.0
    suffix = plain(chart.get("value_suffix"))

    add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, width, height, PALETTE["white"], PALETTE["line"])
    add_textbox(slide, left + 0.22, top + 0.18, width - 0.44, 0.32, [{
        "text": title,
        "size": 16,
        "bold": True,
        "color": PALETTE["navy"],
        "font": "Aptos Display",
        "fit": True,
    }])
    if subtitle:
        add_textbox(slide, left + 0.22, top + 0.48, width - 0.44, 0.34, [{
            "text": subtitle,
            "size": 10.4,
            "color": PALETTE["muted"],
            "fit": True,
        }])

    row_top = top + 0.98
    row_gap = 0.42
    track_left = left + 1.88
    track_width = width - 2.58
    for idx, (item, value) in enumerate(parsed[:5]):
        y = row_top + (idx * row_gap)
        label = compact(item.get("label"), 24)
        display_value = plain(item.get("display_value"))
        if not display_value:
            display_value = f"{int(value) if float(value).is_integer() else round(value, 1)}{suffix}"
        note = compact(item.get("note"), 44)
        tone = plain(item.get("tone")).lower()
        color = PALETTE["teal"] if tone == "teal" else (PALETTE["amber"] if tone in {"amber", "warn"} else PALETTE[accent])

        add_textbox(slide, left + 0.22, y - 0.03, 1.48, 0.18, [{
            "text": label,
            "size": 10.5,
            "bold": True,
            "color": PALETTE["ink"],
            "fit": True,
        }])
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, track_left, y, track_width, 0.12, PALETTE["line"], PALETTE["line"])
        fill_width = max(0.14, track_width * max(0.0, value) / max_value)
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, track_left, y, fill_width, 0.12, color, color)
        add_textbox(slide, left + width - 0.56, y - 0.05, 0.36, 0.18, [{
            "text": display_value,
            "size": 10.5,
            "bold": True,
            "color": PALETTE["ink"],
            "align": PP_ALIGN.RIGHT,
            "fit": True,
        }])
        if note:
            add_textbox(slide, track_left, y + 0.10, track_width, 0.16, [{
                "text": note,
                "size": 8.5,
                "color": PALETTE["muted"],
                "fit": True,
            }])


def build_chart_slides(prs, data, asset_dir, section_title, charts, accent, icon_key):
    usable = []
    for chart in charts or []:
        if plain(chart.get("title")) and any(numeric_value(item.get("value")) is not None for item in (chart.get("series") or [])):
            usable.append(chart)
    if not usable:
        return

    for start in range(0, len(usable), 2):
        chunk = usable[start:start + 2]
        slide = base_slide(
            prs,
            data["brand"]["name"],
            data["brand"].get("slug"),
            asset_dir,
            f"{section_title} Charts",
            "Selected visual comparisons added where the evidence was strong enough to support a chart.",
            accent=accent,
            icon_key=icon_key,
            brand=data["brand"],
        )
        positions = [(0.82, 1.95, 5.76, 3.36), (6.76, 1.95, 5.76, 3.36)]
        for chart, (left, top, width, height) in zip(chunk, positions):
            add_compact_bar_chart(slide, chart, left, top, width, height, accent=accent)


def build_title_slide(prs, data, asset_dir):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, PALETTE["navy"])
    brand = data["brand"]
    cover = data["cover"]
    add_header_badge(slide, 0.78, 0.84, 0.98, 0.98, brand["name"], asset_dir, brand.get("slug"), brand)
    add_bar(slide, 1.95, 1.05, 2.7, 0.08, PALETTE["teal"])
    add_textbox(slide, 1.95, 1.28, 9.7, 0.8, [{"text": f"{brand['name']} New-Business Intelligence", "size": 30, "bold": True, "color": PALETTE["white"], "font": "Aptos Display"}])
    add_textbox(slide, 1.95, 2.16, 9.9, 1.0, [{"text": compact(cover["summary"], 240), "size": 18, "color": PALETTE["white"]}])
    add_textbox(slide, 1.95, 3.52, 4.45, 1.18, [
        {"text": "Focus", "size": 14, "bold": True, "color": PALETTE["teal"]},
        {"text": compact(cover.get("scope", ""), 120), "size": 13, "color": PALETTE["white"]},
    ], fill=PALETTE["blue"], rounded=True)
    add_textbox(slide, 6.62, 3.52, 4.55, 1.18, [
        {"text": "Competitive set", "size": 14, "bold": True, "color": PALETTE["teal"]},
        {"text": ", ".join(cover.get("competitors", [])[:4]), "size": 13, "color": PALETTE["white"]},
    ], fill=PALETTE["blue"], rounded=True)
    report_meta = data.get("report_meta") or {}
    add_textbox(slide, 1.95, 5.02, 9.9, 0.28, [{"text": compact(plain(report_meta.get("note")), 140), "size": 10.5, "color": RGBColor(0xD9, 0xE7, 0xF1)}])
    add_textbox(slide, 1.95, 5.34, 9.9, 0.35, [{"text": f"{brand.get('website', '')} | Report date: {brand.get('date', '')} | {plain(report_meta.get('distribution'))}", "size": 11, "color": RGBColor(0xD9, 0xE7, 0xF1)}])


def build_snapshot_slide(prs, data, asset_dir):
    snapshot = data["company_snapshot"]
    items = {item["label"]: plain(item["value"]) for item in snapshot["items"]}
    subtitle = compact(snapshot.get("summary", ""), 220)
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Company Snapshot", subtitle, accent="teal", icon_key="snapshot", brand=data["brand"])
    bullets = [
        ("Sector", items.get("Sector", "")),
        ("Core proposition", items.get("Core proposition", "")),
        ("Headquarters", items.get("Headquarters", "")),
        ("Funding", items.get("Funding status", "")),
    ]
    add_bullet_rows(slide, bullets, accent="teal")


def build_exec_slide(prs, data, asset_dir):
    executive = data["executive_summary"]
    summary = section_subtitle(
        executive,
        preferred_fields=["overall_recommendation"],
        card_titles=["what stands out", "biggest commercial risk", "biggest messaging opportunity"],
        fallback_limit=195,
    )
    if not summary:
        summary = claimed_positioning_summary(executive)
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Executive Summary", summary, accent="amber", icon_key="executive", brand=data["brand"])
    bullets = [(card["title"], compact(card["body"], 175)) for card in executive["cards"][:4]]
    add_bullet_rows(slide, bullets, accent="amber")


def build_agency_opportunity_slide(prs, data, asset_dir):
    agency = data.get("agency_opportunity") or {}
    cards = agency.get("cards") or []
    workstreams = agency.get("priority_workstreams") or []
    departments = agency.get("department_opportunity_map") or []
    lead = agency.get("lead_offering") or {}
    summary = plain(lead.get("verdict")) or plain(agency.get("score_summary")) or compact(agency.get("summary"), 220)
    if not cards and not workstreams and not departments and not plain(agency.get("summary")) and not plain(agency.get("score")) and not plain(lead.get("name")):
        return
    subtitle = f"Archetype fit score: {plain(agency.get('score'))}" if plain(agency.get("score")) else compact(summary, 220)
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Archetype Opportunity", compact(subtitle, 220), accent="blue", icon_key="content", brand=data["brand"])

    tone_fill = {"good": RGBColor(0xE8, 0xF7, 0xEE), "warn": RGBColor(0xFF, 0xF3, 0xDD), "bad": RGBColor(0xFD, 0xEC, 0xEC)}
    tone_dot = {"good": RGBColor(0x16, 0x65, 0x34), "warn": RGBColor(0x9A, 0x67, 0x00), "bad": RGBColor(0xB4, 0x23, 0x18)}
    lead_department = plain(lead.get("lead_department"))
    support_departments = [plain(item) for item in (lead.get("supporting_departments") or []) if plain(item)]
    why_this_leads = [plain(item) for item in (lead.get("why_this_leads") or []) if plain(item)]
    why_not_first = [plain(item) for item in (lead.get("why_not_first") or []) if plain(item)]
    expected_outcomes = [plain(item) for item in (lead.get("expected_outcomes") or []) if plain(item)]

    add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, 0.78, 1.82, 5.2, 3.42, PALETTE["white"], PALETTE["line"])
    add_bar(slide, 0.78, 1.82, 0.12, 3.42, PALETTE["teal"])
    add_textbox(slide, 1.05, 2.02, 2.2, 0.28, [
        {"text": "RECOMMENDED LEAD OFFERING", "size": 10.5, "bold": True, "color": PALETTE["muted"], "font": "Aptos"},
    ])
    lead_title = plain(lead.get("name"))
    if not lead_title and len(cards) > 1:
        lead_title = plain(cards[1].get("body"))
    if not lead_title:
        lead_title = "Positioning-led engagement"
    add_textbox(slide, 1.05, 2.28, 4.5, 0.84, [
        {"text": lead_title, "size": 20.5, "bold": True, "color": PALETTE["navy"], "font": "Aptos Display", "fit": True},
    ])
    lead_meta = f"Lead department: {lead_department}" if lead_department else ""
    if support_departments:
        lead_meta = f"{lead_meta} | Support: {', '.join(support_departments[:3])}" if lead_meta else f"Support: {', '.join(support_departments[:3])}"
    if lead_meta:
        add_section_icon(slide, asset_dir, department_icon_key(lead_department), 1.05, 3.09, 0.18, 0.18, PALETTE["teal"])
        add_textbox(slide, 1.27, 3.03, 4.18, 0.44, [
            {"text": lead_meta, "size": 10.8, "bold": True, "color": PALETTE["teal"], "fit": True},
        ])
    add_textbox(slide, 1.05, 3.56, 4.5, 1.14, [
        {"text": compact(summary, 250), "size": 13.6, "color": PALETTE["ink"], "fit": True},
    ])
    outcome_text = compact(expected_outcomes[0], 120) if expected_outcomes else compact(workstreams[0], 120) if workstreams else ""
    if outcome_text:
        add_textbox(slide, 1.05, 4.66, 4.45, 0.42, [
            {"text": f"Expected outcome: {outcome_text}", "size": 10.3, "bold": True, "color": PALETTE["blue"], "fit": True},
        ], fill=PALETTE["soft_blue"], line=PALETTE["line"], rounded=True, valign=MSO_ANCHOR.MIDDLE)

    def draw_department_cards(target_slide, items, start_top=1.92):
        card_width = 3.05
        card_height = 0.84
        lefts = [6.22, 9.46]
        tops = [start_top, start_top + 0.98, start_top + 1.96]
        for idx, item in enumerate(items[:6]):
            left = lefts[idx % 2]
            top = tops[idx // 2]
            tone = plain(item.get("tone")).lower() or "warn"
            fill = tone_fill.get(tone, tone_fill["warn"])
            dot = tone_dot.get(tone, tone_dot["warn"])
            if plain(item.get("department")) == lead_department:
                fill = PALETTE["soft_blue"]
                dot = PALETTE["navy"]
            third_line = compact(item.get("opportunity_signal") or item.get("rationale"), 64)
            add_shape(target_slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, card_width, card_height, fill, PALETTE["line"])
            add_textbox(target_slide, left + 0.56, top + 0.06, card_width - 0.68, card_height - 0.12, [
                {"text": plain(item.get("department")), "size": 13.2, "bold": True, "color": PALETTE["navy"], "font": "Aptos Display", "fit": True},
                {"text": third_line, "size": 9.5, "color": PALETTE["ink"], "fit": True},
            ])
            add_shape(target_slide, MSO_AUTO_SHAPE_TYPE.OVAL, left + 0.18, top + 0.19, 0.12, 0.12, dot)
            add_shape(target_slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left + 0.17, top + 0.33, 0.28, 0.28, PALETTE["white"], PALETTE["line"])
            add_section_icon(target_slide, asset_dir, department_icon_key(item.get("department")), left + 0.205, top + 0.365, 0.20, 0.20, dot)

    primary_departments = departments[:3] if len(departments) > 4 else departments[:4]
    overflow_departments = departments[3:] if len(departments) > 4 else departments[4:]
    draw_department_cards(slide, primary_departments)

    bullets = []
    if why_this_leads:
        bullets.append(("Why this leads", compact(why_this_leads[0], 165)))
    if why_not_first:
        bullets.append(("Do not lead with", compact(why_not_first[0], 165)))
    if workstreams:
        bullets.append(("Priority workstream", compact(workstreams[0], 165)))
    if cards:
        bullets.append((plain(cards[2].get("title")) if len(cards) > 2 else plain(cards[0].get("title")), compact((cards[2].get("body") if len(cards) > 2 else cards[0].get("body")), 165)))
    add_bullet_rows(slide, bullets[:2] if overflow_departments else bullets[:4], accent="blue", top=5.08, row_height=0.54, gap=0.08, text_size=12.0)

    if overflow_departments:
        overflow_subtitle = "Department fit and supporting workstreams split out for readability."
        overflow_slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Archetype Opportunity: Department Fit", overflow_subtitle, accent="blue", icon_key="content", brand=data["brand"])
        draw_department_cards(overflow_slide, overflow_departments, start_top=1.84)
        overflow_bullets = []
        for idx, workstream in enumerate(workstreams[1:3], start=1):
            overflow_bullets.append((f"Priority workstream {idx + 1}", compact(workstream, 170)))
        for advantage in agency.get("archetype_advantages") or []:
            if len(overflow_bullets) >= 4:
                break
            overflow_bullets.append(("Why the fit is strong", compact(advantage, 170)))
        if not overflow_bullets and cards:
            overflow_bullets.append(("Highest-value contribution", compact(cards[2].get("body") if len(cards) > 2 else cards[0].get("body"), 170)))
        add_bullet_rows(overflow_slide, overflow_bullets[:3], accent="blue", top=5.02, row_height=0.58, gap=0.08, text_size=11.8)


def build_exec_claims_slide(prs, data, asset_dir):
    positioning = data.get("usp_ksp_review") or {}
    rows = positioning.get("rows") or []
    verdict = positioning.get("overall_verdict") or {}
    score = plain(positioning.get("score"))
    score_summary = plain(positioning.get("score_summary"))
    if not rows and not plain(positioning.get("summary")) and not plain(verdict.get("headline")) and not score and not score_summary:
        return

    subtitle = plain(verdict.get("headline")) or compact(positioning.get("summary"), 220)
    slide = base_slide(
        prs,
        data["brand"]["name"],
        data["brand"].get("slug"),
        asset_dir,
        "USP and KSP Review",
        compact(subtitle, 220),
        accent="amber",
        icon_key="executive",
        brand=data["brand"],
    )
    bullets = []
    if score or score_summary:
        score_body = score
        if score_summary:
            score_body = f"{score_body}: {score_summary}" if score_body else score_summary
        bullets.append(("USP and KSP score", compact(score_body, 165)))
    if plain(verdict.get("uniqueness_verdict")):
        bullets.append(("Unique enough?", compact(verdict.get("uniqueness_verdict"), 165)))
    if plain(verdict.get("who_for")):
        bullets.append(("Best fit", compact(verdict.get("who_for"), 165)))
    for row in rows[:2]:
        label = plain(row.get("claim_type")) or "Claim"
        claim = compact(row.get("claim_summary"), 64)
        feedback = compact(row.get("proof_feedback"), 82)
        body = claim
        if feedback:
            body = f"{claim} Proof read: {feedback}" if claim else feedback
        bullets.append((label, compact(body, 165)))
    if not bullets and plain(positioning.get("summary")):
        bullets.append(("Claim review", compact(positioning.get("summary"), 165)))
    add_bullet_rows(slide, bullets[:4], accent="amber", row_height=0.88, text_size=14.0)


def build_storybrand_slide(prs, data, asset_dir):
    storybrand = data["storybrand"]
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Messaging", f"Messaging score: {storybrand['score']}", accent="teal", icon_key="messaging", brand=data["brand"])
    existing = storybrand.get("existing_messaging_assessment") or {}
    bullets = [
        ("Published messaging", compact(existing.get("summary"), 185)),
        ("Reputation read-across", compact(existing.get("reputation_read_across"), 185)),
        ("Messaging score", compact(storybrand["score_summary"], 185)),
        ("One-liner", compact(storybrand["one_liner"], 190)),
    ]
    for fix in storybrand["messaging_fixes"][:2]:
        bullets.append(("Priority fix", compact(fix, 175)))
    add_bullet_rows(slide, bullets, accent="teal")


def build_competitor_slide(prs, data, asset_dir):
    comp = data["competitive_landscape"]
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Competitive Landscape", competitor_risk_summary(comp), accent="blue", icon_key="competitors", brand=data["brand"])
    x = 0.98
    rows = comp["table"][:5]
    for row in rows:
        visible_name = plain(row.get("display_name") or row.get("competitor"))
        monogram_source = plain(row.get("competitor") or visible_name)
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, 1.86, 0.52, 0.52, PALETTE["white"], PALETTE["line"])
        logo_file = competitor_logo_path(asset_dir, row)
        if logo_file:
            add_picture(slide, logo_file, x + 0.11, 1.97, width=0.3, height=0.3)
        else:
            add_textbox(slide, x + 0.06, 2.00, 0.40, 0.18, [{"text": monogram_source[:2].upper(), "size": 9, "bold": True, "color": PALETTE["blue"], "align": PP_ALIGN.CENTER}])
        x += 0.68
    bullets = [(plain(row.get("display_name") or row.get("competitor")), compact(row["implication"], 175)) for row in rows]
    if comp.get("validation_flags"):
        bullets = bullets[:3] + [("Validation", "Shortlist is still ambiguous, so treat benchmark names as directional until a human confirms the direct competitors.")]
    add_bullet_rows(slide, bullets[:5], accent="blue", top=2.48, row_height=0.68, text_size=13.6)


def build_seo_slide(prs, data, asset_dir):
    seo = data["seo_audit"]
    semrush_evidence = seo.get("semrush_evidence") or []
    subtitle = section_subtitle(
        seo,
        card_titles=["biggest seo opportunity", "search intent", "page positioning"],
    )
    if not subtitle:
        first_issue = (seo.get("priority_issues") or [{}])[0]
        subtitle = compact(first_issue.get("why_it_matters") or first_issue.get("recommended_fix"), 220)
    if not subtitle:
        subtitle = "SEO opportunity is strongest where page purpose, decision-stage clarity, and conversion support are weakest."
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "SEO Priorities", subtitle, accent="teal", icon_key="seo", brand=data["brand"])
    bullets = []
    for item in semrush_evidence[:2]:
        title = plain(item.get("title")) or "SEMrush evidence"
        body = compact(item.get("body"), 118)
        if body:
            bullets.append((title, body))
    for issue in data["seo_audit"]["priority_issues"]:
        label = plain(issue.get("issue"))
        body = compact(issue.get("recommended_fix"), 118)
        if label and body:
            bullets.append((label, body))
        if len(bullets) >= 4:
            break
    add_bullet_rows(slide, bullets, accent="teal", row_height=0.82, text_size=15.0)


def build_reputation_slide(prs, data, asset_dir):
    rep = data["brand_reputation"]
    subtitle = section_subtitle(
        rep,
        card_titles=["positive", "negative", "trust", "risk"],
    )
    if not subtitle:
        subtitle = compact(" ".join(plain(item.get("label")) for item in rep.get("pills", [])[:3]), 220)
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Reputation Signals", subtitle, accent="amber", icon_key="reputation", brand=data["brand"])
    pill_specs = [(6.72, 1.68, 2.02, 0.92), (8.87, 1.68, 2.02, 0.92), (11.02, 1.68, 2.02, 0.92)]
    for idx, pill in enumerate(rep.get("pills", [])[:3]):
        tone = pill.get("tone", "warn")
        fill = PALETTE["soft_amber"] if tone == "warn" else PALETTE["soft_blue"]
        text_color = PALETTE["amber"] if tone == "warn" else PALETTE["teal"]
        left, top, width, height = pill_specs[idx]
        pill_label = compact(pill.get("label", ""), 54)
        add_textbox(
            slide,
            left,
            top,
            width,
            height,
            [{"text": pill_label, "size": 9.8, "color": text_color, "align": PP_ALIGN.CENTER, "fit": True}],
            fill=fill,
            line=PALETTE["line"],
            rounded=True,
            valign=MSO_ANCHOR.MIDDLE,
        )

    news_items = rep.get("influential_news", [])[:4]
    source_items = []
    seen_sources = set()
    for item in news_items:
        source = plain(item.get("source"))
        if not source:
            continue
        key = source.lower()
        if key in seen_sources:
            continue
        seen_sources.add(key)
        source_items.append(item)

    if source_items:
        add_textbox(slide, 0.98, 2.02, 2.2, 0.24, [
            {"text": "RECENT NEWS SOURCES", "size": 10.0, "bold": True, "color": PALETTE["muted"], "font": "Aptos"},
        ])
        x = 0.98
        for item in source_items[:4]:
            add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, 2.24, 0.52, 0.52, PALETTE["white"], PALETTE["line"])
            logo_file = news_source_logo_path(asset_dir, item, data["brand"])
            if logo_file:
                add_picture(slide, logo_file, x + 0.11, 2.35, width=0.30, height=0.30)
            else:
                source = plain(item.get("source"))
                fallback = source[:2].upper() if source else "NS"
                add_textbox(slide, x + 0.06, 2.38, 0.40, 0.18, [{"text": fallback, "size": 9, "bold": True, "color": PALETTE["amber"], "align": PP_ALIGN.CENTER}])
            x += 0.68

    platform_points = []
    for item in rep.get("platform_readout", [])[:2]:
        if isinstance(item, dict):
            platform_points.append(plain(item.get("summary")) or plain(item.get("readout")))
        else:
            platform_points.append(plain(item))
    bullets = [
        (plain(rep["cards"][1]["title"]), compact(rep["cards"][1]["body"], 150)),
        (plain(rep["cards"][3]["title"]), compact(rep["cards"][3]["body"], 150)),
        ("Platform readout", compact(" ".join(item for item in platform_points if item), 150)),
        ("Recent stories matter", compact(" ".join(item.get("why_it_matters", "") for item in rep.get("influential_news", [])[:2]), 150)),
    ]
    add_bullet_rows(slide, bullets, accent="amber", top=3.28, row_height=0.86, gap=0.14, text_size=13.6)


def build_content_slide(prs, data, asset_dir):
    strategy = data["content_strategy"]
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Content Strategy", compact(strategy["response_to_findings"], 220), accent="teal", icon_key="content", brand=data["brand"])
    priority_move = first_priority_opportunity(strategy) or strategy.get("response_to_findings") or first_card_body(strategy.get("cards") or [], fallback_index=0)
    bullets = [
        ("Themes to own", compact(strategy["cards"][0]["body"], 118)),
        ("Best formats", compact(strategy["cards"][1]["body"], 118)),
        ("Audience paths", compact(strategy["cards"][2]["body"], 118)),
        ("Priority move", compact(priority_move, 118)),
    ]
    add_bullet_rows(slide, bullets, accent="teal", row_height=0.8, text_size=14.8)


def build_campaign_slide(prs, data, asset_dir):
    section = data.get("creative_campaign_ideas") or {}
    ideas = section.get("ideas") or []
    usable = [idea for idea in ideas if plain(idea.get("title"))]
    if not usable:
        return

    subtitle = compact(plain(usable[0].get("concept")) or plain(usable[0].get("addresses")) or plain(usable[0].get("intended_effect")), 220)
    if not subtitle:
        subtitle = "Four campaign concepts shaped by the research weak points, proof gaps, and differentiation opportunities."
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "Creative Campaign Ideas", subtitle, accent="amber", icon_key="content", brand=data["brand"])
    card_positions = [
        (0.66, 2.02),
        (6.96, 2.02),
        (0.66, 4.64),
        (6.96, 4.64),
    ]
    fills = [PALETTE["soft_amber"], PALETTE["soft_blue"], PALETTE["soft_blue"], PALETTE["soft_amber"]]
    visual_fills = [
        RGBColor(0xF1, 0xE6, 0xDD),
        RGBColor(0xE7, 0xEE, 0xF2),
        RGBColor(0xE7, 0xEE, 0xE5),
        RGBColor(0xEC, 0xE6, 0xED),
    ]
    data_dir = asset_dir.parent

    for idx, idea in enumerate(usable[:4]):
        left, top = card_positions[idx]
        card_width = 5.72
        card_height = 2.28
        visual_width = 1.46

        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, card_width, card_height, fills[idx], PALETTE["line"])
        add_shape(slide, MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, visual_width, card_height, visual_fills[idx], PALETTE["line"])

        image_path = resolve_data_asset(data_dir, idea.get("illustration_url"))
        if image_path and image_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".wmf"}:
            add_picture(slide, image_path, left + 0.20, top + 0.24, width=1.05, height=1.72)
        else:
            monogram_source = plain(idea.get("title")).strip()
            fallback = "".join(part[:1].upper() for part in monogram_source.split()[:2]) or "CI"
            add_textbox(
                slide,
                left + 0.16,
                top + 0.70,
                1.10,
                0.50,
                [{"text": fallback, "size": 28, "bold": True, "color": PALETTE["muted"], "align": PP_ALIGN.CENTER}],
                valign=MSO_ANCHOR.MIDDLE,
            )

        add_textbox(slide, left + 1.64, top + 0.16, 3.74, 0.26, [
            {"text": "CREATIVE CAMPAIGN IDEA", "size": 8.6, "bold": True, "color": PALETTE["muted"], "font": "Aptos", "fit": True}
        ])
        add_textbox(slide, left + 1.64, top + 0.38, 3.72, 0.34, [
            {"text": compact(idea.get("title"), 44), "size": 16.2, "bold": True, "color": PALETTE["navy"], "font": "Aptos Display", "fit": True}
        ])

        copy_parts = []
        if plain(idea.get("addresses")):
            copy_parts.append(f"Addresses: {compact(idea.get('addresses'), 62)}")
        if plain(idea.get("concept")):
            copy_parts.append(f"Concept: {compact(idea.get('concept'), 74)}")
        if plain(idea.get("activation")):
            copy_parts.append(f"Activation: {compact(idea.get('activation'), 74)}")
        if plain(idea.get("press_angle")):
            copy_parts.append(f"Press angle: {compact(idea.get('press_angle'), 62)}")
        elif plain(idea.get("why_it_fits")):
            copy_parts.append(f"Why it fits: {compact(idea.get('why_it_fits'), 62)}")
        if plain(idea.get("why_it_will_work")):
            copy_parts.append(f"Why it works: {compact(idea.get('why_it_will_work'), 62)}")
        elif plain(idea.get("intended_effect")):
            copy_parts.append(f"Effect: {compact(idea.get('intended_effect'), 52)}")
        add_textbox(slide, left + 1.64, top + 0.76, 3.78, 1.24, [
            {"text": " ".join(copy_parts), "size": 11.3, "color": PALETTE["ink"], "fit": True}
        ])

        channels = [plain(item) for item in (idea.get("channels") or []) if plain(item)]
        if channels:
            add_textbox(slide, left + 1.64, top + 2.00, 3.74, 0.24, [
                {"text": "Channels", "size": 8.4, "bold": True, "color": PALETTE["muted"], "font": "Aptos", "fit": True}
            ])
            add_textbox(slide, left + 2.28, top + 1.97, 3.10, 0.30, [
                {"text": compact(", ".join(channels), 60), "size": 9.2, "color": PALETTE["ink"], "fit": True}
            ])


def build_roadmap_slide(prs, data, asset_dir):
    slide = base_slide(prs, data["brand"]["name"], data["brand"].get("slug"), asset_dir, "30 / 60 / 90 Day Plan", "A practical rollout that turns technical authority into commercial momentum.", accent="blue", icon_key="roadmap", brand=data["brand"])
    blocks = data["opportunities"]["timelines"][:3]
    lefts = [0.66, 4.36, 8.06]
    accents = [PALETTE["teal"], PALETTE["blue"], PALETTE["amber"]]
    fills = [PALETTE["soft_blue"], PALETTE["soft_blue"], PALETTE["soft_amber"]]
    for idx, block in enumerate(blocks):
        add_textbox(slide, lefts[idx], 2.0, 3.02, 3.52, [{"text": block["title"], "size": 16, "bold": True, "color": PALETTE["navy"], "font": "Aptos Display"}], fill=fills[idx], line=PALETTE["line"], rounded=True)
        y = 2.45
        for item in block["items"][:3]:
            add_shape(slide, MSO_AUTO_SHAPE_TYPE.OVAL, lefts[idx] + 0.15, y + 0.07, 0.12, 0.12, accents[idx])
            add_textbox(slide, lefts[idx] + 0.32, y - 0.02, 2.45, 0.56, [{"text": compact(item, 62), "size": 12.0, "color": PALETTE["ink"], "fit": True}])
            y += 0.9


def build_close_slide(prs, data, asset_dir):
    strategy = data.get("content_strategy") or {}
    strategy_cards = strategy.get("cards") or []
    immediate_next_step = first_priority_opportunity(strategy) or first_card_body(strategy_cards, "journey", fallback_index=2)
    closing_subtitle = data["executive_summary"].get("overall_recommendation") or strategy.get("response_to_findings") or immediate_next_step
    slide = base_slide(
        prs,
        data["brand"]["name"],
        data["brand"].get("slug"),
        asset_dir,
        "Closing Takeaways",
        compact(closing_subtitle, 220),
        accent="teal",
        icon_key="closing",
        brand=data["brand"],
    )
    bullets = [
        ("Positioning", compact(first_card_body(data["executive_summary"]["cards"], "messaging", fallback_index=2), 155)),
        ("Growth lever", compact(data["executive_summary"]["cards"][5]["body"], 155)),
        ("Recommendation", compact(data["executive_summary"]["overall_recommendation"], 165)),
        ("Immediate next step", compact(immediate_next_step, 155)),
    ]
    add_bullet_rows(slide, bullets, accent="teal")


def build_deck(data, data_path, output_path):
    asset_dir = Path(data_path).parent / "slide-assets"
    ensure_assets(asset_dir, data)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    build_title_slide(prs, data, asset_dir)
    build_snapshot_slide(prs, data, asset_dir)
    build_exec_slide(prs, data, asset_dir)
    build_agency_opportunity_slide(prs, data, asset_dir)
    build_storybrand_slide(prs, data, asset_dir)
    build_exec_claims_slide(prs, data, asset_dir)
    build_competitor_slide(prs, data, asset_dir)
    build_chart_slides(prs, data, asset_dir, "Competitive Landscape", (data.get("competitive_landscape") or {}).get("charts"), "blue", "competitors")
    build_seo_slide(prs, data, asset_dir)
    build_chart_slides(prs, data, asset_dir, "SEO", (data.get("seo_audit") or {}).get("charts"), "teal", "seo")
    build_reputation_slide(prs, data, asset_dir)
    build_content_slide(prs, data, asset_dir)
    build_campaign_slide(prs, data, asset_dir)
    build_roadmap_slide(prs, data, asset_dir)
    build_close_slide(prs, data, asset_dir)
    prs.save(output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--pptx")
    args = parser.parse_args()
    data_path = os.path.abspath(args.data)
    output_path = os.path.abspath(args.pptx) if args.pptx else os.path.join(os.path.dirname(data_path), "newbizintel-slides.pptx")
    with open(data_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    build_deck(data, data_path, output_path)


if __name__ == "__main__":
    main()


