# 架构与目录

| 目录 | 职责 |
| --- | --- |
| src/imagevideoprocess/core | 公共错误、结果、进度与取消令牌 |
| src/imagevideoprocess/operations | 压缩、缩放、转换、裁剪、抽帧与超分流程 |
| src/imagevideoprocess/media | 图片编解码、视频与音频处理、媒体信息 |
| src/imagevideoprocess/runtime | 输出路径、环境诊断、发布自检 |
| src/imagevideoprocess/gui | 窗口、功能面板、复用控件与后台任务 |
| src/imagevideoprocess/resources | 随应用发布的图标 |
| tests/unit / integration / gui | 环境隔离、媒体功能、GUI 行为测试 |
| tests/support | 现场生成测试媒体，避免保存大素材 |
| scripts | 日常启动、检查、构建和图标生成 |
| packaging | 唯一正式 spec 构建配置 |
| docs/history | 旧需求和过期交接资料 |
| build / dist | 可再生成的中间文件 / 发布产物 |
| processed | 用户输出，禁止当作缓存清理 |

调用方向：GUI → operations → media/core；处理模块不导入 GUI。runtime.paths 集中定义输出位置。源码与冻结模式共用包内 resources，不依赖当前工作目录。

沿用功能注册表、FeaturePanel 与后台任务机制，避免改变现有交互。音频处理沿用 media/audio_ops 的现有公共入口。此次主要迁移职责和导入关系，保留原处理算法；明确的行为修正只有 HEIC 编码器别名问题，见日志。

新增功能：在 operations 实现处理流程并验证边界，在 gui/panels 实现面板，通过注册表声明并在 panels/__init__.py 导入。不要在窗口中复制编解码逻辑。
