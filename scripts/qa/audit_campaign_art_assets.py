#!/usr/bin/env python3
"""Validate that Creative Campaign artwork is delivery-grade raster art.

This audit is deliberately stricter than the prompt-contract audit. Production
reports must not ship local scaffold images, unverified existing artwork, or
missing/undersized assets.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from PIL import Image


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SCAFFOLD_MARKERS = {
    "local-scaffold",
    "placeholder-scaffold",
    "scaffold",
    "scaffold-allowed",
}
FINAL_BACKENDS = {
    "imagegen",
    "imagegen-batch-import",
    "openai-imagegen",
    "manual-final-raster",
    "external-raster-artwork",
    "custom-raster",
}
MIN_WIDTH = 900
MIN_HEIGHT = 1400
MIN_BYTES = 60_000
MIN_ENTROPY = 2.0


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_template_fixture(data: dict) -> bool:
    brand = data.get("brand") or {}
    return brand.get("name") == "Example Brand" or brand.get("website") == "https://example.com/"


def get_section(data: dict) -> dict:
    section = data.get("creative_campaign_ideas")
    if isinstance(section, dict):
        return section
    section = data.get("creative_campaigns")
    if isinstance(section, dict):
        return section
    return {}


def add_issue(
    *,
    message: str,
    errors: list[str],
    warnings: list[str],
    template_fixture: bool,
) -> None:
    if template_fixture:
        warnings.append(message)
    else:
        errors.append(message)


def image_entropy(image: Image.Image) -> float:
    histogram = image.convert("L").histogram()
    total = sum(histogram)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in histogram:
        if count:
            probability = count / total
            entropy -= probability * math.log2(probability)
    return entropy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Creative Campaign artwork files for final raster delivery."
    )
    parser.add_argument("--data", required=True, help="Path to report-data.json")
    args = parser.parse_args()

    data_path = Path(args.data).resolve()
    data = load_json(data_path)
    section = get_section(data)
    ideas = list(section.get("ideas") or [])
    template_fixture = is_template_fixture(data)
    errors: list[str] = []
    warnings: list[str] = []
    assets: list[dict[str, object]] = []
    palette_families: list[str] = []

    delivery_mode = str(section.get("artwork_delivery_mode") or "").strip().lower()
    section_backend = str(section.get("illustration_generation_backend") or "").strip().lower()

    if delivery_mode != "final-raster-required":
        add_issue(
            message=(
                "creative_campaign_ideas.artwork_delivery_mode must be "
                "'final-raster-required' for delivered reports."
            ),
            errors=errors,
            warnings=warnings,
            template_fixture=template_fixture,
        )

    if section_backend in SCAFFOLD_MARKERS:
        add_issue(
            message=(
                "creative_campaign_ideas.illustration_generation_backend must not "
                f"be scaffold/local placeholder mode ('{section_backend}')."
            ),
            errors=errors,
            warnings=warnings,
            template_fixture=template_fixture,
        )

    for index, idea in enumerate(ideas):
        prefix = f"creative_campaign_ideas.ideas[{index}]"
        title = str(idea.get("title") or f"idea {index + 1}")
        url = str(idea.get("illustration_url") or "").strip()
        role = str(idea.get("illustration_asset_role") or "").strip().lower()
        backend = str(idea.get("illustration_generation_backend") or section_backend).strip().lower()
        palette_family = str(idea.get("illustration_palette_family") or "").strip().lower()

        if not url:
            add_issue(
                message=f"{prefix}.illustration_url is required for final campaign artwork ('{title}').",
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
            continue

        if role != "final-raster-artwork":
            add_issue(
                message=(
                    f"{prefix}.illustration_asset_role must be 'final-raster-artwork' "
                    f"for delivered reports; found '{role or 'missing'}' ('{title}')."
                ),
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )

        if not palette_family:
            add_issue(
                message=f"{prefix}.illustration_palette_family is required for delivered reports ('{title}').",
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
        else:
            palette_families.append(palette_family)

        if backend in SCAFFOLD_MARKERS or (backend and backend not in FINAL_BACKENDS):
            add_issue(
                message=(
                    f"{prefix}.illustration_generation_backend must identify a final "
                    f"raster generation path, not '{backend or 'missing'}' ('{title}')."
                ),
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )

        if url.startswith(("http://", "https://", "data:")):
            add_issue(
                message=f"{prefix}.illustration_url must be a bundled local raster asset, not '{url}'.",
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
            continue

        asset_path = (data_path.parent / url).resolve()
        if not asset_path.exists():
            add_issue(
                message=f"{prefix}.illustration_url points to a missing file: {url}",
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
            continue

        if asset_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            add_issue(
                message=f"{prefix}.illustration_url must be PNG/JPG/WEBP raster art, not '{asset_path.suffix}'.",
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
            continue

        size_bytes = asset_path.stat().st_size
        if size_bytes < MIN_BYTES:
            add_issue(
                message=(
                    f"{prefix}.illustration_url is suspiciously small "
                    f"({size_bytes} bytes); expected delivery-grade raster artwork."
                ),
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )

        try:
            with Image.open(asset_path) as image:
                width, height = image.size
                entropy = image_entropy(image)
                format_name = image.format
        except Exception as exc:  # pragma: no cover - surfaced in JSON for users.
            add_issue(
                message=f"{prefix}.illustration_url is not a readable raster image: {asset_path} ({exc})",
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
            continue

        aspect = width / height if height else 0
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            add_issue(
                message=(
                    f"{prefix}.illustration_url must be at least {MIN_WIDTH}x{MIN_HEIGHT}; "
                    f"found {width}x{height} ('{title}')."
                ),
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
        if aspect < 0.45 or aspect > 0.7:
            add_issue(
                message=(
                    f"{prefix}.illustration_url must be portrait artwork close to 9:16; "
                    f"found aspect {aspect:.2f} ('{title}')."
                ),
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )
        if entropy < MIN_ENTROPY:
            add_issue(
                message=(
                    f"{prefix}.illustration_url appears too visually empty "
                    f"(entropy {entropy:.2f}); expected full rendered artwork."
                ),
                errors=errors,
                warnings=warnings,
                template_fixture=template_fixture,
            )

        assets.append(
            {
                "title": title,
                "path": str(asset_path),
                "width": width,
                "height": height,
                "bytes": size_bytes,
                "format": format_name,
                "entropy": round(entropy, 3),
                "role": role,
                "backend": backend,
                "palette_family": palette_family,
            }
        )

    repeated_palette_families = sorted(
        [family for family, count in Counter(palette_families).items() if family and count > 1]
    )
    if repeated_palette_families:
        add_issue(
            message=(
                "Creative campaign artwork repeats palette family or families: "
                + ", ".join(repeated_palette_families)
            ),
            errors=errors,
            warnings=warnings,
            template_fixture=template_fixture,
        )

    payload = {
        "ok": not errors,
        "data": str(data_path),
        "template_fixture": template_fixture,
        "delivery_mode": delivery_mode,
        "generation_backend": section_backend,
        "asset_count": len(assets),
        "assets": assets,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
