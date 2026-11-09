"""功能 2：图片 / 视频缩放（缩放到指定分辨率）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from imagevideoprocess.core import resize as core_resize
from imagevideoprocess.core.errors import InvalidParameterError
from imagevideoprocess.gui.features import register_feature
from imagevideoprocess.gui.widgets.inputs import no_buttons
from imagevideoprocess.gui.widgets.panel import FeaturePanel

#: 分辨率输入上限
_SIZE_MAX = 65535

#: 默认目标分辨率
_DEFAULT_WIDTH = 1280
_DEFAULT_HEIGHT = 720


@register_feature(
    key="resize",
    title="图片 / 视频缩放",
    subtitle="缩放到指定分辨率",
    description="缩放到指定分辨率；目标宽、高都必须小于原分辨率（只做缩小）",
    icon="fa5s.expand-arrows-alt",
    order=20,
)
class ResizePanel(FeaturePanel):
    """缩放工作台。"""

    action_text = "开始缩放"

    # ------------------------------------------------------------- 参数区
    def build_parameters(self) -> QWidget:
        """宽 / 高输入。"""
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        width_label = QLabel("目标宽度")
        width_label.setObjectName("fieldLabel")
        self.width_input = QSpinBox()
        self.width_input.setRange(1, _SIZE_MAX)
        self.width_input.setValue(_DEFAULT_WIDTH)
        self.width_input.setFixedWidth(130)
        self.width_input.setSuffix(" px")
        no_buttons(self.width_input)
        self.width_input.valueChanged.connect(self._on_parameters_changed)

        height_label = QLabel("目标高度")
        height_label.setObjectName("fieldLabel")
        self.height_input = QSpinBox()
        self.height_input.setRange(1, _SIZE_MAX)
        self.height_input.setValue(_DEFAULT_HEIGHT)
        self.height_input.setFixedWidth(130)
        self.height_input.setSuffix(" px")
        no_buttons(self.height_input)
        self.height_input.valueChanged.connect(self._on_parameters_changed)

        self.origin_label = QLabel("载入文件后显示原分辨率")
        self.origin_label.setObjectName("hint")

        grid.addWidget(width_label, 0, 0)
        grid.addWidget(self.width_input, 0, 1)
        grid.addWidget(height_label, 0, 2)
        grid.addWidget(self.height_input, 0, 3)
        grid.addWidget(self.origin_label, 1, 0, 1, 5)
        grid.setColumnStretch(4, 1)
        return card

    # -------------------------------------------------------------- 校验
    def validation_error(self) -> str | None:
        """宽高必须是正整数，且都小于原分辨率。"""
        base = super().validation_error()
        if base:
            return base
        assert self.info is not None  # base 已保证
        try:
            core_resize.validate_size(
                self.info.width, self.info.height, self.target_size[0], self.target_size[1]
            )
        except InvalidParameterError as exc:
            return str(exc)
        return None

    @property
    def target_size(self) -> tuple[int, int]:
        """当前输入的目标分辨率。"""
        return (self.width_input.value(), self.height_input.value())

    # -------------------------------------------------------------- 任务
    def build_task(self):  # type: ignore[override]
        """组装后台任务：缩放到目标分辨率。"""
        source = self.source
        width, height = self.target_size
        if source is None:
            return None

        def run(progress, cancel):
            return core_resize.resize(source, width, height, cancel=cancel, progress=progress)

        return run

    # -------------------------------------------------------------- 联动
    def _on_parameters_changed(self) -> None:
        self.mark_dirty()  # 用户改过参数 → 切换功能时要弹确认框
        self._refresh_preview()
        self.refresh_validation()

    def on_source_changed(self) -> None:
        """载入新文件后把输入框预填成原分辨率的一半，并提示原尺寸。"""
        info = self.info
        if info is None:
            return
        self.origin_label.setText(
            f"原分辨率 {info.resolution_text}，目标宽高都必须小于它（例如 "
            f"{max(1, info.width // 2)} × {max(1, info.height // 2)}）"
        )
        # 程序预填默认值不算「用户修改」
        with self.mute_dirty():
            self.width_input.blockSignals(True)
            self.height_input.blockSignals(True)
            self.width_input.setValue(max(1, info.width // 2))
            self.height_input.setValue(max(1, info.height // 2))
            self.width_input.blockSignals(False)
            self.height_input.blockSignals(False)
        self._refresh_preview()

    def reset_parameters(self) -> None:
        """恢复默认宽高。"""
        self.width_input.setValue(_DEFAULT_WIDTH)
        self.height_input.setValue(_DEFAULT_HEIGHT)
        self.origin_label.setText("载入文件后显示原分辨率")
        self.set_hint("")

    def _refresh_preview(self) -> None:
        """显示目标尺寸与缩放比例。"""
        info = self.info
        if info is None:
            return
        width, height = self.target_size
        if width >= info.width or height >= info.height:
            self.set_hint("")
            return
        ratio = width / info.width * 100
        even_note = ""
        if width % 2 or height % 2:
            even_note = "（视频输出时宽高会向下取偶）"
        self.set_hint(f"{info.resolution_text} → {width} × {height}，约 {ratio:.1f}%{even_note}")
