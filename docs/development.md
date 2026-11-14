# 开发与环境

Python 版本固定在 `.python-version`，uv 的 `only-managed` 策略在 `pyproject.toml`。项目包以 editable 方式安装，源码采用 src 布局。无需 `PYTHONPATH=src`。

`project.ps1 sync/run/check/diagnose` 是常用入口。构建使用 `build-exe.ps1`。脚本使用项目缓存及解释器目录，结束后恢复原有工作目录和进程变量；网络默认继承用户配置。

手动管理依赖：先 `. .\scripts\activate-env.ps1`，再 `uv add 包名` / `uv remove 包名`；开发工具使用 `--group dev`，打包工具使用 `--group packaging`。同步和验证使用 `--locked`，有意更改依赖时更新锁文件。禁止系统 pip 安装。

运行依赖：NumPy 数组、Pillow 图片、OpenCV headless 插值增强、PyAV 媒体编解码、imageio-ffmpeg 裁剪子进程、pillow-heif HEIC、PySide6 界面、qtawesome 图标。

移除的历史预装包包括 scipy、scikit-image、imageio、pyqtgraph、send2trash、typer、rich、platformdirs、pywin32 和 Nuitka；业务源码未使用这些包。冒烟检查同步改为检查实际运行依赖。保留完整 PySide6，暂不冒险更换为 Essentials。

测试按 unit / integration / gui 分组；support 现场生成小型媒体。GUI 测试使用 offscreen；发布验证使用 Windows Qt 平台。测试与构建临时文件集中在 build。新增功能沿用 GUI 功能注册表和面板接口，处理算法放在 operations/media。

系统环境、编译器或 SDK 变更仍须用户单独批准。本次没有安装编译器。
