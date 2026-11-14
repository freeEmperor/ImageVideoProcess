# 构建、瘦身与验证

唯一构建配置：`packaging/ImageVideoProcess.spec`。入口：`scripts/build-exe.ps1`，支持 `-Dir` / `-Console`。脚本通过 uv 同步 packaging 组，用项目解释器构建，临时限制 DLL 搜索 PATH 并恢复所有修改的进程变量。PyInstaller 缓存位于 build，未安装外部编译器。

## 结果（2026-11-14）

| 产物 | MiB |
| --- | ---: |
| 原有 EXE | 210.24 |
| 重构前完整源码重新构建对照（含图片裁剪） | 210.23 |
| 优化单文件 | 169.41 |
| 文件夹版整个目录 | 455.79 |

相对完整功能对照缩小 19.42%。文件夹版必须分发整个目录，不能只比较其启动 EXE。原始数据及校验和在 `build-metrics.json`。

## 具体措施

- OpenCV contrib 改为同版本 headless 主模块包，现有插值、锐化、降噪测试通过。
- 排除未使用的 Qt DataVisualization/Charts/WebEngine、测试与交互工具。
- PyAV 的 av.libs 保留规范目录副本；仅在 SHA256 相同时移除重复的根目录 DLL。新单文件扫描未发现重复 DLL 内容组。
- 保留 PyAV 与 imageio-ffmpeg 两条现有处理路径，未通过删除编解码能力降低体积。
- 图标进入包内 resources，统一源码和冻结模式资源路径。
- 暂不切换 Nuitka：本轮已达到 160–180 MiB 目标，未引入系统编译工具链。

## 可重复验证

先构建两种模式，再在项目终端运行：

```powershell
. .\scripts\activate-env.ps1
uv run --locked --group packaging python scripts/verify_release.py
```

脚本现场生成测试图片和带音轨视频，把发布包复制到独立中文/空格目录，清除 Python/Qt/FFmpeg 注入变量、限制 PATH、从临时目录启动。应用仅在显式 `--verify-release <测试目录>` 时运行自检，将结果写入该目录的 report.json；正常启动路径保持 GUI 行为。

检查涵盖 GUI 七面板与图标、截图、图片/视频压缩缩放转换裁剪、音轨、抽帧、六种超分、全部可选音频格式与输出位置。HEIC/AVIF 实际写入并读回。`release-verification.json` 保存三种模式的结果。

本机首次隔离副本观察到界面渲染时间：源码 1.377 s、文件夹版 6.087 s、单文件 13.000 s；整组验证分别 2.672 / 8.552 / 15.891 s。它们包含加载和验证初始化，受缓存和杀毒扫描影响，不是统计意义上的冷启动基准。

自动化测试覆盖参数错误、取消、文件命名、裁剪 EXIF/透明度及 GUI 联动。发布验证使用 Windows Qt 平台；未使用全新 Windows 虚拟机。用户数据不参与清理。
