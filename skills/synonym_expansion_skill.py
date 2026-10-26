"""术语扩展 skill：执行已有的候选、保护限定与显式审核契约。"""
from modules.synonym_expansion import build_expansion_plan, generate_llm_candidates
from modules.skill_contracts import make_record


def run(features, lexicon, profile="engineering", protected_terms=None, generated=None, approved_ids=None):
    plan = build_expansion_plan(features, lexicon, profile, protected_terms, generated, approved_ids)
    return plan, record_plan(features, lexicon, plan)


def record_plan(features, lexicon, plan):
    return make_record("patent-synonym-expansion", {"features":features,"dictionary":lexicon.groups,
        "policy":plan.get("policy"),"protected_terms":plan.get("protected_terms",[])}, plan,
        producer="model_candidates_and_explicit_filter" if plan.get("generation",{}).get("status")=="ok" else "dictionary_and_explicit_filter")


def generate(*args, **kwargs):
    return generate_llm_candidates(*args, **kwargs)
