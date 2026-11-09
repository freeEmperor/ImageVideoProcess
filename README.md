# ImageVideoProcess

中文 | [English](README.en.md)

ImageVideoProcess 是一款面向 Windows 11 的桌面图片和视频处理工具。你可以把文件拖进窗口，调整参数后在本地完成处理。

## 功能

| 功能 | 说明 |
| --- | --- |
| 图片和视频压缩 | 按目标体积压缩。目标过小时，实际输出可能大于目标值。 |
| 图片和视频缩放 | 将图片或视频缩小到指定分辨率。视频输出的宽和高会调整为偶数。 |
| 视频抽帧 | 按时间或帧号设置起点和提取范围，输出 PNG、JPEG、WebP、BMP 或 TIFF。 |
| 图片和视频格式转换 | 将图片或视频转换为界面中可选的输出格式。 |
| 视频音频提取 | 从带音轨的视频导出音频。 |
| 图片超分辨率 | 使用插值和图像增强算法放大图片，支持 2×、3× 和 4×。 |

## 从源码运行

在 Windows 11 上安装 Git 和 uv，然后在 PowerShell 中执行下面的命令。项目使用 Python 3.13，uv 可以为你安装所需版本。 [uv 安装指南](https://docs.astral.sh/uv/getting-started/installation/)

```powershell
git clone https://github.com/freeEmperor/ImageVideoProcess.git
cd ImageVideoProcess
uv python install 3.13
uv sync --locked --group gui --group media
uv run --locked --group gui --group media imagevideoprocess
```

## 使用方法

1. 从窗口左侧选择功能。
2. 将适用的图片或视频拖到工作区，或点击拖放区选择文件。
3. 查看文件信息，填写处理参数，再点击操作按钮。处理期间可以查看进度或取消任务。
4. 点击「打开 processed 文件夹」查看结果。从源码运行时，`processed/` 位于仓库根目录。从打包的 `.exe` 启动时，它位于可执行文件旁边。

## 构建 Windows 可执行文件

在项目根目录运行以下命令。打包完成后可以双击 `dist\ImageVideoProcess.exe` 启动。

```powershell
uv sync --locked --group gui --group media --group packaging
.\scripts\build-exe.ps1
```

如果单文件版启动时报临时文件解压错误，可用 `-Dir` 构建文件夹版，然后运行 `dist\ImageVideoProcess\ImageVideoProcess.exe`。如果需要查看启动错误，可以用 `-Console` 保留控制台。

## 环境检查和测试

```powershell
uv run --locked --group gui --group media python -m imagevideoprocess.core.envreport
uv run --locked --group gui --group media pytest
```

桌面界面位于 [`src/imagevideoprocess/gui/`](src/imagevideoprocess/gui)，媒体处理逻辑位于 [`src/imagevideoprocess/core/`](src/imagevideoprocess/core)，测试位于 [`tests/`](tests)。
