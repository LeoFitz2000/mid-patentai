"""新颖性判断 skill：完整限定与同一方案，沿用现有CN预筛规则。"""
from modules.novelty_rules import assess_novelty
from modules.skill_contracts import make_record, document_sources


def run(features,documents,reviews,cutoff,**kwargs):
    decision=assess_novelty(features,documents,reviews,cutoff,**kwargs)
    return decision,record_decision(features,documents,reviews,cutoff,decision,kwargs)


def record_decision(features,documents,reviews,cutoff,decision,context=None):
    record=make_record("patent-novelty-assessment", {"features":features,"documents":documents,"reviews":reviews,
        "cutoff":cutoff,"context":context or {}}, decision, sources=document_sources(documents),
        note="证据不足也是业务结论；是否正确保留未知由独立语义裁判核验。")
    return record
