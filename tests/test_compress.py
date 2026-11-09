"""压缩功能测试：图片 / 视频都要能压到目标体积以内。"""

from __future__ import annotations

import pytest

from imagevideoprocess.core import compress, media_info
from imagevideoprocess.core.errors import InvalidParameterError
from media_factory import make_image, make_video


def test_target_bytes_of() -> None:
    """数值 + 单位 → 字节数。"""
    assert compress.target_bytes_of(1, "kb") == 1024
    assert compress.target_bytes_of(1, "MB") == 1024**2
    assert compress.target_bytes_of(0.5, "gb") == 1024**3 // 2
    with pytest.raises(InvalidParameterError):
        compress.target_bytes_of(1, "tb")


def test_compress_image_hits_target(tmp_dir) -> None:
    """图片压缩后必须小于等于目标体积，且文件名带 _compressed。"""
    src = make_image(tmp_dir / "photo.jpg", size=(1200, 800))
    target = src.stat().st_size // 2
    result = compress.compress_image(src, target, out_dir=tmp_dir / "out")

    assert len(result.outputs) == 1
    out = result.outputs[0]
    assert out.name == "photo_compressed.jpg"
    assert out.stat().st_size <= target
    assert result.output_bytes == out.stat().st_size
    assert result.verb == "压缩"
    assert "压缩完成" in result.summary
    # 输出仍然是可读的 JPEG，分辨率保持不变
    info = media_info.probe(out)
    assert info.format == "JPEG"
    assert (info.width, info.height) == (1200, 800)


def test_compress_png_by_palette(tmp_dir) -> None:
    """PNG 是无损格式，靠减色 + 必要时降采样逼近目标体积。"""
    src = make_image(tmp_dir / "shot.png", size=(640, 480))
    target = src.stat().st_size // 3
    result = compress.compress_image(src, target, out_dir=tmp_dir / "out")
    assert result.outputs[0].stat().st_size <= target
    assert result.outputs[0].suffix == ".png"


def test_compress_rejects_larger_target(tmp_dir) -> None:
    """期望体积必须小于原文件。"""
    src = make_image(tmp_dir / "photo.jpg", size=(320, 240))
    with pytest.raises(InvalidParameterError):
        compress.compress_image(src, src.stat().st_size * 2, out_dir=tmp_dir / "out")


def test_compress_video_hits_target(tmp_dir) -> None:
    """视频压缩：扣掉音频占用后按码率逼近目标体积。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=2.0, fps=30, size=(480, 270))
    original = src.stat().st_size
    target = original // 2
    result = compress.compress_video(src, target, out_dir=tmp_dir / "out")

    out = result.outputs[0]
    assert out.name == "clip_compressed.mp4"
    assert out.stat().st_size <= target * 1.05, "压缩结果明显超出目标体积"
    assert out.stat().st_size < original

    # 输出的视频依然可解析，分辨率不变
    info = media_info.probe(out)
    assert info.kind == "video"
    assert (info.width, info.height) == (480, 270)


def test_compress_dispatch_by_kind(tmp_dir) -> None:
    """统一入口按文件类型自动分派。"""
    image = make_image(tmp_dir / "a.jpg", size=(400, 300))
    result = compress.compress(image, image.stat().st_size // 2, out_dir=tmp_dir / "out")
    assert result.outputs[0].name == "a_compressed.jpg"

    video = make_video(tmp_dir / "b.mp4", seconds=1.0, fps=24, size=(240, 160))
    result = compress.compress(video, video.stat().st_size // 2, out_dir=tmp_dir / "out")
    assert result.outputs[0].name == "b_compressed.mp4"


def test_compress_output_not_overwritten(tmp_dir) -> None:
    """重复压缩同一个文件不会覆盖已有结果，而是加序号。"""
    src = make_image(tmp_dir / "photo.jpg", size=(800, 600))
    out_dir = tmp_dir / "out"
    target = src.stat().st_size // 2
    first = compress.compress_image(src, target, out_dir=out_dir)
    second = compress.compress_image(src, target, out_dir=out_dir)
    assert first.outputs[0] != second.outputs[0]
    assert first.outputs[0].exists() and second.outputs[0].exists()


def test_compress_cancel(tmp_dir) -> None:
    """取消令牌生效后立刻抛 Cancelled。"""
    from imagevideoprocess.core.errors import Cancelled
    from imagevideoprocess.core.progress import CancelToken

    src = make_image(tmp_dir / "photo.jpg", size=(800, 600))
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        compress.compress_image(src, src.stat().st_size // 2, out_dir=tmp_dir / "out", cancel=token)


def test_progress_reaches_full(tmp_dir) -> None:
    """进度回调最终要走到 100。"""
    src = make_image(tmp_dir / "photo.jpg", size=(600, 400))
    seen: list[int] = []
    compress.compress_image(
        src, src.stat().st_size // 2, out_dir=tmp_dir / "out", progress=seen.append
    )
    assert seen and seen[-1] == 100
    assert all(0 <= value <= 100 for value in seen)
