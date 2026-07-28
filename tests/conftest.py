# -*- coding: utf-8 -*-
"""tests/ 目录（skill 根级测试）的共享 pytest fixtures。

与 ``scripts/md2docx/tests/conftest.py`` 类似，但服务于 skill 根目录下的
``tests/`` —— 主要是 A1（outline_reader subsections 字段名修复）回归测试
与跨 fixture 的 L2 快照测试。此处只需保证 ``md2docx`` 包可被 import。
"""
from __future__ import annotations

import sys
from pathlib import Path

# skill 根目录 = tests/ 的上一级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
