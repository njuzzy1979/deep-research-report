#!/usr/bin/env python3
"""outline.md 标题树提取（阶段 7 注入用，跨模型兼容性优化方案 §三 B2）。

职责（方案 §B2）：把 ``references/multiagent-orchestration.md`` §8.5「Writer
注入时的标题提取规则（确定性要求）」这条纯 prompt 级规则落成脚本——orchestrator
在阶段 7 为 ``chapter_writer_agent`` 注入"当前章大纲条目"时，不应再靠自己肉眼
判断该注入什么标题文字，而是调用本脚本一次拿到确定性结果。

§8.5 规则原文摘要（脚本行为的唯一权威依据，逐条对应实现）：
    1. 标题文本来源：从 YAML ``structure.bodymatter[*].sections[*].section_title``
       取纯文字标题，``section_no`` 是编号元数据不注入
    2. 注入格式：纯文字，不附带编号前缀（不写"1.1 军事需求分析"）
    3. Markdown heading 中的编号仅供人读，orchestrator 不得从 heading 行解析
       标题——但本脚本额外做**只读**的一致性核验（§8.5 第 4 条），不代表
       "以 Markdown 为准"，纯文字标题仍以 YAML ``section_title`` 为唯一来源
    4. YAML-Markdown 一致性校验：YAML 声明与 Markdown heading（去编号后）
       不一致时标记告警，提示大纲架构师修正

**关键验收标准**：输出的标题不含任何编号前缀。即使 YAML 里 ``section_title``
本身写成 ``"1.1 技术路线分析"``（大纲架构师笔误把编号写进了标题字段），提取
结果也必须是纯文字 ``"技术路线分析"``——本脚本复用
``scripts/md2docx/assemble/headings.py`` 的编号剥离函数
（``_strip_chapter``/``_strip_section``/``_strip_subsection``/``_strip_appendix``，
其正则来自 ``config.py`` 的 N-01~N-07 单一事实来源）对 YAML 侧标题文本也做
剥离，不是只信任 YAML 本身"应该"是纯文字。

YAML 结构解析本身**不重新实现**——直接复用
``scripts/md2docx/assemble/outline_reader.py`` 的
``extract_yaml_front_matter()``/``_find_parent_section_idx()``
（依赖 A1 修复完成，现已完成）。outline_reader 模块内另有一个扁平化查找表
构建函数，返回 ``{标题: (Kind, 编号)}`` 形式，会丢失章→节→小节父子层级，
而本模块的产出恰恰是层级树，因此不复用它——自行遍历 ``structure`` 各层级。

用法：
    python scripts/outline_title_extract.py --outline research/outline.md [--chapter-no N] [--json]

退出码：
    0 = 提取成功（即使存在 YAML/Markdown 一致性告警——告警通过 JSON 的
        ``consistency_warnings`` 字段 / 文本报告传给 orchestrator 自行判断，
        不视为失败。方案 §D1 对 B2 的失败路由只定义了"提取为空 → P0"一项，
        一致性告警属于报告性核验，不应阻断阶段 7 单章注入的正常流程）
    1 = 提取为空（--chapter-no 指定的章不存在，或整份大纲无任何标题）
    2 = 读取错误（文件不存在/不可读、YAML 解析失败、缺少 structure 节点）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py:42-48 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 本文件位于 scripts/ 下，与 md2docx 包同级；`python scripts/outline_title_extract.py`
# 运行时 Python 自动把脚本所在目录加入 sys.path[0]，故 `import md2docx` 直接可用
# （同 scripts/figure_gate.py 对 degradation_log 的直接 import 一致做法）。
from md2docx.assemble.outline_reader import (
    _find_parent_section_idx,
    extract_yaml_front_matter,
)
from md2docx.assemble.headings import (
    _strip_appendix,
    _strip_chapter,
    _strip_section,
    _strip_subsection,
)
from md2docx.issues import IssueCollector

# 降级台账（跨模型兼容性优化方案 §二 A2）：容错兜底为 no-op，
# 避免可观测性依赖影响主流程（沿用 output_envelope_check.py 同款模式）。
try:
    from degradation_log import record_degradation
except ImportError:
    def record_degradation(**kwargs):  # type: ignore[no-redef]
        pass

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

# Markdown heading 提取正则：仅 H2-H4（章/节/小节可能出现的层级）
_RE_MD_HEADING = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.MULTILINE)


def read_outline_text(path: Path) -> str:
    """二进制安全读取，处理 BOM / CRLF（与 contract_check.py:112-120 同款模式）。"""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strip_number_prefix(raw_text: str, level_hashes: int, issues: IssueCollector) -> str:
    """按标题级别（H2/H3/H4）复用 headings.py 的剥离函数，返回纯文字标题。

    H2 优先尝试附录模式（``_strip_appendix``，字面量"附录"前缀，命中判据独立于
    章节编号形状），未命中再退化到章编号剥离（``_strip_chapter``，N-01/02/05/06）。
    H3 用 ``_strip_section``（N-04 + M6_H3），H4 用 ``_strip_subsection``
    （N-03 + M6_H4）。三/四级之外的层级原样返回（调用方不会传入非 2-4 的级别）。
    """
    text = raw_text.strip()
    if level_hashes == 2:
        stripped, letter = _strip_appendix(text, 0, issues)
        if letter is not None:  # 命中附录模式（letter 可能是空串，代表命中但未捕获字母）
            return stripped.strip()
        stripped, _orig_no = _strip_chapter(text, 0, issues)
        return stripped.strip()
    if level_hashes == 3:
        return _strip_section(text, 0, issues).strip()
    # level_hashes == 4
    return _strip_subsection(text, 0, issues).strip()


# ---------------------------------------------------------------------------
# YAML 侧：标题树构建
# ---------------------------------------------------------------------------


def build_title_tree(
    structure: dict, issues: IssueCollector, chapter_no: Optional[int] = None
) -> dict:
    """从 YAML ``structure`` 节点构建纯文字标题树。

    Args:
        structure: outline.md YAML 解析后的 ``structure`` 节点。
        issues: 剥离函数要求的 IssueCollector 参数（本脚本不消费其内容，
            仅满足 headings.py 剥离函数的签名要求）。
        chapter_no: 指定时只保留该章（frontmatter/appendix 一并置空——
            阶段 7 单章注入场景下只关心当前章的大纲条目）。

    Returns:
        {"frontmatter": [...], "chapters": [...], "appendix": [...]}
        三个键的具体结构见各分支注释。
    """
    tree: dict = {"frontmatter": [], "chapters": [], "appendix": []}

    if not isinstance(structure, dict):
        return tree

    # ── frontmatter（chapter_no 过滤时不含前置件，只关心目标章） ──
    if chapter_no is None:
        front_items = structure.get("frontmatter", [])
        if isinstance(front_items, list):
            for item in front_items:
                if not isinstance(item, dict):
                    continue
                ch_title_raw = str(item.get("chapter_title", "") or "")
                ch_title = _strip_number_prefix(ch_title_raw, 2, issues) if ch_title_raw.strip() else ""
                sections: list[str] = []
                for sec in item.get("sections", []) or []:
                    if isinstance(sec, dict):
                        sec_title_raw = str(sec.get("section_title", "") or "")
                    elif isinstance(sec, str):
                        sec_title_raw = sec
                    else:
                        continue
                    if not sec_title_raw.strip():
                        continue
                    sections.append(_strip_number_prefix(sec_title_raw, 3, issues))
                if ch_title or sections:
                    tree["frontmatter"].append({"chapter_title": ch_title, "sections": sections})

    # ── bodymatter ──
    body_items = structure.get("bodymatter", [])
    if isinstance(body_items, list):
        for ch in body_items:
            if not isinstance(ch, dict):
                continue
            ch_no = ch.get("chapter_no")
            if chapter_no is not None and ch_no != chapter_no:
                continue

            ch_title_raw = str(ch.get("chapter_title", "") or "")
            ch_title = _strip_number_prefix(ch_title_raw, 2, issues) if ch_title_raw.strip() else ""

            sections_raw = ch.get("sections", []) or []
            section_entries: list[dict] = []
            for sec in sections_raw:
                if isinstance(sec, dict):
                    sec_no = str(sec.get("section_no", "") or "")
                    sec_title_raw = str(sec.get("section_title", "") or "")
                elif isinstance(sec, str):
                    sec_no = ""
                    sec_title_raw = sec
                else:
                    continue
                sec_title = (
                    _strip_number_prefix(sec_title_raw, 3, issues) if sec_title_raw.strip() else ""
                )
                section_entries.append(
                    {"section_no": sec_no, "section_title": sec_title, "subsections": []}
                )

            # subsections：复用 outline_reader._find_parent_section_idx 做 parent 匹配，
            # 不重新实现"parent_section_no/parent 新旧字段名兼容"这套已有逻辑。
            subsections_raw = ch.get("subsections", []) or []
            if isinstance(subsections_raw, list):
                for sub in subsections_raw:
                    if not isinstance(sub, dict):
                        continue
                    if "parent_section_no" in sub:
                        parent_identifier = str(sub.get("parent_section_no") or "")
                        parent_is_title_text = False
                    elif "parent" in sub:
                        parent_identifier = str(sub.get("parent") or "")
                        parent_is_title_text = True
                    else:
                        parent_identifier = ""
                        parent_is_title_text = False

                    if "subsection_title" in sub:
                        sub_title_raw = str(sub.get("subsection_title") or "")
                    elif "title" in sub:
                        sub_title_raw = str(sub.get("title") or "")
                    else:
                        sub_title_raw = ""

                    if not parent_identifier.strip() or not sub_title_raw.strip():
                        continue

                    parent_idx = _find_parent_section_idx(
                        sections_raw, parent_identifier, parent_is_title_text
                    )
                    sub_title = _strip_number_prefix(sub_title_raw, 4, issues)
                    if parent_idx is not None and 1 <= parent_idx <= len(section_entries):
                        section_entries[parent_idx - 1]["subsections"].append(sub_title)
                    # 匹配失败的孤儿 subsection：outline_reader 侧已经写过台账
                    # （subsection_parent_not_found），本脚本不重复记录，静默跳过即可。

            tree["chapters"].append(
                {"chapter_no": ch_no, "chapter_title": ch_title, "sections": section_entries}
            )

    # ── appendix（chapter_no 过滤时不含附录） ──
    if chapter_no is None:
        app_items = structure.get("appendix", [])
        if isinstance(app_items, list):
            for app in app_items:
                if not isinstance(app, dict):
                    continue
                letter = str(app.get("appendix_letter", "") or "")
                title_raw = str(app.get("appendix_title", "") or "")
                if not title_raw.strip():
                    continue
                title = _strip_number_prefix(title_raw, 2, issues)
                tree["appendix"].append({"appendix_letter": letter, "appendix_title": title})

    return tree


def flatten_tree_titles(tree: dict) -> dict[str, str]:
    """把标题树展平为 {纯文字标题: 层级标签} 字典，供一致性比对使用。"""
    titles: dict[str, str] = {}
    for fm in tree["frontmatter"]:
        if fm["chapter_title"]:
            titles[fm["chapter_title"]] = "chapter"
        for s in fm["sections"]:
            titles[s] = "section"
    for ch in tree["chapters"]:
        if ch["chapter_title"]:
            titles[ch["chapter_title"]] = "chapter"
        for sec in ch["sections"]:
            if sec["section_title"]:
                titles[sec["section_title"]] = "section"
            for sub in sec["subsections"]:
                titles[sub] = "subsection"
    for app in tree["appendix"]:
        if app["appendix_title"]:
            titles[app["appendix_title"]] = "chapter"  # 附录是 H2 级别
    return titles


# ---------------------------------------------------------------------------
# Markdown 侧：heading 提取（仅用于一致性核验，不作为标题文本来源——§8.5 第 3 条）
# ---------------------------------------------------------------------------


def extract_markdown_headings(body_text: str, issues: IssueCollector) -> dict[str, str]:
    """从 Markdown 正文提取 H2-H4 heading，剥离编号后返回 {纯文字标题: 层级标签}。

    仅用于 §8.5 第 4 条的一致性核验，**不**是标题文本的注入来源（来源恒为
    YAML section_title，见模块 docstring）。围栏代码块内的 ``#`` 开头行需
    排除，避免误判为标题（沿用 contract_check.py 的 strip_code_blocks 思路）。
    """
    clean = re.sub(r"```.*?```", "", body_text, flags=re.DOTALL)
    result: dict[str, str] = {}
    for m in _RE_MD_HEADING.finditer(clean):
        level_hashes = len(m.group(1))
        raw_text = m.group(2)
        level_tag = {2: "chapter", 3: "section", 4: "subsection"}[level_hashes]
        stripped = _strip_number_prefix(raw_text, level_hashes, issues)
        if stripped:
            result[stripped] = level_tag
    return result


def check_consistency(
    yaml_titles: dict[str, str],
    md_titles: dict[str, str],
    check_markdown_only: bool = True,
) -> list[dict]:
    """比对 YAML 声明标题集合与 Markdown 正文实际 heading 集合。

    产出三类告警（multiagent-orchestration.md §8.5 第 4 条）：
      - yaml_only：YAML 有但正文缺失
      - markdown_only：正文有但 YAML 未声明
      - 两者文字不一致：本实现不做语义配对（无法可靠判断"哪个 yaml_only 和
        哪个 markdown_only 是同一标题的不同写法" vs "确实是两个不同标题"），
        而是通过集合差集统一表达——一对"同层级、位置相近"的 yaml_only +
        markdown_only 条目在实践中通常就对应"文字不一致"场景，人工核对时
        两条告警放在一起看即可辨认，不强行做模糊匹配以免引入新的误判源。

    Args:
        check_markdown_only: 是否检查 markdown_only 方向（正文有但 YAML 未声明）。
            ``--chapter-no`` 单章过滤场景下 ``yaml_titles`` 只含目标章标题，而
            ``md_titles`` 来自**整份**正文（Markdown 侧本来就不该、也无法按章号
            切片——同一份 Markdown 文件里其他章节的 heading 与本章无关）。此时
            若仍双向比对，除目标章外所有章节的每条 heading 都会被判定为
            "正文有但本章 YAML 未声明"，这是规则误用而非真实的不一致（规则本意
            是"同一标题在 YAML 与 Markdown 两处写法是否一致"，不是"本章 YAML
            没声明别章标题"，见 multiagent-orchestration.md §8.5 第 4 条 /
            D-1a 缺陷修复说明）。调用方在 chapter_no 过滤时应传 False，只保留
            yaml_only 方向（"本章 YAML 声明了但正文没有"在单章语境下仍是有效
            信号，不受该问题影响）。
    """
    warnings: list[dict] = []
    for title, level in yaml_titles.items():
        if title not in md_titles:
            warnings.append(
                {
                    "type": "yaml_only",
                    "title": title,
                    "level": level,
                    "message": f"YAML 声明标题「{title}」（{level}）在 Markdown 正文中未找到匹配 heading",
                }
            )
    if check_markdown_only:
        for title, level in md_titles.items():
            if title not in yaml_titles:
                warnings.append(
                    {
                        "type": "markdown_only",
                        "title": title,
                        "level": level,
                        "message": f"Markdown 正文 heading「{title}」（{level}）未在 YAML 结构清单中声明",
                    }
                )
    return warnings


# ---------------------------------------------------------------------------
# 主提取流程
# ---------------------------------------------------------------------------


def run_extract(
    structure: dict,
    body_text: str,
    outline_path: str,
    chapter_no: Optional[int] = None,
) -> dict:
    """执行标题树提取 + 一致性核验，返回结构化结果，函数级可复用。"""
    issues = IssueCollector()
    tree = build_title_tree(structure, issues, chapter_no=chapter_no)
    yaml_titles = flatten_tree_titles(tree)
    md_titles = extract_markdown_headings(body_text, issues)
    # chapter_no 过滤时抑制 markdown_only 方向：yaml_titles 只含目标章标题，
    # md_titles 却来自整份正文，双向比对会把其他章节的每条 heading 都误判为
    # "本章 YAML 未声明"（D-1a 缺陷）。详见 check_consistency() docstring。
    warnings = check_consistency(
        yaml_titles, md_titles, check_markdown_only=(chapter_no is None)
    )

    # 写降级台账：L-记录（跨模型兼容性优化方案 §A2——L-记录 定义为"记录下来但
    # 不影响产出"的场景。本告警的 fallback_used 是 report_only_no_auto_fix，
    # 即没有发生任何数据丢失或自动回退，纯粹是大纲文档内部 YAML/Markdown 两处
    # 标题写法不同步的报告性提示。区别于 L-显著——后者专指"YAML 解析失败回退
    # 启发式、subsections 丢弃、图表清单降级"等数据实际丢失的场景。定为
    # L-显著会让每次大纲不同步都阻断 CP6 交付，强度过高，故降为 L-记录）。
    for w in warnings:
        record_degradation(
            stage="stage7",
            component="outline_title_extract",
            reason="yaml_markdown_title_mismatch",
            level="L-记录",
            fallback_used="report_only_no_auto_fix",
            impact=w["message"],
            input_path=outline_path,
            instance_key=f"{w['type']}:{w['title']}",
        )

    if chapter_no is not None:
        is_empty = len(tree["chapters"]) == 0
    else:
        is_empty = not tree["frontmatter"] and not tree["chapters"] and not tree["appendix"]

    return {
        "outline_path": outline_path,
        "chapter_no_filter": chapter_no,
        "frontmatter": tree["frontmatter"],
        "chapters": tree["chapters"],
        "appendix": tree["appendix"],
        "consistency_warnings": warnings,
        "empty": is_empty,
    }


# ---------------------------------------------------------------------------
# 报告格式化
# ---------------------------------------------------------------------------


def _format_tree_lines(result: dict) -> list[str]:
    lines: list[str] = []
    if result["frontmatter"]:
        lines.append("-- 前置件 --")
        for fm in result["frontmatter"]:
            lines.append(f"  {fm['chapter_title']}")
            for s in fm["sections"]:
                lines.append(f"    - {s}")
        lines.append("")

    lines.append("-- 正文 --")
    if not result["chapters"]:
        lines.append("  (无匹配章节)")
    for ch in result["chapters"]:
        lines.append(f"  第{ch['chapter_no']}章 {ch['chapter_title']}")
        for sec in ch["sections"]:
            lines.append(f"    {sec['section_no']} {sec['section_title']}")
            for sub in sec["subsections"]:
                lines.append(f"      - {sub}")
    lines.append("")

    if result["appendix"]:
        lines.append("-- 附录 --")
        for app in result["appendix"]:
            lines.append(f"  附录{app['appendix_letter']} {app['appendix_title']}")
        lines.append("")

    return lines


def format_text_report(result: dict) -> str:
    lines = [
        f"=== outline.md 标题树提取：{result['outline_path']} "
        f"（章号过滤={result['chapter_no_filter'] if result['chapter_no_filter'] is not None else '无'}）===",
        "",
    ]
    lines.extend(_format_tree_lines(result))

    warnings = result["consistency_warnings"]
    mark = OK if not warnings else WARN
    lines.append(f"{mark} YAML/Markdown 一致性告警: {len(warnings)} 条")
    for w in warnings:
        lines.append(f"      - [{w['type']}] {w['message']}")
    lines.append("")

    if result["empty"]:
        lines.append("=== 总判定: FAIL（提取为空） ===")
    elif warnings:
        lines.append("=== 总判定: PASS（存在一致性告警，见上，不阻断 exit code） ===")
    else:
        lines.append("=== 总判定: PASS ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="outline.md 标题树提取（阶段 7 注入用，剥离编号前缀 + YAML/Markdown 一致性核验）"
    )
    parser.add_argument("--outline", required=True, help="outline.md 文件路径")
    parser.add_argument("--chapter-no", type=int, default=None, help="仅提取指定章号（阶段 7 单章注入场景）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 orchestrator 解析）")
    args = parser.parse_args()

    outline_path = Path(args.outline)
    if not outline_path.exists():
        print(f"{FAIL} outline 文件不存在: {args.outline}", file=sys.stderr)
        sys.exit(2)

    try:
        text = read_outline_text(outline_path)
    except Exception as e:
        print(f"{FAIL} outline 文件读取失败: {e}", file=sys.stderr)
        sys.exit(2)

    parsed, body = extract_yaml_front_matter(text, outline_path=str(outline_path))
    if parsed is None:
        print(
            f"{FAIL} outline.md YAML front matter 解析失败或不存在"
            f"（详见 stderr 诊断 / 降级台账）",
            file=sys.stderr,
        )
        sys.exit(2)

    structure = parsed.get("structure")
    if not isinstance(structure, dict):
        print(f"{FAIL} outline.md YAML 缺少 structure 节点", file=sys.stderr)
        sys.exit(2)

    result = run_extract(structure, body, outline_path=str(outline_path), chapter_no=args.chapter_no)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    if result["empty"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
