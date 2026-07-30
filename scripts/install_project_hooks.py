#!/usr/bin/env python3
"""把 PreToolUse hook 下发到**项目工作空间**（D2-9）。

裁决背景：不采用用户级全局配置，改为随 skill 阶段 1.2 向项目工作空间下发
``.claude/settings.json``，作用范围收窄到"每次写报告的工作空间"，不影响其他
项目/其他 skill。这利用的是 Claude Code **自带的作用域规则**（项目级
settings 只在该项目被打开为工作区时生效），不需要 hook 脚本自己判断"当前是不是
这个 skill"。

分发模式复用既有先例 ``model_profile.py:_write_local_override``——探测环境 →
生成本地配置文件 → 写入项目根，**已存在则跳过、不覆盖**。挂载点为阶段 1.2
"建立工作目录"，不新开流程节点。

**复制而非路径引用**：曾考虑让项目配置直接引用 skill 目录内脚本的绝对路径，
但若 skill 目录被移动/重装/多版本共存，已下发到各项目的 hook 会**静默失效且
无告警**。定案为复制脚本内容 + 文件头写入来源 skill 版本号，牺牲"skill 升级后
项目侧自动同步"的便利，换取路径稳定性。

**合并语义而非覆盖**（§5.4 第 4 条）：未来任何已有 ``.claude/settings.json``
（可能已含用户自定义的其他 hooks）的项目下发时，**必须做 JSON 层面的合并
（hooks 数组去重追加），严禁整文件覆盖**，否则会静默清除用户已有的项目配置。

用法::

    python scripts/install_project_hooks.py --project-root .
    python scripts/install_project_hooks.py --project-root . --check
    python scripts/install_project_hooks.py --project-root . --force

退出码：0 = 已就绪（新下发或已存在）；1 = ``--check`` 下检出未安装；
       2 = 用法/IO 错误。
"""
from __future__ import annotations

import argparse
import json
import shutil
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
WARN = "[WARN]"

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SRC_HOOK = _SKILL_ROOT / ".claude" / "hooks" / "guard_docx_bypass.py"
_SRC_FRAGMENT = _SKILL_ROOT / ".claude" / "hooks-template" / "settings.fragment.json"

# marker 字段用于幂等检测：阶段 9 入口据此判断是否需要补下发
HOOK_MARKER = "deep-research-report/guard_docx_bypass@v1"


def _has_marker(settings: dict) -> bool:
    pre = ((settings.get("hooks") or {}).get("PreToolUse") or [])
    for entry in pre:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks") or []:
            if isinstance(h, dict) and (
                h.get("_marker") == HOOK_MARKER or HOOK_MARKER in str(h.get("command", ""))
            ):
                return True
            if isinstance(h, dict) and "guard_docx_bypass" in str(h.get("command", "")):
                return True
    return False


def is_installed(project_root: str) -> bool:
    sp = Path(project_root) / ".claude" / "settings.json"
    if not sp.exists():
        return False
    try:
        return _has_marker(json.loads(sp.read_text(encoding="utf-8-sig")))
    except (ValueError, OSError):
        return False


def _merge_hooks(existing: dict, fragment: dict) -> tuple:
    """把 fragment 的 hooks 段**去重追加**进 existing，返回 (合并结果, 是否有变更)。

    严禁整文件覆盖：existing 可能已含用户自定义的其他 hooks/配置项。
    """
    merged = dict(existing)
    if _has_marker(merged):
        return merged, False

    hooks = dict(merged.get("hooks") or {})
    frag_hooks = (fragment.get("hooks") or {})
    for event, entries in frag_hooks.items():
        current = list(hooks.get(event) or [])
        for e in entries or []:
            current.append(e)
        hooks[event] = current
    merged["hooks"] = hooks
    return merged, True


