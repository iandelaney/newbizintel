#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from generate_campaign_illustrations import slugify


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def get_section(data: dict) -> dict:
    section = data.get("creative_campaign_ideas")
    if isinstance(section, dict):
        return section
    section = data.get("creative_campaigns")
    if isinstance(section, dict):
        return section
    raise SystemExit("creative_campaign_ideas section not found in report data")


def output_root() -> Path:
    env_root = os.environ.get("NEWBIZINTEL_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return (Path.cwd() / "output").resolve()


def proof_root(explicit_root: str | None = None) -> Path:
    if explicit_root:
        root = Path(explicit_root).expanduser().resolve()
    else:
        env_root = os.environ.get("NEWBIZINTEL_PROOF_ROOT")
        if env_root:
            root = Path(env_root).expanduser().resolve()
        else:
            root = (Path.cwd() / "tmp-newbizintel-proofs").resolve()
    delivery_root = output_root().resolve()
    delivery_prefix = str(delivery_root).rstrip("\\/") + os.sep
    normalized_root = str(root)
    normalized_delivery = str(delivery_root)
    if normalized_root == normalized_delivery or normalized_root.startswith(delivery_prefix):
        raise SystemExit(
            "NewBizIntel proof artifacts must not be written inside the delivery output root. "
            f"Use a proof root outside '{delivery_root}'. Requested: {root}"
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_imagegen_cli(explicit_path: str | None = None) -> Path:
    if explicit_path:
        script = Path(explicit_path).expanduser().resolve()
    else:
        codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser().resolve()
        script = codex_home / "skills" / ".system" / "imagegen" / "scripts" / "image_gen.py"
    if not script.exists():
        raise SystemExit(f"Bundled imagegen CLI not found: {script}")
    return script


def default_batch_dir(base_proof_root: Path, brand_slug: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base_proof_root / brand_slug / "campaign-art-batches" / stamp


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate original campaign-art rasters through the bundled imagegen CLI."
    )
    parser.add_argument("--data", required=True, help="Path to report-data.json")
    parser.add_argument("--proof-root", help="Optional proof root outside the delivery output tree")
    parser.add_argument("--out-dir", help="Explicit batch directory for generated image outputs")
    parser.add_argument("--imagegen-cli", help="Explicit path to scripts/image_gen.py")
    parser.add_argument("--dry-run", action="store_true", help="Prepare the batch and print the imagegen request without API calls")
    parser.add_argument("--force", action="store_true", help="Allow imagegen CLI to overwrite existing target files")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent image generation jobs for the imagegen batch CLI")
    parser.add_argument(
        "--palette-candidates-per-idea",
        type=int,
        default=1,
        help="How many palette alternatives to generate per campaign idea. Default keeps normal runs to four generated images total.",
    )
    args = parser.parse_args()

    data_path = Path(args.data).expanduser().resolve()
    data = read_json(data_path)
    brand = data.get("brand") or {}
    brand_slug = slugify(str(brand.get("slug") or brand.get("name") or data_path.parent.name))
    section = get_section(data)
    asset_dir = data_path.parent / "slide-assets"

    prompt_manifest_rel = str(section.get("illustration_prompt_manifest") or "").strip()
    batch_request_rel = str(section.get("illustration_batch_request") or "").strip()
    prompt_manifest_path = (data_path.parent / prompt_manifest_rel).resolve() if prompt_manifest_rel else asset_dir / f"{brand_slug}-campaign-illustration-prompts.json"
    batch_request_path = (data_path.parent / batch_request_rel).resolve() if batch_request_rel else asset_dir / f"{brand_slug}-campaign-batch-request.json"

    if not prompt_manifest_path.exists():
        raise SystemExit(f"Campaign prompt manifest missing: {prompt_manifest_path}")
    if not batch_request_path.exists():
        raise SystemExit(f"Campaign batch request missing: {batch_request_path}")

    prompt_manifest = read_json(prompt_manifest_path)
    request_payload = read_json(batch_request_path)
    ideas = list(prompt_manifest.get("ideas") or [])
    if not ideas:
        raise SystemExit(f"No campaign-art ideas found in prompt manifest: {prompt_manifest_path}")

    batch_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else default_batch_dir(proof_root(args.proof_root), brand_slug)
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_manifest_path = batch_dir / "campaign-batch-manifest.json"
    shutil.copyfile(batch_request_path, batch_manifest_path)

    jobs_path = batch_dir / "imagegen-prompts.jsonl"
    selection_manifest_path = batch_dir / "palette-candidate-selection.json"
    selection_manifest: list[dict[str, object]] = []
    with jobs_path.open("w", encoding="utf-8") as handle:
        for idea in ideas:
            candidates = list(idea.get("palette_candidates") or [])
            if not candidates:
                candidates = [
                    {
                        "variant_index": 1,
                        "style_slug": str(idea.get("style_slug") or "").strip(),
                        "style_family": str(idea.get("style_family") or "").strip(),
                        "palette_family": str(idea.get("palette_family") or "").strip(),
                        "medium": str(idea.get("medium") or "").strip(),
                        "prompt": str(idea.get("prompt") or "").strip(),
                        "prompt_sha256": str(idea.get("prompt_sha256") or "").strip(),
                        "candidate_filename": str(idea.get("expected_filename") or "").strip(),
                    }
                ]
            selected_candidates = candidates[: max(1, int(args.palette_candidates_per_idea))]
            selection_manifest.append(
                {
                    "title": str(idea.get("title") or "").strip(),
                    "expected_filename": str(idea.get("expected_filename") or "").strip(),
                    "variants": selected_candidates,
                }
            )
            for candidate in selected_candidates:
                handle.write(
                    json.dumps(
                        {
                            "prompt": str(candidate.get("prompt") or "").strip(),
                            "out": str(candidate.get("candidate_filename") or "").strip(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    selection_manifest_path.write_text(
        json.dumps(selection_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    imagegen_cli = resolve_imagegen_cli(args.imagegen_cli)
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "Campaign-art original generation requires OPENAI_API_KEY for the bundled imagegen CLI."
        )

    command = [
        sys.executable,
        str(imagegen_cli),
        "generate-batch",
        "--input",
        str(jobs_path),
        "--out-dir",
        str(batch_dir),
        "--model",
        "gpt-image-2",
        "--size",
        "1024x1536",
        "--quality",
        "high",
        "--output-format",
        "png",
        "--concurrency",
        str(max(1, min(int(args.concurrency), len(ideas)))),
        "--no-augment",
    ]
    if args.force:
        command.append("--force")
    if args.dry_run:
        command.append("--dry-run")

    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown imagegen CLI failure"
        raise SystemExit(f"generate_final_campaign_art failed: {detail}")

    payload = {
        "ok": True,
        "data": str(data_path),
        "brand_slug": brand_slug,
        "prompt_manifest": str(prompt_manifest_path),
        "batch_request": str(batch_request_path),
        "batch_manifest": str(batch_manifest_path),
        "batch_dir": str(batch_dir),
        "jobs_path": str(jobs_path),
        "selection_manifest": str(selection_manifest_path),
        "expected_files": [str(item.get("expected_filename") or "").strip() for item in ideas],
        "generated_count": sum(
            len(entry.get("variants") or [])
            for entry in selection_manifest
        ),
        "dry_run": bool(args.dry_run),
        "imagegen_cli": str(imagegen_cli),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
