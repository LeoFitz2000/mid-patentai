"""候选排序：组件覆盖、关系/限定线索及提及语境。分数不是相关性或披露结论。

原始词汇分数保留；规则只改变读取顺序，不删除候选。摘要不足时保持未知，
可由独立的模型元数据判断和后续正文逐项复核补充，不能借分数代填复核。
"""
from __future__ import annotations

import re
from statistics import mean
from decimal import Decimal

from modules.novelty_matching import SynonymLexicon
from modules.novelty_models import Feature

RANKING_VERSION = "relation-context-v1"
RELATIONS = {
    "connect": r"连接(?!器|件|头)|相连|\bconnect(?:ed|s)?\b|\bcoupl(?:ed|es|ing)\b",
    "fix": r"固定(?!件|座)|安装|装配|\bfix(?:ed|es|ing)?\b|\bmount(?:ed|s|ing)?\b|\bfasten\w*\b|\bfixture\b",
    "drive": r"驱动(?!轴|器|电机)|\bdriv(?:e|es|en|ing)\b",
    "control": r"控制(?!器|单元|模块)|\bcontrols?\b|\bcontrolled by\b",
    "include": r"包括|包含|\binclud\w*\b|\bcompris\w*\b",
    "series": r"串联|\bin series\b", "parallel": r"并联|\bin parallel\b",
}
NEGATION = r"不包括|不包含|不含|不连接|不启动|不控制|不驱动|没有|未连接|\bnot\b|\bwithout\b"
MENTION_ONLY = (r"(?:术语|名词|关键词|仅在|只在).{0,30}(?:目录|索引|引用|广告|购物)|"
                r"\bonly\b.{0,40}\b(?:index|bibliography|citation|keyword list)\b")


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    pattern = (r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])") if re.search("[a-z]", term) else re.escape(term)
    return re.search(pattern, text, re.IGNORECASE) is not None


def metadata_contexts(candidate: dict) -> list[dict]:
    """同一公开号可在多个查询返回不同摘要；去重文本，保留稳定出处编号。"""
    values = candidate.get("observations") or [{"id": "first", "title": candidate.get("title", ""),
        "content": candidate.get("content", ""), "query_id": ""}]
    contexts = {}
    for value in values:
        pair = (value.get("title", ""), value.get("content", ""))
        context = contexts.setdefault(pair, {"id": value.get("id", "first"), "title": pair[0], "content": pair[1], "query_ids": []})
        if value.get("query_id") and value["query_id"] not in context["query_ids"]:
            context["query_ids"].append(value["query_id"])
    return list(contexts.values())


def _relation(feature: str):
    for kind, pattern in RELATIONS.items():
        for match in re.finditer(pattern, feature, re.IGNORECASE):
            left, right = feature[:match.start()].strip(), feature[match.end():].strip()
            left = re.sub(r"^(?:该|所述|一种|the |a |an )", "", left, flags=re.IGNORECASE).strip()
            right = re.sub(r"^(?:于|到|在|至|to |the |a |an )", "", right, flags=re.IGNORECASE).strip()
            if left and right:
                return kind, left, right
    return None


def _concepts(feature: Feature, lexicon: SynonymLexicon, expansion: dict | None):
    text = lexicon.canonicalize(feature.text)
    concepts = {}
    relation_terms = {"连接", "串联", "并联"}
    for group in lexicon.groups:
        canonical = lexicon.canonicalize(group[0])
        if canonical not in relation_terms and _contains(text, canonical):
            concepts[canonical] = {canonical}
    relation = _relation(text)
    if relation:
        for side in relation[1:]:
            if not any(_contains(side, key) for key in concepts):
                concepts[side] = {side}
    for value in (expansion or {}).get("candidates", []):
        if value.get("feature_id") == feature.id and value.get("status") == "accepted":
            source, term = lexicon.canonicalize(value["source"]), lexicon.canonicalize(value["term"])
            if source not in relation_terms:
                concepts.setdefault(source, {source}).add(term)
    return concepts, relation


def _numeric_conflict(feature: str, text: str) -> bool:
    # 仅对列明的SI单位作精确换算，原文不改写；mW与MW大小写必须区分。
    complex_limit = r"\d\s*[-–—~～]\s*\d|至|以上|以下|范围|[<>≤≥]|\b(?:between|greater than|less than|at least|at most)\b"
    if re.search(complex_limit, feature, re.I) or re.search(complex_limit, text, re.I):
        return False  # 范围/不等式不按单值冲突处理，留给模型和正文复核。
    units = {"Pa": ("pressure", "1"), "kPa": ("pressure", "1000"), "MPa": ("pressure", "1000000"),
        "W": ("power", "1"), "mW": ("power", ".001"), "MW": ("power", "1000000"),
        "m": ("length", "1"), "cm": ("length", ".01"), "mm": ("length", ".001"),
        "Hz": ("frequency", "1"), "kHz": ("frequency", "1000"), "MHz": ("frequency", "1000000"),
        "°C": ("celsius", "1"), "%": ("percentage", "1")}
    pattern = r"(\d+(?:\.\d+)?)\s*(kPa|MPa|Pa|mW|MW|W|mm|cm|m|kHz|MHz|Hz|°C|%)(?![A-Za-z])"
    def values(value):
        return [(units[unit][0], Decimal(number) * Decimal(units[unit][1])) for number, unit in re.findall(pattern, value)]
    wanted, observed = values(feature), values(text)
    return any(any(kind == other_kind for other_kind, _ in observed) and (kind, number) not in observed
               for kind, number in wanted)


