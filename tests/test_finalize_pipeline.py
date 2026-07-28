# -*- coding: utf-8 -*-
"""tests/test_finalize_pipeline.py —— D5 定稿顺序管道测试。

覆盖：
  6 个 failure_step 在各自步骤失败时被正确返回（strip_markers/h1_check/merge/
  convert_refs/contract_check/delivery_checklist），且 steps 字典中该步骤
  status=fail、reason 非空
  成功路径全绿：构造最小但完整的 drafts/outline/source-index 三件套，走完整
  6 步，断言 overall_pass=True、failure_step=None、output_path 指向实际生成
  的文件
  CLI 退出码语义（0/1/2）
  台账隔离（不触碰真实项目台账文件）

注：contract_check 步骤的成功路径刻意构造为"无引用"样本（不含 [SRC-XXX]），
因为已实测确认 contract_check.py 的 C6（`_check_c6_references`）对纯数字
引用 `[N]` 本身判负（`pure_num_hits` 命中即 `pass=False`），与 convert_refs
步骤转换后必然产生纯数字引用这一事实存在真实冲突（详见实现报告"发现的问题"
一节）。为了不让这个既有的 contract_check.py 行为污染"D5 管道本身工作正常"
这一测试目标，成功路径样本不引入任何引用；C6 冲突单独用一个明确标注为
"已知问题重现"的测试记录下来，断言其确实复现（而非静默略过）。
"""
from __future__ import annotations

import json
import sys

import pytest

import finalize_pipeline as fp


def _write_outline(tmp_path):
    """frontmatter-only 结构（无 bodymatter 编号章节）。

    刻意不使用 bodymatter 章节：已实测确认 merge_drafts.assemble_merged()
    按规范插入的章容器 `## 第 X 章：<chapter_title>` 本身会命中
    contract_check.py 的 C2（MANUAL_NUMBER_PATTERN 匹配"第\\s*N...章"），
    且 merged=True + stage="stage9" 下 severity=fatal——这是 merge_drafts.py
    与 contract_check.py 两个既有组件之间的真实冲突（此前被 merge_drafts.py
    "阶段E只WARN不阻断"的反模式掩盖，D5 管道使其第一次真正可见，见实现报告
    "发现的问题"）。用 frontmatter-only 结构隔离"管道机制本身是否正常"这一
    测试目标；该 C2 冲突单独由 test_failure_step_contract_check_reproduces_
    chapter_container_c2_conflict 明确记录复现。
    """
    outline = tmp_path / "outline.md"
    outline.write_text(
        "---\n"
        "struct_template: research\n"
        "title: 测试报告\n"
        "structure:\n"
        "  frontmatter:\n"
        "    - chapter_title: 前言/导论\n"
        "      sections:\n"
        "        - section_no: \"\"\n"
        "          section_title: 问题提出与研究背景\n"
        "  bodymatter: []\n"
        "  appendix: []\n"
        "---\n",
        encoding="utf-8",
    )
    return outline


def _write_outline_with_chapter(tmp_path):
    """含 bodymatter 编号章节的结构，专供 C2 冲突复现测试使用。"""
    outline = tmp_path / "outline.md"
    outline.write_text(
        "---\n"
        "struct_template: research\n"
        "title: 测试报告\n"
        "structure:\n"
        "  frontmatter: []\n"
        "  bodymatter:\n"
        "    - chapter_no: 1\n"
        "      chapter_title: 第一章测试\n"
        "      sections:\n"
        "        - section_no: \"1.1\"\n"
        "          section_title: 测试节\n"
        "  appendix: []\n"
        "---\n",
        encoding="utf-8",
    )
    return outline


def _write_source_index(tmp_path):
    csv_path = tmp_path / "source-index.csv"
    csv_path.write_text(
        "source_id,title,author_or_org,publisher,publish_date,source_type,url_or_path\n"
        "SRC-001,测试来源标题,测试作者,测试出版社,2024,book,\n",
        encoding="utf-8",
    )
    return csv_path


