"""冒烟测试：确认 uv 环境里的处理库都能 import 并跑通最小算子。

用法：
    uv run python scripts/smoke_test.py

输出每项 PASS / FAIL，末尾给出总结；全部通过时退出码为 0。
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import time
from pathlib import Path

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        results.append((name, True, str(detail)))
        print(f"[{PASS}] {name}  {detail}")
    except Exception as exc:  # noqa: BLE001 - 冒烟脚本要抓住一切异常
        results.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"[{FAIL}] {name}  {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------- 各项
def t_numpy() -> str:
    import numpy as np

    a = np.arange(12, dtype=np.uint8).reshape(3, 4)
    assert a.mean() == 5.5
    return f"numpy {np.__version__}"


def t_pillow(tmp: Path) -> str:
    from PIL import Image

    p = tmp / "pillow.jpg"
    Image.new("RGB", (32, 32), (200, 30, 30)).save(p, quality=90)
    with Image.open(p) as im:
        assert im.size == (32, 32)
    return f"Pillow {Image.__version__} 圆形写入/读回 {p.stat().st_size}B"


def t_opencv(tmp: Path) -> str:
    import cv2
    import numpy as np

    img = np.zeros((48, 64, 3), dtype=np.uint8)
    cv2.rectangle(img, (8, 8), (56, 40), (0, 255, 0), -1)
    small = cv2.resize(img, (32, 24), interpolation=cv2.INTER_AREA)
    assert small.shape == (24, 32, 3)
    p = tmp / "cv2.png"
    assert cv2.imwrite(str(p), small)
    assert cv2.imread(str(p)) is not None
    # contrib 模块检查
    ximgproc = hasattr(cv2, "ximgproc")
    return f"OpenCV {cv2.__version__}  contrib={'yes' if ximgproc else 'no'}"


def t_scipy() -> str:
    import numpy as np
    import scipy
    from scipy import ndimage

    blurred = ndimage.gaussian_filter(np.ones((16, 16)), sigma=1.0)
    assert blurred.shape == (16, 16)
    return f"SciPy {scipy.__version__}"


def t_skimage() -> str:
    import numpy as np
    import skimage
    from skimage.metrics import peak_signal_noise_ratio

    a = np.zeros((16, 16), dtype=np.uint8)
    b = np.full((16, 16), 10, dtype=np.uint8)
    psnr = peak_signal_noise_ratio(a, b, data_range=255)
    return f"scikit-image {skimage.__version__}  PSNR={psnr:.2f}dB"


def t_imageio(tmp: Path) -> str:
    import imageio.v3 as iio
    import numpy as np

    p = tmp / "iio.png"
    iio.imwrite(p, np.full((20, 20, 3), 128, dtype=np.uint8))
    back = iio.imread(p)
    assert back.shape == (20, 20, 3)
    import imageio

    return f"imageio {imageio.__version__}"


def t_imageio_ffmpeg() -> str:
    import imageio_ffmpeg

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    assert Path(exe).exists(), f"ffmpeg 不存在: {exe}"
    return f"FFmpeg {imageio_ffmpeg.get_ffmpeg_version()}  {exe}"


def t_av(tmp: Path) -> str:
    import av
    import numpy as np

    p = tmp / "av_test.mp4"
    frames = 8
    with av.open(str(p), mode="w") as out:
        stream = out.add_stream("libx264", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for i in range(frames):
            arr = np.full((48, 64, 3), i * 20, dtype=np.uint8)
            for packet in stream.encode(av.VideoFrame.from_ndarray(arr, format="rgb24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    with av.open(str(p)) as inp:
        n = sum(1 for _ in inp.decode(video=0))
    assert n == frames, f"期望 {frames} 帧，解出 {n} 帧"
    return f"PyAV {av.__version__}  编码+解码 {n} 帧 OK"


def t_pillow_heif(tmp: Path) -> str:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    p = tmp / "heif.heic"
    Image.new("RGB", (32, 32), (10, 10, 200)).save(p, format="HEIF", quality=80)
    with Image.open(p) as im:
        assert im.size == (32, 32)
    return f"pillow-heif {pillow_heif.__version__}  HEIC 往返 OK"


def t_pyside6() -> str:
    from PySide6 import __version__ as qt_ver
    from PySide6.QtCore import qVersion
    from PySide6.QtGui import QImage

    img = QImage(16, 16, QImage.Format.Format_RGB32)
    assert not img.isNull()
    return f"PySide6 {qt_ver} (Qt {qVersion()})"


def t_pyqtgraph() -> str:
    import pyqtgraph

    assert pyqtgraph.__version__
    return f"pyqtgraph {pyqtgraph.__version__}"


def t_send2trash() -> str:
    import send2trash

    assert callable(send2trash.send2trash)
    return "send2trash 可导入"


def t_win32() -> str:
    import win32api  # noqa: F401
    import win32con  # noqa: F401

    return "pywin32 (win32api/win32con) 可导入"


def t_typer_rich() -> str:
    import importlib.metadata as md

    import typer

    return f"typer {typer.__version__} / rich {md.version('rich')}"


def main() -> int:
    print(f"Python: {sys.version.split()[0]}  解释器: {sys.executable}\n")

    # 临时目录不用 tempfile.mkdtemp / TemporaryDirectory：它们会以 0o700 建目录，
    # 在权限被收紧的环境（沙箱、某些企业策略、受控目录）里会导致后续写入被拒。
    # 这里手工 mkdir，目录落在项目内，权限跟随父目录，最稳。
    root = Path(__file__).resolve().parent.parent
    scratch = root / ".smoke-tmp"
    try:
        scratch.mkdir(exist_ok=True)
    except OSError:
        scratch = Path.cwd()
    tmp = scratch / f"run_{os.getpid()}_{int(time.time())}"
    tmp.mkdir(parents=True, exist_ok=True)
    print(f"临时目录: {tmp}\n")

    try:
        check("numpy", t_numpy)
        check("Pillow", lambda: t_pillow(tmp))
        check("OpenCV", lambda: t_opencv(tmp))
        check("SciPy", t_scipy)
        check("scikit-image", t_skimage)
        check("imageio", lambda: t_imageio(tmp))
        check("imageio-ffmpeg", t_imageio_ffmpeg)
        check("PyAV", lambda: t_av(tmp))
        check("pillow-heif", lambda: t_pillow_heif(tmp))
        check("PySide6", t_pyside6)
        check("pyqtgraph", t_pyqtgraph)
        check("send2trash", t_send2trash)
        check("pywin32", t_win32)
        check("typer/rich", t_typer_rich)
    finally:
        # 清理失败（权限受限环境）不影响测试结论
        with contextlib.suppress(Exception):
            shutil.rmtree(tmp, ignore_errors=True)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n共 {len(results)} 项，通过 {len(results) - len(failed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项: " + ", ".join(failed))
        return 1
    print("全部通过 —— uv 环境可用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
