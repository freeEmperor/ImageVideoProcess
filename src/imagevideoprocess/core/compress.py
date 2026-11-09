"""压缩：把图片或视频压到指定的目标体积以内。

- 图片：JPEG / WebP / AVIF / HEIF 用「二分查找质量」逼近目标体积；
  PNG 是无损格式，改用「二分查找调色板颜色数 + 必要时降采样」逼近。
- 视频：按目标体积反推视频码率（扣掉音频占用），用 H.264 重新编码；
  若第一遍超了目标，按实际结果修正码率再压一遍。

输出命名：``原名_compressed.扩展名``，落在 ``processed`` 目录下。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from imagevideoprocess.core.errors import (
    InvalidParameterError,
    ProcessingError,
    UnsupportedFormatError,
)
from imagevideoprocess.core.image_ops import encode_to_bytes
from imagevideoprocess.core.media_info import probe, register_image_plugins
from imagevideoprocess.core.paths import processed_dir, unique_path
from imagevideoprocess.core.progress import CancelToken, ProgressFn, noop_progress
from imagevideoprocess.core.result import ProcessResult
from imagevideoprocess.core.video_ops import (
    TranscodeSpec,
    analyze,
    audio_compatible,
    can_encode_aac,
    transcode,
)

#: 输出文件名后缀标记
SUFFIX_TAG = "compressed"

#: 可压缩的图片格式 → 质量搜索区间（低, 高）
_QUALITY_RANGE: dict[str, tuple[int, int]] = {
    "JPEG": (5, 95),
    "MPO": (5, 95),
    "WEBP": (5, 95),
    "AVIF": (1, 95),
    "HEIF": (1, 95),
    "HEIC": (1, 95),
}

#: 无损图片格式：只能靠「减色 + 降采样」
_PALETTE_FORMATS: frozenset[str] = frozenset({"PNG"})

#: 视频码率下限（bit/s）：再低就没法看了
_MIN_VIDEO_BITRATE = 40_000

#: 音频码率未知时按这个估算（bit/s）
_ASSUMED_AUDIO_BITRATE = 128_000

#: 音频最多占目标码率的比例（其余留给画面）
_AUDIO_SHARE = 0.12

#: 音频重编码的码率下限（bit/s）
_MIN_AUDIO_BITRATE = 32_000

#: 第一遍编码预留的余量（容器 / 索引开销）
_SIZE_HEADROOM = 0.96

#: 最多压几遍（第一遍超了就修正码率再来一遍）
_MAX_ATTEMPTS = 2

#: 图片降采样逼近的缩放系数与最大次数
_DOWNSCALE_STEP = 0.85
_MAX_DOWNSCALE_STEPS = 14
_MIN_SIDE = 16


def target_bytes_of(value: float, unit: str) -> int:
    """把「数值 + 单位」换算成字节数。

    Args:
        value: 0~1024 之间的数值。
        unit: ``kb`` / ``mb`` / ``gb``（不区分大小写）。
    """
    factors = {"kb": 1024, "mb": 1024**2, "gb": 1024**3}
    factor = factors.get(unit.strip().lower())
    if factor is None:
        raise InvalidParameterError(f"不认识的大小单位：{unit}")
    return int(round(value * factor))


# ----------------------------------------------------------------- 图片部分
def _search_bytes(
    encode: Callable[[int], bytes],
    low: int,
    high: int,
    target: int,
    token: CancelToken,
) -> bytes | None:
    """二分查找满足 ``len(<=target)`` 的最大档位，返回最小的可用编码结果。

    档位越大文件越大（质量/颜色数都是这个方向），所以可以直接二分。
    """
    best: bytes | None = None
    while low <= high:
        token.raise_if_cancelled()
        mid = (low + high) // 2
        data = encode(mid)
        if len(data) <= target:
            best = data
            low = mid + 1
        else:
            high = mid - 1
    return best


def _best_image_bytes(
    image: Image.Image, fmt: str, target: int, token: CancelToken
) -> bytes | None:
    """在给定分辨率下尝试各种手段逼近目标体积，达不到返回 None。"""
    if fmt in _QUALITY_RANGE:
        low, high = _QUALITY_RANGE[fmt]
        return _search_bytes(
            lambda q: encode_to_bytes(image, fmt, quality=q), low, high, target, token
        )
    if fmt in _PALETTE_FORMATS:
        token.raise_if_cancelled()
        lossless = encode_to_bytes(image, fmt)
        if len(lossless) <= target:
            return lossless
        return _search_bytes(lambda c: encode_to_bytes(image, fmt, colors=c), 2, 256, target, token)
    raise UnsupportedFormatError(f"暂不支持压缩 {fmt} 格式的图片")


def compress_image(
    source: str | Path,
    target_bytes: int,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """把单张图片压到 ``target_bytes`` 以内。"""
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if target_bytes >= info.size_bytes:
        raise InvalidParameterError("期望大小必须小于原文件大小")

    register_image_plugins()
    with Image.open(src) as handle:
        handle.load()
        fmt = (handle.format or src.suffix.lstrip(".")).upper()
        if getattr(handle, "n_frames", 1) > 1:
            raise UnsupportedFormatError("动图（多帧图片）暂不支持压缩，请先抽帧")
        working = handle.copy()

    progress(5)
    scale = 1.0
    data: bytes | None = None
    for _ in range(_MAX_DOWNSCALE_STEPS):
        token.raise_if_cancelled()
        if scale == 1.0:
            candidate = working
        else:
            size = (max(1, int(working.width * scale)), max(1, int(working.height * scale)))
            candidate = working.resize(size, Image.Resampling.LANCZOS)
        data = _best_image_bytes(candidate, fmt, target_bytes, token)
        if data is not None:
            working = candidate
            break
        if min(working.width, working.height) * scale < _MIN_SIDE:
            break
        scale *= _DOWNSCALE_STEP
        progress(5 + int(60 * (1 - scale)))

    if data is None:
        raise ProcessingError(f"无法把图片压到 {target_bytes} 字节以内，请把期望值调大一些")

    progress(70)
    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / f"{src.stem}_{SUFFIX_TAG}{src.suffix.lower()}")
    dest.write_bytes(data)
    progress(100)

    note = ""
    if (working.width, working.height) != (info.width, info.height):
        note = f"已降采样到 {working.width}×{working.height} 才达到目标体积"
    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=dest.stat().st_size,
        verb="压缩",
        note=note,
    )


# ----------------------------------------------------------------- 视频部分
def compress_video(
    source: str | Path,
    target_bytes: int,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """把单个视频压到 ``target_bytes`` 以内。"""
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if info.kind != "video":
        raise InvalidParameterError("该文件不是视频，无法按体积压缩")
    if target_bytes >= info.size_bytes:
        raise InvalidParameterError("期望大小必须小于原文件大小")

    streams = analyze(src)
    if not streams.duration or streams.duration <= 0:
        raise ProcessingError("读不到视频时长，无法按目标体积推算码率")

    container_format = streams.container_format
    suffix = src.suffix.lower()
    if container_format is None:
        # 源扩展名不是已知输出容器，退化成 mp4（容器和扩展名要一致）
        container_format = "mp4"
        suffix = ".mp4"

    duration = float(streams.duration)
    total_bitrate = target_bytes * 8 / duration

    # 音频预算：能原样复用就复用，装不下才降码率重编码为 AAC
    note_parts: list[str] = []
    audio_target: int | None = None
    audio_bytes = 0
    if streams.audio_codec:
        source_audio = int(streams.audio_bitrate or _ASSUMED_AUDIO_BITRATE)
        compatible = audio_compatible(container_format, streams.audio_codec)
        desired = int(min(max(total_bitrate * _AUDIO_SHARE, _MIN_AUDIO_BITRATE), source_audio))
        if compatible and source_audio <= desired * 1.2:
            audio_bytes = int(duration * source_audio / 8)
        elif can_encode_aac(streams.audio_sample_rate, streams.audio_channels):
            audio_target = desired
            audio_bytes = int(duration * desired / 8)
        elif compatible:
            audio_bytes = int(duration * source_audio / 8)
        else:
            audio_bytes = 0
            note_parts.append("音频编码与目标容器不兼容，已丢弃音频")

    budget = int(target_bytes * _SIZE_HEADROOM) - audio_bytes
    min_video_bytes = int(duration * _MIN_VIDEO_BITRATE / 8)
    if budget < min_video_bytes:
        budget = min_video_bytes
        note_parts.append("期望体积过小，已按最低可用码率压缩，实际结果可能超出期望值")

    bitrate = max(_MIN_VIDEO_BITRATE, int(budget * 8 / duration))

    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / f"{src.stem}_{SUFFIX_TAG}{suffix}")

    outcome = None
    for attempt in range(_MAX_ATTEMPTS):
        token.raise_if_cancelled()
        outcome = transcode(
            src,
            dest,
            TranscodeSpec(
                container_format=container_format,
                video_bitrate=bitrate,
                audio_bitrate=audio_target,
                preset="veryfast",
                keep_audio=True,
            ),
            cancel=token,
            progress=progress,
        )
        if outcome.size_bytes <= target_bytes or attempt == _MAX_ATTEMPTS - 1:
            break
        # 第一遍超了：按实际结果把码率往下修，再压一遍
        bitrate = max(
            _MIN_VIDEO_BITRATE,
            int(bitrate * (target_bytes * 0.92) / max(1, outcome.size_bytes)),
        )
        progress(0)

    assert outcome is not None  # 循环至少执行一次
    if outcome.note:
        note_parts.append(outcome.note)
    if outcome.size_bytes > target_bytes:
        ratio = outcome.size_bytes / max(1, target_bytes) * 100
        note_parts.append(f"已尽力压缩，实际为期望值的 {ratio:.0f}%")

    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=outcome.size_bytes,
        verb="压缩",
        note="；".join(note_parts),
    )


# ----------------------------------------------------------------- 统一入口
def compress(
    source: str | Path,
    target_bytes: int,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """按文件类型自动分派到图片 / 视频压缩。"""
    info = probe(source)
    if info.kind == "video":
        return compress_video(
            source, target_bytes, out_dir=out_dir, cancel=cancel, progress=progress
        )
    return compress_image(source, target_bytes, out_dir=out_dir, cancel=cancel, progress=progress)
