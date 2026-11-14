"""验证裁剪导出的画面像素、时段与音轨。"""

from __future__ import annotations

import av
import pytest
from media_factory import make_video
from PIL import ImageChops, ImageStat

from imagevideoprocess.operations.crop import CropRect, CropSelection, crop_video, read_preview


@pytest.mark.parametrize("with_audio", [True, False])
def test_crop_video(tmp_dir, with_audio: bool) -> None:
    source = make_video(tmp_dir / "待裁剪.mp4", with_audio=with_audio)
    region = CropRect(75, 33, 198, 144)
    times = CropSelection(region, 0.40, 1.20)
    reports = []
    result = crop_video(source, times, out_dir=tmp_dir, progress=reports.append)
    assert result.first_output == tmp_dir / "待裁剪_cut.mp4"
    assert reports[0] == 0 and reports[-1] == 100

    expected = read_preview(source, times.start).image.crop(
        (region.left, region.top, region.right, region.bottom)
    )
    with av.open(str(result.first_output)) as output:
        video = output.streams.video[0]
        assert (video.width, video.height) == (123, 111)
        assert output.duration / av.time_base == pytest.approx(times.end - times.start, abs=0.04)
        assert bool(output.streams.audio) == with_audio
        first = next(output.decode(video))
    assert max(ImageStat.Stat(ImageChops.difference(first.to_image(), expected)).mean) < 5


def test_image_crop_orientation_alpha_and_collision(tmp_dir):
    from PIL import Image, ImageOps

    from imagevideoprocess.operations.crop import crop_image, read_image_preview

    source = tmp_dir / "方向 透明.png"
    image = Image.new("RGBA", (40, 20), (10, 30, 90, 87))
    exif = image.getexif()
    exif[274] = 6
    image.save(source, exif=exif)
    preview = read_image_preview(source)
    assert (preview.width, preview.height) == (20, 40)
    rect = CropRect(2, 3, 14, 29)
    first = crop_image(source, rect, out_dir=tmp_dir).first_output
    second = crop_image(source, rect, out_dir=tmp_dir).first_output
    assert second != first and first.exists()
    with Image.open(first) as actual, Image.open(source) as original:
        expected = ImageOps.exif_transpose(original).convert("RGBA").crop((2, 3, 14, 29))
        assert actual.size == (12, 26)
        assert actual.tobytes() == expected.tobytes()


def test_image_crop_cancel_and_invalid_bounds(tmp_dir):
    from PIL import Image

    from imagevideoprocess.core.errors import Cancelled, InvalidParameterError
    from imagevideoprocess.core.progress import CancelToken
    from imagevideoprocess.operations.crop import crop_image

    source = tmp_dir / "image.png"
    Image.new("RGB", (20, 10)).save(source)
    with pytest.raises(InvalidParameterError):
        crop_image(source, CropRect(0, 0, 30, 10), out_dir=tmp_dir)
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        crop_image(source, CropRect(0, 0, 10, 5), out_dir=tmp_dir, cancel=token)
    assert not list(tmp_dir.glob("*_cut*"))
