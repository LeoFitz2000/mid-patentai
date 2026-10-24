"""同义词仅改善召回和提出候选对照；不自动证明技术披露或法律等同。"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path


class SynonymLexicon:
    def __init__(self, groups: list[list[str]] | None = None) -> None:
        if groups is None:
            path = Path(__file__).parents[1] / "config" / "synonyms.json"
            groups = json.loads(path.read_text(encoding="utf-8"))["groups"]
        self.groups = groups
        self.aliases: dict[str, str] = {}
        for group in groups:
            if len(group) < 2:
                raise ValueError("同义词组至少需要两个术语。")
            first = self.normalize(group[0])
            canonical = self.aliases.get(first, first)
            for alias in group:
                key = self.normalize(alias)
                if not key or (key in self.aliases and self.aliases[key] != canonical):
                    raise ValueError("同义词组存在空术语或冲突。")
                self.aliases[key] = canonical
        self._pattern = re.compile("|".join(
            (r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")
            if re.search(r"[a-z]", alias) else re.escape(alias)
            for alias in sorted(self.aliases, key=len, reverse=True)
        )) if self.aliases else None

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

    def canonicalize(self, text: str) -> str:
        value = self.normalize(text)
        # 一次替换避免把已替换内容再次改写；英文采用词边界，motor 不命中 motorized。
        return self._pattern.sub(lambda match: self.aliases[match.group()], value) if self._pattern else value

    def expand_queries(self, query: str, limit: int = 4, *, profile: str = "theoretical",
                       protected_terms: list[str] | None = None) -> list[str]:
        """按完整术语替换，保留原句、单位大小写和限定；LLM层由独立模块显式调用。"""
        from modules.novelty_models import Feature
        from modules.synonym_expansion import build_expansion_plan
        if type(limit) is not int or limit < 1:
            raise ValueError("扩展数量须为正整数。")
        if not query.strip():
            return []
        plan = build_expansion_plan([Feature("F1", query.strip())], self, profile, protected_terms)
        return [query.strip()] + [v["query"] for v in plan["variants"]][:limit-1]

    def candidate_match(self, feature: str, evidence: str) -> str:
        """只给检索提示。否定、数量和连接关系仍由整段原文与逐项复核检查。"""
        raw_feature = self.normalize(feature)
        raw_evidence = self.normalize(evidence)
        if raw_feature in raw_evidence:
            return "exact_text_candidate"
        if self.canonicalize(feature) in self.canonicalize(evidence):
            return "synonym_candidate"
        return "unresolved"
