import feedparser
import time
from datetime import datetime, timezone

ARXIV_API_URL = "http://export.arxiv.org/api/query"


def fetch_arxiv_category(category: str, max_results: int) -> list[dict]:
    query = f"search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    url = f"{ARXIV_API_URL}?{query}"

    feed = feedparser.parse(url)

    papers = []
    for entry in feed.entries:
        try:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            continue

        arxiv_id = entry.id.split("/abs/")[-1]

        papers.append({
            "source": "arxiv",
            "id": arxiv_id,
            "category": category,
            "title": entry.title.replace("\n", " ").strip(),
            "abstract": entry.summary.replace("\n", " ").strip(),
            "url": entry.id,
            "published": published,
        })

    return papers


def fetch_all_arxiv(categories: list[str], max_results_per_category: int, window_start: datetime) -> list[dict]:

    all_papers = []

    for category in categories:
        papers = fetch_arxiv_category(category, max_results_per_category)
        recent = [p for p in papers if p["published"] >= window_start]
        all_papers.extend(recent)
        time.sleep(3)  

    return all_papers


def apply_keyword_prefilter(papers: list[dict], keywords: list[str], min_hits: int, max_candidates: int) -> list[dict]:
    scored = []
    for paper in papers:
        text = (paper["title"] + " " + paper["abstract"]).lower()
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits >= min_hits:
            paper["keyword_hits"] = hits
            scored.append(paper)

    scored.sort(key=lambda p: p["keyword_hits"], reverse=True)
    return scored[:max_candidates]


def dedup_against_sent(papers: list[dict], sent_ids: set, id_maker) -> list[dict]:
    return [p for p in papers if id_maker("arxiv", p["id"]) not in sent_ids]