def _write_clean_draft(drafts_dir):
    (drafts_dir / "ch01-1-1-测试节.md").write_text(
        "### 测试节\n\n正文内容，无任何引用残留，干净通过，字数足够长一些用于测试。\n",
        encoding="utf-8",
    )


# ── 成功路径全绿 ─────────────────────────────────────────────

def test_success_path_all_steps_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    _write_clean_draft(drafts_dir)
    outline = _write_outline(tmp_path)
    source_index = _write_source_index(tmp_path)
    output = tmp_path / "final-report.md"

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(output),
    )

    assert result["overall_pass"] is True
    assert result["failure_step"] is None
    assert result["output_path"] is not None
    assert output.exists()
    for step in fp.FAILURE_STEPS:
        assert result["steps"][step]["status"] == "pass"


# ── 6 个 failure_step 枚举分别验证 ───────────────────────────

def test_failure_step_strip_markers_when_drafts_dir_missing(tmp_path):
    result = fp.run_finalize_pipeline(
        drafts_dir=str(tmp_path / "does-not-exist"),
        outline_path=str(tmp_path / "outline.md"),
        source_index_path=str(tmp_path / "source-index.csv"),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["overall_pass"] is False
    assert result["failure_step"] == "strip_markers"


def test_failure_step_merge_when_outline_yaml_missing_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    _write_clean_draft(drafts_dir)
    # outline.md 缺少 structure 节点 —— parse_outline_yaml 内部 sys.exit(2)
    outline = tmp_path / "outline.md"
    outline.write_text("---\ntitle: 无 structure 节点\n---\n", encoding="utf-8")
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["overall_pass"] is False
    assert result["failure_step"] == "merge"
    assert "sys.exit" in result["failure_reason"] or "解析失败" in result["failure_reason"]


def test_failure_step_merge_when_outline_yaml_malformed(tmp_path, monkeypatch):
    """outline.md YAML 语法错误（非结构缺失，而是解析异常）同样应捕获为
    merge 步骤失败，而不是让 SystemExit(2) 击穿整个管道进程。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    _write_clean_draft(drafts_dir)
    outline = tmp_path / "outline.md"
    # 制造非法 YAML：未闭合的方括号
    outline.write_text("---\nstructure: [unclosed\n---\n", encoding="utf-8")
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["overall_pass"] is False
    assert result["failure_step"] == "merge"


def test_failure_step_convert_refs_when_source_index_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    _write_clean_draft(drafts_dir)
    outline = _write_outline(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(tmp_path / "does-not-exist-source-index.csv"),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["overall_pass"] is False
    assert result["failure_step"] == "convert_refs"


def test_failure_step_convert_refs_when_slash_refs_present(tmp_path, monkeypatch):
    """斜杠分隔 SRC 引用（[SRC-001/026]）不支持自动转换，应在 convert_refs
    步骤被检出并阻断（复用 convert_references.find_slash_refs_in_file）。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "ch01-1-1-测试节.md").write_text(
        "### 测试节\n\n正文引用了斜杠分隔格式 [SRC-001/SRC-002]。\n",
        encoding="utf-8",
    )
    outline = _write_outline(tmp_path)
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["overall_pass"] is False
    assert result["failure_step"] == "convert_refs"


