# -*- coding: utf-8 -*-
"""output_envelope_check.py 的单元测试（跨模型兼容性优化方案 §三 B1）。

覆盖方案验收标准明确要求的场景：
- 正常信封（无 nonce / 带 nonce 且匹配）通过
- nonce 不匹配 → 降级为无 nonce 匹配 + 写台账，且仍能提取有效载荷
- 标记缺失 / 标记多对 / START-END agent 名不一致 → 失败
- 纯中文正文噪声比率 = 0（无误报）—— 专门测试
- 含 U+FFFD 与进度条字符的输入 → 噪声比率 > 0，超 30% 判失败
- --extract-to 能正确落盘有效载荷
"""
from __future__ import annotations

import json

import output_envelope_check as oec


AGENT = "chapter_writer_agent"


def _wrap(payload: str, agent: str = AGENT, nonce: str | None = None, end_agent: str | None = None) -> str:
    """构造一份带标记的原始输出文本。"""
    end_agent = agent if end_agent is None else end_agent
    if nonce:
        return f"[AGENT-OUTPUT-START:{nonce}] {agent}\n{payload}\n[AGENT-OUTPUT-END:{nonce}] {end_agent}\n"
    return f"[AGENT-OUTPUT-START] {agent}\n{payload}\n[AGENT-OUTPUT-END] {end_agent}\n"


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_normal_envelope_without_nonce_passes():
    text = _wrap("正常输出内容。")
    r = oec.run_check(text, AGENT, expected_nonce=None)
    assert r["pairing_ok"] is True
    assert r["agent_matched"] is True
    assert r["envelope_ok"] is True
    assert r["nonce_matched"] is None  # 未提供 --nonce，跳过校验
    assert r["overall_pass"] is True


def test_normal_envelope_with_matching_nonce_passes():
    text = _wrap("带 nonce 的正常输出。", nonce="a7f3c9d2")
    r = oec.run_check(text, AGENT, expected_nonce="a7f3c9d2")
    assert r["pairing_ok"] is True
    assert r["agent_matched"] is True
    assert r["nonce_matched"] is True
    assert r["degrade_reason"] is None
    assert r["overall_pass"] is True


# ---------------------------------------------------------------------------
# nonce 不匹配 → 降级
# ---------------------------------------------------------------------------


def test_nonce_mismatch_degrades_to_no_nonce_match_and_logs(tmp_path, monkeypatch):
    log_path = tmp_path / "degradation-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(log_path))

    text = _wrap("nonce 不匹配的输出。", nonce="deadbeef")
    r = oec.run_check(text, AGENT, expected_nonce="a7f3c9d2", input_path="fake.txt")

    # 降级为无 nonce 匹配：信封本身（标记配对 + agent 名）仍判定通过
    assert r["nonce_matched"] is False
    assert r["degrade_reason"] == "nonce_mismatch"
    assert r["envelope_ok"] is True  # 降级不阻断信封判定
    # 降级后仍能正确提取有效载荷
    assert r["payload_path"] is None  # 未指定 --extract-to 时为 None
    assert "nonce 不匹配的输出。" in oec.check_envelope(text, AGENT, "a7f3c9d2")["payload"]

    # 台账已写入
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["reason"] == "nonce_mismatch"
    assert record["component"] == "output_envelope_check"
    assert record["level"] == "L-记录"


def test_nonce_missing_when_expected_also_degrades_and_logs(tmp_path, monkeypatch):
    """START/END 标记本身不带 nonce，但调用方期望某个 nonce —— 也应降级并写台账。"""
    log_path = tmp_path / "degradation-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(log_path))

    text = _wrap("没有 nonce 的输出。")  # 旧格式，标记内无 nonce
    r = oec.run_check(text, AGENT, expected_nonce="a7f3c9d2", input_path="fake.txt")

    assert r["nonce_matched"] is False
    assert r["degrade_reason"] == "nonce_missing"
    assert r["envelope_ok"] is True
    assert log_path.exists()
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["reason"] == "nonce_missing"


# ---------------------------------------------------------------------------
# 失败路径：标记缺失 / 多对 / agent 名不一致
# ---------------------------------------------------------------------------


