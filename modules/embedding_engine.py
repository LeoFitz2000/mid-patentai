"""A lightweight local TF-IDF baseline; it does not provide semantic embeddings."""

from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def vectorize(texts: list[str]) -> np.ndarray:
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("向量化输入不能为空。")
    # Character n-grams support both Chinese and English within one language.
    # They do not solve cross-language retrieval or semantic paraphrase.
    encoder = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), max_features=12000)
    return encoder.fit_transform(texts).toarray().astype(np.float32)
