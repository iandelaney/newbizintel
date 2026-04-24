import argparse
import base64
import json
import mimetypes
import os
import re
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

IMG_TAG_RE = re.compile(r"<img\b[^>]*\bsrc=\"([^\"]+)\"[^>]*>", re.IGNORECASE)
IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")', re.IGNORECASE)
IMG_ALT_RE = re.compile(r'\balt="([^"]*)"', re.IGNORECASE)
IMG_ONERROR_RE = re.compile(r"\s+onerror=\"[^\"]*\"", re.IGNORECASE)
EXTENSIONS = (".png", ".svg", ".webp", ".jpg", ".jpeg", ".gif", ".ico")


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def read_report_data(path: Path) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def to_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def make_svg_badge(label: str) -> str:
    initials = "".join(ch for ch in label if ch.isalnum())[:2].upper() or "NB"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='128' height='128' viewBox='0 0 128 128'>"
        "<rect x='4' y='4' width='120' height='120' rx='24' fill='#f8fafc' stroke='#d1d5db' stroke-width='2'/>"
        f"<text x='64' y='76' text-anchor='middle' font-family='Arial, Helvetica, sans-serif' "
        f"font-size='40' font-weight='700' fill='#243949'>{initials}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def iter_candidate_paths(asset_root: Path, host: str, alt_text: str, report_data: dict):
    brand = report_data.get("brand") or {}
    host_slug = safe_slug(host)
    host_no_www = safe_slug(host.replace("www.", ""))
    alt_slug = safe_slug(alt_text.replace(" logo", "").replace(" icon", ""))

    names = []
    if host_slug:
        for base in {host_slug, host_no_www}:
            if not base:
                continue
            names.extend([f"{base}-news", f"{base}-favicon", f"{base}-logo", f"{base}-mark", base])
    if alt_slug:
        names.extend([f"{alt_slug}-news", f"{alt_slug}-favicon", f"{alt_slug}-logo", f"{alt_slug}-mark", alt_slug])

    if host in {
        urlparse((brand.get("website") or "")).netloc.lower(),
        urlparse((brand.get("primary_website") or "")).netloc.lower(),
    }:
        for key in ("mark_url", "logo_url"):
            value = brand.get(key)
            if value:
                candidate = Path(str(value))
                if not candidate.is_absolute():
                    candidate = asset_root.parent / candidate
                yield candidate

    seen = set()
    for name in names:
        for ext in EXTENSIONS:
            candidate = asset_root / f"{name}{ext}"
            key = str(candidate).lower()
            if key not in seen:
                seen.add(key)
                yield candidate


def resolve_local_asset(src: str, html_dir: Path, report_data: dict, tag: str):
    src = unescape(src)
    if not src or src.startswith("data:"):
        return None

    if src.startswith("file:///"):
        raw = src.replace("file:///", "").replace("/", os.sep).replace("%20", " ")
        candidate = Path(raw)
        return candidate if candidate.exists() else None

    if re.match(r"^[A-Za-z]:\\", src):
        candidate = Path(src)
        return candidate if candidate.exists() else None

    if src.startswith("http://") or src.startswith("https://"):
        parsed = urlparse(src)
        host = parsed.netloc.lower()
        alt_match = IMG_ALT_RE.search(tag)
        alt_text = unescape(alt_match.group(1)) if alt_match else ""

        if "google.com" in host and parsed.path.startswith("/s2/favicons"):
            host = urlparse(unescape((parse_qs(parsed.query).get("domain_url") or [""])[0])).netloc.lower()

        asset_root = html_dir / "slide-assets"
        for candidate in iter_candidate_paths(asset_root, host, alt_text, report_data):
            if candidate.exists():
                return candidate
        return None

    candidate = Path(src)
    if not candidate.is_absolute():
        candidate = html_dir / candidate
    return candidate if candidate.exists() else None


def extract_badge_label(src: str, tag: str) -> str:
    alt_match = IMG_ALT_RE.search(tag)
    if alt_match and alt_match.group(1).strip():
        text = unescape(alt_match.group(1)).strip()
        text = re.sub(r"\b(logo|icon|favicon)\b", "", text, flags=re.IGNORECASE).strip()
        if text:
            return text

    parsed = urlparse(unescape(src))
    host = parsed.netloc or src
    host = host.replace("www.", "")
    if host:
        return host.split(".")[0][:2]
    return "NB"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--data")
    args = parser.parse_args()

    html_path = Path(args.html).resolve()
    output_path = Path(args.output).resolve()
    report_data = read_report_data(Path(args.data).resolve()) if args.data else {}

    text = html_path.read_text(encoding="utf-8", errors="ignore")
    html_dir = html_path.parent

    tag_map = {}
    for match in IMG_TAG_RE.finditer(text):
        tag_map[match.group(1)] = match.group(0)

    def replace_src(match):
        prefix, src, suffix = match.groups()
        tag = tag_map.get(src, "")
        resolved = resolve_local_asset(src, html_dir, report_data, tag)
        if resolved:
            return prefix + to_data_uri(resolved) + suffix
        if src.startswith("data:"):
            return match.group(0)
        return prefix + make_svg_badge(extract_badge_label(src, tag)) + suffix

    standalone = IMG_SRC_RE.sub(replace_src, text)
    standalone = IMG_ONERROR_RE.sub("", standalone)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(standalone, encoding="utf-8")

    remaining_external = len(re.findall(r'<img\b[^>]*\bsrc="https?://', standalone, re.IGNORECASE))
    remaining_file = len(re.findall(r'file:///', standalone, re.IGNORECASE))
    print(json.dumps({
        "html": str(html_path),
        "output": str(output_path),
        "remaining_external_img_refs": remaining_external,
        "remaining_file_refs": remaining_file,
    }))


if __name__ == "__main__":
    main()
