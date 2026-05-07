import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


RUNTIMES = {
    "pptx_runtime": [
        "python-pptx==1.0.2",
        "lxml==6.0.2",
        "Pillow==12.1.0",
        "typing_extensions==4.15.0",
        "XlsxWriter==3.2.9",
    ],
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build platform-native vendor runtimes for the newbizintel skill."
    )
    parser.add_argument(
        "--runtime",
        action="append",
        choices=sorted(RUNTIMES.keys()),
        help="One or more runtime directories to refresh. Defaults to all runtimes.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Path to the newbizintel skill repo root.",
    )
    return parser.parse_args()


def rebuild_runtime(target: Path, packages):
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f"{target.name}-"))
    backup = target.parent / f"{target.name}.bak"

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(staging_root),
        *packages,
    ]
    try:
        subprocess.run(command, check=True)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    marker = {
        "platform": sys.platform,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "packages": packages,
    }
    marker_payload = json.dumps(marker, indent=2) + "\n"
    (staging_root / ".newbizintel-runtime.json").write_text(marker_payload, encoding="utf-8")

    if backup.exists():
        shutil.rmtree(backup)

    if target.exists():
        target.rename(backup)

    try:
        staging_root.rename(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def main():
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    vendor_root = repo_root / "vendor"
    runtimes = args.runtime or list(RUNTIMES.keys())

    results = []
    for runtime_name in runtimes:
        target = vendor_root / runtime_name
        rebuild_runtime(target, RUNTIMES[runtime_name])
        results.append(
            {
                "runtime": runtime_name,
                "target": str(target),
                "packages": RUNTIMES[runtime_name],
            }
        )

    print(json.dumps({"repo_root": str(repo_root), "runtimes": results}, indent=2))


if __name__ == "__main__":
    main()
