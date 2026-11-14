"""媒体文件信息探测：判断是图片还是视频，并读出格式、分辨率、帧率、体积等。

- 图片走 Pillow（额外注册 pillow-heif，以支持 HEIC / HEIF / AVIF）；
- 视频走 PyAV（FFmpeg 绑定），可拿到容器、编码、帧率、总帧数、时长。

GUI 的「待处理文件信息」卡片直接消费 :class:`MediaInfo`，不直接碰第三方库。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from imagevideoprocess.core.errors import ProcessingError, UnsupportedFormatError

Kind = Literal["image", "video"]

#: 按扩展名识别图片
IMAGE_EXTS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".jpe",
        ".jfif",
        ".png",
        ".webp",
        ".bmp",
        ".dib",
        ".tif",
        ".tiff",
        ".gif",
        ".heic",
        ".heif",
        ".avif",
        ".ico",
        ".tga",
    }
)

#: 按扩展名识别视频
VIDEO_EXTS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".flv",
        ".wmv",
        ".mpg",
        ".mpeg",
        ".ts",
        ".m2ts",
        ".mts",
        ".3gp",
        ".3g2",
        ".vob",
        ".rmvb",
        ".rm",
        ".f4v",
        ".ogv",
        ".asf",
    }
)

#: 编码名 → 展示名
_CODEC_DISPLAY: dict[str, str] = {
    "h264": "H.264",
    "hevc": "H.265/HEVC",
    "h265": "H.265/HEVC",
    "mpeg4": "MPEG-4",
    "mpeg2video": "MPEG-2",
    "vp8": "VP8",
    "vp9": "VP9",
    "av1": "AV1",
    "mjpeg": "MJPEG",
    "wmv3": "WMV3",
    "prores": "ProRes",
    "aac": "AAC",
    "mp3": "MP3",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "ac3": "AC-3",
    "flac": "FLAC",
    "pcm_s16le": "PCM",
    "wmav2": "WMA",
}

_heif_registered = False


def register_image_plugins() -> None:
    """注册 pillow-heif 插件（幂等），使 Pillow 能读写 HEIC / HEIF / AVIF。"""
    global _heif_registered
    if _heif_registered:
        return
    _heif_registered = True
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:  # pragma: no cover - pillow-heif 缺失时静默降级
        pass


def format_bytes(num: int) -> str:
    """把字节数格式化成人类可读的字符串。"""
    if num < 1024:
        return f"{num} B"
    value = float(num)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}" if value < 100 else f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


def format_duration(seconds: float | None) -> str:
    """把秒数格式化成 ``时:分:秒.毫秒``。"""
    if seconds is None or seconds <= 0:
        return "—"
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def codec_display(name: str | None) -> str:
    """编码名换成展示名（不认识就原样返回大写）。"""
    if not name:
        return "未知"
    return _CODEC_DISPLAY.get(name.lower(), name.upper())


@dataclass(frozen=True)
class InfoRow:
    """信息卡片里的一行。

    ``full_width`` 为 True 的行独占一整排（路径这类很长的值需要）。
    """

    key: str
    value: str
    full_width: bool = False


@dataclass(frozen=True)
class MediaInfo:
    """一个媒体文件的静态信息。"""

    path: Path
    kind: Kind
    format: str
    width: int
    height: int
    size_bytes: int
    fps: float | None = None
    frame_count: int | None = None
    duration: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    mode: str | None = None
    animated: bool = False

    # ------------------------------------------------------------- 展示用
    @property
    def kind_text(self) -> str:
        """「图片」/「视频」。"""
        if self.kind == "image":
            return "图片"
        return "视频"

    @property
    def resolution_text(self) -> str:
        """``1920 × 1080``。"""
        return f"{self.width} × {self.height}"

    @property
    def size_text(self) -> str:
        """``12.34 MB``。"""
        return format_bytes(self.size_bytes)

    @property
    def fps_text(self) -> str:
        """``29.97 fps``，图片显示 ``—``。"""
        return f"{self.fps:.2f} fps" if self.fps else "—"

    @property
    def frame_count_text(self) -> str:
        """总帧数，未知显示 ``—``。"""
        return f"{self.frame_count:,}" if self.frame_count else "—"

    @property
    def duration_text(self) -> str:
        """时长，图片显示 ``—``。"""
        return format_duration(self.duration) if self.kind == "video" else "—"

    @property
    def codec_text(self) -> str:
        """``H.264 + AAC`` / 图片则给色彩模式。"""
        if self.kind == "image":
            return self.mode or "—"
        parts = [codec_display(self.video_codec)]
        if self.audio_codec:
            parts.append(codec_display(self.audio_codec))
        else:
            parts.append("无音频")
        return " + ".join(parts)

    def rows(self) -> list[InfoRow]:
        """给 GUI 信息卡片用的行列表。

        **路径排第一，且独占一整排**（值很长，两列排版会被挤爆）。
        """
        data: list[InfoRow] = [
            InfoRow("路径", str(self.path), full_width=True),
            InfoRow("文件", self.path.name),
            InfoRow("类型", self.kind_text),
            InfoRow("格式", self.format),
            InfoRow("编码", self.codec_text),
            InfoRow("分辨率", self.resolution_text),
        ]
        if self.kind == "video":
            data.append(InfoRow("帧率", self.fps_text))
            data.append(InfoRow("总帧数", self.frame_count_text))
            data.append(InfoRow("时长", self.duration_text))
        data.append(InfoRow("大小", f"{self.size_text}（{self.size_bytes:,} 字节）"))
        return data


# ---------------------------------------------------------------- 探测实现
def _probe_image(path: Path, size_bytes: int) -> MediaInfo:
    register_image_plugins()
    from PIL import Image

    try:
        with Image.open(path) as img:
            width, height = img.size
            fmt = (img.format or path.suffix.lstrip(".")).upper()
            frames = int(getattr(img, "n_frames", 1) or 1)
            return MediaInfo(
                path=path,
                kind="image",
                format=fmt,
                width=width,
                height=height,
                size_bytes=size_bytes,
                mode=img.mode,
                frame_count=frames,
                animated=frames > 1,
            )
    except ProcessingError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(f"无法读取图片 {path.name}：{exc}") from exc


def _stream_fps(stream: object) -> float | None:
    """从视频流里读出帧率。"""
    for attr in ("average_rate", "guessed_rate", "base_rate"):
        rate = getattr(stream, attr, None)
        if rate:
            try:
                value = float(rate)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if value > 0:
                return value
    return None


def _probe_video(path: Path, size_bytes: int) -> MediaInfo:
    import av

    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise UnsupportedFormatError(f"{path.name} 中没有视频轨道")
            vstream = container.streams.video[0]
            audio_stream = container.streams.audio[0] if container.streams.audio else None
            fps = _stream_fps(vstream)
            duration: float | None = None
            if container.duration:
                duration = container.duration / av.time_base
            elif vstream.duration and vstream.time_base:
                duration = float(vstream.duration * vstream.time_base)
            frames = int(vstream.frames or 0)
            if frames <= 0 and duration and fps:
                frames = int(round(duration * fps))
            return MediaInfo(
                path=path,
                kind="video",
                format=path.suffix.lstrip(".").upper() or "VIDEO",
                width=int(vstream.codec_context.width),
                height=int(vstream.codec_context.height),
                size_bytes=size_bytes,
                fps=fps,
                frame_count=frames or None,
                duration=duration,
                video_codec=vstream.codec_context.name,
                audio_codec=audio_stream.codec_context.name if audio_stream else None,
            )
    except ProcessingError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(f"无法读取视频 {path.name}：{exc}") from exc


def probe(path: str | Path) -> MediaInfo:
    """探测文件信息。

    Args:
        path: 待探测的文件路径。

    Raises:
        FileNotFoundError: 文件不存在。
        UnsupportedFormatError: 既不是可读的图片也不是可读的视频。
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"文件不存在：{target}")
    if target.is_dir():
        raise UnsupportedFormatError(f"{target.name} 是文件夹，请拖入文件")
    size_bytes = target.stat().st_size
    if size_bytes <= 0:
        raise UnsupportedFormatError(f"{target.name} 是空文件")

    suffix = target.suffix.lower()
    if suffix in VIDEO_EXTS:
        return _probe_video(target, size_bytes)
    if suffix in IMAGE_EXTS:
        return _probe_image(target, size_bytes)

    # 扩展名不认识：两种都试一遍
    try:
        return _probe_image(target, size_bytes)
    except ProcessingError:
        pass
    return _probe_video(target, size_bytes)
