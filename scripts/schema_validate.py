#!/usr/bin/env python3
"""通用 JSON Schema 校验器 + repair loop 错误消息格式化（跨模型兼容性优化方案 §三 B3）。

设计要点（方案 §B3）：现有 ``agents/contracts/*.json`` 是**叙述性 schema**
（``requirement`` 为自然语言），不能直接 ``jsonschema.validate()``。本脚本在
``schemas/`` 下维护 5 份机读 schema（Draft 2020-12），每份带
``x-generated-from`` 字段标明来源——**真源仍是叙述性契约（或人工维护的参考
文档），schema 是派生产物，不手工维护两份真源**：

    - ``writer-selfclaim``    ← agents/contracts/writer_contract.json#/self_declaration_fields（自动派生）
    - ``auditor-phase-a``     ← agents/contracts/auditor_contract.json#/dimensions（自动派生维度 id 枚举）+ 方案 §C4（JSON 落盘形态，人工设计）
    - ``auditor-phase-b``     ← agents/contracts/auditor_contract.json#/dimensions,/verdict（自动派生）+ agents/chapter_auditor_agent.md Phase B 小节（人工设计 issue 清单结构）
    - ``outline-structure``   ← references/stage-4-outline.md §4.1.y/§4.1.z（人工维护，无 JSON 上游契约）
    - ``model-profile``       ← design/model-compatibility-optimization-plan.md §C1（人工维护，本批次尚无 model-profile.json 本体）

``--regenerate`` 从上述真源重新派生全部 5 份 schema 并写盘；``--check-sync``
校验当前 schemas/ 下的文件与真源是否同步（仅对"自动派生"部分做比对，人工
维护部分按方案要求跳过同步校验，不假装可自动派生）。

repair loop（方案 §B3）：校验失败时，将每条 ``jsonschema`` 错误的
``error.path`` + ``error.message`` 格式化为"请修正以下字段：X"，供 orchestrator
注入下一轮 prompt 重试（重试上限 2 次，对齐 ``chapter_auditor_agent.md:158``
已有的 ``max_rounds=2``；重试循环本身由 orchestrator 执行，本脚本不负责循环，
只输出格式化好的 ``repair_prompt`` 字段）。

用法：
    python scripts/schema_validate.py <target.json> --schema <name> [--json]
    python scripts/schema_validate.py --regenerate
    python scripts/schema_validate.py --check-sync [--json]

``<name>`` 取值：writer-selfclaim / auditor-phase-a / auditor-phase-b /
outline-structure / model-profile。

退出码：0 = 校验通过（或 regenerate/check-sync 全部同步）；
       1 = 校验失败（或 check-sync 发现不同步）；
       2 = 读取或 schema 错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import jsonschema
from jsonschema import Draft202012Validator

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py:42-48 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ASCII 替代符号
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = _PROJECT_ROOT / "schemas"
AUDITOR_CONTRACT_PATH = _PROJECT_ROOT / "agents" / "contracts" / "auditor_contract.json"
WRITER_CONTRACT_PATH = _PROJECT_ROOT / "agents" / "contracts" / "writer_contract.json"

SCHEMA_NAMES = [
    "writer-selfclaim",
    "auditor-phase-a",
    "auditor-phase-b",
    "outline-structure",
    "model-profile",
]

# 每份 schema 的同步来源类型："auto"（可从 JSON 契约自动派生，check-sync 实际比对）
# 或 "manual"（人工维护来源，check-sync 按方案要求跳过，不假装可自动派生）。
SCHEMA_SYNC_KIND = {
    "writer-selfclaim": "auto",
    "auditor-phase-a": "auto",
    "auditor-phase-b": "auto",
    "outline-structure": "manual",
    "model-profile": "manual",
}


def _schema_path(name: str) -> Path:
    return SCHEMA_DIR / f"{name}.schema.json"


def _load_json(path: Path) -> dict:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# 派生函数（真源 = 叙述性契约 JSON / 人工维护参考文档）
# ---------------------------------------------------------------------------


def derive_writer_selfclaim_schema() -> dict:
    """从 writer_contract.json#/self_declaration_fields 派生 6 字段自声明 schema。

    字段实际语义已核对 references/writer-template.md §6（本章字数/图片引用数/
    表格数/引用的card_id/已回填used_in_chapter的卡片/素材缺口标记），与契约中
    的 6 个字段名一一对应，语义一致。
    """
    contract = _load_json(WRITER_CONTRACT_PATH)
    fields = contract["self_declaration_fields"]

    # 6 字段的类型语义（对照 writer-template.md §6 示例逐字段判定）
    field_defs = {
        "chapter_char_count": {"type": "integer", "minimum": 0,
                                "description": "本章字数（估），writer-template.md §6 '本章字数（估）：约 N 字'"},
        "figure_count": {"type": "integer", "minimum": 0,
                         "description": "图片引用数，writer-template.md §6 '图片引用数：M'"},
        "table_count": {"type": "integer", "minimum": 0,
                        "description": "表格数，writer-template.md §6 '表格数：K'"},
        "cited_card_ids": {"type": "array", "items": {"type": "string"},
                           "description": "引用的 card_id 列表，writer-template.md §6 '引用的 card_id：CASE-01, TECH-03, ...'"},
        "backfilled_used_in_chapter": {"type": "array", "items": {"type": "string"},
                                        "description": "已回填 used_in_chapter 的卡片列表"},
        "material_gap_markers": {"type": "array", "items": {"type": "string"},
                                  "description": "素材缺口标记出现位置列表（可为空数组）"},
    }
    properties = {}
    for f in fields:
        properties[f] = field_defs.get(f, {"type": "string"})

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://deep-research-report.local/schemas/writer-selfclaim.schema.json",
        "title": "写作者自声明（6 字段）",
        "description": (
            "chapter_writer_agent 分章文件末尾自声明块的 JSON 校验形态。"
            "对应 references/writer-template.md §6 的 Markdown 元数据块，"
            "由 orchestrator 提取信封内容后转为 JSON 落盘校验。"
        ),
        "x-generated-from": "agents/contracts/writer_contract.json#/self_declaration_fields (auto) + references/writer-template.md#六 (字段语义人工核对)",
        "type": "object",
        "properties": properties,
        "required": list(fields),
        "additionalProperties": False,
    }


def derive_auditor_phase_a_schema() -> dict:
    """从 auditor_contract.json#/dimensions 派生 Phase A 确认式 JSON schema。

    Phase A 书写形态在 tier B/C 下改为"确认式"（方案 §C4），落盘形态为：
        {"ch01": {"outline_coverage": {"mode": "confirm"},
                   "strong_claim": {"mode": "adjust", "text": "..."}}}
    维度 id 枚举取自契约的 dimensions 列表（当前 24 个），confirm/adjust 的
    JSON 形态取自方案 §C4 明确给出的示例（人工设计的落盘约定）。
    """
    contract = _load_json(AUDITOR_CONTRACT_PATH)
    dim_ids = [d["id"] for d in contract["dimensions"]]
    # proposal_extra 维度仅在立项类报告适用，允许出现但不强制
    proposal_ids = [d["id"] for d in contract.get("proposal_extra", [])]
    all_ids = dim_ids + proposal_ids

    mode_entry_schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["confirm", "adjust"]},
            "text": {"type": "string"},
        },
        "required": ["mode"],
        "if": {"properties": {"mode": {"const": "adjust"}}},
        "then": {"required": ["mode", "text"]},
        "additionalProperties": False,
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://deep-research-report.local/schemas/auditor-phase-a.schema.json",
        "title": "Phase A 审计盲态预承诺（确认式）落盘格式",
        "description": (
            "chapter_auditor_agent Phase A 盲态预承诺的 JSON 落盘形态（方案 §C4 tier B/C 确认式）。"
            "顶层键为章标识（如 'ch01'），每章下键为维度 id，值为 {mode: confirm|adjust, text?}。"
            f"当前维度 id 枚举共 {len(dim_ids)} 个核心维度 + {len(proposal_ids)} 个立项扩展维度。"
        ),
        "x-generated-from": "agents/contracts/auditor_contract.json#/dimensions,/proposal_extra (维度id枚举，自动派生) + design/model-compatibility-optimization-plan.md#C4 (confirm/adjust JSON落盘形态，人工设计)",
        "type": "object",
        "propertyNames": {"pattern": "^ch\\d{2,3}$"},
        "minProperties": 1,
        "additionalProperties": {
            "type": "object",
            "propertyNames": {"enum": all_ids},
            "minProperties": 1,
            "additionalProperties": mode_entry_schema,
        },
    }


def derive_auditor_phase_b_schema() -> dict:
    """从 auditor_contract.json#/dimensions,/verdict 派生 Phase B 打分 schema。

    方案未给出 Phase B 完整 JSON 示例，本 schema 依据 auditor_contract.json 的
    维度结构（dimensions 枚举 + verdict 枚举）与 agents/chapter_auditor_agent.md
    §Phase B 的输出要求（`## 逐维度打分` block/warn/pass + 证据；`## issue 清单`
    维度/位置/问题/建议修法）合理设计，issue 清单结构为人工设计部分，
    第 7/8 批（C4/B4）消费时若需微调是预期内的。
    """
    contract = _load_json(AUDITOR_CONTRACT_PATH)
    dim_ids = [d["id"] for d in contract["dimensions"]]
    proposal_ids = [d["id"] for d in contract.get("proposal_extra", [])]
    all_ids = dim_ids + proposal_ids
    verdict_enum = contract["verdict"]  # ["PASS", "REVISE"]

    dimension_score_entry = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "warn", "block"]},
            "evidence": {"type": "string"},
        },
        "required": ["verdict", "evidence"],
        "additionalProperties": False,
    }

    issue_entry = {
        "type": "object",
        "properties": {
            "dimension": {"type": "string", "enum": all_ids},
            "location": {"type": "string"},
            "problem": {"type": "string"},
            "suggested_fix": {"type": "string"},
        },
        "required": ["dimension", "location", "problem", "suggested_fix"],
        "additionalProperties": False,
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://deep-research-report.local/schemas/auditor-phase-b.schema.json",
        "title": "Phase B 审计明态打分 + 裁决 落盘格式",
        "description": (
            "chapter_auditor_agent Phase B 明态打分的 JSON 落盘形态（人工设计，"
            "依据 agents/chapter_auditor_agent.md Phase B 小节 2『## 逐维度打分』"
            "每维度 block/warn/pass + 证据、小节 4『## 裁决』恰一个 PASS/REVISE、"
            "小节 5『## issue 清单』维度/位置/问题/建议修法 四元组）。"
            "dimension_scores 的键枚举与 issues[].dimension 枚举取自契约 dimensions，自动派生；"
            "整体 JSON 结构（issue 四元组字段名）为人工设计，非自动派生。"
        ),
        "x-generated-from": "agents/contracts/auditor_contract.json#/dimensions,/proposal_extra,/verdict (枚举，自动派生) + agents/chapter_auditor_agent.md#Phase-B (issue清单结构，人工设计)",
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "pattern": "^ch\\d{2,3}$"},
            "verdict": {"type": "string", "enum": verdict_enum},
            "dimension_scores": {
                "type": "object",
                "propertyNames": {"enum": all_ids},
                "minProperties": 1,
                "additionalProperties": dimension_score_entry,
            },
            "issues": {"type": "array", "items": issue_entry},
        },
        "required": ["chapter_id", "verdict", "dimension_scores", "issues"],
        "additionalProperties": False,
    }


def derive_outline_structure_schema() -> dict:
    """outline.md YAML front matter 结构清单 schema（人工维护，来源为 Markdown 规范文档）。

    无上游 JSON 契约可自动派生——真源是 references/stage-4-outline.md §4.1.y
    （structure 字段语义）与 §4.1.z（figures_manifest 字段 schema 表格），
    本 schema 由人工对照该文档编写，--check-sync 对本 schema 跳过同步校验。
    """
    section_entry = {
        "type": "object",
        "properties": {
            "section_no": {"type": "string"},
            "section_title": {"type": "string"},
        },
        "required": ["section_no", "section_title"],
        "additionalProperties": False,
    }
    subsection_entry = {
        "type": "object",
        "properties": {
            "parent_section_no": {"type": "string"},
            "subsection_no": {"type": "string"},
            "subsection_title": {"type": "string"},
        },
        "required": ["parent_section_no", "subsection_no", "subsection_title"],
        "additionalProperties": False,
    }
    frontmatter_chapter = {
        "type": "object",
        "properties": {
            "chapter_title": {"type": "string"},
            "sections": {"type": "array", "items": section_entry},
        },
        "required": ["chapter_title"],
        "additionalProperties": False,
    }
    bodymatter_chapter = {
        "type": "object",
        "properties": {
            "chapter_no": {"type": "integer", "minimum": 1},
            "chapter_title": {"type": "string"},
            "sections": {"type": "array", "items": section_entry},
            "subsections": {"type": "array", "items": subsection_entry},
        },
        "required": ["chapter_no", "chapter_title"],
        "additionalProperties": False,
    }
    appendix_entry = {
        "type": "object",
        "properties": {
            "appendix_letter": {"type": "string"},
            "appendix_title": {"type": "string"},
        },
        "required": ["appendix_letter", "appendix_title"],
        "additionalProperties": False,
    }
    figure_entry = {
        "type": "object",
        "properties": {
            "figure_id": {"type": "string"},
            "figure_no": {"type": "string"},
            "title": {"type": "string"},
            "type": {"type": "string"},
            "tool": {"type": "string", "enum": ["drawio", "fireworks-tech-graph", "mermaid", "matplotlib"]},
            "priority": {"type": "string", "enum": ["required", "optional"]},
            "belongs_to_chapter": {"type": "integer"},
            "status": {"type": "string", "enum": ["planned", "in_progress", "done", "dropped"]},
            "output_files": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "checkpoints": {"type": "array", "items": {"type": "string"}},
            "data_source": {"type": "string"},
        },
        "required": ["figure_id", "figure_no", "title", "type", "tool", "priority",
                     "belongs_to_chapter", "status", "output_files"],
        "additionalProperties": False,
    }
    table_entry = {
        "type": "object",
        "properties": {
            "table_id": {"type": "string"},
            "table_no": {"type": "string"},
            "title": {"type": "string"},
            "belongs_to_chapter": {"type": "integer"},
            "status": {"type": "string", "enum": ["planned", "in_progress", "done", "dropped"]},
            "rows_estimate": {"type": "integer"},
        },
        "required": ["table_id", "table_no", "title", "belongs_to_chapter", "status"],
        "additionalProperties": False,
    }
    figures_manifest = {
        "type": "object",
        "properties": {
            "architecture_figures": {"type": "array", "items": figure_entry},
            "data_figures": {"type": "array", "items": figure_entry},
            "tables": {"type": "array", "items": table_entry},
        },
        "additionalProperties": False,
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://deep-research-report.local/schemas/outline-structure.schema.json",
        "title": "outline.md YAML front matter 结构清单",
        "description": (
            "research/outline.md 的机器可读结构清单（references/stage-4-outline.md §4.1.y）。"
            "figures_manifest 为可选字段（§4.1.z），架构图/数据图/表格三个子清单。"
        ),
        "x-generated-from": "references/stage-4-outline.md#4.1.y,#4.1.z (manual)",
        "type": "object",
        "properties": {
            "struct_template": {"type": "string", "enum": ["research", "proposal", "policy", "tech-eval", "brief"]},
            "title": {"type": "string"},
            "structure": {
                "type": "object",
                "properties": {
                    "frontmatter": {"type": "array", "items": frontmatter_chapter},
                    "bodymatter": {"type": "array", "items": bodymatter_chapter, "minItems": 1},
                    "appendix": {"type": "array", "items": appendix_entry},
                },
                "required": ["bodymatter"],
                "additionalProperties": False,
            },
            "figures_manifest": figures_manifest,
        },
        "required": ["struct_template", "title", "structure"],
        "additionalProperties": False,
    }


def derive_model_profile_schema() -> dict:
    """model-profile.json 能力档声明 schema（人工维护，来源为方案文档 §C1）。

    无上游契约（本批次尚未建 model-profile.json 本体，那是第 5 批 C1 的工作）。
    **关键约束（方案 §C4 明确要求）**：`phase_a_mode` 由 `max_output_tokens`
    派生，是派生量，不再单独列入 schema——本 schema 不含 `phase_a_mode` 字段。
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://deep-research-report.local/schemas/model-profile.schema.json",
        "title": "model-profile.json 能力档声明",
        "description": (
            "跨模型兼容性优化方案 §C1 定义的模型能力档配置文件 schema。"
            "注意：phase_a_mode 由 limits.max_output_tokens 派生（方案 §C4：'phase_a_mode = confirm "
            "if max_output_tokens < 16000 else free'），是派生量，**不出现在本 schema 中**。"
        ),
        "x-generated-from": "design/model-compatibility-optimization-plan.md#C1 (manual)",
        "type": "object",
        "properties": {
            "capability_tier": {"type": "string", "enum": ["A", "B", "C"], "default": "A"},
            "host": {
                "type": "object",
                "properties": {
                    "agent_delegation": {"type": "boolean", "default": True},
                },
                "required": ["agent_delegation"],
                "additionalProperties": False,
            },
            "limits": {
                "type": "object",
                "properties": {
                    "max_output_tokens": {"type": "integer", "minimum": 1, "default": 64000},
                },
                "required": ["max_output_tokens"],
                "additionalProperties": False,
            },
            "policy": {
                "type": "object",
                "properties": {
                    "hard_rule_budget": {"type": "integer", "minimum": 0, "default": 0},
                    "envelope_nonce": {"type": "boolean", "default": False},
                    "template_fill_mode": {"type": "string", "enum": ["off", "on"], "default": "off"},
                },
                "required": ["hard_rule_budget", "envelope_nonce", "template_fill_mode"],
                "additionalProperties": False,
            },
        },
        "required": ["capability_tier", "host", "limits", "policy"],
        "additionalProperties": False,
    }


