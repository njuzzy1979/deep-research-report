# -*- coding: utf-8 -*-
"""``scripts/phase_a_to_json.py`` 的单元测试（跨模型兼容性优化方案 §C4 手段 1/2）。

覆盖：
- confirm/adjust 两种形态的转换正确性
- 未知维度 id 报错（不在 auditor_contract.json 声明的 29 个 id 内）
- 产出通过 ``schemas/auditor-phase-a.schema.json`` 校验
- 分批合并 + 批次不完整（缺批次/dims 数不符/id 集合与 batch_grouping 不符）报错
"""
from __future__ import annotations

import json

import pytest

import phase_a_to_json as p
import schema_validate as sv


# ---------------------------------------------------------------------------
# 基础解析：confirm / adjust
# ---------------------------------------------------------------------------


def test_parse_confirm_dimension():
    text = "### outline_coverage\nconfirm\n"
    dims = p.parse_markdown_dimensions(text)
    assert dims == {"outline_coverage": {"mode": "confirm"}}


def test_parse_adjust_dimension():
    text = "### strong_claim\nadjust: 本章因涉及新兴技术需放宽首次性判断阈值\n"
    dims = p.parse_markdown_dimensions(text)
    assert dims == {
        "strong_claim": {
            "mode": "adjust",
            "text": "本章因涉及新兴技术需放宽首次性判断阈值",
        }
    }


def test_parse_multiple_dimensions_mixed_modes():
    text = (
        "### outline_coverage\n"
        "confirm\n"
        "\n"
        "### strong_claim\n"
        "adjust: 需要调整\n"
        "\n"
        "### C1_h1\n"
        "confirm\n"
    )
    dims = p.parse_markdown_dimensions(text)
    assert dims == {
        "outline_coverage": {"mode": "confirm"},
        "strong_claim": {"mode": "adjust", "text": "需要调整"},
        "C1_h1": {"mode": "confirm"},
    }


def test_parse_missing_content_line_raises():
    text = "### outline_coverage\n"
    with pytest.raises(ValueError, match="缺少 confirm/adjust 内容行"):
        p.parse_markdown_dimensions(text)


def test_parse_adjust_missing_text_raises():
    text = "### strong_claim\nadjust:\n"
    with pytest.raises(ValueError, match="缺少说明文本"):
        p.parse_markdown_dimensions(text)


def test_parse_invalid_content_line_raises():
    text = "### outline_coverage\n某种既非confirm也非adjust的文本\n"
    with pytest.raises(ValueError, match="既非 'confirm' 也非"):
        p.parse_markdown_dimensions(text)


def test_parse_duplicate_dimension_raises():
    text = "### outline_coverage\nconfirm\n\n### outline_coverage\nconfirm\n"
    with pytest.raises(ValueError, match="重复出现"):
        p.parse_markdown_dimensions(text)


# ---------------------------------------------------------------------------
# 未知维度 id 校验
# ---------------------------------------------------------------------------


def test_known_dimension_ids_count_is_29():
    ids = p.load_known_dimension_ids()
    assert len(ids) == 29


def test_parse_single_file_rejects_unknown_id(tmp_path):
    known_ids = p.load_known_dimension_ids()
    f = tmp_path / "ch01-precommit.md"
    f.write_text("### outline_coverage\nconfirm\n\n### unknown_dim_xyz\nconfirm\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown_dim_xyz"):
        p.parse_single_file(str(f), known_ids)


def test_parse_single_file_accepts_known_id(tmp_path):
    known_ids = p.load_known_dimension_ids()
    f = tmp_path / "ch01-precommit.md"
    f.write_text("### outline_coverage\nconfirm\n", encoding="utf-8")
    dims = p.parse_single_file(str(f), known_ids)
    assert dims == {"outline_coverage": {"mode": "confirm"}}


# ---------------------------------------------------------------------------
# 产出通过 schema 校验（全量 29 维度 + 单维度）
# ---------------------------------------------------------------------------


def test_build_output_full_29_dims_passes_schema():
    ids = sorted(p.load_known_dimension_ids())
    dims = {i: {"mode": "confirm"} for i in ids}
    output = p.build_output("ch01", dims)
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(output, schema)
    assert result["valid"], result["errors"]


def test_build_output_with_adjust_passes_schema():
    output = p.build_output("ch02", {
        "outline_coverage": {"mode": "confirm"},
        "strong_claim": {"mode": "adjust", "text": "调整理由"},
    })
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(output, schema)
    assert result["valid"], result["errors"]


def test_build_output_invalid_chapter_id_fails_schema():
    output = {"chapter_one": {"outline_coverage": {"mode": "confirm"}}}
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(output, schema)
    assert not result["valid"]


# ---------------------------------------------------------------------------
# 批次元数据解析
# ---------------------------------------------------------------------------


def test_parse_batch_metadata_present():
    text = "<!-- phase=A batch=1 chapter=ch01 dims=8 -->\n\n### outline_coverage\nconfirm\n"
    meta = p.parse_batch_metadata(text)
    assert meta == {"phase": "A", "batch": 1, "chapter": "ch01", "dims": 8}