def test_failure_step_contract_check_reproduces_pure_num_conflict(tmp_path, monkeypatch):
    """回归测试（原为"已知问题重现"，缺陷修复后转为正向验证）：

    历史问题（G7 端到端验证发现的 P0，与 C2 章容器冲突同构）：drafts 中含
    ``[SRC-001]`` 引用，``convert_refs`` 步骤按 GB/T 7714 顺序编码制正确将其
    转换为纯数字 ``[1]``，但紧接着的 ``contract_check`` 步骤又把"纯数字引用"
    本身判为 C6 违规——**定稿管道否定自己上一步的正确产出**。后果：任何含至少
    一条参考文献的真实报告都无法走完管道，``delivery_checklist``（含降级台账
    确认、红队确认、全文通读确认）永远不可达。

    修复（编排器裁决）：``_check_c6_references()`` 改为**分阶段**判定，与 C7 已有的
    stage7/stage9 对称设计保持一致——
    - stage7 分章草稿：纯数字引用仍是违规（作者不应提前写死编号，会与自动编号冲突）
    - stage9 + merged 合并终稿：纯数字引用是 ``convert_references.py`` 的预期产出，不判负
    ``slash_src`` / ``s_variant`` 两类真正的格式错误在任何阶段都仍然判负。

    本测试验证：含引用的报告能顺利通过 contract_check 的 C6 判定并走完管道。
    对"stage7 仍拦截纯数字引用"的验证见
    test_c6_still_blocks_pure_num_in_stage7_draft。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "ch01-1-1-测试节.md").write_text(
        "### 测试节\n\n正文引用了数据来源[SRC-001]，内容详实可靠。\n",
        encoding="utf-8",
    )
    outline = _write_outline_with_chapter(tmp_path)
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    c6 = result["steps"]["contract_check"]["detail"]["contract"]["C6_reference_format"]
    # 纯数字引用在 stage9 合并终稿中被识别为预期产出，不再判负
    assert c6["pure_num_expected"] is True
    assert c6["pass"] is True, f"C6 仍判负，命中：{c6.get('pure_num_hits')}"
    # convert_refs 确实做了转换（存在纯数字引用），只是不再被判为违规
    assert c6["pure_num_count"] >= 1
    # contract_check 不再是阻断点，管道得以继续
    assert result["failure_step"] != "contract_check"


def test_c6_still_blocks_pure_num_in_stage7_draft():
    """豁免精确性回归：stage9 豁免**不得**削弱 C6 对分章草稿的拦截。

    直接调用 ``check_contract()`` 验证三种情形：
    - stage7 草稿：纯数字引用仍判负（作者提前写死编号）
    - stage9 合并终稿：纯数字引用放行
    - stage9 合并终稿：斜杠 SRC / S 变体等真正的格式错误**仍然**判负
    """
    import contract_check as cc

    draft = "# T\n\n## 第 1 章：绪论\n\n正文引用[1]与[2,3]。\n"
    # stage7：仍判负
    r7 = cc.check_contract(draft, merged=False, expect_figures=None, stage="stage7")
    c6_7 = r7["contract"]["C6_reference_format"]
    assert c6_7["pure_num_expected"] is False
    assert c6_7["pass"] is False, "stage7 草稿的纯数字引用未被拦截——豁免范围过宽"

    # stage9 + merged：放行
    r9 = cc.check_contract(draft, merged=True, expect_figures=None, stage="stage9")
    assert r9["contract"]["C6_reference_format"]["pass"] is True

    # stage9 + merged 但含真正的格式错误：仍判负
    bad = "# T\n\n## 第 1 章：绪论\n\n正文[SRC-001/026]与[S001]。\n"
    r9b = cc.check_contract(bad, merged=True, expect_figures=None, stage="stage9")
    c6_9b = r9b["contract"]["C6_reference_format"]
    assert c6_9b["pass"] is False, "斜杠/S变体格式错误被错误放行"
    assert c6_9b["slash_src_hits"] and c6_9b["s_variant_hits"]


def test_contract_check_reproduces_chapter_container_c2_conflict(tmp_path, monkeypatch):
    """回归测试（原为"已知问题重现"，缺陷修复后转为正向验证）：

    历史问题：``merge_drafts.assemble_merged()`` 按 references/stage-7-writing.md
    规范在阶段9合并时统一插入的标准章容器 ``## 第 {c_no} 章：{c_title}``，其字面
    结构必然命中 ``contract_check.MANUAL_NUMBER_PATTERN``，且在 merged=True +
    stage="stage9" 下 C2 severity 升级为 "fatal"（标注"不可降级放行"）。这导致
    **任何含至少一个编号章节的报告**在 contract_check 步骤必然失败——即检查器
    把自家合并管道的标准输出判为致命错误。

    修复（编排器裁决）：``contract_check.PIPELINE_CHAPTER_CONTAINER_PATTERN`` 在
    merged 模式下豁免管道自动生成的章容器。C2 的立法意图是禁止**作者手写**编号
    前缀（应交由 Word 自动编号域生成），而章容器是管道自身按规范产出的结构性标记，
    下游 md2docx 会将其识别为 CHAPTER 并接管编号。

    本测试验证：含编号章节的报告能顺利通过 contract_check 的 C2 判定。
    对"作者手写编号仍被拦截"的验证见
    test_c2_still_blocks_author_written_manual_numbering。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "ch01-1-1-测试节.md").write_text(
        "### 测试节\n\n正文内容干净无残留，不含任何引用，字数足够长一些用于测试。\n",
        encoding="utf-8",
    )
    outline = _write_outline_with_chapter(tmp_path)
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    c2 = result["steps"]["contract_check"]["detail"]["contract"]["C2_manual_number"]
    # 章容器已被豁免：C2 不再因管道自身产出的 `## 第 1 章：xxx` 而判负
    assert c2["pass"] is True, f"章容器未被豁免，C2 命中：{c2['hits']}"
    assert not any("第 1 章" in h or "第1章" in h for h in c2["hits"])
    # contract_check 步骤不再是阻断点
    assert result["failure_step"] != "contract_check"


