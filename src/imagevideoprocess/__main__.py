"""程序入口。

- `uv run imagevideoprocess`  → main()
- `uv run python -m imagevideoprocess` → main()
- 打包成 exe 后双击 → main()

main() 会拉起图形界面；命令行传文件路径时会自动选择能处理该文件的功能并载入它：

    uv run imagevideoprocess D:\\photos\\a.jpg
"""

from __future__ import annotations

import sys


def main() -> int:
    """启动 GUI。返回进程退出码。"""
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-release":
        from pathlib import Path

        from imagevideoprocess.runtime.verify import run as verify

        return verify(Path(sys.argv[2]).resolve())
    from imagevideoprocess.gui.app import run

    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
