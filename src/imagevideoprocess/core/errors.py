"""处理过程中抛出的异常类型。

GUI 层统一捕获 :class:`ProcessingError` 并把 ``str(exc)`` 展示给用户，
因此该层级的所有错误消息都应当是**面向用户的中文说明**。
"""

from __future__ import annotations


class ProcessingError(Exception):
    """所有可预期的处理失败（对用户可见，消息直接展示）。"""


class UnsupportedFormatError(ProcessingError):
    """文件格式不被支持，或该格式不支持当前操作。"""


class InvalidParameterError(ProcessingError):
    """用户输入的参数不合法（越界、区间超出视频范围等）。"""


class Cancelled(ProcessingError):
    """任务被用户取消。"""

    def __init__(self, message: str = "任务已取消") -> None:
        super().__init__(message)
