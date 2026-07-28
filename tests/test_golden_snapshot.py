# -*- coding: utf-8 -*-
"""L2 快照回归测试：现有 8 份 fixture 的 contract_check.py **当前基线**输出快照。

用途：锁定后续批次不得意外改变既有 8 份 fixture（全部 H4=0、无 YAML structure
节点）上 ``scripts/contract_check.py --json`` 的校验输出——任何批次改动落地后
重跑本测试，若断言失败即说明该改动波及了这些既有路径，需要排查是否为预期。

历史说明（G1 交叉验证 D6 裁决更正）：本文件 docstring 曾自称是"对现有 8 份
fixture 建立改动前的行为快照"，用于证明 A1（outline_reader subsections 字段名
修复）是纯加法、不破坏既有行为。但实际这套快照落盘于 A3 改动完成**之后**——
8 份快照全部含 ``C10``/``C11`` 键即为证据，锁定的是改动**后**的行为，对
"A1/A3 是纯加法"这一命题没有证明力（"改动后快照 == 改动后重跑结果"是重言式）。
"纯加法"这一命题的独立验证请见 G1 交叉验证记录：用 ``git show
HEAD:scripts/contract_check.py`` 取改动前版本，对多份 fixture 做新旧对比，
确认除 C10/C11 外既有键逐字节不变。

快照对象：对每份 fixture 跑 ``scripts/contract_check.py --json``（部分
fixture 是分章草稿，用 --stage stage7 默认模式；alt-report 系列内容较完整，
用 --merged 模式，与人工验证时的调用方式一致），并从返回 JSON 中剔除不稳定
字段（``file`` 含绝对/相对路径，会随运行环境变化）后落盘。

重新生成快照：设置环境变量 ``UPDATE_GOLDEN=1`` 后重跑本测试文件，测试改为
"写盘并跳过断言"而非"断言 == 已存快照"。这是后续批次**有意**变更
contract_check.py 校验输出行为时更新快照基线的标准做法——**刷新前必须人工
核对 `git diff tests/golden/` 的每一处差异**，确认变化是本次改动的预期结果
而非意外副作用，再提交刷新后的快照文件，不得盲目刷新后不看 diff 就提交。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_CONTRACT_CHECK = _SCRIPTS_DIR / "contract_check.py"
_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

_ALT_SAMPLE_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "alt-sample"
_MD2DOCX_FIXTURES_DIR = _SCRIPTS_DIR / "md2docx" / "tests" / "test_fixtures"

# 不稳定字段：绝对/相对路径会随调用方式变化，快照前必须剔除。
# （contract_check.py 的输出中未发现时间戳/耗时字段，仅 "file" 一项不稳定。）
_UNSTABLE_TOP_LEVEL_KEYS = ("file",)

# 8 份现有 fixture：(fixture 名, 路径, 是否用 --merged)。
# alt-report / alt-report-cleaned 是完整合并稿（含摘要+多章+附录），用 --merged；
# md2docx/tests/test_fixtures/ 下 6 份是分章草稿风格样本，用默认 stage7 模式
# （不加 --merged，允许校验分章场景下的 C1 等规则）。
_FIXTURES: list[tuple[str, Path, bool]] = [
    ("alt-report", _ALT_SAMPLE_DIR / "alt-report.md", True),
    ("alt-report-cleaned", _ALT_SAMPLE_DIR / "alt-report-cleaned.md", True),
    ("minimal", _MD2DOCX_FIXTURES_DIR / "minimal.md", False),
    ("front-matter", _MD2DOCX_FIXTURES_DIR / "front-matter.md", False),
    ("multi-chapter", _MD2DOCX_FIXTURES_DIR / "multi-chapter.md", False),
    ("with-image", _MD2DOCX_FIXTURES_DIR / "with-image.md", False),
    ("with-table", _MD2DOCX_FIXTURES_DIR / "with-table.md", False),
    ("alt-topic-coffee", _MD2DOCX_FIXTURES_DIR / "alt-topic-coffee.md", False),
]

_UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"


def _run_contract_check(md_path: Path, merged: bool) -> dict:
    """调用 contract_check.py --json，返回规范化后的结果字典（已剔除不稳定字段）。"""
    cmd = [sys.executable, str(_CONTRACT_CHECK), str(md_path), "--json"]
    if merged:
        cmd.append("--merged")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )
    # contract_check.py 对不合约的输入以 exit 1 退出（非崩溃），JSON 仍写到 stdout。
    # exit 2 才代表文件不存在等硬性异常，此时不应尝试解析 JSON。
    assert result.returncode in (0, 1), (
        f"contract_check.py 对 {md_path} 异常退出 (code={result.returncode})\n"
        f"stderr: {result.stderr[-2000:]}"
    )
    data = json.loads(result.stdout)
    for key in _UNSTABLE_TOP_LEVEL_KEYS:
        data.pop(key, None)
    return data


@pytest.mark.parametrize("name,md_path,merged", _FIXTURES, ids=[f[0] for f in _FIXTURES])
def test_golden_snapshot(name: str, md_path: Path, merged: bool):
    """对单份既有 fixture 的 contract_check.py 输出做快照回归。

    UPDATE_GOLDEN=1 时：写盘刷新快照，不做断言（用于有意变更行为后更新基线）。
    默认：断言当前输出与已存快照逐字段一致。
    """
    assert md_path.exists(), f"fixture 不存在: {md_path}"

    actual = _run_contract_check(md_path, merged)
    golden_path = _GOLDEN_DIR / f"{name}.json"

    if _UPDATE_GOLDEN:
        _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"UPDATE_GOLDEN=1：已刷新快照 {golden_path}")

    assert golden_path.exists(), (
        f"快照文件不存在: {golden_path}。"
        f"首次建立基线请设置环境变量 UPDATE_GOLDEN=1 后重跑本测试。"
    )
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"{name} 的 contract_check.py 输出与快照不一致。\n"
        f"若这是本批次有意的行为变更，设置 UPDATE_GOLDEN=1 重新生成快照；\n"
        f"若发现于 A1 等修复落地后，说明该改动波及了既有 fixture 的行为，需排查。\n"
        f"实际: {json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True)[:2000]}\n"
        f"期望: {json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True)[:2000]}"
    )
