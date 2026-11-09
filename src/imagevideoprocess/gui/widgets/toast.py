"""自动消散的提示条（浮在主界面底部）。"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

#: 提示级别 → 展示时长（毫秒）
_DURATIONS = {"success": 2800, "info": 2800, "error": 5000}


class Toast(QFrame):
    """浮层提示条：显示后自动淡出，不需要用户点击。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setProperty("level", "success")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._label = QLabel(self)
        self._label.setObjectName("toastText")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.addWidget(self._label)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(340)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade.finished.connect(self._after_fade)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade)

        self.hide()

    # ----------------------------------------------------------------- API
    def show_message(self, text: str, level: str = "success", duration: int | None = None) -> None:
        """显示一条提示。

        Args:
            text: 提示文本。
            level: ``success`` / ``info`` / ``error``，决定配色与停留时长。
            duration: 覆盖默认停留时长（毫秒）。
        """
        self._label.setText(text)
        self.setProperty("level", level)
        # 改了动态属性要重新走一遍样式，否则配色不变
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        self.reposition()
        self._fade.stop()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(duration if duration is not None else _DURATIONS.get(level, 2800))

    def reposition(self) -> None:
        """贴着父窗口底部居中摆放（父窗口尺寸变化时调用）。"""
        parent = self.parentWidget()
        if parent is None:
            return
        x = max(12, (parent.width() - self.width()) // 2)
        y = max(12, parent.height() - self.height() - 28)
        self.move(x, y)

    # ------------------------------------------------------------ internal
    def _start_fade(self) -> None:
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()
