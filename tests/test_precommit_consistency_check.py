# -*- coding: utf-8 -*-
"""``scripts/precommit_consistency_check.py`` 的单元测试（跨模型兼容性优化方案 §B4）。

覆盖任务规格明确要求的 8 类场景：
- Phase A/B 完全一致 -> exit 0
- Phase B 某维度判定未复述 Phase A 触发词 -> exit 1，且指出是哪个 dimension
- 措辞变化但语义保留（同义改写/语序调整）-> 仍判通过（分词交集比例 vs 严格 substring 的鲁棒性对比）
- Phase A 缺维度 -> 检出
- Phase B verdict 行数 != 1（仅在提供 --phase-b-report 时才有意义）-> 检出（A4）
- schema 非法输入 -> exit 2
- failure_stage 字段正确区分 phaseA/phaseB 失败
- 台账隔离（monkeypatch DRR_DEGRADATION_LOG）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import precommit_consistency_check as m
import schema_validate as sv

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "precommit_consistency_check.py"


# ---------------------------------------------------------------------------
# 构造真实契约数据的辅助函数
# ---------------------------------------------------------------------------


def _all_confirm_phase_a(chapter="ch01"):
    """构造一份全 confirm 模式、覆盖全部 24 核心维度的 Phase A JSON。"""
    core_ids = sorted(m.load_core_dimension_ids())
    dims = {i: {"mode": "confirm"} for i in core_ids}
    return {chapter: dims}, core_ids


def _matching_phase_b(chapter, core_ids, dim_meta, block_dims=(), warn_dims=()):
    """为给定维度集合构造 Phase B JSON，block/warn 维度的 evidence 直接取契约 hint 原文（必然一致）。"""
    scores = {}
    for dim_id in core_ids:
        if dim_id in block_dims:
            scores[dim_id] = {
                "verdict": "block",
                "evidence": dim_meta[dim_id]["what_triggers_block_hint"],
            }
        elif dim_id in warn_dims:
            scores[dim_id] = {
                "verdict": "warn",
                "evidence": dim_meta[dim_id]["what_triggers_warn_hint"],
            }
        else:
            scores[dim_id] = {"verdict": "pass", "evidence": "无异常，符合预期"}
    verdict = "REVISE" if any(dim_meta[d]["severity"] == "high" for d in block_dims) else "PASS"
    return {
        "chapter_id": chapter,
        "verdict": verdict,
        "dimension_scores": scores,
        "issues": (
            [{"dimension": d, "location": "第1节", "problem": "触发block", "suggested_fix": "修改"} for d in block_dims]
            if verdict == "REVISE"
            else []
        ),
    }


# ---------------------------------------------------------------------------
# 场景 1：Phase A/B 完全一致 -> exit 0（含 pass/warn/block 混合）
# ---------------------------------------------------------------------------


def test_fully_consistent_passes():
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    # strong_claim 是 high 严重度维度，触发 block 使得 verdict=REVISE 与 verdict_rule 一致
    phase_b_obj = _matching_phase_b(
        "ch01", core_ids, dim_meta,
        block_dims=["strong_claim"], warn_dims=["structural_consistency"],
    )
    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    assert result["dimension_completeness"]["passed"]
    assert result["a5_consistency"]["passed"]
    assert result["verdict_rule"]["passed"]

    schema_a = sv.validate_instance(phase_a_obj, sv.load_schema("auditor-phase-a"))
    schema_b = sv.validate_instance(phase_b_obj, sv.load_schema("auditor-phase-b"))
    assert schema_a["valid"], schema_a["errors"]
    assert schema_b["valid"], schema_b["errors"]

    overall = m.derive_overall(schema_a, schema_b, result)
    assert overall["overall_pass"] is True
    assert overall["failure_stage"] is None


def test_fully_consistent_cli_exit_0(tmp_path):
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta, block_dims=["strong_claim"])

    a_path = tmp_path / "ch01-audit-phaseA.json"
    b_path = tmp_path / "ch01-audit-phaseB.json"
    a_path.write_text(json.dumps(phase_a_obj, ensure_ascii=False), encoding="utf-8")
    b_path.write_text(json.dumps(phase_b_obj, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(a_path), str(b_path), "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["overall_pass"] is True


# ---------------------------------------------------------------------------
# 场景 2：Phase B 某维度判定未复述 Phase A 触发词 -> exit 1，指出具体 dimension
# ---------------------------------------------------------------------------


def test_a5_unmatched_evidence_fails_and_names_dimension():
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta, block_dims=["strong_claim"])
    # 把 strong_claim 的 evidence 替换为与触发词毫无关系的文本
    phase_b_obj["dimension_scores"]["strong_claim"]["evidence"] = "本段落篇幅适中，用词自然，读来顺畅。"

    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    assert result["a5_consistency"]["passed"] is False
    failing = [r for r in result["a5_consistency"]["results"] if not r["passed"]]
    assert len(failing) == 1
    assert failing[0]["dimension"] == "strong_claim"

    schema_a = sv.validate_instance(phase_a_obj, sv.load_schema("auditor-phase-a"))
    schema_b = sv.validate_instance(phase_b_obj, sv.load_schema("auditor-phase-b"))
    overall = m.derive_overall(schema_a, schema_b, result)
    assert overall["overall_pass"] is False
    assert overall["failure_stage"] == "phaseB"


def test_a5_unmatched_evidence_cli_exit_1(tmp_path):
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta, block_dims=["strong_claim"])
    phase_b_obj["dimension_scores"]["strong_claim"]["evidence"] = "无关文本，未复述触发词"

    a_path = tmp_path / "ch01-audit-phaseA.json"
    b_path = tmp_path / "ch01-audit-phaseB.json"
    a_path.write_text(json.dumps(phase_a_obj, ensure_ascii=False), encoding="utf-8")
    b_path.write_text(json.dumps(phase_b_obj, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(a_path), str(b_path), "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["failure_stage"] == "phaseB"
    failing_dims = [r["dimension"] for r in payload["a5_consistency"]["results"] if not r["passed"]]
    assert failing_dims == ["strong_claim"]


# ---------------------------------------------------------------------------
# 场景 3：措辞变化但语义保留 -> 仍判通过（分词交集 vs 严格 substring 鲁棒性对比）
# ---------------------------------------------------------------------------


def test_paraphrase_still_passes_via_token_overlap():
    """strong_claim 的 block 触发词同义改写后：严格 substring 会误判失败，分词交集法正确判通过。"""
    dim_meta = m.load_dimension_meta()
    block_hint = dim_meta["strong_claim"]["what_triggers_block_hint"]
    paraphrase = "经 claim_strength_check.py 运行核实，发现存在缺乏引用支撑的强表述内容，该脚本判定结果为 exit 1"

    # 严格 substring 判定：应当失败（这正是方案要求"分词交集比例而非严格 substring"的价值所在）
    assert block_hint not in paraphrase, "测试前提：改写文本不应是触发词的原文子串"

    # 分词交集比例判定：应当通过
    ratio = m.token_overlap_ratio(m.tokenize(block_hint), m.tokenize(paraphrase))
    assert ratio >= m.DEFAULT_THRESHOLD, f"改写文本 ratio={ratio} 应达到阈值 {m.DEFAULT_THRESHOLD}"

    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta, block_dims=["strong_claim"])
    phase_b_obj["dimension_scores"]["strong_claim"]["evidence"] = paraphrase

    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    assert result["a5_consistency"]["passed"] is True


def test_paraphrase_structural_consistency_word_order_change():
    """structural_consistency 触发词语序调整后的同义改写，仍应判通过。"""
    dim_meta = m.load_dimension_meta()
    block_hint = dim_meta["structural_consistency"]["what_triggers_block_hint"]
    paraphrase = "正文中出现了未列于 outline.md 结构清单的 H3/H4 标题，同时清单声明的某节在正文里没有出现"

    assert block_hint not in paraphrase

    ratio = m.token_overlap_ratio(m.tokenize(block_hint), m.tokenize(paraphrase))
    assert ratio >= m.DEFAULT_THRESHOLD

    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta, block_dims=["structural_consistency"])
    phase_b_obj["dimension_scores"]["structural_consistency"]["evidence"] = paraphrase

    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    assert result["a5_consistency"]["passed"] is True


def test_strict_substring_vs_token_overlap_divergence_documented():
    """鲁棒性对比实证：同一组改写样本，严格 substring 与分词交集法给出不同判定。"""
    dim_meta = m.load_dimension_meta()
    samples = [
        ("strong_claim", dim_meta["strong_claim"]["what_triggers_block_hint"],
         "经 claim_strength_check.py 运行核实，发现存在缺乏引用支撑的强表述内容，该脚本判定结果为 exit 1"),
        ("structural_consistency", dim_meta["structural_consistency"]["what_triggers_block_hint"],
         "正文中出现了未列于 outline.md 结构清单的 H3/H4 标题，同时清单声明的某节在正文里没有出现"),
    ]
    for dim_id, hint, paraphrase in samples:
        substring_match = hint in paraphrase
        ratio = m.token_overlap_ratio(m.tokenize(hint), m.tokenize(paraphrase))
        token_match = ratio >= m.DEFAULT_THRESHOLD
        # 核心断言：严格 substring 判不匹配，分词交集法判匹配——证明后者更鲁棒
        assert substring_match is False, f"{dim_id}: 改写样本不应是原文子串"
        assert token_match is True, f"{dim_id}: 分词交集法应判通过，ratio={ratio}"


# ---------------------------------------------------------------------------
# 场景 4：Phase A 缺维度 -> 检出
# ---------------------------------------------------------------------------


def test_missing_dimension_in_phase_a_detected():
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    # 从 Phase A 中删除一个核心维度
    del phase_a_obj["ch01"]["strong_claim"]
    remaining_ids = [i for i in core_ids if i != "strong_claim"]
    phase_b_obj = _matching_phase_b("ch01", remaining_ids, dim_meta)

    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    dc = result["dimension_completeness"]
    assert dc["passed"] is False
    assert "strong_claim" in dc["missing_core_in_phase_a"]

    schema_a = sv.validate_instance(phase_a_obj, sv.load_schema("auditor-phase-a"))
    schema_b = sv.validate_instance(phase_b_obj, sv.load_schema("auditor-phase-b"))
    overall = m.derive_overall(schema_a, schema_b, result)
    assert overall["overall_pass"] is False
    assert overall["failure_stage"] == "phaseA"


def test_phase_b_missing_dimension_covered_by_phase_a_detected():
    """Phase A 承诺了但 Phase B 没打分的维度，同样应被检出（属 phaseB 失败）。"""
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta)
    del phase_b_obj["dimension_scores"]["strong_claim"]

    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    dc = result["dimension_completeness"]
    assert dc["passed"] is False
    assert "strong_claim" in dc["missing_in_phase_b"]


# ---------------------------------------------------------------------------
# 场景 5：Phase B verdict 行数 != 1（A4，仅 --phase-b-report 模式）-> 检出
# ---------------------------------------------------------------------------


def test_a4_verdict_line_count_via_report(tmp_path):
    report_ok = "## 裁决\nverdict=PASS\n"
    result_ok = m.check_a4_single_verdict_line(report_ok)
    assert result_ok["passed"] is True
    assert result_ok["verdict_line_count"] == 1

    report_dup = "## 裁决\nverdict=PASS\nverdict=REVISE\n"
    result_dup = m.check_a4_single_verdict_line(report_dup)
    assert result_dup["passed"] is False
    assert result_dup["verdict_line_count"] == 2

    report_zero = "## 裁决\n本章通过。\n"
    result_zero = m.check_a4_single_verdict_line(report_zero)
    assert result_zero["passed"] is False
    assert result_zero["verdict_line_count"] == 0


def test_a4_a1_skipped_when_no_report_provided():
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta)
    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    assert result["a1_script_output_proxy"]["status"] == "skipped"
    assert result["a4_single_verdict_line"]["status"] == "skipped"


def test_a1_proxy_indicator_aligned_with_c4_new_form():
    """A1 代理指标须对齐 C4 后新形态（JSON摘要+落盘路径），不检测已废弃的完整 stdout 形态。"""
    report_new_form = (
        "## 脚本量化结果\n"
        "```json\n{\"C1_h1\": \"pass\", \"QS1_cjk_chars\": 3200}\n```\n"
        "全量输出见 research/chapter-reports/ch01-scripts.json\n"
    )
    result = m.check_a1_script_output_proxy(report_new_form)
    assert result["passed"] is True

    report_old_form_stdout_only = (
        "## 脚本量化结果\n"
        "以下是 contract_check.py 的完整 stdout：\n"
        "[OK] C1 无H1 通过\n[OK] C2 无手动编号\n（此处贴了几十行原始终端输出）\n"
    )
    result_old = m.check_a1_script_output_proxy(report_old_form_stdout_only)
    assert result_old["passed"] is False


# ---------------------------------------------------------------------------
# 场景 6：schema 非法输入 -> exit 2
# ---------------------------------------------------------------------------


def test_invalid_json_file_exit_2(tmp_path, monkeypatch):
    log_path = tmp_path / ".degradation-log.jsonl"
    a_path = tmp_path / "bad.json"
    b_path = tmp_path / "ch01-audit-phaseB.json"
    a_path.write_text("{not valid json", encoding="utf-8")
    b_path.write_text("{}", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(a_path), str(b_path)],
        capture_output=True, text=True, encoding="utf-8",
        env={**__import__("os").environ, "DRR_DEGRADATION_LOG": str(log_path)},
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_missing_file_exit_2(tmp_path):
    a_path = tmp_path / "does-not-exist.json"
    b_path = tmp_path / "ch01-audit-phaseB.json"
    b_path.write_text("{}", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(a_path), str(b_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_schema_invalid_content_reported_but_not_exit_2(tmp_path):
    """schema 层面不合法（非结构性错误，如 verdict 枚举值非法）走 exit 1 内容判定路径，而非 exit 2。

    exit 2 保留给"读取/解析异常"（文件不存在、JSON 语法错误、脚本内部异常）；
    "JSON 语法正确但不满足 schema"属于可路由的内容级失败，走 phaseA/phaseB 失败路由（exit 1）。
    """
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta)
    phase_b_obj["verdict"] = "MAYBE"  # 非法枚举值，不在 ["PASS","REVISE"]
    a_path = tmp_path / "ch01-audit-phaseA.json"
    b_path = tmp_path / "ch01-audit-phaseB.json"
    a_path.write_text(json.dumps(phase_a_obj, ensure_ascii=False), encoding="utf-8")
    b_path.write_text(json.dumps(phase_b_obj, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(a_path), str(b_path), "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema_phase_b"]["valid"] is False
    assert payload["failure_stage"] == "phaseB"


# ---------------------------------------------------------------------------
# 场景 7：failure_stage 正确区分 phaseA / phaseB
# ---------------------------------------------------------------------------


def test_failure_stage_phase_a_when_schema_invalid():
    phase_a_obj = {"not-a-valid-chapter-id": {"outline_coverage": {"mode": "confirm"}}}
    phase_b_obj = {
        "chapter_id": "ch01",
        "verdict": "PASS",
        "dimension_scores": {"outline_coverage": {"verdict": "pass", "evidence": "x"}},
        "issues": [],
    }
    schema_a = sv.validate_instance(phase_a_obj, sv.load_schema("auditor-phase-a"))
    assert schema_a["valid"] is False
    # chapter_id 不合法，extract_phase_a_chapter 仍可执行（顶层只有1个键），
    # 但 schema 校验会先行标记失败——通过 derive_overall 综合裁定 phaseA 失败
    content = {
        "chapter_id": "not-a-valid-chapter-id",
        "dimension_completeness": {"missing_in_phase_b": [], "extra_in_phase_b": [],
                                     "missing_core_in_phase_a": [], "passed": True},
        "a5_consistency": {"passed": True, "results": [], "threshold": 0.4},
        "verdict_rule": {"passed": True, "expected_verdict": "PASS", "actual_verdict": "PASS", "high_block_dims": []},
        "a1_script_output_proxy": {"status": "skipped", "reason": "x"},
        "a4_single_verdict_line": {"status": "skipped", "reason": "x"},
    }
    schema_b = sv.validate_instance(phase_b_obj, sv.load_schema("auditor-phase-b"))
    overall = m.derive_overall(schema_a, schema_b, content)
    assert overall["failure_stage"] == "phaseA"


def test_failure_stage_phase_b_when_verdict_rule_mismatch():
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch01", core_ids, dim_meta, block_dims=["strong_claim"])
    # strong_claim 是 high 严重度，触发 block 理应 verdict=REVISE，这里故意错填为 PASS
    phase_b_obj["verdict"] = "PASS"

    result = m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)
    assert result["verdict_rule"]["passed"] is False

    schema_a = sv.validate_instance(phase_a_obj, sv.load_schema("auditor-phase-a"))
    schema_b = sv.validate_instance(phase_b_obj, sv.load_schema("auditor-phase-b"))
    overall = m.derive_overall(schema_a, schema_b, result)
    assert overall["failure_stage"] == "phaseB"


def test_chapter_id_mismatch_raises_value_error():
    dim_meta = m.load_dimension_meta()
    phase_a_obj, core_ids = _all_confirm_phase_a("ch01")
    phase_b_obj = _matching_phase_b("ch02", core_ids, dim_meta)  # 故意章节不匹配

    with pytest.raises(ValueError, match="章节标识不匹配"):
        m.run_check(phase_a_obj, phase_b_obj, m.DEFAULT_THRESHOLD, None)


# ---------------------------------------------------------------------------
# 场景 8：台账隔离
# ---------------------------------------------------------------------------


def test_degradation_log_isolated(tmp_path, monkeypatch):
    log_path = tmp_path / ".degradation-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(log_path))

    a_path = tmp_path / "bad.json"
    b_path = tmp_path / "ch01-audit-phaseB.json"
    a_path.write_text("{not valid json", encoding="utf-8")
    b_path.write_text("{}", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(a_path), str(b_path)],
        capture_output=True, text=True, encoding="utf-8",
        env={**__import__("os").environ, "DRR_DEGRADATION_LOG": str(log_path)},
    )
    assert proc.returncode == 2
    # 台账应写入隔离路径，不污染项目默认台账
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert record["component"] == "precommit_consistency_check"


# ---------------------------------------------------------------------------
# tokenize / token_overlap_ratio 单元测试
# ---------------------------------------------------------------------------


def test_tokenize_and_ratio_basic():
    assert m.token_overlap_ratio(set(), {"a", "b"}) == 1.0
    ref = m.tokenize("claim_strength_check.py 报告存在无引用支撑的强表述")
    same = m.tokenize("claim_strength_check.py 报告存在无引用支撑的强表述")
    assert m.token_overlap_ratio(ref, same) == 1.0


def test_verdict_rule_high_block_forces_revise():
    dim_meta = m.load_dimension_meta()
    scores = {"strong_claim": {"verdict": "block", "evidence": "x"}}
    result = m.check_verdict_rule(scores, dim_meta, "PASS")
    assert result["passed"] is False
    assert result["expected_verdict"] == "REVISE"
    assert result["high_block_dims"] == ["strong_claim"]


def test_verdict_rule_mid_block_does_not_force_revise():
    dim_meta = m.load_dimension_meta()
    scores = {"structural_consistency": {"verdict": "block", "evidence": "x"}}  # mid 严重度
    result = m.check_verdict_rule(scores, dim_meta, "PASS")
    assert result["passed"] is True
    assert result["expected_verdict"] == "PASS"
