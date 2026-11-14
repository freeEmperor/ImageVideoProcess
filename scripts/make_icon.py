"""生成打包用的应用图标 ``src/imagevideoprocess/resources/app.ico``。

图标是代码画出来的（不依赖任何美术资源），想换风格直接改这里的配色与图形即可。

用法::

    uv run python scripts/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

#: 输出路径（相对项目根目录）
OUTPUT = Path("src/imagevideoprocess/resources/app.ico")

#: 图标尺寸（ICO 里同时塞多档，Windows 会按需取用）
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: 配色
BG_TOP = (58, 122, 235)
BG_BOTTOM = (28, 74, 168)
FRAME = (255, 255, 255)
SUN = (255, 214, 102)
PLAY = (255, 255, 255)


def _rounded_gradient(size: int) -> Image.Image:
    """圆角矩形渐变底。"""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (size, size))
    pixels = gradient.load()
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = tuple(
            int(BG_TOP[index] + (BG_BOTTOM[index] - BG_TOP[index]) * ratio) for index in range(3)
        )
        for x in range(size):
            pixels[x, y] = (*color, 255)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=max(2, size // 5), fill=255
    )
    image.paste(gradient, (0, 0), mask)
    return image


def render(size: int) -> Image.Image:
    """画一张 size×size 的图标：白框照片 + 播放三角（图片 / 视频 通吃）。"""
    canvas = _rounded_gradient(size)
    draw = ImageDraw.Draw(canvas)
    unit = size / 32.0

    # 照片框
    frame_box = (5 * unit, 7 * unit, 27 * unit, 25 * unit)
    draw.rounded_rectangle(
        frame_box, radius=2.2 * unit, outline=FRAME, width=max(1, int(1.6 * unit))
    )
    # 框里的"太阳"
    draw.ellipse(
        (9 * unit, 11 * unit, 13 * unit, 15 * unit),
        fill=SUN,
    )
    # 框里的"山"
    draw.polygon(
        [
            (7 * unit, 23 * unit),
            (14 * unit, 15 * unit),
            (19 * unit, 23 * unit),
        ],
        fill=FRAME,
    )
    # 播放三角
    draw.polygon(
        [
            (20 * unit, 14 * unit),
            (28 * unit, 19 * unit),
            (20 * unit, 24 * unit),
        ],
        fill=PLAY,
    )
    return canvas


def main() -> int:
    """生成 ico 文件。"""
    root = Path(__file__).resolve().parents[1]
    target = root / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)

    frames = [render(size) for size in SIZES]
    # 以最大尺寸为底图交给 Pillow 生成各档尺寸（底图给小了，ICO 里就只有小图）
    largest = frames[-1]
    largest.save(target, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"已生成 {target}（{target.stat().st_size} 字节，{len(SIZES)} 档尺寸）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
