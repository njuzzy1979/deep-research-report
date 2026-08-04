#!/usr/bin/env python3
"""阶段 4 CP3 确认后 —— 生成 Agent 分派清单（Dispatch Manifest）。

读取 ``outline.md`` 的 YAML front matter，自动派生完整的 Agent 分派计划，
输出 JSON。编排器（主对话）在 CP3 确认后运行此脚本，然后严格按 manifest
分派 Agent。

派生规则（参照 ``references/stage-4-outline.md`` YAML structure schema）：

新版 schema（扁平 ``chapters`` 数组）：
1. 遍历 ``structure.chapters``，每个章（非 auto-filled）→ 1 个 Writer
2. 非附录章 → +1 个 Auditor
3. ``kind`` 为 "bibliography" / "figure_index" 的章 → 不分派 Writer（管线自动填充）
4. **architecture_figures**（来自 figures_manifest）→ 每张图 1 个 architecture_chart_agent
5. **data_figures**（来自 figures_manifest）→ 每张图 1 个 data_chart_agent
6. **固定分派**: card_synthesizer_agent ×1, redteam_agent ×4 (2×Opus + 2×Sonnet),
   redteam_synthesizer_agent ×1, finalizer_agent ×1

旧版 schema（frontmatter/bodymatter/appendix）兼容：
- 内部自动转换为新 chapters 数组后按上述规则处理。

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


def _convert_old_to_new(structure: dict) -> list[dict]:
    """将旧格式 (frontmatter/bodymatter/appendix) 转换为新 chapters 数组。

    旧格式有三个独立的区段列表，新格式使用单一扁平 ``chapters`` 数组。
    此函数在消费端入口处做兼容转换，使下游代码只需处理新格式。
    """
    chapters: list[dict] = []

    # frontmatter → chapters（chapter_no 固定为 "frontmatter"）
    for fm in (structure.get("frontmatter") or []):
        if not isinstance(fm, dict):
            continue
        c_title = str(fm.get("chapter_title") or "").strip()
        if not c_title:
            continue
        chapters.append({
            "chapter_no": "frontmatter",
            "chapter_title": c_title,
            "is_appendix": False,
            "kind": None,
            "sections": fm.get("sections") or [],
        })

    # bodymatter → chapters（chapter_no 为整数章号）
    for ch in (structure.get("bodymatter") or []):
        if not isinstance(ch, dict):
            continue
        chapters.append({
            "chapter_no": ch.get("chapter_no"),
            "chapter_title": str(ch.get("chapter_title") or "").strip(),
            "is_appendix": False,
            "kind": None,
            "sections": ch.get("sections") or [],
        })

    # appendix → chapters（is_appendix=True；旧格式无 kind 概念，统一为 None）
    for apx in (structure.get("appendix") or []):
        if not isinstance(apx, dict):
            continue
        letter = str(apx.get("appendix_letter") or "").strip()
        a_title = str(apx.get("appendix_title") or "").strip()
        if not a_title:
            continue
        head = f"附录{letter}：{a_title}" if letter else a_title
        chapters.append({
            "chapter_no": letter if letter else "appendix",
            "chapter_title": head,
            "is_appendix": True,
            "kind": None,
            "sections": [],
        })

    return chapters


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

    # ── 格式检测：新格式 (chapters) vs 旧格式 (frontmatter/bodymatter/appendix) ──
    if "chapters" in structure:
        chapters: list[dict] = list(structure["chapters"])
    else:
        chapters = _convert_old_to_new(structure)

    # 筛选正文章节（非 frontmatter、非 appendix）
    body_chapters: list[dict] = [
        ch for ch in chapters
        if isinstance(ch, dict)
        and not ch.get("is_appendix", False)
        and ch.get("chapter_no") != "frontmatter"
    ]
    if not body_chapters:
        print(
            f"{FAIL} structure 中未声明任何正文章节",
            file=sys.stderr,
        )
        sys.exit(2)

    # ── 提取各区数据 ──────────────────────────────────────────────────────
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
    auto_filled_count = 0

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
                    for ch in body_chapters
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
    writer_dispatch_ids: list = []

    for ch in chapters:
        if not isinstance(ch, dict):
            continue

        chapter_no = ch.get("chapter_no")
        chapter_title = str(ch.get("chapter_title") or "").strip()
        if not chapter_title:
            continue

        is_appendix = ch.get("is_appendix", False)
        kind = ch.get("kind")  # None / "bibliography" / "figure_index"

        # 跳过管线自动填充的章（不分派 Writer）
        if kind in ("bibliography", "figure_index"):
            auto_filled_count += 1
            continue

        secs = ch.get("sections") or []
        dispatch_id = f"writer-{'appendix-' if is_appendix else ''}ch{chapter_no}"

        stage7_writers.append(
            _build_writer_dispatch(chapter_no, chapter_title, secs, dispatch_id)
        )
        writer_dispatch_ids.append(dispatch_id)
        writer_count += 1

        # 非附录章才有 Auditor
        if not is_appendix:
            aid = f"auditor-ch{chapter_no}"
            stage7_auditors.append(
                _build_auditor_dispatch(chapter_no, chapter_title, aid, dispatch_id)
            )
            auditor_count += 1

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
            "auto_filled_chapters": auto_filled_count,
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
    auto_filled = totals.get("auto_filled_chapters", 0)
    lines.append("阶段分派统计:")
    lines.append(f"  Stage 5 (卡片综合)    : card_synthesizer_agent ×{totals['synthesizers'] - 1}")
    lines.append(f"  Stage 6 (架构图)      : architecture_chart_agent ×{totals['architects']}")
    lines.append(f"  Stage 7 (写作+数据图)  : writer ×{totals['writers']} + auditor ×{totals['auditors']} + data_chart ×{totals['data_charts']}")
    if auto_filled > 0:
        lines.append(f"                        (另有 {auto_filled} 章为管线自动填充，不分派 Writer)")
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
