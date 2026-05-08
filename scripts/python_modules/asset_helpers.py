from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from python_modules.common import normalize_url, slugify


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

GENERIC_LOGO_SOURCE_TOKENS = {
    "logo",
    "logos",
    "brand",
    "brands",
    "logotype",
    "wordmark",
    "mark",
    "icon",
    "icons",
    "symbol",
    "glyph",
    "horizontal",
    "vertical",
    "stacked",
    "full",
    "primary",
    "secondary",
    "colour",
    "color",
    "dark",
    "light",
    "black",
    "white",
    "mono",
    "monochrome",
    "transparent",
    "svg",
    "png",
}


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


def tokenise_name(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", (value or "").lower()) if len(token) >= 3]


def source_filename_looks_mismatched(source: str, brand_name: str) -> bool:
    if not source or not brand_name:
        return False
    lower_source = source.lower()
    if "://" not in source and any(
        marker in lower_source
        for marker in (
            "local-raster",
            "local-svg",
            "local-square",
            "brand-logo",
            "reused-local",
            "generated-square-badge",
            "promoted-small-square",
            "replaced-suspicious-brand-logo",
        )
    ):
        return False
    source_path = Path(urllib.parse.urlparse(source).path)
    stem_tokens = [token for token in tokenise_name(source_path.stem) if token not in GENERIC_LOGO_SOURCE_TOKENS]
    if not stem_tokens:
        return False
    brand_tokens = set(tokenise_name(brand_name)) | set(tokenise_name(slugify(brand_name)))
    if not brand_tokens:
        return False
    for token in stem_tokens:
        if any(token == brand_token or token in brand_token or brand_token in token for brand_token in brand_tokens):
            return False
    return True


def suspicious_brand_logo_candidate(path: Path, brand_name: str, source: str) -> bool:
    if not path.exists():
        return True
    if source_filename_looks_mismatched(source, brand_name):
        return True
    if path.suffix.lower() == ".svg" and not svg_asset_contains_term(path, brand_name):
        return True
    return False


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
        request = urllib.request.Request(url, headers={"User-Agent": "newbizintel-python-runner/1.0"})
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
    if not website:
        return []
    try:
        url = normalize_url(website)
        request = urllib.request.Request(url, headers={"User-Agent": "newbizintel-python-runner/1.0"})
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


def promote_small_square_logo(source: Path, destination: Path, canvas_size: int = 256) -> bool:
    if not source.exists() or not quality_ok(source, minimum=16):
        return False
    try:
        from PIL import Image

        with Image.open(source) as image:
            image = image.convert("RGBA")
            if abs(image.width - image.height) > max(2, int(min(image.width, image.height) * 0.08)):
                return False
            image.thumbnail((int(canvas_size * 0.78), int(canvas_size * 0.78)), Image.LANCZOS)
            canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
            x = (canvas_size - image.width) // 2
            y = (canvas_size - image.height) // 2
            canvas.alpha_composite(image, (x, y))
            destination.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(destination, format="PNG", optimize=True)
            return square_quality_ok(destination) and visible_logo_occupancy_ok(destination, minimum_span=0.28)
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


def preferred_loose_square_asset(asset_dir: Path, stem: str) -> Path | None:
    base = re.sub(r"-(logo|mark|favicon)$", "", stem)
    for candidate_stem in (f"{base}-mark", f"{base}-favicon", f"{base}-initial-mark", base, stem):
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"):
            candidate = asset_dir / f"{candidate_stem}{suffix}"
            if candidate.exists() and quality_ok(candidate, minimum=16):
                quality = asset_quality(candidate)
                width = int(quality.get("width") or 0)
                height = int(quality.get("height") or 0)
                if width and height and abs(width - height) <= max(2, int(min(width, height) * 0.08)):
                    return candidate
    return None


def svg_asset_contains_term(path: Path, term: str) -> bool:
    if not path.exists() or path.suffix.lower() != ".svg" or not term:
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False
    return term.lower() in content


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
    elif source_filename_looks_mismatched(source, name):
        entry["ok"] = False
        entry["error"] = f"Primary brand logo source looks mismatched for {name}: {source}"
    elif quality.get("format") != "svg" and (quality.get("width", 0) < 320 or quality.get("height", 0) < 80):
        entry["ok"] = False
        entry["error"] = f"Primary brand logo raster is too small ({quality.get('width')}x{quality.get('height')}); use a dedicated asset at least 320px wide and 80px tall."
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
    brand_host = urllib.parse.urlparse(str(brand.get("website", ""))).netloc.lower().replace("www.", "")
    brand_logo = asset_dir / f"{brand_slug}-logo.svg"
    brand_candidates = discover_site_logo_candidates(str(brand.get("website", "")))
    ok, source = acquire_logo(brand_name, brand.get("website", ""), brand_logo, candidates=brand_candidates, allow_simpleicons=False)
    mark_ok, mark_source = acquire_square_logo(brand_name, brand.get("website", ""), asset_dir, brand_slug)
    if ok:
        brand_asset = None
        source_path = Path(urllib.parse.urlparse(source).path)
        source_suffix = source_path.suffix.lower() if source_path.suffix else ""
        suspicious_exact_brand_asset = False
        if source_suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}:
            exact_brand_asset = asset_dir / f"{brand_slug}-logo{source_suffix}"
            if exact_brand_asset.exists() and quality_ok(exact_brand_asset):
                suspicious_exact_brand_asset = suspicious_brand_logo_candidate(exact_brand_asset, brand_name, source)
                if not suspicious_exact_brand_asset:
                    brand_asset = exact_brand_asset
        pptx_brand_asset = asset_dir / f"{brand_slug}-pptx-logo.png"
        if brand_asset is None and pptx_brand_asset.exists() and quality_ok(pptx_brand_asset, minimum=200):
            brand_asset = pptx_brand_asset
            if suspicious_exact_brand_asset:
                source = "local-raster; replaced-suspicious-brand-logo-with-local-pptx-logo"
        if brand_asset is None:
            brand_asset = preferred_logo_asset(asset_dir, f"{brand_slug}-logo")
        brand["logo_url"] = relative_to_brand(brand_asset, brand_folder) if brand_asset else ""
        mark_asset = preferred_logo_asset(asset_dir, f"{brand_slug}-mark", prefer_square=True) if mark_ok else None
        if not mark_asset:
            loose_square_asset = preferred_loose_square_asset(asset_dir, f"{brand_slug}-mark")
            if loose_square_asset:
                promoted_mark = asset_dir / f"{brand_slug}-mark.png"
                if promote_small_square_logo(loose_square_asset, promoted_mark):
                    mark_asset = promoted_mark
                    mark_source = f"{mark_source or source}; promoted-small-square-brand-mark"
        if not mark_asset and brand_asset:
            derived_mark = asset_dir / f"{brand_slug}-mark.png"
            if create_square_badge_from_logo(brand_asset, derived_mark):
                mark_asset = derived_mark
                mark_source = f"{source}; generated-square-badge-from-brand-logo"
        if not mark_asset and brand_asset and square_quality_ok(brand_asset):
            mark_asset = brand_asset
        brand["mark_url"] = relative_to_brand(mark_asset, brand_folder) if mark_asset else brand["logo_url"]
        if mark_asset:
            brand["mark_resolution_source"] = mark_source or source
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
        source_host = urllib.parse.urlparse(str(source_url)).netloc.lower().replace("www.", "")
        source_type = str(item.get("source_type") or "").strip().lower()
        is_owned_source = source_name.lower().strip() in {
            brand_name.lower().strip(),
            f"{brand_name.lower().strip()} newsroom",
            f"{brand_name.lower().strip()} blog",
            f"{brand_name.lower().strip()} press",
        } or source_type == "owned_newsroom"
        if is_owned_source:
            asset = brand.get("logo_url", "")
            ok = bool(asset)
            resolution = "brand-logo"
            if ok:
                item["source_logo_asset_kind"] = "acquired-or-derived-logo"
        else:
            if source_host and brand_host and source_host == brand_host:
                source_url = ""
            logo_path = asset_dir / f"{slug}-news.svg"
            if (
                logo_path.exists()
                and brand_name
                and brand_name.lower() not in source_name.lower()
                and svg_asset_contains_term(logo_path, brand_name)
            ):
                try:
                    logo_path.unlink()
                except Exception:
                    pass
            ok, resolution = acquire_logo(source_name, source_url, logo_path)
            logo_asset = preferred_logo_asset(asset_dir, f"{slug}-news")
            if not logo_asset:
                logo_asset = preferred_logo_asset(asset_dir, f"{slug}-pptx-logo")
                if logo_asset:
                    ok = True
                    resolution = f"{resolution}; reused-local-pptx-logo"
            asset = relative_to_brand(logo_asset, brand_folder) if ok and logo_asset else ""
            if ok and logo_asset:
                item["source_logo_asset_kind"] = "acquired-or-derived-logo"
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
