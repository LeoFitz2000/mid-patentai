"""Offline ranking eval against human-labeled relevant URLs.

Cases contain a fixed candidate corpus, so these metrics assess the ranker,
not the coverage of Google Patents or any other patent database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from modules.models import PatentRecord
from modules.similarity_engine import analyze


def evaluate(cases: list[dict], k: int = 3) -> dict[str, float | int]:
    if k < 1:
        raise ValueError("k 必须为正整数。")
    if not cases:
        raise ValueError("评测集不能为空。")
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    for case in cases:
        relevant = set(case["relevant_urls"])
        if not relevant:
            raise ValueError("每条评测案例都需要人工标注相关 URL。")
        records = [PatentRecord(**item) for item in case["records"]]
        ranked = analyze(case["query"], records).matches
        urls = [match.record.url for match in ranked]
        recalls.append(len(relevant.intersection(urls[:k])) / len(relevant))
        reciprocal_ranks.append(
            next((1.0 / (i + 1) for i, url in enumerate(urls) if url in relevant), 0.0)
        )
    return {
        "cases": len(cases),
        f"recall@{k}": round(sum(recalls) / len(recalls), 4),
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the local ranking baseline")
    parser.add_argument("cases", type=Path, help="JSON file with manually labeled cases")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    print(json.dumps(evaluate(cases, args.k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
