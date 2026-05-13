#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


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


def normalize_import_task(source: Path, destination: Path) -> dict[str, object]:
    dimensions = normalize_image(source, destination)
    return {
        "source": str(source),
        "destination": str(destination),
        "dimensions": dimensions,
    }


def portable_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def classify_source_root(source_root: Path, report_root: Path) -> str:
    resolved_source = source_root.resolve()
    resolved_report = report_root.resolve()
    script_root = Path(__file__).resolve().parent
    generated_root = DEFAULT_GENERATED_IMAGES_DIR.resolve()
    try:
        resolved_source.relative_to(generated_root)
        return "generated-images-batch"
    except ValueError:
        pass
    try:
        resolved_source.relative_to(resolved_report)
        return "report-output-local"
    except ValueError:
        pass
    try:
        resolved_source.relative_to(script_root)
        return "skill-local"
    except ValueError:
        pass
    return "external-source-dir"


def load_prompt_manifest(asset_dir: Path, brand_slug: str) -> dict[str, dict[str, str]]:
    manifest_path = asset_dir / f"{brand_slug}-campaign-illustration-prompts.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    prompts = payload.get("ideas", [])
    if not isinstance(prompts, list):
        return {}
    by_title: dict[str, dict[str, str]] = {}
    for item in prompts:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        treatment = str(item.get("treatment") or item.get("medium") or "").strip()
        by_title[title] = {
            "illustration_style_family": str(item.get("style_family") or "").strip(),
            "illustration_style_name": str(item.get("style_slug") or "").strip(),
            "illustration_palette_family": str(item.get("palette_family") or "").strip(),
            "illustration_treatment": treatment,
            "illustration_medium": str(item.get("medium") or "").strip(),
        }
    return by_title


def load_prompt_manifest_payload(asset_dir: Path, brand_slug: str) -> dict:
    manifest_path = asset_dir / f"{brand_slug}-campaign-illustration-prompts.json"
    if not manifest_path.exists():
        raise SystemExit(f"Prompt manifest missing: {manifest_path}")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Could not read prompt manifest {manifest_path}: {exc}") from exc


