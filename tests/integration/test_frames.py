"""抽帧功能测试：三种输入组合、越界校验、输出命名。"""

from __future__ import annotations

import pytest
from media_factory import make_image, make_video

from imagevideoprocess.core.errors import InvalidParameterError
from imagevideoprocess.media import media_info
from imagevideoprocess.operations import frames

FPS = 30
SECONDS = 3.0


@pytest.fixture
def video(tmp_dir):
    """3 秒 30fps 的测试视频（共 90 帧）。"""
    return make_video(tmp_dir / "clip.mp4", seconds=SECONDS, fps=FPS, size=(320, 180))


def test_resolve_range_frame_units(video) -> None:
    """（100帧，10帧）：从第 100 帧起取 10 帧。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 40, "f", 10, "f")
    assert rng.start_frame == 40
    assert rng.count == 10
    assert rng.end_frame == 49
    assert rng.start_time == pytest.approx(40 / FPS)


def test_resolve_range_second_start_frame_span(video) -> None:
    """（1秒，10帧）：从第 1 秒起取 10 帧 —— 即第 30 ~ 39 帧。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 1.0, "s", 10, "f")
    assert rng.start_frame == 30
    assert rng.count == 10


def test_resolve_range_second_span_takes_all_frames(video) -> None:
    """（0秒，0.5秒）：取这半秒内的所有帧 —— 30fps 即 15 张。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 0.0, "s", 0.5, "s")
    assert rng.start_frame == 0
    assert rng.count == 15


@pytest.mark.parametrize(
    ("start", "start_unit", "span", "span_unit"),
    [
        (95, "f", 10, "f"),  # 起始就越界
        (85, "f", 10, "f"),  # 区间尾巴越界
        (2.9, "s", 1.0, "s"),  # 秒为单位时越界
        (-1, "f", 5, "f"),  # 负数
        (0, "f", 0, "f"),  # 跨度为 0
        (0, "x", 5, "f"),  # 非法单位
    ],
)
def test_resolve_range_rejects(video, start, start_unit, span, span_unit) -> None:
    """越界 / 非法输入必须报错（界面上按钮会因此变灰）。"""
    info = media_info.probe(video)
    with pytest.raises(InvalidParameterError):
        frames.resolve_range(info, start, start_unit, span, span_unit)


def test_extract_frames_names_and_content(video, tmp_dir) -> None:
    """输出命名为 原名_000100.png，帧号与原视频一致。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 40, "f", 10, "f")
    result = frames.extract_frames(video, rng, out_dir=tmp_dir / "out")

    names = [path.name for path in result.outputs]
    assert names[0] == "clip_000040.png"
    assert names[-1] == "clip_000049.png"
    assert len(names) == 10
    assert all(path.exists() for path in result.outputs)
    for path in result.outputs:
        assert media_info.probe(path).resolution_text == "320 × 180"


def test_extract_frames_jpg(video, tmp_dir) -> None:
    """可以指定输出图片格式。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 10, "f", 3, "f")
    result = frames.extract_frames(video, rng, image_format="jpg", out_dir=tmp_dir / "out")
    assert [path.name for path in result.outputs] == [
        "clip_000010.jpg",
        "clip_000011.jpg",
        "clip_000012.jpg",
    ]
    assert media_info.probe(result.outputs[0]).format == "JPEG"


def test_extract_frames_rejects_bad_format(video, tmp_dir) -> None:
    """不支持的图片格式要报错。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 0, "f", 1, "f")
    with pytest.raises(InvalidParameterError):
        frames.extract_frames(video, rng, image_format="exr", out_dir=tmp_dir / "out")


def test_extract_frames_from_info(video, tmp_dir) -> None:
    """便利入口：直接给界面输入。"""
    result = frames.extract_frames_from_info(video, 1.0, "s", 0.2, "s", out_dir=tmp_dir / "out")
    assert len(result.outputs) == 6
    assert result.outputs[0].name == "clip_000030.png"


def test_resolve_range_requires_video(tmp_dir) -> None:
    """图片不能抽帧。"""
    image = make_image(tmp_dir / "photo.jpg", size=(64, 64))
    info = media_info.probe(image)
    with pytest.raises(InvalidParameterError):
        frames.resolve_range(info, 0, "f", 1, "f")


def test_progress_reaches_full(video, tmp_dir) -> None:
    """抽帧进度最终到 100。"""
    info = media_info.probe(video)
    rng = frames.resolve_range(info, 0, "f", 5, "f")
    seen: list[int] = []
    frames.extract_frames(video, rng, out_dir=tmp_dir / "out", progress=seen.append)
    assert seen[-1] == 100
