"""等价 shim：`python scripts/md2docx.py <input.md> [output.docx] [选项]`

供不熟悉 `python -m md2docx` 用法的调用方（04-interface-spec.md §1.1）。

实现方式：把本文件所在目录（scripts/）加入 sys.path，再 `import md2docx` 调用
包入口。经验证（同目录下包目录与同名模块文件并存时，CPython 的 FileFinder 优先
解析为常规包），`import md2docx` 在此处解析到的是 `scripts/md2docx/__init__.py`
所在的包，而不是本文件自身，不会发生递归导入。
"""
from __future__ import annotations

import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def main() -> int:
    from md2docx.__main__ import main as package_main

    return package_main()


if __name__ == "__main__":
    sys.exit(main())
