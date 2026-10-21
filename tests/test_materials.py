"""Persistence, source binding and Streamlit handoff regression checks."""
from __future__ import annotations

import hashlib
import json
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from modules.material_cases import (case_folder, load_case, load_prepared_features,
                                    reference, save_case, save_result)

ROOT = Path(__file__).resolve().parents[1]


def fixture_root() -> Path:
    root = ROOT / "tests" / ".artifacts" / uuid.uuid4().hex / "cases"
    root.mkdir(parents=True)
    return root


def prepare(root: Path, saved: dict, text="压力传感器连接控制器") -> dict:
    data = {"case_id": saved["case_id"], "case_sha256": saved["case_sha256"],
            "features": [{"id": "F1", "text": text, "evidence": [
                {"source": "idea", "location": "用户描述", "quote": "压力传感器连接控制器"}]}],
            "unknowns": ["供电方式未确定"]}
    (case_folder(root, saved["case_id"]) / "prepared_features.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


class MaterialPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture_root()

    def test_attachment_bytes_paths_hashes_and_unique_cases(self):
        saved = save_case(self.root, "", [("../../材料.txt", b"original bytes")])
        other = save_case(self.root, "", [("../../材料.txt", b"original bytes")])
        self.assertNotEqual(saved["case_id"], other["case_id"])
        case = load_case(self.root, saved["case_id"])
        self.assertFalse(case["ai_execution_started"])
        item = case["files"][0]
        path = case_folder(self.root, saved["case_id"]) / item["path"]
        self.assertEqual(path.parent, case_folder(self.root, saved["case_id"]))
        self.assertEqual(path.read_bytes(), b"original bytes")
        self.assertEqual(item["sha256"], hashlib.sha256(b"original bytes").hexdigest())

    def test_invalid_uploads_create_no_ready_case(self):
        for idea, files in [("", []), ("", [("x.exe", b"a")]),
                            ("", [("x.txt", b"")]), ("x" * 30001, []),
                            ("", [("x.txt", b"a")] * 9)]:
            with self.subTest(idea=idea[:10], files=len(files)), self.assertRaises(ValueError):
                save_case(self.root, idea, files)
        self.assertEqual(list(self.root.glob("*/case.json")), [])

    def test_tampered_attachment_and_escaping_manifest_are_rejected(self):
        saved = save_case(self.root, "测试", [("x.txt", b"original")])
        folder = case_folder(self.root, saved["case_id"])
        manifest = folder / "case.json"
        case = json.loads(manifest.read_text(encoding="utf-8"))
        (folder / case["files"][0]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            reference(self.root, saved["case_id"])
        case["files"][0]["path"] = "../elsewhere.txt"
        manifest.write_text(json.dumps(case), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_case(self.root, saved["case_id"])

    def test_prepared_features_require_current_material_and_source_quotes(self):
        saved = save_case(self.root, "压力传感器连接控制器，供电方式未定。", [])
        data = prepare(self.root, saved)
        loaded = load_prepared_features(self.root, saved["case_id"])
        self.assertEqual(loaded["feature_text"], "压力传感器连接控制器")
        self.assertEqual(loaded["review_status"], "agent_proposal_not_human_review")
        path = case_folder(self.root, saved["case_id"]) / "prepared_features.json"
        data["features"][0]["evidence"][0]["quote"] = "已经完成样机测试"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_prepared_features(self.root, saved["case_id"])
        data = prepare(self.root, saved)
        data["case_sha256"] = "stale"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_prepared_features(self.root, saved["case_id"])

    def test_results_are_separate_versions_and_leave_input_immutable(self):
        saved = save_case(self.root, "测试方案", [])
        manifest = case_folder(self.root, saved["case_id"]) / "case.json"
        before = manifest.read_bytes()
        payload = {"material_case": saved, "decision": {"label": "insufficient_evidence"}}
        a = save_result(self.root, saved["case_id"], payload, "第一轮")
        b = save_result(self.root, saved["case_id"], payload, "第二轮")
        self.assertNotEqual(a, b)
        self.assertEqual((a / "report.md").read_text(encoding="utf-8"), "第一轮")
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(len((self.root / "events.jsonl").read_text().splitlines()), 2)
        payload["material_case"] = saved | {"case_sha256": "stale"}
        with self.assertRaises(ValueError):
            save_result(self.root, saved["case_id"], payload, "不应保存")


class MaterialAppTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture_root()
        self.env = patch.dict(os.environ, {"PATENT_CASES_DIR": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT / "app.py")).run(timeout=60)

    @staticmethod
    def labeled(elements, label):
        return next(item for item in elements if item.label == label)

    def save_in_app(self, app):
        self.labeled(app.text_area, "你的技术想法（与附件至少提供一项）").set_value(
            "压力传感器连接控制器，供电方式未定。")
        self.labeled(app.button, "保存材料，交给 AI 整理").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        return app.session_state["active_material_case"]

    def test_saving_does_not_call_model_or_search_and_can_reopen(self):
        with patch("skills.langgraph_skill.search_patents") as search, patch("modules.llm_client.LLMClient.complete") as model:
            app = self.app()
            saved = self.save_in_app(app)
            self.assertEqual(self.labeled(app.text_area, "确认待判断的技术要素（每行一个）").value, "")
            self.assertFalse(load_case(self.root, saved["case_id"])["ai_execution_started"])
            fresh = self.app()
            self.labeled(fresh.button, "打开已保存案件").click().run(timeout=60)
            self.assertEqual(len(fresh.exception), 0)
            self.assertEqual(fresh.session_state["active_material_case"]["case_id"], saved["case_id"])
            search.assert_not_called()
            model.assert_not_called()

    def test_prepared_features_join_existing_workflow_and_result_persistence(self):
        app = self.app()
        saved = self.save_in_app(app)
        prepare(self.root, saved)
        self.labeled(app.button, "载入 AI 整理的要素").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.labeled(app.text_area, "确认待判断的技术要素（每行一个）").value, "压力传感器连接控制器")
        self.labeled(app.text_input, "Google Patents 单篇链接").set_value("https://patents.google.com/patent/US123/en")
        self.labeled(app.text_input, "公开日期 YYYY-MM-DD").set_value("2023-01-01")
        self.labeled(app.text_area, "原文（空行分段，不要只粘贴搜索摘要）").set_value("压力传感器连接控制器。")
        self.labeled(app.button, "加入人工原文快照").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["novelty_state"]["decision"].label, "insufficient_evidence")
        self.labeled(app.button, "保存本轮结果到案件").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        exported = list(case_folder(self.root, saved["case_id"]).glob("results/*/evidence.json"))
        self.assertEqual(len(exported), 1)
        payload = json.loads(exported[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["material_case"], saved)
        self.assertEqual(payload["feature_preparation"]["unknowns"], ["供电方式未确定"])
        self.assertFalse(payload["reviews"])

    def test_missing_preparation_is_explicit_and_new_case_clears_old_features(self):
        app = self.app()
        saved = self.save_in_app(app)
        self.labeled(app.button, "载入 AI 整理的要素").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("尚未找到" in item.value for item in app.info))
        prepare(self.root, saved)
        self.labeled(app.button, "载入 AI 整理的要素").click().run(timeout=60)
        self.labeled(app.text_area, "你的技术想法（与附件至少提供一项）").set_value("第二个独立方案")
        self.labeled(app.button, "保存材料，交给 AI 整理").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.labeled(app.text_area, "确认待判断的技术要素（每行一个）").value, "")
        self.assertNotEqual(app.session_state["active_material_case"]["case_id"], saved["case_id"])


if __name__ == "__main__":
    unittest.main()
