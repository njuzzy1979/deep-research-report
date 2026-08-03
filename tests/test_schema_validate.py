# -*- coding: utf-8 -*-
"""schema_validate.py 的单元测试（跨模型兼容性优化方案 §三 B3）。

覆盖方案验收标准明确要求的场景：
- 5 份 schema 全部是合法的 Draft 2020-12 schema（check_schema 逐份验证）
- 缺字段 / 类型错 / 枚举越界三类错误都能捕获并给出可回传的错误消息
- model-profile.schema.json 不含 phase_a_mode 字段（断言）
- --check-sync 能检出契约与 schema 不同步
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import schema_validate as sv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = PROJECT_ROOT / "schemas"


# ---------------------------------------------------------------------------
# 5 份 schema 均为合法 Draft 2020-12 schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sv.SCHEMA_NAMES)
def test_schema_is_valid_draft202012(name):
    schema = sv.load_schema(name)
    # 不抛异常即视为合法；check_schema 在非法时抛 SchemaError
    Draft202012Validator.check_schema(schema)


def test_all_five_schema_files_exist_on_disk():
    for name in sv.SCHEMA_NAMES:
        path = SCHEMA_DIR / f"{name}.schema.json"
        assert path.exists(), f"缺少 schema 文件: {path}"


@pytest.mark.parametrize("name", sv.SCHEMA_NAMES)
def test_schema_has_x_generated_from_field(name):
    schema = sv.load_schema(name)
    assert "x-generated-from" in schema
    assert schema["x-generated-from"]  # 非空


# ---------------------------------------------------------------------------
# model-profile.schema.json 不含 phase_a_mode 字段（方案 §C4 明确要求）
# ---------------------------------------------------------------------------


def test_model_profile_schema_does_not_contain_phase_a_mode():
    """phase_a_mode 由 limits.max_output_tokens 派生（方案 §C4），是派生量，
    不得作为独立字段出现在 schema 的任何 properties/required 中。
    （description 中提及该词用于说明"为何不收录"是允许的，本测试只断言
    它不作为字段名出现——不能用粗暴的全字符串搜索，那会连解释性文字都误伤。）
    """
    schema = sv.load_schema("model-profile")

    def _collect_property_keys(node) -> set:
        keys = set()
        if isinstance(node, dict):
            if "properties" in node and isinstance(node["properties"], dict):
                keys.update(node["properties"].keys())
            if "required" in node and isinstance(node["required"], list):
                keys.update(node["required"])
            for v in node.values():
                keys.update(_collect_property_keys(v))
        elif isinstance(node, list):
            for item in node:
                keys.update(_collect_property_keys(item))
        return keys

    all_field_names = _collect_property_keys(schema)
    assert "phase_a_mode" not in all_field_names


# ---------------------------------------------------------------------------
# writer-selfclaim: 缺字段 / 类型错 三类错误捕获
# ---------------------------------------------------------------------------


def _valid_writer_selfclaim() -> dict:
    return {
        "chapter_char_count": 3200,
        "figure_count": 2,
        "table_count": 1,
        "cited_card_ids": ["CASE-01", "TECH-03"],
        "backfilled_used_in_chapter": ["CASE-01"],
        "material_gap_markers": [],
    }


def test_writer_selfclaim_valid_instance_passes():
    schema = sv.load_schema("writer-selfclaim")
    result = sv.validate_instance(_valid_writer_selfclaim(), schema)
    assert result["valid"] is True
    assert result["error_count"] == 0
    assert result["repair_prompt"] is None


def test_writer_selfclaim_missing_field_fails_with_repair_prompt():
    instance = _valid_writer_selfclaim()
    del instance["table_count"]
    schema = sv.load_schema("writer-selfclaim")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False
    assert result["error_count"] >= 1
    assert result["repair_prompt"].startswith("请修正以下字段：")
    assert "table_count" in result["repair_prompt"]


def test_writer_selfclaim_wrong_type_fails():
    instance = _valid_writer_selfclaim()
    instance["figure_count"] = "两张"  # 应为 integer
    schema = sv.load_schema("writer-selfclaim")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False
    assert any(e["path"] == "figure_count" for e in result["errors"])


# ---------------------------------------------------------------------------
# auditor-phase-a: 枚举越界（非法维度 id / 非法 mode 值）
# ---------------------------------------------------------------------------


def test_auditor_phase_a_valid_instance_passes():
    instance = {
        "ch01": {
            "D1_argument_depth": {"mode": "confirm"},
            "D5_structure": {"mode": "adjust", "text": "本章缺少章首结论 blockquote，需补充"},
        }
    }
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is True


def test_auditor_phase_a_invalid_dimension_id_fails_enum():
    instance = {"ch01": {"not_a_real_dimension": {"mode": "confirm"}}}
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False


def test_auditor_phase_a_invalid_mode_enum_fails():
    instance = {"ch01": {"D1_argument_depth": {"mode": "maybe"}}}  # 非法枚举值
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False


def test_auditor_phase_a_adjust_without_text_fails():
    """adjust 模式必须带 text（方案 §C4 落盘形态要求）。"""
    instance = {"ch01": {"D5_structure": {"mode": "adjust"}}}  # 缺 text
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False


# ---------------------------------------------------------------------------
# auditor-phase-b: verdict 枚举越界 + issue 清单结构校验
# ---------------------------------------------------------------------------


def _valid_auditor_phase_b() -> dict:
    return {
        "chapter_id": "ch01",
        "verdict": "PASS",
        "dimension_scores": {
            "D1_argument_depth": {"verdict": "pass", "evidence": "论证深度充分，各节均含实质性 Warranty"},
        },
        "issues": [],
    }


def test_auditor_phase_b_valid_instance_passes():
    schema = sv.load_schema("auditor-phase-b")
    result = sv.validate_instance(_valid_auditor_phase_b(), schema)
    assert result["valid"] is True


def test_auditor_phase_b_invalid_verdict_enum_fails():
    instance = _valid_auditor_phase_b()
    instance["verdict"] = "MAYBE"  # 契约 verdict 枚举只有 PASS/REVISE
    schema = sv.load_schema("auditor-phase-b")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False


def test_auditor_phase_b_issue_missing_field_fails():
    instance = _valid_auditor_phase_b()
    instance["verdict"] = "REVISE"
    instance["issues"] = [{"dimension": "D1_argument_depth", "location": "第2节"}]  # 缺 problem/suggested_fix
    schema = sv.load_schema("auditor-phase-b")
    result = sv.validate_instance(instance, schema)
    assert result["valid"] is False
    assert result["repair_prompt"].startswith("请修正以下字段：")


# ---------------------------------------------------------------------------
# --check-sync：检出契约与 schema 不同步
# ---------------------------------------------------------------------------


def test_check_sync_all_synced_right_after_regenerate(tmp_path, monkeypatch):
    """紧跟 regenerate 之后，check_sync 对 auto 类schema应全部同步。"""
    result = sv.check_sync()
    for name, kind in sv.SCHEMA_SYNC_KIND.items():
        if kind == "auto":
            assert result["detail"][name]["synced"] is True, f"{name} 应与真源同步"
        else:
            assert result["detail"][name]["status"] == "skipped"
    assert result["all_synced"] is True


def test_check_sync_detects_out_of_sync_schema(tmp_path, monkeypatch):
    """手工改动某份 auto schema 磁盘内容，check_sync 应检出不同步。"""
    monkeypatch.setattr(sv, "SCHEMA_DIR", tmp_path)

    def _fake_schema_path(name):
        return tmp_path / f"{name}.schema.json"

    monkeypatch.setattr(sv, "_schema_path", _fake_schema_path)

    # 先按当前真源写入一份"正确"的 schema
    fresh = sv.derive_writer_selfclaim_schema()
    (tmp_path / "writer-selfclaim.schema.json").write_text(
        json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 篡改磁盘上的内容，制造不同步
    tampered = dict(fresh)
    tampered["title"] = "被篡改的标题（模拟漂移）"
    (tmp_path / "writer-selfclaim.schema.json").write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = sv.check_sync()
    assert result["detail"]["writer-selfclaim"]["synced"] is False
    assert result["all_synced"] is False


def test_check_sync_manual_schemas_are_skipped_not_flagged():
    result = sv.check_sync()
    assert result["detail"]["outline-structure"]["status"] == "skipped"
    assert result["detail"]["model-profile"]["status"] == "skipped"


# ---------------------------------------------------------------------------
# CLI 层：--help / exit code 冒烟（不依赖 subprocess 的测试已覆盖核心逻辑，
# 这里仅验证命令行入口本身可用，供自查环节交叉确认）
# ---------------------------------------------------------------------------


def test_cli_help_runs_without_crash():
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "schema_validate.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0
    assert "schema" in proc.stdout.lower()


def test_cli_validate_valid_target_returns_exit_0(tmp_path):
    target = tmp_path / "selfclaim.json"
    target.write_text(json.dumps(_valid_auditor_phase_b(), ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "schema_validate.py"),
         str(target), "--schema", "auditor-phase-b", "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert result["valid"] is True


def test_cli_validate_invalid_target_returns_exit_1(tmp_path):
    target = tmp_path / "bad.json"
    instance = _valid_writer_selfclaim()
    del instance["chapter_char_count"]
    target.write_text(json.dumps(instance, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "schema_validate.py"),
         str(target), "--schema", "writer-selfclaim", "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["valid"] is False


def test_cli_missing_target_file_returns_exit_2():
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "schema_validate.py"),
         "nonexistent_file_xyz.json", "--schema", "writer-selfclaim"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 2
