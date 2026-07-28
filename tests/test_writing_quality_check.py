# -*- coding: utf-8 -*-
"""tests/test_writing_quality_check.py —— Phase E (E1-E4) 单元测试。

覆盖：
  E1 数据点计数正确性 + "连续 500 字无数据点"定位
  E2 章间过渡缺失检出 / 存在且 >=2 句判通过 / 过渡块格式与 writing-standards.md
     标准 18 规范逐字一致 / 节间过渡缺失检出
  E3 黑名单习语检出 / 正常正文零误报
  E4 缩写首次出现有释义通过 / 无释义告警 / 白名单（NASA/API 等）不告警 /
     glossary aliases 生效
  非阻塞语义：E1-E4 全部命中时 exit code 仍为 0（只有读取失败才非 0）
"""
from __future__ import annotations

import json
import sys

import pytest

import writing_quality_check as wq


# ── E1：信息密度 ──────────────────────────────────────────────

def test_e1_count_data_points_numbers_and_citations():
    # 数字（含百分比）+ 引用编号 [N]，去重不重复计数括号内数字
    p = "2024年销量增长35%，同比提升明显[1]，另据统计[2,3]共12家企业参与。"
    assert wq.count_data_points(p) > 0
    # 引用编号 [1] 不应被数字模式重复计数（括号内的 1 已被 citation 正则吃掉）
    only_citation = "详见文献[1]。"
    assert wq.count_data_points(only_citation) == 1


def test_e1_count_data_points_zero_for_pure_prose():
    p = "这是一段纯粹的论述性文字，不包含任何数字或引用标记。"
    assert wq.count_data_points(p) == 0


def test_e1_continuous_no_data_violation_located():
    """连续 500 字无数据点的运行应被定位到具体段落，且只报告一次。"""
    sentence = (
        "这是一段没有任何数字或引用编号的纯论述文字用来测试密度检查逻辑"
        "是否正确工作它包含足够多的汉字字符以便累积超过阈值。"
    )
    # 每段 57 个中文字符，10 段 = 570 字，超过 500 字阈值
    text = "\n\n".join([sentence] * 10)
    result = wq.check_density(text)
    assert result["total_data_points"] == 0
    assert len(result["continuous_no_data_violations"]) == 1
    violation = result["continuous_no_data_violations"][0]
    assert violation["running_no_data_chars"] >= 500
    assert "paragraph_index" in violation


def test_e1_no_violation_when_data_points_reset_counter():
    """段落中出现数据点应重置连续无数据点计数器。"""
    sentence_no_data = "这是一段没有任何数字的纯论述文字用来测试密度检查逻辑是否正确工作。"
    sentence_with_data = "本段包含一个数据点[1]。"
    text = "\n\n".join([sentence_no_data] * 3 + [sentence_with_data] + [sentence_no_data] * 3)
    result = wq.check_density(text)
    # 每段落之间被数据点重置，不应触发 500 字阈值
    assert len(result["continuous_no_data_violations"]) == 0


def test_e1_below_min_density_flagged_when_sparse():
    # 全文有正文字数但零数据点 → below_min_density True
    text = "这是一段完全没有数据支撑的论述性文字。" * 3
    result = wq.check_density(text)
    assert result["below_min_density"] is True


def test_e1_density_ok_when_dense_enough():
    text = "2024年销量增长35%[1]。市场规模达到1200亿元[2]。用户数突破500万[3]。"
    result = wq.check_density(text)
    assert result["below_min_density"] is False


# ── E2：章间/节间过渡存在性 ────────────────────────────────────

def test_e2_missing_chapter_transition_detected():
    text = """## 第一章 测试章节

本章正文内容，没有过渡块。

## 第二章 结束
"""
    result = wq.check_transitions(text)
    chapter_issues = [i for i in result["issues"] if i["level"] == "chapter"]
    assert any(i["issue"] == "missing_transition_block" for i in chapter_issues)


def test_e2_transition_block_format_matches_standard_18_exactly():
    """过渡块格式必须与 writing-standards.md 标准 18 规范逐字一致：
    `> **本章小结与过渡**：...` 引用块形式。"""
    text = """## 第一章 测试章节

正文内容。

> **本章小结与过渡**：本章介绍了基本情况，市场格局正在发生变化。下一章将深入分析驱动因素。

## 第二章 结束

正文。

> **本章小结与过渡**：本章总结完毕。
"""
    result = wq.check_transitions(text)
    chapter_issues = [i for i in result["issues"] if i["level"] == "chapter"]
    assert chapter_issues == []


def test_e2_transition_present_but_insufficient_sentences_flagged():
    """非最后一章过渡块存在但 <2 句应判定不足。"""
    text = """## 第一章 测试

正文。

> **本章小结与过渡**：只有一句话。

## 第二章 结束
"""
    result = wq.check_transitions(text)
    issues = [i for i in result["issues"] if i["level"] == "chapter" and i["chapter"] == "## 第一章"]
    assert any(i["issue"] == "insufficient_sentences" for i in issues)


def test_e2_last_chapter_only_needs_one_sentence():
    """最后一章只需 >=1 句本章小结，无需引出下一章。"""
    text = """## 第一章 结束章节

正文。

> **本章小结与过渡**：本章总结完毕，不再需要过渡到下一章。
"""
    result = wq.check_transitions(text)
    issues = [i for i in result["issues"] if i["level"] == "chapter"]
    assert issues == []


