# ImageVideoProcess

中文 | [English](README.en.md)

Windows 11 本地图片、视频处理应用，使用 PySide6 图形界面。发布包无需安装 Python 或系统 FFmpeg。

## 功能

| 功能 | 行为 |
| --- | --- |
| 图片 / 视频压缩 | 按目标体积处理；目标过小时可能无法达到，界面会提示实际结果 |
| 图片 / 视频缩放 | 缩小至指定分辨率；视频编码尺寸按现有规则调整 |
| 视频抽帧 | 按秒数或帧号指定起点及范围，支持 PNG/JPEG/WebP/BMP/TIFF |
| 图片 / 视频裁剪 | 图片按显示方向裁剪并保留透明度；视频裁剪画面与时段并保留音轨 |
| 格式转换 | 使用界面列出的图片或视频格式；保留现有质量和转封装规则 |
| 视频音频提取 | 导出界面列出的可用音频格式 |
| 图片超分 | 六种经典插值 / 增强方法，支持 2×、3×、4×，不含 AI 模型 |

选择左侧功能后拖入文件或点击选择文件，调整参数再执行。保留输入校验、进度、取消、切换确认及完成提示。

图片裁剪导出 `原名_cut.png`；视频裁剪导出 `原名_cut.mp4`。图片隐藏时间控件；视频可调整预览位置、像素区域及起止时间。裁剪同名文件追加编号。

源码版输出到项目根目录 `processed/`；发布版输出到 EXE 同级 `processed/`。用户媒体和处理结果不属于环境清理对象。

## 从源码运行

先安装 uv，在项目目录打开 PowerShell：

```powershell
.\scripts\project.ps1 sync
.\scripts\project.ps1 run
```

项目使用 uv 下载和管理的 **CPython 3.13.14**，解释器存放在 `.uv-python/`，依赖在 `.venv/`，缓存位于 `.uv-cache/`。只允许 uv 托管 Python；不使用系统 Python，不需要手工设置 `PYTHONPATH`。首次同步可按需下载解释器。脚本不更改代理、用户 profile 或全局环境变量，退出时恢复会话设置。

## 测试与诊断

```powershell
.\scripts\project.ps1 check
.\scripts\project.ps1 diagnose
```

开发者手工操作 uv 时，可在当前终端执行 `. .\scripts\activate-env.ps1`，再用 `uv sync --locked`、`uv run --locked pytest` 等。这个显式加载方式会保留本终端的项目路径变量；日常操作推荐上面的封装脚本。

## 构建发布包

```powershell
.\scripts\build-exe.ps1          # dist/ImageVideoProcess.exe
.\scripts\build-exe.ps1 -Dir     # dist/ImageVideoProcess/，整个目录一起分发
```

`-Console` 用于构建带控制台的排障版本。脚本自动同步打包依赖，唯一构建配置为 `packaging/ImageVideoProcess.spec`。单文件启动时会解压；若运行位置限制临时解压，可使用文件夹版。

## 维护资料

- [架构与目录](docs/architecture.md)
- [环境与开发](docs/development.md)
- [打包与验证](docs/packaging.md)

本地交接信息 `info.md`、变更日志 `log.md` 及 `docs/history/` 按原有隐私约定保留在工作区，不随仓库发布。

所有包通过 uv 管理；依赖声明与 `uv.lock` 一起维护。运行依赖、开发工具和打包工具分别管理。