def test_parse_batch_metadata_absent_returns_none():
    text = "### outline_coverage\nconfirm\n"
    assert p.parse_batch_metadata(text) is None


# ---------------------------------------------------------------------------
# 分批合并：完整场景
# ---------------------------------------------------------------------------


def _write_batch_files(tmp_path, chapter="ch04"):
    """按 batch_grouping 真实分组写出 3 份完整批次文件，返回路径列表。"""
    batch_grouping = p.load_batch_grouping()
    paths = []
    for num, key in [(1, "batch1_high"), (2, "batch2_mid"), (3, "batch3_low")]:
        ids = batch_grouping[key]
        lines = [f"<!-- phase=A batch={num} chapter={chapter} dims={len(ids)} -->", ""]
        for dim_id in ids:
            lines.append(f"### {dim_id}")
            lines.append("confirm")
            lines.append("")
        f = tmp_path / f"{chapter}-precommit-batch{num}.md"
        f.write_text("\n".join(lines), encoding="utf-8")
        paths.append(str(f))
    return paths


def test_merge_batch_files_complete_succeeds(tmp_path):
    paths = _write_batch_files(tmp_path, chapter="ch04")
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    merged = p.merge_batch_files(paths, "ch04", known_ids, batch_grouping)
    assert len(merged) == 29
    assert set(merged) == known_ids


def test_merge_batch_files_output_passes_schema(tmp_path):
    paths = _write_batch_files(tmp_path, chapter="ch04")
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    merged = p.merge_batch_files(paths, "ch04", known_ids, batch_grouping)
    output = p.build_output("ch04", merged)
    schema = sv.load_schema("auditor-phase-a")
    result = sv.validate_instance(output, schema)
    assert result["valid"], result["errors"]


# ---------------------------------------------------------------------------
# 分批合并：不完整场景（不允许静默拼接）
# ---------------------------------------------------------------------------


def test_merge_batch_files_missing_batch_raises(tmp_path):
    paths = _write_batch_files(tmp_path, chapter="ch04")
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    with pytest.raises(ValueError, match="批次不完整"):
        p.merge_batch_files(paths[:2], "ch04", known_ids, batch_grouping)


def test_merge_batch_files_no_metadata_raises(tmp_path):
    f = tmp_path / "ch05-precommit-batch1.md"
    f.write_text("### outline_coverage\nconfirm\n", encoding="utf-8")
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    with pytest.raises(ValueError, match="缺少批次元数据"):
        p.merge_batch_files([str(f)], "ch05", known_ids, batch_grouping)


def test_merge_batch_files_dims_count_mismatch_raises(tmp_path):
    f = tmp_path / "ch05-precommit-batch1.md"
    f.write_text(
        "<!-- phase=A batch=1 chapter=ch05 dims=9 -->\n\n### outline_coverage\nconfirm\n",
        encoding="utf-8",
    )
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    with pytest.raises(ValueError, match="批次不完整"):
        p.merge_batch_files([str(f)], "ch05", known_ids, batch_grouping)


def test_merge_batch_files_id_set_mismatch_raises(tmp_path):
    batch_grouping = p.load_batch_grouping()
    known_ids = p.load_known_dimension_ids()
    ids = batch_grouping["batch1_high"]
    wrong_ids = ids[:-1] + [batch_grouping["batch2_mid"][0]]
    lines = [f"<!-- phase=A batch=1 chapter=ch06 dims={len(wrong_ids)} -->", ""]
    for dim_id in wrong_ids:
        lines.append(f"### {dim_id}")
        lines.append("confirm")
        lines.append("")
    f = tmp_path / "ch06-precommit-batch1.md"
    f.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="批次不完整"):
        p.merge_batch_files([str(f)], "ch06", known_ids, batch_grouping)


def test_merge_batch_files_duplicate_batch_number_raises(tmp_path):
    paths = _write_batch_files(tmp_path, chapter="ch04")
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    # 用 batch1 文件替换 batch3，制造批次号 1 重复出现
    dup_paths = [paths[0], paths[1], paths[0]]
    with pytest.raises(ValueError, match="重复出现"):
        p.merge_batch_files(dup_paths, "ch04", known_ids, batch_grouping)


def test_merge_batch_files_chapter_mismatch_raises(tmp_path):
    paths = _write_batch_files(tmp_path, chapter="ch04")
    known_ids = p.load_known_dimension_ids()
    batch_grouping = p.load_batch_grouping()
    with pytest.raises(ValueError, match="不一致"):
        p.merge_batch_files(paths, "ch99", known_ids, batch_grouping)


# ---------------------------------------------------------------------------
# CLI 层：main() 通过 subprocess 或直接调用 argparse 路径的端到端校验，
# 借助上面已验证的纯函数即可覆盖核心逻辑，CLI 参数校验用 build_output +
# schema 校验的组合已在上方间接覆盖，这里不重复起子进程。
# ---------------------------------------------------------------------------


def test_read_text_strips_bom_and_normalizes_crlf(tmp_path):
    f = tmp_path / "sample.md"
    f.write_bytes(b"\xef\xbb\xbf### outline_coverage\r\nconfirm\r\n")
    text = p.read_text(str(f))
    assert not text.startswith("﻿")
    assert "\r" not in text
