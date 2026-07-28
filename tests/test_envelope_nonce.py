# -*- coding: utf-8 -*-
"""输出信封 nonce 迁移回归测试（跨模型兼容性优化方案 §C5 / §九 V-4，第 6 批实施）。

覆盖方案 §十 Phase C 验收标准："nonce 与无 nonce 两种格式均能被提取正则正确处理"，
并重点覆盖审查层 Critical-5（``scripts/merge_drafts.py`` 的 B1 剥离步骤原用字面量
``startswith("[AGENT-OUTPUT-START]")`` 匹配，nonce 化后会漏剥离带 nonce 的新格式标记，
导致标记残留进入最终 Word 交付物）：

- ``contract_check.RE_ENVELOPE_MARKER`` 对带 nonce / 不带 nonce 两种格式均正确匹配
- 三重误匹配防护实测：nonce 非法字符（大写 hex / 非 hex）、长度越界（<6 或 >16）、
  非行首出现、缺 agent 名 —— 均不应被误判为“不可匹配”（注：contract_check.py 的
  RE_ENVELOPE_MARKER 语义是“检测残留”，不强制行首/agent 名，此处按其实际契约断言）
- ``output_envelope_check.ENVELOPE_MARKER_PATTERN`` 的三重防护（信封配对场景，
  行首 + agent 名后缀 + nonce 格式）
- ``merge_drafts.clean_draft``（B1 剥离）对带 nonce 与不带 nonce 两种标记均能剥离干净
  —— 这是 Critical-5 的回归防线，最重要的测试
- ``contract_check.py`` C5 检测对两种格式均能检出残留
- 向后兼容断言：对不含 nonce 的旧格式输入，C5 检测结果与改动前完全一致
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import contract_check
import merge_drafts
import output_envelope_check as oec

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONTRACT_CHECK = _PROJECT_ROOT / "scripts" / "contract_check.py"


# ---------------------------------------------------------------------------
# 1. contract_check.RE_ENVELOPE_MARKER —— 共享正则常量本体
# ---------------------------------------------------------------------------


def test_re_envelope_marker_matches_legacy_format_without_nonce():
    assert contract_check.RE_ENVELOPE_MARKER.search("[AGENT-OUTPUT-START] chapter_writer_agent")
    assert contract_check.RE_ENVELOPE_MARKER.search("[AGENT-OUTPUT-END] chapter_writer_agent")


def test_re_envelope_marker_matches_new_format_with_nonce():
    assert contract_check.RE_ENVELOPE_MARKER.search("[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent")
    assert contract_check.RE_ENVELOPE_MARKER.search("[AGENT-OUTPUT-END:a7f3c9d2] chapter_writer_agent")


def test_re_envelope_marker_matches_min_and_max_nonce_length():
    # 6 位（下界）与 16 位（上界）均应匹配
    assert contract_check.RE_ENVELOPE_MARKER.search("[AGENT-OUTPUT-START:abcdef] x")
    assert contract_check.RE_ENVELOPE_MARKER.search("[AGENT-OUTPUT-START:0123456789abcdef] x")


# ---------------------------------------------------------------------------
# 2. 误匹配防护（output_envelope_check.ENVELOPE_MARKER_PATTERN —— 信封配对场景，
#    三重约束：行首 + agent 名后缀 + nonce 十六进制格式）
# ---------------------------------------------------------------------------


def test_nonce_uppercase_hex_not_matched_as_nonce_group():
    """大写十六进制不符合 [0-9a-f]{6,16} —— nonce 分组应捕获不到，整体按“无 nonce”回退失败。"""
    text = "[AGENT-OUTPUT-START:A7F3C9D2] chapter_writer_agent\n正文\n[AGENT-OUTPUT-END:A7F3C9D2] chapter_writer_agent\n"
    markers = oec._parse_markers(text)
    # 正则中 nonce 分组要求 [0-9a-f]{6,16}，大写不满足；此时整体标记形态退化匹配
    # 为 START 后紧跟 ":A7F3C9D2"，不在 nonce 捕获组内，agent 名捕获也会异常。
    # 断言：不会得到一个"nonce == 'A7F3C9D2'"的匹配（防止大写被误当作合法 nonce）。
    for m in markers:
        assert m["nonce"] != "A7F3C9D2"


def test_nonce_non_hex_chars_not_matched():
    text = "[AGENT-OUTPUT-START:zzzzzz] chapter_writer_agent\n正文\n[AGENT-OUTPUT-END:zzzzzz] chapter_writer_agent\n"
    markers = oec._parse_markers(text)
    for m in markers:
        assert m["nonce"] != "zzzzzz"


def test_nonce_too_short_not_matched():
    """5 位十六进制（< 6 位下界）不应被识别为合法 nonce。"""
    text = "[AGENT-OUTPUT-START:abcde] chapter_writer_agent\n正文\n[AGENT-OUTPUT-END:abcde] chapter_writer_agent\n"
    markers = oec._parse_markers(text)
    for m in markers:
        assert m["nonce"] != "abcde"


def test_nonce_too_long_not_matched():
    """17 位十六进制（> 16 位上界）不应被识别为合法 nonce。"""
    text = (
        "[AGENT-OUTPUT-START:0123456789abcdef0] chapter_writer_agent\n正文\n"
        "[AGENT-OUTPUT-END:0123456789abcdef0] chapter_writer_agent\n"
    )
    markers = oec._parse_markers(text)
    for m in markers:
        assert m["nonce"] != "0123456789abcdef0"


def test_marker_not_at_line_start_not_matched_by_envelope_pattern():
    """output_envelope_check 的信封配对正则要求行首（MULTILINE + ^ 锚定）——
    正文中间出现类似串不应被误当作真实标记。"""
    text = "这是一段正文，其中提到 [AGENT-OUTPUT-START:a7f3c9d2] 这个词但不在行首。\n"
    markers = oec._parse_markers(text)
    assert markers == []


def test_marker_missing_agent_name_treated_as_suspicious():
    """孤立的 `[AGENT-OUTPUT-START:xxx]`（无 agent 名后缀）应被判为不匹配期望 agent。"""
    text = "[AGENT-OUTPUT-START:a7f3c9d2]\n正文\n[AGENT-OUTPUT-END:a7f3c9d2]\n"
    r = oec.check_envelope(text, "chapter_writer_agent", expected_nonce=None)
    assert r["agent_matched"] is False


# ---------------------------------------------------------------------------
# 3. merge_drafts.clean_draft —— Critical-5 回归防线（最重要）
# ---------------------------------------------------------------------------


def test_merge_drafts_strips_legacy_marker_without_nonce():
    text = (
        "[AGENT-OUTPUT-START] chapter_writer_agent\n"
        "## 第一节 正文标题\n"
        "正文内容。\n"
        "[AGENT-OUTPUT-END] chapter_writer_agent\n"
    )
    cleaned, report = merge_drafts.clean_draft(text)
    assert "AGENT-OUTPUT" not in cleaned
    assert any("B1-剥离标记" in r for r in report)


def test_merge_drafts_strips_new_marker_with_nonce():
    """Critical-5 核心断言：带 nonce 的新格式标记必须能被剥离，否则标记残留进 Word。"""
    text = (
        "[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent\n"
        "## 第一节 正文标题\n"
        "正文内容。\n"
        "[AGENT-OUTPUT-END:a7f3c9d2] chapter_writer_agent\n"
    )
    cleaned, report = merge_drafts.clean_draft(text)
    assert "AGENT-OUTPUT" not in cleaned
    assert any("B1-剥离标记" in r for r in report)


def test_merge_drafts_strips_both_marker_formats_in_same_draft():
    """同一份草稿中正文标记不带 nonce、自声明标记带 nonce（或反之）的混合场景，
    两种格式都必须被剥离干净——不能因为改用共享常量后只认一种格式。"""
    text = (
        "[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent\n"
        "## 第一节 正文标题\n"
        "正文内容。\n"
        "[AGENT-OUTPUT-END:a7f3c9d2] chapter_writer_agent\n"
        "[AGENT-OUTPUT-START] chapter_writer_agent_selfclaim\n"
        "### 写作者自声明（第 1 章）\n"
        "- 本章字数（估）：约 800 字\n"
        "[AGENT-OUTPUT-END] chapter_writer_agent_selfclaim\n"
    )
    cleaned, report = merge_drafts.clean_draft(text)
    assert "AGENT-OUTPUT" not in cleaned
    strip_count = sum(1 for r in report if "B1-剥离标记" in r)
    assert strip_count == 4  # 两对标记，共 4 行


def test_merge_drafts_uses_shared_regex_constant_from_contract_check():
    """确认 merge_drafts 确实 import 了 contract_check 的共享常量（而非自行重复定义
    一份不同步的正则）——这是方案要求的"共享正则常量"设计意图的直接验证。"""
    assert merge_drafts.RE_ENVELOPE_MARKER is contract_check.RE_ENVELOPE_MARKER


# ---------------------------------------------------------------------------
# 4. contract_check.py C5 检测 —— 两种格式均能检出残留
# ---------------------------------------------------------------------------


def _run_contract_check_json(md_path: Path, extra_args: list[str] | None = None) -> dict:
    cmd = [sys.executable, str(_CONTRACT_CHECK), str(md_path), "--json"]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return json.loads(result.stdout)


def test_contract_check_c5_detects_legacy_marker_residue(tmp_path):
    md = tmp_path / "ch01.md"
    md.write_text(
        "## 第一节 正文标题\n正文内容。\n[AGENT-OUTPUT-START] chapter_writer_agent\n",
        encoding="utf-8",
    )
    result = _run_contract_check_json(md)
    c5 = result["contract"]["C5_banned"]
    assert c5["pass"] is False
    assert "输出隔离标记残留" in c5["hits"]


def test_contract_check_c5_detects_nonce_marker_residue(tmp_path):
    md = tmp_path / "ch01.md"
    md.write_text(
        "## 第一节 正文标题\n正文内容。\n[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent\n",
        encoding="utf-8",
    )
    result = _run_contract_check_json(md)
    c5 = result["contract"]["C5_banned"]
    assert c5["pass"] is False
    assert "输出隔离标记残留" in c5["hits"]


def test_contract_check_c5_clean_when_no_marker_present(tmp_path):
    md = tmp_path / "ch01.md"
    md.write_text("## 第一节 正文标题\n正文内容，无任何标记残留。\n", encoding="utf-8")
    result = _run_contract_check_json(md)
    c5 = result["contract"]["C5_banned"]
    assert c5["pass"] is True


# ---------------------------------------------------------------------------
# 5. 向后兼容断言：不含 nonce 的旧格式输入，C5 结果与改动前完全一致
# ---------------------------------------------------------------------------


def test_c5_banned_patterns_backward_compatible_for_legacy_format():
    """放宽后的 RE_ENVELOPE_MARKER 对不含 nonce 的旧格式匹配行为，与放宽前的
    `re.compile(r"\\[AGENT-OUTPUT-(?:START|END)\\]")` 逐字节一致 —— 用旧正则对照验证。"""
    import re

    legacy_pattern = re.compile(r"\[AGENT-OUTPUT-(?:START|END)\]")
    samples = [
        "[AGENT-OUTPUT-START] chapter_writer_agent",
        "[AGENT-OUTPUT-END] chapter_writer_agent",
        "正文中不含任何标记。",
        "half [AGENT-OUTPUT-STAR] broken",
    ]
    for s in samples:
        old_hit = bool(legacy_pattern.search(s))
        new_hit = bool(contract_check.RE_ENVELOPE_MARKER.search(s))
        assert old_hit == new_hit, f"旧格式输入 {s!r} 上新旧正则命中结果不一致"


def test_c5_new_regex_additionally_matches_nonce_format_only():
    """新正则相对旧正则的唯一差异应是"额外能匹配带 nonce 格式"，不改变旧格式判定。"""
    import re

    legacy_pattern = re.compile(r"\[AGENT-OUTPUT-(?:START|END)\]")
    nonce_sample = "[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent"
    assert not legacy_pattern.search(nonce_sample)  # 旧正则匹配不到
    assert contract_check.RE_ENVELOPE_MARKER.search(nonce_sample)  # 新正则能匹配到
