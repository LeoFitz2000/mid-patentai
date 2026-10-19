"""Normalize short search snippets and retain a clickable source for each record."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from modules.models import PatentRecord
from modules.patent_search import GOOGLE_PATENTS_HOST


def _allowed_host(host: str) -> bool:
    return host == GOOGLE_PATENTS_HOST


def extract_records(raw_results: list[dict]) -> list[PatentRecord]:
    records: list[PatentRecord] = []
    seen: set[str] = set()
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        raw_url = str(item.get("url") or "").strip()
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not _allowed_host(host):
            continue
        url = urlunparse(parsed._replace(fragment="")).rstrip("/")
        if url in seen:
            continue
        title = " ".join(str(item.get("title") or "").split())[:200]
        snippet = " ".join(str(item.get("content") or "").split())[:1200]
        if not title and not snippet:
            continue
        seen.add(url)
        records.append(
            PatentRecord(
                title=title or "无标题",
                snippet=snippet,
                url=url,
                source=host,
            )
        )
    return records
