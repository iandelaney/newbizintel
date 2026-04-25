import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def parse_date(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return f"{parsed.day} {parsed.strftime('%B %Y')}"
        except ValueError:
            continue
    return value


def infer_source_name(result: dict) -> str:
    title = str(result.get("title") or "").strip()
    url = str(result.get("url") or "").strip()
    domain = get_domain(url)
    if "retailgazette" in domain:
        return "Retail Gazette"
    if "thegrocer" in domain:
        return "The Grocer"
    if "reuters" in domain:
        return "Reuters"
    if "marketingweek" in domain:
        return "Marketing Week"
    if "semrush" in domain:
        return "SEMrush"
    if "similarweb" in domain:
        return "Similarweb"
    if "statista" in domain:
        return "Statista"
    if "kantar" in domain:
        return "Kantar"
    if title:
        return title.split("|")[0].split(" - ")[-1].strip() or domain
    return domain


def unique_by_url(items):
    seen = set()
    output = []
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        output.append(item)
    return output


def workpack_role(path: Path) -> str:
    name = path.name.lower()
    if "competitor" in name:
        return "competitor_discovery"
    if "news" in name:
        return "recent_news"
    if "seo" in name or "source" in name:
        return "source_gathering"
    if "reputation" in name or "review" in name:
        return "reputation_public_web"
    return "source_gathering"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workpack", action="append", default=[])
    args = parser.parse_args()

    data_path = Path(args.data).resolve()
    output_path = Path(args.output).resolve()
    data = load_json(data_path)

    workpacks = []
    for value in args.workpack:
        path = Path(value)
        if not path.is_absolute():
            path = data_path.parent / path
        workpacks.append(path.resolve())

    all_results = []
    role_counts = {
        "competitor_discovery": 0,
        "recent_news": 0,
        "reputation_public_web": 0,
        "source_gathering": 0,
    }
    workpack_summaries = []
    for path in workpacks:
        pack = load_json(path)
        status = str(pack.get("status") or "completed")
        if status in {"timeout", "pending", "queued", "running", "processing", "in_progress"}:
            raise SystemExit(f"Workpack is not complete and must be polled or replaced before reduction: {path}")
        results = pack.get("results") or []
        role = workpack_role(path)
        role_counts[role] += len(results)
        workpack_summaries.append(
            {
                "path": str(path),
                "query": pack.get("query"),
                "role": role,
                "result_count": len(results),
                "request_id": pack.get("request_id"),
            }
        )
        for result in results:
            result["_workpack_role"] = role
            all_results.append(result)

    all_results = unique_by_url(all_results)
    source_map = []
    for result in all_results:
        title = str(result.get("title") or result.get("url") or "").strip()
        url = str(result.get("url") or "").strip()
        if not url:
            continue
        role = result.get("_workpack_role") or "source_gathering"
        used_for = ["appendix"]
        if role == "competitor_discovery":
            used_for.append("competitive_landscape")
        elif role == "recent_news":
            used_for.append("brand_reputation")
        elif role == "reputation_public_web":
            used_for.append("brand_reputation")
        else:
            used_for.append("seo_audit")
        source_map.append(
            {
                "title": title,
                "url": url,
                "source": infer_source_name(result),
                "used_for": sorted(set(used_for)),
            }
        )

    competitors = []
    for row in data.get("competitive_landscape", {}).get("table", []) or []:
        name = row.get("competitor")
        if not name:
            continue
        competitors.append(
            {
                "competitor": name,
                "website": row.get("website"),
                "why_it_matters": row.get("why_it_matters"),
                "positioning_pattern": row.get("positioning_pattern"),
                "implication": row.get("implication"),
            }
        )

    news_candidates = [
        result for result in all_results
        if result.get("_workpack_role") == "recent_news" and result.get("published_date")
    ]
    news_candidates.sort(key=lambda row: str(row.get("published_date") or ""), reverse=True)
    influential_news = []
    for result in news_candidates[:5]:
        title = str(result.get("title") or "").strip()
        url = str(result.get("url") or "").strip()
        if not title or not url:
            continue
        influential_news.append(
            {
                "date": parse_date(str(result.get("published_date") or "")),
                "headline": title,
                "source": infer_source_name(result),
                "url": url,
                "why_it_matters": "Included because cheap current-web search returned it as recent, relevant coverage for the brand or its category.",
            }
        )

    if len(influential_news) < 5:
        for item in data.get("brand_reputation", {}).get("influential_news", []) or []:
            if len(influential_news) >= 5:
                break
            if item.get("url") and item.get("url") not in {row["url"] for row in influential_news}:
                influential_news.append(item)

    semrush_evidence = data.get("seo_audit", {}).get("semrush_evidence", []) or []
    priority_issues = data.get("seo_audit", {}).get("priority_issues", []) or []
    platform_readout = data.get("brand_reputation", {}).get("platform_readout", []) or []
    recommended_actions = data.get("brand_reputation", {}).get("recommended_actions", []) or []

    tavily_validation = {
        "competitor_discovery": {
            "status": "passed" if competitors and role_counts["competitor_discovery"] > 0 else "partial",
            "tool": "tavily",
            "source_count": role_counts["competitor_discovery"],
            "used_in_sections": ["competitive_landscape"],
            "why_passed": "Cheap Tavily Search workpacks supplied competitor/category sources; reducer preserved delivery-safe competitor set from report data.",
        },
        "recent_news": {
            "status": "passed" if len(influential_news) >= 5 and role_counts["recent_news"] > 0 else "partial",
            "tool": "tavily",
            "source_count": role_counts["recent_news"],
            "used_in_sections": ["brand_reputation"],
            "why_passed": "Cheap Tavily Search workpacks supplied dated recent-news candidates.",
        },
        "reputation_public_web": {
            "status": "passed" if platform_readout else "partial",
            "tool": "tavily",
            "source_count": role_counts["reputation_public_web"],
            "used_in_sections": ["brand_reputation"],
            "why_passed": "Reducer preserved reputation readout and attached cheap-search source coverage where available.",
        },
        "source_gathering": {
            "status": "passed" if len(source_map) >= 8 else "partial",
            "tool": "tavily",
            "source_count": len(source_map),
            "used_in_sections": ["appendix"],
            "why_passed": "Cheap Tavily Search workpacks produced a source map without Tavily Research escalation.",
        },
    }

    summary = {
        "mode": "live-search-workpack-summary",
        "data_path": str(data_path),
        "brand_name": data.get("brand", {}).get("name"),
        "brand_website": data.get("brand", {}).get("website"),
        "competitors": competitors,
        "influential_news": influential_news,
        "reputation": {
            "platform_readout": platform_readout,
            "recommended_actions": recommended_actions,
        },
        "seo": {
            "semrush_evidence": semrush_evidence,
            "priority_issues": priority_issues,
        },
        "tavily_validation": tavily_validation,
        "source_provenance_summary": {
            "tavily_backed_sources": len(source_map),
            "owned_sources": len([s for s in source_map if get_domain(s.get("url", "")).endswith(("ocado.com", "ocadoretail.com", "ocadogroup.com"))]),
            "third_party_sources": len([s for s in source_map if not get_domain(s.get("url", "")).endswith(("ocado.com", "ocadoretail.com", "ocadogroup.com"))]),
            "tavily_research_used": False,
            "synthesis_owner": "codex",
        },
        "source_map": source_map,
        "locked_sets": {
            "competitors": [row.get("competitor") for row in competitors if row.get("competitor")],
            "influential_news": [row.get("headline") for row in influential_news if row.get("headline")],
        },
        "status": {
            "competitor_discovery": "passed" if competitors else "pending",
            "recent_news": "passed" if len(influential_news) >= 5 else "partial",
            "reputation_public_web": "passed" if platform_readout else "partial",
            "source_gathering": "passed" if len(source_map) >= 8 else "partial",
            "semrush": "passed" if semrush_evidence else "pending",
        },
        "workpacks": workpack_summaries,
        "notes": [
            "Summary reduced from cheap Tavily Search workpacks, not Tavily Research.",
            "Codex owns source judgement and research synthesis by default; Tavily Research is an explicit escalation when cheap coverage is insufficient.",
        ],
    }

    write_json(output_path, summary)
    print(json.dumps({
        "ok": True,
        "summary": str(output_path),
        "source_count": len(source_map),
        "news_count": len(influential_news),
        "competitor_count": len(competitors),
        "tavily_research_used": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
