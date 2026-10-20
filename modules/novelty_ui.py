"""新颖性界面：检索/粘贴原文 → 候选对照 → 人工复核 → 有边界的预筛报告。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

from modules.google_patent_documents import manual_google_document
from modules.llm_client import LLMClient
from modules.material_cases import reference, save_result
from modules.material_ui import cases_root, render_material_intake
from modules.novelty_matching import SynonymLexicon
from modules.novelty_models import DocumentReview, EvidenceRow, review_content, stamp_review
from modules.novelty_review import adopt_candidate_quotes, edited_review_rows, empty_review_rows
from modules.novelty_report import report_payload, to_markdown
from skills.langgraph_skill import NoveltyHarness, model_suggest_rows


def fingerprint(*items: str) -> str:
    return hashlib.sha256("\x1f".join(items).encode("utf-8")).hexdigest()[:20]


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    st.set_page_config(page_title="Google Patents 新颖性预筛", page_icon="🔎", layout="wide")
    st.title("🔎 Google Patents 新颖性预筛")
    st.caption("CNIPA 新颖性规则 · 逐篇证据对照 · 同义词召回 · 每个 skill 都有基础 eval")
    with st.sidebar:
        st.header("检索与模型设置")
        max_documents = st.slider("最多获取文献数", 1, 10, 4)
        api_key = st.text_input("模型 API Key（可选）", value=os.getenv("LLM_API_KEY", ""), type="password")
        base_url = st.text_input("模型 API 地址", value=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
        model = st.text_input("模型名", value=os.getenv("LLM_MODEL", "deepseek-flash"))
        with st.expander("补充领域同义词"):
            extra_synonyms = st.text_area("每行一组，用 | 分隔", placeholder="术语甲 | 同义术语 | English term")
            st.caption("用于检索召回和候选定位，不代表法律等同。优先添加具体领域、含义一致的术语。")
        if st.button("运行三个 skill 的基础 eval"):
            try:
                from skills.deepeval_skill import run_basic_evals
                with st.spinner("运行离线合成回归…"):
                    st.session_state["basic_eval_report"] = run_basic_evals()
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))
        if "basic_eval_report" in st.session_state:
            evaluation = st.session_state["basic_eval_report"]
            st.write(evaluation["summary"])
            st.caption("这是教学合成题回归结果，不是实际专利准确率。")
            st.download_button("下载基础 eval 记录", json.dumps(evaluation, ensure_ascii=False, indent=2),
                               "basic_eval.json", "application/json")

    lexicon = SynonymLexicon()
    if extra_synonyms.strip():
        try:
            groups = [[word.strip() for word in line.split("|") if word.strip()]
                      for line in extra_synonyms.splitlines() if line.strip()]
            lexicon = SynonymLexicon(lexicon.groups + groups)
        except ValueError as exc:
            st.error(str(exc))
            return
    render_material_intake()
    invention = st.text_area("发明描述", key="invention_input", placeholder="描述完整技术方案；保留结构、连接关系、步骤、条件和数值。", height=110)
    feature_text = st.text_area("确认待判断的技术要素（每行一个）", height=130,
                                key="feature_text_input",
                                placeholder="压力传感器\n压力传感器连接控制器\n控制器通过无线通信模块发送数据")
    cutoff = st.date_input("判断基准日", value=datetime.now(ZoneInfo("Asia/Shanghai")).date()).isoformat()
    query = st.text_input("Google Patents 检索词（可选）")
    st.caption("先按整套要素评估，不区分独立/从属权利要求。基准日及优先权适用性由你确认。")
    st.info("检索会把检索词发送到 Google Patents。只有另行确认后，选定要素和原文才会发送到模型。")
    prepared = st.session_state.get("prepared_material_features")
    material_context = {"material_unknowns": list(prepared.get("unknowns", [])) if prepared else [],
                        "material_warnings": list(prepared.get("warnings", [])) if prepared else []}
    if prepared and prepared["feature_text"] != feature_text:
        material_context["material_warnings"].append("当前要素已修改，原整理出处不能自动证明新要素的材料支持。")
    material_identity = {"case": st.session_state.get("active_material_case"),
                         "preparation": prepared.get("preparation_ref") if prepared else None,
                         **material_context}
    signature = fingerprint(invention, feature_text, cutoff, query, str(max_documents),
                            json.dumps(lexicon.groups, ensure_ascii=False),
                            json.dumps(material_identity, ensure_ascii=False, sort_keys=True))
    harness = NoveltyHarness(lexicon=lexicon, max_documents=max_documents)
    state = st.session_state.get("novelty_state") if st.session_state.get("novelty_signature") == signature else None

    if st.button("1 · 检索 Google Patents 并定位证据", type="primary", disabled=not feature_text.strip()):
        st.session_state.pop("novelty_state", None)
        try:
            with st.spinner("扩展同义词、检索文献并读取原文…"):
                state = harness.run(feature_text=feature_text, query=query, cutoff=cutoff, **material_context)
            st.session_state["novelty_state"] = state
            st.session_state["novelty_signature"] = signature
            st.session_state["review_epoch"] = 0
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))

    with st.expander("网页无法访问时：粘贴 Google Patents 原文快照"):
        manual_url = st.text_input("Google Patents 单篇链接")
        manual_title = st.text_input("文献标题")
        manual_pub = st.text_input("公开日期 YYYY-MM-DD")
        manual_filing = st.text_input("申请日期（可选）")
        manual_priority = st.text_input("优先权日期（可选）")
        manual_body = st.text_area("原文（空行分段，不要只粘贴搜索摘要）", height=150)
        manual_complete = st.checkbox("我确认已粘贴待比对的完整相关权利要求和说明书，保留了上下文限定")
        if st.button("加入人工原文快照", disabled=not feature_text.strip()):
            try:
                document = manual_google_document(manual_url, manual_title, manual_pub, manual_body,
                                                  manual_filing, manual_priority, manual_complete)
                documents = [doc for doc in (state or {}).get("documents", []) if doc.id != document.id] + [document]
                state = harness.run(feature_text=feature_text, query=query, cutoff=cutoff, documents=documents,
                                    errors=(state or {}).get("errors", []), **material_context)
                st.session_state["novelty_state"] = state
                st.session_state["novelty_signature"] = signature
                st.session_state["review_epoch"] = st.session_state.get("review_epoch", 0) + 1
            except (RuntimeError, ValueError) as exc:
                st.error(str(exc))
    if state is None:
        st.caption("可直接人工录入 Google Patents 原文，无需配置模型密钥。修改输入后需重新建立对照。")
        return

    st.divider()
    st.subheader("2 · 查看原文与候选对照")
    for error in state.get("errors", []):
        st.warning(error)
    for doc in state["documents"]:
        with st.expander(f"{doc.id} · {doc.title}"):
            st.link_button("打开 Google Patents 来源", doc.url)
            st.write(f"公开日：{doc.publication_date or '未取得'}；来源类型：{doc.source_kind}")
            for section in doc.sections:
                location = section.source_location or "旧版快照内部编号（非原文权利要求号）"
                st.text(f"[{section.id}] {location}：{section.text}")
    if state.get("hits"):
        st.dataframe(state["hits"], hide_index=True, width="stretch")
    st.caption("候选匹配分数不是新颖性概率。相似术语、否定句、连接方向及数值差异都要回看原文。")

    with st.expander("可选：让模型提出对照建议"):
        options = {doc.id: doc for doc in state["documents"]}
        selected = st.multiselect("发送给模型的文献", list(options), default=list(options)[:2], max_selections=3)
        st.caption("模型将收到全部已确认要素及所选文献快照中的所有段落。总长度超过 5 万字时拒绝发送。")
        consent_payload = json.dumps({"features": [asdict(f) for f in state["features"]],
            "documents": [{"document_id": key, "sections": [asdict(s) for s in options[key].sections]}
                          for key in selected]}, ensure_ascii=False, sort_keys=True)
        consent_key = fingerprint(consent_payload, base_url, model)
        consent = st.checkbox("我确认将上述要素和选定原文发送到此模型服务", key=f"model-consent-{consent_key}")
        if st.button("生成待复核对照", disabled=not (consent and selected and api_key.strip())):
            try:
                with st.spinner("生成并校验原文引文…"):
                    suggestions = model_suggest_rows(state["features"], [options[key] for key in selected],
                                                     LLMClient(api_key, base_url, model), consent)
                merged = {review.document_id: review for review in state["suggestions"]}
                merged.update({review.document_id: review for review in suggestions})
                state["suggestions"] = list(merged.values())
                state["reviews"] = []
                state["decision"] = harness.run(features=state["features"], cutoff=cutoff,
                                                documents=state["documents"], errors=state.get("errors", []),
                                                **material_context)["decision"]
                st.session_state["review_epoch"] = st.session_state.get("review_epoch", 0) + 1
            except (RuntimeError, ValueError, PermissionError) as exc:
                st.error(str(exc))

    pending_reviews = []
    checked_documents = []
    suggestions_by_id = {review.document_id: review for review in state["suggestions"]}
    committed_by_id = {review.document_id: review for review in state.get("reviews", [])}
    reviewer = st.text_input("复核人姓名或代号（自行填写）", key="reviewer_alias").strip()
    st.caption("此处记录操作人自填身份与提交时刻，不核验姓名、资质或执业身份。")
    for doc in state["documents"]:
        st.markdown(f"**复核 {doc.id}**")
        st.caption("disclosed=原文披露；not_found=本篇未找到；unknown=无法确定。同一技术方案使用相同方案编号，勿合并不同实施例。")
        content_key = fingerprint(signature, replace(doc, complete=False).snapshot_hash,
                                  str(st.session_state.get("review_epoch", 0)))
        candidates = suggestions_by_id[doc.id].rows
        with st.expander(f"候选建议（未确认） · {doc.id}"):
            st.dataframe([asdict(row) for row in candidates], hide_index=True, width="stretch")
        draft_key = f"review-draft-{content_key}"
        if draft_key not in st.session_state:
            st.session_state[draft_key] = empty_review_rows(state["features"])
        draft_rows = st.session_state[draft_key]
        initial_rows = [asdict(row) for row in draft_rows]
        editor_epoch_key = f"editor-epoch-{content_key}"
        editor_key = f"chart-{content_key}-{st.session_state.get(editor_epoch_key, 0)}"
        edited = st.data_editor(initial_rows, hide_index=True, width="stretch", num_rows="fixed",
            key=editor_key, disabled=["feature_id", "origin"],
            column_config={"status": st.column_config.SelectboxColumn("披露状态", options=["disclosed", "not_found", "unknown"], required=True),
                           "quote": st.column_config.TextColumn("逐字原文引文"),
                           "section_id": st.column_config.TextColumn("原文位置"),
                           "scheme_id": st.column_config.TextColumn("同一技术方案编号"),
                           "basis": st.column_config.TextColumn("人工复核说明（状态改变时更新）"),
                           "origin": st.column_config.TextColumn("引文来源")})
        prior = committed_by_id.get(doc.id)
        rows = edited_review_rows(edited, prior.rows if prior else draft_rows)
        selected_quotes = st.multiselect(f"采纳哪些要素的候选引文 · {doc.id}",
                                         [row.feature_id for row in candidates if row.quote.strip()],
                                         key=f"adopt-selection-{content_key}")
        if st.button(f"采纳所选候选引文 · {doc.id}", disabled=not selected_quotes):
            st.session_state[draft_key] = adopt_candidate_quotes(rows, candidates, selected_quotes)
            st.session_state[editor_epoch_key] = st.session_state.get(editor_epoch_key, 0) + 1
            st.session_state[f"review-{content_key}"] = False
            st.rerun()
        sections_by_id = {section.id: section for section in doc.sections}
        for row in rows:
            if row.status in {"disclosed", "not_found"} and not row.basis.strip():
                st.warning(f"{row.feature_id}：请填写或更新人工复核说明，旧说明不能自动沿用到新状态。")
            section = sections_by_id.get(row.section_id)
            if section and row.quote.strip() and row.quote.strip() == section.text.strip():
                st.warning(f"{row.feature_id}：引文等于整段原文，请核对是否真正支持全部关系和限定。")
        scheme_basis = st.text_area(f"同一技术方案的原文依据 · {doc.id}", key=f"scheme-basis-{content_key}")
        scheme_sections = st.multiselect(f"同一方案依据位置 · {doc.id}", list(sections_by_id),
            format_func=lambda key: f"{key} · {sections_by_id[key].source_location or '快照内部位置'}",
            key=f"scheme-sections-{content_key}")
        if doc.parsed_complete:
            st.caption("解析器发现了权利要求和说明书；这仅是结构提示，不代表相关上下文完整。")
        complete = st.checkbox("确认快照内容完整，已保留相关上下文", value=False, key=f"complete-{content_key}")
        edit_signature = fingerprint(json.dumps([asdict(row) for row in rows], ensure_ascii=False),
                                     str(complete), reviewer, scheme_basis, json.dumps(scheme_sections))
        last_edit_key = f"last-review-edit-{content_key}"
        if last_edit_key in st.session_state and st.session_state[last_edit_key] != edit_signature:
            for prefix in ("review", "scheme", "enabling"):
                st.session_state[f"{prefix}-{content_key}"] = False
        st.session_state[last_edit_key] = edit_signature
        reviewed = st.checkbox("我已逐项核对披露状态与引文（not_found 仅代表本次文献未找到）", key=f"review-{content_key}")
        same_scheme = st.checkbox("全部已披露要素属于同一技术方案，并非不同实施例的拼接", key=f"scheme-{content_key}")
        enabling = st.checkbox("确认相关披露可实施，且同义表述的技术含义和限定一致", key=f"enabling-{content_key}")
        pending_reviews.append(DocumentReview(doc.id, rows, reviewed, same_scheme, enabling,
                                              reviewer=reviewer, same_scheme_basis=scheme_basis,
                                              scheme_section_ids=tuple(scheme_sections)))
        checked_documents.append(replace(doc, complete=complete))

    if st.button("3 · 根据已复核对照进行新颖性预筛"):
        try:
            candidates = state["suggestions"]
            submitted = [stamp_review(review, state["features"], doc, cutoff)
                         for review, doc in zip(pending_reviews, checked_documents)]
            state = harness.run(features=state["features"], cutoff=cutoff, documents=checked_documents,
                                reviews=submitted, errors=state.get("errors", []), **material_context)
            state["suggestions"] = candidates
            st.session_state["novelty_state"] = state
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
    if state.get("reviews") and (
        [review_content(review) for review in state["reviews"]] != [review_content(review) for review in pending_reviews]
        or [doc.complete for doc in state["documents"]] != [doc.complete for doc in checked_documents]
    ):
        st.info("对照或复核确认已改变，请点击第 3 步重新预筛后再导出报告。")
        return
    st.divider()
    st.subheader("预筛结果")
    decision = state["decision"]
    st.write(f"**{decision.text}**")
    for reason in decision.reasons:
        st.write(reason)
    for warning in decision.warnings:
        st.warning(warning)
    payload = report_payload(state, invention, cutoff, lexicon.groups)
    active_case = st.session_state.get("active_material_case")
    case_ready = False
    if active_case:
        try:
            current_case = reference(cases_root(), active_case["case_id"])
            if current_case != active_case:
                raise ValueError("材料版本已变化，请重新保存并建立对照。")
            payload["material_case"] = current_case
            prepared = st.session_state.get("prepared_material_features")
            if prepared:
                payload["feature_preparation"] = prepared
                payload["feature_preparation_matches_input"] = prepared["feature_text"] == feature_text
            case_ready = True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            st.error(str(exc))
            return
    st.session_state["last_generated_report"] = payload
    st.download_button("下载新颖性 Markdown 报告", to_markdown(payload), "novelty_report.md", "text/markdown")
    st.download_button("下载证据快照与判断记录 JSON", json.dumps(payload, ensure_ascii=False, indent=2),
                       "novelty_evidence.json", "application/json")
    if case_ready and st.button("保存本轮结果到案件"):
        try:
            saved_path = save_result(cases_root(), active_case["case_id"], payload, to_markdown(payload))
            st.success(f"本轮结果已单独保存：{saved_path.name}。原始材料和以前的结果保持不变。")
        except (OSError, ValueError) as exc:
            st.error(str(exc))
    st.caption("本次未发现完整披露不等于具备新颖性或可以授权。资料范围仅为本次取得的 Google Patents 文献。")
