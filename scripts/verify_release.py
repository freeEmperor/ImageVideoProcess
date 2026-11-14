"""Generate media and verify source, directory and single-file releases in isolation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/support"))
from media_factory import make_image, make_video  # noqa: E402


def main() -> int:
    scratch = ROOT / "build/release-validation" / time.strftime("%Y%m%d-%H%M%S")
    scratch.mkdir(parents=True)
    records = []
    for mode in ("source", "onedir", "onefile"):
        folder = scratch / mode / "中文 path"
        folder.mkdir(parents=True)
        make_image(folder / "source.jpg", size=(320, 180))
        make_video(folder / "source.mp4", seconds=1.2, with_audio=True)
        env = os.environ.copy()
        for key in (
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_QPA_PLATFORM",
            "IMAGEIO_FFMPEG_EXE",
        ):
            env.pop(key, None)
        env["PATH"] = os.pathsep.join(
            [str(Path(env["SYSTEMROOT"]) / "System32"), env["SYSTEMROOT"]]
        )
        if mode == "source":
            command = [sys.executable, "-m", "imagevideoprocess"]
        else:
            release = scratch / mode / "独立发布 copy"
            if mode == "onedir":
                shutil.copytree(ROOT / "dist/ImageVideoProcess", release)
            else:
                release.mkdir()
                shutil.copy2(ROOT / "dist/ImageVideoProcess.exe", release / "ImageVideoProcess.exe")
            command = [str(release / "ImageVideoProcess.exe")]
        started = time.time()
        result = subprocess.run(
            command + ["--verify-release", str(folder)],
            cwd=os.environ["TEMP"],
            env=env,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        elapsed = time.time() - started
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        record = {
            "mode": mode,
            "exit_code": result.returncode,
            "seconds": round(elapsed, 3),
            "gui_ready_seconds": round((folder / "window.png").stat().st_mtime - started, 3),
            "report": report,
        }
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
        if result.returncode or not report["ok"]:
            raise RuntimeError(f"{mode} verification failed")
    destination = ROOT / "docs/release-verification.json"
    destination.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
