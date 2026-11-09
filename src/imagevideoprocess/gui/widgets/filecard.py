"""待处理文件信息卡片：路径、图像/视频、格式、分辨率、帧率、大小等。

排版规则：**路径排第一且独占一整排**（值太长，两列会被挤爆），
其余属性每行放两组「标题: 值」。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from imagevideoprocess.core.media_info import MediaInfo

#: 每行放几组「标题: 值」
_PAIRS_PER_ROW = 2

#: 普通值超过这个长度就省略中间（完整内容放 tooltip）
_VALUE_MAX = 30

#: 独占整排的值（路径）超过这个长度才省略
_FULL_WIDTH_MAX = 120


def _elide_middle(text: str, limit: int) -> str:
    """中间省略：``C:\\a\\…\\photo.jpg``，保留头尾便于辨认。"""
    if len(text) <= limit:
        return text
    head = max(6, (limit - 1) * 2 // 3)
    tail = max(6, limit - 1 - head)
    return f"{text[:head]}…{text[-tail:]}"


class FileInfoCard(QFrame):
    """把 :class:`MediaInfo` 渲染成信息网格。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(14, 12, 14, 12)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(7)
        for column in range(_PAIRS_PER_ROW * 2):
            self._grid.setColumnStretch(column, 2 if column % 2 else 1)
        self.set_info(None)

    def set_info(self, info: MediaInfo | None) -> None:
        """刷新显示内容；``None`` 表示隐藏整张卡片。"""
        self._clear()
        if info is None:
            self.setVisible(False)
            return

        grid_row = 0
        column = 0
        for row in info.rows():
            if row.full_width:
                # 整排独占：先把当前行剩余的位置空掉
                if column:
                    grid_row += 1
                    column = 0
                self._grid.addWidget(self._key_label(row.key), grid_row, 0)
                self._grid.addWidget(
                    self._value_label(row.value, _FULL_WIDTH_MAX),
                    grid_row,
                    1,
                    1,
                    _PAIRS_PER_ROW * 2 - 1,
                )
                grid_row += 1
                continue

            self._grid.addWidget(self._key_label(row.key), grid_row, column * 2)
            self._grid.addWidget(self._value_label(row.value, _VALUE_MAX), grid_row, column * 2 + 1)
            column += 1
            if column >= _PAIRS_PER_ROW:
                column = 0
                grid_row += 1

        self.setVisible(True)

    @staticmethod
    def _key_label(key: str) -> QLabel:
        """属性名标签。"""
        label = QLabel(key)
        label.setObjectName("infoKey")
        return label

    @staticmethod
    def _value_label(value: str, limit: int) -> QLabel:
        """属性值标签（过长则中间省略，完整值放 tooltip）。"""
        label = QLabel(_elide_middle(value, limit))
        label.setObjectName("infoValue")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setToolTip(value)
        return label

    def _clear(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
