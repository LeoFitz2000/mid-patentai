"""提交前检查：只输出可疑文件和行号，不打印疑似密钥内容。"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


PATTERNS = [
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="检查暂存区实际内容")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached"], cwd=root).split(b"\0")
    failures = []
    count = 0
    for raw in names:
        if not raw:
            continue
        name = raw.decode("utf-8")
        if args.staged:
            content = subprocess.check_output(["git", "show", ":" + name], cwd=root)
        else:
            content = (root / name).read_bytes()
        count += 1
        for line_no, line in enumerate(content.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                failures.append((name, line_no))
    if failures:
        for name, line_no in failures:
            print(f"Potential secret: {name}:{line_no}; value omitted")
        return 1
    print(f"Secret scan passed: {count} tracked files; no credential values printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
