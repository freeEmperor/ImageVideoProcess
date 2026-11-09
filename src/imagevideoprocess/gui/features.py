"""功能注册表：**新增一个功能只需要在这里登记一次**。

设计目标（可扩展性）：左侧列表栏、主界面工作台都由这份注册表驱动，
新增功能 = 写一个 :class:`~imagevideoprocess.gui.widgets.panel.FeaturePanel` 子类，
用 ``@register_feature(...)`` 装饰它，并在 ``gui/panels/__init__.py`` 里 import 一次。
不需要改主窗口、侧栏或任何已有面板。

示例::

    @register_feature(
        key="convert",
        title="格式转换",
        subtitle="PNG / JPG / WebP / HEIC 互转",
        icon="fa5s.exchange-alt",
        accepted_kinds=("image", "video"),
        order=40,
    )
    class ConvertPanel(FeaturePanel):
        ...
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅用于类型检查，避免循环导入
    from imagevideoprocess.gui.widgets.panel import FeaturePanel


@dataclass(frozen=True)
class Feature:
    """一个功能项的描述。"""

    key: str
    title: str
    #: 左侧列表里的一行短说明（太长会被截断，建议 ≤ 10 个汉字）
    subtitle: str
    #: 工作台标题下方的完整说明（可以长）
    description: str
    icon: str
    panel_factory: Callable[[Feature], FeaturePanel]
    accepted_kinds: tuple[str, ...] = ("image", "video")
    order: int = 100

    @property
    def accepts_image(self) -> bool:
        """是否接受图片文件。"""
        return "image" in self.accepted_kinds

    @property
    def accepts_video(self) -> bool:
        """是否接受视频文件。"""
        return "video" in self.accepted_kinds

    @property
    def file_filter(self) -> str:
        """QFileDialog 用的过滤器字符串。"""
        if self.accepts_image and self.accepts_video:
            return "图片 / 视频文件 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.heic *.avif *.mp4 *.mov *.mkv *.avi *.webm *.flv *.wmv *.ts);;所有文件 (*.*)"
        if self.accepts_video:
            return "视频文件 (*.mp4 *.mov *.mkv *.avi *.webm *.flv *.wmv *.ts *.m4v *.mpg);;所有文件 (*.*)"
        return "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.heic *.heif *.avif);;所有文件 (*.*)"


#: 全部已注册功能（按 order 排序后使用）
_REGISTRY: list[Feature] = []


def register_feature(
    *,
    key: str,
    title: str,
    subtitle: str,
    description: str | None = None,
    icon: str = "fa5s.cube",
    accepted_kinds: tuple[str, ...] = ("image", "video"),
    order: int = 100,
) -> Callable[[type], type]:
    """装饰器：把一个面板类登记成左侧列表里的一个功能项。

    Args:
        key: 唯一标识。
        title: 左侧列表标题。
        subtitle: 左侧列表里的一行短说明（建议 ≤ 10 个汉字，长了会被截断）。
        description: 工作台标题下方的完整说明；不填则用 ``subtitle``。
        icon: qtawesome 图标名。
        accepted_kinds: 接受的文件类型，``("image", "video")`` / ``("video",)`` 等。
        order: 左侧列表排序。
    """

    def decorator(cls: type) -> type:
        for existing in _REGISTRY:
            if existing.key == key:
                raise ValueError(f"功能 key 重复：{key}")
        _REGISTRY.append(
            Feature(
                key=key,
                title=title,
                subtitle=subtitle,
                description=description or subtitle,
                icon=icon,
                panel_factory=cls,  # type: ignore[arg-type]
                accepted_kinds=accepted_kinds,
                order=order,
            )
        )
        return cls

    return decorator


def all_features() -> list[Feature]:
    """返回按 order 排序的全部功能。"""
    return sorted(_REGISTRY, key=lambda item: (item.order, item.title))


def find_feature(key: str) -> Feature | None:
    """按 key 找功能。"""
    for feature in _REGISTRY:
        if feature.key == key:
            return feature
    return None
