"""图标助手：优先用 qtawesome 的字体图标，拿不到就退回文字。"""

from __future__ import annotations

from PySide6.QtGui import QIcon

from imagevideoprocess.gui.theme import ACCENT


def icon(name: str, color: str = ACCENT) -> QIcon | None:
    """按名字取一个字体图标；qtawesome 不可用时返回 None。"""
    try:
        import qtawesome as qta

        return qta.icon(name, color=color)
    except Exception:  # pragma: no cover - 缺图标库时静默降级
        return None
