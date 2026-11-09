"""图片超分测试：各方法 / 各倍率的尺寸与命名、方法差异、边界与进度。"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from PIL import Image

from imagevideoprocess.core import media_info, superres
from imagevideoprocess.core.errors import InvalidParameterError
from media_factory import make_image, make_video


def _blocks_and_noise(tmp_dir, size: int = 200):
    """造两张确定性的测试图：干净棋盘图 + 加噪图。"""
    board = ((np.add.outer(np.arange(size), np.arange(size)) // 8) % 2 * 200 + 30).astype(np.uint8)
    canvas = np.dstack([board, board, np.zeros_like(board)])
    cv2.circle(canvas, (size // 2, size // 2), size // 4, (240, 240, 240), 3)

    clean = tmp_dir / "clean.png"
    Image.fromarray(canvas).save(clean)

    rng = np.random.default_rng(7)
    noisy_array = np.clip(
        canvas.astype(np.int16) + rng.normal(0, 18, canvas.shape).astype(np.int16), 0, 255
    ).astype(np.uint8)
    noisy = tmp_dir / "noisy.png"
    Image.fromarray(noisy_array).save(noisy)
    return clean, noisy


def _high_frequency(path) -> float:
    """拉普拉斯方差：高频能量，用来比较"锐不锐"。"""
    array = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    return float(cv2.Laplacian(array, cv2.CV_64F).var())


def _noise_level(path) -> float:
    """平坦区域的高频残差：越大说明噪点越明显。"""
    array = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    return float(np.mean(np.abs(array - cv2.GaussianBlur(array, (0, 0), 2.0))))


# ------------------------------------------------------------------ 方法表
def test_methods_are_described() -> None:
    """每种方法都要有名字和特点说明（界面下拉框要显示特点）。"""
    keys = [method.key for method in superres.METHODS]
    assert len(keys) == len(set(keys)), "方法 key 不能重复"
    for method in superres.METHODS:
        assert method.label
        assert method.description, f"{method.key} 缺少特点说明"
    assert superres.DEFAULT_METHOD in keys


def test_scale_factors_match_requirement() -> None:
    """需求规定倍率只有 2x / 3x / 4x。"""
    assert superres.SCALE_FACTORS == (2, 3, 4)
    assert superres.DEFAULT_SCALE in superres.SCALE_FACTORS


def test_method_by_key() -> None:
    """按 key 取方法；不认识的要报错。"""
    assert superres.method_by_key("lanczos").label == "Lanczos"
    assert superres.method_by_key("lanczos_sharp").sharpen
    assert superres.method_by_key("lanczos_denoise").denoise
    with pytest.raises(InvalidParameterError):
        superres.method_by_key("waifu2x")


def test_file_tag() -> None:
    """输出名里的「方法_倍率」片段。"""
    assert superres.file_tag(superres.method_by_key("lanczos"), 2) == "lanczos_2x"
    assert superres.file_tag(superres.method_by_key("lanczos_sharp"), 4) == "lanczos_sharp_4x"


# ------------------------------------------------------------------ 放大结果
@pytest.mark.parametrize("method", [method.key for method in superres.METHODS])
def test_supersample_size_and_name(tmp_dir, method: str) -> None:
    """每种方法 2x：尺寸翻倍、命名符合「原名_方法_倍率」。"""
    src = make_image(tmp_dir / "photo.jpg", size=(120, 90))
    result = superres.supersample(src, method, 2, out_dir=tmp_dir / "out")

    output = result.outputs[0]
    assert output.name == f"photo_{method}_2x.jpg"
    info = media_info.probe(output)
    assert (info.width, info.height) == (240, 180)
    assert info.kind == "image"
    assert result.verb == "超分"
    assert "2x" in result.note


@pytest.mark.parametrize(("scale", "expected"), [(2, (240, 180)), (3, (360, 270)), (4, (480, 360))])
def test_supersample_scales(tmp_dir, scale: int, expected: tuple[int, int]) -> None:
    """2x / 3x / 4x 都要放对尺寸。"""
    src = make_image(tmp_dir / "photo.png", size=(120, 90))
    result = superres.supersample(src, "lanczos", scale, out_dir=tmp_dir / "out")
    assert result.outputs[0].name == f"photo_lanczos_{scale}x.png"
    info = media_info.probe(result.outputs[0])
    assert (info.width, info.height) == expected


def test_methods_really_differ(tmp_dir) -> None:
    """不同方法的结果必须真的不一样（否则说明参数没生效）。"""
    clean, _ = _blocks_and_noise(tmp_dir)
    arrays = {}
    for method in superres.METHODS:
        output = superres.supersample(clean, method, 2, out_dir=tmp_dir / "out").outputs[0]
        arrays[method.key] = np.asarray(Image.open(output).convert("RGB"), dtype=np.int16)

    assert not np.array_equal(arrays["nearest"], arrays["bilinear"])
    assert not np.array_equal(arrays["bilinear"], arrays["bicubic"])
    assert not np.array_equal(arrays["bicubic"], arrays["lanczos"])
    assert not np.array_equal(arrays["lanczos"], arrays["lanczos_sharp"])


def test_nearest_is_pixel_block_replication(tmp_dir) -> None:
    """最近邻放大就是复制像素：4x4 输出块内每个通道都完全相同。"""
    clean, _ = _blocks_and_noise(tmp_dir)
    output = superres.supersample(clean, "nearest", 4, out_dir=tmp_dir / "out").outputs[0]
    array = np.asarray(Image.open(output).convert("RGB"))

    block = array[100:104, 100:104, :]  # 100 是 4 的倍数，正好落在一个放大块里
    for channel in range(3):
        values = block[..., channel]
        assert values.max() == values.min(), f"通道 {channel} 的 4x4 块内部应当完全一致"


def test_sharpen_increases_high_frequency(tmp_dir) -> None:
    """Lanczos + 锐化应当比纯 Lanczos 更锐。"""
    clean, _ = _blocks_and_noise(tmp_dir)
    plain = superres.supersample(clean, "lanczos", 2, out_dir=tmp_dir / "a").outputs[0]
    sharp = superres.supersample(clean, "lanczos_sharp", 2, out_dir=tmp_dir / "b").outputs[0]
    assert _high_frequency(sharp) > _high_frequency(plain)


def test_smooth_interpolation_ordering(tmp_dir) -> None:
    """平滑插值族的锐度应当 双线性 < 双三次 ≤ Lanczos。"""
    clean, _ = _blocks_and_noise(tmp_dir)
    values = {}
    for key in ("bilinear", "bicubic", "lanczos"):
        output = superres.supersample(clean, key, 2, out_dir=tmp_dir / key).outputs[0]
        values[key] = _high_frequency(output)
    assert values["bilinear"] < values["bicubic"] <= values["lanczos"], values


def test_denoise_reduces_noise_sharpen_amplifies(tmp_dir) -> None:
    """降噪版噪点更少、锐化版噪点更多。"""
    _, noisy = _blocks_and_noise(tmp_dir)
    plain = _noise_level(
        superres.supersample(noisy, "lanczos", 3, out_dir=tmp_dir / "a").outputs[0]
    )
    sharp = _noise_level(
        superres.supersample(noisy, "lanczos_sharp", 3, out_dir=tmp_dir / "b").outputs[0]
    )
    denoised = _noise_level(
        superres.supersample(noisy, "lanczos_denoise", 3, out_dir=tmp_dir / "c").outputs[0]
    )
    assert sharp > plain, "锐化应当放大噪点"
    assert denoised < plain, "降噪应当压住噪点"


def test_alpha_channel_preserved(tmp_dir) -> None:
    """带透明通道的 PNG 放大后仍要有透明通道。"""
    src = tmp_dir / "alpha.png"
    Image.new("RGBA", (80, 60), (200, 40, 40, 160)).save(src)
    result = superres.supersample(src, "lanczos_sharp", 4, out_dir=tmp_dir / "out")

    with Image.open(result.outputs[0]) as image:
        assert image.mode == "RGBA"
        assert image.size == (320, 240)
        assert image.getchannel("A").getextrema() == (160, 160), "透明值不该被锐化改变"


def test_grayscale_preserved(tmp_dir) -> None:
    """灰度图放大后还是灰度图。"""
    src = tmp_dir / "gray.png"
    Image.new("L", (50, 40), 128).save(src)
    result = superres.supersample(src, "bicubic", 3, out_dir=tmp_dir / "out")
    with Image.open(result.outputs[0]) as image:
        assert image.mode == "L"
        assert image.size == (150, 120)


def test_palette_image_converted(tmp_dir) -> None:
    """调色板图（P 模式）要先转 RGB 才能放大，不能报错。"""
    src = tmp_dir / "palette.png"
    Image.new("P", (40, 30)).save(src)
    result = superres.supersample(src, "lanczos", 2, out_dir=tmp_dir / "out")
    info = media_info.probe(result.outputs[0])
    assert (info.width, info.height) == (80, 60)


# ------------------------------------------------------------------ 校验
@pytest.mark.parametrize("scale", [1, 5, 0, -2])
def test_validate_rejects_bad_scale(tmp_dir, scale: int) -> None:
    """倍率只能是 2 / 3 / 4。"""
    info = media_info.probe(make_image(tmp_dir / "photo.jpg", size=(80, 60)))
    with pytest.raises(InvalidParameterError):
        superres.validate_request(info, scale)


def test_validate_rejects_oversized_output() -> None:
    """输出尺寸超限要拦住（否则会把内存吃爆）。"""
    with pytest.raises(InvalidParameterError):
        superres.validate_scale(20_000, 20_000, 4)
    # 12MP 手机照片 4x ≈ 192MP，仍在上限内
    assert superres.validate_scale(4000, 3000, 4) == (16000, 12000)


def test_supersample_rejects_video(tmp_dir) -> None:
    """超分只支持图片。"""
    video = make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90))
    with pytest.raises(InvalidParameterError):
        superres.supersample(video, "lanczos", 2, out_dir=tmp_dir / "out")


def test_describe_plan_mentions_output_name(tmp_dir) -> None:
    """界面说明要给出目标分辨率与输出文件名。"""
    src = make_image(tmp_dir / "photo.jpg", size=(800, 600))
    info = media_info.probe(src)
    text = superres.describe_plan(info, superres.method_by_key("bicubic"), 3)
    assert "2400×1800" in text
    assert "photo_bicubic_3x.jpg" in text
    assert "双三次" in text


def test_progress_reaches_full(tmp_dir) -> None:
    """进度回调最终到 100（降噪方法是分块处理的，中途也要有进度）。"""
    src = make_image(tmp_dir / "photo.jpg", size=(160, 120))
    seen: list[int] = []
    superres.supersample(src, "lanczos_denoise", 2, out_dir=tmp_dir / "out", progress=seen.append)
    assert seen[0] < seen[-1] == 100
    assert len(seen) > 3, "应当有多个进度节点"


def test_cancel_stops_work(tmp_dir) -> None:
    """取消令牌生效后立刻抛 Cancelled。"""
    from imagevideoprocess.core.errors import Cancelled
    from imagevideoprocess.core.progress import CancelToken

    src = make_image(tmp_dir / "photo.jpg", size=(160, 120))
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        superres.supersample(src, "lanczos", 2, out_dir=tmp_dir / "out", cancel=token)
