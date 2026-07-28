# -*- coding: utf-8 -*-
"""structured-sample fixture 的 A1 回归测试（第 2 批：A1 修复后的正式版本）。

跨模型兼容性优化方案 §六 Critical-4：现有 8 份 fixture 全部 H4 数量=0、
无 YAML structure 节点，对 A1（outline_reader subsections 字段名修复）
零敏感——若直接用它们建快照，A1 改前改后零差异，快照会给出假阳性。

本文件针对新建的 ``tests/fixtures/structured-sample/`` fixture 编写正式的
"期望行为"回归测试。第 1 批（A1 修复前）曾用 ``@pytest.mark.xfail(strict=True)``
标记两条测试以复现 bug（``_build_structure_lookup()`` 读取
``sub.get("parent")`` / ``sub.get("title")`` 这两个不存在的字段名，规范字段名是
``parent_section_no`` / ``subsection_title``，导致所有 subsection 被静默丢弃、
SUBSECTION 条目数恒为 0）；第 2 批 A1 修复落地后，xfail 装饰器已删除，
测试转为正式回归测试（不应再失败）。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from md2docx.assemble.outline_reader import (
    _build_structure_lookup,
    build_structure_manifest,
    extract_yaml_front_matter,
)
from md2docx.ir import HeadingKind

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "structured-sample"
_MD_PATH = _FIXTURE_DIR / "structured-report.md"
_EXPECTED_PATH = _FIXTURE_DIR / "expected-structure.json"


def _load_expected() -> dict:
    return json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))


def _load_lookup() -> dict:
    """解析 structured-report.md 的 YAML front matter，返回 structure lookup 表。"""
    text = _MD_PATH.read_text(encoding="utf-8")
    parsed, _body = extract_yaml_front_matter(text)
    assert parsed is not None, "structured-report.md 的 YAML front matter 解析失败"
    structure = parsed.get("structure")
    assert isinstance(structure, dict), "YAML 中缺少 structure 节点"
    return _build_structure_lookup(structure)


# ---------------------------------------------------------------------------
# 基础健全性检查（不 xfail —— 证明 fixture 本身格式正确，不是整体解析失败）
# ---------------------------------------------------------------------------


def test_fixture_yaml_parses_and_chapters_sections_recognized():
    """健全性检查：YAML 能正确解析，且 CHAPTER/SECTION 条目数 > 0。

    这条断言不 xfail——它证明 fixture 本身格式正确、YAML 解析未整体失败。
    若这条也失败，说明 fixture 有格式错误（而非 A1 bug），需要先修 fixture。
    """
    lookup = _load_lookup()
    counts = Counter(kind.name for kind, _number in lookup.values())

    expected = _load_expected()["lookup_counts"]
    assert counts.get("CHAPTER", 0) == expected["CHAPTER"] > 0, (
        f"CHAPTER 条目数应为 {expected['CHAPTER']}（且 >0），实际 lookup 分类统计：{dict(counts)}"
    )
    assert counts.get("SECTION", 0) == expected["SECTION"] > 0, (
        f"SECTION 条目数应为 {expected['SECTION']}（且 >0），实际 lookup 分类统计：{dict(counts)}"
    )


def test_fixture_subsection_declared_matches_yaml():
    """A1 修复后：本测试从"SUBSECTION 恒为 0 的 bug 复现快照"改为
    正向健全性检查——证明 fixture 声明的 subsection 总数与
    expected-structure.json 的期望一致（供下面的正式回归测试引用同一基线）。

    跨模型兼容性优化方案 §二 第2批 A1 修复后，原
    ``test_fixture_subsection_lookup_currently_empty``（断言 SUBSECTION
    恒为 0）已随 bug 修复而失效——继续保留该断言会导致本文件测试失败，
    与"第2批验收要求本文件全部 PASSED"矛盾，故在此改写为正向基线检查，
    不再保留"复现 bug"语义。
    """
    lookup = _load_lookup()
    counts = Counter(kind.name for kind, _number in lookup.values())
    expected = _load_expected()["lookup_counts"]
    assert counts.get("SUBSECTION", 0) == expected["SUBSECTION"] > 0, (
        f"SUBSECTION 条目数应为 {expected['SUBSECTION']}（且 >0，A1 修复后不应再"
        f"恒为 0），实际 lookup 分类统计：{dict(counts)}"
    )


# ---------------------------------------------------------------------------
# A1 修复后的期望行为（第 2 批：xfail 装饰器已删除，正式转为回归测试）
# ---------------------------------------------------------------------------


def test_subsection_lookup_matches_yaml_declaration():
    """A1 修复后期望：SUBSECTION 条目数 == YAML 中声明的 subsection 总数（5）。

    同时校验每个声明的 subsection 标题都被正确分类为 HeadingKind.SUBSECTION
    并且确实入表（不依赖具体编号——编号权威见 headings.py Phase 7b，
    详见 expected-structure.json 的 note 字段）。
    """
    lookup = _load_lookup()
    expected = _load_expected()

    counts = Counter(kind.name for kind, _number in lookup.values())
    assert counts.get("SUBSECTION", 0) == expected["lookup_counts"]["SUBSECTION"], (
        f"SUBSECTION 条目数应为 {expected['lookup_counts']['SUBSECTION']}，"
        f"实际 {counts.get('SUBSECTION', 0)}"
    )

    for sub in expected["subsections"]:
        title = sub["title"]
        assert title in lookup, f"subsection 标题 {title!r} 未出现在 lookup 表中（被静默丢弃）"
        kind, _number = lookup[title]
        assert kind == HeadingKind.SUBSECTION, (
            f"subsection 标题 {title!r} 分类应为 SUBSECTION，实际 {kind.name}"
        )


def test_manifest_count_matches_lookup_count():
    """A1 修复后期望：build_structure_manifest() 的 subsection_count 与
    lookup 表中实际 SUBSECTION 条目数一致（当前 manifest 用 len() 统计，
    与 lookup 的实际展平结果脱节，构成"谎报"）。
    """
    text = _MD_PATH.read_text(encoding="utf-8")
    parsed, _body = extract_yaml_front_matter(text)
    structure = parsed.get("structure")

    lookup = _build_structure_lookup(structure)
    manifest = build_structure_manifest(structure)

    lookup_subsection_count = sum(
        1 for kind, _number in lookup.values() if kind == HeadingKind.SUBSECTION
    )
    assert manifest["subsection_count"] == lookup_subsection_count, (
        f"manifest.subsection_count={manifest['subsection_count']} 应与 "
        f"lookup 实际 SUBSECTION 条目数={lookup_subsection_count} 一致"
    )
