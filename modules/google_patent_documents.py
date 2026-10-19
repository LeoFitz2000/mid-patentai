"""取得 Google Patents 正文快照。检索摘要只用于找候选，不能冒充完整披露。"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from modules.novelty_models import PatentDocument, SourceSection, google_patent_url


def parse_google_page(url: str, html: str) -> PatentDocument:
    url = google_patent_url(url)
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names: str) -> str:
        for name in names:
            node = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"itemprop": name})
            if node and node.get("content"):
                return str(node["content"]).strip()
            node = soup.find("time", attrs={"itemprop": name})
            if node:
                return str(node.get("datetime") or node.get_text()).strip()
        return ""

    sections: list[SourceSection] = []
    selectors = (
        ("abstract", '[itemprop="abstract"], .abstract-content'),
        ("claim", 'div.claim, [itemprop="claim"]'),
        ("description", '[itemprop="description"] .description-paragraph, .description-line'),
    )
    seen: set[str] = set()
    kinds: set[str] = set()
    for kind, selector in selectors:
        nodes = soup.select(selector)
        if kind == "description" and not nodes:
            nodes = soup.select('[itemprop="description"]')
        for node in nodes:
            text = " ".join(node.get_text(" ", strip=True).split())
            if len(text) < 4 or text in seen:
                continue
            seen.add(text)
            kinds.add(kind)
            sections.append(SourceSection(f"{kind}-{len(sections) + 1}", text))
    doc_id = url.split("/patent/", 1)[1].split("/")[0]
    return PatentDocument(
        id=doc_id, title=meta("DC.title", "citation_title") or doc_id, url=url,
        publication_date=meta("publicationDate", "citation_publication_date"),
        filing_date=meta("filingDate", "citation_filing_date"),
        priority_date=meta("priorityDate", "citation_priority_date"),
        sections=tuple(sections), complete="claim" in kinds and "description" in kinds,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        error="" if sections else "页面没有取得可核对正文。",
    )


def fetch_google_document(url: str, get: Callable | None = None) -> PatentDocument:
    url = google_patent_url(url)
    get = get or requests.get
    try:
        response = get(url, headers={"User-Agent": "PatentNoveltyHarness/1.0"},
                       timeout=(5, 30), allow_redirects=False)
        if 300 <= response.status_code < 400:
            raise RuntimeError("Google Patents 返回重定向，请人工打开并核对单篇来源。")
        response.raise_for_status()
        return parse_google_page(url, response.text)
    except requests.RequestException as exc:
        raise RuntimeError("Google Patents 正文获取失败；可粘贴同一来源的原文快照。") from exc


def manual_google_document(url: str, title: str, publication_date: str, body: str,
                           filing_date: str = "", priority_date: str = "",
                           complete: bool = False) -> PatentDocument:
    """网页无法访问时的显式人工入口；报告保留人工录入标记，不伪装成网络抓取。"""
    url = google_patent_url(url)
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", body) if item.strip()]
    if not paragraphs:
        raise ValueError("请粘贴该 Google Patents 页面的原文，并用空行分段。")
    return PatentDocument(
        id=url.split("/patent/", 1)[1].split("/")[0], title=title.strip() or "人工录入原文",
        url=url, publication_date=publication_date.strip(), filing_date=filing_date.strip(),
        priority_date=priority_date.strip(), source_kind="manual_google_patents_snapshot",
        sections=tuple(SourceSection(f"manual-{i}", text) for i, text in enumerate(paragraphs, 1)),
        complete=complete, retrieved_at=datetime.now(timezone.utc).isoformat(),
    )
