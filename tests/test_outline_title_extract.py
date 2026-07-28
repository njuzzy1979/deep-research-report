# -*- coding: utf-8 -*-
"""outline_title_extract.py 的单元测试（跨模型兼容性优化方案 §三 B2）。

覆盖方案验收标准明确要求的场景：
- 用 structured-sample fixture 验证标题树结构正确、层级正确（2章4节5小节）
- 标题不含编号前缀——专门构造 YAML 标题字段本身带编号前缀的样本，确认被剥离
- --chapter-no N 过滤生效
- YAML/Markdown 一致性告警：YAML 声明但正文缺失 → 告警
- 提取为空 → exit 1（非 0）

G1 交叉验证 D-1/D-2 回归（第 4 批 B2 回炉修复）：
- D-1a：--chapter-no 过滤下不应因整份正文扫描而产生 markdown_only 假阳性，
  但 yaml_only 方向（本章 YAML 声明但正文缺失）仍应生效
- D-1b：一致性告警不应影响 exit code（只有提取为空才 exit 1）
- D-2：一致性告警写入降级台账时 level 应为 "L-记录"（不是 "L-显著"）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import outline_title_extract as ote
from md2docx.assemble.outline_reader import extract_yaml_front_matter


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "structured-sample" / "structured-report.md"


@pytest.fixture(autouse=True)
def _isolate_degradation_log(tmp_path, monkeypatch):
    """自动隔离降级台账写入（沿用 test_output_envelope_check.py 同款模式）。

    本文件多个用例（一致性告警场景、structured-sample fixture 跑通、CLI 场景）
    会触发 run_extract() 内部的 record_degradation() 调用；若不隔离，每次跑
    pytest 都会真实追加到项目默认台账 research/.degradation-log.jsonl，
    污染工作区且干扰 CP6 交付门禁的真实判定。autouse=True 确保本文件内
    所有测试无需逐个手动设置即可生效。返回隔离后的台账路径，供需要读取
    台账内容断言 level 字段的测试（如 D-2 回归）使用。
    """
    log_path = tmp_path / "test-isolated-degradation-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(log_path))
    return log_path



def _load_fixture_structure():
    text = ote.read_outline_text(_FIXTURE)
    parsed, body = extract_yaml_front_matter(text, outline_path=str(_FIXTURE))
    assert parsed is not None
    return parsed["structure"], body


# ---------------------------------------------------------------------------
# 标题树结构正确性（structured-sample：2 章 4 节 5 小节 + 1 前置件 + 1 附录）
# ---------------------------------------------------------------------------


def test_structured_fixture_tree_shape():
    structure, body = _load_fixture_structure()
    result = ote.run_extract(structure, body, outline_path=str(_FIXTURE))

    assert result["empty"] is False
    assert result["consistency_warnings"] == []

    # 前置件：前言 + 2 节
    assert len(result["frontmatter"]) == 1
    assert result["frontmatter"][0]["chapter_title"] == "前言"
    assert result["frontmatter"][0]["sections"] == ["研究背景与意义", "研究范围界定"]

    # 正文：2 章
    assert len(result["chapters"]) == 2
    ch1, ch2 = result["chapters"]
    assert ch1["chapter_no"] == 1
    assert ch1["chapter_title"] == "机器视觉技术基础与产业现状"
    assert len(ch1["sections"]) == 2
    assert ch2["chapter_no"] == 2
    assert ch2["chapter_title"] == "关键技术挑战与优化路径"
    assert len(ch2["sections"]) == 2

    # 小节总数 = 5（章1: 2+1, 章2: 2+0）
    total_subsections = sum(len(sec["subsections"]) for ch in result["chapters"] for sec in ch["sections"])
    assert total_subsections == 5

    # 附录
    assert len(result["appendix"]) == 1
    assert result["appendix"][0]["appendix_title"] == "术语表"


def test_structured_fixture_all_titles_no_number_prefix():
    """标题树里所有纯文字标题都不应带编号前缀（结构性穷举检查）。"""
    structure, body = _load_fixture_structure()
    result = ote.run_extract(structure, body, outline_path=str(_FIXTURE))

    all_titles: list[str] = []
    for fm in result["frontmatter"]:
        all_titles.append(fm["chapter_title"])
        all_titles.extend(fm["sections"])
    for ch in result["chapters"]:
        all_titles.append(ch["chapter_title"])
        for sec in ch["sections"]:
            all_titles.append(sec["section_title"])
            all_titles.extend(sec["subsections"])
    for app in result["appendix"]:
        all_titles.append(app["appendix_title"])

    import re
    number_prefix_pattern = re.compile(r"^\s*(\d+[.．]|[一二三四五六七八九十]+[、．.]|第)")
    for title in all_titles:
        assert title, "标题不应为空字符串"
        assert not number_prefix_pattern.match(title), f"标题「{title}」仍带编号前缀"


# ---------------------------------------------------------------------------
# 编号剥离——专门构造 YAML 标题字段本身带编号前缀的样本
# ---------------------------------------------------------------------------


def test_yaml_title_with_embedded_number_prefix_is_stripped():
    """构造 YAML 里 section_title 本身写成 '1.1 技术路线分析' 的样本，确认被剥离。"""
    structure = {
        "frontmatter": [],
        "bodymatter": [
            {
                "chapter_no": 1,
                "chapter_title": "第一章 技术路线综述",
                "sections": [
                    {"section_no": "1.1", "section_title": "1.1 技术路线分析"},
                ],
                "subsections": [
                    {
                        "parent_section_no": "1.1",
                        "subsection_title": "1.1.1 关键技术选型",
                    }
                ],
            }
        ],
        "appendix": [
            {"appendix_letter": "A", "appendix_title": "附录A 术语表"},
        ],
    }
    body = (
        "## 技术路线综述\n\n"
        "### 技术路线分析\n\n"
        "#### 关键技术选型\n\n"
        "## 附录A：术语表\n"
    )
    result = ote.run_extract(structure, body, outline_path="fake-outline.md")

    ch = result["chapters"][0]
    assert ch["chapter_title"] == "技术路线综述"
    assert ch["sections"][0]["section_title"] == "技术路线分析"
    assert ch["sections"][0]["subsections"] == ["关键技术选型"]
    assert result["appendix"][0]["appendix_title"] == "术语表"


# ---------------------------------------------------------------------------
# --chapter-no 过滤
# ---------------------------------------------------------------------------


def test_chapter_no_filter_keeps_only_target_chapter():
    structure, body = _load_fixture_structure()
    result = ote.run_extract(structure, body, outline_path=str(_FIXTURE), chapter_no=2)

    assert result["frontmatter"] == []
    assert result["appendix"] == []
    assert len(result["chapters"]) == 1
    assert result["chapters"][0]["chapter_no"] == 2
    assert result["chapters"][0]["chapter_title"] == "关键技术挑战与优化路径"


def test_chapter_no_filter_nonexistent_chapter_is_empty():
    structure, body = _load_fixture_structure()
    result = ote.run_extract(structure, body, outline_path=str(_FIXTURE), chapter_no=99)

    assert result["chapters"] == []
    assert result["empty"] is True


# ---------------------------------------------------------------------------
# D-1a 回归：--chapter-no 过滤下一致性校验不应产生系统性假阳性
#
# 缺陷复现路径：build_title_tree(chapter_no=1) 只保留第1章的 YAML 标题，
# 但 extract_markdown_headings(body_text) 仍扫描整份正文（含第2章的所有
# heading）。若 check_consistency() 双向比对，第2章每条 heading 都会被
# 误判为 markdown_only（"本章 YAML 未声明"）——这是规则误用，不是真实的
# YAML/Markdown 不一致（见 check_consistency() docstring 与
# multiagent-orchestration.md §8.5 第 4 条）。
# ---------------------------------------------------------------------------


def test_chapter_no_filter_suppresses_markdown_only_false_positives():
    """structured-report.md 全文一致（全量模式 0 告警）；--chapter-no 1/2
    分别提取单章后，也不应因为正文含"其他章节"的 heading 而产生假告警。
    """
    structure, body = _load_fixture_structure()

    # 全量模式：基线应为 0 告警（fixture 本身 YAML 与正文一致）
    full_result = ote.run_extract(structure, body, outline_path=str(_FIXTURE))
    assert full_result["consistency_warnings"] == []

    for target_chapter in (1, 2):
        result = ote.run_extract(
            structure, body, outline_path=str(_FIXTURE), chapter_no=target_chapter
        )
        assert result["consistency_warnings"] == [], (
            f"chapter_no={target_chapter} 不应产生假阳性告警，实际: "
            f"{result['consistency_warnings']}"
        )


def test_chapter_no_filter_yaml_only_direction_still_effective():
    """chapter_no 过滤下应抑制 markdown_only 方向，但 yaml_only 方向仍需生效——
    构造"本章 YAML 声明了但正文缺失"的场景，确认仍能告警。
    """
    structure = {
        "frontmatter": [],
        "bodymatter": [
            {
                "chapter_no": 1,
                "chapter_title": "第一章 综述",
                "sections": [
                    {"section_no": "1.1", "section_title": "背景介绍"},
                    {"section_no": "1.2", "section_title": "研究意义"},  # 正文缺失
                ],
                "subsections": [],
            },
            {
                "chapter_no": 2,
                "chapter_title": "第二章 方法",
                "sections": [{"section_no": "2.1", "section_title": "实验设计"}],
                "subsections": [],
            },
        ],
        "appendix": [],
    }
    # 正文含第1章（缺 1.2 对应 heading）与第2章（YAML 未过滤但正文完整）。
    body = (
        "## 综述\n\n### 背景介绍\n\n正文内容。\n\n"
        "## 方法\n\n### 实验设计\n\n正文内容。\n"
    )
    result = ote.run_extract(structure, body, outline_path="fake-outline.md", chapter_no=1)

    # markdown_only 方向应被抑制：即使正文里"方法/实验设计"不在本章 YAML 中，
    # 也不应报告为告警。
    md_only = [w for w in result["consistency_warnings"] if w["type"] == "markdown_only"]
    assert md_only == [], f"markdown_only 方向应被抑制，实际: {md_only}"

    # yaml_only 方向仍应生效：本章 YAML 声明的"研究意义"正文缺失，应告警。
    yaml_only = [w for w in result["consistency_warnings"] if w["type"] == "yaml_only"]
    assert any(w["title"] == "研究意义" for w in yaml_only)


# ---------------------------------------------------------------------------
# YAML/Markdown 一致性告警
# ---------------------------------------------------------------------------


def test_yaml_declared_but_markdown_missing_triggers_warning():
    structure = {
        "frontmatter": [],
        "bodymatter": [
            {
                "chapter_no": 1,
                "chapter_title": "第一章 综述",
                "sections": [
                    {"section_no": "1.1", "section_title": "背景介绍"},
                    {"section_no": "1.2", "section_title": "研究意义"},  # 正文中缺失
                ],
                "subsections": [],
            }
        ],
        "appendix": [],
    }
    # 正文只有 1.1 对应的 heading，1.2 对应的 heading 缺失
    body = "## 综述\n\n### 背景介绍\n\n正文内容。\n"
    result = ote.run_extract(structure, body, outline_path="fake-outline.md")

    assert result["consistency_warnings"], "应产生一致性告警"
    yaml_only = [w for w in result["consistency_warnings"] if w["type"] == "yaml_only"]
    assert any(w["title"] == "研究意义" for w in yaml_only)


def test_markdown_extra_heading_not_in_yaml_triggers_warning():
    structure = {
        "frontmatter": [],
        "bodymatter": [
            {
                "chapter_no": 1,
                "chapter_title": "第一章 综述",
                "sections": [{"section_no": "1.1", "section_title": "背景介绍"}],
                "subsections": [],
            }
        ],
        "appendix": [],
    }
    # 正文多出一个 YAML 未声明的 H3
    body = "## 综述\n\n### 背景介绍\n\n### 额外未声明小节\n\n正文内容。\n"
    result = ote.run_extract(structure, body, outline_path="fake-outline.md")

    md_only = [w for w in result["consistency_warnings"] if w["type"] == "markdown_only"]
    assert any(w["title"] == "额外未声明小节" for w in md_only)


def test_consistency_warning_degradation_log_level_is_record(_isolate_degradation_log):
    """D-2 回归：一致性告警写入台账时 level 应为 "L-记录"（不是 "L-显著"）。

    裁决依据（方案 §A2）：L-显著 = 数据实际丢失（YAML 解析失败回退启发式、
    subsections 丢弃、图表清单降级）；L-记录 = 记录下来但不影响产出。本告警
    fallback_used 是 report_only_no_auto_fix——没有发生任何降级回退，纯粹是
    大纲文档内部 YAML/Markdown 两处标题不同步的报告性提示，应归为 L-记录。
    """
    log_path = _isolate_degradation_log
    structure = {
        "frontmatter": [],
        "bodymatter": [
            {
                "chapter_no": 1,
                "chapter_title": "第一章 综述",
                "sections": [
                    {"section_no": "1.1", "section_title": "背景介绍"},
                    {"section_no": "1.2", "section_title": "研究意义"},
                ],
                "subsections": [],
            }
        ],
        "appendix": [],
    }
    body = "## 综述\n\n### 背景介绍\n\n正文内容。\n"
    result = ote.run_extract(structure, body, outline_path="fake-outline.md")
    assert result["consistency_warnings"], "应产生一致性告警（前置条件）"

    assert log_path.exists()
    lines = [l for l in log_path.read_text(encoding="utf-8").strip().splitlines() if l]
    assert len(lines) == len(result["consistency_warnings"])
    for line in lines:
        record = json.loads(line)
        assert record["component"] == "outline_title_extract"
        assert record["reason"] == "yaml_markdown_title_mismatch"
        assert record["level"] == "L-记录"


# ---------------------------------------------------------------------------
# 提取为空
# ---------------------------------------------------------------------------


def test_empty_structure_is_empty():
    structure: dict = {"frontmatter": [], "bodymatter": [], "appendix": []}
    result = ote.run_extract(structure, "", outline_path="fake-outline.md")
    assert result["empty"] is True


# ---------------------------------------------------------------------------
# CLI 层面：exit code
# ---------------------------------------------------------------------------


def test_cli_exit_code_success(tmp_path, monkeypatch, capsys):
    outline_path = tmp_path / "outline.md"
    outline_path.write_text(_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["outline_title_extract.py", "--outline", str(outline_path)])
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        ote.main()
    assert exc_info.value.code == 0


def test_cli_exit_code_empty_chapter_filter(tmp_path, monkeypatch):
    outline_path = tmp_path / "outline.md"
    outline_path.write_text(_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["outline_title_extract.py", "--outline", str(outline_path), "--chapter-no", "99"],
    )
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        ote.main()
    assert exc_info.value.code == 1


def test_cli_exit_code_consistency_warning_does_not_block(tmp_path, monkeypatch, capsys):
    """D-1b 回归：一致性告警只应在文本报告里显示，不应影响 exit code（仍为 0）。

    构造一份确有真实不一致的大纲（YAML 声明"研究意义"但正文缺失对应 heading），
    确认告警在文本输出中可见，同时 exit code 为 0（不再是旧版本的 1）。
    """
    outline_text = (
        "---\n"
        "struct_template: research\n"
        "title: \"测试报告\"\n"
        "structure:\n"
        "  frontmatter: []\n"
        "  bodymatter:\n"
        "    - chapter_no: 1\n"
        "      chapter_title: \"综述\"\n"
        "      sections:\n"
        "        - section_no: \"1.1\"\n"
        "          section_title: \"背景介绍\"\n"
        "        - section_no: \"1.2\"\n"
        "          section_title: \"研究意义\"\n"
        "      subsections: []\n"
        "  appendix: []\n"
        "---\n\n"
        "## 综述\n\n### 背景介绍\n\n正文内容，缺少「研究意义」对应的 heading。\n"
    )
    outline_path = tmp_path / "outline.md"
    outline_path.write_text(outline_text, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["outline_title_extract.py", "--outline", str(outline_path)])
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        ote.main()
    assert exc_info.value.code == 0, "一致性告警存在但提取非空，exit code 应为 0"

    captured = capsys.readouterr()
    assert "一致性告警: 1 条" in captured.out
    assert "研究意义" in captured.out


def test_cli_exit_code_empty_extraction_still_fails(tmp_path, monkeypatch):
    """D-1b 回归对照组：提取为空（唯一的失败路由）仍应 exit 1。"""
    outline_text = (
        "---\n"
        "struct_template: research\n"
        "title: \"空报告\"\n"
        "structure:\n"
        "  frontmatter: []\n"
        "  bodymatter: []\n"
        "  appendix: []\n"
        "---\n\n"
        "正文无任何 heading。\n"
    )
    outline_path = tmp_path / "outline.md"
    outline_path.write_text(outline_text, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["outline_title_extract.py", "--outline", str(outline_path)])
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        ote.main()
    assert exc_info.value.code == 1


def test_cli_exit_code_read_error_missing_file(tmp_path, monkeypatch):
    outline_path = tmp_path / "does-not-exist.md"
    monkeypatch.setattr("sys.argv", ["outline_title_extract.py", "--outline", str(outline_path)])
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        ote.main()
    assert exc_info.value.code == 2