def validate_strict_batch_manifest(source_root: Path, asset_dir: Path, brand_slug: str, target_ideas: list[tuple[int, dict]]) -> tuple[dict, dict[str, dict[str, str]]]:
    batch_manifest_path = source_root / "campaign-batch-manifest.json"
    if not batch_manifest_path.exists():
        raise SystemExit(
            f"Strict campaign-art import requires {batch_manifest_path}. Copy the generated batch request into the image batch folder before import."
        )
    try:
        batch_manifest = json.loads(batch_manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Could not read campaign batch manifest {batch_manifest_path}: {exc}") from exc
    prompt_manifest_payload = load_prompt_manifest_payload(asset_dir, brand_slug)
    expected_prompt_sha = sha256_file(asset_dir / f"{brand_slug}-campaign-illustration-prompts.json")
    if str(batch_manifest.get("brand_slug") or "").strip() != brand_slug:
        raise SystemExit(
            f"Campaign batch manifest brand_slug mismatch. Expected {brand_slug}, found {batch_manifest.get('brand_slug')!r}."
        )
    if str(batch_manifest.get("prompt_manifest_sha256") or "").strip().upper() != expected_prompt_sha:
        raise SystemExit(
            "Campaign batch manifest does not match the current prompt manifest. "
            f"Expected SHA {expected_prompt_sha}, found {batch_manifest.get('prompt_manifest_sha256')!r}."
        )
    manifest_items = batch_manifest.get("ideas")
    if not isinstance(manifest_items, list):
        raise SystemExit("Campaign batch manifest must include an ideas list.")
    by_title: dict[str, dict[str, str]] = {}
    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        expected_filename = str(item.get("expected_filename") or "").strip()
        if title and expected_filename:
            by_title[title] = item
    if len(by_title) < len(target_ideas):
        raise SystemExit(
            f"Campaign batch manifest does not cover all target ideas. Needed {len(target_ideas)}, found {len(by_title)}."
        )
    batch_manifest["_manifest_path"] = str(batch_manifest_path)
    return batch_manifest, by_title


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import final raster campaign artwork into newbizintel report data."
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
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Number of parallel image-normalisation workers. Defaults to a safe small pool.",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Write imported image files and a report-data patch manifest without mutating report-data.json.",
    )
    args = parser.parse_args()

    data_path = Path(args.data).resolve()
    base_sha256 = hashlib.sha256(data_path.read_bytes()).hexdigest().upper()
    data = load_json(data_path)
    brand = data.get("brand", {})
    brand_slug = slugify(brand.get("slug") or brand.get("name") or data_path.parent.name)
    asset_dir = data_path.parent / "slide-assets"
    prompt_manifest_by_title = load_prompt_manifest(asset_dir, brand_slug)
    section = get_section(data)
    section_key = "creative_campaign_ideas" if data.get("creative_campaign_ideas") is section else "creative_campaigns"
    ideas = list(section.get("ideas") or [])

    target_ideas = []
    for index, idea in enumerate(ideas):
        role = str(idea.get("illustration_asset_role") or "").strip().lower()
        if role == "final-raster-artwork" and not args.overwrite_final:
            continue
        target_ideas.append((index, idea))

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
    source_provenance = classify_source_root(source_root, data_path.parent)

    batch_manifest, batch_items_by_title = validate_strict_batch_manifest(source_root, asset_dir, brand_slug, target_ideas)
    prepared_imports: list[dict[str, object]] = []

    for index, idea in target_ideas:
        title = (idea.get("title") or "").strip()
        manifest_item = batch_items_by_title.get(title)
        if not manifest_item:
            raise SystemExit(f"Campaign batch manifest is missing an entry for idea {title!r}.")
        expected_filename = str(manifest_item.get("expected_filename") or "").strip()
        if not expected_filename:
            raise SystemExit(f"Campaign batch manifest entry for {title!r} is missing expected_filename.")
        source_path = source_root / expected_filename
        if not source_path.exists():
            raise SystemExit(
                f"Campaign batch folder {source_root} is missing expected file {expected_filename!r} for idea {title!r}."
            )
        existing_url = idea.get("illustration_url") or ""
        destination = output_path_for_idea(asset_dir, brand_slug, title, existing_url)
        prepared_imports.append(
            {
                "index": index,
                "idea": idea,
                "title": title,
                "manifest_item": manifest_item,
                "source": source_path,
                "destination": destination,
            }
        )

    worker_count = args.workers
    if worker_count <= 0:
        worker_count = min(len(prepared_imports), max(1, min(4, (os.cpu_count() or 2))))

    normalised_by_destination: dict[str, dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                normalize_import_task,
                item["source"],
                item["destination"],
            ): item
            for item in prepared_imports
        }
        for future in as_completed(futures):
            result = future.result()
            normalised_by_destination[str(result["destination"])] = result

    imported_files: list[str] = []
    imported_titles: list[str] = []
    patches: list[dict[str, object]] = []

    for item in prepared_imports:
        index = int(item["index"])
        idea = item["idea"]
        title = str(item["title"])
        manifest_item = item["manifest_item"]
        source_path = item["source"]
        destination = item["destination"]
        result = normalised_by_destination[str(destination)]
        dimensions = result["dimensions"]
        idea["illustration_url"] = relative_asset_path(asset_dir, destination)
        idea["illustration_asset_role"] = "final-raster-artwork"
        idea["illustration_generation_backend"] = "imagegen-batch-import"
        idea["illustration_delivery_target"] = "true-raster-artwork"
        idea["illustration_import_source"] = str(source_path)
        idea["illustration_source_provenance"] = source_provenance
        idea["illustration_batch_root"] = str(source_root)
        idea["illustration_batch_manifest"] = str(batch_manifest.get("_manifest_path") or "")
        idea["illustration_imported_at"] = datetime.now(timezone.utc).isoformat()
        idea["illustration_dimensions"] = dimensions
        idea["illustration_expected_filename"] = str(manifest_item.get("expected_filename") or "")
        idea["illustration_prompt_manifest_sha256"] = str(batch_manifest.get("prompt_manifest_sha256") or "").strip().upper()
        idea["illustration_prompt_sha256"] = str(manifest_item.get("prompt_sha256") or "").strip().upper()
        style_hints = prompt_manifest_by_title.get(title, {})
        for field, value in style_hints.items():
            if value and not str(idea.get(field) or "").strip():
                idea[field] = value
        for field in (
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
        ):
            patches.append(
                {
                    "path": f"{section_key}.ideas[{index}].{field}",
                    "value": idea.get(field),
                }
            )
        imported_files.append(str(destination))
        imported_titles.append(title)

    patch_manifest_path = asset_dir / f"{brand_slug}-campaign-import-report-data-patch.json"
    patch_manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "domain": "campaign-art",
                "data": data_path.name,
                "base_sha256": base_sha256,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "patches": patches,
                "source_dir": portable_path(source_root, data_path.parent),
                "source_provenance": source_provenance,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if not args.manifest_only:
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = {
        "data": str(data_path),
        "source_dir": str(source_root),
        "source_provenance": source_provenance,
        "batch_manifest": str(batch_manifest.get("_manifest_path") or ""),
        "imported": len(imported_files),
        "titles": imported_titles,
        "files": imported_files,
        "report_data_patch_manifest": str(patch_manifest_path),
        "overwrite_final": bool(args.overwrite_final),
        "manifest_only": bool(args.manifest_only),
        "parallel_workers": worker_count,
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
