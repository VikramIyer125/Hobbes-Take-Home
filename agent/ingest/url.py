"""URL ingestion: fetch homepage, score and fetch subpages, extract."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from agent import sources
from agent.config import (
    HTTP_TIMEOUT_SECS,
    HTTP_USER_AGENT,
    SUBPAGE_MAX_FETCHES,
    TRUST_BY_TYPE,
)
from agent.ingest import gap_closure
from agent.ingest.pipeline import ingest_source
from agent.models import Source


SUBPAGE_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"/pricing(?:/|$|\?)", re.I), 10),
    (re.compile(r"/product(?:s)?(?:/|$|\?)", re.I), 9),
    (re.compile(r"/about(?:/|$|\?)", re.I), 8),
    (re.compile(r"/team(?:/|$|\?)", re.I), 8),
    (re.compile(r"/customers?(?:/|$|\?)", re.I), 8),
    (re.compile(r"/company(?:/|$|\?)", re.I), 7),
    (re.compile(r"/features?(?:/|$|\?)", re.I), 7),
    (re.compile(r"/docs?(?:/|$|\?)", re.I), 6),
    (re.compile(r"/solutions?(?:/|$|\?)", re.I), 5),
    (re.compile(r"/security(?:/|$|\?)", re.I), 4),
    (re.compile(r"/enterprise(?:/|$|\?)", re.I), 4),
    (re.compile(r"/blog(?:/|$|\?)", re.I), 3),
    (re.compile(r"/careers?(?:/|$|\?)", re.I), 3),
]


def _same_site(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    if not pa.netloc or not pb.netloc:
        return False
    na = pa.netloc.lower().removeprefix("www.")
    nb = pb.netloc.lower().removeprefix("www.")
    return na == nb


def _score_url(url: str) -> int:
    for pat, weight in SUBPAGE_PATTERNS:
        if pat.search(url):
            return weight
    return 0


def _normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/")


def _discover_subpages(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = _normalize_url(urljoin(base_url, href))
        if not _same_site(base_url, absolute):
            continue
        if absolute == _normalize_url(base_url):
            continue
        score = _score_url(absolute)
        if score <= 0:
            continue
        # keep the highest score we see for a URL
        if absolute not in found or score > found[absolute]:
            found[absolute] = score

    ranked = sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))
    return [u for u, _ in ranked[:SUBPAGE_MAX_FETCHES]]


def _fetch(client: httpx.Client, url: str) -> Optional[tuple[str, bytes]]:
    try:
        resp = client.get(url, follow_redirects=True)
    except httpx.HTTPError as e:
        print(f"[ingest-url] fetch failed: {url} -> {e}")
        return None
    if resp.status_code >= 400:
        print(f"[ingest-url] {resp.status_code} {url}")
        return None
    ctype = resp.headers.get("content-type", "").lower()
    if "html" not in ctype and "text" not in ctype and "xml" not in ctype:
        print(f"[ingest-url] skipping non-html {url} ({ctype})")
        return None
    return resp.text, resp.content


def _to_clean_text(html: str) -> str:
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if extracted and extracted.strip():
        return extracted.strip()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ingest_one_url(client: httpx.Client, url: str) -> Optional[str]:
    """Fetch, save raw, extract, merge. Returns source_id on success."""
    fetched = _fetch(client, url)
    if fetched is None:
        return None
    html_text, html_bytes = fetched

    content = _to_clean_text(html_text)
    if not content.strip():
        print(f"[ingest-url] empty content after extraction: {url}")
        return None

    source_id = sources.mint_source_id()
    raw_path = sources.save_raw_bytes(source_id, html_bytes, "html")

    src = Source(
        source_id=source_id,
        type="url",
        location=url,
        fetched_at=_now(),
        raw_content_path=str(raw_path),
        content_hash=sources.content_hash(html_bytes),
        trust=TRUST_BY_TYPE["url"],
        derived_fact_ids=[],
        ingestion_summary={},
    )
    sources.save_source(src)

    summary = ingest_source(src, content)
    print(f"[ingest-url] {source_id} {url}  {summary}")
    return source_id


def ingest_url(start_url: str) -> dict:
    """Crawl + ingest pass on a single starting URL."""
    headers = {"User-Agent": HTTP_USER_AGENT}
    report: dict = {"fetched": [], "gap_closure": []}
    with httpx.Client(
        timeout=HTTP_TIMEOUT_SECS,
        headers=headers,
        follow_redirects=True,
    ) as client:
        homepage = _fetch(client, start_url)
        if homepage is None:
            raise RuntimeError(f"Could not fetch homepage: {start_url}")
        home_html, home_bytes = homepage

        home_source_id = sources.mint_source_id()
        raw_path = sources.save_raw_bytes(home_source_id, home_bytes, "html")
        home_src = Source(
            source_id=home_source_id,
            type="url",
            location=start_url,
            fetched_at=_now(),
            raw_content_path=str(raw_path),
            content_hash=sources.content_hash(home_bytes),
            trust=TRUST_BY_TYPE["url"],
            derived_fact_ids=[],
            ingestion_summary={},
        )
        sources.save_source(home_src)
        home_content = _to_clean_text(home_html)
        summary = ingest_source(home_src, home_content)
        print(f"[ingest-url] {home_source_id} {start_url}  {summary}")
        report["fetched"].append({"url": start_url, "source_id": home_source_id})

        subpages = _discover_subpages(start_url, home_html)
        fetched_urls = [start_url]
        for u in subpages:
            sid = _ingest_one_url(client, u)
            if sid:
                report["fetched"].append({"url": u, "source_id": sid})
                fetched_urls.append(u)

        # LLM-guided gap closure, bounded.
        try:
            proposed = gap_closure.propose_gap_closure_urls(start_url, fetched_urls)
        except Exception as e:
            print(f"[ingest-url] gap closure skipped: {e}")
            proposed = []

        for u in proposed:
            if u in fetched_urls:
                continue
            if not _same_site(start_url, u):
                continue
            sid = _ingest_one_url(client, u)
            if sid:
                report["gap_closure"].append({"url": u, "source_id": sid})
                fetched_urls.append(u)

    return report
