from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PatentRecord:
    title: str
    snippet: str
    url: str
    source: str

    @property
    def text_for_vector(self) -> str:
        return f"{self.title}. {self.snippet}".strip()


@dataclass(frozen=True)
class ScoredRecord:
    record: PatentRecord
    similarity: float


@dataclass(frozen=True)
class AnalysisResult:
    # Row 0 is the invention/search query; subsequent rows match `matches` order.
    vectors: np.ndarray
    matches: tuple[ScoredRecord, ...]

    @property
    def max_similarity(self) -> float | None:
        return self.matches[0].similarity if self.matches else None


@dataclass(frozen=True)
class Improvement:
    category: str
    suggestion: str
    rationale: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class PatentDraft:
    title: str
    abstract: str
    background: str
    summary: str
    description: str
    claims: tuple[str, ...]
