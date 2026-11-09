"""进度回报与取消令牌。

core 层的所有耗时函数都接收两个可选参数：

- ``progress``：``Callable[[int], None]``，参数为 0~100 的整数百分比；
- ``cancel``：:class:`CancelToken`，任务内部定期检查，被取消时抛 :class:`Cancelled`。

GUI 层据此更新进度条与响应「取消」按钮，core 层本身不依赖任何 GUI 库。
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from imagevideoprocess.core.errors import Cancelled

#: 进度回调类型
ProgressFn = Callable[[int], None]


def noop_progress(_percent: int) -> None:
    """默认进度回调：什么都不做（便于命令行/单测调用）。"""


class CancelToken:
    """线程安全的取消令牌。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """请求取消。"""
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """是否已被请求取消。"""
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        """已被取消则抛出 :class:`Cancelled`。"""
        if self._event.is_set():
            raise Cancelled()


def clamp_percent(value: float) -> int:
    """把任意浮点进度夹到 0~100 的整数。"""
    return max(0, min(100, int(value)))
