"""格式转换：只换格式/容器，**不做体积压缩**。

- 图片：用 Pillow 解码后按目标格式重新编码，质量给到接近无损
  （JPEG 质量 95 + 4:4:4 无色度抽样，PNG/TIFF/BMP 本身无损）。
- 视频：源编码本来就兼容目标容器时走**无损转封装**（:func:`video_ops.remux`，
  不重新编码，画质完全不变、速度极快）；不兼容时（例如 h264 装不进 webm）
  才重新编码，且用 CRF 18（视觉无损）而不是按体积压。

输出命名：``原文件名.新扩展名``，落在 ``processed`` 目录下。
目标格式列表会**排除源文件原本的格式**（需求要求）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import av
from PIL import Image

from imagevideoprocess.core import audio_ops, video_ops
from imagevideoprocess.core.errors import (
    InvalidParameterError,
    UnsupportedFormatError,
)
from imagevideoprocess.core.image_ops import encode_to_bytes, get_exif
from imagevideoprocess.core.media_info import MediaInfo, probe, register_image_plugins
from imagevideoprocess.core.paths import processed_dir, unique_path
from imagevideoprocess.core.progress import CancelToken, ProgressFn, noop_progress
from imagevideoprocess.core.result import ProcessResult

#: 重新编码视频时的质量（CRF 越小越好；18 基本视觉无损）
_VIDEO_CRF = 18

#: 重新编码视频时的 x264 预设
_VIDEO_PRESET = "fast"

#: 几种格式的质量参数（不追求压小，只求画质接近原图）
_IMAGE_QUALITY = 95

#: webm 容器只能装 opus / vorbis 音轨
_WEBM_AUDIO_CODEC = "libopus"

#: 各容器在"源音轨装不进去"时改用的音频编码
_FALLBACK_AUDIO_CODEC: dict[str, str] = {
    "webm": _WEBM_AUDIO_CODEC,
    "avi": "libmp3lame",
    "mpeg": "libmp3lame",
    "asf": "wmav2",
}


@dataclass(frozen=True)
class TargetFormat:
    """一种可转换到的目标格式。"""

    key: str
    #: 文件扩展名（含点）
    suffix: str
    #: 界面上显示的名字
    label: str
    #: ``image`` / ``video``
    kind: str
    #: 图片用：Pillow 格式名
    pil_format: str | None = None
    #: 视频用：FFmpeg 容器名
    container: str | None = None
    #: 视频用：目标视频编码（None 表示按容器自动选）
    video_codec: str | None = None
    #: 一句话说明
    description: str = ""


#: 图片可转出的格式
IMAGE_TARGETS: tuple[TargetFormat, ...] = (
    TargetFormat("png", ".png", "PNG", "image", pil_format="PNG", description="无损，支持透明"),
    TargetFormat("jpg", ".jpg", "JPG", "image", pil_format="JPEG", description="最通用"),
    TargetFormat(
        "webp", ".webp", "WebP", "image", pil_format="WEBP", description="体积小、支持透明"
    ),
    TargetFormat("bmp", ".bmp", "BMP", "image", pil_format="BMP", description="无压缩位图"),
    TargetFormat("tiff", ".tiff", "TIFF", "image", pil_format="TIFF", description="印刷常用"),
    TargetFormat("avif", ".avif", "AVIF", "image", pil_format="AVIF", description="新一代格式"),
    TargetFormat("heic", ".heic", "HEIC", "image", pil_format="HEIC", description="苹果手机常用"),
)

#: 视频可转出的格式
VIDEO_TARGETS: tuple[TargetFormat, ...] = (
    TargetFormat("mp4", ".mp4", "MP4", "video", container="mp4", description="兼容性最好"),
    TargetFormat("mkv", ".mkv", "MKV", "video", container="matroska", description="几乎什么都能装"),
    TargetFormat("mov", ".mov", "MOV", "video", container="mov", description="苹果 / 剪辑软件"),
    TargetFormat("avi", ".avi", "AVI", "video", container="avi", description="老设备兼容"),
    TargetFormat("webm", ".webm", "WebM", "video", container="webm", description="网页常用（VP9）"),
    TargetFormat("ts", ".ts", "TS", "video", container="mpegts", description="录制 / 直播流"),
    TargetFormat("flv", ".flv", "FLV", "video", container="flv", description="老式网页视频"),
)

#: 扩展名别名 → 目标 key（用于判断"源文件原本是什么格式"）
_EXT_ALIASES: dict[str, str] = {
    ".jpeg": "jpg",
    ".jpe": "jpg",
    ".jfif": "jpg",
    ".tif": "tiff",
    ".heif": "heic",
    ".m4v": "mp4",
    ".m2ts": "ts",
    ".mts": "ts",
    ".asf": "wmv",
    ".mpeg": "mpg",
}

#: Pillow 格式名 → 目标 key
_PIL_ALIASES: dict[str, str] = {
    "JPEG": "jpg",
    "MPO": "jpg",
    "TIF": "tiff",
    "HEIF": "heic",
}


def source_format_key(info: MediaInfo) -> str:
    """判断源文件"原本的格式"对应哪个目标 key。"""
    suffix = info.path.suffix.lower()
    if suffix in _EXT_ALIASES:
        return _EXT_ALIASES[suffix]
    if info.kind == "image":
        return _PIL_ALIASES.get(info.format.upper(), info.format.lower())
    return suffix.lstrip(".")


def _encoder_available(target: TargetFormat) -> bool:
    """本机有没有这种格式的编码器。"""
    if target.kind == "video":
        codec = target.video_codec or video_ops.video_codec_for(target.container or "mp4")
        return codec in av.codecs_available
    return True  # 图片能力由 Pillow 决定，真正写的时候再报错


def targets_for(info: MediaInfo) -> list[TargetFormat]:
    """该文件能转成的目标格式（**排除它原本的格式**，需求要求）。"""
    table = IMAGE_TARGETS if info.kind == "image" else VIDEO_TARGETS
    current = source_format_key(info)
    return [target for target in table if target.key != current and _encoder_available(target)]


def target_by_key(key: str, kind: str) -> TargetFormat:
    """按 key 找目标格式。

    Raises:
        UnsupportedFormatError: 没有这种格式。
    """
    table = IMAGE_TARGETS if kind == "image" else VIDEO_TARGETS
    for target in table:
        if target.key == key:
            return target
    raise UnsupportedFormatError(f"不支持的{('图片' if kind == 'image' else '视频')}格式：{key}")


# ---------------------------------------------------------------- 图片转换
def convert_image(
    source: str | Path,
    target: TargetFormat,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """图片格式转换（画质接近无损，不做体积压缩）。"""
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if info.kind != "image":
        raise InvalidParameterError("该文件不是图片")
    if target.pil_format is None:
        raise UnsupportedFormatError(f"{target.label} 不是图片格式")

    register_image_plugins()
    progress(10)
    with Image.open(src) as handle:
        handle.load()
        image = handle.copy()
        exif = get_exif(handle)

    token.raise_if_cancelled()
    progress(40)
    data = encode_to_bytes(
        image,
        target.pil_format,
        quality=_IMAGE_QUALITY,
        exif=exif,
        subsampling="4:4:4",
    )

    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / f"{src.stem}{target.suffix}")
    dest.write_bytes(data)
    progress(100)

    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=dest.stat().st_size,
        verb="格式转换",
        note=f"{info.format} → {target.label}（不做体积压缩）",
    )


# ---------------------------------------------------------------- 视频转换
def convert_video(
    source: str | Path,
    target: TargetFormat,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """视频格式转换：能无损转封装就转封装，否则按视觉无损质量重新编码。"""
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if info.kind != "video":
        raise InvalidParameterError("该文件不是视频")
    if target.container is None:
        raise UnsupportedFormatError(f"{target.label} 不是视频格式")

    streams = video_ops.analyze(src)
    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / f"{src.stem}{target.suffix}")

    lossless = video_ops.can_remux(target.container, streams.video_codec, streams.audio_codec)
    if lossless:
        outcome = video_ops.remux(src, dest, target.container, cancel=token, progress=progress)
        mode = "无损转封装"
    else:
        spec = video_ops.TranscodeSpec(
            container_format=target.container,
            crf=_VIDEO_CRF,
            preset=_VIDEO_PRESET,
            keep_audio=True,
        )
        if not video_ops.audio_compatible(target.container, streams.audio_codec):
            # 例如 webm 只吃 opus、avi 装不下 aac：换成对应的编码，别把音轨丢掉
            spec.audio_codec = _FALLBACK_AUDIO_CODEC.get(target.container, "aac")
            spec.audio_forced_sample_rate = audio_ops.encoder_sample_rate(spec.audio_codec, None)
            spec.audio_frame_size = audio_ops.encoder_frame_size(spec.audio_codec)
        outcome = video_ops.transcode(src, dest, spec, cancel=token, progress=progress)
        mode = "重新编码（视觉无损 CRF 18）"

    note = f"{info.format} → {target.label}：{mode}"
    if outcome.note:
        note += f"；{outcome.note}"

    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=outcome.size_bytes,
        verb="格式转换",
        note=note,
    )


# ---------------------------------------------------------------- 统一入口
def convert(
    source: str | Path,
    target: TargetFormat | str,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """按文件类型自动分派到图片 / 视频格式转换。

    Args:
        source: 待转换文件。
        target: 目标格式（:class:`TargetFormat` 或它的 key）。
    """
    info = probe(source)
    spec = target if isinstance(target, TargetFormat) else target_by_key(target, info.kind)
    if source_format_key(info) == spec.key:
        raise InvalidParameterError(f"源文件已经是 {spec.label} 格式了，请换一个目标格式")

    if info.kind == "video":
        return convert_video(source, spec, out_dir=out_dir, cancel=cancel, progress=progress)
    return convert_image(source, spec, out_dir=out_dir, cancel=cancel, progress=progress)


def describe_plan(info: MediaInfo, target: TargetFormat) -> str:
    """给界面用：说明这次转换会怎么走。"""
    if info.kind == "image":
        return f"{info.format} → {target.label}（重新编码，不压缩体积）"
    codec = target.video_codec or video_ops.video_codec_for(target.container or "mp4")
    if video_ops.can_remux(target.container or "", info.video_codec, info.audio_codec):
        return f"{info.format} → {target.label}（无损转封装，不重新编码）"
    return f"{info.format} → {target.label}（用 {codec} 按视觉无损质量重新编码）"
