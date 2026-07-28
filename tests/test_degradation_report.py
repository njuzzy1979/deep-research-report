# -*- coding: utf-8 -*-
"""degradation_report.py 的单元测试（跨模型兼容性优化方案 §三 B5）。

覆盖方案验收标准明确要求的场景：
- 台账不存在 → exit 0（视为无降级）
- 只有 L-记录事件 → exit 0，但汇总中列出
- 存在未确认 L-显著 → exit 1 + 逐条列出 impact（断言输出里确实含每条的 impact 全文）
- --acknowledge <event_id> 后该条不再阻断；其余未确认的 L-显著仍继续阻断
  （证明"不支持批量确认"）
- 全部确认后 → exit 0

所有测试均使用临时台账文件（tmp_path + --log 参数 / 直接传 Path 给函数级 API），
不触碰项目真实的 research/.degradation-log.jsonl。
"""
from __future__ import annotations

import json

import degradation_report as dr


def _write_event(
    log_path,
    event_id: str,
    level: str,
    impact: str = "",
    acknowledged: bool = False,
    component: str = "outline_reader",
    reason: str = "yaml_parse_failed",
):
    """直接构造一条降级事件记录写入台账（不依赖 degradation_log.record_degradation
    的幂等/event_id 计算细节，测试只关心 degradation_report 的读取/汇总/阻断逻辑）。"""
    record = {
        "event_id": event_id,
        "ts": "2026-07-28T00:00:00+00:00",
        "stage": "assemble",
        "component": component,
        "reason": reason,
        "level": level,
        "fallback_used": "heuristic_text_match",
        "impact": impact,
        "acknowledged": acknowledged,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 台账不存在 → 视为无降级
# ---------------------------------------------------------------------------


def test_missing_log_file_is_not_blocking(tmp_path):
    log_path = tmp_path / "does-not-exist.jsonl"
    summary = dr.summarize(log_path)
    assert summary["log_exists"] is False
    assert summary["blocking"] is False
    assert summary["total_events"] == 0

    text = dr.format_text_report(summary)
    assert "无降级事件" in text or "可交付" in text


# ---------------------------------------------------------------------------
# 只有 L-记录事件 → 不阻断，但汇总中列出
# ---------------------------------------------------------------------------


def test_only_record_level_events_not_blocking_but_listed(tmp_path):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-record-1", dr.LEVEL_RECORD, impact="旧字段名使用")

    summary = dr.summarize(log_path)
    assert summary["blocking"] is False
    assert len(summary["record_events"]) == 1
    assert summary["record_events"][0]["event_id"] == "eid-record-1"

    text = dr.format_text_report(summary)
    assert "eid-record-1" in text
    assert "旧字段名使用" in text


# ---------------------------------------------------------------------------
# 存在未确认 L-显著 → 阻断 + 逐条列出 impact
# ---------------------------------------------------------------------------


def test_unacknowledged_significant_events_block_and_list_impact(tmp_path):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-sig-1", dr.LEVEL_SIGNIFICANT, impact="第一条影响描述：结构清单可能错误")
    _write_event(log_path, "eid-sig-2", dr.LEVEL_SIGNIFICANT, impact="第二条影响描述：小节丢失")
    _write_event(log_path, "eid-record-1", dr.LEVEL_RECORD, impact="记录级事件不影响阻断")

    summary = dr.summarize(log_path)
    assert summary["blocking"] is True
    assert len(summary["significant_unacknowledged"]) == 2

    text = dr.format_text_report(summary)
    # 逐条 impact 全文必须出现在输出中（不能只给计数）
    assert "第一条影响描述：结构清单可能错误" in text
    assert "第二条影响描述：小节丢失" in text
    assert "eid-sig-1" in text
    assert "eid-sig-2" in text


# ---------------------------------------------------------------------------
# --acknowledge 单条确认后该条不再阻断；其余未确认的仍阻断（不支持批量确认）
# ---------------------------------------------------------------------------


def test_acknowledge_single_event_leaves_others_blocking(tmp_path):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-sig-1", dr.LEVEL_SIGNIFICANT, impact="影响一")
    _write_event(log_path, "eid-sig-2", dr.LEVEL_SIGNIFICANT, impact="影响二")

    # 确认前：两条都阻断
    summary_before = dr.summarize(log_path)
    assert summary_before["blocking"] is True
    assert len(summary_before["significant_unacknowledged"]) == 2

    # 只确认 eid-sig-1
    dr._append_acknowledgement(log_path, "eid-sig-1")

    summary_after = dr.summarize(log_path)
    assert summary_after["blocking"] is True  # eid-sig-2 仍未确认，继续阻断
    unacked_ids = {ev["event_id"] for ev in summary_after["significant_unacknowledged"]}
    assert unacked_ids == {"eid-sig-2"}

    text_after = dr.format_text_report(summary_after)
    assert "eid-sig-2" in text_after
    assert "影响二" in text_after
    # eid-sig-1 不应再出现在"未确认"阻断列表里
    assert "eid-sig-1" not in text_after or "已确认" in text_after


def test_acknowledge_does_not_support_batch(tmp_path, monkeypatch, capsys):
    """CLI --acknowledge 只接受单个 event_id，不提供 --acknowledge-all（真实跑 --help 核实）。"""
    monkeypatch.setattr("sys.argv", ["degradation_report.py", "--help"])
    import pytest

    with pytest.raises(SystemExit):
        dr.main()
    help_text = capsys.readouterr().out
    assert "--acknowledge-all" not in help_text
    assert "--acknowledge" in help_text


# ---------------------------------------------------------------------------
# 全部确认后 → 不再阻断
# ---------------------------------------------------------------------------


def test_all_acknowledged_not_blocking(tmp_path):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-sig-1", dr.LEVEL_SIGNIFICANT, impact="影响一")
    _write_event(log_path, "eid-sig-2", dr.LEVEL_SIGNIFICANT, impact="影响二")

    dr._append_acknowledgement(log_path, "eid-sig-1")
    dr._append_acknowledgement(log_path, "eid-sig-2")

    summary = dr.summarize(log_path)
    assert summary["blocking"] is False
    assert summary["significant_unacknowledged"] == []

    text = dr.format_text_report(summary)
    assert "PASS" in text


# ---------------------------------------------------------------------------
# 已在写入时标记 acknowledged=True 的事件（degradation_log.record_degradation
# 的 acknowledged 参数）也应被视为已确认——不依赖必须有 acknowledgement 追加记录
# ---------------------------------------------------------------------------


def test_event_already_acknowledged_at_write_time_not_blocking(tmp_path):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-sig-1", dr.LEVEL_SIGNIFICANT, impact="影响一", acknowledged=True)

    summary = dr.summarize(log_path)
    assert summary["blocking"] is False


# ---------------------------------------------------------------------------
# CLI 层面：exit code
# ---------------------------------------------------------------------------


def test_cli_exit_code_missing_log(tmp_path, monkeypatch):
    log_path = tmp_path / "does-not-exist.jsonl"
    monkeypatch.setattr(
        "sys.argv", ["degradation_report.py", "--log", str(log_path)]
    )
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        dr.main()
    assert exc_info.value.code == 0


def test_cli_exit_code_blocking(tmp_path, monkeypatch):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-sig-1", dr.LEVEL_SIGNIFICANT, impact="影响一")
    monkeypatch.setattr(
        "sys.argv", ["degradation_report.py", "--log", str(log_path)]
    )
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        dr.main()
    assert exc_info.value.code == 1


def test_cli_acknowledge_flow(tmp_path, monkeypatch):
    log_path = tmp_path / "log.jsonl"
    _write_event(log_path, "eid-sig-1", dr.LEVEL_SIGNIFICANT, impact="影响一")
    monkeypatch.setattr(
        "sys.argv",
        ["degradation_report.py", "--log", str(log_path), "--acknowledge", "eid-sig-1"],
    )
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        dr.main()
    assert exc_info.value.code == 0

    # 确认记录已落盘（append，不是原地改写原始事件行）
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    ack_record = json.loads(lines[1])
    assert ack_record["record_type"] == "acknowledgement"
    assert ack_record["event_id"] == "eid-sig-1"
    # 原始事件行本身未被改写
    original_record = json.loads(lines[0])
    assert original_record["acknowledged"] is False


# ---------------------------------------------------------------------------
# 路径解析一致性：与 degradation_log.py 的 _resolve_log_path 完全一致
# ---------------------------------------------------------------------------


def test_path_resolution_matches_degradation_log(tmp_path, monkeypatch):
    import degradation_log as dl

    env_path = tmp_path / "env-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(env_path))

    # degradation_report 不传 --log 时应解析到与 degradation_log 相同的路径
    assert dr._resolve_log_path(None) == dl._resolve_log_path(None)
    assert dr._resolve_log_path(None) == env_path
