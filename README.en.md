# ImageVideoProcess

[中文](README.md) | English

ImageVideoProcess is a Windows 11 desktop app for processing images and videos locally. Drag a file into the window, set the options, and start the job.

## Features

| Feature | What it does |
| --- | --- |
| Image and video compression | Compress toward a target file size. The output may exceed a very small target. |
| Image and video resizing | Downscale to a specified resolution. The app adjusts video output dimensions to even numbers. |
| Video frame extraction | Set the start and range in seconds or frames, then export PNG, JPEG, WebP, BMP, or TIFF images. |
| Image and video format conversion | Convert an image or video to one of the output formats offered in the app. |
| Audio extraction | Export audio from a video that contains an audio track. |
| Image upscaling | Enlarge images by 2×, 3×, or 4× using interpolation and image enhancement. |

## Run from source

Install Git and uv on Windows 11, then run the following commands in PowerShell. The project uses Python 3.13, which uv can install for you. [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

```powershell
git clone https://github.com/freeEmperor/ImageVideoProcess.git
cd ImageVideoProcess
uv python install 3.13
uv sync --locked --group gui --group media
uv run --locked --group gui --group media imagevideoprocess
```

## Use the app

1. Choose a tool from the sidebar. The interface is in Chinese.
2. Drop a supported image or video into the workspace, or click the drop area to browse for a file.
3. Review the file details, set the options, and click the action button. You can follow progress or cancel while the job runs.
4. Click **打开 processed 文件夹** to open the output folder. When running from source, `processed/` is in the repository root. When running the packaged app, it is next to the `.exe`.

## Build the Windows executable

Run these commands from the repository root. When the build finishes, double-click `dist\ImageVideoProcess.exe` to launch the app.

```powershell
uv sync --locked --group gui --group media --group packaging
.\scripts\build-exe.ps1
```

If the single-file build fails to extract temporary files at startup, pass `-Dir` to build a directory-based version and run `dist\ImageVideoProcess\ImageVideoProcess.exe`. Pass `-Console` to keep the console visible for startup errors.

## Check the environment and run tests

```powershell
uv run --locked --group gui --group media python -m imagevideoprocess.core.envreport
uv run --locked --group gui --group media pytest
```

The desktop interface is in [`src/imagevideoprocess/gui/`](src/imagevideoprocess/gui), the media processing code is in [`src/imagevideoprocess/core/`](src/imagevideoprocess/core), and tests are in [`tests/`](tests).
