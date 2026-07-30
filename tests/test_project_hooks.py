# -*- coding: utf-8 -*-
"""tests/test_project_hooks.py —— D2-9 hook 判断逻辑 + 下发机制测试。

含 §5.4 第 5 条明确要求的**误伤率测试**：用一批合法与违规两类样本用例验证
规则一，不假设规则一次写对。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import install_project_hooks as iph

_HOOK_PATH = Path(iph.__file__).resolve().parent.parent / ".claude" / "hooks" / "guard_docx_bypass.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("guard_docx_bypass", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load_hook()


def _payload(tool="Bash", **ti):
    return {"tool_name": tool, "tool_input": ti}


# ── 规则一：违规样本（必须 deny）─────────────────────────────


@pytest.mark.parametrize("cmd", [
    'python -c "from docx import Document; d=Document(); d.save(\'output/r.docx\')"',
    'python gen.py  # 内含 import docx，输出 output/report.docx',
    'python -c "import docx; docx.Document().save(\'output/x.docx\')"',
])
def test_rule1_denies_python_docx_writing_to_output(cmd, tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    # 命令文本中的相对路径需落在 output_dir 下才命中；用绝对路径构造等价场景
    cmd_abs = cmd.replace("output/", str(tmp_path / "output") + "/")
    reason = guard.evaluate(_payload(command=cmd_abs))
    assert reason is not None, f"违规样本未被拦截: {cmd_abs}"
    assert "md2docx" in reason


def test_rule1_denies_write_tool_creating_docx_via_python_docx(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    p = tmp_path / "output" / "gen_report.py"
    reason = guard.evaluate(_payload(
        tool="Write", file_path=str(p),
        content=f"from docx import Document\nd=Document()\nd.save(r'{tmp_path}/output/a.docx')\n",
    ))
    assert reason is not None


# ── 规则一：合法样本（必须放行——误伤率测试的核心）───────────


def test_rule1_allows_md2docx_invocation(tmp_path, monkeypatch):
    """唯一合法的 docx 生成路径。"""
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    cmd = f'python -m md2docx research/drafts/final-report.md "{tmp_path}/output/r.docx" --cover research/cover.md'
    assert guard.evaluate(_payload(command=cmd)) is None


def test_rule1_allows_outline_skeleton_generator(tmp_path, monkeypatch):
    """【登记在案的合法调用正样本】D1-8 骨架生成器。

    两条独立的不命中路径：① 骨架落 research/ 不在 output_dir 下；
    ② 命令含 md2docx 引用。任一条即足以排除误伤。
    """
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    cmd = "python scripts/outline_skeleton.py --outline research/outline.md --cover research/cover.md"
    assert guard.evaluate(_payload(command=cmd)) is None
    # 骨架内部实际执行的 md2docx 调用同样放行
    inner = f'python -m md2docx research/drafts/.outline-skeleton.md research/outline-skeleton-preview.docx'
    assert guard.evaluate(_payload(command=inner)) is None


def test_rule1_allows_python_docx_readback_outside_output_dir(tmp_path, monkeypatch):
    """D2-7 的回读校验：python-docx 只读、且目标不在 output_dir 下时不误伤。"""
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    cmd = f'python -c "from docx import Document; d=Document(r\'{tmp_path}/research/skel.docx\'); print(len(d.paragraphs))"'
    assert guard.evaluate(_payload(command=cmd)) is None


def test_rule1_allows_unrelated_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    for cmd in [
        "python scripts/finalize_pipeline.py --drafts-dir research/drafts --json",
        "python scripts/figure_gate.py --outline research/outline.md",
        "git status",
    ]:
        assert guard.evaluate(_payload(command=cmd)) is None, cmd


def test_rule1_does_not_fire_without_docx_target(tmp_path, monkeypatch):
    """含 python-docx 特征但不写 .docx（如读 docx 做统计）不应命中。"""
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    assert guard.evaluate(_payload(command='python -c "from docx import Document; print(1)"')) is None


# ── 规则二：skill 脚本本体路径黑名单 ────────────────────────


@pytest.mark.parametrize("sub", ["scripts", "agents", "references"])
def test_rule2_denies_editing_skill_body(sub, tmp_path, monkeypatch):
    skill = tmp_path / "skill"
    monkeypatch.setenv("DRR_SKILL_ROOT", str(skill))
    target = skill / sub / "some_file.py"
    reason = guard.evaluate(_payload(tool="Edit", file_path=str(target), new_string="x"))
    assert reason is not None
    assert "skill 脚本本体" in reason


def test_rule2_allows_editing_project_workspace_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_SKILL_ROOT", str(tmp_path / "skill"))
    target = tmp_path / "project" / "research" / "drafts" / "ch01.md"
    assert guard.evaluate(_payload(tool="Edit", file_path=str(target), new_string="正文")) is None


def test_rule2_inactive_when_skill_root_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("DRR_SKILL_ROOT", raising=False)
    monkeypatch.setenv("DRR_OUTPUT_DIR", str(tmp_path / "output"))
    target = tmp_path / "skill" / "scripts" / "x.py"
    assert guard.evaluate(_payload(tool="Edit", file_path=str(target), new_string="x")) is None


# ── 下发机制：合并语义而非覆盖（§5.4 第 4 条）────────────────


def test_install_creates_settings_when_absent(tmp_path):
    r = iph.install(str(tmp_path))
    assert r["passed"] is True and r["action"] == "created"
    assert (tmp_path / ".claude" / "hooks" / "guard_docx_bypass.py").exists()
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "PreToolUse" in data["hooks"]


def test_install_merges_without_clobbering_user_config(tmp_path):
    """**严禁整文件覆盖**——用户已有的其他 hooks 与配置项必须保留。"""
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text(json.dumps({
        "env": {"MY_VAR": "keep-me"},
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": "echo user-own-hook"}]}],
            "PostToolUse": [{"matcher": "Write", "hooks": [
                {"type": "command", "command": "echo user-post"}]}],
        },
    }, ensure_ascii=False), encoding="utf-8")

    r = iph.install(str(tmp_path))
    assert r["action"] == "merged_into_existing"
    data = json.loads((cdir / "settings.json").read_text(encoding="utf-8"))
    assert data["env"]["MY_VAR"] == "keep-me", "用户自定义配置项被清除"
    cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("user-own-hook" in c for c in cmds), "用户已有 PreToolUse hook 被清除"
    assert any("guard_docx_bypass" in c for c in cmds), "本 skill 的 hook 未追加"
    assert "PostToolUse" in data["hooks"], "用户的 PostToolUse 段被清除"


def test_install_is_idempotent(tmp_path):
    iph.install(str(tmp_path))
    r2 = iph.install(str(tmp_path))
    assert r2["action"] == "already_installed"
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert sum("guard_docx_bypass" in c for c in cmds) == 1, "重复下发产生了重复 hook 条目"


def test_install_refuses_to_overwrite_unparseable_settings(tmp_path):
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text("{ 这不是合法 JSON", encoding="utf-8")
    r = iph.install(str(tmp_path))
    assert r["passed"] is False
    assert "拒绝覆盖" in r["error"]
    # 原文件未被破坏
    assert "这不是合法 JSON" in (cdir / "settings.json").read_text(encoding="utf-8")


def test_is_installed_and_ensure_hooks_installed(tmp_path):
    """阶段 9 入口的幂等补下发（覆盖"半路接手"会话的下发盲区）。"""
    assert iph.is_installed(str(tmp_path)) is False
    r = iph.ensure_hooks_installed(str(tmp_path))
    assert r["passed"] is True
    assert iph.is_installed(str(tmp_path)) is True
    r2 = iph.ensure_hooks_installed(str(tmp_path))
    assert r2["action"] == "already_installed"


def test_hook_script_is_copied_not_referenced(tmp_path):
    """复制而非路径引用：skill 目录被移动/重装时已下发的 hook 不应静默失效。"""
    iph.install(str(tmp_path))
    dst = tmp_path / ".claude" / "hooks" / "guard_docx_bypass.py"
    assert dst.read_text(encoding="utf-8") == _HOOK_PATH.read_text(encoding="utf-8")
    settings = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "CLAUDE_PROJECT_DIR" in settings, "应引用项目内副本而非 skill 绝对路径"


def test_legitimate_samples_documented_in_hook_source():
    """§9.4.5/§5.6 要求把合法调用正样本写进 hook 脚本注释，供误伤率测试引用。"""
    src = _HOOK_PATH.read_text(encoding="utf-8")
    assert "合法调用正样本" in src
    assert "outline_skeleton" in src
    assert "递归漏洞" in src, "必须诚实标注未闭环的递归漏洞"
