"""导出可复核报告：保留逐篇对照、时间基准、来源类型和原文快照哈希。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import quote as url_quote


def report_payload(state: dict, invention: str, cutoff: str, lexicon_groups: list) -> dict:
    return {
        "report_schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(), "task": "CN_novelty_precheck",
        "scope": "Google Patents；整套用户确认要素；不展开独立/从属权利要求",
        "cutoff": cutoff, "invention": invention,
        "features": [asdict(f) for f in state["features"]],
        "documents": [doc.to_dict() | {"snapshot_hash": doc.snapshot_hash} for doc in state["documents"]],
        "reviews": [asdict(review) for review in state.get("reviews", [])],
        "candidate_reviews": [asdict(review) for review in state.get("suggestions", [])],
        "decision": asdict(state["decision"]), "trace": state["trace"], "synonym_groups": lexicon_groups,
        "material_unknowns": state.get("material_unknowns", []),
        "material_warnings": state.get("material_warnings", []),
        "limits": ["未发现完整披露不等于可以授权。", "同义词匹配不证明技术披露或法律等同。",
                   "Google Patents 不包含全部非专利现有技术；日期、抵触申请、充分公开等须人工核验。"],
    }


def to_markdown(payload: dict) -> str:
    from modules.novelty_models import LABELS

    lines = ["# 新颖性预筛报告", "", f"结论：**{LABELS[payload['decision']['label']]}**",
             f"判断基准日：{payload['cutoff']}", f"范围：{payload['scope']}",
             "", "## 发明描述", payload["invention"], "", "## 已确认技术要素"]
    lines += [f"- {f['id']}：{f['text']}" for f in payload["features"]]
    lines += ["", "## 判断依据"] + [f"- {reason}" for reason in payload["decision"]["reasons"]]
    lines += ["", "## 缺口与待核验事项"] + [f"- {warning}" for warning in payload["decision"]["warnings"]]
    reviews = {item["document_id"]: item for item in payload["reviews"]}
    for doc in payload["documents"]:
        lines += ["", f"## {doc['id']} · {doc['title']}", f"来源：{doc['url']}",
                  f"公开日：{doc['publication_date'] or '未取得'}；申请日：{doc['filing_date'] or '未取得'}；"
                  f"优先权日：{doc['priority_date'] or '未取得'}",
                  f"资料类型：{doc['source_kind']}；快照格式：{doc.get('snapshot_schema_version', 1)}",
                  (f"完整性人工确认：{doc['complete']}；解析结构提示：{doc.get('parsed_complete', False)}"
                   if doc.get('snapshot_schema_version') == 2 else
                   f"历史完整性标记：{doc['complete']}（不自动视为新的人工确认）"),
                  f"快照 SHA-256：`{doc['snapshot_hash']}`"]
        sections = {section['id']: section for section in doc['sections']}
        review = reviews.get(doc["id"])
        if review:
            lines += [f"提交复核标记：{review['reviewed']}；同一方案确认：{review['same_scheme_confirmed']}；"
                      f"充分公开确认：{review['enabling_disclosure_confirmed']}",
                      f"复核人（自填）：{review.get('reviewer') or '未记录'}；提交时间：{review.get('reviewed_at') or '未记录'}",
                      f"复核输入绑定：`{review.get('input_hash') or '历史记录未绑定，须重新复核'}`",
                      f"同一方案说明：{review.get('same_scheme_basis') or '未提供'}；"
                      f"依据位置：{', '.join(review.get('scheme_section_ids', [])) or '未提供'}"]
            for row in review["rows"]:
                section = sections.get(row['section_id'], {})
                location = section.get('source_location') or f"旧版快照内部编号 {row['section_id']}（非原文权利要求号）"
                anchor = section.get('source_anchor')
                link = doc['url'] + ('#' + url_quote(anchor, safe='') if anchor else '')
                origin = {'auto': '自动定位候选', 'model': '模型候选', 'human': '人工填写'}.get(row.get('origin'), '历史来源未记录')
                lines += [f"- {row['feature_id']}：{row['status']}；原文位置=[{location}]({link})；内部ID={row['section_id']}；"
                          f"技术方案={row['scheme_id']}；引文来源={origin}；人工复核说明={row['basis'] or '未提供'}",
                          f"  引文：{row['quote'] or '未取得'}"]
    if payload.get('report_schema_version') == 2:
        lines += ["", "复核身份为操作人自行填写，系统不核验姓名或专业资质；候选建议另存于JSON，不等于最终复核。"]
    lines += ["", "## 执行记录", " → ".join(payload["trace"]), "", "## 适用边界"]
    lines += [f"- {limit}" for limit in payload["limits"]]
    if payload.get("material_case"):
        material = payload["material_case"]
        lines += ["", "## 原始材料案件", f"案件：{material['case_id']}",
                  f"材料清单 SHA-256：`{material['case_sha256']}`"]
        for attachment in material["attachments"]:
            lines += [f"- {attachment['name']}；SHA-256：`{attachment['sha256']}`"]
        preparation = payload.get("feature_preparation")
        if preparation:
            lines += ["", "AI 整理候选不等于人工复核；附件引文的语义支持仍须核查。"]
            if preparation.get("preparation_ref"):
                revision = preparation["preparation_ref"]
                lines += [f"整理版本：{revision['path']}；SHA-256：`{revision['sha256']}`"]
            if not payload.get("feature_preparation_matches_input", True):
                lines += ["当前要素已修改：以下出处属于原整理候选，不自动视为新要素的材料支持。"]
            for feature in preparation["features"]:
                for evidence in feature["evidence"]:
                    validation = {"verified_exact_text": "逐字引文已机器回查（不代表语义确认）",
                                  "not_machine_verified": "引文未机器校验"}.get(evidence.get("quote_validation"), "引文未机器校验")
                    lines += [f"- {feature['id']}：{evidence['source']} / {evidence['location']}；{validation}；原文：{evidence['quote']}"]
            lines += [f"- 材料未知项：{item}" for item in preparation["unknowns"]]
    lines += ["", "基础 eval 是单独的合成回归测试，不是本报告的专业正确性认证。"]
    return "\n\n".join(lines)
