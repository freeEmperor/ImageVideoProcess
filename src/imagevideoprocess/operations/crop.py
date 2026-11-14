"""视频预览取帧，以及保留指定画面和时段的 MP4 导出。"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import av
import imageio_ffmpeg
from PIL import Image, ImageOps

from imagevideoprocess.core.errors import InvalidParameterError, ProcessingError
from imagevideoprocess.core.progress import CancelToken, ProgressFn, clamp_percent, noop_progress
from imagevideoprocess.core.result import ProcessResult
from imagevideoprocess.media.media_info import probe, register_image_plugins
from imagevideoprocess.runtime.paths import processed_dir, unique_path


@dataclass(frozen=True)
class CropRect:
    """右、下为像素边界，整幅画面为 (0, 0, 宽, 高)。"""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def is_valid(self, width: int, height: int) -> bool:
        return 0 <= self.left < self.right <= width and 0 <= self.top < self.bottom <= height


@dataclass(frozen=True)
class CropSelection:
    rect: CropRect
    start: float
    end: float

    def validate(self, width: int, height: int, duration: float) -> None:
        if not self.rect.is_valid(width, height):
            raise InvalidParameterError("左上坐标必须小于右下坐标，并且都在画面内")
        if not 0 <= self.start < self.end <= duration:
            raise InvalidParameterError("开始时间必须早于结束时间，并且都在视频时长内")


@dataclass(frozen=True)
class PreviewFrame:
    image: Image.Image
    width: int
    height: int


def _frame_at(source: Path, seconds: float) -> av.VideoFrame:
    """选取时刻所在的帧，时间轴以容器起点为 0。"""
    try:
        with av.open(str(source)) as container:
            if not container.streams.video:
                raise ProcessingError("文件中没有视频轨道")
            origin = (container.start_time or 0) / av.time_base
            target = origin + seconds
            if seconds > 0:
                try:
                    container.seek(int(target * av.time_base), backward=True)
                except av.FFmpegError:
                    # 某些容器不能随机定位，重新打开后顺序查找。
                    return _scan_frame(source, target)
            frame = _decode_at(container, target)
            if frame is not None:
                return frame
        return _scan_frame(source, target)
    except (av.FFmpegError, OSError) as exc:
        raise ProcessingError(f"无法读取视频画面：{exc}") from exc


def _scan_frame(source: Path, target: float) -> av.VideoFrame:
    with av.open(str(source)) as container:
        frame = _decode_at(container, target)
    if frame is None:
        raise ProcessingError("视频中没有可解码的画面")
    return frame


def _decode_at(container: av.container.InputContainer, target: float) -> av.VideoFrame | None:
    previous = None
    for frame in container.decode(video=0):
        if frame.time is None or frame.time > target:
            return previous if previous is not None else frame
        previous = frame
    return previous


def _display_size(frame: av.VideoFrame) -> tuple[int, int]:
    return (
        (frame.height, frame.width) if frame.rotation % 180 == 90 else (frame.width, frame.height)
    )


def read_preview(source: Path, seconds: float) -> PreviewFrame:
    frame = _frame_at(source, seconds)
    scale = min(1.0, 1280 / max(frame.width, frame.height))
    image = frame.reformat(
        width=max(1, round(frame.width * scale)),
        height=max(1, round(frame.height * scale)),
        format="rgb24",
    ).to_image()
    if frame.rotation:
        image = image.rotate(frame.rotation, expand=frame.rotation % 180 == 90)
    return PreviewFrame(image, *_display_size(frame))


def crop_video(
    source: Path,
    selection: CropSelection,
    *,
    out_dir: Path | None = None,
    progress: ProgressFn = noop_progress,
    cancel: CancelToken | None = None,
) -> ProcessResult:
    """剪切视频并保留选定时段内的音轨。"""
    token = cancel or CancelToken()
    token.raise_if_cancelled()
    info = probe(source)
    if info.kind != "video" or not info.duration or not math.isfinite(info.duration):
        raise InvalidParameterError("无法确定视频时长")
    selection.validate(*_display_size(_frame_at(source, 0)), info.duration)

    output_folder = processed_dir() if out_dir is None else out_dir
    output_folder.mkdir(parents=True, exist_ok=True)
    destination = output_folder / f"{source.stem}_cut.mp4"
    rect = selection.rect
    duration = selection.end - selection.start
    pixel_format = "yuv444p" if rect.width % 2 or rect.height % 2 else "yuv420p"
    # 先转为无色度抽样的格式，奇数像素偏移也能准确裁剪。
    crop = f"format=yuv444p,crop={rect.width}:{rect.height}:{rect.left}:{rect.top}:exact=1"
    try:
        with TemporaryDirectory(prefix=".cut-", dir=output_folder) as staging:
            folder = Path(staging)
            temporary = folder / "video.mp4"
            command = [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-xerror",
                "-progress",
                "pipe:1",
                "-ss",
                f"{selection.start:.6f}",
                "-i",
                str(source.resolve()),
                "-t",
                f"{duration:.6f}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-map_chapters",
                "-1",
                "-vf",
                crop,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                pixel_format,
                "-fps_mode",
                "passthrough",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(temporary.resolve()),
            ]
            _encode(command, folder, duration, progress, token)
            with av.open(str(temporary)) as output:
                if not output.streams.video or not output.streams.video[0].frames:
                    raise ProcessingError("所选时段没有视频帧，请扩大时间范围")
            token.raise_if_cancelled()
            destination = unique_path(destination)
            temporary.rename(destination)
    except (av.FFmpegError, OSError, RuntimeError) as exc:
        raise ProcessingError(f"无法导出裁剪视频：{exc}") from exc

    progress(100)
    return ProcessResult(
        outputs=[destination],
        source_path=source,
        source_bytes=info.size_bytes,
        output_bytes=destination.stat().st_size,
        verb="裁剪",
    )


def _encode(
    command: list[str], folder: Path, duration: float, progress: ProgressFn, token: CancelToken
) -> None:
    log = folder / "progress"
    errors = folder / "errors"
    token.raise_if_cancelled()
    progress(0)
    with (
        log.open("wb") as stdout,
        errors.open("wb") as stderr,
        log.open("rb") as updates,
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as process,
    ):
        try:
            while process.poll() is None:
                token.raise_if_cancelled()
                try:
                    process.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    for line in updates:
                        key, _, value = line.strip().partition(b"=")
                        if key == b"out_time_us" and value.lstrip(b"-").isdigit():
                            progress(min(99, clamp_percent(int(value) / (duration * 10_000))))
            token.raise_if_cancelled()
        finally:
            if process.poll() is None:
                process.kill()
    if process.returncode != 0:
        details = errors.read_text(encoding="utf-8", errors="replace").strip()
        raise ProcessingError(f"视频裁剪失败：{details[-1200:] or process.returncode}")


def read_image_preview(source: Path) -> PreviewFrame:
    register_image_plugins()
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
    width, height = image.size
    image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    return PreviewFrame(image, width, height)


def crop_image(
    source: Path,
    rect: CropRect,
    *,
    out_dir: Path | None = None,
    progress: ProgressFn = noop_progress,
    cancel: CancelToken | None = None,
) -> ProcessResult:
    """按显示方向裁剪静态图片，保存为保留透明度的 PNG。"""
    token = cancel or CancelToken()
    token.raise_if_cancelled()
    register_image_plugins()
    progress(0)
    folder = processed_dir() if out_dir is None else out_dir
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original)
            if not rect.is_valid(*image.size):
                raise InvalidParameterError("裁剪坐标必须位于图片内，且宽高大于零")
            cropped = image.convert("RGBA").crop((rect.left, rect.top, rect.right, rect.bottom))
        token.raise_if_cancelled()
        progress(50)
        with TemporaryDirectory(prefix=".cut-", dir=folder) as staging:
            temporary = Path(staging) / "image.png"
            cropped.save(temporary, format="PNG")
            token.raise_if_cancelled()
            destination = unique_path(folder / f"{source.stem}_cut.png")
            temporary.rename(destination)
    except OSError as exc:
        raise ProcessingError(f"图片裁剪失败：{exc}") from exc
    progress(100)
    return ProcessResult(
        outputs=[destination],
        source_path=source,
        source_bytes=source.stat().st_size,
        output_bytes=destination.stat().st_size,
        verb="裁剪",
    )