DERIVE_FUNCS = {
    "writer-selfclaim": derive_writer_selfclaim_schema,
    "auditor-phase-a": derive_auditor_phase_a_schema,
    "auditor-phase-b": derive_auditor_phase_b_schema,
    "outline-structure": derive_outline_structure_schema,
    "model-profile": derive_model_profile_schema,
}


# ---------------------------------------------------------------------------
# regenerate / check-sync
# ---------------------------------------------------------------------------


def regenerate_all() -> dict:
    """从真源重新派生全部 5 份 schema 并写盘，返回逐份结果。"""
    results = {}
    for name, fn in DERIVE_FUNCS.items():
        schema = fn()
        path = _schema_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results[name] = {"path": str(path), "kind": SCHEMA_SYNC_KIND[name], "written": True}
    return results


def check_sync() -> dict:
    """校验当前 schemas/ 下文件与真源是否同步。人工维护部分按方案要求跳过。"""
    results = {}
    all_synced = True
    for name in SCHEMA_NAMES:
        kind = SCHEMA_SYNC_KIND[name]
        path = _schema_path(name)
        if kind == "manual":
            results[name] = {"kind": "manual", "status": "skipped", "reason": "人工维护来源，无法自动派生，按方案要求跳过同步校验"}
            continue
        if not path.exists():
            results[name] = {"kind": "auto", "status": "missing", "synced": False}
            all_synced = False
            continue
        try:
            on_disk = _load_json(path)
        except Exception as e:
            results[name] = {"kind": "auto", "status": "unreadable", "synced": False, "error": str(e)}
            all_synced = False
            continue
        fresh = DERIVE_FUNCS[name]()
        synced = on_disk == fresh
        results[name] = {"kind": "auto", "status": "ok" if synced else "out_of_sync", "synced": synced}
        if not synced:
            all_synced = False
    return {"all_synced": all_synced, "detail": results}


