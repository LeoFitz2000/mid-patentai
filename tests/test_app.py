"""真实 Streamlit 运行测试：首屏、人工快照、外发确认与输入变更。"""

from __future__ import annotations

import unittest
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def labeled(elements, label):
    return next(item for item in elements if item.label == label)


class AppFlowTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=60)

    def manual_snapshot(self, app, body="该装置不包括压力传感器。"):
        labeled(app.text_area, "发明描述").set_value("测试装置包含压力传感器。")
        labeled(app.text_area, "确认待判断的技术要素（每行一个）").set_value("压力传感器")
        app.date_input[0].set_value(date(2024, 1, 1))
        labeled(app.text_input, "Google Patents 单篇链接").set_value("https://patents.google.com/patent/US123/en")
        labeled(app.text_input, "文献标题").set_value("教学测试快照")
        labeled(app.text_input, "公开日期 YYYY-MM-DD").set_value("2023-01-01")
        labeled(app.text_area, "原文（空行分段，不要只粘贴搜索摘要）").set_value(body)
        app.run(timeout=60)  # 浏览器输入发生后先重绘，按钮才会从 disabled 变为可点击。
        labeled(app.button, "加入人工原文快照").click().run(timeout=60)
        return app

    def test_first_screen_has_no_network_or_paid_model_call(self):
        with patch("skills.langgraph_skill.search_patents") as search, patch("modules.llm_client.LLMClient.complete") as model:
            app = self.app()
            self.assertEqual(len(app.exception), 0)
            search.assert_not_called()
            model.assert_not_called()
            self.assertTrue(labeled(app.button, "1 · 检索 Google Patents 并定位证据").disabled)

    def test_manual_evidence_does_not_auto_judge_or_send_model(self):
        with patch("skills.langgraph_skill.search_patents") as search, patch("modules.llm_client.LLMClient.complete") as model:
            app = self.manual_snapshot(self.app())
            self.assertEqual(len(app.exception), 0)
            state = app.session_state["novelty_state"]
            self.assertEqual(state["decision"].label, "insufficient_evidence")
            self.assertEqual(state["suggestions"][0].rows[0].status, "unknown")
            self.assertTrue(labeled(app.button, "生成待复核对照").disabled)
            search.assert_not_called()
            model.assert_not_called()

    def test_changed_features_invalidate_old_report(self):
        app = self.manual_snapshot(self.app())
        labeled(app.text_area, "确认待判断的技术要素（每行一个）").set_value("温度传感器").run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(any(element.value == "预筛结果" for element in app.subheader))

    def test_offline_basic_eval_button_works_without_model(self):
        app = self.app()
        labeled(app.button, "运行三个 skill 的基础 eval").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.session_state["basic_eval_report"]["all_passed"])

    def test_model_is_called_only_after_payload_confirmation(self):
        response = json.dumps({"reviews": [{"document_id": "US123", "rows": [
            {"feature_id": "F1", "status": "unknown", "section_id": "manual-1",
             "quote": "该装置不包括压力传感器。", "scheme_id": "", "basis": "negation_needs_review"}
        ]}]}, ensure_ascii=False)
        with patch("modules.llm_client.LLMClient.complete", return_value=response) as model:
            app = self.manual_snapshot(self.app())
            labeled(app.sidebar.text_input, "模型 API Key（可选）").set_value("test-key").run(timeout=60)
            self.assertTrue(labeled(app.button, "生成待复核对照").disabled)
            model.assert_not_called()
            labeled(app.checkbox, "我确认将上述要素和选定原文发送到此模型服务").set_value(True).run(timeout=60)
            self.assertFalse(labeled(app.button, "生成待复核对照").disabled)
            labeled(app.button, "生成待复核对照").click().run(timeout=60)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(app.session_state["novelty_state"]["decision"].label, "insufficient_evidence")
            self.assertFalse(app.session_state["novelty_state"]["suggestions"][0].reviewed)

    def test_reviewed_suggestion_produces_report_and_changed_confirmation_invalidates_it(self):
        app = self.manual_snapshot(self.app(), "该装置包括压力传感器。")
        state = app.session_state["novelty_state"]
        suggestion = state["suggestions"][0]
        row = replace(suggestion.rows[0], status="disclosed", quote="压力传感器", scheme_id="scheme1")
        state["suggestions"] = [replace(suggestion, rows=(row,))]
        app.session_state["novelty_state"] = state
        app.session_state["review_epoch"] = 20
        app.run(timeout=60)
        for label in ["确认快照内容完整，已保留相关上下文",
                      "我已逐项核对披露状态与引文（not_found 仅代表本次文献未找到）",
                      "全部已披露要素属于同一技术方案，并非不同实施例的拼接",
                      "确认相关披露可实施，且同义表述的技术含义和限定一致"]:
            labeled(app.checkbox, label).set_value(True)
        app.run(timeout=60)
        labeled(app.button, "3 · 根据已复核对照进行新颖性预筛").click().run(timeout=60)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["novelty_state"]["decision"].label, "potential_novelty_risk")
        self.assertTrue(any(item.value == "预筛结果" for item in app.subheader))
        labeled(app.checkbox, "我已逐项核对披露状态与引文（not_found 仅代表本次文献未找到）").set_value(False).run(timeout=60)
        self.assertFalse(any(item.value == "预筛结果" for item in app.subheader))


if __name__ == "__main__":
    unittest.main()
