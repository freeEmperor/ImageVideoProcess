"""视频裁剪画布和共用时间轴。"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from imagevideoprocess.operations.crop import CropRect

_ACCENT = QColor("#2f6fed")
_HANDLE_RADIUS = 7


def _limit(value: int, lower: int, upper: int) -> int:
    return min(upper, max(lower, value))


class CropCanvas(QWidget):
    """按预览图的缩放比例，在屏幕坐标与原视频像素之间转换。"""

    crop_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setToolTip("拖动裁剪框的边或角调整大小，拖动框内移动位置")
        self.frame = QImage()
        self.video_size = (0, 0)
        self.crop: CropRect | None = None
        self.message = "正在读取视频画面…"
        self._drag: tuple[QPointF, CropRect, int, int] | None = None

    def clear(self) -> None:
        self.frame = QImage()
        self.video_size = (0, 0)
        self.crop = None
        self.message = "正在读取视频画面…"
        self._drag = None
        self.unsetCursor()
        self.update()

    def _picture(self) -> QRectF:
        width, height = self.video_size
        scale = min((self.width() - 16) / width, (self.height() - 16) / height)
        return QRectF(
            (self.width() - width * scale) / 2,
            (self.height() - height * scale) / 2,
            width * scale,
            height * scale,
        )

    def _selection(self, picture: QRectF, crop: CropRect) -> QRectF:
        scale = picture.width() / self.video_size[0]
        return QRectF(
            picture.left() + crop.left * scale,
            picture.top() + crop.top * scale,
            crop.width * scale,
            crop.height * scale,
        )

    def paintEvent(self, _event) -> None:
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#141d2d"))
            painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
            if self.frame.isNull() or self.crop is None:
                painter.setPen(QColor("#d4deee"))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
                return

            picture = self._picture()
            selection = self._selection(picture, self.crop)
            painter.drawImage(picture, self.frame)
            outside = QPainterPath()
            outside.addRect(picture)
            outside.addRect(selection)
            painter.fillPath(outside, QColor(0, 0, 0, 140))
            painter.setPen(QPen(_ACCENT, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(selection)
            painter.setPen(QPen(_ACCENT, 1))
            painter.setBrush(QColor("#ffffff"))
            left, center_x, right = selection.left(), selection.center().x(), selection.right()
            top, center_y, bottom = selection.top(), selection.center().y(), selection.bottom()
            for x, y in (
                (left, top),
                (center_x, top),
                (right, top),
                (left, center_y),
                (right, center_y),
                (left, bottom),
                (center_x, bottom),
                (right, bottom),
            ):
                painter.drawRect(QRectF(x - 3, y - 3, 6, 6))

    def _hit(self, point: QPointF) -> tuple[int, int] | None:
        if self.crop is None:
            return None
        rect = self._selection(self._picture(), self.crop)
        radius = _HANDLE_RADIUS
        if not rect.adjusted(-radius, -radius, radius, radius).contains(point):
            return None

        def edge(position: float, near: float, far: float) -> int:
            first, second = abs(position - near), abs(position - far)
            if min(first, second) > radius:
                return 0
            return -1 if first <= second else 1

        return edge(point.x(), rect.left(), rect.right()), edge(
            point.y(), rect.top(), rect.bottom()
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        hit = self._hit(event.position())
        if event.button() == Qt.MouseButton.LeftButton and hit is not None and self.crop:
            self._drag = (event.position(), self.crop, *hit)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            hit = self._hit(event.position())
            if hit is None:
                self.unsetCursor()
                return
            x, y = hit
            if x and y:
                cursor = (
                    Qt.CursorShape.SizeFDiagCursor if x == y else Qt.CursorShape.SizeBDiagCursor
                )
            elif x or y:
                cursor = Qt.CursorShape.SizeHorCursor if x else Qt.CursorShape.SizeVerCursor
            else:
                cursor = Qt.CursorShape.SizeAllCursor
            self.setCursor(cursor)
            return

        origin, rect, x, y = self._drag
        width, height = self.video_size
        scale = self._picture().width() / width
        offset = event.position() - origin
        dx, dy = round(offset.x() / scale), round(offset.y() / scale)
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        if x == y == 0:
            left = _limit(left + dx, 0, width - rect.width)
            top = _limit(top + dy, 0, height - rect.height)
            right, bottom = left + rect.width, top + rect.height
        else:
            if x < 0:
                left = _limit(left + dx, 0, right - 1)
            elif x > 0:
                right = _limit(right + dx, left + 1, width)
            if y < 0:
                top = _limit(top + dy, 0, bottom - 1)
            elif y > 0:
                bottom = _limit(bottom + dy, top + 1, height)
        updated = CropRect(left, top, right, bottom)
        if updated != self.crop:
            self.crop_changed.emit(updated)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event)
            self._drag = None


class CropTimeline(QWidget):
    """上排控制预览位置，下排拖动剪辑范围的两个端点。"""

    seek = Signal(float)
    trim_changed = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(54)
        self.setMouseTracking(True)
        self.setToolTip("上排点击或拖动以预览画面，下排拖动两端以设置剪辑时间")
        self.duration = 0
        self.position = 0.0
        self.start = 0
        self.end = 0
        self._drag: str | None = None

    def reset(self, duration: int) -> None:
        self.duration = self.end = duration
        self.position = 0.0
        self.start = 0
        self._drag = None
        self.unsetCursor()
        self.update()

    def _track_width(self) -> int:
        return max(1, self.width() - 172)

    def _x(self, value: float) -> float:
        return 48 + value * self._track_width() / max(1, self.duration)

    def _handle(self, x: float) -> str | None:
        start = abs(x - self._x(self.start))
        end = abs(x - self._x(self.end))
        if min(start, end) > _HANDLE_RADIUS:
            return None
        return "start" if start <= end else "end"

    def paintEvent(self, _event) -> None:
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for label, y in (("预览", 13), ("剪辑", 40)):
                painter.setPen(QColor("#475569"))
                painter.drawText(QRectF(0, y - 12, 40, 24), Qt.AlignmentFlag.AlignVCenter, label)
                painter.setPen(
                    QPen(QColor("#d7e0ef"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                )
                painter.drawLine(QLineF(self._x(0), y, self._x(self.duration), y))

            start, end = self._x(self.start), self._x(self.end)
            painter.setPen(QPen(_ACCENT, 6))
            painter.drawLine(QLineF(start, 40, end, 40))
            painter.setPen(QPen(_ACCENT, 1))
            painter.setBrush(QColor("#ffffff"))
            for x in (start, end):
                painter.drawRoundedRect(QRectF(x - 4, 31, 8, 18), 3, 3)

            painter.setBrush(_ACCENT)
            painter.drawEllipse(QPointF(self._x(self.position), 13), 6, 6)
            painter.setPen(QColor("#475569"))
            painter.drawText(
                QRectF(self.width() - 113, 0, 113, 26),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                f"{self.position / 100:.2f} / {self.duration / 100:.2f} 秒",
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.duration:
            return
        point = event.position()
        if point.y() < 26 and self._x(0) - 8 <= point.x() <= self._x(self.duration) + 8:
            self._drag = "seek"
        elif point.y() >= 26:
            self._drag = self._handle(point.x())
        self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position()
        if self._drag is None:
            if point.y() >= 26 and self._handle(point.x()) is not None:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()
            return
        value = (point.x() - self._x(0)) * self.duration / self._track_width()
        if self._drag == "seek":
            self.position = min(self.duration, max(0.0, value))
            self.seek.emit(self.position / 100)
            self.update()
        elif self._drag == "start":
            self.trim_changed.emit(_limit(round(value), 0, self.end - 1), self.end)
        else:
            self.trim_changed.emit(self.start, _limit(round(value), self.start + 1, self.duration))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event)
            self._drag = None
