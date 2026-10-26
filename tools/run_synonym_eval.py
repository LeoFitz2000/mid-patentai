"""离线对比原词、词典、原始LLM候选与审核后扩展；输出新JSON和Markdown。"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.synonym_eval import evaluation_markdown, run_synonym_evaluation, ranking_comparison, ranking_comparison_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/synonym_retrieval_cases.json")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--compare-rankers", action="store_true", help="固定查询/成本，另存旧词汇与新关系排序对照")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".local/evaluations" /
                        ("synonym-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")))
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("输出目录已存在，不覆盖历史评测。")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = run_synonym_evaluation(dataset, args.k)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "evaluation.md").write_text(evaluation_markdown(report), encoding="utf-8")
    if args.compare_rankers:
        comparison = ranking_comparison(dataset, args.k)
        (args.output_dir / "ranking_comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output_dir / "ranking_comparison.md").write_text(ranking_comparison_markdown(comparison), encoding="utf-8")
    print(json.dumps({"provenance": report["provenance"], "comparisons": report["comparisons"],
                      "output": str(args.output_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
