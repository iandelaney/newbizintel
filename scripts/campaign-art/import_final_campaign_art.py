#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from generate_campaign_illustrations import (
    HEIGHT,
    WIDTH,
    output_path_for_idea,
    relative_asset_path,
    slugify,
)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_GENERATED_IMAGES_DIR = Path.home() / ".codex" / "generated_images"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def get_section(data: dict) -> dict:
    section = data.get("creative_campaign_ideas")
    if isinstance(section, dict):
        return section
    section = data.get("creative_campaigns")
    if isinstance(section, dict):
        return section
    raise SystemExit("creative_campaign_ideas section not found in report data")


def latest_generated_batch(root: Path) -> Path:
    if not root.exists():
        raise SystemExit(f"Generated images directory not found: {root}")
    batches = [item for item in root.iterdir() if item.is_dir()]
    if not batches:
        raise SystemExit(f"No generated image batches found in: {root}")
    return max(batches, key=lambda item: item.stat().st_mtime)


def image_files(root: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda path: path.stat().st_mtime,
    )


def select_source_images(root: Path, needed: int) -> list[Path]:
    files = image_files(root)
    if len(files) < needed:
        raise SystemExit(
            f"Not enough image files in {root}. Needed {needed}, found {len(files)}."
        )
    selected = files[-needed:]
    return sorted(selected, key=lambda path: path.stat().st_mtime)


def normalize_image(source: Path, destination: Path) -> dict[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        elif image.mode == "RGBA":
            image = image.convert("RGB")
        normalized = ImageOps.fit(image, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        normalized.save(destination, format="PNG", optimize=True)
    return {"width": WIDTH, "height": HEIGHT}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import final raster campaign artwork into newbiz2 report data."
    )
    parser.add_argument("--data", required=True, help="Path to report-data.json")
    parser.add_argument("--source-dir", help="Directory containing generated image files")
    parser.add_argument(
        "--latest-generated-batch",
        action="store_true",
        help="Use the latest batch under ~/.codex/generated_images",
    )
    parser.add_argument(
        "--overwrite-final",
        action="store_true",
        help="Allow overwriting ideas already marked as final-raster-artwork",
    )
    args = parser.parse_args()

    data_path = Path(args.data).resolve()
    data = load_json(data_path)
    brand = data.get("brand", {})
    brand_slug = slugify(brand.get("slug") or brand.get("name") or data_path.parent.name)
    asset_dir = data_path.parent / "slide-assets"
    section = get_section(data)
    ideas = list(section.get("ideas") or [])

    target_ideas = []
    for idea in ideas:
        role = str(idea.get("illustration_asset_role") or "").strip().lower()
        if role == "final-raster-artwork" and not args.overwrite_final:
            continue
        target_ideas.append(idea)

    if not target_ideas:
        payload = {
            "data": str(data_path),
            "imported": 0,
            "source_dir": None,
            "files": [],
            "message": "No campaign ideas required import.",
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 0

    source_root: Path
    if args.source_dir:
        source_root = Path(args.source_dir).resolve()
    else:
        source_root = latest_generated_batch(DEFAULT_GENERATED_IMAGES_DIR)

    if args.latest_generated_batch and not args.source_dir:
        source_root = latest_generated_batch(DEFAULT_GENERATED_IMAGES_DIR)

    source_files = select_source_images(source_root, len(target_ideas))
    imported_files: list[str] = []
    imported_titles: list[str] = []

    for idea, source_path in zip(target_ideas, source_files):
        title = (idea.get("title") or "").strip()
        existing_url = idea.get("illustration_url") or ""
        destination = output_path_for_idea(asset_dir, brand_slug, title, existing_url)
        dimensions = normalize_image(source_path, destination)
        idea["illustration_url"] = relative_asset_path(asset_dir, destination)
        idea["illustration_asset_role"] = "final-raster-artwork"
        idea["illustration_generation_backend"] = "imagegen"
        idea["illustration_delivery_target"] = "true-raster-artwork"
        idea["illustration_import_source"] = str(source_path)
        idea["illustration_imported_at"] = datetime.now(timezone.utc).isoformat()
        idea["illustration_dimensions"] = dimensions
        imported_files.append(str(destination))
        imported_titles.append(title)

    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = {
        "data": str(data_path),
        "source_dir": str(source_root),
        "imported": len(imported_files),
        "titles": imported_titles,
        "files": imported_files,
        "overwrite_final": bool(args.overwrite_final),
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