def test_e2_missing_section_transition_detected():
    """相邻 H3 节之间无任何文本（存在性代理）应检出缺失。"""
    text = """## 第一章 测试

### 第一节
### 第二节

内容B。

> **本章小结与过渡**：小结与过渡文字，字数足够长了。
"""
    result = wq.check_transitions(text)
    section_issues = [i for i in result["issues"] if i["level"] == "section"]
    assert len(section_issues) == 1
    assert "第一节" in section_issues[0]["between"]


def test_e2_section_transition_present_passes():
    text = """## 第一章 测试

### 第一节

内容A。

这是节间过渡文字，承上启下。

### 第二节

内容B。

> **本章小结与过渡**：小结与过渡文字，字数足够长了。
"""
    result = wq.check_transitions(text)
    section_issues = [i for i in result["issues"] if i["level"] == "section"]
    assert section_issues == []


# ── E3：后台泄露黑名单 ────────────────────────────────────────

def test_e3_blacklist_idioms_detected():
    text = (
        "A 级证据支撑充分，但 B 级证据仍需补充。证据强度评估显示信源分级机制运行良好。"
        "本报告采用严格标准不采用未经核实的传闻。尚未见独立信源证实这一说法。"
        "本次核验范围内未发现重大问题。"
    )
    result = wq.check_backstage_leak(text)
    assert result["total_hits"] > 0
    assert "证据强度" in result["hits"]
    assert "信源分级" in result["hits"]
    assert "尚未见独立信源" in result["hits"]
    assert "本次核验范围内" in result["hits"]


def test_e3_normal_body_zero_false_positive():
    text = (
        "2024年，全球新能源汽车市场持续增长，销量达到1200万辆，同比增长35%[1]。"
        "中国市场占据主导地位，龙头企业市占率超过40%。政策支持力度持续加大。"
    )
    result = wq.check_backstage_leak(text)
    assert result["hits"] == {}
    assert result["total_hits"] == 0


def test_e3_f7_f8_reuse_hits_counted():
    """E3 复用 contract_check 的 F7（信源分级前缀）/F8（claim_id 泄露）正则。"""
    text = "[A] 这是一条带信源分级前缀的行\n正文中残留了 [CM021] 这样的 claim_id 标记。"
    result = wq.check_backstage_leak(text)
    assert "信源分级前缀(F7复用)" in result["hits"] or "claim_id泄露(F8复用)" in result["hits"]


# ── E4：缩写展开检查 ──────────────────────────────────────────

def test_e4_abbreviation_with_nearby_explanation_passes():
    text = "CBTC（基于通信的列车控制系统）是当前主流技术路线，后续简称 CBTC。"
    result = wq.check_abbreviations(text)
    assert result["violations"] == []


def test_e4_abbreviation_without_explanation_warns():
    text = "本文首次提到 XYZW 这一缩写，全文未对其做任何展开说明。"
    result = wq.check_abbreviations(text)
    abbrs = [v["abbr"] for v in result["violations"]]
    assert "XYZW" in abbrs


def test_e4_generic_whitelist_skips_common_abbreviations():
    text = "本报告基于 GDP 增长数据展开分析，并参考 NASA 与 API 的公开资料。"
    result = wq.check_abbreviations(text)
    assert result["violations"] == []
    assert set(result["whitelist_skipped"]) >= {"GDP", "NASA", "API"}


def test_e4_glossary_aliases_whitelist_effective(tmp_path):
    glossary_content = """# 术语表

```yaml
glossary:
  - term_id: GL-001
    preferred_form: 空间认知智能
    aliases: ["SCI", "Space Cognitive Intelligence"]
    banned_forms: []
    definition: "测试用途"
    scope: "全文"
    category: "核心概念"
    source_card: "CARD-001"
```
"""
    glossary_path = tmp_path / "glossary.md"
    glossary_path.write_text(glossary_content, encoding="utf-8")

    text = "SCI 是本报告的核心概念，未在正文中进一步展开释义。"
    result = wq.check_abbreviations(text, glossary_path=str(glossary_path))
    assert "SCI" in result["whitelist_skipped"]
    assert result["violations"] == []


def test_e4_cbtc_boundary_case_appendix_only_explanation_still_warns():
    """真实边界案例：正文首次出现处未展开，仅附录给出释义 —— 应判定为告警
    （不能满足于"全文任意位置存在过释义"这种宽松判断）。"""
    text = """## 正文

国内企业成功开发出达到国际水平的 CBTC 系统。市场格局已发生变化。

## 附录A：术语对照表

| 缩写 | 全称 |
|------|------|
| CBTC | 基于通信的列车控制系统 |
"""
    result = wq.check_abbreviations(text)
    abbrs = [v["abbr"] for v in result["violations"]]
    assert "CBTC" in abbrs


# ── 非阻塞语义：exit code ────────────────────────────────────

def test_all_e1_e4_hit_still_exit_zero(tmp_path, monkeypatch, capsys):
    """构造一个 E1-E4 全部命中的样本，确认 exit code 仍为 0（非阻塞语义）。"""
    content = """## 第一章 测试

正文完全没有数据支撑，纯粹论述性文字，不包含任何数字或引用编号占据这一整段。

XYZW 是一个从未展开的缩写。A 级证据支撑充分，证据强度良好，信源分级清楚。

## 第二章 结束

正文。
"""
    f = tmp_path / "sample.md"
    f.write_text(content, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["writing_quality_check.py", str(f), "--json"])
    with pytest.raises(SystemExit) as exc_info:
        wq.main()
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["any_findings"] is True


def test_file_not_found_exits_2(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["writing_quality_check.py", "does-not-exist.md"])
    with pytest.raises(SystemExit) as exc_info:
        wq.main()
    assert exc_info.value.code == 2
