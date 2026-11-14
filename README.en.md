# ImageVideoProcess

[中文](README.md) | English

A local Windows 11 image/video processing desktop application with a PySide6 GUI. Releases include their Python and FFmpeg runtimes.

## Features

Image/video compression, downscaling, frame extraction, image/video cropping, format conversion, audio extraction, and six classical image upscaling methods (2×/3×/4×). Existing validation, progress, cancellation and feature-switch confirmation are retained.

Image cropping respects EXIF orientation and exports transparent PNG files (`name_cut.png`). Video cropping exports `name_cut.mp4` with the selected time range and audio. Source runs save to the repository's `processed/`; packaged runs save beside the executable.

## Run and maintain

Install uv, open PowerShell in the project directory, then run:

```powershell
.\scripts\project.ps1 sync
.\scripts\project.ps1 run
.\scripts\project.ps1 check
.\scripts\project.ps1 diagnose
```

Only uv-managed CPython 3.13.14 is used. Python lives in `.uv-python`, project dependencies in `.venv`, and downloads/build cache in `.uv-cache`. The scripts restore process environment settings on exit and do not change global Python, proxy settings or your PowerShell profile. No custom `PYTHONPATH` is needed.

For manual uv commands, explicitly load `. .\scripts\activate-env.ps1` in the current terminal, then use `uv sync --locked` and `uv run --locked ...`. Runtime dependencies are project dependencies; development and packaging tools have separate groups.

## Build

```powershell
.\scripts\build-exe.ps1
.\scripts\build-exe.ps1 -Dir
```

The default produces `dist/ImageVideoProcess.exe`. Directory mode produces `dist/ImageVideoProcess/`; distribute the whole directory. Add `-Console` for debugging. Both modes use `packaging/ImageVideoProcess.spec` and automatically sync the packaging group. One-file mode extracts its payload at startup.

See [architecture](docs/architecture.md), [development](docs/development.md), [packaging/validation](docs/packaging.md). Local handoff notes (`info.md`, `log.md`, `docs/history/`) remain outside version control. Media and processed outputs are never environment cleanup targets.
