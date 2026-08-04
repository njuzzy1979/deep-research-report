#!/usr/bin/env python3
"""阶段 4 大纲结构完整性门禁（D1-9）。

存在意义：``references/stage-4-outline.md`` 的质量门槛明写"大纲含三级标题
（章→节→小节）"、`:324` 明写"用户确认了大纲结构"、`:326` 是 🔴 CHECKPOINT
🛑 STOP，**但阶段 4 全文零脚本调用**（grep ``python``/``scripts/`` 零命中），
整个质量门槛是**人工勾选的复选框**。

本次事故的实证：这一项被勾选通过，而实际 ``subsections`` 16/16 全为空列表、
YAML 声明 0 个 section，终稿却实际产出 113 个 ``Heading 2``。这是根因
R-B（规范依赖人工执行而无机器门禁）在阶段 4 的实例——阶段 4 由此**首次获得
机器校验**。

六项检查：

======  =============================================================  ========
 编号    判据                                                           级别
======  =============================================================  ========
 S1     YAML ``structure`` 存在且归一化后 ``chapters`` 非空             FATAL
 S2     每个 ``chapters[*]`` 有非空 ``chapter_title``                   FATAL
 S3     每个 ``chapters[*]``（非 appendix）的 ``sections`` 条目数 >= 2  FATAL
 S4     每个 ``sections[*]`` 有非空 ``section_no`` 与 ``section_title`` FATAL
 S5     YAML 章标题集合 == Markdown 正文 ``##`` 标题集合（去编号）       WARNING
 S6     ``section_title`` 不含编号前缀（复用 headings._strip_section）   WARNING
======  =============================================================  ========

S3 阈值取 >=2 而非 >=1 的理由：只有 1 个节的章，其节标题必然与章标题语义
重复，是"为过门禁而填一行"的典型形态。

用法::

    python scripts/outline_structure_gate.py --outline research/outline.md
    python scripts/outline_structure_gate.py --outline research/outline.md --json
    python scripts/outline_structure_gate.py --outline research/outline.md \\
        --structure-gate strict
    python scripts/outline_structure_gate.py --outline research/outline.md \\
        --normalize > research/outline-v2.md

退出码：0 = 通过（warn 模式下 S1-S4 违规也返回 0，仅告警）；
       1 = strict 模式下存在 S1-S4 违规；
       2 = outline.md 不存在/不可读/YAML 无 structure 节点（用法层面错误）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 本文件位于 scripts/ 下，与 md2docx 包同级（同 outline_title_extract.py 做法）
from md2docx.assemble.outline_reader import (  # noqa: E402
    extract_yaml_front_matter,
    normalize_outline_structure,
)
from md2docx.assemble.headings import _strip_section  # noqa: E402
from md2docx.issues import IssueCollector  # noqa: E402

OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

# ---------------------------------------------------------------------------
# --structure-gate 三态与切换 strict 的**客观**触发判据（U6 裁决）
# ---------------------------------------------------------------------------
#
# 用户裁决（总览 §六 U6 / D1 §9.8）：**首版默认 warn**，与 U3/U4 同口径。
# 理由：实测真实 outline 的 subsections 16/16 全为空，S3 一旦 strict 会使
# **存量项目 100% 卡在阶段 4 CP3 无法进入阶段 5**。
#
# ⚠ 切换到 strict 的触发判据（必须是可验证的客观判据，不是"待定后再切"）：
#
#   连续 STRICT_SWITCH_CONSECUTIVE_PROJECTS 个**新**项目，其 outline.md 在
#   **未经人工补写**的情况下自然通过 S1-S4（即 outline_architect_agent 按
#   已补齐的 section 级产出要求，自然产出非空 sections）。
#
# 判定方法（可机器执行）：对每个新项目在阶段 4 首次运行本脚本时记录
# `s1_s4_passed`；连续 N 次为 True 即满足切换条件。
#
# N 值定为 3：低于 3 无法排除偶然（单个项目可能恰好选题简单），高于 3 会让
# 切换无限期推迟。这个数字是可争议的，但**必须有一个数字**——D2 §2.2 已论证
# 纯口头"待补齐后再切"若无客观判据，等同于永不切换。
STRICT_SWITCH_CONSECUTIVE_PROJECTS = 3

# S3 阈值：每章至少声明的节数
MIN_SECTIONS_PER_CHAPTER = 2

_RE_MD_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# 章标题的编号前缀（如 "第 1 章：" / "1. " / "一、"），用于 S5 去编号比对
_RE_CHAPTER_NUM_PREFIX = re.compile(
    r"^\s*(?:第\s*[0-9一二三四五六七八九十百]+\s*章\s*[：:、.]?\s*"
    r"|[0-9]+\s*[.、：:]\s*"
    r"|[一二三四五六七八九十]+\s*[、.：:]\s*)"
)


def _strip_chapter_num(text: str) -> str:
    return _RE_CHAPTER_NUM_PREFIX.sub("", str(text or "")).strip()


def normalize_outline_v1_to_v2(structure: dict) -> dict:
    """将旧格式三区段 outline（frontmatter/bodymatter/appendix）转换为新格式扁平 chapters 数组。

    旧格式（v1）结构：
        {"title": "...", "frontmatter": [{...}], "bodymatter": [{...}], "appendix": [{...}]}

    新格式（v2）结构：
        {"title": "...", "chapters": [
            {"chapter_no": 1, "chapter_title": "...", "sections": [...]},
            ...
            {"chapter_no": "A", "chapter_title": "...", "sections": [...], "is_appendix": True},
        ]}

    若已为新格式（已含 ``chapters`` 键），直接返回原 structure（幂等）。
    """
    if not isinstance(structure, dict):
        return structure
    if "chapters" in structure:
        return structure  # 已是新格式，幂等

    chapters: list = []
    chapter_no: int = 0

    # 前导章节（frontmatter）
    for ch in structure.get("frontmatter") or []:
        if not isinstance(ch, dict):
            continue
        chapter_no += 1
        chapters.append({
            "chapter_no": chapter_no,
            "chapter_title": str(ch.get("chapter_title") or ch.get("appendix_title") or ""),
            "sections": ch.get("sections") or [],
        })

    # 正文章节（bodymatter）
    for ch in structure.get("bodymatter") or []:
        if not isinstance(ch, dict):
            continue
        chapter_no += 1
        chapters.append({
            "chapter_no": chapter_no,
            "chapter_title": str(ch.get("chapter_title") or ch.get("appendix_title") or ""),
            "sections": ch.get("sections") or [],
        })

    # 附录章节（appendix），编号使用大写字母
    _APPENDIX_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    appendix_idx = 0
    for ch in structure.get("appendix") or []:
        if not isinstance(ch, dict):
            continue
        letter = _APPENDIX_LABELS[appendix_idx] if appendix_idx < len(_APPENDIX_LABELS) else f"APP{appendix_idx}"
        appendix_idx += 1
        chapters.append({
            "chapter_no": letter,
            "chapter_title": str(ch.get("chapter_title") or ch.get("appendix_title") or ""),
            "sections": ch.get("sections") or [],
            "is_appendix": True,
        })

    return {"title": str(structure.get("title") or ""), "chapters": chapters}


def run_structure_gate(outline_path: str, gate_mode: str = "warn") -> dict:
    """执行 S1-S6 六项检查，返回结构化结果。

    Args:
        outline_path: outline.md 路径。
        gate_mode: ``off`` / ``warn``（默认）/ ``strict``。三态语义与 D1-6 的
            ``--structure-overlay`` 同构：``off`` 跳过全部检查；``warn`` 报告
            但不阻断；``strict`` 下 S1-S4 违规即阻断（exit 1）。

    Returns:
        {"gate_mode", "checks": {S1..S6}, "s1_s4_passed", "passed", ...}
    """
    result: dict = {
        "outline_path": str(Path(outline_path).resolve()),
        "gate_mode": gate_mode,
        "checks": {},
        "s1_s4_passed": False,
        "passed": False,
        "strict_switch_criterion": (
            f"连续 {STRICT_SWITCH_CONSECUTIVE_PROJECTS} 个新项目的 outline 在未经"
            f"人工补写的情况下自然通过 S1-S4，即可将默认值切换为 strict"
        ),
    }

    if gate_mode == "off":
        result["passed"] = True
        result["note"] = "gate_mode=off，跳过全部结构检查"
        return result

    path = Path(outline_path)
    if not path.exists():
        result["error"] = f"outline.md 不存在: {outline_path}"
        return result

    text = path.read_text(encoding="utf-8", errors="replace")
    parsed, body = extract_yaml_front_matter(text, str(path))
    if not isinstance(parsed, dict) or "structure" not in parsed:
        result["error"] = "outline.md 的 YAML front matter 中缺少 structure 节点"
        return result

    structure = normalize_outline_structure(parsed["structure"], str(path))
    structure = normalize_outline_v1_to_v2(structure)
    chapters = structure.get("chapters") or []
    issues = IssueCollector()

    # 辅助：判断章节是否为附录
    def _is_appendix(ch: dict) -> bool:
        if ch.get("is_appendix"):
            return True
        c_no = ch.get("chapter_no")
        if isinstance(c_no, str) and c_no and c_no[0].isalpha():
            return True
        return False

    # ── S1：structure 存在且归一化后 chapters 非空 ──────────────────────────
    s1_violations: list = []
    if not chapters:
        s1_violations.append("structure.chapters 为空——大纲未声明任何章节")
    result["checks"]["S1"] = {
        "level": "FATAL",
        "desc": "structure 存在且归一化后 chapters 非空",
        "passed": not s1_violations,
        "violations": s1_violations,
    }

    # ── S2：每章有非空 chapter_title ──────────────────────────────────────
    s2_violations = [
        f"第 {ch.get('chapter_no', i + 1)} 章缺少非空 chapter_title"
        for i, ch in enumerate(chapters)
        if isinstance(ch, dict) and not str(ch.get("chapter_title") or "").strip()
    ]
    result["checks"]["S2"] = {
        "level": "FATAL",
        "desc": "每个 chapters[*] 有非空 chapter_title",
        "passed": not s2_violations,
        "violations": s2_violations,
    }

    # ── S3：每章（非 appendix）sections 条目数 >= 2 ────────────────────────
    s3_violations = []
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            continue
        if _is_appendix(ch):
            continue  # 附录不要求 sections >= 2
        secs = ch.get("sections") or []
        if len(secs) < MIN_SECTIONS_PER_CHAPTER:
            s3_violations.append(
                f"第 {ch.get('chapter_no', i + 1)} 章"
                f"「{str(ch.get('chapter_title') or '')[:20]}」"
                f"只声明了 {len(secs)} 个节，少于要求的 {MIN_SECTIONS_PER_CHAPTER} 个"
            )
    result["checks"]["S3"] = {
        "level": "FATAL",
        "desc": f"每个 chapters[*]（非 appendix）的 sections 条目数 >= {MIN_SECTIONS_PER_CHAPTER}",
        "passed": not s3_violations,
        "violations": s3_violations,
    }

    # ── S4：每个 section 有非空 section_no 与 section_title ───────────────
    s4_violations = []
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            continue
        c_no = ch.get("chapter_no", i + 1)
        for j, sec in enumerate(ch.get("sections") or []):
            if not isinstance(sec, dict):
                s4_violations.append(f"第 {c_no} 章第 {j + 1} 个 section 不是映射结构")
                continue
            if not str(sec.get("section_no") or "").strip():
                s4_violations.append(f"第 {c_no} 章第 {j + 1} 个 section 缺少 section_no")
            if not str(sec.get("section_title") or "").strip():
                s4_violations.append(f"第 {c_no} 章第 {j + 1} 个 section 缺少 section_title")
    result["checks"]["S4"] = {
        "level": "FATAL",
        "desc": "每个 sections[*] 有非空 section_no 与 section_title",
        "passed": not s4_violations,
        "violations": s4_violations,
    }

    # ── S5：YAML 章标题集合 == Markdown 正文 ## 标题集合（去编号后）───────
    yaml_titles = {
        _strip_chapter_num(ch.get("chapter_title"))
        for ch in chapters
        if isinstance(ch, dict) and str(ch.get("chapter_title") or "").strip()
    }
    md_titles = {_strip_chapter_num(m) for m in _RE_MD_H2.findall(body or "")}
    only_yaml = sorted(t for t in yaml_titles - md_titles if t)
    only_md = sorted(t for t in md_titles - yaml_titles if t)
    result["checks"]["S5"] = {
        "level": "WARNING",
        "desc": "YAML 声明的章标题集合 == Markdown 正文 ## 标题集合（去编号后）",
        "passed": not only_yaml and not only_md,
        "violations": (
            [f"仅在 YAML 中出现: {t}" for t in only_yaml]
            + [f"仅在 Markdown 正文中出现: {t}" for t in only_md]
        ),
    }

    # ── S6：section_title 不含编号前缀（复用 headings.py 的剥离函数）──────
    s6_violations = []
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            continue
        c_no = ch.get("chapter_no", i + 1)
        for sec in ch.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            raw = str(sec.get("section_title") or "").strip()
            if not raw:
                continue
            stripped = _strip_section(raw, 0, issues)
            if isinstance(stripped, tuple):
                stripped = stripped[0]
            if str(stripped).strip() != raw:
                s6_violations.append(
                    f"第 {c_no} 章的 section_title「{raw}」含编号前缀，"
                    f"应为纯文字「{str(stripped).strip()}」"
                )
    result["checks"]["S6"] = {
        "level": "WARNING",
        "desc": "section_title 不含编号前缀",
        "passed": not s6_violations,
        "violations": s6_violations,
    }

    s1_s4 = all(result["checks"][k]["passed"] for k in ("S1", "S2", "S3", "S4"))
    result["s1_s4_passed"] = s1_s4
    # warn 模式下即使 S1-S4 违规也判 passed（只报告不阻断），与 U3/U4/U6 同口径
    result["passed"] = s1_s4 if gate_mode == "strict" else True
    return result


def _structure_to_yaml_value(struct: dict) -> dict:
    """将 v2 structure 转为 YAML 友好的纯数据 dict，便于 yaml.dump 输出。

    确保 YAML 输出使用中文友好的块风格，不使用 !!python 标签。
    """
    if not isinstance(struct, dict):
        return struct
    result: dict = {}
    if "title" in struct:
        result["title"] = struct["title"]
    if "chapters" in struct:
        chapters_out = []
        for ch in struct["chapters"]:
            if not isinstance(ch, dict):
                chapters_out.append(ch)
                continue
            c = {"chapter_no": ch.get("chapter_no"), "chapter_title": ch.get("chapter_title", "")}
            if ch.get("is_appendix"):
                c["is_appendix"] = True
            sections = ch.get("sections") or []
            if sections:
                c["sections"] = [
                    {"section_no": s.get("section_no"), "section_title": s.get("section_title", "")}
                    if isinstance(s, dict) else s
                    for s in sections
                ]
            else:
                c["sections"] = []
            chapters_out.append(c)
        result["chapters"] = chapters_out
    return result


def normalize_and_print(outline_path: str) -> None:
    """--normalize 模式：读取旧 outline，输出 v2 格式 YAML front matter + 正文到 stdout。"""
    import yaml

    path = Path(outline_path)
    if not path.exists():
        print(f"错误：outline.md 不存在: {outline_path}", file=sys.stderr)
        sys.exit(2)

    text = path.read_text(encoding="utf-8", errors="replace")
    parsed, body = extract_yaml_front_matter(text, str(path))
    if not isinstance(parsed, dict):
        print("错误：outline.md 缺少有效的 YAML front matter", file=sys.stderr)
        sys.exit(2)

    raw_structure = parsed.get("structure")
    if not isinstance(raw_structure, dict):
        print("错误：YAML front matter 中缺少 structure 节点", file=sys.stderr)
        sys.exit(2)

    # 两级归一化：先补键名，再转换格式
    structure = normalize_outline_structure(raw_structure, str(path))
    structure_v2 = normalize_outline_v1_to_v2(structure)

    # 构建新的 front matter（保留原 front matter 中除 structure 外的其他字段）
    new_parsed = {k: v for k, v in parsed.items() if k != "structure"}
    new_parsed["structure"] = _structure_to_yaml_value(structure_v2)

    # 输出：---\n YAML \n---\n 正文
    yaml_text = yaml.dump(
        new_parsed,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    print("---")
    print(yaml_text.rstrip("\n"))
    print("---")
    if body:
        print(body)


def format_text_report(result: dict) -> str:
    lines = [
        f"=== 阶段4 大纲结构完整性门禁（D1-9，S1-S6）"
        f"[gate_mode={result['gate_mode']}] ===",
        "",
    ]
    if result.get("error"):
        lines.append(f"{FAIL} {result['error']}")
        return "\n".join(lines)
    if result.get("note"):
        lines.append(f"{WARN} {result['note']}")
        return "\n".join(lines)

    for key in ("S1", "S2", "S3", "S4", "S5", "S6"):
        chk = result["checks"].get(key)
        if not chk:
            continue
        mark = OK if chk["passed"] else (FAIL if chk["level"] == "FATAL" else WARN)
        lines.append(f"{mark} {key}（{chk['level']}）: {chk['desc']}")
        for v in chk["violations"][:10]:
            lines.append(f"      - {v}")
        if len(chk["violations"]) > 10:
            lines.append(f"      ... 另有 {len(chk['violations']) - 10} 项")

    lines.append("")
    # CP3 呈报须附机器判据数字（D1 §9.5 C3 的缓解措施：使确认对象是数字而非印象）
    declared_chapters = len(
        [c for c in result["checks"].get("S2", {}).get("violations", [])]
    )
    lines.append(
        f"S1-S4（FATAL 级）整体判定: {'PASS' if result['s1_s4_passed'] else 'FAIL'}"
    )
    if not result["s1_s4_passed"]:
        if result["gate_mode"] == "strict":
            lines.append(
                f"{FAIL} strict 模式：S1-S4 未通过，阶段 4 CP3 阻断，"
                f"不得进入阶段 5"
            )
        else:
            lines.append(
                f"{WARN} warn 模式（首版默认，U6 裁决）：S1-S4 未通过但**不阻断**。"
                f"存量项目按此口径放行；新项目应补齐 section 级声明"
            )
            lines.append(f"      切换 strict 的判据：{result['strict_switch_criterion']}")
    _ = declared_chapters
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段4 大纲结构完整性门禁（D1-9，S1-S6 六项检查）"
    )
    parser.add_argument("--outline", required=True, help="outline.md 路径")
    parser.add_argument(
        "--structure-gate", dest="gate_mode",
        choices=("off", "warn", "strict"), default="warn",
        help="三态开关：off 跳过 | warn（首版默认，U6 裁决）只报告不阻断 | "
             "strict S1-S4 违规即阻断",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument(
        "--normalize", action="store_true",
        help="格式转换模式：读旧格式 outline（frontmatter/bodymatter/appendix），"
             "输出 v2 格式（扁平 chapters 数组）YAML front matter + 正文到 stdout，"
             "不做门禁检查",
    )
    args = parser.parse_args()

    if args.normalize:
        normalize_and_print(args.outline)
        return

    result = run_structure_gate(args.outline, args.gate_mode)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    if result.get("error"):
        sys.exit(2)
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
