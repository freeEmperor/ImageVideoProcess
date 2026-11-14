"""缩放：把图片或视频缩放到指定分辨率。

规则（来自需求）：**目标宽、高都必须小于原分辨率**，也就是只允许缩小。

输出命名：``原名_宽x高.扩展名``（宽高为**实际输出**的尺寸，可能因编码要求取偶），
落在 ``processed`` 目录下。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from imagevideoprocess.core.errors import InvalidParameterError, UnsupportedFormatError
from imagevideoprocess.core.progress import CancelToken, ProgressFn, noop_progress
from imagevideoprocess.core.result import ProcessResult
from imagevideoprocess.media.image_ops import pil_format_for, save_image
from imagevideoprocess.media.media_info import probe, register_image_plugins
from imagevideoprocess.media.video_ops import TranscodeSpec, analyze, transcode
from imagevideoprocess.runtime.paths import processed_dir, unique_path

#: 视频缩放的编码质量（CRF 越小越好，18 接近视觉无损）
_VIDEO_CRF = 18


def validate_size(info_width: int, info_height: int, width: int, height: int) -> None:
    """校验目标分辨率。

    Raises:
        InvalidParameterError: 参数不是正整数或没有小于原分辨率。
    """
    for name, value in (("宽", width), ("高", height)):
        if value <= 0:
            raise InvalidParameterError(f"{name}必须是大于 0 的整数")
    if width >= info_width or height >= info_height:
        raise InvalidParameterError(
            f"目标分辨率需小于原分辨率（当前 {info_width}×{info_height}），本工具只做缩小"
        )


def resize_image(
    source: str | Path,
    width: int,
    height: int,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """缩放单张图片。"""
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if info.kind != "image":
        raise InvalidParameterError("该文件不是图片")
    validate_size(info.width, info.height, width, height)

    register_image_plugins()
    fmt = pil_format_for(src.suffix) or (info.format or "").upper()
    if not fmt:
        raise UnsupportedFormatError(f"无法确定 {src.name} 的输出格式")

    progress(10)
    with Image.open(src) as handle:
        handle.load()
        token.raise_if_cancelled()
        exif = handle.info.get("exif")
        resized = handle.resize((width, height), Image.Resampling.LANCZOS)
        progress(60)

        folder = Path(out_dir) if out_dir else processed_dir()
        folder.mkdir(parents=True, exist_ok=True)
        dest = unique_path(folder / f"{src.stem}_{width}x{height}{src.suffix.lower()}")
        save_image(resized, dest, fmt, quality=95, exif=exif if isinstance(exif, bytes) else None)

    progress(100)
    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=dest.stat().st_size,
        verb="缩放",
        note=f"{info.resolution_text} → {width}×{height}",
    )


def resize_video(
    source: str | Path,
    width: int,
    height: int,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """缩放单个视频（重新编码，音频原样复用）。"""
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if info.kind != "video":
        raise InvalidParameterError("该文件不是视频")
    validate_size(info.width, info.height, width, height)

    streams = analyze(src)
    suffix = src.suffix.lower()
    container_format = streams.container_format or "mp4"
    if streams.container_format is None:
        suffix = ".mp4"

    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)

    # 编码要求宽高为偶数：先算实际输出尺寸，再据此命名
    actual_width = max(2, width - width % 2)
    actual_height = max(2, height - height % 2)
    dest = unique_path(folder / f"{src.stem}_{actual_width}x{actual_height}{suffix}")

    outcome = transcode(
        src,
        dest,
        TranscodeSpec(
            container_format=container_format,
            crf=_VIDEO_CRF,
            preset="medium",
            target_size=(actual_width, actual_height),
            keep_audio=True,
        ),
        cancel=token,
        progress=progress,
    )

    note = f"{info.resolution_text} → {actual_width}×{actual_height}"
    if (actual_width, actual_height) != (width, height):
        note += "（宽高已取偶）"
    if outcome.note:
        note += f"；{outcome.note}"

    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=outcome.size_bytes,
        verb="缩放",
        note=note,
    )


def resize(
    source: str | Path,
    width: int,
    height: int,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """按文件类型自动分派到图片 / 视频缩放。"""
    info = probe(source)
    if info.kind == "video":
        return resize_video(
            source, width, height, out_dir=out_dir, cancel=cancel, progress=progress
        )
    return resize_image(source, width, height, out_dir=out_dir, cancel=cancel, progress=progress)
