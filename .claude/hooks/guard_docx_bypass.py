#!/usr/bin/env python3
"""PreToolUse hook：拦截绕过 md2docx 直写 docx / 修改 skill 脚本本体（D2-9）。

来源 skill：deep-research-report
来源版本：随 skill 版本管理；本文件是**下发到项目工作空间的副本**，不是权威源。
权威源位于 ``<skill_root>/.claude/hooks/guard_docx_bypass.py``。

--------------------------------------------------------------------------
作用域隔离机制
--------------------------------------------------------------------------
本 hook 依赖 Claude Code **自带的作用域规则**实现隔离，而不是靠 matcher 表达式：
项目级 ``.claude/settings.json`` 只在该项目目录被打开为工作区时加载生效
（用户级 ``~/.claude/settings.json`` 才全局生效）。因此把配置写成项目级文件，
天然只在这一个工作空间生效，**不影响其他项目、其他 skill**。

--------------------------------------------------------------------------
两条规则（合并为同一份脚本：裁决动作相同、共用同一次下发时机，避免两处副本漂移）
--------------------------------------------------------------------------
规则一（原 U1）：禁止绕过 md2docx 直写 docx
    命中条件（三者同时成立）：
      目标路径在 output_dir 下、扩展名 .docx
      命令/内容含 python-docx 特征（from docx import / Document(）
      且**不含** md2docx 引用
    → deny

规则二（原 U2）：禁止在报告编写会话中修改 skill 脚本本体
    命中条件：目标路径落在 <skill_root>/scripts|agents|references/** 内
    → deny

--------------------------------------------------------------------------
【合法调用正样本】—— 供误伤率测试使用，不得当作违规样本
--------------------------------------------------------------------------
1. ``scripts/outline_skeleton.py``（D1-8 骨架 docx 生成）：**只合成 Markdown，
   docx 一律交给 `python -m md2docx`，绝不自行 `from docx import Document`**。
   两条独立的不命中路径：① 骨架落 ``research/`` 不在 output_dir 下；
   ② 命令含 md2docx 引用。任一条即足以排除误伤。
2. ``python -m md2docx <in.md> <out.docx>``：这是**唯一合法**的 docx 生成路径。
3. ``scripts/finalize_pipeline.py`` 的 ``verify_docx_structure()`` 内部
   ``from docx import Document`` 用于**回读校验**（只读，不生成），且它是
   skill 脚本自身而非报告编写会话的临时代码。

注：``outline_skeleton.py`` / ``outline_structure_gate.py`` 是**新增** skill
脚本，落在规则二黑名单 ``<skill_root>/scripts/**`` 内。规则二禁止的是"在**报告
编写会话**中修改 skill 脚本本体"，而新增这些脚本属于**实施优化方案时**的 skill
开发行为，不在报告编写会话内，**不受规则二约束**。此处记录以免混淆。

--------------------------------------------------------------------------
【必须诚实标注的局限】
--------------------------------------------------------------------------
1. **递归漏洞（未闭环）**：orchestrator 在报告编写会话中拥有对
   ``project_root/.claude/settings.json`` 的 Write/Edit 权限，理论上可直接编辑
   该文件删掉 hooks 段以绕过规则一、二本身。要堵住需把
   ``project_root/.claude/**`` 也加进规则二黑名单，但那会连带挡住用户手动调整
   项目 hooks 配置的正常需求——**需用户显式确认后才启用**，故本版默认不含该层。
2. **下发时机盲区**：分发挂在阶段 1.2；"半路接手"的会话（跳过阶段 1、直接从
   已有草稿进入阶段 7-9，正是本次事故的实际形态之一）不会被下发。故阶段 9
   入口补一次幂等检测（见 ``ensure_hooks_installed``）。
3. **规则一是文本模式匹配**，无法识别"合法但间接"的调用路径（如脚本先 import
   自己封装的中间模块、内部才调用 python-docx）。上线前需用两类样本做误伤率
   测试，不能假设一次写对。
4. 规则二**不是文件系统级只读保护**——真正生效的是这条 PreToolUse deny，
   而非操作系统权限位。

退出码约定（Claude Code PreToolUse hook）：0 = 放行；2 = deny（stderr 为原因）。
"""
from __future__ import annotations

