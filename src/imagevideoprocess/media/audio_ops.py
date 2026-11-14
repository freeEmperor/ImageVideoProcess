"""音频相关操作：音频格式表 + 从视频里提取音频。

本模块同时给「视频音频提取」功能与视频转码引擎（webm 需要 opus 音轨）提供
「目标编码 → 采样格式 / 采样率 / 帧长」的对应关系，避免这些细节散落各处。

实现要点：

- 源音频编码与目标一致时**直接复用**（不重新编码，最快且无损）；
- 否则解码 → 重采样成编码器要的采样格式 → 重新编码；
- **Opus 只能是 48 kHz，且必须固定帧长**（20ms = 960 采样），
  所以它要额外设采样率与 :class:`av.AudioResampler` 的 ``frame_size``；
- 先写 ``.part`` 再原子替换。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import av
from av.audio.stream import AudioStream

from imagevideoprocess.core.errors import ProcessingError, UnsupportedFormatError
from imagevideoprocess.core.progress import CancelToken, ProgressFn, clamp_percent, noop_progress
from imagevideoprocess.core.result import ProcessResult
from imagevideoprocess.media.media_info import probe
from imagevideoprocess.runtime.paths import processed_dir, unique_path


@dataclass(frozen=True)
class AudioTarget:
    """一种可输出的音频格式。"""

    key: str
    #: 文件扩展名（含点）
    suffix: str
    #: 界面上显示的名字
    label: str
    #: FFmpeg 编码器名
    codec: str
    #: 输出容器名
    container: str
    #: 编码器要求的采样格式
    sample_format: str
    #: 目标码率（bit/s）；None 表示无损
    bitrate: int | None = None
    #: 强制采样率（Opus 必须 48000）
    forced_sample_rate: int | None = None
    #: 强制帧长（采样点数）；Opus 需要固定 20ms
    frame_size: int | None = None
    #: 一句话说明，显示在界面上
    description: str = ""

    @property
    def is_lossless(self) -> bool:
        """是否无损格式。"""
        return self.bitrate is None


#: 支持输出的音频格式（按界面顺序）
AUDIO_TARGETS: tuple[AudioTarget, ...] = (
    AudioTarget(
        key="mp3",
        suffix=".mp3",
        label="MP3",
        codec="libmp3lame",
        container="mp3",
        sample_format="s16p",
        bitrate=192_000,
        description="兼容性最好",
    ),
    AudioTarget(
        key="m4a",
        suffix=".m4a",
        label="M4A（AAC）",
        codec="aac",
        container="mp4",
        sample_format="fltp",
        bitrate=192_000,
        description="苹果设备通用",
    ),
    AudioTarget(
        key="wav",
        suffix=".wav",
        label="WAV（无损 PCM）",
        codec="pcm_s16le",
        container="wav",
        sample_format="s16",
        description="无损、体积大",
    ),
    AudioTarget(
        key="flac",
        suffix=".flac",
        label="FLAC（无损压缩）",
        codec="flac",
        container="flac",
        sample_format="s16",
        description="无损、体积小",
    ),
    AudioTarget(
        key="ogg",
        suffix=".ogg",
        label="OGG（Opus）",
        codec="libopus",
        container="ogg",
        sample_format="s16",
        bitrate=128_000,
        forced_sample_rate=48000,
        frame_size=960,
        description="体积小、质量好",
    ),
)

#: 音频编码名 → 编码器要的采样格式（供 video_ops 复用）
_SAMPLE_FORMAT_BY_CODEC: dict[str, str] = {
    "aac": "fltp",
    "libmp3lame": "s16p",
    "mp3": "s16p",
    "flac": "s16",
    "pcm_s16le": "s16",
    "libopus": "s16",
    "opus": "s16",
}

#: 重新编码音频时的默认码率
_DEFAULT_BITRATE_BY_CODEC: dict[str, int] = {
    "aac": 192_000,
    "libmp3lame": 192_000,
    "libopus": 128_000,
    "opus": 128_000,
}


#: 编码器名 → 编码名（容器兼容性判断用的是编码名，例如 avi 表里写的是 ``mp3`` 而不是 ``libmp3lame``）
_ENCODER_ALIASES: dict[str, str] = {
    "libmp3lame": "mp3",
    "libopus": "opus",
    "libvorbis": "vorbis",
    "libfdk_aac": "aac",
    "libtwolame": "mp2",
}


def normalize_codec(name: str | None) -> str:
    """把编码器名归一成编码名（``libmp3lame`` → ``mp3``）。"""
    if not name:
        return ""
    lowered = name.lower()
    return _ENCODER_ALIASES.get(lowered, lowered)


def encoder_sample_format(codec: str) -> str:
    """该编码器要求的采样格式（不认识就退化成 s16）。"""
    return _SAMPLE_FORMAT_BY_CODEC.get(codec.lower(), "s16")


def encoder_bitrate(codec: str, requested: int | None = None) -> int | None:
    """该编码器重新编码时的码率；无损编码返回 None。"""
    if codec.lower() in {"flac", "pcm_s16le", "pcm_s24le"}:
        return None
    return requested or _DEFAULT_BITRATE_BY_CODEC.get(codec.lower(), 192_000)


def encoder_sample_rate(codec: str, source_rate: int | None, forced: int | None = None) -> int:
    """该编码器要用的采样率（Opus 强制 48 kHz）。"""
    if forced:
        return forced
    if codec.lower() in {"libopus", "opus"}:
        return 48_000
    return int(source_rate or 44_100)


def encoder_frame_size(codec: str, forced: int | None = None) -> int | None:
    """该编码器需要的固定帧长（Opus 为 960 = 20ms@48kHz），其它返回 None。"""
    if forced:
        return forced
    if codec.lower() in {"libopus", "opus"}:
        return 960
    return None


def target_by_key(key: str) -> AudioTarget:
    """按 key 找音频格式。

    Raises:
        UnsupportedFormatError: 没有这种格式。
    """
    for target in AUDIO_TARGETS:
        if target.key == key:
            return target
    raise UnsupportedFormatError(f"不支持的音频格式：{key}")


def available_targets() -> list[AudioTarget]:
    """本机真的能编码的音频格式（缺编码器的不出现在界面上）。"""
    available = av.codecs_available
    return [target for target in AUDIO_TARGETS if target.codec in available]


def _audio_source_info(source: Path) -> tuple[float | None, str, int | None, str, int | None]:
    """读出源音频的时长 / 编码 / 采样率 / 声道布局 / 总采样数（用于进度）。"""
    with av.open(str(source)) as container:
        if not container.streams.audio:
            raise ProcessingError(f"{source.name} 里没有音频轨道")
        stream = container.streams.audio[0]
        ctx = stream.codec_context
        duration: float | None = None
        if container.duration:
            duration = container.duration / av.time_base
        elif stream.duration and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        total_samples = int(stream.frames or 0) or None
        if total_samples is None and duration:
            total_samples = int(duration * int(ctx.sample_rate or 44_100))
        return (
            duration,
            ctx.name or "",
            int(ctx.sample_rate or 0) or None,
            ctx.layout.name if ctx.layout else "stereo",
            total_samples,
        )


def extract_audio(
    source: str | Path,
    target: AudioTarget | str,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """把视频里的音频提取成独立的音频文件，输出命名 ``原名.扩展名``。

    Args:
        source: 待处理视频。
        target: 目标音频格式（:class:`AudioTarget` 或它的 key）。
        out_dir: 输出目录，默认 ``processed``。
        cancel: 取消令牌。
        progress: 进度回调（0~100）。

    Raises:
        ProcessingError: 视频没有音轨，或解码/编码失败。
        UnsupportedFormatError: 目标格式不支持。
    """
    token = cancel or CancelToken()
    src = Path(source)
    spec = target_by_key(target) if isinstance(target, str) else target

    info = probe(src)
    if info.kind != "video":
        raise ProcessingError("音频提取只支持视频文件")
    if not info.audio_codec:
        raise ProcessingError("该视频没有音频轨道，无法提取")

    _duration, source_codec, sample_rate, layout, total_samples = _audio_source_info(src)
    if spec.codec not in av.codecs_available:
        raise UnsupportedFormatError(f"本机没有 {spec.label} 的编码器")

    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / f"{src.stem}{spec.suffix}")
    temp = dest.with_name(dest.name + ".part")
    temp.unlink(missing_ok=True)

    # 源编码与目标一致 → 直接复用（最省时，且完全无损）
    copy_stream = source_codec.lower() == spec.codec.lower()

    notes: list[str] = []
    try:
        with av.open(str(src)) as container:
            astream_in = container.streams.audio[0]
            with av.open(str(temp), mode="w", format=spec.container) as out:
                if copy_stream:
                    astream_out = out.add_stream_from_template(astream_in)
                    _copy_audio(
                        container, astream_in, astream_out, out, token, progress, total_samples
                    )
                else:
                    _encode_audio(
                        container,
                        astream_in,
                        out,
                        spec,
                        sample_rate,
                        layout,
                        token,
                        progress,
                        total_samples,
                    )
        temp.replace(dest)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise

    progress(100)
    if copy_stream:
        notes.append(f"原音频已是 {spec.label.split('（')[0]}，直接复用未重新编码")
    output_bytes = dest.stat().st_size
    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=output_bytes,
        verb="提取音频",
        note="；".join(notes),
    )


def _copy_audio(
    container: av.container.InputContainer,
    astream_in: AudioStream,
    astream_out: AudioStream,
    out: av.container.OutputContainer,
    token: CancelToken,
    progress: ProgressFn,
    total_packets: int | None,
) -> None:
    """不重新编码，直接把音频包搬到新容器里。"""
    done = 0
    last = -1
    for packet in container.demux(astream_in):
        token.raise_if_cancelled()
        if packet.dts is None:
            continue
        packet.stream = astream_out
        out.mux(packet)
        done += 1
        percent = clamp_percent(done * 100 / total_packets) if total_packets else 0
        if percent != last:
            last = percent
            progress(percent)


def _encode_audio(
    container: av.container.InputContainer,
    astream_in: AudioStream,
    out: av.container.OutputContainer,
    spec: AudioTarget,
    source_rate: int | None,
    source_layout: str,
    token: CancelToken,
    progress: ProgressFn,
    total_samples: int | None,
) -> None:
    """解码 → 重采样 → 按目标格式重新编码。"""
    rate = encoder_sample_rate(spec.codec, source_rate, spec.forced_sample_rate)
    layout = pick_layout(source_layout, spec.codec)
    sample_format = spec.sample_format
    bitrate = encoder_bitrate(spec.codec, spec.bitrate)

    stream_out = cast(AudioStream, out.add_stream(spec.codec, rate=rate))
    stream_out.layout = layout
    stream_out.format = sample_format
    if bitrate:
        stream_out.bit_rate = int(bitrate)

    resampler = av.AudioResampler(
        format=sample_format,
        layout=layout,
        rate=rate,
        frame_size=spec.frame_size,
    )

    done = 0
    last = -1
    for frame in container.decode(astream_in):
        token.raise_if_cancelled()
        for converted in resampler.resample(frame):
            for packet in stream_out.encode(converted):
                out.mux(packet)
            done += converted.samples
            percent = clamp_percent(done * 100 / total_samples) if total_samples else 0
            if percent != last:
                last = percent
                progress(percent)

    for converted in resampler.resample(None):  # 冲干净重采样器里的残留
        for packet in stream_out.encode(converted):
            out.mux(packet)
    for packet in stream_out.encode():
        out.mux(packet)


def pick_layout(source_layout: str, codec: str) -> str:
    """声道布局：目标编码器不支持多声道时降到立体声。"""
    if codec.lower() in {"libmp3lame", "mp3", "libopus", "opus"} and source_layout not in {
        "mono",
        "stereo",
    }:
        return "stereo"
    return source_layout
