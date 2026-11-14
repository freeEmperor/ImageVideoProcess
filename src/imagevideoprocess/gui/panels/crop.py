"""图片视频裁剪工作台。"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSignalBlocker, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QGridLayout, QLabel, QSpinBox, QVBoxLayout

from imagevideoprocess.core.errors import InvalidParameterError
from imagevideoprocess.gui.features import register_feature
from imagevideoprocess.gui.widgets.crop_editor import CropCanvas, CropTimeline
from imagevideoprocess.gui.widgets.inputs import no_buttons
from imagevideoprocess.gui.widgets.panel import FeaturePanel
from imagevideoprocess.gui.workers import TaskFunction
from imagevideoprocess.operations.crop import (
    CropRect,
    CropSelection,
    PreviewFrame,
    crop_image,
    crop_video,
    read_image_preview,
    read_preview,
)


class _PreviewSignal(QObject):
    done = Signal(int, object, str)


class _PreviewTask(QRunnable):
    def __init__(self, source: Path, generation: int, seconds: float, kind: str) -> None:
        super().__init__()
        self.source = source
        self.generation = generation
        self.seconds = seconds
        self.kind = kind
        self.signal = _PreviewSignal()

    def run(self) -> None:
        try:
            frame = (
                read_image_preview(self.source)
                if self.kind == "image"
                else read_preview(self.source, self.seconds)
            )
        except Exception as exc:
            self.signal.done.emit(self.generation, None, str(exc))
        else:
            self.signal.done.emit(self.generation, frame, "")


@register_feature(
    key="crop",
    title="图片视频裁剪",
    subtitle="裁剪画面与时间段",
    description="拖入图片或视频裁剪画面，视频还可选择时间段。图片导出 PNG，视频导出 MP4。",
    icon="fa5s.crop-alt",
    accepted_kinds=("image", "video"),
    order=35,
)
class CropPanel(FeaturePanel):
    action_text = "裁剪"

    def _build_ui(self) -> None:
        super()._build_ui()
        layout = self.layout()
        assert isinstance(layout, QVBoxLayout)
        layout.setStretch(layout.indexOf(self.editor), 1)
        layout.setStretch(layout.count() - 2, 0)

    def build_parameters(self) -> QFrame:
        self._generation = 0
        self._preview_task: _PreviewTask | None = None
        self._pending_seek: float | None = None
        self._preview_error = ""
        self._duration = 0.0
        self._end_tick = 0
        self.editor = QFrame()
        self.editor.setObjectName("card")
        self.source_summary = QLabel("视频预览")
        self.source_summary.setObjectName("hint")
        self.canvas = CropCanvas()
        self.canvas.crop_changed.connect(self._set_crop)
        self.timeline = CropTimeline()
        self.timeline.seek.connect(self._seek)
        self.timeline.trim_changed.connect(self._set_trim)

        self.coordinates = tuple(QSpinBox() for _ in range(4))
        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for time_box in (self.start, self.end):
            time_box.setDecimals(2)
            time_box.setSingleStep(0.01)
        spin_boxes: tuple[QSpinBox | QDoubleSpinBox, ...] = (
            *self.coordinates,
            self.start,
            self.end,
        )
        for box in spin_boxes:
            no_buttons(box)
            box.setMinimumWidth(72)
            box.valueChanged.connect(self._parameters_changed)

        self.time_widgets = [self.timeline, self.start, self.end]
        fields = QGridLayout()
        fields.setHorizontalSpacing(8)
        for column, (name, box) in enumerate(
            zip(
                ("左上 X", "左上 Y", "右下 X", "右下 Y", "开始", "结束"),
                spin_boxes,
                strict=True,
            )
        ):
            unit = "像素" if column < 4 else "秒"
            caption = f"{name}（{unit}）" if column in (0, 4) else name
            label = QLabel(caption)
            if column >= 4:
                self.time_widgets.append(label)
            label.setObjectName("fieldLabel")
            label.setBuddy(box)
            box.setAccessibleName(f"{name}（{unit}）")
            fields.addWidget(label, 0, column)
            fields.addWidget(box, 1, column)

        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(self.source_summary)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.timeline)
        layout.addLayout(fields)
        self.editor.hide()
        return self.editor

    def reset_parameters(self) -> None:
        self._generation += 1
        self._pending_seek = None
        self._preview_error = ""
        self._duration = 0.0
        self.source_summary.setText("视频预览")
        self.canvas.clear()
        self.timeline.reset(0)
        self.editor.hide()

    def on_source_changed(self) -> None:
        # 为预览留出高度，文件名保留在拖放区，尺寸和帧率显示在预览上方。
        self.info_card.hide()
        self.reset_parameters()
        self.set_hint("")
        info = self.info
        is_video = info is not None and info.kind == "video"
        for widget in self.time_widgets:
            widget.setVisible(is_video)
        if info is not None and info.kind == "image":
            for coordinate in self.coordinates:
                coordinate.setEnabled(False)
            self.editor.show()
            self._seek(0)
            return
        if (
            info is None
            or not info.duration
            or not math.isfinite(info.duration)
            or info.duration <= 0
        ):
            self._preview_error = "无法确定视频时长"
            return
        self._duration = info.duration
        self._end_tick = max(1, round(info.duration * 100))
        self.timeline.setEnabled(False)
        for box in (*self.coordinates, self.start, self.end):
            box.setEnabled(False)
        self.editor.show()
        self._seek(0)

    def _seek(self, seconds: float) -> None:
        self._pending_seek = min(seconds, self._duration)
        self._start_preview()

    def _start_preview(self) -> None:
        if (
            self.source is None
            or self.info is None
            or self._pending_seek is None
            or self._preview_task is not None
        ):
            return
        task = _PreviewTask(self.source, self._generation, self._pending_seek, self.info.kind)
        self._pending_seek = None
        self._preview_task = task
        task.signal.done.connect(self._show_preview)
        QThreadPool.globalInstance().start(task)

    @Slot(int, object, str)
    def _show_preview(self, generation: int, frame: PreviewFrame | None, error: str) -> None:
        self._preview_task = None
        if generation == self._generation:
            if frame is not None:
                initial = self.canvas.crop is None
                image = frame.image.convert("RGBA")
                self.canvas.frame = QImage(
                    image.tobytes(),
                    image.width,
                    image.height,
                    image.width * 4,
                    QImage.Format.Format_RGBA8888,
                ).copy()
                if initial:
                    self.canvas.video_size = (frame.width, frame.height)
                    self._fill_defaults(frame.width, frame.height)
                self.canvas.update()
            elif self.canvas.crop is None:
                self._preview_error = error or "无法预览此文件"
                self.canvas.message = "无法预览此文件"
                self.canvas.update()
                self.refresh_validation()
            elif self._pending_seek is None:
                self.notify.emit("无法读取当前时间的预览画面", "error")
        self._start_preview()

    def _fill_defaults(self, width: int, height: int) -> None:
        fps = self.info.fps_text if self.info else ""
        label = "图片预览" if self.info and self.info.kind == "image" else "视频预览"
        self.source_summary.setText(f"{label}  ·  {width} × {height} 像素  ·  {fps}")
        self.timeline.reset(self._end_tick)
        self.timeline.setEnabled(True)
        for box, maximum in zip(
            self.coordinates, (width - 1, height - 1, width, height), strict=True
        ):
            with QSignalBlocker(box):
                box.setRange(0, maximum)
            box.setEnabled(True)
        for time_box in (self.start, self.end):
            with QSignalBlocker(time_box):
                time_box.setRange(0.0, self._end_tick / 100)
            time_box.setEnabled(True)
        with self.mute_dirty():
            self._set_crop(CropRect(0, 0, width, height))
            self._set_trim(0, self._end_tick)

    def _set_crop(self, rect: CropRect) -> None:
        for box, value in zip(
            self.coordinates, (rect.left, rect.top, rect.right, rect.bottom), strict=True
        ):
            with QSignalBlocker(box):
                box.setValue(value)
        self._parameters_changed()

    def _set_trim(self, start: int, end: int) -> None:
        with QSignalBlocker(self.start), QSignalBlocker(self.end):
            self.start.setValue(start / 100)
            self.end.setValue(end / 100)
        self._parameters_changed()

    def _selection(self) -> CropSelection:
        rect = CropRect(*(box.value() for box in self.coordinates))
        # 显示值保留两位小数，最后一个刻度仍代表视频的精确结尾。
        end = (
            self._duration if round(self.end.value() * 100) == self._end_tick else self.end.value()
        )
        return CropSelection(rect, self.start.value(), end)

    def _parameters_changed(self) -> None:
        self.mark_dirty()
        selection = self._selection()
        if selection.rect.is_valid(*self.canvas.video_size):
            self.canvas.crop = selection.rect
            self.canvas.update()
        if self.start.value() < self.end.value():
            self.timeline.start = round(self.start.value() * 100)
            self.timeline.end = round(self.end.value() * 100)
            self.timeline.update()
        self.refresh_validation()

    def validation_error(self) -> str | None:
        base = super().validation_error()
        if base:
            return base
        if self._preview_error:
            return self._preview_error
        if self.canvas.crop is None:
            return "正在读取画面…"
        if self.info and self.info.kind == "image":
            return (
                None
                if self._selection().rect.is_valid(*self.canvas.video_size)
                else "裁剪坐标必须位于图片内，且宽高大于零"
            )
        try:
            self._selection().validate(*self.canvas.video_size, self._duration)
        except InvalidParameterError as exc:
            return str(exc)
        return None

    def build_task(self) -> TaskFunction | None:
        source = self.source
        if source is None:
            return None
        selection = self._selection()
        is_image = self.info is not None and self.info.kind == "image"

        def run(progress, cancel):
            if is_image:
                return crop_image(source, selection.rect, progress=progress, cancel=cancel)
            return crop_video(source, selection, progress=progress, cancel=cancel)

        return run

    def _set_busy(self, busy: bool) -> None:
        self.editor.setEnabled(not busy)
        self.drop_zone.setEnabled(not busy)
        super()._set_busy(busy)
