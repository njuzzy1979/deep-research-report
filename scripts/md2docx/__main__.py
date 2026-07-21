"""python -m md2docx 入口（C-01）。

本模块只做"解析参数 → 调用管道 → 转发退出码"的胶水工作，不包含任何转换逻辑。
argparse 自身的 --help/--version/参数错误路径由 argparse 内部处理（直接写
sys.stdout/stderr 并 sys.exit(2)），这是 argparse 标准库行为，不受本项目
"cli.py 是唯一允许 print 的模块"约束支配的范围（该约束针对本项目自定义的输出，
不改写标准库内部实现）。
"""
from __future__ import annotations

import sys

from .cli import parse_args
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    return run(options)


if __name__ == "__main__":
    sys.exit(main())
