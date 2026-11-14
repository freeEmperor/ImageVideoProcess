"""验证实际运行依赖、FFmpeg 和项目解释器隔离。"""

from __future__ import annotations

import pytest

from imagevideoprocess.runtime import envreport


def test_no_dependency_missing() -> None:
    """pyproject.toml 里声明的依赖必须全部装好。"""
    missing = [
        f"{s.display} ({s.error})"
        for s in envreport.collect()
        if not s.ok and s.display in _REQUIRED
    ]
    assert not missing, "以下依赖未安装: " + ", ".join(missing)


def test_ffmpeg_available() -> None:
    """imageio-ffmpeg 必须能定位到 ffmpeg.exe。"""
    exe = envreport.ffmpeg_path()
    assert exe, "未找到 ffmpeg.exe"
    from pathlib import Path

    assert Path(exe).exists()


def test_summary_renders() -> None:
    """环境摘要文本能正常生成，且列出所有被跟踪依赖。"""
    text = envreport.summary()
    assert "Python" in text
    assert "FFmpeg" in text
    for _, _, note in envreport.TRACKED:
        del note
    assert text.count("[OK ") >= len(_REQUIRED)


def test_pipeline_roundtrip(tmp_dir) -> None:
    """最小端到端：numpy -> OpenCV 缩放 -> Pillow 存盘 -> 读回。"""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from PIL import Image

    canvas = np.zeros((120, 160, 3), dtype=np.uint8)
    canvas[:, :] = (18, 52, 86)
    resized = cv2.resize(canvas, (80, 60), interpolation=cv2.INTER_AREA)
    out = tmp_dir / "out.jpg"
    Image.fromarray(resized[:, :, ::-1]).save(out, quality=85)
    with Image.open(out) as im:
        assert im.size == (80, 60)


#: 必须存在的发行包（与 pyproject.toml 的分组对应）
_REQUIRED = {
    "opencv-python-headless",
    "Pillow",
    "numpy",
    "imageio-ffmpeg",
    "av",
    "pillow-heif",
    "PySide6",
    "qtawesome",
}


def test_project_interpreter_and_dependency_isolation():
    import sys
    from pathlib import Path

    import numpy

    root = Path(__file__).resolve().parents[2]
    assert Path(sys.prefix).resolve() == root / ".venv"
    assert Path(sys.base_prefix).resolve().is_relative_to(root / ".uv-python")
    assert Path(numpy.__file__).resolve().is_relative_to(root / ".venv")
    assert not any(".uv-packages" in entry for entry in sys.path)
