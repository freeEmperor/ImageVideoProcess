"""功能工作台基类 —— 新增功能只需要继承它。

每个功能面板都是「主界面里的一个工作台」，统一结构：

    ┌ 标题 + 说明 ────────────────────────────────┐
    │ 拖拽区（DropZone）                           │
    │ 文件信息卡片（FileCard，载入后出现）          │
    │ 参数区（子类实现 build_parameters()）         │
    │ 提示 / 校验信息                               │
    │ [打开输出目录]        [进度条]   [主操作按钮]  │
    └──────────────────────────────────────────────┘

子类需要实现/覆盖：

- :meth:`build_parameters`：返回参数控件（可返回 None）。
- :meth:`validation_error`：返回不合法原因（None = 合法，按钮可点）。
- :meth:`build_task`：返回 ``fn(progress, cancel) -> ProcessResult``。
- 可选钩子：:meth:`on_source_changed`、:meth:`on_finished_extra`。

耗时逻辑**必须**放在 :meth:`build_task` 返回的函数里，它会被丢到 QThreadPool 执行。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from imagevideoprocess.core.errors import ProcessingError
from imagevideoprocess.core.media_info import MediaInfo, probe
from imagevideoprocess.core.paths import processed_dir
from imagevideoprocess.core.progress import CancelToken, ProgressFn
from imagevideoprocess.core.result import ProcessResult
from imagevideoprocess.gui.features import Feature
from imagevideoprocess.gui.widgets.dropzone import DropZone
from imagevideoprocess.gui.widgets.filecard import FileInfoCard
from imagevideoprocess.gui.workers import Task

#: 主操作按钮文字
DEFAULT_ACTION_TEXT = "开始处理"


class FeaturePanel(QWidget):
    """所有功能工作台的基类。"""

    #: (提示文本, 级别) → 主窗口弹出自动消散的提示条
    notify = Signal(str, str)
    #: 任务进行中为 True → 主窗口据此禁用左侧列表，避免中途切走
    busy_changed = Signal(bool)
    #: 状态栏文本
    status_message = Signal(str)

    #: 主操作按钮文字，子类可覆盖
    action_text: str = DEFAULT_ACTION_TEXT

    def __init__(self, feature: Feature, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.feature = feature
        self._source: Path | None = None
        self._info: MediaInfo | None = None
        self._task: Task | None = None
        #: 用户是否改过参数（决定切换功能时要不要弹确认框）
        self._dirty = False
        #: 程序自动预填默认值期间为 True，期间的改动不算「用户修改」
        self._dirty_muted = False
        #: 界面搭好之前不要刷校验（子类在 build_parameters 里可能触发信号）
        self._ui_ready = False
        self.setObjectName("page")
        self._build_ui()
        self._ui_ready = True
        self.refresh_validation()

    # ================================================================ 子类接口
    def build_parameters(self) -> QWidget | None:
        """构建参数区控件；不需要参数就返回 None。"""
        return None

    def validation_error(self) -> str | None:
        """返回当前输入不合法原因；返回 None 表示可以开始处理。"""
        if self._source is None or self._info is None:
            return "请先拖入待处理的文件"
        return None

    def build_task(self) -> Callable[[ProgressFn, CancelToken], ProcessResult] | None:
        """返回要放到后台线程执行的工作函数。"""
        return None

    def on_source_changed(self) -> None:
        """载入新文件后回调，子类可用来重置参数。"""

    def on_finished_extra(self, _result: ProcessResult) -> None:
        """处理成功后的额外回调。"""

    # ============================================================== 修改状态
    def mark_dirty(self) -> None:
        """标记「用户已经动过这个工作台」。

        子类在参数控件的信号处理里调用它；这样切换功能时才能判断
        要不要弹「确定要切换吗」的确认框（没动过就不打扰用户）。

        界面搭好之前的调用一律忽略：子类在 ``build_parameters()`` 里初始化控件时
        也会触发信号，那不是用户改的。
        """
        if self._dirty_muted or not self._ui_ready:
            return
        self._dirty = True

    @contextmanager
    def mute_dirty(self) -> Iterator[None]:
        """在这个上下文里做的改动不算「用户修改」（用于程序预填默认值）。"""
        previous = self._dirty_muted
        self._dirty_muted = True
        try:
            yield
        finally:
            self._dirty_muted = previous

    def is_dirty(self) -> bool:
        """是否已经动过这个工作台：拖入过文件，或改过参数。"""
        return self._source is not None or self._dirty

    def reset(self) -> None:
        """清空工作台：丢掉已载入的文件与参数，回到刚打开时的状态。

        切换功能时会调用它，这样确认框里说的"文件和参数不会保留"才是真的，
        同时避免切回来时还是一个"改过"的面板、动不动就弹确认框。
        """
        self._source = None
        self._info = None
        self._dirty = False
        with self.mute_dirty():
            self.reset_parameters()
        self.drop_zone.set_loaded(None)
        self.info_card.set_info(None)
        self.set_hint("")
        self.refresh_validation()

    def reset_parameters(self) -> None:
        """把参数控件恢复成默认值（子类按需覆盖）。"""

    # ==================================================================== UI
    def _build_ui(self) -> None:
        header = QVBoxLayout()
        header.setSpacing(2)

        title = QLabel(self.feature.title)
        title.setObjectName("panelTitle")
        description = QLabel(self.feature.description)
        description.setObjectName("panelDescription")
        description.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(description)

        self.drop_zone = DropZone(
            file_filter=self.feature.file_filter,
            accepted_kinds=self.feature.accepted_kinds,
        )
        self.drop_zone.file_selected.connect(self.set_source)

        self.info_card = FileInfoCard()

        parameters = self.build_parameters()

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("hint")
        self.hint_label.setWordWrap(True)
        self.hint_label.hide()

        self.error_label = QLabel("")
        self.error_label.setObjectName("hintWarn")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        # 底部：进度条 + 按钮
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumWidth(220)
        self.progress_bar.hide()

        self.action_button = QPushButton(self.action_text)
        self.action_button.setObjectName("primary")
        self.action_button.setMinimumWidth(140)
        self.action_button.clicked.connect(self._on_action)

        open_button = QPushButton("打开输出目录")
        open_button.clicked.connect(self._open_processed_dir)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        footer.addWidget(open_button)
        footer.addWidget(self.progress_bar, 1)
        footer.addStretch(1)
        footer.addWidget(self.action_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(self.drop_zone)
        layout.addWidget(self.info_card)
        if parameters is not None:
            layout.addWidget(parameters)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.error_label)
        layout.addStretch(1)
        layout.addLayout(footer)

    # ================================================================ 文件载入
    def set_source(self, path: Path) -> None:
        """载入待处理文件（拖拽或点击选择都会走到这里）。"""
        if self._task is not None:
            self.notify.emit("任务进行中，请先等待或取消", "info")
            return
        target = Path(path)
        try:
            info = probe(target)
        except (ProcessingError, FileNotFoundError, OSError) as exc:
            self.notify.emit(f"无法识别的文件：{exc}", "error")
            return

        if info.kind not in self.feature.accepted_kinds:
            wanted = "、".join(
                "图片" if k == "image" else "视频" for k in self.feature.accepted_kinds
            )
            self.notify.emit(f"「{self.feature.title}」只接受{wanted}文件", "error")
            return

        self._source = target
        self._info = info
        self.drop_zone.set_loaded(target.name)
        self.info_card.set_info(info)
        self.status_message.emit(f"已载入：{target.name}")
        self.on_source_changed()
        self.refresh_validation()

    @property
    def source(self) -> Path | None:
        """当前待处理文件。"""
        return self._source

    @property
    def info(self) -> MediaInfo | None:
        """当前文件信息。"""
        return self._info

    def is_busy(self) -> bool:
        """是否有任务在跑。"""
        return self._task is not None

    def request_cancel(self) -> None:
        """请求取消当前任务（供主窗口退出时调用）。"""
        if self._task is not None:
            self._task.cancel()

    # ============================================================== 校验联动
    def refresh_validation(self) -> None:
        """刷新按钮可用状态与错误提示（子类参数变化时调用）。"""
        if self._task is not None or not self._ui_ready:
            return
        error = self.validation_error()
        self.action_button.setEnabled(error is None)
        if error:
            self.error_label.setText(f"⚠ {error}")
            self.error_label.show()
        else:
            self.error_label.clear()
            self.error_label.hide()

    def set_hint(self, text: str) -> None:
        """设置参数区下方的普通提示（不影响校验）。"""
        if not hasattr(self, "hint_label"):
            return
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))

    # ================================================================== 任务
    def _on_action(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.action_button.setEnabled(False)
            self.action_button.setText("正在取消…")
            return
        if self.validation_error() is not None:
            return
        task_fn = self.build_task()
        if task_fn is None:
            return

        task = Task(task_fn)
        task.signals.progress.connect(self.progress_bar.setValue)
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        task.signals.cancelled.connect(self._on_cancelled)
        self._task = task
        self._set_busy(True)
        self.status_message.emit("处理中…")
        QThreadPool.globalInstance().start(task)

    def _set_busy(self, busy: bool) -> None:
        """切换「处理中」界面状态。"""
        self.action_button.setObjectName("danger" if busy else "primary")
        self.action_button.setText("取消" if busy else self.action_text)
        self.action_button.setEnabled(True)
        self.style().unpolish(self.action_button)
        self.style().polish(self.action_button)

        if busy:
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.error_label.hide()
        else:
            self.progress_bar.hide()
        self.busy_changed.emit(busy)
        if not busy:
            self._task = None
            self.refresh_validation()

    def _on_finished(self, result: object) -> None:
        self._set_busy(False)
        if not isinstance(result, ProcessResult):  # pragma: no cover - 防御性
            return
        self.notify.emit(result.summary, "success")
        names = "、".join(path.name for path in result.outputs[:3])
        if len(result.outputs) > 3:
            names += f" 等 {len(result.outputs)} 个文件"
        self.set_hint(f"已输出到 processed：{names}")
        self.status_message.emit(f"{result.verb}完成")
        self.on_finished_extra(result)

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.warning(self, f"{self.feature.title}失败", message)
        self.notify.emit("处理失败，详见弹窗说明", "error")
        self.status_message.emit("处理失败")

    def _on_cancelled(self) -> None:
        self._set_busy(False)
        self.notify.emit("任务已取消", "info")
        self.status_message.emit("任务已取消")

    # ================================================================== 杂项
    def _open_processed_dir(self) -> None:
        """在资源管理器里打开输出目录。"""
        folder = processed_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt 命名
        """面板关闭前请求取消任务（正常流程用不到，防御性代码）。"""
        if self._task is not None:
            self._task.cancel()
        super().closeEvent(event)  # type: ignore[arg-type]
