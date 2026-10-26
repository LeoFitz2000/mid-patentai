"""同义词四层流程的界面；新术语审核仅授权查询，不是人工专利结论。"""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from modules.llm_client import LLMClient
from modules.novelty_models import parse_features
from modules.synonym_expansion import PROFILES, build_expansion_plan, generate_llm_candidates


def render_synonym_expansion(feature_text, lexicon, api_key, base_url, model):
    with st.expander("同义词四层扩展与检索评测", expanded=False):
        profile = st.selectbox("专利检索类型", list(PROFILES), index=1,
                               format_func=lambda key: PROFILES[key]["label"])
        policy = PROFILES[profile]
        st.caption(f"{policy['label']}：最多{policy['query_budget']}条查询，每要素最多{policy['variants_per_feature']}个变体；"
                   f"最多组合{policy['combination_width']}个独立术语。类型由你按当前技术内容选择。")
        protected = [x.strip() for x in st.text_area("保护术语（每行一个，不做替换）",
            placeholder="Kalman\n某标准编号或算法专名").splitlines() if x.strip()]
        st.caption("第一层使用预定义词典；第二层可选LLM生成中英文和缩写；第三层拦截语义漂移及限定变化。"
                   "词典外的新词需明确审核才进入查询，未审核项不自动当同义词。")
        try:
            features = parse_features(feature_text) if feature_text.strip() else []
        except ValueError as exc:
            st.warning(str(exc))
            return None
        payload = {"features": [asdict(f) for f in features], "profile": profile,
                   "protected_terms": protected, "dictionary_groups": lexicon.groups}
        signature = hashlib.sha256(json.dumps([payload, base_url.strip(), model.strip()],
                                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
        consent = st.checkbox("我确认将技术要素、保护术语和词典发送到模型生成扩展候选",
                              key=f"synonym-consent-{signature}")
        st.json(payload, expanded=False)
        cache_key = f"synonym-generation-{signature}"
        if st.button("生成中英文同义词候选", disabled=not (features and consent and api_key.strip())):
            st.session_state.pop(cache_key, None)
            try:
                with st.spinner("生成候选并检查术语与限定…"):
                    st.session_state[cache_key] = generate_llm_candidates(features, lexicon, profile, protected,
                        LLMClient(api_key, base_url, model), consent)
            except (ValueError, RuntimeError, PermissionError) as exc:
                st.error(str(exc))
        generated = st.session_state.get(cache_key)
        plan = build_expansion_plan(features, lexicon, profile, protected, generated) if features else None
        if generated:
            if generated["status"] == "error":
                st.error("候选生成失败，保留词典方案：" + generated.get("error", "未取得有效候选"))
            st.caption("本次候选生成成本（未知用量不填零）：")
            st.json(generated["cost"], expanded=False)
        pending = {c["id"]: c for c in (plan or {}).get("candidates", []) if c["status"] == "pending"}
        candidate_signature = hashlib.sha256(json.dumps((generated or {}).get("candidates", []),
            ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        approved = st.multiselect("审核后允许用于查询的新增术语", list(pending),
            format_func=lambda key: f"{pending[key]['feature_id']} · {pending[key]['source']} → {pending[key]['term']} · {pending[key]['rationale']}",
            key=f"synonym-approved-{signature}-{candidate_signature}")
        approval_signature = hashlib.sha256(json.dumps([signature, approved, (generated or {}).get("candidates", [])],
            ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
        confirmation = st.checkbox("我已核对所选新增术语在当前要素中的技术含义和限定",
                                    key=f"synonym-approved-confirm-{approval_signature}")
        if plan and approved and confirmation:
            plan = build_expansion_plan(features, lexicon, profile, protected, generated, approved)
        if plan:
            st.dataframe(plan["candidates"], hide_index=True, width="stretch")
            st.caption(f"本轮有{len(plan['variants'])}个候选查询变体；按原要素优先、类型预算发送，多余或超长查询另行记录。")
            st.download_button("下载同义词扩展与审核记录", json.dumps(plan, ensure_ascii=False, indent=2),
                               "synonym_expansion.json", "application/json")
        st.caption("第四层比较相同题目、K、排序器及最大查询预算下的Recall@K、Precision@K和成本；词多不代表效果好。")
        if st.button("运行同义词扩展示例 Eval（离线）"):
            from modules.synonym_eval import run_synonym_evaluation, ranking_comparison
            dataset = json.loads((Path(__file__).parents[1] / "evals/synonym_retrieval_cases.json").read_text(encoding="utf-8"))
            st.session_state["synonym-eval-result"] = run_synonym_evaluation(dataset, 3)
            st.session_state["synonym-ranking-comparison"] = ranking_comparison(dataset, 3)
        if "synonym-eval-result" in st.session_state:
            from modules.synonym_eval import evaluation_markdown
            evaluation = st.session_state["synonym-eval-result"]
            st.warning("这是4个作者编写的合成固定检索池，含改善与变差情形；没有调用模型或Google，不证明真实检索效果改善。")
            st.dataframe([{"案例": row["id"], "类型": row["profile"], "方案": arm,
                "Recall@K": value["metrics"]["recall_at_k"], "Precision@K": value["metrics"]["precision_at_k"],
                "查询数": value["cost"]["planned_search_queries"]}
                for row in evaluation["cases"] for arm, value in row["arms"].items()], hide_index=True, width="stretch")
            st.download_button("下载同义词评测报告", evaluation_markdown(evaluation), "synonym_evaluation.md", "text/markdown")
            comparison = st.session_state.get("synonym-ranking-comparison")
            if comparison:
                from modules.synonym_eval import ranking_comparison_markdown
                st.caption("旧词汇排序与新规则排序使用相同查询、候选池、标签和成本。新增相关文献单独计数，排序修复不等于产生新增收益。")
                st.dataframe([{"案例": r["case_id"], "方案": r["arm"], "旧Recall@K": r["before"]["recall_at_k"],
                    "新Recall@K": r["after"]["recall_at_k"], "旧Precision@K": r["before"]["precision_at_k"],
                    "新Precision@K": r["after"]["precision_at_k"], "新增相关": len(r["increment"]["new_relevant_ids"])
                    if r["increment"]["new_relevant_ids"] is not None else None} for r in comparison["rows"]],
                    hide_index=True, width="stretch")
                st.download_button("下载候选排序前后对照", ranking_comparison_markdown(comparison), "ranking_comparison.md", "text/markdown")
        return plan
