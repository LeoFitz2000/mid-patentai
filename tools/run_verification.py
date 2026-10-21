"""Run current engineering tests and retained legacy compatibility tests with separate counts."""
import argparse
import json
import sys
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def group_tests(suite):
    groups = {"current_engineering": [], "legacy_compatibility": []}

    def visit(item):
        if isinstance(item, unittest.TestSuite):
            for child in item:
                visit(child)
        else:
            key = "legacy_compatibility" if item.id().startswith(("test_workflow.", "tests.test_workflow.")) else "current_engineering"
            groups[key].append(item)
    visit(suite)
    return {key: unittest.TestSuite(values) for key, values in groups.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="每次使用新目录")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    groups = group_tests(unittest.defaultTestLoader.discover(str(ROOT / "tests")))
    summary = {"scope": "engineering_and_legacy_compatibility_not_patent_accuracy", "groups": {},
               "python": sys.executable, "python_version": sys.version, "command": sys.argv,
               "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "overlap_note": "当前工程测试内部会调用合成eval；另行34条合成结果不能与此处相加为独立样本。"}
    for key, suite in groups.items():
        count = suite.countTestCases()
        with (args.output_dir / f"{key}.txt").open("x", encoding="utf-8") as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        summary["groups"][key] = {"count": count, "passed": result.wasSuccessful(),
                                   "failures": len(result.failures), "errors": len(result.errors)}
    summary["all_engineering_checks_passed"] = all(v["passed"] for v in summary["groups"].values())
    (args.output_dir / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary["all_engineering_checks_passed"] else 1)


if __name__ == "__main__":
    main()
