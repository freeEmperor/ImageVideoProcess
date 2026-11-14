"""功能 1：图片 / 视频压缩（按目标体积）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QLabel,
    QWidget,
)

from imagevideoprocess.core.errors import InvalidParameterError
from imagevideoprocess.gui.features import register_feature
from imagevideoprocess.gui.widgets.inputs import ChevronComboBox, no_buttons
from imagevideoprocess.gui.widgets.panel import FeaturePanel
from imagevideoprocess.media.media_info import format_bytes
from imagevideoprocess.operations import compress as core_compress

#: 期望大小的可选单位
_UNITS: tuple[tuple[str, str], ...] = (("KB", "kb"), ("MB", "mb"), ("GB", "gb"))

#: 数值上限（需求规定 0~1024）
_VALUE_MAX = 1024.0

#: 默认期望大小（KB）
_DEFAULT_VALUE = 500.0


@register_feature(
    key="compress",
    title="图片视频压缩",
    subtitle="按目标体积压缩",
    description="指定期望体积，把图片或视频压到该大小以内（如把 10 MB 的照片压到 500 KB）",
    icon="fa5s.compress",
    order=10,
)
class CompressPanel(FeaturePanel):
    """压缩工作台。"""

    action_text = "开始压缩"

    # ------------------------------------------------------------- 参数区
    def build_parameters(self) -> QWidget:
        """期望大小输入 + 单位 + 实时比例提示。"""
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        label = QLabel("期望大小")
        label.setObjectName("fieldLabel")

        self.value_input = QDoubleSpinBox()
        self.value_input.setDecimals(2)
        self.value_input.setRange(0.0, _VALUE_MAX)
        self.value_input.setSingleStep(10.0)
        self.value_input.setValue(_DEFAULT_VALUE)
        self.value_input.setFixedWidth(130)
        no_buttons(self.value_input)
        self.value_input.valueChanged.connect(self._on_parameters_changed)

        self.unit_input = ChevronComboBox()
        for text, data in _UNITS:
            self.unit_input.addItem(text, data)
        self.unit_input.setFixedWidth(72)
        self.unit_input.currentIndexChanged.connect(self._on_parameters_changed)

        # 需求：输入区右侧显示「（压缩至 xx.x%）」
        self.ratio_label = QLabel("（压缩至 --%）")
        self.ratio_label.setObjectName("ratio")

        limit_hint = QLabel(f"数值范围 0 ~ {_VALUE_MAX:.0f}")
        limit_hint.setObjectName("hint")

        grid.addWidget(label, 0, 0)
        grid.addWidget(self.value_input, 0, 1)
        grid.addWidget(self.unit_input, 0, 2)
        grid.addWidget(self.ratio_label, 0, 3)
        grid.addWidget(limit_hint, 1, 1)
        grid.setColumnStretch(4, 1)

        # 需求：输入区下方固定提示语
        disclaimer = QLabel("实际压缩效果与期望大小有偏差请仔细甄别")
        disclaimer.setObjectName("hint")
        grid.addWidget(disclaimer, 2, 0, 1, 5)
        return card

    # -------------------------------------------------------- 输入 → 字节数
    @property
    def target_bytes(self) -> int:
        """当前输入换算出的目标字节数。"""
        return core_compress.target_bytes_of(
            self.value_input.value(), str(self.unit_input.currentData())
        )

    # -------------------------------------------------------------- 校验
    def validation_error(self) -> str | None:
        """输入必须落在 0~1024，且小于原文件大小。"""
        base = super().validation_error()
        if base:
            return base
        assert self.info is not None  # base 已保证
        value = self.value_input.value()
        if value <= 0:
            return "期望大小必须大于 0"
        if value > _VALUE_MAX:
            return f"期望大小不能超过 {_VALUE_MAX:.0f}"
        if self.target_bytes >= self.info.size_bytes:
            return f"期望大小必须小于原文件大小（{self.info.size_text}）"
        return None

    def validation_only(self) -> str | None:
        """只校验参数本身（忽略是否已载入文件），供提示语使用。"""
        value = self.value_input.value()
        if value <= 0:
            return "期望大小必须大于 0"
        if value > _VALUE_MAX:
            return f"期望大小不能超过 {_VALUE_MAX:.0f}"
        return None

    # -------------------------------------------------------------- 任务
    def build_task(self):  # type: ignore[override]
        """组装后台任务：按目标字节数压缩当前文件。"""
        source = self.source
        target = self.target_bytes
        if source is None:
            return None

        def run(progress, cancel):
            return core_compress.compress(source, target, cancel=cancel, progress=progress)

        return run

    # -------------------------------------------------------------- 联动
    def _on_parameters_changed(self) -> None:
        self.mark_dirty()  # 用户改过参数 → 切换功能时要弹确认框
        self._refresh_ratio()
        self.refresh_validation()

    def on_source_changed(self) -> None:
        """换了文件就自动给一个合理的默认期望大小，并重新算比例。"""
        info = self.info
        if info is not None:
            self.value_input.setToolTip(f"原文件 {format_bytes(info.size_bytes)}，期望值需小于它")
            # 程序预填默认值不算「用户修改」
            with self.mute_dirty():
                self._apply_suggested_target(info.size_bytes)
        self._refresh_ratio()

    def _apply_suggested_target(self, size_bytes: int) -> None:
        """默认填「原体积的一半」，并自动挑一个读起来顺眼的单位（不超过 1024）。"""
        half = max(1, size_bytes) / 2
        if half >= 1024**3:
            unit = "gb"
        elif half >= 1024**2:
            unit = "mb"
        else:
            unit = "kb"
        factor = {"kb": 1024, "mb": 1024**2, "gb": 1024**3}[unit]
        value = min(_VALUE_MAX, max(0.01, round(half / factor, 2)))
        index = next(i for i, (_, data) in enumerate(_UNITS) if data == unit)
        self.value_input.blockSignals(True)
        self.unit_input.blockSignals(True)
        self.unit_input.setCurrentIndex(index)
        self.value_input.setValue(value)
        self.unit_input.blockSignals(False)
        self.value_input.blockSignals(False)

    def _refresh_ratio(self) -> None:
        """刷新「（压缩至 xx.x%）」。"""
        self.ratio_label.setText(self.ratio_text())

    def reset_parameters(self) -> None:
        """恢复默认：500 KB。"""
        self.value_input.setValue(_DEFAULT_VALUE)
        self.unit_input.setCurrentIndex(0)
        self.value_input.setToolTip("")
        self._refresh_ratio()

    def ratio_text(self) -> str:
        """算出比例提示文本（无法计算时给 ``--``）。"""
        info = self.info
        if info is None or self.validation_only() is not None:
            return "（压缩至 --%）"
        try:
            target = self.target_bytes
        except InvalidParameterError:
            return "（压缩至 --%）"
        if target <= 0:
            return "（压缩至 --%）"
        percent = target / info.size_bytes * 100
        return f"（压缩至 {percent:.1f}%）"
