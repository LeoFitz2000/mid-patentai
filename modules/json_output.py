"""Minimal JSON extraction and strict field checks for generated text."""

from __future__ import annotations

import json


def parse_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            cleaned = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("模型未返回有效 JSON；请重试。") from exc
    if not isinstance(data, dict):
        raise ValueError("模型 JSON 顶层必须是对象。")
    return data


def required_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"模型结果缺少有效字段：{key}。")
    return value.strip()
