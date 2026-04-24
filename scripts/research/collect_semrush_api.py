#!/usr/bin/env python3
"""Collect compact SEMrush API evidence for NewBiz2 reports.

The script reads the API key from an environment variable and never writes it to
disk. Output is a small evidence workpack suitable for review or merging into a
NewBiz2 research summary.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_URL = "https://api.semrush.com/"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def root_domain(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    host = parsed.netloc or parsed.path
    return host.lower().removeprefix("www.").split("/")[0]


def semrush_get(params: dict[str, str], timeout: int = 45) -> dict[str, Any]:
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "newbiz2-semrush-collector/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8-sig", errors="replace")

    if body.lstrip().upper().startswith("ERROR"):
        return {"ok": False, "error": body.strip(), "rows": [], "columns": []}

    reader = csv.DictReader(io.StringIO(body), delimiter=";")
    rows = [dict(row) for row in reader]
    return {"ok": True, "error": "", "rows": rows, "columns": reader.fieldnames or []}


def to_number(value: Any) -> float:
    if value is None:
        return 0
    text = str(value).replace(",", "").strip()
    if not text:
        return 0
    try:
        return float(text)
    except ValueError:
        return 0


def first_present(row: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def evidence_from_datasets(domain: str, datasets: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []

    keywords = datasets.get("organic_keywords", {}).get("rows") or []
    if keywords:
        top = sorted(keywords, key=lambda row: to_number(first_present(row, ["Search Volume", "Nq"])), reverse=True)[:3]
        examples = []
        for row in top:
            keyword = first_present(row, ["Keyword", "Ph"])
            position = first_present(row, ["Position", "Po"])
            volume = first_present(row, ["Search Volume", "Nq"])
            if keyword:
                examples.append(f"{keyword} (position {position or 'n/a'}, volume {volume or 'n/a'})")
        if examples:
            evidence.append(
                {
                    "title": "Organic demand is visible but unevenly captured",
                    "body": (
                        f"SEMrush organic keyword data for {domain} shows demand around "
                        f"{'; '.join(examples)}. These terms indicate where search intent is already present "
                        "and where messaging or content can be tightened."
                    ),
                }
            )

    competitors = datasets.get("organic_competitors", {}).get("rows") or []
    if competitors:
        top = sorted(competitors, key=lambda row: to_number(first_present(row, ["Common Keywords", "Np"])), reverse=True)[:3]
        examples = []
        for row in top:
            competitor = first_present(row, ["Domain", "Dn"])
            common = first_present(row, ["Common Keywords", "Np"])
            if competitor:
                examples.append(f"{competitor} ({common or 'n/a'} common keywords)")
        if examples:
            evidence.append(
                {
                    "title": "Organic competitors can be validated from search overlap",
                    "body": (
                        f"SEMrush competitor data identifies search-overlap rivals including "
                        f"{'; '.join(examples)}. This helps separate true organic competitors from broader "
                        "commercial or narrative comparisons."
                    ),
                }
            )

    pages = datasets.get("organic_pages", {}).get("rows") or []
    if pages:
        top = sorted(pages, key=lambda row: to_number(first_present(row, ["Traffic", "Tr"])), reverse=True)[:3]
        examples = []
        for row in top:
            url = first_present(row, ["Url", "Ur"])
            keywords = first_present(row, ["Number of Keywords", "Pc"])
            traffic = first_present(row, ["Traffic", "Tr"])
            if url:
                examples.append(f"{url} ({keywords or 'n/a'} keywords, traffic {traffic or 'n/a'})")
        if examples:
            evidence.append(
                {
                    "title": "Ranking pages show where organic visibility is concentrated",
                    "body": (
                        f"SEMrush organic pages data highlights visible URLs such as "
                        f"{'; '.join(examples)}. This gives the report a page-level evidence layer for "
                        "content and SEO recommendations."
                    ),
                }
            )

    return evidence[:3]


def build_requests(domain: str, database: str, key: str, limits: dict[str, int]) -> dict[str, dict[str, str]]:
    return {
        "organic_keywords": {
            "type": "domain_organic",
            "key": key,
            "domain": domain,
            "database": database,
            "display_limit": str(limits["keywords"]),
            "display_sort": "nq_desc",
            "export_columns": "Ph,Po,Nq,Cp,Co,Ur,Tr,Tc,Kd",
        },
        "organic_competitors": {
            "type": "domain_organic_organic",
            "key": key,
            "domain": domain,
            "database": database,
            "display_limit": str(limits["competitors"]),
            "display_sort": "np_desc",
            "export_columns": "Dn,Cr,Np,Or",
        },
        "organic_pages": {
            "type": "domain_organic_unique",
            "key": key,
            "domain": domain,
            "database": database,
            "display_limit": str(limits["pages"]),
            "display_sort": "tr_desc",
            "export_columns": "Ur,Pc,Tg,Tr",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect SEMrush API evidence for a NewBiz2 report.")
    parser.add_argument("--data", help="Path to report-data.json")
    parser.add_argument("--domain", help="Domain or URL to query")
    parser.add_argument("--database", default="uk", choices=["uk", "us"], help="SEMrush regional database")
    parser.add_argument("--output", help="Optional output JSON path")
    parser.add_argument("--api-key-env", default="SEMRUSH_API_KEY", help="Environment variable containing the API key")
    parser.add_argument("--keyword-limit", type=int, default=20)
    parser.add_argument("--competitor-limit", type=int, default=10)
    parser.add_argument("--page-limit", type=int, default=10)
    args = parser.parse_args()

    data_path = Path(args.data).resolve() if args.data else None
    data: dict[str, Any] = {}
    if data_path:
        data = load_json(data_path)

    domain = root_domain(args.domain or (data.get("brand") or {}).get("website", ""))
    if not domain:
        raise SystemExit("Provide --domain or report data with brand.website.")

    key = os.environ.get(args.api_key_env, "").strip()
    if not key:
        payload = {
            "ok": False,
            "status": "blocked",
            "provider": "semrush-direct-api",
            "domain": domain,
            "database": args.database,
            "errors": [f"Missing {args.api_key_env} environment variable."],
            "seo": {"semrush_evidence": [], "priority_issues": []},
            "datasets": {},
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 2

    limits = {
        "keywords": max(1, args.keyword_limit),
        "competitors": max(1, args.competitor_limit),
        "pages": max(1, args.page_limit),
    }
    request_map = build_requests(domain, args.database, key, limits)
    datasets: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for name, params in request_map.items():
        safe_params = {k: v for k, v in params.items() if k != "key"}
        try:
            result = semrush_get(params)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "rows": [], "columns": []}
        result["request"] = safe_params
        datasets[name] = result
        if not result.get("ok"):
            errors.append(f"{name}: {result.get('error') or 'unknown SEMrush error'}")

    evidence = evidence_from_datasets(domain, datasets)
    available_dataset_count = sum(1 for result in datasets.values() if result.get("ok") and result.get("rows"))
    status = "passed" if len(evidence) >= 2 else ("partial" if available_dataset_count > 0 else "blocked")
    ok = status in {"passed", "partial"}

    payload = {
        "ok": ok,
        "status": status,
        "provider": "semrush-direct-api",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "data": str(data_path) if data_path else None,
        "domain": domain,
        "database": args.database,
        "seo": {"semrush_evidence": evidence, "priority_issues": []},
        "datasets": datasets,
        "dataset_counts": {name: len(result.get("rows") or []) for name, result in datasets.items()},
        "errors": errors,
        "notes": [
            "Collected via direct SEMrush API using SEMRUSH_API_KEY from the environment.",
            "API key is intentionally omitted from this output.",
        ],
    }

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(payload, separators=(",", ":")))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
