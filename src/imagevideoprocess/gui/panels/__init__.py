"""功能面板集合。

**新增功能时：在这里 import 一次对应模块**，装饰器会自动把功能注册进左侧列表。

约定：一个功能一个模块，模块内用 ``@register_feature(...)`` 登记。
"""

from __future__ import annotations

# 逐行 import 即可，import 的副作用就是「注册功能」
from imagevideoprocess.gui.panels.audio import AudioPanel
from imagevideoprocess.gui.panels.compress import CompressPanel
from imagevideoprocess.gui.panels.convert import ConvertPanel
from imagevideoprocess.gui.panels.crop import CropPanel
from imagevideoprocess.gui.panels.frames import FramesPanel
from imagevideoprocess.gui.panels.resize import ResizePanel
from imagevideoprocess.gui.panels.superres import SuperResPanel

__all__ = [
    "AudioPanel",
    "CompressPanel",
    "ConvertPanel",
    "CropPanel",
    "FramesPanel",
    "ResizePanel",
    "SuperResPanel",
]
