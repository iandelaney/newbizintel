from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from python_modules.common import (
    load_state,
    normalize_url,
    output_root,
    read_json,
    record_token_usage,
    save_state,
    set_gate,
    set_status,
    slugify,
    write_json,
)


def module_intake(args: argparse.Namespace, *, template_path: Path, template_assets: Path) -> dict[str, str]:
    if getattr(args, "data_path", None):
        data_path = Path(args.data_path).expanduser().resolve()
        brand_folder = data_path.parent
        data = read_json(data_path)
        if getattr(args, "brand_name", None):
            data.setdefault("brand", {})["name"] = args.brand_name
        if getattr(args, "website", None):
            data.setdefault("brand", {})["website"] = normalize_url(args.website)
        write_json(data_path, data)
    else:
        if not getattr(args, "brand_name", None) or not getattr(args, "website", None):
            raise SystemExit("Creating a new workspace requires --brand-name and --website.")
        root = output_root(getattr(args, "brand_folder", None))
        brand_slug = slugify(args.brand_name)
        brand_folder = root / brand_slug
        brand_folder.mkdir(parents=True, exist_ok=True)
        data_path = brand_folder / "report-data.json"
        if data_path.exists():
            data = read_json(data_path)
        else:
            data = read_json(template_path)
        data.setdefault("brand", {})
        data["brand"]["name"] = args.brand_name
        data["brand"]["slug"] = brand_slug
        data["brand"]["website"] = normalize_url(args.website)
        data.setdefault("cover", {}).setdefault("assumptions", [])
        if data["cover"]["assumptions"]:
            data["cover"]["assumptions"][0] = f"Confirmed primary site: {data['brand']['website']}."
        write_json(data_path, data)
        if template_assets.exists() and not (brand_folder / "slide-assets").exists():
            shutil.copytree(template_assets, brand_folder / "slide-assets")

    state = load_state(brand_folder)
    data = read_json(data_path)
    if not str(data.get("brand", {}).get("website", "")).startswith(("http://", "https://")):
        set_status(state, "intake", "failed")
        set_gate(state, "gate_1_intake", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Intake failed: brand.website must be a confirmed real website.")
    set_status(state, "intake", "passed")
    set_gate(state, "gate_1_intake", "passed")
    record_token_usage(
        state,
        "intake.workspace_setup",
        None,
        provider="local-python",
        model="deterministic",
        status="deterministic",
        note="Workspace creation and input normalization are deterministic local operations.",
    )
    save_state(brand_folder, state)
    return {
        "module": "intake",
        "data": str(data_path),
        "brand_folder": str(brand_folder),
        "run_state": str(brand_folder / "run-state.json"),
    }