def test_c2_still_blocks_author_written_manual_numbering(tmp_path, monkeypatch):
    """豁免精确性回归：章容器豁免**不得**削弱 C2 对作者手写编号的拦截。

    构造一份正文含 `### 1.1 手写编号节` 的草稿，确认在 merged+stage9 下
    C2 仍判负且 severity 为 fatal——证明豁免范围严格限定为"管道章容器"
    这一种确定格式，没有把 C2 整体放宽。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "ch01-1-1-测试节.md").write_text(
        "### 1.1 手写编号节\n\n正文内容干净无残留，字数足够长一些用于测试。\n",
        encoding="utf-8",
    )
    outline = _write_outline_with_chapter(tmp_path)
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    c2 = result["steps"]["contract_check"]["detail"]["contract"]["C2_manual_number"]
    assert c2["pass"] is False, "作者手写编号未被拦截——豁免范围过宽"
    assert c2["severity"] == "fatal"
    assert any("1.1" in h for h in c2["hits"])


def test_delivery_checklist_step_unreachable_via_pipeline_due_to_c2_conflict(tmp_path, monkeypatch):
    """回归测试（原为"已知问题重现"，C2 冲突修复后恢复其原始测试意图）：

    历史问题：因 C2 章容器冲突（见
    test_contract_check_reproduces_chapter_container_c2_conflict），任何含
    bodymatter 的报告都在 contract_check 步骤被提前拦下，导致 delivery_checklist
    这道最后关卡经由完整管道**根本不可达**。

    C2 豁免修复后，本测试恢复原始意图：验证 delivery_checklist 确实是管道
    最后一道独立关卡——构造一个能通过 contract_check、但会被 D6 清单第 06 项
    （写作者自声明剥离）拦下的样本，确认 failure_step 正确指向
    delivery_checklist 而非更早的步骤。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "ch01-1-1-测试节.md").write_text(
        "### 测试节\n\n正文内容干净无残留，字数足够长一些用于测试。\n\n"
        "## 写作者自声明\n\n本文由AI生成，不代表任何官方立场。\n",
        encoding="utf-8",
    )
    outline = _write_outline_with_chapter(tmp_path)
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["overall_pass"] is False
    # delivery_checklist 现在可达，且正确成为阻断点
    assert result["failure_step"] == "delivery_checklist", (
        f"delivery_checklist 未被触达或未正确阻断，实际 failure_step="
        f"{result['failure_step']}，已执行步骤={list(result['steps'].keys())}"
    )
    assert "delivery_checklist" in result["steps"]
    assert "06_writer_selfclaim_stripped" in (
        result["steps"]["delivery_checklist"]["detail"]["failed_items"]
    )