import json
import os
import re
import sys

# python-docx 直接调用特征
_RE_PYTHON_DOCX = re.compile(
    r"from\s+docx\s+import|import\s+docx\b|docx\.Document\s*\(|(?<![\w.])Document\s*\("
)
# md2docx 引用（合法路径标识）
_RE_MD2DOCX = re.compile(r"md2docx")

# 规则二黑名单：skill 脚本/契约文件本体
_SKILL_PROTECTED_SUBDIRS = ("scripts", "agents", "references")

_DENY_RULE_1 = (
    "docx 生成须经 finalize_pipeline.py → md2docx，禁止直接调用 python-docx。\n"
    "唯一合法路径：python -m md2docx <input.md> <output.docx> [--cover cover.md]\n"
    "若管线报错，请读 JSON 的 failure_step 并查 agents/finalizer_agent.md 的"
    "固定路由表；路由表给不出有效动作时停机呈报用户，不要自行编写替代实现。"
)
_DENY_RULE_2 = (
    "skill 脚本本体不可在报告编写会话中修改，如需调整请在 skill 开发场景下进行。\n"
    "命中的是 <skill_root>/scripts|agents|references/** 路径黑名单。"
)


def _norm(p: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(p))
    except Exception:
        return (p or "").lower()


def _extract_targets(payload: dict) -> tuple:
    """从 hook payload 中取出（目标路径, 命令/内容文本）。"""
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or ""
    text_parts = [
        str(ti.get("command") or ""),
        str(ti.get("content") or ""),
        str(ti.get("new_string") or ""),
    ]
    return str(path), "\n".join(tp for tp in text_parts if tp)


def check_rule_1(path: str, text: str, output_dir: str | None) -> str | None:
    """规则一：目标在 output_dir 下的 .docx + 含 python-docx 特征 + 不含 md2docx。"""
    blob = f"{path}\n{text}"
    if not _RE_PYTHON_DOCX.search(blob):
        return None
    if _RE_MD2DOCX.search(blob):
        return None  # 合法路径（含骨架生成器的 python -m md2docx 调用）

    # 判定"是否指向 output_dir 下的 .docx"：路径参数或命令文本中出现均算
    docx_refs = [path] if path.lower().endswith(".docx") else []
    docx_refs += re.findall(r"[^\s\"']+\.docx", text)
    if not docx_refs:
        return None
    if output_dir:
        od = _norm(output_dir)
        if not any(_norm(d).startswith(od) for d in docx_refs):
            return None
    return _DENY_RULE_1


def check_rule_2(path: str, skill_root: str | None) -> str | None:
    """规则二：目标落在 skill 的 scripts/agents/references 内。"""
    if not path or not skill_root:
        return None
    target = _norm(path)
    for sub in _SKILL_PROTECTED_SUBDIRS:
        protected = _norm(os.path.join(skill_root, sub))
        if target.startswith(protected + os.sep) or target == protected:
            return _DENY_RULE_2
    return None


def evaluate(payload: dict) -> str | None:
    """返回 deny 原因；None 表示放行。"""
    path, text = _extract_targets(payload)
    skill_root = os.environ.get("DRR_SKILL_ROOT")
    output_dir = os.environ.get("DRR_OUTPUT_DIR") or os.path.join(os.getcwd(), "output")

    reason = check_rule_2(path, skill_root)
    if reason:
        return reason
    return check_rule_1(path, text, output_dir)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # 读不到 payload 时放行，不阻断正常工作

    reason = evaluate(payload if isinstance(payload, dict) else {})
    if reason:
        print(f"[deep-research-report guard] {reason}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
