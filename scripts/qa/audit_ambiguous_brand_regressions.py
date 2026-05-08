#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_reduce_module(repo_root: Path):
    module_path = repo_root / "scripts" / "research" / "reduce_search_workpacks.py"
    spec = importlib.util.spec_from_file_location("newbiz_reduce_search_workpacks", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_case_data(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "brand": {
            "name": case["brand_name"],
            "website": case["website"],
        },
        "company_snapshot": {
            "summary": case.get("company_summary", ""),
            "items": [{"value": value} for value in case.get("company_items", [])],
        },
        "seo_audit": {
            "priority_issues": [{"issue": value} for value in case.get("seo_priority_issues", [])],
        },
        "competitive_landscape": {
            "table": [{"competitor": value} for value in case.get("competitors", [])],
        },
    }


def run_identity_case(module, case: dict[str, Any]) -> dict[str, Any]:
    data = build_case_data(case)
    brand_name = data["brand"]["name"]
    target_domain = module.get_domain(data["brand"]["website"])
    context_tokens = module.build_run_context_tokens(data, brand_name)
    competitor_tokens = module.competitor_name_tokens(data)
    result = dict(case["result"])
    check_type = case["check_type"]
    if check_type == "result_matches_run_context":
        actual = module.result_matches_run_context(result, context_tokens, competitor_tokens)
    elif check_type == "source_map_entry_allowed":
        actual = module.source_map_entry_allowed(
            result,
            brand_name,
            target_domain,
            set(case.get("influential_urls", [])),
            context_tokens,
            competitor_tokens,
        )
    else:
        raise ValueError(f"Unsupported check_type: {check_type}")
    expected = bool(case["expected"])
    return {
        "name": case["name"],
        "check_type": check_type,
        "expected": expected,
        "actual": actual,
        "ok": actual == expected,
    }


def run_preservation_case(repo_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    reducer = repo_root / "scripts" / "research" / "reduce_search_workpacks.py"
    with tempfile.TemporaryDirectory(prefix="newbizintel-ambiguous-regression-") as tmpdir:
        temp_root = Path(tmpdir)
        data_path = temp_root / "report-data.json"
        output_path = temp_root / "summary.json"
        write_json(data_path, case["data"])
        cmd = [sys.executable, str(reducer), "--data", str(data_path), "--output", str(output_path)]
        for pack in case.get("workpacks", []):
            pack_path = temp_root / str(pack["filename"])
            write_json(pack_path, pack["payload"])
            cmd.extend(["--workpack", str(pack_path)])
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        summary = load_json(output_path)

    expected_competitors = [
        row["competitor"] for row in case["data"]["competitive_landscape"]["table"]
    ]
    actual_competitors = [row.get("competitor") for row in summary.get("competitors", [])]
    expected_news = [
        row["headline"] for row in case["data"]["brand_reputation"]["influential_news"]
    ]
    actual_news = [row.get("headline") for row in summary.get("influential_news", [])]
    expected_source_urls = [
        row["url"] for row in case["data"]["appendix"]["source_map"]
    ]
    actual_source_urls = [row.get("url") for row in summary.get("source_map", [])]
    noisy_tokens = (
        "paddlepals",
        "jack black",
        "paul rudd",
        "montana",
        "operation anaconda",
        "fightwear",
    )
    serialized = json.dumps(summary, ensure_ascii=False).lower()
    unexpected_noise = [token for token in noisy_tokens if token in serialized]
    ok = (
        actual_competitors == expected_competitors
        and actual_news == expected_news
        and actual_source_urls == expected_source_urls
        and not unexpected_noise
    )
    return {
        "name": case["name"],
        "expected_competitors": expected_competitors,
        "actual_competitors": actual_competitors,
        "expected_news": expected_news,
        "actual_news": actual_news,
        "expected_source_urls": expected_source_urls,
        "actual_source_urls": actual_source_urls,
        "unexpected_noise": unexpected_noise,
        "ok": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--fixture", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    fixture_path = Path(args.fixture).resolve() if args.fixture else repo_root / "scripts" / "fixtures" / "ambiguous-brand-regressions.json"
    fixtures = load_json(fixture_path)
    module = load_reduce_module(repo_root)

    identity_results = [run_identity_case(module, case) for case in fixtures.get("identity_cases", [])]
    preservation_result = run_preservation_case(repo_root, fixtures["preservation_case"])
    all_results = identity_results + [preservation_result]
    failures = [result for result in all_results if not result.get("ok")]

    print(json.dumps({
        "ok": not failures,
        "fixture": str(fixture_path),
        "case_count": len(all_results),
        "identity_cases": identity_results,
        "preservation_case": preservation_result,
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
