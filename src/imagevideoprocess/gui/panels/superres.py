"""功能 6：图片超分辨率（插值 / 增强方法放大 2x / 3x / 4x）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QWidget,
)

from imagevideoprocess.core.errors import InvalidParameterError
from imagevideoprocess.gui.features import register_feature
from imagevideoprocess.gui.widgets.inputs import ChevronComboBox
from imagevideoprocess.gui.widgets.panel import FeaturePanel
from imagevideoprocess.operations import superres


@register_feature(
    key="superres",
    title="图片超分辨率",
    subtitle="插值放大 2~4 倍",
    description="用经典插值 / 增强方法把图片放大 2x / 3x / 4x"
    "（不含 AI 模型推理）；输出命名为「原文件名_方法_倍率」",
    icon="fa5s.search-plus",
    accepted_kinds=("image",),
    order=60,
)
class SuperResPanel(FeaturePanel):
    """超分工作台（只接受图片）。"""

    action_text = "开始超分"

    # ------------------------------------------------------------- 参数区
    def build_parameters(self) -> QWidget:
        """超分方法 + 倍率。"""
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        method_label = QLabel("超分方法")
        method_label.setObjectName("fieldLabel")
        self.method_input = ChevronComboBox()
        self.method_input.setMinimumWidth(360)
        for method in superres.METHODS:
            # 下拉项里直接带上方法特点（需求要求"可简述不同方法的特点"）
            self.method_input.addItem(f"{method.label}　—　{method.description}", method.key)
        default_index = self.method_input.findData(superres.DEFAULT_METHOD)
        if default_index >= 0:
            self.method_input.setCurrentIndex(default_index)
        self.method_input.currentIndexChanged.connect(self._on_parameters_changed)

        scale_label = QLabel("超分倍率")
        scale_label.setObjectName("fieldLabel")
        self.scale_input = ChevronComboBox()
        self.scale_input.setFixedWidth(120)
        for scale in superres.SCALE_FACTORS:
            self.scale_input.addItem(f"{scale}x", scale)
        default_scale = self.scale_input.findData(superres.DEFAULT_SCALE)
        if default_scale >= 0:
            self.scale_input.setCurrentIndex(default_scale)
        self.scale_input.currentIndexChanged.connect(self._on_parameters_changed)

        self.method_note = QLabel("")
        self.method_note.setObjectName("hint")
        self.method_note.setWordWrap(True)

        note = QLabel("输出文件名为「原文件名_方法_倍率.扩展名」，例如 photo_lanczos_2x.png")
        note.setObjectName("hint")
        note.setWordWrap(True)

        grid.addWidget(method_label, 0, 0)
        grid.addWidget(self.method_input, 0, 1, 1, 4)
        grid.addWidget(scale_label, 1, 0)
        grid.addWidget(self.scale_input, 1, 1)
        grid.addWidget(self.method_note, 2, 0, 1, 6)
        grid.addWidget(note, 3, 0, 1, 6)
        grid.setColumnStretch(6, 1)
        return card

    # -------------------------------------------------------------- 取值
    @property
    def method_key(self) -> str:
        """当前选中的超分方法 key。"""
        return str(self.method_input.currentData())

    def current_method(self) -> superres.SuperResMethod | None:
        """当前选中的方法对象。"""
        try:
            return superres.method_by_key(self.method_key)
        except InvalidParameterError:
            return None

    @property
    def scale(self) -> int:
        """当前选中的倍率。"""
        return int(self.scale_input.currentData())

    # -------------------------------------------------------------- 校验
    def validation_error(self) -> str | None:
        """必须有图片，且输出分辨率不能超过上限。"""
        base = super().validation_error()
        if base:
            return base
        assert self.info is not None  # base 已保证
        if self.current_method() is None:
            return "请选择超分方法"
        try:
            superres.validate_request(self.info, self.scale)
        except InvalidParameterError as exc:
            return str(exc)
        return None

    # -------------------------------------------------------------- 任务
    def build_task(self):  # type: ignore[override]
        """组装后台任务：按方法 + 倍率放大。"""
        source = self.source
        info = self.info
        method = self.current_method()
        if source is None or info is None or method is None:
            return None
        scale = self.scale

        def run(progress, cancel):
            return superres.supersample(source, method, scale, cancel=cancel, progress=progress)

        return run

    # -------------------------------------------------------------- 联动
    def _on_parameters_changed(self) -> None:
        self.mark_dirty()  # 用户改过参数 → 切换功能时要弹确认框
        self._refresh_preview()
        self.refresh_validation()

    def on_source_changed(self) -> None:
        """载入图片后就刷新预览（方法 / 倍率都是默认值，不需要预填）。"""
        self._refresh_preview()

    def reset_parameters(self) -> None:
        """恢复默认方法与倍率。"""
        method_index = self.method_input.findData(superres.DEFAULT_METHOD)
        if method_index >= 0:
            self.method_input.setCurrentIndex(method_index)
        scale_index = self.scale_input.findData(superres.DEFAULT_SCALE)
        if scale_index >= 0:
            self.scale_input.setCurrentIndex(scale_index)
        self.method_note.setText("")
        self.set_hint("")

    def _refresh_preview(self) -> None:
        """刷新"将放大到多少"的说明。"""
        info = self.info
        method = self.current_method()
        if info is None or method is None:
            return
        self.method_note.setText(f"{method.label}：{method.description}")
        try:
            self.set_hint(superres.describe_plan(info, method, self.scale))
        except InvalidParameterError:
            self.set_hint("")