# ---------------------------------------------------------------------------
# 校验 + repair loop 消息格式化
# ---------------------------------------------------------------------------


def load_schema(name: str) -> dict:
    """加载指定 schema。若磁盘上不存在，即时从真源派生（不强制先手工跑 --regenerate）。"""
    path = _schema_path(name)
    if path.exists():
        return _load_json(path)
    return DERIVE_FUNCS[name]()


def _format_error_path(error: jsonschema.exceptions.ValidationError) -> str:
    """把 jsonschema 的 error.path（deque）格式化为可读的字段路径，如 'ch01.outline_coverage.mode'。"""
    parts = [str(p) for p in error.absolute_path]
    return ".".join(parts) if parts else "(根)"


def validate_instance(instance, schema: dict) -> dict:
    """执行 Draft 2020-12 校验，返回结构化结果，函数级可复用（方案 §D5）。"""
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))

    error_list = []
    for e in errors:
        error_list.append({
            "path": _format_error_path(e),
            "message": e.message,
            "validator": e.validator,
        })

    valid = len(error_list) == 0
    repair_prompt = None
    if not valid:
        lines = ["请修正以下字段："]
        for e in error_list:
            lines.append(f"- {e['path']}：{e['message']}")
        repair_prompt = "\n".join(lines)

    return {
        "valid": valid,
        "error_count": len(error_list),
        "errors": error_list,
        "repair_prompt": repair_prompt,
        "max_repair_rounds": 2,  # 对齐 chapter_auditor_agent.md:158 已有的 max_rounds=2；循环由 orchestrator 执行
    }


