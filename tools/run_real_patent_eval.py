"""Real public source regression: no paid models, fabricated human review or preset labels."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.real_patent_eval import fetch_sources, real_cases, run_real_evaluation, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="新目录，不覆盖历史记录")
    parser.add_argument("--fetch-sources", action="store_true", help="显式获取两篇公开页面到新来源目录")
    parser.add_argument("--references", type=Path, help="独立参考记录；在预测保存后读取")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("输出目录已存在，请使用新的运行目录。")
    if args.fetch_sources:
        fetch_sources(args.source_dir, real_cases(ROOT)[2])
    report = run_real_evaluation(ROOT, args.source_dir, args.output_dir, args.references)
    write_json(args.output_dir / "runtime.json", {"python": sys.executable, "python_version": sys.version,
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "command": sys.argv, "model_called": False, "human_review_created": False})
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
