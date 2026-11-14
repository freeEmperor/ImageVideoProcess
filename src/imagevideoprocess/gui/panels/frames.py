"""功能 3：视频抽帧（按时间点 / 帧号 + 帧数 / 秒数跨度）。"""

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
from imagevideoprocess.operations import frames as core_frames

#: 单位下拉项：(显示名, 内部值)
_UNIT_ITEMS: tuple[tuple[str, str], ...] = (
    ("秒", core_frames.UNIT_SECONDS),
    ("帧", core_frames.UNIT_FRAMES),
)

#: 输出图片格式下拉项
_FORMAT_LABELS: dict[str, str] = {
    "png": "PNG（默认）",
    "jpg": "JPG",
    "webp": "WebP",
    "bmp": "BMP",
    "tiff": "TIFF",
}

#: 默认提取跨度：1 帧（从起始位置起只取一帧）
_DEFAULT_SPAN = 1.0

#: 默认起始位置
_DEFAULT_START = 0.0


@register_feature(
    key="frames",
    title="视频抽帧",
    subtitle="按帧号或时间抽帧",
    description="从指定时间点或帧号开始，按「帧数」或「秒数」跨度提取图片，"
    "输出命名 原名_000100.png（数字为该帧在原视频中的帧号）",
    icon="fa5s.film",
    accepted_kinds=("video",),
    order=30,
)
class FramesPanel(FeaturePanel):
    """抽帧工作台（只接受视频文件）。"""

    action_text = "提取帧"

    # ------------------------------------------------------------- 参数区
    def build_parameters(self) -> QWidget:
        """起始位置 + 单位、跨度 + 单位、输出图片格式。"""
        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # 起始位置
        start_label = QLabel("起始位置")
        start_label.setObjectName("fieldLabel")
        self.start_input = self._make_value_input(_DEFAULT_START)
        self.start_unit = self._make_unit_input()
        self.start_unit.currentIndexChanged.connect(self._on_unit_changed)

        # 跨度
        span_label = QLabel("提取跨度")
        span_label.setObjectName("fieldLabel")
        self.span_input = self._make_value_input(_DEFAULT_SPAN)
        self.span_unit = self._make_unit_input()
        self.span_unit.currentIndexChanged.connect(self._on_unit_changed)

        # 输出格式
        format_label = QLabel("图片格式")
        format_label.setObjectName("fieldLabel")
        self.format_input = ChevronComboBox()
        for name in core_frames.OUTPUT_FORMATS:
            self.format_input.addItem(_FORMAT_LABELS.get(name, name.upper()), name)
        self.format_input.setFixedWidth(130)
        self.format_input.currentIndexChanged.connect(self._on_parameters_changed)

        example = QLabel(
            "示例：（40秒，10帧）= 从第 40 秒起取 10 张；（40秒，1秒）= 取这 1 秒内的所有帧；"
            "（100帧，10帧）= 取第 100 ~ 109 帧"
        )
        example.setObjectName("hint")
        example.setWordWrap(True)

        grid.addWidget(start_label, 0, 0)
        grid.addWidget(self.start_input, 0, 1)
        grid.addWidget(self.start_unit, 0, 2)
        grid.addWidget(span_label, 0, 3)
        grid.addWidget(self.span_input, 0, 4)
        grid.addWidget(self.span_unit, 0, 5)
        grid.addWidget(format_label, 1, 0)
        grid.addWidget(self.format_input, 1, 1)
        grid.addWidget(example, 2, 0, 1, 6)
        grid.setColumnStretch(6, 1)

        # 默认按「帧」起步：从第 0 帧起取 1 帧
        # （用「秒」当默认单位的话，跨度会随帧率放大，短视频一载入就越界）
        self.start_unit.setCurrentIndex(1)
        self.span_unit.setCurrentIndex(1)
        self._on_unit_changed()
        return card

    def _make_value_input(self, value: float) -> QDoubleSpinBox:
        """数值输入框（帧为单位时不允许小数）。"""
        box = QDoubleSpinBox()
        box.setRange(0.0, 10_000_000.0)
        box.setDecimals(0)
        box.setValue(value)
        box.setFixedWidth(120)
        no_buttons(box)
        box.valueChanged.connect(self._on_parameters_changed)
        return box

    def _make_unit_input(self) -> ChevronComboBox:
        """单位下拉框。"""
        combo = ChevronComboBox()
        for text, data in _UNIT_ITEMS:
            combo.addItem(text, data)
        combo.setFixedWidth(70)
        return combo

    # -------------------------------------------------------------- 取值
    @property
    def start_value(self) -> float:
        """起始位置输入值。"""
        return self.start_input.value()

    @property
    def start_unit_value(self) -> str:
        """起始位置单位。"""
        return str(self.start_unit.currentData())

    @property
    def span_value(self) -> float:
        """跨度输入值。"""
        return self.span_input.value()

    @property
    def span_unit_value(self) -> str:
        """跨度单位。"""
        return str(self.span_unit.currentData())

    @property
    def image_format(self) -> str:
        """输出图片格式（扩展名）。"""
        return str(self.format_input.currentData())

    def resolved_range(self) -> core_frames.FrameRange | None:
        """把界面输入换算成帧区间；非法时返回 None。"""
        info = self.info
        if info is None:
            return None
        try:
            return core_frames.resolve_range(
                info, self.start_value, self.start_unit_value, self.span_value, self.span_unit_value
            )
        except InvalidParameterError:
            return None

    # -------------------------------------------------------------- 校验
    def validation_error(self) -> str | None:
        """帧区间必须落在视频范围内。"""
        base = super().validation_error()
        if base:
            return base
        assert self.info is not None  # base 已保证
        try:
            core_frames.resolve_range(
                self.info,
                self.start_value,
                self.start_unit_value,
                self.span_value,
                self.span_unit_value,
            )
        except InvalidParameterError as exc:
            return str(exc)
        return None

    # -------------------------------------------------------------- 任务
    def build_task(self):  # type: ignore[override]
        """组装后台任务：按帧区间抽帧。"""
        source = self.source
        info = self.info
        if source is None or info is None:
            return None
        try:
            frame_range = core_frames.resolve_range(
                info, self.start_value, self.start_unit_value, self.span_value, self.span_unit_value
            )
        except InvalidParameterError:
            return None
        image_format = self.image_format

        def run(progress, cancel):
            return core_frames.extract_frames(
                source,
                frame_range,
                image_format=image_format,
                cancel=cancel,
                progress=progress,
            )

        return run

    # -------------------------------------------------------------- 联动
    def _on_unit_changed(self) -> None:
        """按单位调整小数位：帧是整数，秒保留 2 位小数。"""
        for box, combo in ((self.start_input, self.start_unit), (self.span_input, self.span_unit)):
            is_seconds = combo.currentData() == core_frames.UNIT_SECONDS
            box.setDecimals(2 if is_seconds else 0)
            box.setSingleStep(1.0 if is_seconds else 10.0)
        if self.span_unit.currentData() == core_frames.UNIT_FRAMES and self.span_input.value() < 1:
            # 跨度为「帧」时至少要 1 帧，否则会把 0 传下去
            self.span_input.setValue(_DEFAULT_SPAN)
        self._on_parameters_changed()

    def _on_parameters_changed(self) -> None:
        self.mark_dirty()  # 用户改过参数 → 切换功能时要弹确认框
        self._refresh_preview()
        self.refresh_validation()

    def on_source_changed(self) -> None:
        """载入视频后：把明显不合法的默认值收回来，并提示帧率 / 总帧数。"""
        info = self.info
        if info is None:
            return
        # 程序预填默认值不算「用户修改」
        with self.mute_dirty():
            self._fit_defaults_to_video()
        self.set_hint(
            f"该视频 {info.fps_text}、共 {info.frame_count_text} 帧、时长 {info.duration_text}"
        )
        self.refresh_validation()
        self._refresh_preview()

    def _fit_defaults_to_video(self) -> None:
        """短视频时把默认的起始位置 / 跨度收进合法范围，避免一载入按钮就是灰的。"""
        info = self.info
        if info is None:
            return
        total = info.frame_count
        if not total and info.duration and info.fps:
            total = int(round(info.duration * info.fps))
        if total and self.start_unit_value == core_frames.UNIT_FRAMES and self.start_value >= total:
            self.start_input.setValue(0.0)
        if self.span_unit_value == core_frames.UNIT_FRAMES:
            if total and self.span_value > total:
                self.span_input.setValue(float(total))
        elif info.duration and self.span_value > info.duration:
            self.span_input.setValue(round(info.duration, 2))

    def reset_parameters(self) -> None:
        """恢复默认：从第 0 帧起取 1 帧、输出 PNG。"""
        self.start_input.setValue(_DEFAULT_START)
        self.span_input.setValue(_DEFAULT_SPAN)
        self.start_unit.setCurrentIndex(1)  # 帧
        self.span_unit.setCurrentIndex(1)  # 帧
        self.format_input.setCurrentIndex(0)  # PNG
        self._on_unit_changed()
        self.set_hint("")

    def _refresh_preview(self) -> None:
        """显示将要提取的帧区间。"""
        info = self.info
        if info is None:
            return
        frame_range = self.resolved_range()
        if frame_range is None:
            return
        self.set_hint(
            f"该视频 {info.fps_text}、共 {info.frame_count_text} 帧、时长 {info.duration_text}"
            f"　|　将提取 {frame_range.text}"
        )
