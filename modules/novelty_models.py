"""新颖性链路的数据契约：原文、候选匹配与人工复核分开保存。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import urlparse


LABELS = {
    "potential_novelty_risk": "发现单篇文献完整披露风险（预筛）",
    "no_complete_disclosure_found": "本次已复核文献中未发现完整披露",
    "insufficient_evidence": "证据不足，需要补充或复核",
    "out_of_scope": "超出本工具的新颖性范围",
}


def google_patent_url(url: str) -> str:
    """只接收 Google Patents 单篇页面，不允许相似域名或任意外部地址。"""
    parsed = urlparse(url.strip())
    if (parsed.scheme != "https" or parsed.hostname != "patents.google.com"
            or parsed.port not in {None, 443} or parsed.username or parsed.password
            or not re.fullmatch(r"/patent/[A-Za-z0-9]+(?:/[a-zA-Z-]+)?/?", parsed.path)):
        raise ValueError("来源必须是 https://patents.google.com/patent/公开号 的单篇页面。")
    return f"https://patents.google.com{parsed.path.rstrip('/')}"


@dataclass(frozen=True)
class Feature:
    id: str
    text: str


def parse_features(text: str) -> list[Feature]:
    """按用户确认的整套要素逐行读取，保留句内连接关系、否定词和数值。

    不自动按逗号拆分，防止把“传感器连接控制器”拆成两个无关系的名词。
    当前不解析独立/从属权利要求依赖，也不推测用户遗漏的必要特征。
    """
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.、）)])\s*", "", line).strip()
             for line in re.split(r"[\r\n；;]+", text)]
    lines = [line for line in lines if line]
    if not lines or len(lines) > 30 or any(len(line) > 1500 for line in lines):
        raise ValueError("请逐行填写 1–30 个技术要素，每个不超过 1500 字，并保留关系和限定。")
    return [Feature(f"F{i}", value) for i, value in enumerate(dict.fromkeys(lines), 1)]


@dataclass(frozen=True)
class SourceSection:
    id: str
    text: str


@dataclass(frozen=True)
class PatentDocument:
    id: str
    title: str
    url: str
    publication_date: str
    sections: tuple[SourceSection, ...]
    filing_date: str = ""
    priority_date: str = ""
    source_kind: str = "google_patents_page"
    retrieved_at: str = ""
    complete: bool = False
    error: str = ""

    @property
    def snapshot_hash(self) -> str:
        # 日期也是判断输入，所以不仅对正文做哈希。
        raw = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "PatentDocument":
        data = dict(value)
        expected_hash = data.pop("snapshot_hash", None)
        data["sections"] = tuple(SourceSection(**item) for item in data.get("sections", []))
        document = cls(**data)
        if expected_hash is not None and document.snapshot_hash != expected_hash:
            raise ValueError("证据快照哈希不匹配，不能沿用原复核记录。")
        return document


@dataclass(frozen=True)
class EvidenceRow:
    feature_id: str
    status: str = "unknown"  # disclosed / not_found / unknown
    section_id: str = ""
    quote: str = ""
    scheme_id: str = ""  # 同一文献中同一技术方案；不得拼接互斥实施例。
    basis: str = "unreviewed"

    def __post_init__(self) -> None:
        # 表格清空文本单元格时 Streamlit 可能返回 None，按空证据处理而不是崩溃。
        for key in ("feature_id", "status", "section_id", "quote", "scheme_id", "basis"):
            value = getattr(self, key)
            if value is None:
                object.__setattr__(self, key, "")
            elif not isinstance(value, str):
                raise ValueError(f"要素对照的 {key} 必须是文本。")


@dataclass(frozen=True)
class DocumentReview:
    document_id: str
    rows: tuple[EvidenceRow, ...]
    reviewed: bool = False
    same_scheme_confirmed: bool = False
    enabling_disclosure_confirmed: bool = False


@dataclass
class NoveltyDecision:
    label: str
    reasons: list[str]
    document_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return LABELS[self.label]


def check_cutoff(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("判断基准日必须为 YYYY-MM-DD；有优先权时请人工确定适用基准日。") from exc
