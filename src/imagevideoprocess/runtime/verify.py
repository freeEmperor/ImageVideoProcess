"""Explicit release verification; writes only inside the supplied scratch directory."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any


def run(folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "executable": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "checks": [],
    }
    try:
        import av
        from PIL import Image
        from PySide6.QtWidgets import QApplication

        from imagevideoprocess.gui.app import _app_icon
        from imagevideoprocess.gui.features import all_features
        from imagevideoprocess.gui.main_window import MainWindow
        from imagevideoprocess.media import audio_ops, media_info
        from imagevideoprocess.operations import compress, convert, crop, frames, resize, superres
        from imagevideoprocess.runtime.paths import processed_dir

        app = QApplication.instance() or QApplication([])
        assert isinstance(app, QApplication)
        from imagevideoprocess.gui.theme import STYLESHEET, light_palette

        app.setStyle("Fusion")
        app.setPalette(light_palette())
        app.setStyleSheet(STYLESHEET)
        window = MainWindow()
        assert len(all_features()) == 7
        icon = _app_icon()
        assert icon is not None and not icon.isNull()
        panels = [feature.panel_factory(feature) for feature in all_features()]
        window.show()
        app.processEvents()
        assert not window.grab().isNull()
        window.grab().save(str(folder / "window.png"))
        window.close()
        for panel in panels:
            panel.close()
        report["checks"].append("GUI: seven panels, icon, window rendering")
        photo = folder / "source.jpg"
        video = folder / "source.mp4"
        assert photo.is_file() and video.is_file(), "Generate source fixtures first"
        output = folder / "results"
        output.mkdir(exist_ok=True)

        def image_size(result, expected):
            with Image.open(result.first_output) as image:
                assert image.size == expected

        image_size(resize.resize_image(photo, 160, 90, out_dir=output), (160, 90))
        report["checks"].append("image resize")
        result = compress.compress_image(photo, photo.stat().st_size // 2, out_dir=output)
        assert result.output_bytes <= photo.stat().st_size // 2
        report["checks"].append("image compression")
        for fmt in ("png", "webp", "bmp", "tiff", "avif", "heic"):
            image_size(convert.convert(photo, fmt, out_dir=output), (320, 180))
        report["checks"].append("image conversion including HEIC/AVIF")
        for method in superres.METHODS:
            image_size(superres.supersample(photo, method, 2, out_dir=output), (640, 360))
        report["checks"].append("six upscaling methods")
        image_size(
            crop.crop_image(photo, crop.CropRect(10, 10, 110, 80), out_dir=output), (100, 70)
        )
        report["checks"].append("image crop")
        for name, result in [
            ("video resize", resize.resize_video(video, 160, 90, out_dir=output)),
            (
                "video compression",
                compress.compress_video(video, video.stat().st_size // 2, out_dir=output),
            ),
            ("video conversion", convert.convert(video, "mkv", out_dir=output)),
            (
                "video crop",
                crop.crop_video(
                    video,
                    crop.CropSelection(crop.CropRect(10, 10, 210, 110), 0.2, 0.8),
                    out_dir=output,
                ),
            ),
        ]:
            with av.open(str(result.first_output)) as container:
                assert container.streams.audio and next(container.decode(video=0)) is not None
            report["checks"].append(name + " with audio")
        result = frames.extract_frames(
            video, frames.resolve_range(media_info.probe(video), 0, "f", 3, "f"), out_dir=output
        )
        assert len(result.outputs) == 3
        report["checks"].append("frame extraction")
        for target in audio_ops.available_targets():
            result = audio_ops.extract_audio(video, target, out_dir=output)
            with av.open(str(result.first_output)) as container:
                assert next(container.decode(audio=0)) is not None
        report["checks"].append("all advertised audio formats")
        if report["frozen"]:
            assert processed_dir(False) == Path(sys.executable).parent / "processed"
        report["checks"].append("output location")
        report["ok"] = True
    except Exception:
        report["ok"] = False
        report["error"] = traceback.format_exc()
    (folder / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if report["ok"] else 1