def install(project_root: str, force: bool = False) -> dict:
    result: dict = {
        "project_root": str(Path(project_root).resolve()),
        "hook_script": None,
        "settings_file": None,
        "action": None,
        "warnings": [],
        "passed": False,
    }

    if not _SRC_HOOK.exists() or not _SRC_FRAGMENT.exists():
        result["error"] = (
            f"skill 侧源文件缺失: {_SRC_HOOK if not _SRC_HOOK.exists() else _SRC_FRAGMENT}"
        )
        return result

    proot = Path(project_root)
    if not proot.is_dir():
        result["error"] = f"项目根目录不存在: {project_root}"
        return result

    hooks_dir = proot / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    dst_hook = hooks_dir / _SRC_HOOK.name

    # 复制脚本副本（而非路径引用）——路径稳定性优先
    if dst_hook.exists() and not force:
        result["warnings"].append("hook 脚本副本已存在，跳过复制（--force 可强制更新）")
    else:
        shutil.copyfile(_SRC_HOOK, dst_hook)
    result["hook_script"] = str(dst_hook)

    settings_path = proot / ".claude" / "settings.json"
    result["settings_file"] = str(settings_path)
    fragment = json.loads(_SRC_FRAGMENT.read_text(encoding="utf-8-sig"))
    fragment.pop("_marker", None)
    fragment.pop("_note", None)

    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            result["error"] = (
                f"项目 .claude/settings.json 存在但 JSON 解析失败，"
                f"**拒绝覆盖**（避免清除用户已有配置）: {e}"
            )
            return result
        if not isinstance(existing, dict):
            result["error"] = "项目 .claude/settings.json 顶层不是对象，拒绝合并"
            return result
        merged, changed = _merge_hooks(existing, fragment)
        if not changed:
            result["action"] = "already_installed"
            result["passed"] = True
            return result
        settings_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result["action"] = "merged_into_existing"
    else:
        settings_path.write_text(
            json.dumps(fragment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result["action"] = "created"

    result["passed"] = True
    return result


def ensure_hooks_installed(project_root: str) -> dict:
    """阶段 9 入口的**幂等补下发**（§5.4 第 3 条：下发时机的覆盖盲区）。

    分发动作挂在阶段 1.2，若某次会话是"半路接手"（跳过阶段 1、直接从已有草稿
    进入阶段 7-9，正是本次事故的实际形态之一），hook 不会被下发、两条规则在该
    会话中不生效。故阶段 9 入口先检测 marker，缺失则补下发再继续。
    """
    if is_installed(project_root):
        return {"action": "already_installed", "passed": True,
                "project_root": str(Path(project_root).resolve())}
    return install(project_root)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把 PreToolUse hook 下发到项目工作空间（D2-9，JSON 合并不覆盖）"
    )
    parser.add_argument("--project-root", default=".", help="项目根目录（默认当前目录）")
    parser.add_argument(
        "--check", action="store_true",
        help="只检测是否已安装，不做任何写入（未安装时 exit 1）",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="强制更新 hook 脚本副本（skill 侧 hook 逻辑有重大更新时使用）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.check:
        installed = is_installed(args.project_root)
        out = {"installed": installed, "project_root": str(Path(args.project_root).resolve())}
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json
              else f"{OK if installed else WARN} hook {'已安装' if installed else '未安装'}")
        sys.exit(0 if installed else 1)

    result = install(args.project_root, args.force)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("error"):
            print(f"{FAIL} {result['error']}", file=sys.stderr)
        else:
            print(f"{OK} hook 下发完成（action={result['action']}）")
            print(f"      脚本: {result['hook_script']}")
            print(f"      配置: {result['settings_file']}")
            for w in result["warnings"]:
                print(f"{WARN} {w}")
            print("")
            print("⚠ 已知未闭环局限：orchestrator 对本项目 .claude/settings.json 有写权限，")
            print("  理论上可编辑该文件关掉 hooks 以绕过规则（递归漏洞）。要堵住需把")
            print("  project_root/.claude/** 也加进规则二黑名单，但会连带挡住用户手动")
            print("  调整项目 hooks 配置的正常需求，故默认不含该层。")
    sys.exit(0 if result["passed"] else 2)


if __name__ == "__main__":
    main()
