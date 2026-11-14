"""媒体信息探测与格式化测试。"""

from __future__ import annotations

from media_factory import make_image, make_video

from imagevideoprocess.core.errors import UnsupportedFormatError
from imagevideoprocess.media import media_info


def test_probe_image(tmp_dir) -> None:
    """图片：格式 / 分辨率 / 体积都要读对。"""
    path = make_image(tmp_dir / "photo.jpg", size=(320, 200))
    info = media_info.probe(path)
    assert info.kind == "image"
    assert info.kind_text == "图片"
    assert info.format == "JPEG"
    assert (info.width, info.height) == (320, 200)
    assert info.resolution_text == "320 × 200"
    assert info.size_bytes == path.stat().st_size
    assert info.fps_text == "—"
    assert info.duration_text == "—"


def test_probe_video(tmp_dir) -> None:
    """视频：容器 / 编码 / 帧率 / 总帧数 / 时长 / 音频都要读对。"""
    path = make_video(tmp_dir / "clip.mp4", seconds=2.0, fps=30, size=(320, 180))
    info = media_info.probe(path)
    assert info.kind == "video"
    assert info.kind_text == "视频"
    assert info.format == "MP4"
    assert (info.width, info.height) == (320, 180)
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"
    assert info.fps is not None and abs(info.fps - 30.0) < 0.01
    assert info.frame_count == 60
    assert info.duration is not None and abs(info.duration - 2.0) < 0.05
    assert info.fps_text == "30.00 fps"
    assert "H.264" in info.codec_text and "AAC" in info.codec_text


def test_rows_contains_required_fields(tmp_dir) -> None:
    """信息卡片必须包含需求里点名的字段。"""
    path = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=25, size=(160, 120))
    keys = [row.key for row in media_info.probe(path).rows()]
    for expected in ("类型", "格式", "分辨率", "帧率", "大小"):
        assert expected in keys, expected


def test_path_row_is_first_and_full_width(tmp_dir) -> None:
    """路径属性排第一，且要独占一整排（需求要求）。"""
    path = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=25, size=(160, 120))
    rows = media_info.probe(path).rows()

    first = rows[0]
    assert first.key == "路径"
    assert first.full_width, "路径必须独占整排"
    assert first.value == str(path), "应当显示完整文件路径"
    assert sum(row.full_width for row in rows) == 1, "只有路径独占整排"


def test_format_helpers() -> None:
    """体积与时长格式化。"""
    assert media_info.format_bytes(512) == "512 B"
    assert media_info.format_bytes(2048) == "2.00 KB"
    assert media_info.format_bytes(5 * 1024**2) == "5.00 MB"
    assert media_info.format_duration(0) == "—"
    assert media_info.format_duration(3661.5) == "01:01:01.500"


def test_probe_rejects_unknown_file(tmp_dir) -> None:
    """既不是图片也不是视频的文件要报错，而不是抛第三方异常。"""
    path = tmp_dir / "notes.txt"
    path.write_text("这不是媒体文件", encoding="utf-8")
    try:
        media_info.probe(path)
    except UnsupportedFormatError:
        return
    raise AssertionError("应当抛出 UnsupportedFormatError")


def test_probe_missing_file(tmp_dir) -> None:
    """文件不存在时抛 FileNotFoundError。"""
    try:
        media_info.probe(tmp_dir / "nope.jpg")
    except FileNotFoundError:
        return
    raise AssertionError("应当抛出 FileNotFoundError")
