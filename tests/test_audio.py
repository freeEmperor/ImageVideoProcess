"""视频音频提取测试。"""

from __future__ import annotations

import av
import pytest

from imagevideoprocess.core import audio_ops
from imagevideoprocess.core.errors import ProcessingError, UnsupportedFormatError
from media_factory import make_image, make_video


def _audio_streams(path) -> list[object]:
    """读出音频文件里的音频流。"""
    with av.open(str(path)) as container:
        return list(container.streams.audio)


def test_targets_have_encoders() -> None:
    """列出来的音频格式，本机必须都有编码器。"""
    targets = audio_ops.available_targets()
    assert targets, "至少要有一个可用的音频格式"
    for target in targets:
        assert target.codec in av.codecs_available, target.label


def test_target_by_key() -> None:
    """按 key 取格式；不认识的要报错。"""
    assert audio_ops.target_by_key("mp3").suffix == ".mp3"
    assert audio_ops.target_by_key("wav").is_lossless
    assert not audio_ops.target_by_key("mp3").is_lossless
    with pytest.raises(UnsupportedFormatError):
        audio_ops.target_by_key("aiff")


def test_encoder_settings() -> None:
    """编码器参数：opus 必须 48kHz + 固定帧长。"""
    assert audio_ops.encoder_sample_format("aac") == "fltp"
    assert audio_ops.encoder_sample_format("libmp3lame") == "s16p"
    assert audio_ops.encoder_sample_rate("libopus", 44100) == 48000
    assert audio_ops.encoder_frame_size("libopus") == 960
    assert audio_ops.encoder_sample_rate("aac", 44100) == 44100
    assert audio_ops.encoder_bitrate("flac") is None
    assert audio_ops.encoder_bitrate("aac", None) == 192_000


def test_normalize_codec_aliases() -> None:
    """编码器名要能归一成编码名（否则容器兼容性判断会误判）。"""
    assert audio_ops.normalize_codec("libmp3lame") == "mp3"
    assert audio_ops.normalize_codec("libopus") == "opus"
    assert audio_ops.normalize_codec("AAC") == "aac"
    assert audio_ops.normalize_codec(None) == ""


@pytest.mark.parametrize("key", ["mp3", "m4a", "wav", "flac", "ogg"])
def test_extract_audio(tmp_dir, key: str) -> None:
    """从视频里提音频：命名、扩展名、可解码、有音频流。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=15, size=(160, 90))
    target = audio_ops.target_by_key(key)
    result = audio_ops.extract_audio(src, target, out_dir=tmp_dir / "out")

    output = result.outputs[0]
    assert output.name == f"clip{target.suffix}"
    assert output.stat().st_size > 0
    assert _audio_streams(output), f"{key} 输出里没有音频流"
    assert result.verb == "提取音频"


def test_extract_audio_reuses_matching_codec(tmp_dir) -> None:
    """源音轨已经是 AAC 时，转 m4a 直接复用、不重新编码。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=15, size=(160, 90))
    result = audio_ops.extract_audio(src, "m4a", out_dir=tmp_dir / "out")
    assert "直接复用" in result.note


def test_extract_audio_requires_video(tmp_dir) -> None:
    """图片不能提音频。"""
    image = make_image(tmp_dir / "photo.jpg", size=(80, 60))
    with pytest.raises(ProcessingError):
        audio_ops.extract_audio(image, "mp3", out_dir=tmp_dir / "out")


def test_extract_audio_requires_audio_track(tmp_dir) -> None:
    """没有音轨的视频要给出明确错误。"""
    silent = make_video(
        tmp_dir / "silent.mp4", seconds=0.5, fps=10, size=(160, 90), with_audio=False
    )
    with pytest.raises(ProcessingError) as excinfo:
        audio_ops.extract_audio(silent, "mp3", out_dir=tmp_dir / "out")
    assert "没有音频" in str(excinfo.value)


def test_extract_audio_progress_reaches_full(tmp_dir) -> None:
    """进度回调最终到 100。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=15, size=(160, 90))
    seen: list[int] = []
    audio_ops.extract_audio(src, "mp3", out_dir=tmp_dir / "out", progress=seen.append)
    assert seen and seen[-1] == 100
