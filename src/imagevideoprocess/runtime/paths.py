"""路径解析：定位「应用目录」与输出目录 ``processed``。

约定（用户需求）：处理结果统一放在 **exe 同级目录下的 processed 文件夹**。

- 打包成 exe 运行：``sys.frozen`` 为真，应用目录 = ``exe 所在目录``；
- 开发模式（``uv run imagevideoprocess``）：应用目录 = 项目根目录。

注意：单文件 exe 运行时 ``__file__`` 指向临时解压目录（``sys._MEIPASS``），
**不能**用它推算应用目录，否则处理结果会落到临时目录里并被清空。
"""

from __future__ import annotations

import sys
from pathlib import Path

#: 输出目录名（相对应用目录）
PROCESSED_DIRNAME = "processed"


def is_frozen() -> bool:
    """当前是否运行在打包产物（exe）里。"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """返回应用目录（exe 所在目录 / 开发时的项目根目录）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # runtime/paths.py → runtime → imagevideoprocess → src → 项目根
    return Path(__file__).resolve().parents[3]


def processed_dir(create: bool = True) -> Path:
    """返回输出目录 ``<应用目录>/processed``，默认自动创建。"""
    target = app_dir() / PROCESSED_DIRNAME
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def unique_path(path: Path) -> Path:
    """若 ``path`` 已存在，则追加 ``_1``、``_2``… 直到不冲突，避免覆盖旧结果。"""
    if not path.exists():
        return path
    parent, stem, suffix = path.parent, path.stem, path.suffix
    for index in range(1, 10_000):
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise OSError(f"无法为 {path.name} 找到可用的输出文件名")
