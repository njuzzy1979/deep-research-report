# -*- coding: utf-8 -*-
"""tests/test_outline_structure_gate.py —— D1-9 阶段4 结构完整性门禁测试。

覆盖 S1-S6 各自的红/绿用例、三态开关语义、以及"warn 不阻断 / strict 阻断"
这一 U6 裁决的核心行为。
"""
from __future__ import annotations

import pytest

import outline_structure_gate as gate


def _write(tmp_path, yaml_body: str, md_body: str = "") -> str:
    p = tmp_path / "outline.md"
    p.write_text(f"---\n{yaml_body}---\n{md_body}", encoding="utf-8")
    return str(p)


_GOOD_YAML = """struct_template: research
title: 测试报告
structure:
  frontmatter: []
  bodymatter:
    - chapter_no: 1
      chapter_title: 导论
      sections:
        - section_no: "1.1"
          section_title: 研究背景
        - section_no: "1.2"
          section_title: 研究目标
    - chapter_no: 2
      chapter_title: 方法
      sections:
        - section_no: "2.1"
          section_title: 数据来源
        - section_no: "2.2"
          section_title: 分析框架
  appendix: []
"""

_GOOD_MD = "## 第 1 章：导论\n\n## 第 2 章：方法\n"


def test_s1_s4_all_pass_on_compliant_outline(tmp_path):
    r = gate.run_structure_gate(_write(tmp_path, _GOOD_YAML, _GOOD_MD), "strict")
    assert r["s1_s4_passed"] is True
    assert r["passed"] is True
    for k in ("S1", "S2", "S3", "S4", "S5", "S6"):
        assert r["checks"][k]["passed"] is True, f"{k} 应通过: {r['checks'][k]}"


def test_s1_fails_when_bodymatter_empty(tmp_path):
    y = "structure:\n  bodymatter: []\n"
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["checks"]["S1"]["passed"] is False
    assert r["s1_s4_passed"] is False


def test_s2_fails_when_chapter_title_empty(tmp_path):
    y = (
        "structure:\n  bodymatter:\n"
        '    - chapter_no: 1\n      chapter_title: ""\n'
        "      sections:\n"
        '        - section_no: "1.1"\n          section_title: A\n'
        '        - section_no: "1.2"\n          section_title: B\n'
    )
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["checks"]["S2"]["passed"] is False


def test_s3_fails_on_real_world_empty_sections(tmp_path):
    """复刻真实事故形态：声明了章但 sections 全为空列表（实测 16/16）。"""
    y = (
        "structure:\n  bodymatter:\n"
        "    - chapter_no: 1\n      chapter_title: 导论\n      subsections: []\n"
    )
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["checks"]["S3"]["passed"] is False
    assert "只声明了 0 个节" in r["checks"]["S3"]["violations"][0]


def test_s3_fails_when_only_one_section(tmp_path):
    """阈值是 >=2 而非 >=1：只有 1 个节的章属"为过门禁而填一行"形态。"""
    y = (
        "structure:\n  bodymatter:\n"
        "    - chapter_no: 1\n      chapter_title: 导论\n"
        "      sections:\n"
        '        - section_no: "1.1"\n          section_title: 唯一节\n'
    )
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["checks"]["S3"]["passed"] is False


def test_s4_fails_when_section_fields_missing(tmp_path):
    y = (
        "structure:\n  bodymatter:\n"
        "    - chapter_no: 1\n      chapter_title: 导论\n"
        "      sections:\n"
        '        - section_no: "1.1"\n          section_title: A\n'
        '        - section_no: ""\n          section_title: ""\n'
    )
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["checks"]["S4"]["passed"] is False


def test_s5_warns_on_yaml_markdown_mismatch(tmp_path):
    r = gate.run_structure_gate(_write(tmp_path, _GOOD_YAML, "## 完全不同的标题\n"), "warn")
    assert r["checks"]["S5"]["passed"] is False
    # S5 是 WARNING 级，不影响 S1-S4 判定
    assert r["s1_s4_passed"] is True


def test_s6_warns_on_numbered_section_title(tmp_path):
    y = (
        "structure:\n  bodymatter:\n"
        "    - chapter_no: 1\n      chapter_title: 导论\n"
        "      sections:\n"
        '        - section_no: "1.1"\n          section_title: "1.1 研究背景"\n'
        '        - section_no: "1.2"\n          section_title: 研究目标\n'
    )
    r = gate.run_structure_gate(_write(tmp_path, y), "warn")
    assert r["checks"]["S6"]["passed"] is False


# ── 三态开关（U6 裁决的核心行为）─────────────────────────────


def test_warn_mode_does_not_block_even_when_s1_s4_fail(tmp_path):
    """U6 裁决：首版默认 warn，存量项目（16/16 空 section）不得被阻断。"""
    y = "structure:\n  bodymatter:\n    - chapter_no: 1\n      chapter_title: 导论\n      subsections: []\n"
    r = gate.run_structure_gate(_write(tmp_path, y), "warn")
    assert r["s1_s4_passed"] is False
    assert r["passed"] is True, "warn 模式必须不阻断"


def test_strict_mode_blocks_when_s1_s4_fail(tmp_path):
    y = "structure:\n  bodymatter:\n    - chapter_no: 1\n      chapter_title: 导论\n      subsections: []\n"
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["passed"] is False


def test_off_mode_skips_all_checks(tmp_path):
    r = gate.run_structure_gate(_write(tmp_path, "structure:\n  bodymatter: []\n"), "off")
    assert r["passed"] is True
    assert r["checks"] == {}


def test_strict_switch_criterion_is_objective_and_present(tmp_path):
    """U6 实施约束：切换 strict 的触发判据必须是客观可验证的，不能是空话。"""
    r = gate.run_structure_gate(_write(tmp_path, _GOOD_YAML, _GOOD_MD), "warn")
    crit = r["strict_switch_criterion"]
    assert str(gate.STRICT_SWITCH_CONSECUTIVE_PROJECTS) in crit
    assert "自然通过" in crit


# ── 旧键名兼容（依赖 D1-1 归一化）───────────────────────────


def test_legacy_key_names_are_normalized_before_checking(tmp_path):
    """门禁须在归一化后判定——否则旧键名 outline 会被误报为 S2 全违规。"""
    y = (
        "structure:\n  bodymatter:\n"
        '    - section_no: "1"\n      section_title: 导论\n'
        "      sections:\n"
        '        - section_no: "1.1"\n          section_title: A\n'
        '        - section_no: "1.2"\n          section_title: B\n'
    )
    r = gate.run_structure_gate(_write(tmp_path, y), "strict")
    assert r["checks"]["S2"]["passed"] is True, "旧键名 section_title 应被归一化为 chapter_title"
    assert r["s1_s4_passed"] is True


# ── 用法层面错误 ─────────────────────────────────────────────


def test_missing_outline_returns_error(tmp_path):
    r = gate.run_structure_gate(str(tmp_path / "nope.md"), "warn")
    assert "error" in r


def test_missing_structure_node_returns_error(tmp_path):
    p = tmp_path / "outline.md"
    p.write_text("---\ntitle: 无 structure 节点\n---\n正文", encoding="utf-8")
    r = gate.run_structure_gate(str(p), "warn")
    assert "error" in r
