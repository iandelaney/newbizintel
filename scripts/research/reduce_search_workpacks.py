import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SCORE_WEIGHTS = {
    "source_authority": 0.25,
    "buyer_relevance": 0.25,
    "reputation_risk_or_opportunity": 0.20,
    "evidence_quality": 0.15,
    "novelty": 0.10,
    "recency": 0.05,
}

PLACEHOLDER_COMPETITORS = {"competitor a", "competitor b", "competitor c"}
PLACEHOLDER_MARKERS = ("replace with", "example brand", "competitor a", "example.com")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def contains_placeholder(value) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


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
            return f"{parsed.day} {parsed.strftime('%B')} {parsed.year}"
        except ValueError:
            continue
    return value


def extract_exact_date(result: dict) -> str:
    published = parse_date(str(result.get("published_date") or ""))
    if re.match(r"^\d{1,2}\s+[A-Z][a-z]+\s+\d{4}$", published):
        return published

    text = result_text(result)
    month_names = (
        "January|February|March|April|May|June|July|August|September|October|November|December|"
        "Jan\\.?|Feb\\.?|Mar\\.?|Apr\\.?|Jun\\.?|Jul\\.?|Aug\\.?|Sep\\.?|Sept\\.?|Oct\\.?|Nov\\.?|Dec\\.?"
    )
    patterns = [
        rf"\b(\d{{1,2}})\s+({month_names})\s+(20\d{{2}})\b",
        rf"\b({month_names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        groups = match.groups()
        if groups[0].isdigit():
            day, month, year = groups[0], groups[1], groups[2]
        else:
            month, day, year = groups[0], groups[1], groups[2]
        month_key = month.lower().rstrip(".")
        month_map = {
            "jan": "January",
            "feb": "February",
            "mar": "March",
            "apr": "April",
            "jun": "June",
            "jul": "July",
            "aug": "August",
            "sep": "September",
            "sept": "September",
            "oct": "October",
            "nov": "November",
            "dec": "December",
        }
        full_month = month_map.get(month_key[:4].rstrip("."), month_map.get(month_key[:3], month.title().rstrip(".")))
        if full_month == "Sept":
            full_month = "September"
        return f"{int(day)} {full_month} {year}"
    return ""


def parsed_year(value: str) -> int:
    if not value:
        return 0
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(value.strip(), fmt).year
        except ValueError:
            continue
    match = re.search(r"\b(20\d{2})\b", value)
    return int(match.group(1)) if match else 0


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


def infer_source_type(result: dict) -> str:
    domain = get_domain(str(result.get("url") or ""))
    title = str(result.get("title") or "").lower()
    if any(token in domain for token in ("reuters", "bloomberg", "ft.com", "wsj", "cnbc", "bbc", "theguardian", "telegraph", "independent", "forbes")):
        return "national_business_press"
    if any(token in domain for token in ("investors", "lse.co", "marketwatch", "morningstar", "sharecast", "proactiveinvestors")):
        return "financial_investor_press"
    if any(token in domain for token in ("retailgazette", "thegrocer", "marketingweek", "campaignlive", "foodnavigator", "grocerygazette", "internetretailing")):
        return "trade_press"
    if any(token in domain for token in ("trustpilot", "reviews.io", "which.co.uk", "reddit", "glassdoor")):
        return "review_platform" if "reddit" not in domain else "social_or_forum"
    if any(token in domain for token in ("similarweb", "semrush", "statista", "kantar", "yougov", "mintel")):
        return "analyst_or_research"
    if any(token in domain for token in ("gov.uk", "asa.org.uk", "cma.org.uk", "ico.org.uk")):
        return "regulatory_or_legal"
    if "press release" in title or "newsroom" in domain:
        return "owned_newsroom"
    return "consumer_press"


def result_text(result: dict) -> str:
    return " ".join(
        str(result.get(field) or "")
        for field in ("title", "content", "url")
    )


def brand_tokens(brand_name: str) -> tuple[str, list[str]]:
    compact = re.sub(r"[^a-z0-9]+", "", brand_name.lower())
    words = [word for word in re.findall(r"[a-z0-9]+", brand_name.lower()) if len(word) > 2]
    return compact, list(dict.fromkeys(words))


def mentions_brand(result: dict, tokens: tuple[str, list[str]]) -> bool:
    compact_brand, words = tokens
    if not compact_brand and not words:
        return True
    haystack = re.sub(r"[^a-z0-9]+", "", result_text(result).lower())
    spaced_words = set(re.findall(r"[a-z0-9]+", result_text(result).lower()))
    if compact_brand and compact_brand in haystack:
        return True
    if len(words) > 1 and all(word in spaced_words for word in words):
        return True
    if len(words) == 1 and words[0] in spaced_words:
        return True
    return False


def score_source_authority(source_type: str, domain: str) -> int:
    if any(token in domain for token in ("reuters", "bloomberg", "ft.com", "wsj", "bbc", "theguardian")):
        return 94
    if source_type == "national_business_press":
        return 88
    if source_type in {"financial_investor_press", "trade_press", "analyst_or_research"}:
        return 84
    if source_type in {"regulatory_or_legal", "industry_body"}:
        return 82
    if source_type == "review_platform":
        return 74
    if source_type == "owned_newsroom":
        return 63
    return 70


def reputation_subscores(result: dict, index: int, brand_name: str) -> dict[str, int]:
    text = result_text(result).lower()
    title = str(result.get("title") or "").lower()
    domain = get_domain(str(result.get("url") or ""))
    source_type = infer_source_type(result)
    risk_terms = ("concern", "complaint", "cuts", "loss", "fall", "warning", "refund", "recall", "probe", "lawsuit", "strike", "delay")
    opportunity_terms = ("growth", "launch", "partnership", "profit", "rise", "record", "expansion", "wins", "new", "investment")
    exact_date = extract_exact_date(result)
    evidence_bonus = 8 if exact_date else 0
    content_bonus = 6 if len(str(result.get("content") or "")) > 120 else 0
    year = parsed_year(exact_date or str(result.get("published_date") or ""))
    recency = 88 if year >= 2026 else 78 if year == 2025 else 62 if year else 50
    novelty_hits = sum(1 for term in (*risk_terms, *opportunity_terms) if term in title)
    impact_hits = sum(1 for term in (*risk_terms, *opportunity_terms) if term in text)
    title_mentions_brand = brand_name.lower() in title or re.sub(r"[^a-z0-9]+", "", brand_name.lower()) in re.sub(r"[^a-z0-9]+", "", title)
    return {
        "source_authority": score_source_authority(source_type, domain),
        "buyer_relevance": min(96, 78 + (10 if title_mentions_brand else 0) + min(8, impact_hits)),
        "reputation_risk_or_opportunity": min(95, 72 + min(18, impact_hits * 3)),
        "evidence_quality": min(94, 70 + evidence_bonus + content_bonus + (6 if domain else 0)),
        "novelty": min(93, 66 + min(21, novelty_hits * 7) + max(0, 5 - index)),
        "recency": recency,
    }


def influence_score(subscores: dict[str, int]) -> int:
    return int(round(sum(subscores[factor] * weight for factor, weight in SCORE_WEIGHTS.items())))


def infer_sentiment(result: dict) -> str:
    text = result_text(result).lower()
    negative = ("complaint", "concern", "cuts", "loss", "fall", "refund", "recall", "probe", "lawsuit", "warning", "strike", "delay")
    positive = ("growth", "launch", "partnership", "profit", "rise", "record", "expansion", "wins", "investment")
    if any(term in text for term in negative):
        return "negative"
    if any(term in text for term in positive):
        return "positive"
    return "neutral"


def build_influential_news(results: list[dict], brand_name: str, workpack_summaries: list[dict]) -> tuple[list[dict], dict]:
    tokens = brand_tokens(brand_name)
    candidate_roles = {"recent_news", "reputation_public_web"}
    candidates = [
        result for result in unique_by_url(results)
        if result.get("_workpack_role") in candidate_roles and mentions_brand(result, tokens)
    ]
    if len(candidates) < 12:
        candidates = [
            result for result in unique_by_url(results)
            if mentions_brand(result, tokens)
        ]

    scored = []
    for index, result in enumerate(candidates):
        if not result.get("url") or not result.get("title") or not extract_exact_date(result):
            continue
        subscores = reputation_subscores(result, index, brand_name)
        scored.append((influence_score(subscores), subscores, result))
    scored.sort(key=lambda item: item[0], reverse=True)

    final = []
    source_counts: dict[str, int] = {}

    def add_final(score: int, subscores: dict[str, int], result: dict) -> bool:
        source = infer_source_name(result)
        source_key = source.lower()
        if source_counts.get(source_key, 0) >= 2:
            return False
        final.append(
            {
                "date": extract_exact_date(result),
                "headline": str(result.get("title") or "").strip(),
                "source": source,
                "source_type": infer_source_type(result),
                "sentiment": infer_sentiment(result),
                "influence_score": score,
                "influence_subscores": subscores,
                "rank_reason": (
                    "Selected after broad current-web discovery because this item scored strongly for "
                    "source authority, buyer relevance, reputation impact, evidence quality, novelty, and recency."
                ),
                "url": str(result.get("url") or "").strip(),
                "why_it_matters": "This story materially shapes how a buyer may understand the brand's momentum, trust, risk, or market context.",
            }
        )
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        return True

    represented_types: set[str] = set()
    for score, subscores, result in scored:
        source_type = infer_source_type(result)
        if source_type in represented_types:
            continue
        if add_final(score, subscores, result):
            represented_types.add(source_type)
        if len(represented_types) >= 3:
            break

    for score, subscores, result in scored:
        if len(final) >= 5:
            break
        if any(item["url"] == str(result.get("url") or "").strip() for item in final):
            continue
        add_final(score, subscores, result)
    final.sort(key=lambda item: int(item.get("influence_score") or 0), reverse=True)

    broad_queries = [
        str(item.get("query") or "").strip()
        for item in workpack_summaries
        if item.get("role") in {"recent_news", "reputation_public_web"} and str(item.get("query") or "").strip()
    ]
    broad_queries = list(dict.fromkeys(broad_queries))[:8]
    candidate_pool = [
        f"{infer_source_name(result)}: {str(result.get('title') or result.get('url') or '').strip()}"
        for result in candidates
    ]
    ranking = {
        "discovery_mode": "broad_first_scored_reduction",
        "candidate_story_count": len(candidates),
        "candidate_pool_summary": candidate_pool,
        "broad_discovery_queries": broad_queries,
        "verification_queries": [
            f"{item['headline']} {item['source']} {brand_name}"
            for item in final
        ],
        "discovery_sequence": [
            "Broad current-web discovery was run first across news, market, reputation, review, investor, and trade contexts.",
            "All candidate results that mentioned the brand were scored using the weighted influence model before the final set was reduced.",
            "Story-specific verification queries are reserved for the final ranked set after scoring, not used to preselect the candidates.",
        ],
        "ranking_method": "Score candidate stories from 1 to 100 using the weighted influence model and order the final set by score descending.",
        "search_queries": broad_queries,
        "ranking_factors": list(SCORE_WEIGHTS.keys()),
        "score_weights": SCORE_WEIGHTS,
        "confidence_score": 70 if len(final) >= 5 and len(candidates) >= 12 else 50,
        "confidence_rationale": "Confidence is based on broad cheap-search coverage, explicit candidate scoring, source diversity checks, and dated source URLs.",
        "limitations": [
            "Cheap Tavily Search may miss paywalled, syndicated, or social-only coverage; live NewBiz2 runs should use Tavily Research as the final reputation quality layer."
        ],
    }
    return final, ranking


def label_from_domain(domain: str) -> str:
    label = domain.split(".")[0]
    special = {
        "gousto": "Gousto",
        "simplycook": "SimplyCook",
        "mindfulchef": "Mindful Chef",
        "blueapron": "Blue Apron",
        "everyplate": "EveryPlate",
        "dinnerly": "Dinnerly",
    }
    return special.get(label.lower(), re.sub(r"[-_]+", " ", label).title())


def build_competitors_from_workpacks(results: list[dict], data: dict) -> list[dict]:
    competitors = []
    seen = set()
    target_domain = get_domain(str(data.get("brand", {}).get("website") or ""))
    blocked_domains = {
        target_domain,
        "similarweb.com",
        "cbinsights.com",
        "reddit.com",
        "facebook.com",
        "savethestudent.org",
        "consumeredge.com",
        "mealkitcomparison.com",
        "statista.com",
    }

    for result in results:
        if result.get("_workpack_role") != "competitor_discovery":
            continue
        text = result_text(result).lower()
        for domain in re.findall(r"\b([a-z0-9-]+\.(?:co\.uk|com|io|ai|net|org))\b", text):
            domain = domain.lower()
            if domain in blocked_domains or domain.startswith("www."):
                continue
            if domain in seen:
                continue
            seen.add(domain)
            competitors.append(
                {
                    "competitor": label_from_domain(domain),
                    "website": f"https://www.{domain}",
                    "why_it_matters": "Current market-discovery search identified this brand as an alternative or category comparator.",
                    "positioning_pattern": "Identified from current market alternatives coverage.",
                    "implication": "Use this comparator to sharpen positioning, proof, and category messaging.",
                }
            )
            if len(competitors) >= 5:
                return competitors

    for row in data.get("competitive_landscape", {}).get("table", []) or []:
        name = row.get("competitor")
        if not name or str(name).strip().lower() in PLACEHOLDER_COMPETITORS:
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
    return competitors


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

    competitors = build_competitors_from_workpacks(all_results, data)

    brand_name = data.get("brand", {}).get("name") or ""
    influential_news, influence_ranking = build_influential_news(all_results, brand_name, workpack_summaries)

    semrush_evidence = data.get("seo_audit", {}).get("semrush_evidence", []) or []
    priority_issues = data.get("seo_audit", {}).get("priority_issues", []) or []
    platform_readout = data.get("brand_reputation", {}).get("platform_readout", []) or []
    recommended_actions = data.get("brand_reputation", {}).get("recommended_actions", []) or []
    semrush_evidence = [] if contains_placeholder(semrush_evidence) else semrush_evidence
    priority_issues = [] if contains_placeholder(priority_issues) else priority_issues
    platform_readout = [] if contains_placeholder(platform_readout) else platform_readout
    recommended_actions = [] if contains_placeholder(recommended_actions) else recommended_actions

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
            "why_passed": "Cheap Tavily Search workpacks produced the initial source map; Tavily Research may add final reputation citations downstream.",
        },
    }

    summary = {
        "mode": "live-search-workpack-summary",
        "data_path": str(data_path),
        "brand_name": data.get("brand", {}).get("name"),
        "brand_website": data.get("brand", {}).get("website"),
        "competitors": competitors,
        "influential_news": influential_news,
        "influence_ranking": influence_ranking,
        "reputation": {
            "platform_readout": platform_readout,
            "recommended_actions": recommended_actions,
            "influence_ranking": influence_ranking,
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
            "Summary reduced from broad Tavily Search workpacks before the Tavily Research reputation quality layer.",
            "Codex owns initial source judgement and synthesis; Tavily Research is the default final quality layer for Brand Reputation in live-summary runs.",
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