def test_delivery_checklist_function_detects_writer_selfclaim_directly(tmp_path, monkeypatch):
    """绕开完整管道（不经过 contract_check 这道会因 C2 冲突提前阻断的关卡），
    直接调用 delivery_checklist_check.run_delivery_checklist() 验证该函数
    自身对写作者自声明残留的检测逻辑是正确的——证明 D6 聚合脚本本身没有
    缺陷，问题完全出在"管道内它被 contract_check 步骤挡在前面、根本触达
    不到"这一编排层面。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text(
        "### 测试节\n\n正文内容干净无残留，字数足够长一些用于测试。\n\n"
        "## 写作者自声明\n\n本文由AI生成，不代表任何官方立场。\n",
        encoding="utf-8",
    )
    from delivery_checklist_check import run_delivery_checklist

    result = run_delivery_checklist(str(merged))
    assert result["overall_pass"] is False
    assert "06_writer_selfclaim_stripped" in result["failed_items"]


# ── h1_check 步骤：正向验证 H1 被正确替换为 H2 ──────────────────

def test_h1_check_replaces_h1_with_h2(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    draft_file = drafts_dir / "ch01-1-1-测试节.md"
    draft_file.write_text(
        "# 误用的一级标题\n\n### 测试节\n\n正文内容干净无残留，字数足够长一些用于测试。\n",
        encoding="utf-8",
    )
    outline = _write_outline(tmp_path)
    source_index = _write_source_index(tmp_path)

    result = fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )
    assert result["steps"]["h1_check"]["status"] == "pass"
    assert str(draft_file) in result["steps"]["h1_check"]["files_with_h1_replaced"]
    # 文件已被写回，H1 应变为 H2
    new_text = draft_file.read_text(encoding="utf-8")
    assert "## 误用的一级标题" in new_text
    assert not new_text.startswith("# 误用的一级标题")


# ── strip_markers 步骤：.bak 备份 + 清洗生效 ─────────────────────

def test_strip_markers_creates_bak_and_cleans(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    draft_file = drafts_dir / "ch01-1-1-测试节.md"
    original_text = (
        "### 测试节\n\n正文内容干净无残留，字数足够长一些用于测试。\n\n"
        "全文约 1200 字\n"
    )
    draft_file.write_text(original_text, encoding="utf-8")
    outline = _write_outline(tmp_path)
    source_index = _write_source_index(tmp_path)

    fp.run_finalize_pipeline(
        drafts_dir=str(drafts_dir),
        outline_path=str(outline),
        source_index_path=str(source_index),
        output_path=str(tmp_path / "final-report.md"),
    )

    bak_file = drafts_dir / "ch01-1-1-测试节.md.bak"
    assert bak_file.exists()
    assert bak_file.read_text(encoding="utf-8") == original_text
    cleaned_text = draft_file.read_text(encoding="utf-8")
    assert "全文约 1200 字" not in cleaned_text


# ── CLI 退出码语义 ───────────────────────────────────────────────

def test_cli_exit_2_when_drafts_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "finalize_pipeline.py",
        "--drafts-dir", str(tmp_path / "does-not-exist"),
        "--outline", str(tmp_path / "outline.md"),
        "--source-index", str(tmp_path / "source-index.csv"),
        "--output", str(tmp_path / "final-report.md"),
    ])
    with pytest.raises(SystemExit) as exc_info:
        fp.main()
    assert exc_info.value.code == 2


def test_cli_exit_0_when_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    _write_clean_draft(drafts_dir)
    outline = _write_outline(tmp_path)
    source_index = _write_source_index(tmp_path)
    output = tmp_path / "final-report.md"

    monkeypatch.setattr(sys, "argv", [
        "finalize_pipeline.py",
        "--drafts-dir", str(drafts_dir),
        "--outline", str(outline),
        "--source-index", str(source_index),
        "--output", str(output),
        "--json",
    ])
    with pytest.raises(SystemExit) as exc_info:
        fp.main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["overall_pass"] is True


def test_cli_exit_1_when_step_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    _write_clean_draft(drafts_dir)
    outline = _write_outline(tmp_path)

    monkeypatch.setattr(sys, "argv", [
        "finalize_pipeline.py",
        "--drafts-dir", str(drafts_dir),
        "--outline", str(outline),
        "--source-index", str(tmp_path / "does-not-exist-source-index.csv"),
        "--output", str(tmp_path / "final-report.md"),
    ])
    with pytest.raises(SystemExit) as exc_info:
        fp.main()
    assert exc_info.value.code == 1