def format_text_report(target: str, schema_name: str, result: dict) -> str:
    lines = [f"=== Schema 校验：{target} （schema={schema_name}）==="]
    if result["valid"]:
        lines.append(f"{OK} 校验通过，无字段错误。")
    else:
        lines.append(f"{FAIL} 校验失败，共 {result['error_count']} 处错误：")
        for e in result["errors"]:
            lines.append(f"      - [{e['path']}] {e['message']}")
        lines.append("")
        lines.append(result["repair_prompt"])
    lines.append("")
    lines.append(f"=== 总判定: {'PASS' if result['valid'] else 'FAIL'} ===")
    return "\n".join(lines)


def format_check_sync_report(sync_result: dict) -> str:
    lines = ["=== Schema 同步性校验 ==="]
    for name, detail in sync_result["detail"].items():
        if detail["kind"] == "manual":
            lines.append(f"{WARN} {name}: 人工维护来源，已跳过（{detail['reason']}）")
        elif detail["status"] == "ok":
            lines.append(f"{OK} {name}: 与真源同步")
        elif detail["status"] == "missing":
            lines.append(f"{FAIL} {name}: schema 文件不存在，需先跑 --regenerate")
        else:
            lines.append(f"{FAIL} {name}: 与真源不同步（状态={detail['status']}）")
    lines.append("")
    lines.append(f"=== 总判定: {'PASS' if sync_result['all_synced'] else 'FAIL'} ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="通用 JSON Schema 校验器 + repair loop 错误消息格式化")
    parser.add_argument("target", nargs="?", default=None, help="待校验的 JSON 文件")
    parser.add_argument("--schema", choices=SCHEMA_NAMES, default=None, help="schema 名称")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--regenerate", action="store_true", help="从真源重新派生全部 5 份 schema 并写盘")
    parser.add_argument("--check-sync", action="store_true", help="校验当前 schema 与真源是否同步")
    args = parser.parse_args()

    if args.regenerate:
        results = regenerate_all()
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for name, r in results.items():
                print(f"{OK} 已写入 {r['path']} (kind={r['kind']})")
        sys.exit(0)

    if args.check_sync:
        sync_result = check_sync()
        if args.json:
            print(json.dumps(sync_result, ensure_ascii=False, indent=2))
        else:
            print(format_check_sync_report(sync_result))
        sys.exit(0 if sync_result["all_synced"] else 1)

    if not args.target or not args.schema:
        print(f"{FAIL} 需要提供 <target.json> 与 --schema <name>（或改用 --regenerate / --check-sync）", file=sys.stderr)
        sys.exit(2)

    target_path = Path(args.target)
    if not target_path.exists():
        print(f"{FAIL} 文件不存在: {args.target}", file=sys.stderr)
        sys.exit(2)

    try:
        instance = json.loads(target_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"{FAIL} 目标 JSON 读取/解析失败: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        schema = load_schema(args.schema)
    except Exception as e:
        print(f"{FAIL} schema 加载失败: {e}", file=sys.stderr)
        sys.exit(2)

    result = validate_instance(instance, schema)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(args.target, args.schema, result))

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
