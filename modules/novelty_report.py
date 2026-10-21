"""导出可复核报告：保留逐篇对照、时间基准、来源类型和原文快照哈希。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone


def report_payload(state: dict, invention: str, cutoff: str, lexicon_groups: list) -> dict:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(), "task": "CN_novelty_precheck",
        "scope": "Google Patents；整套用户确认要素；不展开独立/从属权利要求",
        "cutoff": cutoff, "invention": invention,
        "features": [asdict(f) for f in state["features"]],
        "documents": [doc.to_dict() | {"snapshot_hash": doc.snapshot_hash} for doc in state["documents"]],
        "reviews": [asdict(review) for review in state.get("reviews", [])],
        "decision": asdict(state["decision"]), "trace": state["trace"], "synonym_groups": lexicon_groups,
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
                  f"资料类型：{doc['source_kind']}；完整性人工/解析标记：{doc['complete']}",
                  f"快照 SHA-256：`{doc['snapshot_hash']}`"]
        review = reviews.get(doc["id"])
        if review:
            lines += [f"人工复核：{review['reviewed']}；同一方案确认：{review['same_scheme_confirmed']}；"
                      f"充分公开确认：{review['enabling_disclosure_confirmed']}"]
            for row in review["rows"]:
                lines += [f"- {row['feature_id']}：{row['status']}；原文位置={row['section_id']}；"
                          f"技术方案={row['scheme_id']}；匹配依据={row['basis']}", f"  引文：{row['quote'] or '未取得'}"]
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
            for feature in preparation["features"]:
                for evidence in feature["evidence"]:
                    lines += [f"- {feature['id']}：{evidence['source']} / {evidence['location']}；原文：{evidence['quote']}"]
            lines += [f"- 材料未知项：{item}" for item in preparation["unknowns"]]
    lines += ["", "基础 eval 是单独的合成回归测试，不是本报告的专业正确性认证。"]
    return "\n\n".join(lines)
