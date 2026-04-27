#!/usr/bin/env python3
import argparse
import importlib
import json
import os
import sys
from pathlib import Path


REQUIRED_MODULES = {
    "Pillow": "PIL",
    "python-pptx": "pptx",
    "lxml": "lxml.etree",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Check NewBiz2 Python runtime dependencies.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def runtime_marker(vendor_site: Path) -> dict:
    marker_path = vendor_site / ".newbiz2-runtime.json"
    if not marker_path.exists():
        return {}
    try:
        return json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def vendor_has_binary_extensions(vendor_site: Path) -> bool:
    if not vendor_site.exists():
        return False
    return any(vendor_site.rglob(pattern) for pattern in ("*.pyd", "*.so", "*.dylib"))


def vendor_is_compatible(vendor_site: Path) -> tuple[bool, str]:
    if not vendor_site.exists():
        return False, f"Missing vendored runtime at {vendor_site}."

    marker = runtime_marker(vendor_site)
    if not marker:
        return False, f"Missing or unreadable runtime marker at {vendor_site / '.newbiz2-runtime.json'}."

    expected_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    marker_platform = marker.get("platform")
    marker_python = marker.get("python")

    if vendor_has_binary_extensions(vendor_site):
        if marker_platform != sys.platform:
            return False, f"Vendored runtime is for {marker_platform}, current platform is {sys.platform}."
        if marker_python != expected_python:
            return False, f"Vendored runtime is for Python {marker_python}, current Python is {expected_python}."

    return True, f"Vendored runtime matches {sys.platform} / Python {expected_python}."


def import_required_modules(vendor_site: Path, use_vendor: bool) -> list[dict]:
    if use_vendor and str(vendor_site) not in sys.path:
        sys.path.insert(0, str(vendor_site))

    checks = []
    for package, module_name in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module_name)
            checks.append(
                {
                    "key": f"python_module_{package.lower().replace('-', '_')}",
                    "ok": True,
                    "detail": f"{package} is importable as {module_name}.",
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "key": f"python_module_{package.lower().replace('-', '_')}",
                    "ok": False,
                    "detail": f"{package} is not importable as {module_name}: {exc}",
                }
            )
    return checks


def main():
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    vendor_site = repo_root / "vendor" / "pptx_runtime"
    version_ok = sys.version_info >= (3, 10)
    vendor_ok, vendor_detail = vendor_is_compatible(vendor_site)
    module_checks = import_required_modules(vendor_site, vendor_ok)

    checks = [
        {
            "key": "python_version",
            "ok": version_ok,
            "detail": f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; NewBiz2 requires Python 3.10+.",
        },
        {
            "key": "python_vendor_runtime",
            "ok": vendor_ok,
            "detail": vendor_detail,
        },
        *module_checks,
    ]

    result = {
        "ok": all(check["ok"] for check in checks),
        "repo_root": str(repo_root),
        "python": sys.executable,
        "checks": checks,
        "repair": f"{sys.executable} {repo_root / 'scripts' / 'bootstrap_vendor_runtime.py'} --repo-root {repo_root}",
    }

    if not args.quiet:
        print(json.dumps(result, separators=(",", ":")))

    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
