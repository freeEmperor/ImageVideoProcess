"""缩放功能测试。"""

from __future__ import annotations

import pytest

from imagevideoprocess.core import media_info, resize
from imagevideoprocess.core.errors import InvalidParameterError
from media_factory import make_image, make_video


def test_resize_image(tmp_dir) -> None:
    """缩放图片：分辨率正确，文件名带 宽x高。"""
    src = make_image(tmp_dir / "photo.jpg", size=(1200, 800))
    result = resize.resize_image(src, 600, 400, out_dir=tmp_dir / "out")
    out = result.outputs[0]
    assert out.name == "photo_600x400.jpg"
    info = media_info.probe(out)
    assert (info.width, info.height) == (600, 400)
    assert result.verb == "缩放"


@pytest.mark.parametrize(
    ("width", "height"),
    [(1200, 800), (1300, 900), (600, 800), (1200, 400), (0, 100), (-5, 100)],
)
def test_resize_image_rejects_bad_size(tmp_dir, width: int, height: int) -> None:
    """宽高必须都是正数，且都小于原分辨率。"""
    src = make_image(tmp_dir / "photo.jpg", size=(1200, 800))
    with pytest.raises(InvalidParameterError):
        resize.resize_image(src, width, height, out_dir=tmp_dir / "out")


def test_resize_video(tmp_dir) -> None:
    """缩放视频：重新编码并保留音频，输出分辨率正确。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=24, size=(320, 180))
    result = resize.resize_video(src, 160, 90, out_dir=tmp_dir / "out")
    out = result.outputs[0]
    assert out.name == "clip_160x90.mp4"
    info = media_info.probe(out)
    assert (info.width, info.height) == (160, 90)
    assert info.audio_codec == "aac", "音频轨道应当被保留"


def test_resize_video_rounds_to_even(tmp_dir) -> None:
    """奇数分辨率会向下取偶，文件名用实际输出尺寸。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=24, size=(320, 180))
    result = resize.resize_video(src, 161, 91, out_dir=tmp_dir / "out")
    assert result.outputs[0].name == "clip_160x90.mp4"
    assert "取偶" in result.note


def test_resize_dispatch(tmp_dir) -> None:
    """统一入口按文件类型分派。"""
    image = make_image(tmp_dir / "a.png", size=(400, 300))
    result = resize.resize(image, 200, 150, out_dir=tmp_dir / "out")
    assert result.outputs[0].name == "a_200x150.png"
    assert media_info.probe(result.outputs[0]).resolution_text == "200 × 150"
