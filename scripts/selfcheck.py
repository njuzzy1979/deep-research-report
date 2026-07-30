#!/usr/bin/env python3
"""一键自检入口（D3 §7.5）。

覆盖**两套**测试目录——``tests/`` 与 ``scripts/md2docx/tests/``。此前没有单一
入口，实施者容易只跑其中一套就宣布通过。

分级：

  ``--level quick``  只跑 ``tests/``（约数秒，日常改动自查）
  ``--level full``   两套测试全跑 + 关键脚本的可执行性冒烟（默认）

冒烟项存在的理由：``model_profile.py`` 的"基本用法必崩"（`format_text_report`
函数定义头丢失导致 NameError）**至今未被任何测试发现**，因为文档教用户执行的是
``--json`` 分支、而 orchestrator 走的是另一条路径。纯 pytest 覆盖不到"脚本能否
被当作命令行工具正常调用"这一层，故显式补一组无参/基本用法冒烟。

用法::

    python scripts/selfcheck.py --level full
    python scripts/selfcheck.py --level quick --json

退出码：0 = 全部通过；1 = 存在失败项。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

OK = "[OK]"
FAIL = "[FAIL]"

_SKILL_ROOT = Path(__file__).resolve().parent.parent

# 两套测试目录（此前无单一入口，容易只跑一套就宣布通过）
_TEST_SUITES = (
    ("tests", "tests"),
    ("md2docx-tests", "scripts/md2docx/tests"),
)

# 关键脚本的命令行可执行性冒烟——pytest 覆盖不到这一层
_SMOKE_COMMANDS = (
    ("model_profile 基本用法", ["scripts/model_profile.py"]),
    ("model_profile --json", ["scripts/model_profile.py", "--json"]),
    ("outline_structure_gate --help", ["scripts/outline_structure_gate.py", "--help"]),
    ("outline_skeleton --help", ["scripts/outline_skeleton.py", "--help"]),
    ("finalize_pipeline --help", ["scripts/finalize_pipeline.py", "--help"]),
    ("figure_gate --help", ["scripts/figure_gate.py", "--help"]),
    ("delivery_checklist_check --help", ["scripts/delivery_checklist_check.py", "--help"]),
    ("install_project_hooks --help", ["scripts/install_project_hooks.py", "--help"]),
)


def _run(cmd: list, cwd: Path) -> tuple:
    proc = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_selfcheck(level: str = "full") -> dict:
    result: dict = {"level": level, "suites": {}, "smoke": {}, "passed": False}

    suites = _TEST_SUITES if level == "full" else _TEST_SUITES[:1]
    for name, rel in suites:
        code, out = _run([sys.executable, "-m", "pytest", rel, "-q"], _SKILL_ROOT)
        tail = [ln for ln in out.strip().split("\n") if ln.strip()][-1:] or [""]
        result["suites"][name] = {
            "path": rel, "exit": code, "passed": code == 0, "summary": tail[0][:200],
        }

    if level == "full":
        for name, argv in _SMOKE_COMMANDS:
            code, out = _run([sys.executable] + argv, _SKILL_ROOT)
            result["smoke"][name] = {
                "exit": code, "passed": code == 0,
                "detail": "" if code == 0 else out.strip()[-300:],
            }

    result["passed"] = (
        all(v["passed"] for v in result["suites"].values())
        and all(v["passed"] for v in result["smoke"].values())
    )
    return result


def format_text_report(result: dict) -> str:
    lines = [f"=== deep-research-report 一键自检（level={result['level']}）===", ""]
    lines.append("测试套件：")
    for name, info in result["suites"].items():
        mark = OK if info["passed"] else FAIL
        lines.append(f"  {mark} {name} ({info['path']}): {info['summary']}")
    if result["smoke"]:
        lines.append("")
        lines.append("脚本可执行性冒烟：")
        for name, info in result["smoke"].items():
            mark = OK if info["passed"] else FAIL
            lines.append(f"  {mark} {name}")
            if not info["passed"]:
                lines.append(f"        {info['detail']}")
    lines.append("")
    lines.append(f"=== 总判定: {'PASS' if result['passed'] else 'FAIL'} ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="一键自检：两套测试 + 关键脚本冒烟")
    parser.add_argument(
        "--level", choices=("quick", "full"), default="full",
        help="quick 只跑 tests/；full 两套测试全跑 + 脚本冒烟（默认）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    result = run_selfcheck(args.level)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
