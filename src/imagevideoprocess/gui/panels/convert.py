"""功能 4：图片 / 视频格式转换（只换格式，不做体积压缩）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QWidget,
)

from imagevideoprocess.core.errors import InvalidParameterError, ProcessingError
from imagevideoprocess.gui.features import register_feature
from imagevideoprocess.gui.widgets.inputs import ChevronComboBox
from imagevideoprocess.gui.widgets.panel import FeaturePanel
from imagevideoprocess.media.media_info import MediaInfo
from imagevideoprocess.operations import convert as core_convert


@register_feature(
    key="convert",
    title="图片视频格式转换",
    subtitle="转成别的格式",
    description="把图片或视频转成其它格式；只换格式不压缩体积，"
    "视频在兼容时走无损转封装（不重新编码）",
    icon="fa5s.exchange-alt",
    order=40,
)
class ConvertPanel(FeaturePanel):
    """格式转换工作台。"""

    action_text = "开始转换"

    # ------------------------------------------------------------- 参数区
    def build_parameters(self) -> QWidget:
        """目标格式下拉框（会排除源文件原本的格式）。"""
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        label = QLabel("目标格式")
        label.setObjectName("fieldLabel")
        self.format_input = ChevronComboBox()
        self.format_input.setFixedWidth(180)
        self.format_input.currentIndexChanged.connect(self._on_parameters_changed)

        self.plan_label = QLabel("载入文件后选择要转成的格式")
        self.plan_label.setObjectName("hint")
        self.plan_label.setWordWrap(True)

        note = QLabel("转换过程不做体积压缩；输出文件名为「原文件名.新扩展名」")
        note.setObjectName("hint")
        note.setWordWrap(True)

        grid.addWidget(label, 0, 0)
        grid.addWidget(self.format_input, 0, 1)
        grid.addWidget(self.plan_label, 1, 0, 1, 4)
        grid.addWidget(note, 2, 0, 1, 4)
        grid.setColumnStretch(4, 1)
        return card

    # -------------------------------------------------------------- 取值
    @property
    def target_key(self) -> str | None:
        """当前选中的目标格式 key。"""
        data = self.format_input.currentData()
        return str(data) if data else None

    def current_target(self) -> core_convert.TargetFormat | None:
        """当前选中的目标格式对象。"""
        info = self.info
        key = self.target_key
        if info is None or key is None:
            return None
        try:
            return core_convert.target_by_key(key, info.kind)
        except ProcessingError:
            return None

    # -------------------------------------------------------------- 校验
    def validation_error(self) -> str | None:
        """必须有文件、且选中了一个不同于原格式的目标格式。"""
        base = super().validation_error()
        if base:
            return base
        target = self.current_target()
        if target is None:
            return "请选择要转换成的格式"
        return None

    # -------------------------------------------------------------- 任务
    def build_task(self):  # type: ignore[override]
        """组装后台任务：按目标格式转换。"""
        source = self.source
        target = self.current_target()
        if source is None or target is None:
            return None

        def run(progress, cancel):
            return core_convert.convert(source, target, cancel=cancel, progress=progress)

        return run

    # -------------------------------------------------------------- 联动
    def _on_parameters_changed(self) -> None:
        self.mark_dirty()  # 用户改过参数 → 切换功能时要弹确认框
        self._refresh_plan()
        self.refresh_validation()

    def on_source_changed(self) -> None:
        """载入文件后重建格式列表（**排除原格式**）并预选第一个。"""
        info = self.info
        if info is None:
            return
        with self.mute_dirty():  # 重建下拉列表不是用户改的
            self._rebuild_formats(info)
        self._refresh_plan()

    def reset_parameters(self) -> None:
        """清空工作台时把格式列表也清掉。"""
        self.format_input.blockSignals(True)
        self.format_input.clear()
        self.format_input.blockSignals(False)
        self.plan_label.setText("载入文件后选择要转成的格式")
        self.set_hint("")

    def _rebuild_formats(self, info: MediaInfo) -> None:
        """按文件类型与原本格式重建下拉列表。"""
        targets = core_convert.targets_for(info)
        current = core_convert.source_format_key(info)

        self.format_input.blockSignals(True)
        self.format_input.clear()
        for target in targets:
            self.format_input.addItem(f"{target.label}　{target.description}", target.key)
        self.format_input.blockSignals(False)

        if not targets:
            self.plan_label.setText(f"没有可转换的目标格式（源格式：{current.upper()}）")
            return
        self.format_input.setCurrentIndex(0)
        self.plan_label.setText(
            f"源格式 {info.format}；可选 {len(targets)} 种目标格式（已排除原格式）"
        )

    def _refresh_plan(self) -> None:
        """刷新"这次转换会怎么走"的说明。"""
        info = self.info
        target = self.current_target()
        if info is None or target is None:
            return
        try:
            self.set_hint(core_convert.describe_plan(info, target))
        except (InvalidParameterError, ProcessingError):
            self.set_hint("")
