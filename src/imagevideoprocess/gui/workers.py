"""后台任务：把 core 层的耗时函数丢到 QThreadPool 里跑。

约定（README 7.3）：**绝不在 GUI 线程里做逐帧循环**。
面板只需提供一个 ``fn(progress, cancel) -> ProcessResult``，其余交给 :class:`Task`：

- 进度通过 ``signals.progress`` 回传到 GUI 线程；
- 结果 / 失败 / 取消分别走 ``finished`` / ``failed`` / ``cancelled``；
- ``cancel()`` 只是打个标记，真正的退出由 core 层在循环里检查 :class:`CancelToken`。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from imagevideoprocess.core.errors import Cancelled, ProcessingError
from imagevideoprocess.core.progress import CancelToken, ProgressFn
from imagevideoprocess.core.result import ProcessResult

#: 面板要提供的工作函数签名
TaskFunction = Callable[[ProgressFn, CancelToken], ProcessResult]


class TaskSignals(QObject):
    """任务信号集合（QRunnable 本身不是 QObject，所以单独放一个）。"""

    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class Task(QRunnable):
    """在后台线程里执行 ``fn``。"""

    def __init__(self, fn: TaskFunction) -> None:
        super().__init__()
        # 自己管理生命周期，避免 C++ 侧提前析构后 Python 还在用它发信号
        self.setAutoDelete(False)
        self.signals = TaskSignals()
        self.cancel_token = CancelToken()
        self._fn = fn
        self._last_percent = -1

    def cancel(self) -> None:
        """请求取消（异步生效）。"""
        self.cancel_token.cancel()

    def _report(self, percent: int) -> None:
        value = int(percent)
        if value != self._last_percent:
            self._last_percent = value
            self.signals.progress.emit(value)

    def run(self) -> None:  # pragma: no cover - 需要 Qt 事件循环，单测不覆盖
        try:
            result = self._fn(self._report, self.cancel_token)
        except Cancelled:
            self.signals.cancelled.emit()
        except ProcessingError as exc:
            self.signals.failed.emit(str(exc))
        except MemoryError:
            self.signals.failed.emit("内存不足，请换一个更小的文件或降低目标参数")
        except Exception as exc:  # 兜底：任何意外都不该让程序崩掉
            self.signals.failed.emit(f"未预期的错误：{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)