def rule_ranking_hint(features: list[Feature], candidate: dict, lexicon: SynonymLexicon,
                       expansion: dict | None = None) -> dict:
    feature_specs = [(f, *_concepts(f, lexicon, expansion)) for f in features]
    lexical = float(candidate.get("lexical_hint", {}).get("score", 0)) / max(1, len(features))
    source_is_indexing = any(re.search(r"索引|目录|引用|\b(?:index|directory|citation)\b", f.text, re.I) for f in features)
    results = []
    for context in metadata_contexts(candidate):
        raw = context["title"] + "\n" + context["content"]
        text = lexicon.canonicalize(raw)
        mention = not source_is_indexing and bool(re.search(MENTION_ONLY, raw, re.I))
        checks = []
        for feature, concepts, relation in feature_specs:
            coverage = (mean(any(_contains(text, alias) for alias in aliases) for aliases in concepts.values())
                        if concepts else lexical)
            relation_score, relation_state = 0.0, "unresolved"
            contradiction = False
            if relation:
                kind, left, right = relation
                for clause in re.split(r"[。；;\n]", text):
                    if _contains(clause, left) and _contains(clause, right):
                        relation_state, relation_score = "component_cooccurrence_only", max(relation_score, 0.25)
                        predicate = re.search(RELATIONS[kind], clause, re.I)
                        if predicate:
                            relation_state, relation_score = "relation_term_cooccurrence", max(relation_score, 0.45)
                            a, b = clause.find(left), clause.find(right)
                            passive = bool(re.match(r"(?:controlled|driven) by\b", clause[predicate.start():], re.I))
                            correct_order = b < predicate.start() < a if passive else a < predicate.start() < b
                            reversed_order = a < predicate.start() < b if passive else b < predicate.start() < a
                            if correct_order:
                                relation_state, relation_score = "ordered_relation_hint", 1.0
                            elif reversed_order and kind in {"control", "drive"}:
                                relation_state, contradiction = "reversed_relation_hint", True
                            if bool(re.search(NEGATION, lexicon.canonicalize(feature.text), re.I)) != bool(re.search(NEGATION, clause, re.I)):
                                relation_state, contradiction = "negation_conflict_hint", True
                        if kind in {"series", "parallel"} and re.search(RELATIONS["parallel" if kind == "series" else "series"], clause, re.I):
                            relation_state, contradiction = "connection_conflict_hint", True
            numeric = _numeric_conflict(feature.text, raw)
            checks.append({"feature_id": feature.id, "concept_coverage": round(coverage, 4),
                "relation_hint": relation_state, "relation_score": relation_score,
                "contradiction_hint": contradiction, "numeric_conflict_hint": numeric})
        component = mean(c["concept_coverage"] for c in checks) if checks else 0
        relation_score = mean(c["relation_score"] for c in checks) if checks else 0
        penalty = (0.65 if mention else 0) + (0.3 if any(c["contradiction_hint"] for c in checks) else 0) + (
            0.2 if any(c["numeric_conflict_hint"] for c in checks) else 0)
        score = max(0, 0.5 * component + 0.3 * lexical + 0.2 * relation_score - penalty)
        results.append({"score": round(score, 6), "context_id": context["id"], "mention_only_hint": mention,
            "feature_checks": checks, "component_coverage": round(component, 4), "penalty": penalty})
    best = max(results, key=lambda value: value["score"], default={"score": 0, "feature_checks": []})
    return {"version": RANKING_VERSION, **best, "contexts": results,
            "meaning": "规则排序线索，非已确认的相关性、技术关系、披露或新颖性概率"}


def rank_candidates(features: list[Feature], candidates: list[dict], lexicon: SynonymLexicon,
                     expansion: dict | None = None, metadata_reviews: dict | None = None) -> list[dict]:
    from modules.candidate_relevance import valid_metadata_review
    for candidate in candidates:
        candidate["ranking_hint"] = rule_ranking_hint(features, candidate, lexicon, expansion)
        review = (metadata_reviews or {}).get(candidate["publication_id"])
        candidate["metadata_relevance"] = review if valid_metadata_review(review, features, candidate) else None
    tier = {"related": 0, "unknown": 1, "unrelated": 2}
    # 模型未判定者与unknown同组；规则从不把unknown排除，所有候选仍保留。
    return sorted(candidates, key=lambda c: (tier.get((c.get("metadata_relevance") or {}).get("relevance"), 1),
        -c["ranking_hint"]["score"], -c.get("lexical_hint", {}).get("score", 0)))
