"""应用入口：创建 QApplication、套上样式表、打开主窗口。

- ``uv run imagevideoprocess``  → 走这里
- ``uv run python -m imagevideoprocess`` → 同样走这里
- 打包成 exe 后双击 → 同样走这里

环境自检界面已移到命令行：``uv run python -m imagevideoprocess.core.envreport``。
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import imagevideoprocess as pkg
from imagevideoprocess.core.paths import processed_dir
from imagevideoprocess.gui.theme import STYLESHEET, light_palette


def _app_icon() -> QIcon | None:
    """打包时随附的图标（有就用，没有就跳过）。"""
    candidates: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / "assets" / "app.ico")
    candidates.append(Path(__file__).resolve().parents[3] / "assets" / "app.ico")
    for candidate in candidates:
        if candidate.is_file():
            return QIcon(str(candidate))
    return None


def _configure_environment() -> None:
    """打包运行时的一些环境微调。"""
    # 高 DPI 缩放交给 Qt 6 自己处理；避免 Qt 把 4K 屏幕上的界面画得过小
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    # 确保「exe 同级的 processed 文件夹」一开始就存在（需求要求）。
    # 只读目录（例如装在 Program Files）下不阻塞启动，任务执行时再报错。
    with contextlib.suppress(OSError):
        processed_dir(create=True)


def run(argv: Sequence[str] | None = None) -> int:
    """创建 QApplication、显示主窗口并进入事件循环，返回退出码。"""
    _configure_environment()

    app = QApplication(list(argv) if argv else [])
    app.setApplicationName(pkg.APP_NAME)
    app.setApplicationDisplayName(pkg.APP_NAME)
    app.setApplicationVersion(pkg.__version__)
    app.setOrganizationName(pkg.APP_NAME)
    app.setStyle("Fusion")
    # ⚠️ 顺序不能反：先套调色板再套样式表。
    # 调色板负责「样式表没覆盖到」的控件（QMessageBox、下拉弹出层、QToolTip 等），
    # 缺了它，Windows 深色模式下这些控件会变暗，与亮色界面撞色（字看不清）。
    app.setPalette(light_palette())
    app.setStyleSheet(STYLESHEET)

    icon = _app_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    from imagevideoprocess.gui.main_window import MainWindow

    window = MainWindow()
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()

    # 支持把文件路径当命令行参数传进来（例如把文件拖到 exe 图标上打开）
    file_args = [arg for arg in (argv or [])[1:] if not arg.startswith("-")]
    if file_args:
        window.activate_file(Path(file_args[0]))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run(sys.argv))
