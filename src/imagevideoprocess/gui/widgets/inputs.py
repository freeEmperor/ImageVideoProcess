"""输入控件的小工具。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox

from imagevideoprocess.gui.theme import TEXT_MUTED, TEXT_SECONDARY

#: chevron 箭头尺寸 / 线宽 / 中心距右边缘的距离
#: （偏移量与 theme.py 里 ``QComboBox::drop-down`` 的宽度对应，改样式时一起改）
_ARROW_SIZE = 10.0
_ARROW_LINE_WIDTH = 1.6
_ARROW_RIGHT_OFFSET = 11.0


def no_buttons(box: QAbstractSpinBox) -> QAbstractSpinBox:
    """去掉数值输入框右侧的增减按钮（需求：输入框里不要上下箭头）。

    样式表里也写了一份（``QSpinBox::up-button`` 等），
    但直接关掉按钮符号更干净——连点击区域都不再存在。
    """
    box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return box


class ChevronComboBox(QComboBox):
    """右侧带 chevron（∨）箭头的下拉框。

    **为什么不用别的方式画箭头**：

    - QSS 的 ``::down-arrow`` 只能指定一张图片，画不出折线，
      又不想为一个小箭头引入资源文件；
    - 试过用 ``QProxyStyle`` 覆盖 ``PE_IndicatorArrowDown``：只要套了全局样式表，
      ``QStyleSheetStyle`` 就接管了 compat 下拉框的绘制，**根本不会调用**我们的
      ``drawPrimitive``（实测下拉框里完全找不到箭头颜色）。

    所以最稳的办法是在自己的 ``paintEvent`` 里叠一个箭头。
    面板里的单位 / 格式选择框统一用这个类；它仍是 ``QComboBox`` 子类，
    QSS 中 ``QComboBox`` 的样式照样生效。
    """

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt 命名
        """先让基类画好边框与文字，再在右侧补一个箭头。"""
        super().paintEvent(event)  # type: ignore[arg-type]
        self._paint_chevron()

    def _paint_chevron(self) -> None:
        """画一个「∨」形箭头。"""
        color = QColor(TEXT_SECONDARY if self.isEnabled() else TEXT_MUTED)
        pen = QPen(color, _ARROW_LINE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        half = _ARROW_SIZE / 2.0
        center_x = float(self.width()) - _ARROW_RIGHT_OFFSET
        center_y = self.height() / 2.0 + 0.5

        path = QPainterPath()
        path.moveTo(QPointF(center_x - half, center_y - half * 0.45))
        path.lineTo(QPointF(center_x, center_y + half * 0.45))
        path.lineTo(QPointF(center_x + half, center_y - half * 0.45))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
