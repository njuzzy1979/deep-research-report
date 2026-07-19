#!/usr/bin/env python3
"""
Markdown → Word (.docx) 研究报告格式转换引擎 — 顶层入口脚本。

用法:
    python scripts/md2docx.py input.md -o output.docx
    python scripts/md2docx.py input.md -o output.docx --config report.yaml
    python scripts/md2docx.py input.md -o output.docx --title "报告题名" --org "机构名" --images figures/

此脚本将 scripts/md2docx/ 包加入 sys.path，然后委托给 cli.main()。
兼容旧版 markdown_to_docx.py 的命令行接口。

依赖: pip install python-docx pyyaml
"""

import sys
import os

# 将 scripts/ 目录加入 Python path（支持从任意目录运行此脚本）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from md2docx.cli import main

if __name__ == '__main__':
    main()
