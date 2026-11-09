"""拖拽接收区：支持从 Windows 资源管理器直接拖文件进来，也可以点击选择。

样式由 ``QFrame#dropZone`` 决定，``dragActive`` / ``loaded`` 两个动态属性
控制「正在拖拽」「已载入文件」两种形态。

**提示文案随功能接受的类型变化**：抽帧只收视频，文案就写"把视频拖拽到这里"，
避免让用户误以为图片也能拖进来。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout, QWidget

from imagevideoprocess.gui.widgets.icons import icon

#: 空态文案：按接受的类型给出 (标题, 副标题, 图标名)
_EMPTY_TEXT: dict[tuple[str, ...], tuple[str, str, str]] = {
    ("image", "video"): (
        "把图片 / 视频拖拽到这里",
        "也可以点击此区域从磁盘选择文件",
        "fa5s.file-upload",
    ),
    ("video",): ("把视频拖拽到这里", "也可以点击此区域从磁盘选择视频", "fa5s.film"),
    ("image",): ("把图片拖拽到这里", "也可以点击此区域从磁盘选择图片", "fa5s.image"),
}

#: 已载入文件时的副标题
_LOADED_HINT = "可继续拖入新文件替换，或点击重新选择"


def _texts_for(kinds: tuple[str, ...]) -> tuple[str, str, str]:
    """取该功能对应的空态文案（未知组合退回"图片 / 视频"）。"""
    return _EMPTY_TEXT.get(kinds, _EMPTY_TEXT[("image", "video")])


class DropZone(QFrame):
    """文件拖拽 / 选择区。"""

    file_selected = Signal(Path)

    def __init__(
        self,
        *,
        file_filter: str = "所有文件 (*.*)",
        accepted_kinds: tuple[str, ...] = ("image", "video"),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", "false")
        self.setProperty("loaded", "false")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(148)
        self._file_filter = file_filter
        self._empty_title, self._empty_hint, self._icon_name = _texts_for(accepted_kinds)
        self._build_ui()
        self.set_loaded(None)

    # ----------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        self._icon_label = QLabel(self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap_icon = icon(self._icon_name, "#8fa2bd")
        if pixmap_icon is not None:
            self._icon_label.setPixmap(pixmap_icon.pixmap(30, 30))

        self._title_label = QLabel(self._empty_title, self)
        self._title_label.setObjectName("dropTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hint_label = QLabel(self._empty_hint, self)
        self._hint_label.setObjectName("dropHint")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        layout.addStretch(1)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._title_label)
        layout.addWidget(self._hint_label)
        layout.addStretch(1)

    # -------------------------------------------------------------- 状态
    def set_filter(self, file_filter: str) -> None:
        """更新「点击选择」时的文件过滤器。"""
        self._file_filter = file_filter

    def set_loaded(self, name: str | None) -> None:
        """切换空态 / 已载入形态。``name`` 为 None 表示回到空态。"""
        loaded = name is not None
        self.setProperty("loaded", "true" if loaded else "false")
        self.setMinimumHeight(96 if loaded else 148)
        if loaded:
            self._title_label.setText(name or "")
            self._hint_label.setText(_LOADED_HINT)
            self._icon_label.show()
        else:
            self._title_label.setText(self._empty_title)
            self._hint_label.setText(self._empty_hint)
            self._icon_label.show()
        self._repolish()

    @property
    def title_text(self) -> str:
        """空态标题（供测试/排查用）。"""
        return self._empty_title

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", "true" if active else "false")
        self._repolish()

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------- 事件（拖拽）
    @staticmethod
    def _local_files(mime: QMimeData) -> list[Path]:
        """取拖拽内容里的本地文件路径。"""
        return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt 命名
        """拖入时高亮，只接受本地文件。"""
        if self._local_files(event.mimeData()):
            event.acceptProposedAction()
            self._set_drag_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt 命名
        """拖动经过时保持接受状态。"""
        if self._local_files(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 - Qt 命名
        """拖出后取消高亮。"""
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt 命名
        """放下文件：只取第一个，其余交给面板提示。"""
        self._set_drag_active(False)
        files = self._local_files(event.mimeData())
        if files:
            event.acceptProposedAction()
            self.file_selected.emit(files[0])

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt 命名
        """点击打开文件选择对话框。"""
        if event.button() == Qt.MouseButton.LeftButton:
            selected, _ = QFileDialog.getOpenFileName(
                self, "选择待处理的文件", "", self._file_filter
            )
            if selected:
                self.file_selected.emit(Path(selected))
        super().mousePressEvent(event)
