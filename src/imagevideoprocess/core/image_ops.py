"""图片编解码的公共小工具（压缩 / 缩放 / 未来的格式转换共用）。

把「Pillow 的格式细节」集中在这里，别的模块只跟 ``format`` 字符串打交道。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image

from imagevideoprocess.core.errors import UnsupportedFormatError
from imagevideoprocess.core.media_info import register_image_plugins

#: 扩展名（含点）→ Pillow 格式名
PIL_FORMAT_BY_SUFFIX: dict[str, str] = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".jpe": "JPEG",
    ".jfif": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".dib": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".gif": "GIF",
    ".heic": "HEIC",
    ".heif": "HEIF",
    ".avif": "AVIF",
    ".ico": "ICO",
    ".tga": "TGA",
}

#: 支持「有损质量」参数的格式
QUALITY_FORMATS: frozenset[str] = frozenset({"JPEG", "MPO", "WEBP", "AVIF", "HEIF", "HEIC"})

#: 无损但有调色板可减的格式
PALETTE_FORMATS: frozenset[str] = frozenset({"PNG"})


def pil_format_for(suffix: str) -> str | None:
    """扩展名 → Pillow 格式名（不认识返回 None）。"""
    return PIL_FORMAT_BY_SUFFIX.get(suffix.lower())


def flatten_alpha(image: Image.Image) -> Image.Image:
    """去掉 alpha（JPEG 不支持透明），透明处填白。"""
    if image.mode in {"RGB", "L"}:
        return image
    if image.mode == "RGBA" or "transparency" in image.info:
        background = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def get_exif(image: Image.Image) -> bytes | None:
    """取出图片里的 EXIF 字节（没有就返回 None）。"""
    exif = image.info.get("exif")
    return exif if isinstance(exif, bytes) and exif else None


def encode_to_bytes(
    image: Image.Image,
    fmt: str,
    *,
    quality: int | None = None,
    colors: int | None = None,
    exif: bytes | None = None,
    subsampling: str = "4:2:0",
) -> bytes:
    """把图片编码进内存并返回字节串。

    Args:
        image: 源图。
        fmt: Pillow 格式名，如 ``JPEG`` / ``PNG``。
        quality: 有损格式的质量（1~95）。
        colors: 仅 PNG 使用；小于 256 时走调色板量化。
        exif: 需要写回的 EXIF 字节。
        subsampling: 仅 JPEG 使用；``4:4:4`` 不做色度抽样（画质最好），
            ``4:2:0`` 体积更小。格式转换时用 ``4:4:4``。
    """
    register_image_plugins()
    buffer = io.BytesIO()
    upper = fmt.upper()
    try:
        if upper in {"JPEG", "MPO"}:
            kwargs: dict[str, Any] = {
                "format": "JPEG",
                "quality": int(quality or 85),
                "optimize": True,
                "progressive": True,
                "subsampling": subsampling,
            }
            if exif:
                kwargs["exif"] = exif
            flatten_alpha(image).save(buffer, **kwargs)
        elif upper == "WEBP":
            kwargs = {"format": "WEBP", "quality": int(quality or 85), "method": 6}
            if exif:
                kwargs["exif"] = exif
            image.save(buffer, **kwargs)
        elif upper == "PNG":
            target = image
            if colors is not None and colors < 256:
                mode = "RGBA" if image.mode in {"RGBA", "LA", "P"} else "RGB"
                target = image.convert(mode).quantize(
                    colors=max(2, int(colors)), method=Image.Quantize.FASTOCTREE
                )
            target.save(buffer, format="PNG", optimize=True, compress_level=9)
        elif upper in {"AVIF", "HEIF", "HEIC"}:
            image.save(buffer, format=upper, quality=int(quality or 85))
        elif upper == "BMP":
            # BMP 的 32 位带 alpha 版本 Windows 看图不一定认，这里拍平成 24 位
            flatten_alpha(image).save(buffer, format="BMP")
        elif upper in {"TIFF", "TIF"}:
            kwargs = {"format": "TIFF", "compression": "tiff_lzw"}  # 无损压缩
            if exif:
                kwargs["exif"] = exif
            image.save(buffer, **kwargs)
        else:
            raise UnsupportedFormatError(f"暂不支持以 {upper} 格式输出图片")
    except UnsupportedFormatError:
        raise
    except Exception as exc:
        raise UnsupportedFormatError(f"{upper} 格式编码失败：{exc}") from exc
    return buffer.getvalue()


def save_image(
    image: Image.Image,
    dest: Path,
    fmt: str,
    *,
    quality: int = 95,
    exif: bytes | None = None,
) -> None:
    """按指定格式把图片写到磁盘（覆盖已存在文件）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(encode_to_bytes(image, fmt, quality=quality, exif=exif))
