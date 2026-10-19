"""Boundary guard for the external-generation stage."""

from __future__ import annotations

from modules.models import ScoredRecord


def require_confirmation(confirmed: bool, selected: list[tuple[str, ScoredRecord]]) -> None:
    if not confirmed:
        raise PermissionError("必须先由用户确认外部模型发送内容。")
    if not selected:
        raise ValueError("必须至少选择一条可追溯的参考文献。")
