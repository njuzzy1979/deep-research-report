"""转换报告生成模块（C-13）。

每次转换完成后生成一份 Markdown 格式的转换报告，记录转换过程的完整信息。
报告结构遵循 03-workflow.md §5 的 schema，包含 7 节 + 检查清单表。

全项目唯一写报告路径（G-01 硬约束）：所有文件写入均经 iotools.write_text()。
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from . import __version__
from .iotools import write_text
from .issues import IssueCollector, Level

if TYPE_CHECKING:
    from .config import BehaviorFlags
    from .ir import DocumentIR

# ---------------------------------------------------------------------------
# G-11：timestamp 使用固定 build-date 兜底，保证幂等
# ---------------------------------------------------------------------------
_BUILD_DATE_FALLBACK = "2000-01-01"

# ---- 门3 检查项定义（03-workflow.md §5 14 项，与规格保持单一事实来源） ----
_GATE3_CHECKS: list[tuple[int, str]] = [
    (1, "封面完整（标题/副标题/机构/日期/版本）"),
    (2, "全篇无密级标注"),
    (3, "目录自动生成（TOC 域）"),
    (4, "章节编号连续无跳号"),
    (5, "图表编号连续"),
    (6, "表格全框线"),
    (7, "页码正确（摘要罗马/正文阿拉伯）"),
    (8, "页眉页脚完整"),
    (9, "分页规划一致性（R15）"),
    (10, "TOC/PAGE/PAGEREF 域三态"),
    (11, "无空白页"),
    (12, "链接可点击"),
    (13, "表体字号校验（10.5pt）"),
    (14, "字体（系统通用字体）"),
]


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def generate_report(
    ir: DocumentIR | None,
    issues: IssueCollector,
    output_docx_path: str,
    elapsed_sec: float,
    flags: BehaviorFlags | None,
    gate3_results: dict | None = None,
    *,
    build_date: str = _BUILD_DATE_FALLBACK,
    source_path: str = "",
) -> str:
    """生成转换报告，返回报告文件路径。

    Args:
        ir: DocumentIR（FATAL 短路路径下可能为 None，此时统计段放置降级说明）。
        issues: 全流程 Issue 收集器。
        output_docx_path: 输出 docx 的绝对路径。
        elapsed_sec: 转换耗时（秒）。
        flags: 最终生效的 BehaviorFlags；为 None 时配置摘要段标记为不可用。
        gate3_results: 门3 14 项检查的逐项结果 dict，key 为检查项编号 1-14，
            value 为 bool 或 None；None 时全部标记为未执行。
        build_date: 用于报告时间戳的固定日期（G-11 幂等要求）；默认 2000-01-01。
        source_path: 源 md 文件路径；若 ir 不含此字段且调用方未传入，显示占位提示。

    Returns:
        报告文件的绝对路径。
    """
    # ---- 确定源文件路径 ----
    src = source_path or getattr(ir, "source_path", "")
    if not src:
        src = "（未记录——FATAL 短路路径）"

    # ---- 确定退出码 ----
    exit_code = _determine_exit_code(issues)
    exit_meaning = _exit_code_meaning(exit_code)

    # ---- 组装报告正文 ----
    lines: list[str] = []
    _append_section_overview(lines, src, output_docx_path, elapsed_sec, exit_code, exit_meaning, build_date)
    _append_section_stats(lines, ir)
    _append_section_issues(lines, issues)
    _append_section_config(lines, flags)
    _append_section_gate3(lines, gate3_results)
    _append_section_review(lines, issues)
    _append_section_next_steps(lines, output_docx_path)

    report_text = "\n".join(lines) + "\n"

    # ---- 确定报告路径并写入（G-01：必须经 iotools） ----
    report_path = _report_path(output_docx_path)
    write_text(report_path, report_text)
    return report_path


def generate(options, issues: IssueCollector, source_meta=None,
             gate3_results: dict | None = None, document_ir=None) -> str | None:
    """兼容入口：供 pipeline.py _emit_report 调用。

    pipeline.py 当前不传 ir/flags/elapsed/gate3 等参数到报告阶段，此包装函数
    从 RunOptions 和已有 IssueCollector 提取可用信息，以降级模式调用
    generate_report()。

    调用方约定的入口签名（pipeline.py _emit_report 占位约定）：
        module.generate(options, issues, source_meta, gate3_results=gate3_results, document_ir=document_ir)
    """
    from .config import BehaviorFlags

    # 从 RunOptions 构造行为开关的近似视图（pipeline 未传入已解析的 BehaviorFlags，
    # 此处只能从 CLI 显式值和预置默认值拼出一个近似 flags，供报告 §4 配置摘要使用）。
    flags = BehaviorFlags(
        strict=bool(options.strict),
        allow_missing_figures=bool(options.allow_missing_figures),
        appendix_page_break=options.appendix_page_break
        if options.appendix_page_break is not None
        else True,
        dump_intermediate=bool(options.dump_intermediate),
        generate_figures_table_toc=options.generate_figures_table_toc or "auto",
    )

    return generate_report(
        ir=document_ir,
        issues=issues,
        output_docx_path=options.output_path,
        elapsed_sec=0.0,
        flags=flags,
        gate3_results=gate3_results,
        build_date=options.build_date or _BUILD_DATE_FALLBACK,
        source_path=options.input_path,
    )


# ---------------------------------------------------------------------------
# 私有辅助
# ---------------------------------------------------------------------------


def _report_path(output_docx_path: str) -> str:
    """由 docx 路径推导报告路径：{stem}.conversion-report.md（R7 裁决）。"""
    stem, _ext = os.path.splitext(output_docx_path)
    return stem + ".conversion-report.md"


def _determine_exit_code(issues: IssueCollector) -> int:
    """R2 退出码判定：FATAL→2 / ERROR→1 / 否则→0。"""
    if issues.has_fatal():
        return 2
    if issues.has_error():
        return 1
    return 0


def _exit_code_meaning(code: int) -> str:
    return {0: "成功（可含 WARNING）", 1: "含 ERROR", 2: "FATAL 或参数错误"}.get(code, "未知")


# ---------------------------------------------------------------------------
# §1 转换概览
# ---------------------------------------------------------------------------


def _append_section_overview(
    lines: list[str],
    source_path: str,
    output_docx_path: str,
    elapsed_sec: float,
    exit_code: int,
    exit_meaning: str,
    build_date: str,
) -> None:
    lines.append("# 转换报告")
    lines.append("")
    lines.append(f"- **源文件**：{source_path}")
    lines.append(f"- **输出文件**：{output_docx_path}")
    lines.append(f"- **转换时间**：{build_date} 00:00:00")
    lines.append(f"- **耗时**：{elapsed_sec:.1f} 秒")
    lines.append(f"- **转换器版本**：{__version__}")
    lines.append(f"- **退出码**：{exit_code}（{exit_meaning}）")
    lines.append("")


# ---------------------------------------------------------------------------
# §2 文档统计
# ---------------------------------------------------------------------------


def _append_section_stats(lines: list[str], ir: DocumentIR | None) -> None:
    lines.append("## 文档统计")
    lines.append("")
    lines.append("| 项目 | 数量 |")
    lines.append("|------|------|")

    if ir is None:
        lines.append("| 章 (H1) | — |")
        lines.append("| 节 (H2) | — |")
        lines.append("| 小节 (H3) | — |")
        lines.append("| 图 | — |")
        lines.append("| 正文表 | — |")
        lines.append("| 附录表 | — |")
        lines.append("| 总段落 | — |")
        lines.append("")
        lines.append("> 文档统计不可用：DocumentIR 未构建（FATAL 短路或阶段3 前中断）。")
        lines.append("")
        return

    # 统计标题层级
    from .ir import HeadingIR, HeadingKind

    h1_count = 0
    h2_count = 0
    h3_count = 0
    figure_count = 0
    body_table_count = 0
    appendix_table_count = 0
    paragraph_count = 0

    for elem in ir.elements:
        if isinstance(elem, HeadingIR):
            if elem.kind is HeadingKind.MAIN_TITLE:
                h1_count += 1
            elif elem.kind in (HeadingKind.ABSTRACT, HeadingKind.CHAPTER, HeadingKind.APPENDIX):
                h2_count += 1
            elif elem.kind is HeadingKind.SECTION:
                h3_count += 1
            # PLAIN 类不计入任一统计列（规格仅要求 H1/H2/H3）
        elif hasattr(elem, "figure_id"):
            figure_count += 1
        elif hasattr(elem, "kind") and hasattr(elem, "table_id"):
            from .ir import TableIR, TableKind

            if isinstance(elem, TableIR):
                if elem.kind is TableKind.BODY:
                    body_table_count += 1
                elif elem.kind is TableKind.APPENDIX:
                    appendix_table_count += 1
        elif hasattr(elem, "runs"):
            from .ir import ParagraphIR

            if isinstance(elem, ParagraphIR):
                paragraph_count += 1

    lines.append(f"| 章 (H1) | {h1_count} |")
    lines.append(f"| 节 (H2) | {h2_count} |")
    lines.append(f"| 小节 (H3) | {h3_count} |")
    lines.append(f"| 图 | {figure_count} |")
    lines.append(f"| 正文表 | {body_table_count} |")
    lines.append(f"| 附录表 | {appendix_table_count} |")
    lines.append(f"| 总段落 | {paragraph_count} |")
    lines.append("")


# ---------------------------------------------------------------------------
# §3 Issue 汇总
# ---------------------------------------------------------------------------


def _append_section_issues(lines: list[str], issues: IssueCollector) -> None:
    counts = issues.count_by_level()
    fatal_count = counts[Level.FATAL]
    error_count = counts[Level.ERROR]
    warning_count = counts[Level.WARNING]
    info_count = counts[Level.INFO]

    lines.append("## Issue 汇总")
    lines.append("")
    lines.append("| 级别 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| FATAL | {fatal_count} |")
    lines.append(f"| ERROR | {error_count} |")
    lines.append(f"| WARNING | {warning_count} |")
    lines.append(f"| INFO | {info_count} |")
    lines.append("")

    # 按级别分组列出前 20 条 Issue
    for level in (Level.FATAL, Level.ERROR, Level.WARNING, Level.INFO):
        level_issues = [i for i in issues if i.level is level]
        if not level_issues:
            continue
        display = level_issues[:20]
        lines.append(f"### {level.value}（{len(level_issues)} 条）")
        lines.append("")
        for issue in display:
            loc = ""
            if issue.source_line is not None:
                loc = f"（行 {issue.source_line}）"
            elif issue.element_ref:
                loc = f"（{issue.element_ref}）"
            lines.append(f"- {issue.code}：{issue.message}{loc}")
        if len(level_issues) > 20:
            lines.append(f"- ...（另有 {len(level_issues) - 20} 条 {level.value} 未列出）")
        lines.append("")


# ---------------------------------------------------------------------------
# §4 配置摘要
# ---------------------------------------------------------------------------


def _append_section_config(lines: list[str], flags: BehaviorFlags | None) -> None:
    lines.append("## 配置摘要")
    lines.append("")
    lines.append("| 配置项 | 值 |")
    lines.append("|--------|-----|")

    if flags is None:
        lines.append("| --strict | — |")
        lines.append("| --allow-missing-figures | — |")
        lines.append("| --no-appendix-page-break | — |")
        lines.append("| --dump-intermediate | — |")
        lines.append("| 图表目录生成 | — |")
        lines.append("")
        lines.append("> 配置摘要不可用：BehaviorFlags 未传入（FATAL 短路路径）。")
        lines.append("")
        return

    lines.append(f"| --strict | {'是' if flags.strict else '否'} |")
    lines.append(f"| --allow-missing-figures | {'是' if flags.allow_missing_figures else '否'} |")
    lines.append(
        f"| --no-appendix-page-break | {'是' if not flags.appendix_page_break else '否'} |"
    )
    lines.append(f"| --dump-intermediate | {'是' if flags.dump_intermediate else '否'} |")
    lines.append(f"| 图表目录生成 | {flags.generate_figures_table_toc} |")
    lines.append("")


# ---------------------------------------------------------------------------
# §5 输出校验（门3）
# ---------------------------------------------------------------------------


def _append_section_gate3(lines: list[str], gate3_results: dict | None) -> None:
    lines.append("## 输出校验（门3）")
    lines.append("")
    lines.append("| # | 检查项 | 结果 | 备注 |")
    lines.append("|---|--------|------|------|")

    if gate3_results is None:
        for num, description in _GATE3_CHECKS:
            lines.append(f"| {num} | {description} | — | 未执行（门3 尚未运行或结果未传入） |")
        lines.append("")
        return

    # gate3.py 返回格式：{"checks": [{"id": N, "name": "...", "result": "pass"/"fail"/"warning"/"na", "detail": "..."}]}
    checks_list = gate3_results.get("checks", [])
    # 构建 id→check 查找表
    checks_by_id: dict[int, dict] = {c["id"]: c for c in checks_list}

    # gate3 id → report _GATE3_CHECKS id 映射（两边编号体系不同）
    # gate3 1=密级复检, 2=分页规划, 3=域三态, 4=封面, 5=章节编号, 6=图表编号,
    #         7=表格全框线, 8=页码, 9=页眉页脚, 10=空白页, 11=TOC域, 13=表体字号, 14=字体
    _GATE3_TO_REPORT_MAP = {
        4: 1,   # 封面完整
        1: 2,   # 全篇无密级
        11: 3,  # 目录自动生成（TOC域存在）
        5: 4,   # 章节编号连续
        6: 5,   # 图表编号连续
        7: 6,   # 表格全框线
        8: 7,   # 页码正确
        9: 8,   # 页眉页脚完整
        2: 9,   # 分页规划一致性（R15）
        3: 10,  # TOC/PAGE/PAGEREF 域三态
        10: 11, # 无空白页
        # 12: 12, # 链接可点击（gate3 未实现 id=12，始终标记 N/A）
        13: 13, # 表体字号校验
        14: 14, # 字体（系统通用字体）
    }

    for num, description in _GATE3_CHECKS:
        # 反向查找：report id → gate3 id
        gate3_id = None
        for gid, rid in _GATE3_TO_REPORT_MAP.items():
            if rid == num:
                gate3_id = gid
                break

        if gate3_id is None:
            # 无对应 gate3 检查项（如 id=12 链接可点击）
            lines.append(f"| {num} | {description} | — | 未实现（gate3 无对应检查） |")
            continue

        check = checks_by_id.get(gate3_id)
        if check is None:
            lines.append(f"| {num} | {description} | — | 未执行 |")
            continue

        result = check.get("result", "na")
        detail = check.get("detail", "")
        if result == "pass":
            mark = "✅"
        elif result in ("fail", "warning"):
            mark = "❌" if result == "fail" else "⚠️"
        else:
            mark = "—"
        lines.append(f"| {num} | {description} | {mark} | {detail} |")

    lines.append("")


# ---------------------------------------------------------------------------
# §6 人工复核清单
# ---------------------------------------------------------------------------


def _append_section_review(lines: list[str], issues: IssueCollector) -> None:
    lines.append("## 需人工复核")
    lines.append("")

    review_items = [i for i in issues if i.needs_review]
    if not review_items:
        lines.append("（无）")
        lines.append("")
        return

    for item in review_items:
        loc = ""
        if item.element_ref:
            loc = f"（{item.element_ref}）"
        elif item.source_line is not None:
            loc = f"（行 {item.source_line}）"
        lines.append(f"- {item.code}：{item.message}{loc}")
    lines.append("")


# ---------------------------------------------------------------------------
# §7 后续操作
# ---------------------------------------------------------------------------


def _append_section_next_steps(lines: list[str], output_docx_path: str) -> None:
    lines.append("## 后续操作")
    lines.append("")
    lines.append(f"1. 用 Word 打开 {output_docx_path}")
    lines.append("2. 按 **F9** 更新所有域（目录、页码、图表目录）")
    lines.append('3. **WPS 用户**：右键目录 → "更新域"；右键页码 → "更新域"')
    lines.append("4. 检查封面要素是否完整")
    lines.append("5. 检查图表目录中的页码是否正确跳转")
    lines.append("6. 如有 ❌ 标记的检查项，请对照上方 Issue 列表处理")
    lines.append("")
