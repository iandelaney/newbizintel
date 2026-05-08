#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_qa_module(repo_root: Path):
    scripts_root = repo_root / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    module_path = repo_root / "scripts" / "python_modules" / "qa.py"
    spec = importlib.util.spec_from_file_location("newbiz_qamodule", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def format_date(offset_days: int) -> str:
    target = date.today() - timedelta(days=offset_days)
    return target.strftime("%d %B %Y")


def materialize_story(story: dict[str, Any]) -> dict[str, Any]:
    item = dict(story)
    if "date_offset_days" in item:
        item["date"] = format_date(int(item.pop("date_offset_days")))
    item.setdefault("why_it_matters", "Evidence-backed why-it-matters rationale.")
    item.setdefault("rank_reason", "Ranked through the broad-first reduction workflow.")
    item.setdefault("sentiment", "positive")
    item.setdefault("source_logo_url", "slide-assets/source.png")
    item.setdefault("publisher_logo_url", item["source_logo_url"])
    return item


def build_base_report(base_case: dict[str, Any]) -> dict[str, Any]:
    brand_name = base_case["brand_name"]
    website = base_case["brand_website"]
    stories = [materialize_story(story) for story in base_case["influential_news"]]
    return {
        "brand": {
            "name": brand_name,
            "website": website,
        },
        "company_snapshot": {
            "summary": f"{brand_name} provides governed open-source Python and AI tooling for enterprise teams.",
            "items": [
                {"label": "Core proposition", "value": "Governed open-source Python foundation for AI and data science."},
                {"label": "Market position", "value": "Trusted by enterprise technical and security teams for package governance and reproducible environments."},
            ],
        },
        "competitors": [{"competitor": name, "website": f"https://{name.lower().replace(' ', '')}.example.com"} for name in base_case["competitors"]],
        "storybrand": deepcopy(base_case["storybrand"]),
        "seo_audit": {
            "priority_issues": [
                {"issue": "Organic visibility appears broad but inefficient."},
                {"issue": "Search proof should better explain governance, package security, and reproducibility."},
            ]
        },
        "brand_reputation": {
            "influence_ranking": {
                "candidate_story_count": len(base_case["candidate_pool_summary"]),
                "candidate_pool_summary": list(base_case["candidate_pool_summary"]),
                "broad_discovery_queries": list(base_case["broad_discovery_queries"]),
                "verification_queries": list(base_case["verification_queries"]),
            },
            "influential_news": stories,
        },
        "appendix": {
            "source_map": [
                {"label": "Anaconda about page", "url": "https://www.anaconda.com/about-us"},
                {"label": "Anaconda press release", "url": stories[0]["url"]},
            ],
            "sources_reviewed": [
                {"label": "Anaconda about page", "url": "https://www.anaconda.com/about-us"},
                {"label": "UpGuard profile", "url": "https://www.upguard.com/security-report/anaconda"},
            ],
        },
    }


def apply_mutations(report: dict[str, Any], mutations: dict[str, Any]) -> dict[str, Any]:
    if not mutations:
        return report
    if "candidate_pool_summary" in mutations:
        report["brand_reputation"]["influence_ranking"]["candidate_pool_summary"] = list(mutations["candidate_pool_summary"])
        report["brand_reputation"]["influence_ranking"]["candidate_story_count"] = len(mutations["candidate_pool_summary"])
    if "replace_story" in mutations:
        config = mutations["replace_story"]
        index = int(config["index"])
        story = report["brand_reputation"]["influential_news"][index]
        if "date_offset_days" in config:
            story["date"] = format_date(int(config["date_offset_days"]))
    if "stories_override" in mutations:
        report["brand_reputation"]["influential_news"] = [materialize_story(story) for story in mutations["stories_override"]]
    if "storybrand" in mutations:
        report["storybrand"] = deepcopy(mutations["storybrand"])
    if "appendix_noise" in mutations:
        for item in mutations["appendix_noise"]:
            report["appendix"]["source_map"].append(dict(item))
            report["appendix"]["sources_reviewed"].append(dict(item))
    return report


def run_case(module, repo_root: Path, base_case: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    report = build_base_report(base_case)
    report = apply_mutations(report, case.get("mutations", {}))
    with tempfile.TemporaryDirectory(prefix="newbizintel-research-quality-") as tmpdir:
        temp_root = Path(tmpdir)
        data_path = temp_root / "report-data.json"
        write_json(data_path, report)
        result = module.audit_research_quality(data_path)
    expect_ok = bool(case["expect_ok"])
    expected_category = case.get("expected_category")
    category_ok = None
    if expected_category:
        category_ok = result.get("categories", {}).get(expected_category, {}).get("ok")
    ok = result.get("ok") == expect_ok
    if expected_category and expect_ok is False:
        ok = ok and category_ok is False
    return {
        "name": case["name"],
        "expect_ok": expect_ok,
        "actual_ok": result.get("ok"),
        "expected_category": expected_category,
        "actual_category_ok": category_ok,
        "ok": ok,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--fixture", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    fixture_path = Path(args.fixture).resolve() if args.fixture else repo_root / "scripts" / "fixtures" / "research-quality-regressions.json"
    fixtures = load_json(fixture_path)
    module = load_qa_module(repo_root)

    results = [run_case(module, repo_root, fixtures["base_case"], case) for case in fixtures.get("cases", [])]
    failures = [result for result in results if not result.get("ok")]
    print(
        json.dumps(
            {
                "ok": not failures,
                "fixture": str(fixture_path),
                "case_count": len(results),
                "results": results,
                "failures": failures,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
