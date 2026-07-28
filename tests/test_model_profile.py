# -*- coding: utf-8 -*-
"""model_profile.py 的单元测试（跨模型兼容性优化方案 §C1/§C2）。

覆盖用户任务书点名的三条路径 + derive_phase_a_mode 边界值 +
resolve_collaboration_mode 硬规则 + 三份 example / 主文件的 schema 合法性与
默认值断言。所有测试用 monkeypatch.setenv("DRR_DEGRADATION_LOG", ...) 隔离
台账，避免污染真实台账（参考 tests/test_output_envelope_check.py 的既有模式）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import model_profile as mp
import schema_validate as sv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate_degradation_log(tmp_path, monkeypatch):
    """自动应用于本文件全部测试：隔离降级台账，防止污染真实 research/.degradation-log.jsonl。"""
    log_path = tmp_path / "degradation-log.jsonl"
    monkeypatch.setenv("DRR_DEGRADATION_LOG", str(log_path))
    return log_path


# ---------------------------------------------------------------------------
# 路径 1：文件不存在 -> tier A
# ---------------------------------------------------------------------------


def test_missing_file_falls_back_to_tier_a(tmp_path, _isolate_degradation_log):
    missing = tmp_path / "no-such-model-profile.json"
    profile = mp.load_profile(str(missing))

    assert profile["_source"] == "fallback_tier_a_missing"
    assert profile["capability_tier"] == "A"
    assert profile["phase_a_mode"] == "free"

    # 写了台账
    log_lines = _isolate_degradation_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 1
    record = json.loads(log_lines[0])
    assert record["reason"] == "profile_file_missing"
    assert record["component"] == "model_profile"


# ---------------------------------------------------------------------------
# 路径 2：文件存在但 JSON 解析失败 -> tier C
# ---------------------------------------------------------------------------


def test_invalid_json_falls_back_to_tier_c(tmp_path, _isolate_degradation_log):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ this is not valid json ,,, ", encoding="utf-8")

    profile = mp.load_profile(str(bad_file))

    assert profile["_source"] == "fallback_tier_c_invalid"
    assert profile["capability_tier"] == "C"

    log_lines = _isolate_degradation_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 1
    record = json.loads(log_lines[0])
    assert record["reason"] == "profile_json_parse_failed"
    assert record["level"] == "L-显著"


# ---------------------------------------------------------------------------
# 路径 3：文件存在但 schema 校验失败 -> tier C
# ---------------------------------------------------------------------------


def test_schema_invalid_falls_back_to_tier_c(tmp_path, _isolate_degradation_log):
    bad_file = tmp_path / "schema-invalid.json"
    bad_file.write_text(json.dumps({
        "capability_tier": "Z",  # 非法枚举值
        "host": {"agent_delegation": True},
        "limits": {"max_output_tokens": 64000},
        "policy": {"hard_rule_budget": 0, "envelope_nonce": False, "template_fill_mode": "off"},
    }), encoding="utf-8")

    profile = mp.load_profile(str(bad_file))

    assert profile["_source"] == "fallback_tier_c_invalid"
    assert profile["capability_tier"] == "C"

    log_lines = _isolate_degradation_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 1
    record = json.loads(log_lines[0])
    assert record["reason"] == "profile_schema_invalid"


# ---------------------------------------------------------------------------
# 路径 4：文件存在且合法 -> 按声明的 tier 运行（分别测 A/B/C 三份 example）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("example_file,expected_tier", [
    ("model-profile.claude.example.json", "A"),
    ("model-profile.deepseek.example.json", "B"),
    ("model-profile.unknown.example.json", "C"),
])
def test_valid_example_loads_declared_tier(example_file, expected_tier, _isolate_degradation_log):
    path = PROJECT_ROOT / example_file
    profile = mp.load_profile(str(path))

    assert profile["_source"] == "file"
    assert profile["capability_tier"] == expected_tier

    # 合法加载不应写台账
    assert not _isolate_degradation_log.exists() or _isolate_degradation_log.read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------------------
# derive_phase_a_mode 边界值
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tokens,expected", [
    (64000, "free"),
    (8000, "confirm"),
    (16000, "free"),      # 边界值：恰为阈值 -> free（< 16000 才 confirm）
    (15999, "confirm"),   # 阈值前一格 -> confirm
])
def test_derive_phase_a_mode_boundaries(tokens, expected):
    assert mp.derive_phase_a_mode(tokens) == expected


# ---------------------------------------------------------------------------
# resolve_collaboration_mode 硬规则
# ---------------------------------------------------------------------------


def test_tier_c_full_mode_degrades_to_layered(_isolate_degradation_log):
    profile = {"capability_tier": "C", "host": {"agent_delegation": True}}
    mode, reason = mp.resolve_collaboration_mode(profile, mp.MODE_FULL)

    assert mode == mp.MODE_LAYERED
    assert reason is not None

    log_lines = _isolate_degradation_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 1
    record = json.loads(log_lines[0])
    assert record["reason"] == "tier_c_full_mode_forbidden"


def test_tier_a_full_mode_does_not_degrade(_isolate_degradation_log):
    profile = {"capability_tier": "A", "host": {"agent_delegation": True}}
    mode, reason = mp.resolve_collaboration_mode(profile, mp.MODE_FULL)

    assert mode == mp.MODE_FULL
    assert reason is None
    assert not _isolate_degradation_log.exists() or _isolate_degradation_log.read_text(encoding="utf-8").strip() == ""


def test_agent_delegation_false_forces_solo_mode(_isolate_degradation_log):
    profile = {"capability_tier": "A", "host": {"agent_delegation": False}}
    mode, reason = mp.resolve_collaboration_mode(profile, mp.MODE_FULL)

    assert mode == mp.MODE_SOLO
    assert reason is not None

    log_lines = _isolate_degradation_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 1
    record = json.loads(log_lines[0])
    assert record["reason"] == "agent_delegation_disabled"


def test_agent_delegation_false_and_already_solo_no_extra_log(_isolate_degradation_log):
    """已经请求单 Agent 极速档时，即使 agent_delegation=false，也不算"降级"，不写台账。"""
    profile = {"capability_tier": "A", "host": {"agent_delegation": False}}
    mode, reason = mp.resolve_collaboration_mode(profile, mp.MODE_SOLO)

    assert mode == mp.MODE_SOLO
    assert reason is None
    assert not _isolate_degradation_log.exists() or _isolate_degradation_log.read_text(encoding="utf-8").strip() == ""


def test_tier_b_full_mode_not_forced_to_degrade():
    """Tier B × 完整多 Agent 未经实测但未被禁止（方案仅风险标注，非硬规则）。"""
    profile = {"capability_tier": "B", "host": {"agent_delegation": True}}
    mode, reason = mp.resolve_collaboration_mode(profile, mp.MODE_FULL)

    assert mode == mp.MODE_FULL
    assert reason is None


def test_resolve_collaboration_mode_rejects_unknown_mode():
    profile = {"capability_tier": "A", "host": {"agent_delegation": True}}
    with pytest.raises(ValueError):
        mp.resolve_collaboration_mode(profile, "不存在的档位")


# ---------------------------------------------------------------------------
# 三份 example 文件均通过 schema 校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("example_file", [
    "model-profile.json",
    "model-profile.claude.example.json",
    "model-profile.deepseek.example.json",
    "model-profile.unknown.example.json",
])
def test_example_files_pass_schema_validation(example_file):
    path = PROJECT_ROOT / example_file
    instance = json.loads(path.read_text(encoding="utf-8"))
    schema = sv.load_schema("model-profile")
    result = sv.validate_instance(instance, schema)
    assert result["valid"], f"{example_file} 未通过 schema 校验: {result['errors']}"


# ---------------------------------------------------------------------------
# model-profile.json 主文件是 tier A 且各 policy 为方案规定的默认值
# ---------------------------------------------------------------------------


def test_main_profile_file_is_tier_a_with_spec_defaults():
    """这是"Claude 路径字节级不变"的配置层保证：主文件必须是 tier A 全 off。"""
    path = PROJECT_ROOT / "model-profile.json"
    instance = json.loads(path.read_text(encoding="utf-8"))

    assert instance["capability_tier"] == "A"
    assert instance["host"]["agent_delegation"] is True
    assert instance["limits"]["max_output_tokens"] == 64000
    assert instance["policy"]["hard_rule_budget"] == 0
    assert instance["policy"]["envelope_nonce"] is False
    assert instance["policy"]["template_fill_mode"] == "off"


# ---------------------------------------------------------------------------
# model-profile.json 与三份 example 均不含 phase_a_mode 字段
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("example_file", [
    "model-profile.json",
    "model-profile.claude.example.json",
    "model-profile.deepseek.example.json",
    "model-profile.unknown.example.json",
])
def test_profile_files_do_not_contain_phase_a_mode_field(example_file):
    path = PROJECT_ROOT / example_file
    instance = json.loads(path.read_text(encoding="utf-8"))
    assert "phase_a_mode" not in instance
    assert "phase_a_mode" not in instance.get("policy", {})
    assert "phase_a_mode" not in instance.get("limits", {})
