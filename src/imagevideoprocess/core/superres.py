"""图片超分辨率：用经典插值 / 增强方法把图片放大 2x / 3x / 4x。

**不含 AI 模型推理**（AI 超分需要额外的大型模型与运行时，不在本项目范围内，见 README）。
这里都是传统图像处理：零额外依赖、速度快、结果完全可预期；
代价是不会有 AI 那种"脑补"出来的细节。

可选方法（界面下拉框里显示的就是各自的 ``description``）：

| key | 方法 | 特点 |
| --- | --- | --- |
| ``nearest`` | 最近邻 | 最快，像素块状、边缘锯齿明显，适合像素画 / 图标 |
| ``bilinear`` | 双线性 | 快、画面偏软，几乎不会产生振铃 |
| ``bicubic`` | 双三次 | 平滑自然、通用默认，细节一般 |
| ``lanczos`` | Lanczos | 最锐利、边缘清晰，可能有轻微振铃 |
| ``lanczos_sharp`` | Lanczos + 锐化 | 放大后再做 USM 锐化，细节更突出（也会放大噪点） |
| ``lanczos_denoise`` | Lanczos + 先降噪 | 先双边滤波去噪再放大，适合有噪点 / 压缩伪影的图 |

输出命名：``原名_方法_倍率.扩展名``（例如 ``photo_lanczos_2x.png``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from imagevideoprocess.core.errors import InvalidParameterError, ProcessingError
from imagevideoprocess.core.image_ops import encode_to_bytes, get_exif, pil_format_for
from imagevideoprocess.core.media_info import MediaInfo, probe, register_image_plugins
from imagevideoprocess.core.paths import processed_dir, unique_path
from imagevideoprocess.core.progress import CancelToken, ProgressFn, noop_progress
from imagevideoprocess.core.result import ProcessResult

#: 可选倍率（需求规定 2x / 3x / 4x）
SCALE_FACTORS: tuple[int, ...] = (2, 3, 4)

#: 输出边长上限（很多编码器 / 看图软件超过这个尺寸就不认了）
MAX_OUTPUT_SIDE = 30_000

#: 输出总像素上限（约 250 MP；4x 放大 12MP 手机照片 ≈ 192 MP，仍在上限内）
MAX_OUTPUT_PIXELS = 250_000_000

#: 锐化的强度与模糊半径
_SHARPEN_AMOUNT = 0.6
_SHARPEN_SIGMA = 1.2

#: 降噪参数与分块数（分块是为了能报进度、能取消）
_DENOISE_D = 5
_DENOISE_SIGMA_COLOR = 40
_DENOISE_SIGMA_SPACE = 5
_DENOISE_BANDS = 8
_DENOISE_HALO = 4

#: 保存质量（超分是"还原细节"，所以按高保真存；仍用无损 / 高质量有损）
_SAVE_QUALITY = 95


@dataclass(frozen=True)
class SuperResMethod:
    """一种超分方法。"""

    key: str
    #: 界面上显示的名字
    label: str
    #: 一句话特点，显示在下拉框里
    description: str
    #: OpenCV 插值标志；None 表示用 Lanczos
    cv_flag: int | None = None
    #: 放大后是否做 USM 锐化
    sharpen: bool = False
    #: 放大前是否先做双边滤波降噪
    denoise: bool = False


#: 全部方法（按界面顺序：由快到慢、由软到锐）
METHODS: tuple[SuperResMethod, ...] = (
    SuperResMethod(
        key="nearest",
        label="最近邻",
        description="最快，像素块状、边缘锯齿，适合像素画 / 图标",
        cv_flag=cv2.INTER_NEAREST,
    ),
    SuperResMethod(
        key="bilinear",
        label="双线性",
        description="快、画面偏软，几乎不产生振铃",
        cv_flag=cv2.INTER_LINEAR,
    ),
    SuperResMethod(
        key="bicubic",
        label="双三次",
        description="平滑自然、通用，细节一般",
        cv_flag=cv2.INTER_CUBIC,
    ),
    SuperResMethod(
        key="lanczos",
        label="Lanczos",
        description="最锐利、边缘清晰，可能有轻微振铃",
        cv_flag=cv2.INTER_LANCZOS4,
    ),
    SuperResMethod(
        key="lanczos_sharp",
        label="Lanczos + 锐化",
        description="放大后再锐化，细节更突出（也会放大噪点）",
        cv_flag=cv2.INTER_LANCZOS4,
        sharpen=True,
    ),
    SuperResMethod(
        key="lanczos_denoise",
        label="Lanczos + 先降噪",
        description="先去噪再放大，适合有噪点 / 压缩伪影的图，画面更干净",
        cv_flag=cv2.INTER_LANCZOS4,
        denoise=True,
    ),
)

#: 默认方法（最锐利的经典插值）
DEFAULT_METHOD = "lanczos"

#: 默认倍率
DEFAULT_SCALE = 2

#: Pillow 模式 → 处理时用的模式（调色板 / CMYK 先转成 RGB，否则没法做像素运算）
_MODE_PLAN: dict[str, str] = {
    "1": "L",
    "L": "L",
    "LA": "LA",
    "P": "RGB",
    "RGB": "RGB",
    "RGBA": "RGBA",
    "CMYK": "RGB",
    "YCbCr": "RGB",
    "I;16": "I;16",
    "I": "RGB",
}

#: 处理模式 → 写回 Pillow 时用的模式（两边一一对应，16 位灰度要原样保留）
_PIL_MODE_OUT: dict[str, str] = {
    "L": "L",
    "LA": "LA",
    "RGB": "RGB",
    "RGBA": "RGBA",
    "I;16": "I;16",
}


def method_by_key(key: str) -> SuperResMethod:
    """按 key 找方法。

    Raises:
        InvalidParameterError: 没有这种方法。
    """
    for method in METHODS:
        if method.key == key:
            return method
    raise InvalidParameterError(f"不认识的超分方法：{key}")


def planned_size(width: int, height: int, scale: int) -> tuple[int, int]:
    """算出放大后的分辨率。"""
    return (int(width) * int(scale), int(height) * int(scale))


def validate_scale(width: int, height: int, scale: int) -> tuple[int, int]:
    """校验倍率与输出尺寸。

    Returns:
        放大后的 ``(宽, 高)``。

    Raises:
        InvalidParameterError: 倍率不合法，或输出尺寸超过上限。
    """
    if scale not in SCALE_FACTORS:
        raise InvalidParameterError(
            f"倍率只能是 {' / '.join(f'{value}x' for value in SCALE_FACTORS)}"
        )
    out_width, out_height = planned_size(width, height, scale)
    if out_width > MAX_OUTPUT_SIDE or out_height > MAX_OUTPUT_SIDE:
        raise InvalidParameterError(
            f"{scale}x 后分辨率为 {out_width}×{out_height}，"
            f"超过单边上限 {MAX_OUTPUT_SIDE}，请选更小的倍率"
        )
    pixels = out_width * out_height
    if pixels > MAX_OUTPUT_PIXELS:
        raise InvalidParameterError(
            f"{scale}x 后为 {out_width}×{out_height}"
            f"（约 {pixels / 1_000_000:.0f} 百万像素），"
            f"超过上限 {MAX_OUTPUT_PIXELS // 1_000_000} 百万像素，请选更小的倍率"
        )
    return out_width, out_height


def validate_request(info: MediaInfo, scale: int) -> tuple[int, int]:
    """校验一张图片能不能按该倍率放大，返回放大后的 ``(宽, 高)``。"""
    return validate_scale(info.width, info.height, scale)


def file_tag(method: SuperResMethod, scale: int) -> str:
    """输出文件名里的「方法_倍率」部分。"""
    return f"{method.key}_{int(scale)}x"


# ---------------------------------------------------------------- 图像处理
def _unsharp(array: np.ndarray) -> np.ndarray:
    """USM 锐化：原图 + 强度 ×（原图 − 高斯模糊）。"""
    blurred = cv2.GaussianBlur(array, (0, 0), sigmaX=_SHARPEN_SIGMA, sigmaY=_SHARPEN_SIGMA)
    return cv2.addWeighted(array, 1 + _SHARPEN_AMOUNT, blurred, -_SHARPEN_AMOUNT, 0)


def _sharpen_preserving_alpha(array: np.ndarray) -> np.ndarray:
    """锐化颜色通道，透明通道原样保留（否则透明边缘会出现光晕）。"""
    if array.ndim == 3 and array.shape[2] == 4:
        color = _unsharp(array[..., :3])
        return np.dstack([color, array[..., 3]])
    return _unsharp(array)


def _denoise(
    array: np.ndarray, token: CancelToken, progress: ProgressFn, start: int, end: int
) -> np.ndarray:
    """分块做双边滤波（去噪保边），顺便报进度、留出取消点。"""
    height = array.shape[0]
    result = array.copy()
    step = max(1, -(-height // _DENOISE_BANDS))  # 向上取整
    for y0 in range(0, height, step):
        token.raise_if_cancelled()
        y1 = min(height, y0 + step)
        # 取上下多几行做缓冲，避免分块边界出现接缝
        source_y0 = max(0, y0 - _DENOISE_HALO)
        source_y1 = min(height, y1 + _DENOISE_HALO)
        filtered = cv2.bilateralFilter(
            array[source_y0:source_y1],
            _DENOISE_D,
            _DENOISE_SIGMA_COLOR,
            _DENOISE_SIGMA_SPACE,
        )
        offset = y0 - source_y0
        result[y0:y1] = filtered[offset : offset + (y1 - y0)]
        progress(start + int((end - start) * y1 / height))
    return result


def _upscale(
    array: np.ndarray,
    method: SuperResMethod,
    scale: int,
    token: CancelToken,
    progress: ProgressFn,
) -> np.ndarray:
    """按方法放大像素数组。"""
    height, width = array.shape[:2]
    target = planned_size(width, height, scale)

    working = array
    if method.denoise:
        working = _denoise(working, token, progress, 20, 55)

    token.raise_if_cancelled()
    flag = method.cv_flag if method.cv_flag is not None else cv2.INTER_LANCZOS4
    if working.ndim == 3 and working.shape[2] not in (3, 4):
        # 2 通道（LA）之类的少见布局，逐通道放大更稳
        channels = [
            cv2.resize(working[..., index], target, interpolation=flag)
            for index in range(working.shape[2])
        ]
        upscaled = np.stack(channels, axis=-1)
    else:
        upscaled = cv2.resize(working, target, interpolation=flag)
    progress(70)

    if method.sharpen:
        upscaled = _sharpen_preserving_alpha(upscaled)
    progress(85)
    return upscaled


# ---------------------------------------------------------------- 对外入口
def supersample(
    source: str | Path,
    method: SuperResMethod | str = DEFAULT_METHOD,
    scale: int = DEFAULT_SCALE,
    *,
    out_dir: str | Path | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn = noop_progress,
) -> ProcessResult:
    """把一张图片放大 ``scale`` 倍，输出 ``原名_方法_倍率.扩展名``。

    Args:
        source: 待处理图片。
        method: 超分方法（:class:`SuperResMethod` 或它的 key）。
        scale: 放大倍率（2 / 3 / 4）。
        out_dir: 输出目录，默认 ``processed``。
        cancel: 取消令牌。
        progress: 进度回调（0~100）。

    Raises:
        InvalidParameterError: 不是图片、倍率不合法、输出尺寸超限。
        ProcessingError: 图片读不出来。
    """
    token = cancel or CancelToken()
    src = Path(source)
    info = probe(src)
    if info.kind != "image":
        raise InvalidParameterError("超分只支持图片文件")

    spec = method_by_key(method) if isinstance(method, str) else method
    out_width, out_height = validate_request(info, int(scale))

    register_image_plugins()
    progress(5)
    try:
        with Image.open(src) as handle:
            handle.load()
            source_mode = handle.mode
            target_mode = _MODE_PLAN.get(source_mode, "RGB")
            pil_format = pil_format_for(src.suffix) or (handle.format or "PNG").upper()
            exif = get_exif(handle)
            image = handle if source_mode == target_mode else handle.convert(target_mode)
            array = np.asarray(image).copy()
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"无法读取图片 {src.name}：{exc}") from exc

    token.raise_if_cancelled()
    progress(15)

    upscaled = _upscale(array, spec, int(scale), token, progress)
    if upscaled.shape[1] != out_width or upscaled.shape[0] != out_height:  # pragma: no cover
        raise ProcessingError("放大结果尺寸与预期不符")

    token.raise_if_cancelled()
    result_image = Image.fromarray(upscaled, mode=_PIL_MODE_OUT.get(target_mode, "RGB"))
    data = encode_to_bytes(
        result_image,
        pil_format,
        quality=_SAVE_QUALITY,
        exif=exif,
        subsampling="4:4:4",
    )

    folder = Path(out_dir) if out_dir else processed_dir()
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / f"{src.stem}_{file_tag(spec, int(scale))}{src.suffix.lower()}")
    dest.write_bytes(data)
    progress(100)

    note = f"{info.resolution_text} → {out_width}×{out_height}（{scale}x，{spec.label}）"
    if target_mode != source_mode:
        note += f"；源图 {source_mode} 模式已转换为 {target_mode}"
    return ProcessResult(
        outputs=[dest],
        source_path=src,
        source_bytes=info.size_bytes,
        output_bytes=dest.stat().st_size,
        verb="超分",
        note=note,
    )


def describe_plan(info: MediaInfo, method: SuperResMethod, scale: int) -> str:
    """给界面用：说明这次超分会怎么走。"""
    out_width, out_height = planned_size(info.width, info.height, scale)
    return (
        f"{info.resolution_text} → {out_width}×{out_height}"
        f"（{scale}x，{method.label}）；输出文件名 "
        f"{info.path.stem}_{file_tag(method, scale)}{info.path.suffix.lower()}"
    )
