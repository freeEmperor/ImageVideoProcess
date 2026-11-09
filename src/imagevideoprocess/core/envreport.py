"""环境自检：列出当前 venv 里各处理库的版本与可用性。

GUI 启动时调用一次，用于确认 uv 环境完整；也用于排障。
"""

from __future__ import annotations

import importlib.metadata as md
import platform
import sys
from dataclasses import dataclass

#: 关心的依赖：(显示名, 发行包名, 备注)
TRACKED: tuple[tuple[str, str, str], ...] = (
    ("opencv-contrib-python", "opencv-contrib-python", "图像/视频 I/O + 基础算法"),
    ("Pillow", "Pillow", "位图编解码、EXIF"),
    ("numpy", "numpy", "ndarray 运算"),
    ("imageio", "imageio", "统一读写后端"),
    ("imageio-ffmpeg", "imageio-ffmpeg", "内置 FFmpeg 可执行文件"),
    ("av (PyAV)", "av", "FFmpeg 绑定，精确抽帧/转码"),
    ("scipy", "scipy", "滤波/插值"),
    ("scikit-image", "scikit-image", "高质量缩放、质量指标"),
    ("pillow-heif", "pillow-heif", "HEIC/HEIF/AVIF"),
    ("PySide6", "PySide6", "GUI"),
    ("pyqtgraph", "pyqtgraph", "直方图/曲线"),
    ("qtawesome", "qtawesome", "图标"),
    ("send2trash", "send2trash", "删除到回收站"),
    ("typer", "typer", "命令行入口"),
    ("rich", "rich", "终端输出/进度条"),
    ("pywin32", "pywin32", "Windows 原生 API"),
    ("PyInstaller", "pyinstaller", "打包 exe"),
    ("Nuitka", "nuitka", "打包 exe（编译式）"),
)


@dataclass(frozen=True)
class DepStatus:
    """单个依赖的状态。"""

    display: str
    note: str
    version: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.version is not None


def _version(dist: str) -> tuple[str | None, str | None]:
    try:
        return md.version(dist), None
    except md.PackageNotFoundError:
        return None, "未安装"
    except Exception as exc:  # pragma: no cover - 仅在环境损坏时触发
        return None, f"{type(exc).__name__}: {exc}"


def collect() -> list[DepStatus]:
    """返回所有被跟踪依赖的版本信息。"""
    out: list[DepStatus] = []
    for display, dist, note in TRACKED:
        version, error = _version(dist)
        out.append(DepStatus(display=display, note=note, version=version, error=error))
    return out


def ffmpeg_path() -> str | None:
    """返回 imageio-ffmpeg 附带的 ffmpeg.exe 路径（拿不到就返回 None）。"""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def summary() -> str:
    """把环境信息渲染成一段纯文本，用于日志或"关于"窗口。"""
    import imagevideoprocess as pkg

    lines = [
        f"{pkg.APP_NAME} {pkg.__version__}",
        "",
        f"Python      : {sys.version.split()[0]}  ({platform.architecture()[0]})",
        f"解释器路径  : {sys.executable}",
        f"虚拟环境    : {sys.prefix}",
        f"操作系统    : {platform.system()} {platform.release()} ({platform.version()})",
        f"FFmpeg      : {ffmpeg_path() or '不可用'}",
        "",
        "依赖:",
    ]
    for status in collect():
        mark = "OK " if status.ok else "缺失"
        version = status.version or status.error or "?"
        lines.append(f"  [{mark}] {status.display:<22} {version:<12} {status.note}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
