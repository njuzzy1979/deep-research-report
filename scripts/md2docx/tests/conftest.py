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
