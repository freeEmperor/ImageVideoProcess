"""功能 5：视频音频提取（把视频里的声音单独存成音频文件）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QWidget,
)

from imagevideoprocess.core import audio_ops
from imagevideoprocess.core.errors import ProcessingError
from imagevideoprocess.core.media_info import codec_display
from imagevideoprocess.gui.features import register_feature
from imagevideoprocess.gui.widgets.inputs import ChevronComboBox
from imagevideoprocess.gui.widgets.panel import FeaturePanel


@register_feature(
    key="audio",
    title="视频音频提取",
    subtitle="把声音单独存出来",
    description="从视频里把音轨提取成独立的音频文件；源编码与目标一致时直接复用，不重新编码",
    icon="fa5s.music",
    accepted_kinds=("video",),
    order=50,
)
class AudioPanel(FeaturePanel):
    """音频提取工作台（只接受视频文件）。"""

    action_text = "提取音频"

    # ------------------------------------------------------------- 参数区
    def build_parameters(self) -> QWidget:
        """输出音频格式下拉框。"""
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        label = QLabel("音频格式")
        label.setObjectName("fieldLabel")
        self.format_input = ChevronComboBox()
        self.format_input.setFixedWidth(200)
        for target in audio_ops.available_targets():
            self.format_input.addItem(f"{target.label}　{target.description}", target.key)
        self.format_input.currentIndexChanged.connect(self._on_parameters_changed)

        self.source_label = QLabel("载入视频后显示它的音轨信息")
        self.source_label.setObjectName("hint")
        self.source_label.setWordWrap(True)

        note = QLabel("输出文件名为「原文件名.音频扩展名」，文件里只有声音")
        note.setObjectName("hint")
        note.setWordWrap(True)

        grid.addWidget(label, 0, 0)
        grid.addWidget(self.format_input, 0, 1)
        grid.addWidget(self.source_label, 1, 0, 1, 4)
        grid.addWidget(note, 2, 0, 1, 4)
        grid.setColumnStretch(4, 1)
        return card

    # -------------------------------------------------------------- 取值
    @property
    def target_key(self) -> str | None:
        """当前选中的音频格式 key。"""
        data = self.format_input.currentData()
        return str(data) if data else None

    def current_target(self) -> audio_ops.AudioTarget | None:
        """当前选中的音频格式对象。"""
        key = self.target_key
        if key is None:
            return None
        try:
            return audio_ops.target_by_key(key)
        except ProcessingError:
            return None

    # -------------------------------------------------------------- 校验
    def validation_error(self) -> str | None:
        """必须有视频，且视频里确实有音轨，还选好了目标格式。"""
        base = super().validation_error()
        if base:
            return base
        assert self.info is not None  # base 已保证
        if not self.info.audio_codec:
            return "该视频没有音频轨道，无法提取音频"
        if self.current_target() is None:
            return "请选择要输出的音频格式"
        return None

    # -------------------------------------------------------------- 任务
    def build_task(self):  # type: ignore[override]
        """组装后台任务：提取音频。"""
        source = self.source
        target = self.current_target()
        if source is None or target is None:
            return None

        def run(progress, cancel):
            return audio_ops.extract_audio(source, target, cancel=cancel, progress=progress)

        return run

    # -------------------------------------------------------------- 联动
    def _on_parameters_changed(self) -> None:
        self.mark_dirty()  # 用户改过参数 → 切换功能时要弹确认框
        self._refresh_preview()
        self.refresh_validation()

    def on_source_changed(self) -> None:
        """载入视频后提示它的音轨信息。"""
        self._refresh_preview()
        self.refresh_validation()

    def reset_parameters(self) -> None:
        """清空工作台。"""
        self.format_input.setCurrentIndex(0)
        self.source_label.setText("载入视频后显示它的音轨信息")
        self.set_hint("")

    def _refresh_preview(self) -> None:
        """刷新"源音轨 → 目标格式"的说明。"""
        info = self.info
        target = self.current_target()
        if info is None or target is None:
            return
        if not info.audio_codec:
            self.source_label.setText("该视频没有音频轨道")
            self.set_hint("")
            return

        source_codec = codec_display(info.audio_codec)
        self.source_label.setText(
            f"源音轨：{source_codec}，时长 {info.duration_text}；将输出为 {target.label}"
        )
        if info.audio_codec.lower() == target.codec.lower():
            self.set_hint(f"源音轨已经是 {source_codec}，会直接复用，不重新编码（无损）")
        elif target.is_lossless:
            self.set_hint(f"{source_codec} → {target.label}（无损保存）")
        else:
            self.set_hint(
                f"{source_codec} → {target.label}"
                f"（{target.bitrate // 1000 if target.bitrate else 0} kbps 重新编码）"
            )

    def set_source(self, path: Path) -> None:
        """载入文件（保留基类行为，仅补一个空音轨的提示）。"""
        super().set_source(path)
        info = self.info
        if info is not None and not info.audio_codec:
            self.notify.emit("该视频没有音频轨道，无法提取音频", "error")
