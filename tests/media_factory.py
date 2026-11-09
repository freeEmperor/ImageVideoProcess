"""测试用媒体素材工厂：现场生成图片与视频，避免把二进制素材提交进仓库。

只依赖已安装的 PyAV / Pillow / numpy，生成的素材很小（几百 KB 以内）。
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image


def make_image(
    path: Path,
    size: tuple[int, int] = (640, 480),
    color: tuple[int, int, int] = (200, 60, 60),
    fmt: str | None = None,
) -> Path:
    """生成一张带渐变的测试图片（渐变使 JPEG 压缩有真实体积）。"""
    width, height = size
    yy, xx = np.mgrid[0:height, 0:width]
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[..., 0] = (xx * 255 // max(1, width - 1)).astype(np.uint8)
    arr[..., 1] = (yy * 255 // max(1, height - 1)).astype(np.uint8)
    arr[..., 2] = (np.sin(xx / 7.0) * 60 + 128).astype(np.uint8)
    arr[height // 4 : height // 2, width // 4 : width // 2] = color
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, mode="RGB").save(path, format=fmt)
    return path


def make_video(
    path: Path,
    seconds: float = 2.0,
    fps: int = 30,
    size: tuple[int, int] = (320, 180),
    with_audio: bool = True,
    crf: int = 18,
) -> Path:
    """生成一段 H.264 测试视频（画面在动，便于验证抽帧）。

    Args:
        path: 输出路径，扩展名决定容器（.mp4 / .mkv …）。
        seconds: 时长（秒）。
        fps: 帧率。
        size: 分辨率。
        with_audio: 是否带一条 AAC 立体声正弦音轨。
        crf: 编码质量。

    Returns:
        输出路径。
    """
    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, int(round(seconds * fps)))

    with av.open(str(path), mode="w") as container:
        vstream = container.add_stream("libx264", rate=fps)
        vstream.width = width
        vstream.height = height
        vstream.pix_fmt = "yuv420p"
        vstream.options = {"crf": str(crf), "preset": "ultrafast"}

        astream = None
        if with_audio:
            astream = container.add_stream("aac", rate=44100)
            astream.layout = "stereo"
            astream.format = "fltp"

        base = np.zeros((height, width, 3), dtype=np.uint8)
        base[..., 2] = np.linspace(20, 200, width, dtype=np.uint8)[None, :]

        for index in range(total_frames):
            arr = base.copy()
            box = 24
            left = int((width - box) * (index / total_frames))
            top = height // 2 - box // 2 + int(np.sin(index / 3.0) * 12)
            arr[top : top + box, left : left + box] = (255, 255, 255)
            frame = av.VideoFrame.from_ndarray(arr, format="bgr24")
            frame.pts = index
            frame.time_base = Fraction(1, fps)
            for packet in vstream.encode(frame):
                container.mux(packet)
        for packet in vstream.encode():
            container.mux(packet)

        if astream is not None:
            rate = 44100
            chunk = 1024
            written = 0
            total_samples = int(round(seconds * rate))
            while written < total_samples:
                count = min(chunk, total_samples - written)
                t = (np.arange(written, written + count, dtype=np.float64)) / rate
                wave = (0.25 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
                samples = np.stack([wave, wave])
                aframe = av.AudioFrame.from_ndarray(samples, format="fltp", layout="stereo")
                aframe.sample_rate = rate
                aframe.pts = written
                aframe.time_base = Fraction(1, rate)
                for packet in astream.encode(aframe):
                    container.mux(packet)
                written += count
            for packet in astream.encode():
                container.mux(packet)

    return path
