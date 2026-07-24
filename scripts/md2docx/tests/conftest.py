# -*- coding: utf-8 -*-
"""pytest fixtures for md2docx integration tests.

提供临时目录、样本文件准备、转换器调用封装等共享基础设施。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# 项目根目录 = deep-research-report skill 根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_FIXTURES_DIR = Path(__file__).resolve().parent / "test_fixtures"


def _make_dummy_png(path: Path) -> None:
    """生成最小合法 PNG (1x1 像素)，供图片引用测试使用。"""
    import struct
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\xff\x00"))
    iend = _chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)


@pytest.fixture
def project_root() -> Path:
    """返回 deep-research-report skill 根目录的绝对路径。"""
    return _PROJECT_ROOT


@pytest.fixture
def scripts_dir() -> Path:
    """返回 scripts/ 目录路径（转换器 --cwd 参数值）。"""
    return _SCRIPTS_DIR


@pytest.fixture
def tmp_workdir(tmp_path: Path) -> Path:
    """为每个测试创建独立的工作目录。

    同时在该目录下放入 dummy.png，供图片引用测试使用。
    """
    _make_dummy_png(tmp_path / "dummy.png")
    return tmp_path


def copy_fixture_to_workdir(fixture_name: str, workdir: Path) -> Path:
    """将 test_fixtures/ 下的样本文件复制到 workdir，返回目标路径。

    复制时自动将 test_fixtures/dummy.png 的相对路径替换为 workdir 下的实际路径。
    """
    src = _FIXTURES_DIR / fixture_name
    dst = workdir / fixture_name
    content = src.read_text(encoding="utf-8")
    # 将 test_fixtures/dummy.png 替换为 workdir/dummy.png
    content = content.replace("test_fixtures/dummy.png", "dummy.png")
    dst.write_text(content, encoding="utf-8")
    return dst


def run_converter(
    input_md: Path,
    output_docx: Path | None = None,
    *,
    figures_dir: Path | None = None,
    allow_missing_figures: bool = True,
    report_path: Path | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """调用 md2docx 转换器，返回 subprocess.CompletedProcess。

    从 scripts/ 目录执行 `python -m md2docx`，确保模块路径正确。
    """
    if cwd is None:
        cwd = _SCRIPTS_DIR

    cmd = [sys.executable, "-m", "md2docx", str(input_md)]

    if output_docx is not None:
        cmd.append(str(output_docx))

    if figures_dir is not None:
        cmd.extend(["--figures-dir", str(figures_dir)])

    if allow_missing_figures:
        cmd.append("--allow-missing-figures")

    if report_path is not None:
        cmd.extend(["--report-path", str(report_path)])

    # Windows 中文环境下 subprocess 默认用 GBK 解码 stdout/stderr，
    # 但转换器输出 UTF-8 中文文本。强制使用 UTF-8 + errors='replace' 防崩溃。
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
    )
    return result


def count_fatal_in_stderr(stderr: str) -> int:
    """从 stderr 输出中统计 FATAL 级别问题数量。"""
    return stderr.count("[FATAL]")


def count_pattern_in_output(output: str, pattern: str) -> int:
    """统计 output 中 pattern 出现次数。"""
    return output.count(pattern)


# ---------------------------------------------------------------------------
# 结构化断言支持：在进程内驱动 阶段0→3（normalize→clean→parse→assemble），
# 直接返回 DocumentIR，供测试对 HeadingIR.kind / number / display_number 等
# **结构化字段**做断言（而非对转换报告文本做脆弱的字符串包含检测）。
# ---------------------------------------------------------------------------


class _MinimalBuildOptions:
    """assemble.builder.build() 所需的最小 options 蒙皮。

    builder 仅消费 options.input_path 与 options.metadata_cli_overrides()，
    故无需构造完整 RunOptions（其字段众多且面向 CLI）。
    """

    def __init__(self, input_path: str):
        self.input_path = input_path

    def metadata_cli_overrides(self) -> dict:
        return {}


def assemble_document_ir(md_path: Path, *, figures_dir: Path | None = None):
    """在进程内跑 阶段0→3，返回 (DocumentIR, IssueCollector)。

    用于对装配后的结构化 IR 做断言。图片存在性问题不影响标题分类，
    默认不传 figures_dir（缺图仅产 E-IMG，不阻断 IR 装配）。
    """
    # 确保 md2docx 包可导入（scripts/ 在 sys.path 上）
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))

    from md2docx.issues import IssueCollector
    from md2docx.textstage.normalize import normalize
    from md2docx.textstage.clean import clean
    from md2docx.textstage.parse import parse
    from md2docx.assemble.builder import build
    from md2docx.config import BehaviorFlags

    issues = IssueCollector()
    text, _source_meta = normalize(str(md_path), issues)
    cleaned = clean(text, issues, None)
    tokens = parse(cleaned, issues)

    flags = BehaviorFlags()
    if figures_dir is not None:
        flags = BehaviorFlags(figures_dir=str(figures_dir))

    options = _MinimalBuildOptions(str(md_path))
    doc = build(tokens, options, flags, issues)
    return doc, issues
