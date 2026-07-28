# -*- coding: utf-8 -*-
"""tests/test_delivery_checklist_check.py —— D6 交付清单聚合检查测试。

覆盖：
  10 项可脚本化项的聚合调用（术语一致性/引用格式/参考文献去重/图表编号/
  输出隔离标记/写作者自声明/红队批注/字数统计残留/局部参考文献/交叉引用）
  2 项 manual_required 显式标记（断言不被标记为 pass，断言 status 精确等于
  "manual_required" 常量值，不与 pass/fail/skipped 混同）
  第 13 项降级台账确认 + 台账隔离（monkeypatch.setenv("DRR_DEGRADATION_LOG", ...)）
  整体 overall_pass / failed_items / manual_required_items 聚合语义
  CLI 退出码语义（0/1/2）
"""
from __future__ import annotations

import json
import sys

import pytest

import delivery_checklist_check as dcc


# ── 基础聚合调用：13 项全部出现在返回结构中 ──────────────────────

def test_all_13_items_present_in_result(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text(
        "# 前言/导论\n\n## 问题提出\n\n正文内容。\n\n"
        "## 第一章 测试章节\n\n### 第一节\n\n正文。\n\n"
        "> **本章小结与过渡**：本章总结完毕，无需过渡到下一章。\n",
        encoding="utf-8",
    )
    result = dcc.run_delivery_checklist(str(merged))
    expected_keys = {
        "01_term_consistency", "02_reference_format", "03_reference_dedup",
        "04_figure_numbering", "05_output_isolation_marker",
        "06_writer_selfclaim_stripped", "07_redteam_annotation_stripped",
        "08_word_count_residue", "09_local_bibliography", "10_xref_consistency",
        "11_redteam_resolution_confirmation", "12_full_read_confirmation",
        "13_degradation_ledger",
    }
    assert expected_keys == set(result["items"].keys())


# ── 2 项 manual_required：断言不被标记为 pass ────────────────────

def test_redteam_resolution_confirmation_is_manual_required_not_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text("# 标题\n\n正文。\n", encoding="utf-8")
    result = dcc.run_delivery_checklist(str(merged))
    item = result["items"]["11_redteam_resolution_confirmation"]
    assert item["status"] == dcc.MANUAL_REQUIRED
    assert item["status"] != "pass"
    assert "11_redteam_resolution_confirmation" in result["manual_required_items"]


def test_full_read_confirmation_is_manual_required_not_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text("# 标题\n\n正文。\n", encoding="utf-8")
    result = dcc.run_delivery_checklist(str(merged))
    item = result["items"]["12_full_read_confirmation"]
    assert item["status"] == dcc.MANUAL_REQUIRED
    assert item["status"] != "pass"
    assert "12_full_read_confirmation" in result["manual_required_items"]


def test_manual_required_items_never_counted_as_failed(tmp_path, monkeypatch):
    """manual_required 项即使不是 pass，也不应进入 failed_items（它们是待人工
    确认，不是脚本判定失败）——这是 D6 方案要求"显式标记但不静默跳过/不冒充
    pass"的另一面：也不能被误判为脚本层 fail。"""
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text(
        "# 前言/导论\n\n## 第一章 测试\n\n### 第一节\n\n正文。\n\n"
        "> **本章小结与过渡**：总结完毕。\n",
        encoding="utf-8",
    )
    result = dcc.run_delivery_checklist(str(merged))
    assert "11_redteam_resolution_confirmation" not in result["failed_items"]
    assert "12_full_read_confirmation" not in result["failed_items"]


# ── 06/07 本地正则检测（写作者自声明/红队批注剥离） ────────────────

def test_writer_selfclaim_heading_detected_as_residue():
    text = "## 写作者自声明\n\n本文由AI生成。\n\n## 正文\n\n内容。\n"
    result = dcc.check_writer_selfclaim_stripped(text)
    assert result["status"] == "fail"
    assert len(result["hits"]) == 1


def test_writer_selfclaim_absent_passes():
    text = "## 正文\n\n内容。\n"
    result = dcc.check_writer_selfclaim_stripped(text)
    assert result["status"] == "pass"


def test_redteam_annotation_blockquote_detected_as_residue():
    text = "正文第一段。\n\n> [红队-R003] 该处风险已在阶段8确认降级处理。\n\n正文第二段。\n"
    result = dcc.check_redteam_annotation_stripped(text)
    assert result["status"] == "fail"
    assert len(result["hits"]) == 1


def test_redteam_annotation_absent_passes():
    text = "正文第一段。\n\n正文第二段，正常引用块。\n\n> 这是普通引用，不含红队标记。\n"
    result = dcc.check_redteam_annotation_stripped(text)
    assert result["status"] == "pass"


# ── 10 交叉引用一致性（存在性/格式校验） ──────────────────────────

def test_xref_consistency_orphan_ref_reported_but_status_still_pass():
    """孤儿引用（引用了不存在的图表编号）只作为 orphan_refs 供人工抽查，
    不导致本项 fail——语义指对与否超出脚本判定范围（方案 §D6 声明的天花板）。"""
    text = "正文引用了如图1-1所示的架构。\n"
    result = dcc.check_xref_consistency(text)
    assert result["status"] == "pass"
    assert "图1-1" in result["orphan_refs"]


def test_xref_consistency_matched_ref_no_orphan():
    text = "正文引用了如图1-1所示的架构。\n\n![图1-1 架构总览](figures/图1-1.png)\n"
    result = dcc.check_xref_consistency(text)
    assert result["status"] == "pass"
    assert result["orphan_refs"] == []


# ── 03 参考文献去重代理指标（has_any_src_refs 安全调用，不触发 sys.exit） ──

def test_reference_dedup_no_residue_when_no_src_refs():
    text = "正文引用采用 [1] 编号格式，无 SRC 残留。\n"
    result = dcc.check_reference_dedup(text, drafts_dir=None)
    assert result["status"] == "pass"
    assert result["src_residue_found"] is False


def test_reference_dedup_residue_detected_when_src_ref_present():
    text = "正文残留了 [SRC-001] 未转换的引用标记。\n"
    result = dcc.check_reference_dedup(text, drafts_dir=None)
    assert result["status"] == "fail"
    assert result["src_residue_found"] is True


# ── 13 降级台账确认 + 台账隔离 ─────────────────────────────────────

def test_degradation_ledger_passes_when_log_absent(tmp_path, monkeypatch):
    """台账文件不存在时 summarize() 返回 blocking=False（不抛异常），本项应 pass。"""
    isolated_log = tmp_path / "nonexistent-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(isolated_log))
    result = dcc.check_degradation_ledger(log_path=None)
    assert result["status"] == "pass"
    assert result["summary"]["log_exists"] is False


def test_degradation_ledger_fails_when_unacknowledged_significant_event(tmp_path, monkeypatch):
    """台账隔离：用 monkeypatch.setenv("DRR_DEGRADATION_LOG", ...) 指向临时文件，
    写入一条未确认的 L-显著事件，断言第 13 项判定 fail（阻断），且不影响真实
    项目台账文件。"""
    isolated_log = tmp_path / "test-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(isolated_log))

    from degradation_log import record_degradation, LEVEL_SIGNIFICANT

    record_degradation(
        stage="stage9",
        component="test_component",
        reason="测试用未确认降级事件",
        level=LEVEL_SIGNIFICANT,
        log_path=str(isolated_log),
    )

    result = dcc.check_degradation_ledger(log_path=None)
    assert result["status"] == "fail"
    assert result["summary"]["blocking"] is True


def test_degradation_ledger_explicit_log_path_overrides_env(tmp_path, monkeypatch):
    """显式 log_path 参数优先级高于环境变量（_resolve_log_path 的既有优先级
    语义），验证聚合脚本传参路径正确。"""
    env_log = tmp_path / "env-log.jsonl"
    explicit_log = tmp_path / "explicit-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(env_log))

    from degradation_log import record_degradation, LEVEL_SIGNIFICANT

    record_degradation(
        stage="stage9", component="c", reason="仅写入 explicit_log",
        level=LEVEL_SIGNIFICANT, log_path=str(explicit_log),
    )

    result = dcc.check_degradation_ledger(log_path=str(explicit_log))
    assert result["status"] == "fail"

    result_env = dcc.check_degradation_ledger(log_path=None)
    assert result_env["status"] == "pass"


# ── 01 术语一致性：调用处自行 try/except 兜底（run_check 本身无保护） ──

def test_term_consistency_skipped_when_glossary_missing(tmp_path):
    merged = tmp_path / "final-report.md"
    merged.write_text("正文。\n", encoding="utf-8")
    result = dcc.check_term_consistency(str(merged), glossary_path=None)
    assert result["status"] == "skipped"


def test_term_consistency_error_wrapped_not_raised(tmp_path):
    """glossary 文件存在但格式错误应被 try/except 捕获为 status=error，
    不应向上抛出未处理异常（term_consistency_check.run_check 本身无保护，
    这是 D6 聚合脚本必须自行包裹的边界）。"""
    merged = tmp_path / "final-report.md"
    merged.write_text("正文。\n", encoding="utf-8")
    bad_glossary = tmp_path / "glossary.md"
    bad_glossary.write_text("# 术语表\n\n没有 yaml 代码块。\n", encoding="utf-8")
    result = dcc.check_term_consistency(str(merged), glossary_path=str(bad_glossary))
    assert result["status"] == "error"


# ── overall_pass 聚合语义 ───────────────────────────────────────

def test_overall_pass_true_when_all_scriptable_items_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text(
        "# 前言/导论\n\n## 第一章 测试章节\n\n### 第一节\n\n正文内容干净无残留。\n\n"
        "> **本章小结与过渡**：本章总结完毕。\n",
        encoding="utf-8",
    )
    result = dcc.run_delivery_checklist(str(merged))
    assert result["overall_pass"] is True
    assert result["failed_items"] == []


def test_overall_pass_false_when_src_residue_present(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text("正文残留 [SRC-001] 未转换引用。\n", encoding="utf-8")
    result = dcc.run_delivery_checklist(str(merged))
    assert result["overall_pass"] is False
    assert "03_reference_dedup" in result["failed_items"]


# ── CLI 退出码语义 ───────────────────────────────────────────────

def test_cli_exit_2_when_file_not_found(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["delivery_checklist_check.py", "does-not-exist.md"])
    with pytest.raises(SystemExit) as exc_info:
        dcc.main()
    assert exc_info.value.code == 2


def test_cli_exit_0_when_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text(
        "# 前言/导论\n\n## 第一章 测试章节\n\n### 第一节\n\n正文内容干净无残留。\n\n"
        "> **本章小结与过渡**：本章总结完毕。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["delivery_checklist_check.py", str(merged), "--json"])
    with pytest.raises(SystemExit) as exc_info:
        dcc.main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["overall_pass"] is True
    assert set(data["manual_required_items"]) == {
        "11_redteam_resolution_confirmation", "12_full_read_confirmation",
    }


def test_cli_exit_1_when_residue_present(tmp_path, monkeypatch):
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(tmp_path / "empty-log.jsonl"))
    merged = tmp_path / "final-report.md"
    merged.write_text("正文残留 [SRC-001] 未转换引用。\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["delivery_checklist_check.py", str(merged)])
    with pytest.raises(SystemExit) as exc_info:
        dcc.main()
    assert exc_info.value.code == 1
