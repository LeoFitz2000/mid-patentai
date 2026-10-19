"""General technical-background search and deterministic completeness prompts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import requests


TAVILY_URL = "https://api.tavily.com/search"
PATENT_DOMAINS = [
    "patents.google.com",
    "patents.uspto.gov",
    "patentscope.wipo.int",
    "worldwide.espacenet.com",
    "lens.org",
]


@dataclass(frozen=True)
class InformationAssessment:
    sufficient: bool
    questions: tuple[str, ...]


def search_background(
    query: str,
    api_key: str,
    max_results: int = 5,
    post: Callable = requests.post,
) -> list[dict]:
    """Search general technical context; patent-office sites are excluded."""
    if not query.strip():
        raise ValueError("请先填写发明描述。")
    if not api_key.strip():
        raise ValueError("请配置 Tavily API Key，用于基础信息检索。")

    payload = {
        "api_key": api_key.strip(),
        "query": query.strip()[:1000],
        "search_depth": "basic",
        "exclude_domains": PATENT_DOMAINS,
        "max_results": max(1, min(max_results, 10)),
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        response = post(TAVILY_URL, json=payload, timeout=(5, 30))
        response.raise_for_status()
        results = response.json().get("results")
    except requests.RequestException as exc:
        raise RuntimeError("基础信息检索失败；请检查网络、Tavily 密钥或额度。") from exc
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError("Tavily 返回了无法解析的结果。") from exc
    if not isinstance(results, list):
        raise RuntimeError("Tavily 返回的结果格式不正确。")
    return results


_INFORMATION_DIMENSIONS = (
    (
        ("技术问题", "现有方案", "现有技术", "痛点", "缺陷", "不足", "problem", "challenge", "shortcoming"),
        "要解决的技术问题是什么？现有方案具体有哪些不足？",
    ),
    (
        (
            "通过", "采用", "利用", "包括", "包含", "模块", "组件", "结构", "装置", "系统", "方法", "步骤", "算法",
            "工作原理", "工作流程", "运行流程", "输入", "输出", "响应", "采集", "检测", "处理", "执行", "当", "首先", "然后",
            "mechanism", "component", "comprises", "module", "workflow", "input", "output", "process", "operation",
        ),
        "核心结构、组件或算法是什么？系统在什么输入或条件下按什么步骤运行，各部分如何配合？",
    ),
    (
        ("提高", "降低", "减少", "提升", "改善", "避免", "增强", "缩短", "节省", "效率", "精度", "性能", "效果", "从而", "使得", "improve", "reduce", "increase", "effect", "performance"),
        "相对于现有方案，预期改善什么效果？有可量化的指标或例子吗？",
    ),
)


def assess_information(description: str) -> InformationAssessment:
    """Ask about missing technical dimensions without sending data to an LLM."""
    text = " ".join(description.split())
    folded = text.casefold()
    if len(text) < 35:
        return InformationAssessment(
            sufficient=False,
            questions=("请再用几句话说明技术问题、核心实现方式和预期效果。",),
        )

    questions = [
        question
        for terms, question in _INFORMATION_DIMENSIONS
        if not any(term.casefold() in folded for term in terms)
    ][:3]
    return InformationAssessment(sufficient=not questions, questions=tuple(questions))
