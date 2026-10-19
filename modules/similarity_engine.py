"""Rank retrieved snippets by lexical vector similarity, without patentability labels."""

from __future__ import annotations

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from modules.embedding_engine import vectorize
from modules.models import AnalysisResult, PatentRecord, ScoredRecord


def analyze(query: str, records: list[PatentRecord]) -> AnalysisResult:
    if not query.strip():
        raise ValueError("检索词不能为空。")
    if not records:
        return AnalysisResult(vectors=np.empty((0, 0), dtype=np.float32), matches=())
    matrix = vectorize([query.strip()] + [item.text_for_vector for item in records])
    scores = cosine_similarity(matrix[:1], matrix[1:])[0]
    order = np.argsort(-scores, kind="stable")
    matches = tuple(
        ScoredRecord(records[int(i)], float(scores[int(i)])) for i in order
    )
    ordered_vectors = np.vstack((matrix[:1], matrix[1:][order]))
    return AnalysisResult(vectors=ordered_vectors, matches=matches)
