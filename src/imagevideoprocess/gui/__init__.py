"""GUI 层（PySide6）：主窗口、功能列表、各功能工作台。"""

from __future__ import annotations

__all__ = ["run"]


def run(argv: list[str] | None = None) -> int:
    """启动图形界面（延迟导入，避免 import 包时就拉起 Qt）。"""
    from imagevideoprocess.gui.app import run as _run

    return _run(argv)
