"""视频抽帧：从指定起点开始，按「帧数」或「秒数」跨度提取图片。

用户输入的两种单位组合：

==================  ==========================  ========================================
输入                含义                        举例
==================  ==========================  ========================================
（40s，10帧）       从第 40 秒起取 10 张        第 40.00s 那帧及其后 9 帧
（40s，1s）         从第 40 秒起取 1 秒内所有帧  30fps 视频 = 30 张
（100帧，10帧）     从第 100 帧起取 10 张        第 100~109 帧
==================  ==========================  ========================================

输出命名：``原名_000100.png``，6 位数字是**该帧在原视频中的帧号**（默认 PNG，
可在界面上改成 jpg / webp / bmp / tiff），落在 ``processed`` 目录下。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import av

from imagevideoprocess.core.errors import InvalidParameterError, ProcessingError
from imagevideoprocess.core.image_ops import PIL_FORMAT_BY_SUFFIX, QUALITY_FORMATS
from imagevideoprocess.core.media_info import MediaInfo, probe
from imagevideoprocess.core.paths import processed_dir
from imagevideoprocess.core.progress import CancelToken, ProgressFn, clamp_percent, noop_progress
from imagevideoprocess.core.result import ProcessResult
from imagevideoprocess.core.video_ops import stream_fps

#: 单位：秒 / 帧
UNIT_SECONDS = "s"
UNIT_FRAMES = "f"

#: 界面上可选单位 → 显示名
UNIT_LABELS: dict[str, str] = {UNIT_SECONDS: "秒", UNIT_FRAMES: "帧"}

#: 界面上可选的输出图片格式（扩展名，不带点）
OUTPUT_FORMATS: tuple[str, ...] = ("png", "jpg", "webp", "bmp", "tiff")

#: seek 时向前多退一点，保证解码器能从关键帧顺利推到目标帧
_SEEK_BACKOFF_SECONDS = 1.5


@dataclass(frozen=True)
class FrameRange:
    """换算并校验过的抽帧区间。"""

    start_frame: int
    count: int
    fps: float
    total_frames: int

    @property
    def end_frame(self) -> int:
        """最后一帧的帧号（含）。"""
        return self.start_frame + self.count - 1

    @property
    def start_time(self) -> float:
        """起始时间（秒）。"""
        return self.start_frame / self.fps

    @property
    def end_time(self) -> float:
        """结束时间（秒，不含）。"""
        return (self.start_frame + self.count) / self.fps

    @property
    def text(self) -> str:
        """给界面用的一行摘要。"""
        return (
            f"第 {self.start_frame} ~ {self.end_frame} 帧（共 {self.count} 张）"
            f"，时间 {self.start_time:.2f}s ~ {self.end_time:.2f}s"
        )


def resolve_range(
    info: MediaInfo,
    start_value: float,
    start_unit: str,
    span_value: float,
    span_unit: str,
) -> FrameRange:
    """把界面输入换算成帧区间，并校验是否落在视频范围内。

    Raises:
        InvalidParameterError: 输入非法或超出视频范围。
    """
    if info.kind != "video":
        raise InvalidParameterError("抽帧功能只支持视频文件")
    fps = info.fps
    if not fps or fps <= 0:
        raise InvalidParameterError("读不到该视频的帧率，无法换算帧号")

    total = info.frame_count
    if not total and info.duration:
        total = int(round(info.duration * fps))
    if not total:
        raise InvalidParameterError("读不到该视频的总帧数，无法校验区间")

    if start_unit not in UNIT_LABELS or span_unit not in UNIT_LABELS:
        raise InvalidParameterError("单位只能是「秒」或「帧」")
    if start_value < 0:
        raise InvalidParameterError("起始位置不能为负数")
    if span_value <= 0:
        raise InvalidParameterError("跨度必须大于 0")

    start_frame = int(round(start_value * fps)) if start_unit == UNIT_SECONDS else int(start_value)
    count = int(round(span_value * fps)) if span_unit == UNIT_SECONDS else int(span_value)
    count = max(1, count)

    if start_frame >= total:
        raise InvalidParameterError(f"起始位置超出视频范围（共 {total} 帧）")
    if start_frame + count > total:
        raise InvalidParameterError(
            f"帧区间超出视频范围：共 {total} 帧，"
            f"当前区间为 {start_frame} ~ {start_frame + count - 1} 帧"
        )
    return FrameRange(start_frame=start_frame, count=count, fps=fps, total_frames=total)


def output_suffix(image_format: str) -> str:
    """把界面选的格式转成扩展名（不带点）。"""
    fmt = image_format.strip().lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in OUTPUT_FORMATS:
        raise InvalidParameterError(f"不支持的图片格式：{image_format}")
    return fmt


def extract_frames(
    source: str | Path,
    frame_range: FrameRange,
    *,
    image_format: str = "png",
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """按 ``frame_range`` 抽帧并写盘。

    同名文件会被覆盖（命名规则由需求固定为 ``原名_000100.png``）。

    Raises:
        ProcessingError: 视频无法解码。
        Cancelled: 用户取消。
    """
    token = cancel or CancelToken()
    src = Path(source)
    suffix = output_suffix(image_format)
    pil_format = PIL_FORMAT_BY_SUFFIX[f".{suffix}"]
    quality = 95 if pil_format in QUALITY_FORMATS else None

    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    stats = src.stat().st_size
    try:
        with av.open(str(src)) as container:
            if not container.streams.video:
                raise ProcessingError(f"{src.name} 中没有视频轨道")
            vstream = container.streams.video[0]
            fps = stream_fps(vstream) or frame_range.fps
            origin = 0.0
            if vstream.time_base and vstream.start_time:
                origin = float(vstream.start_time * vstream.time_base)

            seek_time = max(0.0, origin + frame_range.start_time - _SEEK_BACKOFF_SECONDS)
            if seek_time > origin:
                container.seek(int(seek_time * av.time_base))

            for frame in container.decode(vstream):
                token.raise_if_cancelled()
                index = _frame_index(frame, fps, origin)
                if index is None:
                    continue
                if index < frame_range.start_frame:
                    continue
                if index >= frame_range.start_frame + frame_range.count:
                    break
                dest = folder / f"{src.stem}_{index:06d}.{suffix}"
                _save_frame(frame, dest, pil_format, quality)
                written.append(dest)
                progress(clamp_percent(len(written) * 100 / frame_range.count))
    except (InvalidParameterError, ProcessingError):
        raise
    except Exception as exc:
        raise ProcessingError(f"抽帧失败：{exc}") from exc

    if not written:
        raise ProcessingError("没有提取到任何帧，请检查起始位置是否有效")

    total_bytes = sum(path.stat().st_size for path in written)
    note = f"帧号 {frame_range.start_frame} ~ {frame_range.start_frame + len(written) - 1}"
    if len(written) < frame_range.count:
        note += f"；只取到 {len(written)} 张（视频末尾不足）"
    progress(100)
    return ProcessResult(
        outputs=written,
        source_path=src,
        source_bytes=stats,
        output_bytes=total_bytes,
        verb="抽帧",
        note=note,
    )


def _frame_index(frame: av.VideoFrame, fps: float, origin: float) -> int | None:
    """算出这一帧在原视频中的帧号（优先用时间戳，其次用 pts）。"""
    try:
        if frame.time is not None:
            return int(round((float(frame.time) - origin) * fps))
        if frame.pts is not None and frame.time_base is not None:
            return int(round((float(frame.pts * frame.time_base) - origin) * fps))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return None


def _save_frame(frame: av.VideoFrame, dest: Path, pil_format: str, quality: int | None) -> None:
    """把一帧写成图片文件。"""
    from imagevideoprocess.core.image_ops import encode_to_bytes

    image = frame.to_image()
    dest.write_bytes(encode_to_bytes(image, pil_format, quality=quality))


def extract_frames_from_info(
    source: str | Path,
    start_value: float,
    start_unit: str,
    span_value: float,
    span_unit: str,
    *,
    image_format: str = "png",
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """便利入口：直接用界面的原始输入抽帧（内部自行探测与换算）。"""
    info = probe(source)
    frame_range = resolve_range(info, start_value, start_unit, span_value, span_unit)
    return extract_frames(
        source,
        frame_range,
        image_format=image_format,
        out_dir=out_dir,
        cancel=cancel,
        progress=progress,
    )
