"""格式转换测试：图片 / 视频换格式，且不做体积压缩。"""

from __future__ import annotations

import pytest

from imagevideoprocess.core import convert, media_info
from imagevideoprocess.core.errors import InvalidParameterError, UnsupportedFormatError
from media_factory import make_image, make_video


@pytest.mark.parametrize(
    ("factory", "expected_missing"),
    [("image", "jpg"), ("png", "png"), ("video", "mp4")],
)
def test_targets_exclude_source_format(tmp_dir, factory: str, expected_missing: str) -> None:
    """目标格式列表必须排除源文件原本的格式（需求要求）。"""
    path = {
        "image": lambda: make_image(tmp_dir / "photo.jpg", size=(120, 90)),
        "png": lambda: make_image(tmp_dir / "logo.png", size=(120, 90)),
        "video": lambda: make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90)),
    }[factory]()

    info = media_info.probe(path)
    keys = [target.key for target in convert.targets_for(info)]
    assert keys, "应当至少有一个可选目标格式"
    assert expected_missing not in keys
    assert convert.source_format_key(info) == expected_missing


def test_source_format_key_aliases(tmp_dir) -> None:
    """扩展名别名要能归一（.jpeg→jpg、.tif→tiff、.m4v→mp4）。"""
    jpeg = tmp_dir / "a.jpeg"
    make_image(jpeg, size=(40, 30))
    assert convert.source_format_key(media_info.probe(jpeg)) == "jpg"

    tif = tmp_dir / "b.tif"
    make_image(tif, size=(40, 30))
    assert convert.source_format_key(media_info.probe(tif)) == "tiff"


def test_convert_image_formats(tmp_dir) -> None:
    """图片转换：扩展名变了、文件名保持原名、分辨率不变、能读回。"""
    src = make_image(tmp_dir / "photo.jpg", size=(200, 150))
    for key in ("png", "webp", "bmp", "tiff", "avif"):
        target = convert.target_by_key(key, "image")
        result = convert.convert(src, target, out_dir=tmp_dir / "out")
        output = result.outputs[0]
        assert output.name == f"photo{target.suffix}"
        info = media_info.probe(output)
        assert info.kind == "image"
        assert (info.width, info.height) == (200, 150)
        assert result.verb == "格式转换"
        assert "不做体积压缩" in result.note


def test_convert_image_keeps_alpha_for_png(tmp_dir) -> None:
    """PNG 的透明通道转到 WebP 时要保留，转到 JPG 时要拍平（不能报错）。"""
    from PIL import Image

    src = tmp_dir / "alpha.png"
    Image.new("RGBA", (60, 40), (255, 0, 0, 128)).save(src)

    webp = convert.convert(src, "webp", out_dir=tmp_dir / "out")
    with Image.open(webp.outputs[0]) as image:
        assert image.mode in {"RGBA", "RGBa"} or "A" in image.mode

    jpg = convert.convert(src, "jpg", out_dir=tmp_dir / "out")
    with Image.open(jpg.outputs[0]) as image:
        assert image.mode == "RGB"


def test_convert_video_lossless_remux(tmp_dir) -> None:
    """mp4 → mkv：源编码兼容，走无损转封装（音频也保留）。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=15, size=(160, 90))
    result = convert.convert(src, "mkv", out_dir=tmp_dir / "out")
    output = result.outputs[0]
    assert output.name == "clip.mkv"
    assert "无损转封装" in result.note

    info = media_info.probe(output)
    assert info.kind == "video"
    assert (info.width, info.height) == (160, 90)
    assert info.audio_codec == "aac", "音轨不能丢"


def test_convert_video_reencode_keeps_audio(tmp_dir) -> None:
    """mp4 → webm：h264 装不进 webm，要重新编码，且音轨改成 opus（不能丢音频）。"""
    src = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=15, size=(160, 90))
    result = convert.convert(src, "webm", out_dir=tmp_dir / "out")
    output = result.outputs[0]
    assert output.name == "clip.webm"

    info = media_info.probe(output)
    assert info.kind == "video"
    assert info.video_codec in {"vp9", "vp8", "av1"}
    assert info.audio_codec is not None, "转换不该把音轨丢掉"


def test_convert_rejects_same_format(tmp_dir) -> None:
    """源格式与目标格式相同时要报错。"""
    src = make_image(tmp_dir / "photo.jpg", size=(80, 60))
    with pytest.raises(InvalidParameterError):
        convert.convert(src, "jpg", out_dir=tmp_dir / "out")


def test_target_by_key_rejects_unknown() -> None:
    """不认识的格式名要报错。"""
    with pytest.raises(UnsupportedFormatError):
        convert.target_by_key("xyz", "image")


def test_describe_plan_mentions_mode(tmp_dir) -> None:
    """界面上的说明要讲清是转封装还是重新编码。"""
    video = make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90))
    info = media_info.probe(video)
    assert "无损转封装" in convert.describe_plan(info, convert.target_by_key("mkv", "video"))
    assert "重新编码" in convert.describe_plan(info, convert.target_by_key("webm", "video"))

    image = make_image(tmp_dir / "photo.jpg", size=(80, 60))
    assert "不压缩体积" in convert.describe_plan(
        media_info.probe(image), convert.target_by_key("png", "image")
    )


def test_convert_progress_reaches_full(tmp_dir) -> None:
    """进度回调最终到 100。"""
    src = make_image(tmp_dir / "photo.jpg", size=(120, 90))
    seen: list[int] = []
    convert.convert(src, "png", out_dir=tmp_dir / "out", progress=seen.append)
    assert seen and seen[-1] == 100
    assert all(0 <= value <= 100 for value in seen)
