"""一次处理任务的结果摘要（core 层返回值，GUI 层据此提示用户）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from imagevideoprocess.core.media_info import format_bytes


@dataclass
class ProcessResult:
    """处理结果。

    Attributes:
        outputs: 写出的文件列表（抽帧会有很多个）。
        source_path: 源文件。
        source_bytes: 源文件字节数。
        output_bytes: 全部输出文件的字节数之和。
        verb: 动作名，用于拼提示语，如「压缩」。
        note: 附加说明（例如音频被丢弃、未能完全达到目标体积）。
    """

    outputs: list[Path] = field(default_factory=list)
    source_path: Path | None = None
    source_bytes: int = 0
    output_bytes: int = 0
    verb: str = "处理"
    note: str = ""

    @property
    def ratio(self) -> float:
        """输出体积 / 源体积（0~∞）。源体积为 0 时返回 0。"""
        if self.source_bytes <= 0:
            return 0.0
        return self.output_bytes / self.source_bytes

    @property
    def summary(self) -> str:
        """一行中文摘要，用于自动消散的提示条。"""
        if self.source_bytes and self.output_bytes:
            text = (
                f"{self.verb}完成：{format_bytes(self.source_bytes)}"
                f" → {format_bytes(self.output_bytes)}（{self.ratio * 100:.1f}%）"
            )
        else:
            text = f"{self.verb}完成"
        if self.outputs:
            text += f"，输出 {len(self.outputs)} 个文件"
        if self.note:
            text += f"；{self.note}"
        return text

    @property
    def first_output(self) -> Path | None:
        """第一个输出文件（没有则为 None）。"""
        return self.outputs[0] if self.outputs else None
