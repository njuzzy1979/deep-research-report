#!/usr/bin/env python3
"""阶段 4 CP3 确认后 —— 生成 Agent 分派清单（Dispatch Manifest）。

读取 ``outline.md`` 的 YAML front matter，自动派生完整的 Agent 分派计划，
输出 JSON。编排器（主对话）在 CP3 确认后运行此脚本，然后严格按 manifest
分派 Agent。

派生规则（参照 ``references/stage-4-outline.md`` YAML structure schema）：

1. **frontmatter**（如果存在）→ 1 个 Writer
2. **bodymatter**（每章）→ 1 个 Writer + 1 个 Auditor
3. **appendix**（如果存在）→ 1 个 Writer
4. **architecture_figures**（来自 figures_manifest）→ 每张图 1 个 architecture_chart_agent
5. **data_figures**（来自 figures_manifest）→ 每张图 1 个 data_chart_agent
6. **固定分派**: card_synthesizer_agent ×1, redteam_agent ×4 (2×Opus + 2×Sonnet),
   redteam_synthesizer_agent ×1, finalizer_agent ×1

用法::

    python scripts/generate_dispatch_manifest.py \
        --outline research/outline.md \
        --output research/dispatch-manifest.json

退出码：0 = 成功产出 manifest；2 = outline 不存在 / YAML 解析失败 / structure 为空。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from md2docx.assemble.outline_reader import (  # noqa: E402
    extract_yaml_front_matter,
    normalize_outline_structure,
)

OK = "[OK]"
FAIL = "[FAIL]"

# ── 固定分派常量 ──────────────────────────────────────────────────────────
REDTEAM_COUNT = 4
REDTEAM_OPUS_COUNT = 2
REDTEAM_SONNET_COUNT = 2


def _build_writer_dispatch(
    chapter_no: int | str,
    chapter_title: str,
    sections: list,
    dispatch_id: str,
) -> dict:
    """构造一个 Writer 分派条目。"""
    return {
        "agent": "chapter_writer_agent",
        "model": "sonnet",
        "chapter": chapter_no,
        "chapter_title": chapter_title,
        "sections": sections,
        "dispatch_id": dispatch_id,
        "depends_on": ["card-synth"],
        "input": {
            "outline_chapter": chapter_no,
            "chapter_title": chapter_title,
            "sections": [
                {
                    "section_no": str(s.get("section_no", "")).strip(),
                    "section_title": str(s.get("section_title", "")).strip(),
                }
                for s in sections
                if isinstance(s, dict)
            ],
        },
    }


def _build_auditor_dispatch(
    chapter_no: int,
    chapter_title: str,
    dispatch_id: str,
    writer_dispatch_id: str,
) -> dict:
    """构造一个 Auditor 分派条目。"""
    return {
        "agent": "chapter_auditor_agent",
        "model": "opus",
        "chapter": chapter_no,
        "chapter_title": chapter_title,
        "dispatch_id": dispatch_id,
        "depends_on": [writer_dispatch_id],
        "input": {
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "writer_output_ref": writer_dispatch_id,
        },
    }


def _build_arch_chart_dispatch(fig: dict) -> dict:
    """构造一个架构图 Agent 分派条目。"""
    figure_no = str(fig.get("figure_no", ""))
    figure_title = str(fig.get("title", ""))
    return {
        "agent": "architecture_chart_agent",
        "model": "sonnet",
        "dispatch_id": f"arch-fig-{figure_no}",
        "figure_id": str(fig.get("figure_id", "")),
        "figure_no": figure_no,
        "figure_title": figure_title,
        "figure_type": str(fig.get("type", "")),
        "tool": str(fig.get("tool", "drawio")),
        "priority": str(fig.get("priority", "required")),
        "belongs_to_chapter": fig.get("belongs_to_chapter", 0),
        "depends_on": ["card-synth"],
        "input": {
            "figure_id": str(fig.get("figure_id", "")),
            "figure_no": figure_no,
            "figure_title": figure_title,
            "figure_type": str(fig.get("type", "")),
            "tool": str(fig.get("tool", "drawio")),
            "belongs_to_chapter": fig.get("belongs_to_chapter", 0),
            "output_files": fig.get("output_files", []),
        },
    }


def _build_data_chart_dispatch(fig: dict) -> dict:
    """构造一个数据图表 Agent 分派条目。"""
    figure_no = str(fig.get("figure_no", ""))
    figure_title = str(fig.get("title", ""))
    return {
        "agent": "data_chart_agent",
        "model": "sonnet",
        "dispatch_id": f"data-fig-{figure_no}",
        "figure_id": str(fig.get("figure_id", "")),
        "figure_no": figure_no,
        "figure_title": figure_title,
        "figure_type": str(fig.get("type", "")),
        "tool": str(fig.get("tool", "matplotlib")),
        "priority": str(fig.get("priority", "required")),
        "belongs_to_chapter": fig.get("belongs_to_chapter", 0),
        "data_source": str(fig.get("data_source", "")),
        "depends_on": ["card-synth"],
        "input": {
            "figure_id": str(fig.get("figure_id", "")),
            "figure_no": figure_no,
            "figure_title": figure_title,
            "figure_type": str(fig.get("type", "")),
            "tool": str(fig.get("tool", "matplotlib")),
            "belongs_to_chapter": fig.get("belongs_to_chapter", 0),
            "data_source": str(fig.get("data_source", "")),
            "output_files": fig.get("output_files", []),
        },
    }


def generate_manifest(
    outline_path: str,
) -> dict:
    """读取 outline.md YAML front matter，生成完整 Dispatch Manifest。

    Returns:
        Dict 形式的 manifest JSON 结构。
    """
    op = Path(outline_path)
    if not op.exists():
        print(f"{FAIL} outline.md 不存在: {outline_path}", file=sys.stderr)
        sys.exit(2)

    text = op.read_text(encoding="utf-8", errors="replace")
    parsed, _body = extract_yaml_front_matter(text, str(op))

    if not isinstance(parsed, dict):
        print(f"{FAIL} outline.md YAML front matter 解析失败：未返回 dict", file=sys.stderr)
        sys.exit(2)

    if "structure" not in parsed:
        print(
            f"{FAIL} outline.md 的 YAML front matter 中缺少 structure 节点",
            file=sys.stderr,
        )
        sys.exit(2)

    structure = normalize_outline_structure(parsed["structure"], str(op))
    report_title = str(parsed.get("title") or parsed.get("report_title") or "").strip()

    # ── 提取各区数据 ──────────────────────────────────────────────────────
    frontmatter = structure.get("frontmatter") or []
    bodymatter = structure.get("bodymatter") or []
    appendix = structure.get("appendix") or []

    if not bodymatter:
        print(
            f"{FAIL} structure.bodymatter 为空——大纲未声明任何正文章节",
            file=sys.stderr,
        )
        sys.exit(2)

    figures_manifest = parsed.get("figures_manifest") or {}
    arch_figures = figures_manifest.get("architecture_figures") or []
    data_figures = figures_manifest.get("data_figures") or []

    now_iso = datetime.now(timezone.utc).isoformat()

    # ── 统计计数器 ────────────────────────────────────────────────────────
    writer_count = 0
    auditor_count = 0
    arch_count = 0
    data_chart_count = 0
    redteam_count = 0
    synthesizer_count = 0
    finalizer_count = 0

    # ── Stage 5: 卡片综合 ─────────────────────────────────────────────────
    stage5_agents: list = [
        {
            "agent": "card_synthesizer_agent",
            "model": "sonnet",
            "dispatch_id": "card-synth",
            "depends_on": [],
            "input": {
                "outline_path": str(op.resolve()),
                "report_title": report_title,
                "bodymatter_chapters": [
                    {"chapter_no": ch.get("chapter_no"), "chapter_title": ch.get("chapter_title")}
                    for ch in bodymatter
                    if isinstance(ch, dict)
                ],
            },
        }
    ]
    synthesizer_count += 1

    # ── Stage 6: 架构图 ───────────────────────────────────────────────────
    stage6_agents: list = []
    for fig in arch_figures:
        if not isinstance(fig, dict):
            continue
        stage6_agents.append(_build_arch_chart_dispatch(fig))
        arch_count += 1

    # ── Stage 7: Writers + Auditors + 数据图表 ─────────────────────────────
    stage7_writers: list = []
    stage7_auditors: list = []
    stage7_data_charts: list = []

    # frontmatter writers
    writer_dispatch_ids: list = []
    for fm in frontmatter:
        if not isinstance(fm, dict):
            continue
        c_title = str(fm.get("chapter_title") or "").strip()
        if not c_title:
            continue
        secs = fm.get("sections") or []
        wid = "writer-frontmatter"
        stage7_writers.append(
            _build_writer_dispatch("frontmatter", c_title, secs, wid)
        )
        writer_dispatch_ids.append(wid)
        writer_count += 1

    # bodymatter writers + auditors
    for ch in bodymatter:
        if not isinstance(ch, dict):
            continue
        c_no = ch.get("chapter_no")
        if c_no is None:
            continue
        c_title = str(ch.get("chapter_title") or f"第{c_no}章").strip()
        secs = ch.get("sections") or []
        wid = f"writer-ch{c_no}"
        stage7_writers.append(_build_writer_dispatch(c_no, c_title, secs, wid))
        writer_dispatch_ids.append(wid)
        writer_count += 1

        aid = f"auditor-ch{c_no}"
        stage7_auditors.append(_build_auditor_dispatch(c_no, c_title, aid, wid))
        auditor_count += 1

    # appendix writer（所有附录项合并为 1 个 Writer）
    if appendix:
        appendix_sections = []
        appendix_title = "附录"
        for apx in appendix:
            if not isinstance(apx, dict):
                continue
            letter = str(apx.get("appendix_letter") or "").strip()
            a_title = str(apx.get("appendix_title") or "").strip()
            if not apx:
                continue
            head = f"附录{letter}：{a_title}" if letter else a_title
            appendix_sections.append(
                {"section_no": "", "section_title": head}
            )
        if appendix_sections:
            wid = "writer-appendix"
            stage7_writers.append(
                _build_writer_dispatch("appendix", appendix_title, appendix_sections, wid)
            )
            writer_dispatch_ids.append(wid)
            writer_count += 1

    # data charts (in stage 7)
    for fig in data_figures:
        if not isinstance(fig, dict):
            continue
        stage7_data_charts.append(_build_data_chart_dispatch(fig))
        data_chart_count += 1

    # ── Stage 8: 红队审查 ─────────────────────────────────────────────────
    stage8_redteam: list = []
    redteam_agents = []

    for i in range(REDTEAM_OPUS_COUNT):
        rid = f"redteam-opus-{i + 1}"
        entry = {
            "agent": "redteam_agent",
            "model": "opus",
            "dispatch_id": rid,
            "depends_on": writer_dispatch_ids,
            "input": {
                "role": "redteam_reviewer",
                "model_tier": "opus",
                "index": i + 1,
                "writer_dispatch_ids": writer_dispatch_ids,
            },
        }
        stage8_redteam.append(entry)
        redteam_agents.append(entry)
        redteam_count += 1

    for i in range(REDTEAM_SONNET_COUNT):
        rid = f"redteam-sonnet-{i + 1}"
        entry = {
            "agent": "redteam_agent",
            "model": "sonnet",
            "dispatch_id": rid,
            "depends_on": writer_dispatch_ids,
            "input": {
                "role": "redteam_reviewer",
                "model_tier": "sonnet",
                "index": REDTEAM_OPUS_COUNT + i + 1,
                "writer_dispatch_ids": writer_dispatch_ids,
            },
        }
        stage8_redteam.append(entry)
        redteam_agents.append(entry)
        redteam_count += 1

    redteam_dispatch_ids = [r["dispatch_id"] for r in redteam_agents]
    stage8_synthesizer = {
        "agent": "redteam_synthesizer_agent",
        "model": "sonnet",
        "dispatch_id": "redteam-synth",
        "depends_on": redteam_dispatch_ids,
        "input": {
            "redteam_dispatch_ids": redteam_dispatch_ids,
        },
    }
    synthesizer_count += 1

    # ── Stage 9: 终稿编排 ─────────────────────────────────────────────────
    stage9_agents: list = [
        {
            "agent": "finalizer_agent",
            "model": "haiku",
            "dispatch_id": "finalizer",
            "depends_on": ["redteam-synth"],
            "input": {
                "outline_path": str(op.resolve()),
                "redteam_synth_ref": "redteam-synth",
            },
        }
    ]
    finalizer_count += 1

    # ── 汇总 ───────────────────────────────────────────────────────────────
    total_agents = (
        writer_count
        + auditor_count
        + arch_count
        + data_chart_count
        + redteam_count
        + synthesizer_count
        + finalizer_count
    )

    manifest = {
        "report_title": report_title,
        "generated_at": now_iso,
        "outline_path": str(op.resolve()),
        "phases": {
            "stage5": {"agents": stage5_agents},
            "stage6": {"agents": stage6_agents},
            "stage7": {
                "writers": stage7_writers,
                "auditors": stage7_auditors,
                "data_charts": stage7_data_charts,
            },
            "stage8": {
                "redteam": stage8_redteam,
                "synthesizer": stage8_synthesizer,
            },
            "stage9": {"agents": stage9_agents},
        },
        "totals": {
            "total_agents": total_agents,
            "writers": writer_count,
            "auditors": auditor_count,
            "architects": arch_count,
            "data_charts": data_chart_count,
            "redteam": redteam_count,
            "synthesizers": synthesizer_count,
            "finalizers": finalizer_count,
        },
    }

    return manifest


def format_text_report(manifest: dict) -> str:
    """生成 stdout 摘要。"""
    lines = ["=== Dispatch Manifest 生成 ===", ""]
    lines.append(f"报告标题: {manifest['report_title']}")
    lines.append(f"生成时间: {manifest['generated_at']}")
    lines.append("")

    totals = manifest["totals"]
    lines.append("阶段分派统计:")
    lines.append(f"  Stage 5 (卡片综合)    : card_synthesizer_agent ×{totals['synthesizers'] - 1}")
    lines.append(f"  Stage 6 (架构图)      : architecture_chart_agent ×{totals['architects']}")
    lines.append(f"  Stage 7 (写作+数据图)  : writer ×{totals['writers']} + auditor ×{totals['auditors']} + data_chart ×{totals['data_charts']}")
    lines.append(f"  Stage 8 (红队审查)    : redteam_agent ×{totals['redteam']} + redteam_synthesizer ×1")
    lines.append(f"  Stage 9 (终稿编排)    : finalizer_agent ×{totals['finalizers']}")
    lines.append(f"  ────────────────────")
    lines.append(f"  总计                : {totals['total_agents']} agents")
    lines.append("")

    # 按阶段列出 dispatch_id
    for phase_key, phase_data in manifest["phases"].items():
        if phase_key == "stage7":
            entries = (
                phase_data.get("writers", [])
                + phase_data.get("auditors", [])
                + phase_data.get("data_charts", [])
            )
        elif phase_key == "stage8":
            entries = list(phase_data.get("redteam", []))
            if phase_data.get("synthesizer"):
                entries.append(phase_data["synthesizer"])
        else:
            entries = phase_data.get("agents", [])
        ids = [e["dispatch_id"] for e in entries]
        lines.append(f"  {phase_key}: {', '.join(ids)}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段4 CP3 确认后：从 outline.md YAML front matter 生成 Agent 分派清单"
    )
    parser.add_argument("--outline", required=True, help="outline.md 路径")
    parser.add_argument(
        "--output", required=True, help="dispatch manifest JSON 输出路径"
    )
    parser.add_argument("--json", action="store_true", help="也输出 JSON 到 stdout")
    args = parser.parse_args()

    manifest = generate_manifest(args.outline)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(format_text_report(manifest))
    print(f"\n{OK} Manifest 已写入: {out_path.resolve()}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
