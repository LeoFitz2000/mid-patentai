"""Immutable intake adapted from LeoFitz2000/patent-precheck; no model calls."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import date, datetime
from pathlib import Path

from modules.novelty_models import parse_features

MAX_FILES = 8
MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
CASE_ID = re.compile(r"case-\d{8}-\d{6}-[a-f0-9]{12}")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def save_case(root: Path, idea: str, files: list[tuple[str, bytes]],
              cutoff: str | None = None) -> dict:
    if not isinstance(idea, str) or len(idea) > 30000:
        raise ValueError("想法须为文字，最多 30000 字。")
    if len(files) > MAX_FILES or sum(len(raw) for _, raw in files) > MAX_BYTES:
        raise ValueError("最多 8 份附件，合计 10 MB。")
    if cutoff:
        date.fromisoformat(cutoff)
    prepared = []
    for index, (name, raw) in enumerate(files, 1):
        name = re.split(r"[\\/]", name)[-1]
        name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
        suffix = Path(name).suffix.lower()
        if suffix not in EXTENSIONS or not isinstance(raw, bytes) or not raw:
            raise ValueError("附件须为非空的 PDF、DOCX、TXT、MD 或常见图片。")
        stem = Path(name).stem[:90].strip(" .") or "材料"
        prepared.append((f"{index:02d}-{stem}{suffix}", raw))
    if not idea.strip() and not prepared:
        raise ValueError("请描述想法或至少上传一份材料。")
    case_id = "case-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(6)
    folder = Path(root) / case_id
    folder.mkdir(parents=True)
    attachments = []
    for name, raw in prepared:
        with (folder / name).open("xb") as stream:
            stream.write(raw)
        attachments.append({"name": name, "path": name, "bytes": len(raw), "sha256": digest(raw)})
    case = {"schema_version": "patent-material-case-1", "case_id": case_id,
            "saved_at": now(), "input_status": "ready", "idea": idea.strip(),
            "goal": "CN_novelty_precheck", "cutoff_date": cutoff,
            "files": attachments, "ai_execution_started": False}
    write_json(folder / "case.json", case)
    return reference(root, case_id)


def case_folder(root: Path, case_id: str) -> Path:
    if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
        raise ValueError("案件编号格式不正确。")
    base = Path(root).resolve()
    folder = (base / case_id).resolve()
    if folder.parent != base:
        raise ValueError("案件目录越出材料目录。")
    return folder


def load_case(root: Path, case_id: str) -> dict:
    folder = case_folder(root, case_id)
    case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    if case.get("case_id") != case_id:
        raise ValueError("案件清单编号不一致。")
    for item in case["files"]:
        path = (folder / item["path"]).resolve()
        if path.parent != folder or path.name != item["path"]:
            raise ValueError("附件路径越出案件目录。")
        raw = path.read_bytes()
        if digest(raw) != item["sha256"] or len(raw) != item["bytes"]:
            raise ValueError("附件哈希不一致，停止沿用该案件。")
    return case


def reference(root: Path, case_id: str) -> dict:
    case = load_case(root, case_id)
    return {"case_id": case_id,
            "case_sha256": digest((case_folder(root, case_id) / "case.json").read_bytes()),
            "attachments": case["files"]}


def load_prepared_features(root: Path, case_id: str) -> dict:
    """Load Agent proposals with source anchors; do not mark human review."""
    current = reference(root, case_id)
    original = load_case(root, case_id)
    folder = case_folder(root, case_id)
    data = json.loads((folder / "prepared_features.json").read_text(encoding="utf-8"))
    if data.get("case_id") != case_id or data.get("case_sha256") != current["case_sha256"]:
        raise ValueError("要素文件对应的案件或材料版本不一致。")
    rows = data.get("features")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError("整理结果须包含 1–30 条技术要素。")
    sources = {"idea"} | {item["path"] for item in current["attachments"]}
    for index, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or row.get("id") != f"F{index}"
                or not isinstance(row.get("text"), str) or not row["text"].strip()
                or any(char in row["text"] for char in "\r\n；;")
                or not isinstance(row.get("evidence"), list) or not row["evidence"]):
            raise ValueError("每个要素须有连续编号、单行文字与原材料出处。")
        for evidence in row["evidence"]:
            if (not isinstance(evidence, dict) or evidence.get("source") not in sources
                    or not isinstance(evidence.get("location"), str) or not evidence["location"].strip()
                    or not isinstance(evidence.get("quote"), str) or not evidence["quote"].strip()):
                raise ValueError("要素出处须指向本案件材料并记录位置和原文。")
            if evidence["source"] == "idea" and evidence["quote"] not in original["idea"]:
                raise ValueError("要素引用无法回查用户描述。")
    text = "\n".join(row["text"].strip() for row in rows)
    if len(parse_features(text)) != len(rows):
        raise ValueError("要素重复或长度超限，请重新整理。")
    unknowns = data.get("unknowns", [])
    if not isinstance(unknowns, list) or any(not isinstance(x, str) for x in unknowns):
        raise ValueError("未知项须为文字列表。")
    return {"feature_text": text, "features": rows, "unknowns": unknowns,
            "review_status": "agent_proposal_not_human_review"}


def save_result(root: Path, case_id: str, payload: dict, markdown: str) -> Path:
    current = reference(root, case_id)
    if payload.get("material_case") != current:
        raise ValueError("报告与当前材料版本不一致，不能保存到该案件。")
    folder = case_folder(root, case_id) / "results" / (
        "run-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4))
    folder.mkdir(parents=True)
    write_json(folder / "evidence.json", payload)
    with (folder / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(markdown)
    event = {"case_id": case_id, "phase": "report_saved", "at": now(),
             "result": folder.relative_to(Path(root).resolve()).as_posix(),
             "decision": payload["decision"]["label"]}
    with (Path(root) / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return folder
