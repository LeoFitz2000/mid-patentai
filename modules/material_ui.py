"""Material intake and conversation handoff inside the existing Streamlit UI."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from modules.material_cases import load_case, load_prepared_features, reference, save_case


def cases_root() -> Path:
    return Path(os.getenv("PATENT_CASES_DIR", str(Path(__file__).parents[1] / ".local" / "cases")))


def render_material_intake() -> None:
    with st.expander("先交材料：描述想法或上传附件", expanded=True):
        idea = st.text_area("你的技术想法（与附件至少提供一项）", key="intake_idea",
                            placeholder="想解决什么问题？准备怎样做？未确定的地方可以直接说明。")
        uploads = st.file_uploader("已有材料（最多 8 份，合计 10 MB）", accept_multiple_files=True,
            type=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg"], key="intake_uploads")
        st.caption("原始材料保存在本机。保存不调用模型，也不表示附件已解析；回到此整合项目的 AI 对话说“开始初筛”，由 AI 整理。")
        if st.button("保存材料，交给 AI 整理"):
            try:
                saved = save_case(cases_root(), idea, [(f.name, f.getvalue()) for f in uploads])
                st.session_state["active_material_case"] = saved
                st.session_state["invention_input"] = idea.strip()
                st.session_state["feature_text_input"] = ""
                st.session_state.pop("prepared_material_features", None)
                st.session_state.pop("novelty_state", None)
                st.session_state.pop("novelty_signature", None)
                st.success("材料已保存。请在此整合项目的 AI 对话中说“开始初筛”。")
            except (OSError, ValueError, TypeError) as exc:
                st.error(str(exc))
        recent = sorted(cases_root().glob("case-*/case.json"), reverse=True)[:20]
        if recent:
            selected = st.selectbox("已保存的案件", [p.parent.name for p in recent])
            if st.button("打开已保存案件"):
                try:
                    case = load_case(cases_root(), selected)
                    st.session_state["active_material_case"] = reference(cases_root(), selected)
                    st.session_state["invention_input"] = case["idea"]
                    st.session_state["feature_text_input"] = ""
                    for key in ("prepared_material_features", "novelty_state", "novelty_signature"):
                        st.session_state.pop(key, None)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    st.error(str(exc))
        active = st.session_state.get("active_material_case")
        if active:
            try:
                if reference(cases_root(), active["case_id"]) != active:
                    raise ValueError("原始材料已变化，请重新保存案件。")
                st.caption(f"当前案件：{active['case_id']}。AI 整理完成后，点击下方按钮接入现有流程。")
                if st.button("载入 AI 整理的要素"):
                    prepared = load_prepared_features(cases_root(), active["case_id"])
                    case = load_case(cases_root(), active["case_id"])
                    st.session_state["invention_input"] = case["idea"]
                    st.session_state["feature_text_input"] = prepared["feature_text"]
                    st.session_state["prepared_material_features"] = prepared
                    st.session_state.pop("novelty_state", None)
                    st.session_state.pop("novelty_signature", None)
                    st.success("已载入 AI 整理候选，可继续检索。此状态不等同人工复核或最终专利判断。")
                prepared = st.session_state.get("prepared_material_features")
                if prepared:
                    for unknown in prepared["unknowns"]:
                        st.warning("材料未知项：" + unknown)
                    with st.expander("查看要素的材料出处"):
                        st.json(prepared["features"])
            except FileNotFoundError:
                st.info("尚未找到本案件的 AI 整理结果，请在整合项目的对话中接手。")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                st.error(str(exc))
