#!/usr/bin/env python3
"""Compatibility wrapper for the canonical NewBizIntel Python runner."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


if __name__ == "__main__":
    sys.argv[0] = str(Path(__file__).name)
    legacy_path = Path(__file__).with_name("newbiz2.py")
    spec = importlib.util.spec_from_file_location("newbizintel_legacy_runner", legacy_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load legacy runner at {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