def test_missing_markers_fails():
    text = "没有任何信封标记的纯文本。"
    r = oec.run_check(text, AGENT)
    assert r["pairing_ok"] is False
    assert r["start_count"] == 0
    assert r["end_count"] == 0
    assert r["envelope_ok"] is False
    assert r["overall_pass"] is False


def test_multiple_pairs_fails():
    text = _wrap("first") + _wrap("second")
    r = oec.run_check(text, AGENT)
    assert r["start_count"] == 2
    assert r["end_count"] == 2
    assert r["pairing_ok"] is False
    assert r["overall_pass"] is False


def test_start_end_agent_mismatch_fails():
    text = _wrap("mismatched agent content", end_agent="chapter_auditor_agent")
    r = oec.run_check(text, AGENT)
    assert r["pairing_ok"] is True  # 标记本身仍成对
    assert r["agent_matched"] is False  # 但 START/END agent 名不一致
    assert r["envelope_ok"] is False
    assert r["overall_pass"] is False


def test_agent_name_differs_from_expected_fails():
    """标记内 START/END 一致，但与调用方期望的 agent 名不同 —— 防跨 Agent 输出粘连。"""
    text = _wrap("wrong agent entirely", agent="chapter_auditor_agent", end_agent="chapter_auditor_agent")
    r = oec.run_check(text, AGENT)
    assert r["pairing_ok"] is True
    assert r["agent_matched"] is False
    assert r["envelope_ok"] is False


# ---------------------------------------------------------------------------
# 噪声比率：纯中文正文必须为 0（方案验收标准明确项，无误报）
# ---------------------------------------------------------------------------


def test_pure_chinese_body_noise_ratio_is_zero():
    chinese_body = "本章讨论空间态势感知系统的技术演进路径与关键节点分析。" * 30
    text = _wrap(chinese_body)
    r = oec.run_check(text, AGENT)
    assert r["noise_ratio"] == 0.0
    assert r["noise_pass"] is True
    assert r["noise_detail"]["cjk_chars"] > 0


def test_replacement_char_and_progress_bar_increase_noise_ratio_and_fail():
    # 构造一段噪声占比明显超过 30% 阈值的载荷
    noisy_payload = "正常文字" + "�" * 40 + "█▓▏▎" * 10 + "正常文字结尾"
    text = _wrap(noisy_payload)
    r = oec.run_check(text, AGENT)
    assert r["noise_ratio"] > 0.30
    assert r["noise_pass"] is False
    assert r["overall_pass"] is False
    assert r["noise_detail"]["replacement_char_count"] == 40
    assert r["noise_detail"]["progress_bar_char_count"] > 0


def test_low_noise_ratio_below_threshold_passes():
    # 极少量噪声字符，占比远低于 30%
    body = "正常中文段落内容占据绝大多数字符" * 10 + "�"
    text = _wrap(body)
    r = oec.run_check(text, AGENT)
    assert 0 < r["noise_ratio"] <= 0.30
    assert r["noise_pass"] is True
    assert r["overall_pass"] is True


# ---------------------------------------------------------------------------
# --extract-to 落盘
# ---------------------------------------------------------------------------


def test_extract_to_writes_payload_to_disk(tmp_path):
    text = _wrap("需要落盘的有效载荷内容。")
    out_path = tmp_path / "extracted.txt"
    r = oec.run_check(text, AGENT, extract_to=str(out_path))
    assert r["payload_path"] == str(out_path)
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8").strip() == "需要落盘的有效载荷内容。"


def test_extract_to_not_written_when_pairing_fails(tmp_path):
    text = "没有标记的文本。"
    out_path = tmp_path / "extracted.txt"
    r = oec.run_check(text, AGENT, extract_to=str(out_path))
    assert r["payload_path"] is None
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# read_text：BOM / CRLF 处理（对齐 contract_check.py 同款约定）
# ---------------------------------------------------------------------------


def test_read_text_strips_bom_and_normalizes_crlf(tmp_path):
    raw = b"\xef\xbb\xbf[AGENT-OUTPUT-START] chapter_writer_agent\r\ncontent\r\n[AGENT-OUTPUT-END] chapter_writer_agent\r\n"
    p = tmp_path / "bom_crlf.txt"
    p.write_bytes(raw)
    text = oec.read_text(str(p))
    assert not text.startswith("﻿")
    assert "\r\n" not in text
    r = oec.run_check(text, AGENT)
    assert r["envelope_ok"] is True
