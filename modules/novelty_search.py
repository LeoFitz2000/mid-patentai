"""Bounded query planning and an exportable journal; lexical hints are not relevance judgments."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone

from modules.novelty_matching import SynonymLexicon
from modules.novelty_models import Feature, google_patent_url
from modules.patent_search import MAX_QUERY_LENGTH

MAX_QUERIES = 8
RESULTS_PER_QUERY = 5


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def search_input_hash(features: list[Feature], cutoff: str) -> str:
    raw = json.dumps({"features": [asdict(f) for f in features], "cutoff": cutoff},
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def query_plan(features: list[Feature], query: str, lexicon: SynonymLexicon) -> dict:
    """Each original feature gets priority over variants. Never shorten a feature."""
    query = query.strip()
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError("专利检索词超过 400 字，请拆分查询；不会静默截断。")
    plan = {"query_mode": "user_query" if query else "per_feature", "queries": [], "skipped": []}
    sources = [([], query)] if query else [([f.id], f.text) for f in features]
    seen: set[str] = set()

    def add(ids: list[str], text: str, kind: str) -> None:
        if text in seen:
            # Same query can cover multiple explicitly identical feature inputs.
            for item in plan["queries"]:
                if item["query"] == text:
                    item["feature_ids"] = list(dict.fromkeys(item["feature_ids"] + ids))
            return
        seen.add(text)
        reason = "超过400字，未发送且未截断" if len(text) > MAX_QUERY_LENGTH else (
            "已达到8条查询预算，未发送" if len(plan["queries"]) >= MAX_QUERIES else "")
        if reason:
            plan["skipped"].append({"feature_ids": ids, "query": text, "kind": kind, "reason": reason})
        else:
            plan["queries"].append({"id": f"Q{len(plan['queries']) + 1}", "feature_ids": ids,
                                    "query": text, "kind": kind})

    for ids, text in sources:
        add(ids, text, "original")
    # A case-only variant adds no useful recall. Original queries remain exact:
    # mW and MW must never be merged into one feature-coverage record.
    variants = [(ids, [variant for variant in lexicon.expand_queries(text)[1:]
                       if lexicon.normalize(variant) != lexicon.normalize(text)])
                for ids, text in sources if len(text) <= MAX_QUERY_LENGTH]
    for index in range(3):
        for ids, texts in variants:
            if index < len(texts):
                add(ids, texts[index], "synonym_variant")
    return plan


def _terms(text: str, lexicon: SynonymLexicon) -> set[str]:
    normalized = lexicon.canonicalize(text)
    english = set(re.findall(r"[a-z0-9]+", normalized)) - {
        "a", "an", "the", "of", "to", "and", "or", "in", "on", "is", "are", "with", "has", "have", "when", "into", "by"}
    chinese = {part[i:i+2] for part in re.findall(r"[\u4e00-\u9fff]+", normalized) for i in range(len(part)-1)}
    return english | chinese


def lexical_hint(features: list[Feature], text: str, lexicon: SynonymLexicon) -> dict:
    terms = _terms(text, lexicon)
    overlap = {f.id: round(len(_terms(f.text, lexicon) & terms) / max(1, len(_terms(f.text, lexicon))), 4)
               for f in features}
    return {"score": round(sum(overlap.values()), 4), "feature_overlap": overlap,
            "meaning": "仅按标题/摘要词汇重合排序；不是相关性、披露或新颖性判断"}


def retrieve_with_journal(features: list[Feature], cutoff: str, query: str, lexicon: SynonymLexicon,
                          searcher, fetcher, max_documents: int) -> tuple[list, dict]:
    audit = {"schema_version": 1, "mode": "online", "input_hash": search_input_hash(features, cutoff),
             "started_at": now(), "query_budget": MAX_QUERIES, "results_per_query": RESULTS_PER_QUERY,
             "document_budget": max_documents, "synonym_groups": deepcopy(lexicon.groups),
             **query_plan(features, query, lexicon), "candidates": []}
    candidates: dict[str, dict] = {}
    for record in audit["queries"]:
        record.update(started_at=now(), status="error", results=[], returned_count=0, error="")
        try:
            raw = searcher(record["query"], RESULTS_PER_QUERY)
            if not isinstance(raw, list):
                raise ValueError("检索器未返回文献列表。")
            record["returned_count"] = len(raw)
            for item in raw[:RESULTS_PER_QUERY]:
                if not isinstance(item, dict):
                    record["results"].append({"validation_error": "检索结果不是文献对象"})
                    continue
                result = {key: str(item.get(key) or "") for key in ("title", "url", "content", "publication_number")}
                try:
                    result["url"] = google_patent_url(result["url"])
                    pub_id = result["url"].split("/patent/", 1)[1].split("/")[0]
                    result["publication_id"] = pub_id
                    candidate = candidates.setdefault(pub_id, {**result, "query_ids": [],
                        "lexical_hint": lexical_hint(features, result["title"] + " " + result["content"], lexicon),
                        "fetch_status": "not_selected", "fetch_error": ""})
                    if record["id"] not in candidate["query_ids"]:
                        candidate["query_ids"].append(record["id"])
                except ValueError as exc:
                    result["validation_error"] = str(exc)
                record["results"].append(result)
            record["status"] = "ok"
        except (RuntimeError, ValueError) as exc:
            record["error"] = str(exc)
        record["finished_at"] = now()
    # All planned queries run before any page budget can stop fetching.
    ordered = sorted(candidates.values(), key=lambda c: c["lexical_hint"]["score"], reverse=True)
    documents = []
    for candidate in ordered[:max_documents]:
        candidate["fetch_started_at"] = now()
        try:
            doc = fetcher(candidate["url"])
            if doc.id != candidate["publication_id"]:
                raise ValueError("正文公开号与检索来源不一致。")
            if doc.error or not doc.sections:
                raise ValueError(doc.error or "正文没有可核对段落。")
            documents.append(doc)
            candidate.update(fetch_status="fetched", snapshot_hash=doc.snapshot_hash)
        except (RuntimeError, ValueError) as exc:
            candidate.update(fetch_status="error", fetch_error=str(exc))
        candidate["fetch_finished_at"] = now()
    audit["candidates"] = ordered
    audit["finished_at"] = now()
    return documents, audit


def snapshot_journal(features: list[Feature], cutoff: str) -> dict:
    return {"schema_version": 1, "mode": "provided_snapshots", "input_hash": search_input_hash(features, cutoff),
            "queries": [], "candidates": [], "skipped": [],
            "scope_note": "仅比对提供的快照；本轮未执行在线检索，不能推断检索覆盖。"}


def search_warnings(audit: dict | None, features: list[Feature], cutoff: str) -> list[str]:
    if audit is None:  # Direct rule callers have an explicitly bounded snapshot comparison.
        return []
    if (not isinstance(audit, dict) or audit.get("schema_version") != 1 or audit.get("input_hash") != search_input_hash(features, cutoff)
            or audit.get("mode") not in {"online", "provided_snapshots"}):
        return ["检索记录缺失绑定或与当前要素/基准日不一致，不能沿用覆盖记录。"]
    if audit["mode"] == "provided_snapshots":
        return []
    warnings = []
    queries = audit.get("queries", [])
    if not queries or len(queries) > MAX_QUERIES:
        warnings.append("在线检索缺少有效的有界查询记录。")
    if audit.get("query_mode") != "per_feature":
        warnings.append("使用自定义检索词，逐要素检索覆盖尚未确认。")
    covered = set()
    for record in queries:
        if record.get("status") != "ok":
            warnings.append(f"{record['id']}检索失败：{record.get('error') or '未完成'}")
        else:
            covered.update(record.get("feature_ids", []))
            if not record.get("results"):
                warnings.append(f"{record['id']}未返回候选；空结果不证明没有相关技术。")
            if any(r.get("validation_error") for r in record.get("results", [])):
                warnings.append(f"{record['id']}含来源无效的候选，已保留记录。")
    missing = [f.id for f in features if f.id not in covered]
    if missing:
        warnings.append("以下要素没有成功发送并取得响应的独立查询：" + "、".join(missing))
    if audit.get("skipped"):
        warnings.append("存在因查询长度或预算未发送的查询，详见检索记录。")
    for candidate in audit.get("candidates", []):
        if candidate["fetch_status"] == "error":
            warnings.append(f"{candidate['publication_id']}正文获取失败：{candidate['fetch_error']}")
        elif candidate["fetch_status"] != "fetched":
            warnings.append(f"{candidate['publication_id']}未读取正文（文献预算限制），不能作为已核查。")
    if not audit.get("candidates"):
        warnings.append("Google Patents 没有返回可核对正文；不代表不存在相关现有技术。")
    return list(dict.fromkeys(warnings))
