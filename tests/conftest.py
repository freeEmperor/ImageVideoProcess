r"""pytest 全局配置。

存在的唯一理由：`tmp_path` / `tmp_path_factory` 底层用 `tempfile.mkdtemp()`，
它在 Windows 上把目录建成 `0o700`（仅属主可访问）。某些权限被收紧的环境里，
子进程随后访问这个目录会被拒绝（`WinError 5 / PermissionError`），
导致任何用到 `tmp_path` 的测试报错——看起来像测试挂了，其实是环境问题。

这里把临时根目录换成普通 `mkdir` 出来的目录，权限跟随父目录，兼容性最好。

可用环境变量 `DSH_TEST_TMP` 覆盖临时根目录，例如：
    $env:DSH_TEST_TMP = "D:\scratch\ivp"; uv run pytest
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest


def _pick_root() -> Path:
    """选一个可用于建临时目录的根路径。"""
    candidates: list[Path] = []
    if os.environ.get("DSH_TEST_TMP"):
        candidates.append(Path(os.environ["DSH_TEST_TMP"]))
    candidates.append(Path(__file__).resolve().parent.parent / "build" / "test-tmp")

    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / f".probe_{uuid.uuid4().hex[:8]}"
            probe.mkdir()
            (probe / "t.bin").write_bytes(b"x")
            shutil.rmtree(probe, ignore_errors=True)
            return root
        except OSError:
            continue
    return Path(os.environ.get("TEMP", "."))


@pytest.fixture
def tmp_dir() -> Path:
    """普通 mkdir 出来的临时目录（用完尽力清理）。"""
    target = _pick_root() / f"t_{uuid.uuid4().hex[:10]}"
    target.mkdir(parents=True, exist_ok=True)
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)
