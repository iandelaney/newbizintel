from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from python_modules.common import add_event, load_state, read_json, save_state, set_gate, set_status, write_json


def module_assets(
    args: argparse.Namespace,
    *,
    data_path_from_args: Callable[[argparse.Namespace], Path],
    brand_folder_from_data: Callable[[Path], Path],
    patch_assets: Callable[[dict[str, Any], Path], tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    data_path = data_path_from_args(args)
    brand_folder = brand_folder_from_data(data_path)
    state = load_state(brand_folder)
    set_status(state, "assets", "in_progress")
    set_gate(state, "gate_5_assets", "in_progress")
    set_gate(state, "gate_5a_source_badges", "in_progress")
    set_gate(state, "gate_5b_required_logos", "in_progress")
    add_event(state, "fanout", "assets.logo_acquisition", jobs=["brand", "competitors", "news_sources"])
    save_state(brand_folder, state)
    data, manifest = patch_assets(read_json(data_path), brand_folder)
    write_json(data_path, data)
    manifest_path = brand_folder / "required-logo-manifest.json"
    badge_path = brand_folder / "source-badge-manifest.json"
    write_json(manifest_path, manifest)
    write_json(badge_path, {"ok": manifest["ok"], "sources": manifest["news_sources"], "errors": manifest["errors"]})
    if not manifest["ok"]:
        set_status(state, "assets", "failed")
        set_gate(state, "gate_5_assets", "failed")
        set_gate(state, "gate_5a_source_badges", "failed")
        set_gate(state, "gate_5b_required_logos", "failed")
        save_state(brand_folder, state)
        raise SystemExit("Logo/assets validation failed: " + "; ".join(manifest["errors"]))
    add_event(state, "fanout", "assets.source_badges", jobs=["source-badge-manifest", "brand-asset-validation", "delivery-asset-validation"])
    add_event(state, "reducer", "assets.asset_manifest_reducer", outputs=[str(manifest_path), str(badge_path)])
    set_status(state, "assets", "passed")
    set_gate(state, "gate_5_assets", "passed")
    set_gate(state, "gate_5a_source_badges", "passed")
    set_gate(state, "gate_5b_required_logos", "passed")
    save_state(brand_folder, state)
    return {"module": "assets", "data": str(data_path), "brand_folder": str(brand_folder), "required_logos": manifest}
