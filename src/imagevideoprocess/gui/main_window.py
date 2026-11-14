"""主窗口：左侧功能列表栏 + 右侧功能工作台。

交互约定（来自需求）：

- 左侧每一项是一个功能，**先点列表项，右侧才显示对应工作台**；
- 切换功能会弹确认框（确定 / 取消），取消则退回原来的功能；
- 处理任务进行中禁用左侧列表，避免中途切走导致状态错乱；
- 处理完成 / 失败时在窗口底部弹出会自动消散的提示条。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeyEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import imagevideoprocess as pkg
from imagevideoprocess.core.errors import ProcessingError
from imagevideoprocess.gui import features as feature_registry

# 导入各功能面板模块（import 的副作用就是把它们注册进功能列表，
# 漏掉这一行左侧列表会是空的 —— 新增功能时不用改这里，改 panels/__init__.py）
from imagevideoprocess.gui import panels as _panels  # noqa: F401
from imagevideoprocess.gui.features import Feature
from imagevideoprocess.gui.theme import STYLESHEET
from imagevideoprocess.gui.widgets.icons import icon
from imagevideoprocess.gui.widgets.panel import FeaturePanel
from imagevideoprocess.gui.widgets.toast import Toast
from imagevideoprocess.media.media_info import probe
from imagevideoprocess.runtime.paths import processed_dir

#: 左侧列表项的固定高度
_ITEM_HEIGHT = 60

#: 副标题在列表里最多显示多少字
_SUBTITLE_MAX = 16


class FeatureList(QListWidget):
    """左侧功能列表。

    **为什么不用 ``currentRowChanged``**：Qt 在控件首次显示时会自动把当前项设成第 0 行，
    于是「还没点任何功能，主界面就显示出了第一个工作台」，与需求（先点列表项才显示工作台）
    不符。这里只在**用户主动点击 / 按方向键**时才发出 :attr:`row_activated`。
    """

    row_activated = Signal(int)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt 命名
        """鼠标点击某项后通知外部（点在空白处不通知）。"""
        item = self.itemAt(event.position().toPoint())
        super().mouseReleaseEvent(event)
        if item is not None:
            self.row_activated.emit(self.row(item))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt 命名
        """键盘方向键切换后通知外部。"""
        navigation = {
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
        }
        previous = self.currentRow()
        super().keyPressEvent(event)
        if event.key() in navigation and self.currentRow() != previous:
            self.row_activated.emit(self.currentRow())


class SidebarItem(QWidget):
    """左侧列表项的内容（图标 + 标题 + 一行副标题）。"""

    def __init__(self, feature: Feature, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 让点击事件穿透到 QListWidget 的 item 上，选中高亮才生效
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        icon_label = QLabel(self)
        pixmap_icon = icon(feature.icon)
        if pixmap_icon is not None:
            icon_label.setPixmap(pixmap_icon.pixmap(20, 20))
        icon_label.setFixedWidth(24)

        title = QLabel(feature.title, self)
        title.setObjectName("sidebarTitle")
        subtitle_text = feature.subtitle
        if len(subtitle_text) > _SUBTITLE_MAX:
            subtitle_text = subtitle_text[: _SUBTITLE_MAX - 1] + "…"
        subtitle = QLabel(subtitle_text, self)
        subtitle.setObjectName("sidebarSubtitle")

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(0)
        texts.addWidget(title)
        texts.addWidget(subtitle)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        layout.addWidget(icon_label)
        layout.addLayout(texts, 1)


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{pkg.APP_NAME} v{pkg.__version__}")
        self.resize(1120, 740)
        self.setMinimumSize(940, 640)
        app_icon = icon("fa5s.magic", "#2f6fed")
        if app_icon is not None:
            self.setWindowIcon(app_icon)

        self._features: list[Feature] = feature_registry.all_features()
        self._panels: dict[str, FeaturePanel] = {}
        self._current_key: str | None = None
        self._switching = False

        self._build_ui()
        self._toast = Toast(self._central)
        self._status_label.setText("就绪：请从左侧选择一个功能")
        # 等 Qt 把窗口摆好后再清掉自动选中的第一项
        QTimer.singleShot(0, self.clear_initial_selection)

    # ==================================================================== UI
    def _build_ui(self) -> None:
        self._central = QWidget(self)
        self._central.setObjectName("page")
        self.setCentralWidget(self._central)

        self._sidebar = FeatureList()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(236)
        self._sidebar.setIconSize(QSize(20, 20))
        self._sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for feature in self._features:
            item = QListWidgetItem(self._sidebar)
            item.setData(Qt.ItemDataRole.UserRole, feature.key)
            item.setSizeHint(QSize(0, _ITEM_HEIGHT))
            item.setToolTip(f"{feature.title}\n{feature.subtitle}")
            self._sidebar.setItemWidget(item, SidebarItem(feature))
        self._sidebar.row_activated.connect(self._on_row_activated)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_welcome_page())

        sidebar_panel = QFrame()
        sidebar_panel.setObjectName("sidebarPanel")
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        app_title = QLabel(pkg.APP_NAME)
        app_title.setObjectName("appTitle")
        app_subtitle = QLabel("处理结果统一保存到 processed 文件夹")
        app_subtitle.setObjectName("appSubtitle")
        sidebar_layout.addWidget(app_title)
        sidebar_layout.addWidget(app_subtitle)
        sidebar_layout.addWidget(self._sidebar, 1)

        row = QHBoxLayout(self._central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(sidebar_panel)
        row.addWidget(self._stack, 1)

        self._build_status_bar()

    def _build_welcome_page(self) -> QWidget:
        """未选择功能时的欢迎页。"""
        page = QWidget()
        page.setObjectName("page")
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(560)

        title = QLabel("请从左侧列表选择一个功能")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lines = [
            "1. 在左侧点击要使用的功能（切换功能会先弹确认框）",
            "2. 把图片 / 视频从资源管理器拖到工作台的提示区域",
            "3. 填好参数后点击下方按钮，处理结果自动存到 processed 文件夹",
        ]
        body = QVBoxLayout(card)
        body.setContentsMargins(28, 26, 28, 26)
        body.setSpacing(10)
        body.addWidget(title)
        for line in lines:
            label = QLabel(line)
            label.setObjectName("hint")
            body.addWidget(label)

        outer = QVBoxLayout(page)
        outer.addStretch(1)
        wrapper = QHBoxLayout()
        wrapper.addStretch(1)
        wrapper.addWidget(card)
        wrapper.addStretch(1)
        outer.addLayout(wrapper)
        outer.addStretch(1)
        return page

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self._status_label = QLabel("就绪")
        open_button = QPushButton("打开 processed 文件夹")
        open_button.clicked.connect(self._open_processed_dir)
        folder_label = QLabel(f"输出目录：{processed_dir(create=False)}")

        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(folder_label)
        bar.addPermanentWidget(open_button)

    # =============================================================== 功能切换
    def _on_row_activated(self, row: int) -> None:
        """用户点击了左侧某个功能：必要时先弹确认框，再切换工作台。"""
        if self._switching or row < 0 or row >= len(self._features):
            return
        feature = self._features[row]
        if feature.key == self._current_key:
            self._sync_sidebar(feature)
            return
        # 只有当前工作台被动过（拖入文件或改过参数）才弹确认框
        if self._current_key is not None and self._current_panel_dirty():
            current = feature_registry.find_feature(self._current_key)
            if current is not None and not self._confirm_switch(current, feature):
                self._restore_row()
                return
        self._activate(feature)

    def _current_panel_dirty(self) -> bool:
        """当前工作台是否已经被动过（拖入过文件，或改过参数）。"""
        if self._current_key is None:
            return False
        panel = self._panels.get(self._current_key)
        return panel is not None and panel.is_dirty()

    def clear_initial_selection(self) -> None:
        """启动时清掉 Qt 自作主张的初始选中项（此时还没有任何工作台）。"""
        if self._current_key is None:
            self._switching = True
            self._sidebar.setCurrentRow(-1)
            self._sidebar.clearSelection()
            self._switching = False

    def _confirm_switch(self, current: Feature, target: Feature) -> bool:
        """切换功能前的确认框（仅在当前工作台被动过时才会调用）。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("切换功能")
        box.setText(f"确定要从「{current.title}」切换到「{target.title}」吗？")
        box.setInformativeText("当前工作台已载入的文件和填写的参数会被清空。")
        confirm = box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        # 「确定」用主色按钮（强调默认动作）。注意：objectName 是按钮建好之后才改的，
        # 必须重新 polish 一次，否则样式表不会重新计算，颜色不会变。
        confirm.setObjectName("primary")
        confirm.style().unpolish(confirm)
        confirm.style().polish(confirm)
        box.setDefaultButton(confirm)
        box.exec()
        return box.clickedButton() is confirm

    def _restore_row(self) -> None:
        """用户取消切换：把选中项退回当前功能。"""
        if self._current_key is None:
            return
        for index, feature in enumerate(self._features):
            if feature.key == self._current_key:
                self._switching = True
                self._sidebar.setCurrentRow(index)
                self._switching = False
                break

    def _activate(self, feature: Feature) -> None:
        """显示某个功能的工作台（首次访问时才创建），并同步左侧选中项。"""
        previous_key = self._current_key
        panel = self._panel_for(feature)
        if previous_key is not None and previous_key != feature.key:
            # 切走时把上一个工作台清空（确认框里承诺的"不会保留"要兑现）
            old_panel = self._panels.get(previous_key)
            if old_panel is not None:
                old_panel.reset()
        self._current_key = feature.key
        self._stack.setCurrentWidget(panel)
        self._sync_sidebar(feature)
        self._status_label.setText(f"当前功能：{feature.title}")
        panel.refresh_validation()

    def _sync_sidebar(self, feature: Feature) -> None:
        """让左侧列表的选中项与当前功能保持一致（不触发确认框）。"""
        for index, item in enumerate(self._features):
            if item.key == feature.key and self._sidebar.currentRow() != index:
                self._switching = True
                self._sidebar.setCurrentRow(index)
                self._switching = False
                break

    def _panel_for(self, feature: Feature) -> FeaturePanel:
        """取（或创建）功能面板，并接好与主窗口的信号。"""
        panel = self._panels.get(feature.key)
        if panel is None:
            panel = feature.panel_factory(feature)
            panel.notify.connect(self.show_toast)
            panel.status_message.connect(self._status_label.setText)
            panel.busy_changed.connect(self._on_busy_changed)
            self._panels[feature.key] = panel
            self._stack.addWidget(panel)
        return panel

    def activate_file(self, path: Path) -> bool:
        """把文件路径直接交给「第一个能处理它的功能」（供命令行参数使用）。

        Returns:
            是否找到了可处理该文件的功能。
        """
        if not path.exists():
            return False
        try:
            info = probe(path)
        except (ProcessingError, OSError):
            return False
        for feature in self._features:
            if info.kind not in feature.accepted_kinds:
                continue
            self._activate(feature)
            panel = self._panels[feature.key]
            panel.set_source(path)
            return True
        return False

    # ================================================================== 提示
    def show_toast(self, text: str, level: str = "success") -> None:
        """弹出会自动消散的提示条。"""
        self._toast.show_message(text, level)

    def _on_busy_changed(self, busy: bool) -> None:
        """任务进行中禁用左侧列表。"""
        self._sidebar.setEnabled(not busy)
        if busy:
            self._status_label.setText("处理中…（可点「取消」中止）")

    def _open_processed_dir(self) -> None:
        """在资源管理器里打开输出目录。"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(processed_dir())))

    # ================================================================== 事件
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt 命名
        """窗口尺寸变化时重新摆放提示条。"""
        super().resizeEvent(event)
        self._toast.reposition()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 命名
        """退出前先请求取消所有后台任务，避免线程还在跑就退出。"""
        running = [panel for panel in self._panels.values() if panel.is_busy()]
        if running:
            answer = QMessageBox.question(
                self,
                "任务进行中",
                "还有任务正在处理，确定要退出吗？未完成的文件不会保留。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for panel in running:
                panel.request_cancel()
            QThreadPool.globalInstance().waitForDone(8000)
        event.accept()


#: 样式表在 app.py 里统一 apply，这里导出便于测试引用
__all__ = ["MainWindow", "SidebarItem", "STYLESHEET"]
