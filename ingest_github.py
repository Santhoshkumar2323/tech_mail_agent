"""
ingest_github.py
Module 1b — Pulls trending repos from GitHub for each configured topic.

Key fix from the original design: filters on `pushed:>` (recent activity)
combined with a star threshold, NOT `created:>` (repo age). A repo created
a year ago that just started trending is what we actually want — a repo
literally created in the last 3 days almost never has 50+ stars yet.

Requires a GitHub token (env var GITHUB_TOKEN) for a higher search rate limit.
"""

import os
import requests
import time
from datetime import datetime, timezone

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def fetch_github_topic(topic: str, min_stars: int, pushed_since: datetime, max_results: int) -> list[dict]:
    """
    Fetches repos for a single topic: recently pushed AND above the star threshold.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Authorization": f"token {token}"} if token else {}

    pushed_date = pushed_since.strftime("%Y-%m-%d")
    query = f"topic:{topic} stars:>={min_stars} pushed:>{pushed_date}"

    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": max_results,
    }

    resp = requests.get(GITHUB_SEARCH_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    repos = []
    for item in data.get("items", []):
        repos.append({
            "source": "github",
            "id": item["full_name"],
            "topic": topic,
            "title": item["full_name"],
            "abstract": item.get("description") or "",
            "readme_url": f"https://raw.githubusercontent.com/{item['full_name']}/{item['default_branch']}/README.md",
            "url": item["html_url"],
            "stars": item["stargazers_count"],
            "pushed_at": item["pushed_at"],
        })

    return repos


def fetch_all_github(topics: list[str], min_stars: int, pushed_since: datetime, max_per_topic: int) -> list[dict]:
    """
    Fetches repos across all topics, then dedups by full repo name
    (a repo can legitimately match more than one topic).
    """
    all_repos = []
    seen_names = set()

    for topic in topics:
        repos = fetch_github_topic(topic, min_stars, pushed_since, max_per_topic)
        for repo in repos:
            if repo["id"] not in seen_names:
                seen_names.add(repo["id"])
                all_repos.append(repo)
        time.sleep(2)  # stay well under the search API rate limit

    return all_repos


def apply_keyword_prefilter(repos: list[dict], keywords: list[str], min_hits: int, max_candidates: int) -> list[dict]:
    """
    Same pre-filter logic as arXiv, applied to repo name + description.
    """
    scored = []
    for repo in repos:
        text = (repo["title"] + " " + repo["abstract"]).lower()
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits >= min_hits:
            repo["keyword_hits"] = hits
            scored.append(repo)

    scored.sort(key=lambda r: r["keyword_hits"], reverse=True)
    return scored[:max_candidates]


def dedup_against_sent(repos: list[dict], sent_ids: set, id_maker) -> list[dict]:
    return [r for r in repos if id_maker("github", r["id"]) not in sent_ids]