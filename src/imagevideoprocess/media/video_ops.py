"""视频转码引擎：压缩 / 缩放 / 后续其它视频功能共用的底层实现。

对外暴露：

- :func:`analyze` —— 打开一次视频，读出分辨率 / 帧率 / 帧数 / 时长 / 音频信息；
- :func:`transcode` —— 按 :class:`TranscodeSpec` 重新编码视频（H.264 或 VP9），
  音频默认原样复用（stream copy，不重新编码，省时且无损），
  当目标体积装不下原音频时才降码率重编码为 AAC。

实现要点（都是踩过的坑，改动前请先读）：

1. PyAV 18 **没有** ``add_stream(template=...)``，必须用 ``add_stream_from_template``。
2. 逐帧解码 / 编码用 ``container.demux([视频流, 音频流])`` 的写法：
   视频包解码后重编码，音频包直接把 ``packet.stream`` 换成输出流再 mux，
   这样音视频时间戳能自然对齐。
3. ``yuv420p`` 要求宽高都是偶数，所以输出分辨率一律向下取偶。
4. 先写 ``xxx.part`` 再 ``replace`` 成正式文件，中途失败不会留下半个坏文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import av
import cv2
import numpy as np
from av.audio.stream import AudioStream
from av.stream import Stream
from av.video.stream import VideoStream

from imagevideoprocess.core.errors import ProcessingError, UnsupportedFormatError
from imagevideoprocess.core.progress import CancelToken, ProgressFn, clamp_percent, noop_progress
from imagevideoprocess.media import audio_ops

#: 扩展名 → FFmpeg 输出容器名
_OUTPUT_CONTAINERS: dict[str, str] = {
    ".mp4": "mp4",
    ".m4v": "mp4",
    ".mov": "mov",
    ".mkv": "matroska",
    ".webm": "webm",
    ".avi": "avi",
    ".ts": "mpegts",
    ".m2ts": "mpegts",
    ".flv": "flv",
    ".wmv": "asf",
    ".asf": "asf",
    ".mpg": "mpeg",
    ".mpeg": "mpeg",
    ".3gp": "3gp",
}

#: 容器能直接复用的音频编码；None 表示「什么都行」
_CONTAINER_AUDIO_OK: dict[str, set[str] | None] = {
    "mp4": {"aac", "mp3", "ac3", "eac3", "alac"},
    "mov": {"aac", "mp3", "ac3", "alac", "pcm_s16le", "pcm_s24le"},
    "3gp": {"aac"},
    "matroska": None,
    "webm": {"opus", "vorbis"},
    "avi": {"mp3", "ac3", "pcm_s16le"},
    "mpegts": {"aac", "mp3", "ac3"},
    "asf": {"wmav2", "mp3"},
    "flv": {"aac", "mp3"},
    "mpeg": {"mp2", "mp3"},
}

#: 容器能直接复用的视频编码（用于「无损转封装」判断）；None 表示「什么都行」
_CONTAINER_VIDEO_OK: dict[str, set[str] | None] = {
    "mp4": {"h264", "hevc", "mpeg4", "av1", "vp9"},
    "mov": {"h264", "hevc", "mpeg4", "prores", "mjpeg", "dnxhd"},
    "3gp": {"h264", "h263", "mpeg4"},
    "matroska": None,
    "webm": {"vp8", "vp9", "av1"},
    "avi": {"mpeg4", "mjpeg", "h264", "msmpeg4"},
    "mpegts": {"h264", "hevc", "mpeg2video"},
    "asf": {"wmv2", "wmv3", "msmpeg4"},
    "flv": {"h264", "flv1"},
    "mpeg": {"mpeg1video", "mpeg2video"},
}

#: AAC 编码器支持的采样率（源采样率不在此列就不做音频重编码，退回原样复用）
_AAC_SAMPLE_RATES: frozenset[int] = frozenset(
    {96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000}
)


def container_format_for(suffix: str) -> str | None:
    """扩展名 → 容器名；不认识的扩展名返回 None。"""
    return _OUTPUT_CONTAINERS.get(suffix.lower())


def audio_compatible(container_format: str, audio_codec: str | None) -> bool:
    """该音频编码能否直接复用进目标容器。

    注意：这里会先把编码器名归一成编码名（``libmp3lame`` → ``mp3``、
    ``libopus`` → ``opus``），否则拿编码器名去查表会误判成"不兼容"，
    进而把音轨丢掉。
    """
    if not audio_codec:
        return False
    allowed = _CONTAINER_AUDIO_OK.get(container_format, set())
    if allowed is None:
        return True
    return audio_ops.normalize_codec(audio_codec) in allowed


def video_compatible(container_format: str, video_codec: str | None) -> bool:
    """该视频编码能否直接复用进目标容器。"""
    if not video_codec:
        return False
    allowed = _CONTAINER_VIDEO_OK.get(container_format, set())
    if allowed is None:
        return True
    return video_codec.lower() in allowed


def can_remux(container_format: str, video_codec: str | None, audio_codec: str | None) -> bool:
    """能否不重新编码、直接把音视频搬进目标容器（无损转封装）。"""
    if not video_compatible(container_format, video_codec):
        return False
    return not audio_codec or audio_compatible(container_format, audio_codec)


def video_codec_for(container_format: str) -> str:
    """目标容器的视频编码：webm 只能装 VP9，其余统一 H.264。"""
    return "libvpx-vp9" if container_format == "webm" else "libx264"


def even_size(size: tuple[int, int]) -> tuple[int, int]:
    """把宽高向下取偶（yuv420p 的硬性要求）。"""
    return (max(2, size[0] - size[0] % 2), max(2, size[1] - size[1] % 2))


def stream_fps(stream: object) -> float | None:
    """从视频流里读帧率。"""
    for attr in ("average_rate", "guessed_rate", "base_rate"):
        rate = getattr(stream, attr, None)
        if not rate:
            continue
        try:
            value = float(rate)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if value > 0:
            return value
    return None


def can_encode_aac(sample_rate: int | None, channels: int | None) -> bool:
    """判断能否把音频重编码成 AAC（采样率与声道数都要合法）。"""
    if not sample_rate or not channels:
        return False
    return sample_rate in _AAC_SAMPLE_RATES and 1 <= channels <= 2


@dataclass(frozen=True)
class SourceStreams:
    """打开视频后拿到的基础信息。"""

    width: int
    height: int
    fps: float | None
    duration: float | None
    frame_count: int | None
    video_codec: str
    audio_codec: str | None
    audio_bitrate: int | None
    audio_sample_rate: int | None
    audio_channels: int | None
    container_format: str | None

    @property
    def resolution(self) -> tuple[int, int]:
        """``(宽, 高)``。"""
        return (self.width, self.height)


@dataclass
class TranscodeSpec:
    """一次转码的参数。"""

    container_format: str
    #: 目标视频码率（bit/s）。与 crf 二选一：给了码率就走 ABR。
    video_bitrate: int | None = None
    #: 目标质量（恒定质量模式，0~51，越小越好）。码率为 None 时生效。
    crf: int | None = None
    #: 输出分辨率；None 表示保持原样。
    target_size: tuple[int, int] | None = None
    #: 目标音频码率（bit/s）。None / 不小于源码率时原样复用音频。
    audio_bitrate: int | None = None
    #: 强制把音频重编码成指定编码（如 webm 必须要 opus）。None 表示能复用就复用。
    audio_codec: str | None = None
    #: 音频重编码用的采样率 / 帧长（Opus 需要 48000 Hz、960 采样）。
    audio_forced_sample_rate: int | None = None
    audio_frame_size: int | None = None
    #: 是否保留音频（容器不兼容时会自动丢弃）。
    keep_audio: bool = True
    #: x264 预设，越大越慢越小。
    preset: str = "veryfast"
    #: 覆盖视频编码（默认按容器自动选）。
    video_codec: str | None = None
    extra_options: dict[str, str] = field(default_factory=dict)


@dataclass
class TranscodeOutcome:
    """转码结果。"""

    path: Path
    size_bytes: int
    frames_written: int
    audio_kept: bool
    note: str = ""


def analyze(source: str | Path) -> SourceStreams:
    """打开视频读基础信息（不解码，很快）。"""
    target = Path(source)
    try:
        with av.open(str(target)) as container:
            if not container.streams.video:
                raise UnsupportedFormatError(f"{target.name} 中没有视频轨道")
            vstream = container.streams.video[0]
            astream = container.streams.audio[0] if container.streams.audio else None
            fps = stream_fps(vstream)
            duration: float | None = None
            if container.duration:
                duration = container.duration / av.time_base
            elif vstream.duration and vstream.time_base:
                duration = float(vstream.duration * vstream.time_base)
            frame_count = int(vstream.frames or 0)
            if frame_count <= 0 and duration and fps:
                frame_count = int(round(duration * fps))
            return SourceStreams(
                width=int(vstream.codec_context.width),
                height=int(vstream.codec_context.height),
                fps=fps,
                duration=duration,
                frame_count=frame_count or None,
                video_codec=vstream.codec_context.name or "",
                audio_codec=astream.codec_context.name if astream else None,
                audio_bitrate=(int(astream.codec_context.bit_rate or 0) or None)
                if astream
                else None,
                audio_sample_rate=int(astream.codec_context.sample_rate or 0) if astream else None,
                audio_channels=(len(astream.codec_context.layout.channels) if astream else None),
                container_format=container_format_for(target.suffix),
            )
    except ProcessingError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(f"无法解析视频 {target.name}：{exc}") from exc


def _frame_total(container: av.container.InputContainer, vstream: Stream, fps: float | None) -> int:
    """估算总帧数，用于进度条。"""
    frames = int(getattr(vstream, "frames", 0) or 0)
    if frames > 0:
        return frames
    duration: float | None = None
    if container.duration:
        duration = container.duration / av.time_base
    else:
        stream_duration = getattr(vstream, "duration", None)
        time_base = getattr(vstream, "time_base", None)
        if stream_duration and time_base:
            duration = float(stream_duration * time_base)
    if duration and fps:
        return int(round(duration * fps))
    return 0


def _add_audio_stream(out: av.container.OutputContainer, source_stream: AudioStream) -> AudioStream:
    """按模板复制一条音频流（编码 / 时间基沿用源流）。"""
    adder = getattr(out, "add_stream_from_template", None)
    if adder is not None:
        return cast(AudioStream, adder(source_stream))
    return cast(AudioStream, out.add_stream(template=source_stream))  # type: ignore[call-overload]  # PyAV < 9


def _resize_frame(frame: av.VideoFrame, width: int, height: int) -> av.VideoFrame:
    """用 OpenCV 缩放一帧（缩小用 INTER_AREA，放大用 Lanczos），并保留时间戳。"""
    array = frame.to_ndarray(format="bgr24")
    shrinking = width * height < frame.width * frame.height
    interpolation = cv2.INTER_AREA if shrinking else cv2.INTER_LANCZOS4
    resized = cast(
        "np.ndarray[Any, np.dtype[np.uint8]]",
        np.ascontiguousarray(cv2.resize(array, (width, height), interpolation=interpolation)),
    )
    out = av.VideoFrame.from_ndarray(resized, format="bgr24")
    out.pts = frame.pts
    out.time_base = frame.time_base
    return out


def transcode(
    source: str | Path,
    dest: str | Path,
    spec: TranscodeSpec,
    *,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> TranscodeOutcome:
    """把 ``source`` 转码写成 ``dest``（先写 .part，成功后原子替换）。

    Raises:
        ProcessingError: 视频不可解析或没有解出任何帧。
        Cancelled: 用户取消。
    """
    token = cancel or CancelToken()
    src = Path(source)
    dst = Path(dest)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name + ".part")
    temp.unlink(missing_ok=True)

    notes: list[str] = []
    try:
        frames_written, audio_kept = _run(src, temp, spec, token, progress, notes)
        temp.replace(dst)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise

    progress(100)
    return TranscodeOutcome(
        path=dst,
        size_bytes=dst.stat().st_size,
        frames_written=frames_written,
        audio_kept=audio_kept,
        note="；".join(notes),
    )


def remux(
    source: str | Path,
    dest: str | Path,
    container_format: str,
    *,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> TranscodeOutcome:
    """**不重新编码**，只换容器（音视频流原样搬过去）。

    用于格式转换：源编码本来就兼容目标容器时，这样最快且完全无损。
    调用前请先用 :func:`can_remux` 判断能否这么做。

    Raises:
        ProcessingError: 视频不可解析或读取失败。
        Cancelled: 用户取消。
    """
    token = cancel or CancelToken()
    src = Path(source)
    dst = Path(dest)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name + ".part")
    temp.unlink(missing_ok=True)

    try:
        with av.open(str(src)) as container:
            if not container.streams.video:
                raise UnsupportedFormatError(f"{src.name} 中没有视频轨道")
            vstream_in = container.streams.video[0]
            astream_in = container.streams.audio[0] if container.streams.audio else None
            fps = stream_fps(vstream_in)
            total = _frame_total(container, vstream_in, fps)

            with av.open(str(temp), mode="w", format=container_format) as out:
                vstream_out = out.add_stream_from_template(vstream_in)
                astream_out = (
                    out.add_stream_from_template(astream_in) if astream_in is not None else None
                )
                streams: list[Stream] = [vstream_in]
                if astream_in is not None and astream_out is not None:
                    streams.append(astream_in)

                done = 0
                last_percent = -1
                for packet in container.demux(streams):
                    token.raise_if_cancelled()
                    if packet.dts is None:
                        continue
                    if packet.stream.index == vstream_in.index:
                        packet.stream = vstream_out
                        done += 1
                        percent = clamp_percent(done * 100 / total) if total else 0
                        if percent != last_percent:
                            last_percent = percent
                            progress(percent)
                    elif astream_out is not None:
                        packet.stream = astream_out
                    else:
                        continue
                    out.mux(packet)
        temp.replace(dst)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise

    progress(100)
    return TranscodeOutcome(
        path=dst,
        size_bytes=dst.stat().st_size,
        frames_written=done,
        audio_kept=astream_in is not None,
        note="未重新编码，直接转封装（画质无损）",
    )


def _run(
    src: Path,
    temp: Path,
    spec: TranscodeSpec,
    token: CancelToken,
    progress: ProgressFn,
    notes: list[str],
) -> tuple[int, bool]:
    """真正的转码循环，返回 (写入帧数, 是否保留音频)。"""
    with av.open(str(src)) as container:
        if not container.streams.video:
            raise UnsupportedFormatError(f"{src.name} 中没有视频轨道")
        vstream_in = container.streams.video[0]
        astream_in = container.streams.audio[0] if container.streams.audio else None
        fps = stream_fps(vstream_in)
        total = _frame_total(container, vstream_in, fps)

        src_width = int(vstream_in.codec_context.width)
        src_height = int(vstream_in.codec_context.height)
        width, height = even_size(spec.target_size or (src_width, src_height))
        if spec.target_size and (width, height) != tuple(spec.target_size):
            notes.append(f"为满足编码要求已把分辨率调整为 {width}×{height}")
        if total == 0:
            notes.append("无法预先取得总帧数，进度仅供参考")

        # 音频策略：能在目标容器里直接复用就复用；装不下就降码率重编码为 AAC
        audio_copy = False
        audio_reencode = False
        audio_rate = 0
        audio_layout = ""
        source_audio_bitrate = 0
        if astream_in is not None and spec.keep_audio:
            ctx = astream_in.codec_context
            source_audio_bitrate = int(ctx.bit_rate or 0)
            audio_rate = int(ctx.sample_rate or 0)
            audio_layout = ctx.layout.name if ctx.layout else ""
            channels = len(ctx.layout.channels) if ctx.layout else 0
            forced_codec = spec.audio_codec
            if forced_codec:
                # 明确指定了目标音频编码（例如 webm 必须要 opus）：
                # 只要这个编码能装进目标容器就重编码，别把音轨丢掉
                if audio_compatible(spec.container_format, forced_codec):
                    audio_reencode = True
                elif spec.container_format == "matroska":
                    audio_reencode = True  # mkv 什么都能装
                else:
                    notes.append(f"目标容器不支持 {forced_codec} 音轨，已丢弃音频")
            elif not audio_compatible(spec.container_format, ctx.name):
                notes.append("音频编码与目标容器不兼容，已丢弃音频")
            elif spec.audio_bitrate and spec.audio_bitrate < max(source_audio_bitrate, 1):
                if can_encode_aac(audio_rate, channels):
                    audio_reencode = True
                else:
                    audio_copy = True
                    notes.append("音频参数不适合重编码，已原样保留音频")
            else:
                audio_copy = True

        codec = spec.video_codec or video_codec_for(spec.container_format)
        options: dict[str, str] = dict(spec.extra_options)
        if codec == "libx264":
            options.setdefault("preset", spec.preset)
            if spec.video_bitrate:
                # 限制峰值，避免短时码率暴涨把总体积顶穿
                options.setdefault("maxrate", str(int(spec.video_bitrate * 1.3)))
                options.setdefault("bufsize", str(int(spec.video_bitrate * 2.5)))
            elif spec.crf is not None:
                options.setdefault("crf", str(spec.crf))
        elif codec == "libvpx-vp9":
            options.setdefault("deadline", "good")
            options.setdefault("cpu-used", "4")
            if spec.crf is not None and not spec.video_bitrate:
                options.setdefault("crf", str(spec.crf))
                options.setdefault("b:v", "0")

        rate = Fraction(fps).limit_denominator(100_000) if fps else None

        with av.open(str(temp), mode="w", format=spec.container_format) as out:
            vstream_out = cast(
                VideoStream,
                out.add_stream(codec, rate=rate, options=options),
            )
            vstream_out.width = width
            vstream_out.height = height
            vstream_out.pix_fmt = "yuv420p"
            if spec.video_bitrate:
                vstream_out.bit_rate = int(spec.video_bitrate)

            astream_out: AudioStream | None = None
            resampler: av.AudioResampler | None = None
            if audio_copy and astream_in is not None:
                astream_out = _add_audio_stream(out, astream_in)
            elif audio_reencode and astream_in is not None:
                audio_codec = spec.audio_codec or "aac"
                sample_format = audio_ops.encoder_sample_format(audio_codec)
                out_rate = audio_ops.encoder_sample_rate(
                    audio_codec, audio_rate, spec.audio_forced_sample_rate
                )
                frame_size = audio_ops.encoder_frame_size(audio_codec, spec.audio_frame_size)
                out_layout = audio_ops.pick_layout(audio_layout, audio_codec)
                astream_out = cast(
                    AudioStream, out.add_stream(audio_codec, rate=out_rate, options={})
                )
                target_bitrate = audio_ops.encoder_bitrate(audio_codec, spec.audio_bitrate)
                if target_bitrate:
                    astream_out.bit_rate = int(target_bitrate)
                astream_out.layout = out_layout
                astream_out.format = sample_format
                # 解码出来的音频格式五花八门，统一重采样成编码器要的样子
                resampler = av.AudioResampler(
                    format=sample_format,
                    layout=out_layout,
                    rate=out_rate,
                    frame_size=frame_size,
                )

            demux_streams: list[Stream] = [vstream_in]
            if astream_in is not None and astream_out is not None:
                demux_streams.append(astream_in)

            done = 0
            audio_broken = False
            last_percent = -1
            for packet in container.demux(demux_streams):
                token.raise_if_cancelled()
                if packet.dts is None:
                    continue
                if packet.stream.index == vstream_in.index:
                    for decoded in packet.decode():
                        if not isinstance(decoded, av.VideoFrame):
                            continue
                        source_frame = (
                            _resize_frame(decoded, width, height)
                            if (width, height) != (decoded.width, decoded.height)
                            else decoded
                        )
                        if source_frame.format.name != "yuv420p":
                            source_frame = source_frame.reformat(format="yuv420p")
                        for out_packet in vstream_out.encode(source_frame):
                            out.mux(out_packet)
                        done += 1
                        percent = clamp_percent(done * 100 / total) if total else 0
                        if percent != last_percent:
                            last_percent = percent
                            progress(percent)
                elif astream_out is not None and not audio_broken:
                    try:
                        if resampler is not None:
                            for decoded_audio in packet.decode():
                                if not isinstance(decoded_audio, av.AudioFrame):
                                    continue
                                for converted in resampler.resample(decoded_audio):
                                    for out_packet in astream_out.encode(converted):
                                        out.mux(out_packet)
                        else:
                            # 音频直接复用源编码，只需换流引用
                            packet.stream = astream_out
                            out.mux(packet)
                    except Exception as exc:  # 音频出问题不该让整个任务失败
                        audio_broken = True
                        notes.append(f"音频处理失败已跳过（{type(exc).__name__}: {exc}）")

            for out_packet in vstream_out.encode():
                out.mux(out_packet)
            if resampler is not None and astream_out is not None and not audio_broken:
                for converted in resampler.resample(None):  # 冲干净重采样器里的残留
                    for out_packet in astream_out.encode(converted):
                        out.mux(out_packet)
                for out_packet in astream_out.encode():
                    out.mux(out_packet)

    if done == 0:
        raise ProcessingError(f"{src.name} 没有解码出任何视频帧")
    kept_audio = (audio_copy or audio_reencode) and not audio_broken
    if audio_reencode:
        notes.append("音频已降码率重编码为 AAC")
    return done, kept_audio
