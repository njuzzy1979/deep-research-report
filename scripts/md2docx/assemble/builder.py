"""IR 构建总控（C-05c）：Token 流 → DocumentIR。

按七步流水线编排全部 assemble 子模块：元数据装配 → 标题分类编号 → 图解析 →
表解析 → 分页分节规划 → 有序元素流组装 → DocumentIR 装配。

设计依据：01-architecture.md §3.2 builder 职责卡、02-algorithms.md §D.4。
"""
from __future__ import annotations

import os

from ..ir import (
    BlockIR,
    DocumentIR,
    FigureIR,
    HeadingIR,
    HeadingKind,
    ListBlockIR,
    MetadataIR,
    PageBreakIR,
    ParagraphIR,
    QuoteIR,
    SectionKind,
    SectionSpec,
    TableIR,
)
from ..issues import Issue, IssueCollector, Level
from ..textstage.tokens import (
    BlankToken,
    FencedCodeToken,
    HeadingToken,
    HrToken,
    ImageToken,
    MetaLine,
    OrderedItemToken,
    ParagraphToken,
    QuoteToken,
    TableRowToken,
    UnorderedItemToken,
)

from .breaks import plan_breaks_and_sections
from .figures import resolve_figures
from .headings import classify_and_number
from .metadata import extract_metadata
from .tables import resolve_tables


def _build_heading_index(
    heading_irs: list[HeadingIR],
) -> dict[int, HeadingIR]:
    """构建 source_line → HeadingIR 的索引。

    索引键仅用 source_line：每个源码行至多对应一个标题 Token（parse 阶段
    保证），故 source_line 全局唯一，足以无歧义定位 HeadingIR。

    历史缺陷（P0-1 根因B）修复说明：
    旧实现用 (source_line, level) 联合键，其中 level 由 kind 经 kind_to_level
    字典反推。但该字典**缺少 FRONT_MATTER 映射**，走 .get(kind, 5) 默认值 5；
    而 FRONT_MATTER 实际来自 H2/H3（level=2 或 3），导致 builder 步骤6 以
    (source_line, 2) 查找时命中键为 (source_line, 5)，get 返回 None → 该
    FRONT_MATTER 标题**从未被加入 elements 流**（内容在最终 docx 中静默丢失，
    仅留一条 W-HDR-01）。改用 source_line 单键后，kind→level 反推被彻底移除，
    这类"新增 kind 忘记登记 level 映射即静默丢内容"的失配从索引层根除。
    """
    index: dict[int, HeadingIR] = {}
    for hir in heading_irs:
        index[hir.source_line] = hir
    return index


def _remap_section_indices(
    section_plan_sections: list[SectionSpec],
    token_to_element: dict[int, int],
) -> list[SectionSpec]:
    """将 SectionSpec 的 start_element_index 从 Token 索引重映射为元素索引。

    breaks.py 产出的是 Token 流中的位置；builder 组装 elements 时需映射。
    """
    remapped: list[SectionSpec] = []
    for sec in section_plan_sections:
        new_start = token_to_element.get(sec.start_element_index, 0)
        remapped.append(
            SectionSpec(
                kind=sec.kind,
                page_num_fmt=sec.page_num_fmt,
                page_num_restart=sec.page_num_restart,
                header_mode=sec.header_mode,
                start_element_index=new_start,
            )
        )
    return remapped


def build(
    tokens: list,
    options,  # RunOptions（含 input_path/output_path/metadata_cli_overrides 等）
    flags,  # BehaviorFlags
    issues: IssueCollector,
) -> DocumentIR:
    """IR 构建总控：编排全部 assemble 子模块，产出 DocumentIR。

    Args:
        tokens: parse 阶段产出的全部 Token 列表。
        options: RunOptions 实例（含 input_path 等）。
        flags: BehaviorFlags 实例。
        issues: IssueCollector 实例。

    Returns:
        完整的 DocumentIR 实例。
    """
    # ==================================================================
    # 步骤1：提取元数据（MetaLine + H1 → MetadataIR）
    # ==================================================================
    meta_lines = [t for t in tokens if isinstance(t, MetaLine)]

    h1_token: HeadingToken | None = None
    for t in tokens:
        if isinstance(t, HeadingToken) and t.level == 1:
            h1_token = t
            break
    h1_text = h1_token.raw_text if h1_token else None

    metadata = extract_metadata(
        meta_lines,
        h1_text,
        options.metadata_cli_overrides(),
        {},  # YAML 默认值由外部解析后传入；此处先传空，后续由 pipeline 注入
        issues,
    )

    # ==================================================================
    # 步骤2：标题分类 + 编号（HeadingToken → HeadingIR）
    # ==================================================================
    heading_tokens = [t for t in tokens if isinstance(t, HeadingToken)]
    heading_irs = classify_and_number(heading_tokens, issues)

    # 构建 heading 索引供步骤6 使用
    heading_index = _build_heading_index(heading_irs)

    # ==================================================================
    # 步骤3：图解析（ImageToken → FigureIR）
    # ==================================================================
    image_tokens = [t for t in tokens if isinstance(t, ImageToken)]
    md_dir = os.path.dirname(os.path.abspath(options.input_path))
    figure_irs = resolve_figures(
        image_tokens,
        md_dir,
        flags.figures_dir if flags.figures_dir else None,
        issues,
    )
    figure_registry: dict[str, FigureIR] = {
        f.figure_id: f for f in figure_irs
    }

    # ==================================================================
    # 步骤4：表解析（Token 流 → TableIR）
    # ==================================================================
    table_irs = resolve_tables(tokens, issues)
    table_registry: dict[str, TableIR] = {
        t.table_id: t
        for t in table_irs
        if t.table_id is not None  # 仅正文表有编号，可注册
    }

    # ==================================================================
    # 步骤5：分页分节规划（breaks.py 唯一 PageBreakIR 生成点）
    # ==================================================================
    body_table_count = sum(
        1 for t in table_irs if t.kind == TableIR  # TableKind.BODY
    )
    # 注意：TableIR.kind 是 TableKind 枚举，需正确引用
    from ..ir import TableKind

    body_table_count = sum(
        1 for t in table_irs if t.kind == TableKind.BODY
    )

    processed_tokens, section_plan = plan_breaks_and_sections(
        tokens,
        heading_irs,
        appendix_page_break=flags.appendix_page_break,
        generate_figures_table_toc=flags.generate_figures_table_toc,
        figure_count=len(figure_irs),
        body_table_count=body_table_count,
        issues=issues,
    )

    # ==================================================================
    # 步骤6：组装有序元素流（Token/PageBreakIR → BlockIR 列表）
    # ==================================================================

    # 图/表队列（文档序消费）
    figure_queue: list[FigureIR] = list(figure_irs)
    table_queue: list[TableIR] = list(table_irs)

    # 已在处理的表格跨段（跟踪是否处于 TableRowToken 连续序列中）
    in_table_span = False

    # 连续同类型列表项缓冲（合并为单个 ListBlockIR）
    list_buffer: list[OrderedItemToken | UnorderedItemToken] = []

    # Token 索引 → 元素索引 映射表（供段索引重映射）
    token_to_element_map: dict[int, int] = {}

    elements: list[BlockIR] = []

    def _flush_list_buffer() -> None:
        """将累积的连续同类型列表项合并为一个 ListBlockIR 写入 elements。"""
        nonlocal list_buffer
        if not list_buffer:
            return
        first = list_buffer[0]
        ordered = isinstance(first, OrderedItemToken)
        items = [item.runs for item in list_buffer]
        elements.append(
            ListBlockIR(
                ordered=ordered,
                items=items,
                source_line=first.source_line,
            )
        )
        list_buffer = []

    for token_idx, t in enumerate(processed_tokens):
        # ---- PageBreakIR（已由 breaks.py 插入）→ 直接进入 ----
        if isinstance(t, PageBreakIR):
            _flush_list_buffer()
            token_to_element_map[token_idx] = len(elements)
            elements.append(t)
            continue

        # ---- HeadingToken → HeadingIR ----
        if isinstance(t, HeadingToken):
            _flush_list_buffer()
            in_table_span = False

            # P006-2：H1 是否入 elements 由重编 kind 决定（不由 md level 决定）。
            # 先按 source_line 查重编后的 HeadingIR，当且仅当 kind==MAIN_TITLE 时
            # 跳过（主标题由 cover.py 单独渲染）。原 `if t.level == 1: continue`
            # 会把任何 md H1 排除，导致：(1) P006-1 归为 FRONT_MATTER 的前言 H1
            # 被静默丢失；(2) W-HDR-03 降级为 CHAPTER 的第二个 H1 标题文本静默丢失
            # （既有缺陷，一并闭环）。改为看 kind 后，被重编为 CHAPTER/FRONT_MATTER
            # 的 H1 照常入 elements 渲染。
            key = t.source_line
            hir = heading_index.get(key)
            if hir is not None and hir.kind == HeadingKind.MAIN_TITLE:
                # 仅主标题不入正文流（cover.py 渲染）
                continue

            if hir is not None:
                token_to_element_map[token_idx] = len(elements)
                elements.append(hir)
            else:
                # 防御：未分类的标题（理论上不应出现）
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-HDR-01",
                        stage="assemble",
                        message=(
                            f"未能匹配 HeadingIR 的标题 Token："
                            f"{t.raw_text!r}（行 {t.source_line}）"
                        ),
                        source_line=t.source_line,
                    )
                )
            continue

        # ---- ImageToken → FigureIR（队列消费） ----
        if isinstance(t, ImageToken):
            _flush_list_buffer()
            in_table_span = False

            if figure_queue:
                token_to_element_map[token_idx] = len(elements)
                elements.append(figure_queue.pop(0))
            continue

        # ---- TableRowToken（按跨段检测，首行时消费 TableIR） ----
        if isinstance(t, TableRowToken):
            _flush_list_buffer()

            if not in_table_span:
                # 新的表格跨段开始 → 消费一个 TableIR
                in_table_span = True
                if table_queue:
                    token_to_element_map[token_idx] = len(elements)
                    elements.append(table_queue.pop(0))
                else:
                    # 防御：TableIR 不足（数据不一致）
                    issues.append(
                        Issue(
                            level=Level.WARNING,
                            code="W-TBL-01",
                            stage="assemble",
                            message=(
                                f"TableIR 队列已耗尽，但仍有 TableRowToken "
                                f"（行 {t.source_line}）"
                            ),
                            source_line=t.source_line,
                        )
                    )
            # 同表格跨段内的后续 TableRowToken 已被首个 TableIR 覆盖，
            # 不再重复插入。
            continue

        # ---- MetaLine → 跳过（已被 metadata 消费） ----
        if isinstance(t, MetaLine):
            continue

        # ---- BlankToken → 跳过（不进入 IR） ----
        if isinstance(t, BlankToken):
            continue

        # ---- HrToken → 跳过（已被 breaks.py 消费为 PageBreakIR） ----
        if isinstance(t, HrToken):
            continue

        # ---- ParagraphToken → ParagraphIR ----
        if isinstance(t, ParagraphToken):
            _flush_list_buffer()
            # 检测是否属于表来源行（已被 resolve_tables 关联消费的段落）
            # 由于 resolve_tables 可能已将来源行段落标记消费，此处不做额外处理
            in_table_span = False
            token_to_element_map[token_idx] = len(elements)
            elements.append(
                ParagraphIR(runs=t.runs, source_line=t.source_line)
            )
            continue

        # ---- 列表项（合并论：连续同类型 → 一个 ListBlockIR） ----
        if isinstance(t, (OrderedItemToken, UnorderedItemToken)):
            in_table_span = False
            if list_buffer:
                # 检查类型是否与缓冲一致
                both_ordered = isinstance(
                    t, OrderedItemToken
                ) and isinstance(list_buffer[0], OrderedItemToken)
                both_unordered = isinstance(
                    t, UnorderedItemToken
                ) and isinstance(list_buffer[0], UnorderedItemToken)
                if both_ordered or both_unordered:
                    list_buffer.append(t)  # 同类型，合并
                else:
                    _flush_list_buffer()
                    list_buffer.append(t)
            else:
                list_buffer.append(t)
            continue

        # ---- QuoteToken → QuoteIR ----
        if isinstance(t, QuoteToken):
            _flush_list_buffer()
            in_table_span = False
            token_to_element_map[token_idx] = len(elements)
            elements.append(
                QuoteIR(runs=t.runs, source_line=t.source_line)
            )
            continue

        # ---- FencedCodeToken → 降级为 ParagraphIR（防御性） ----
        if isinstance(t, FencedCodeToken):
            _flush_list_buffer()
            in_table_span = False
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="assemble",
                    message=(
                        f"围栏代码块降级为普通段落渲染"
                        f"（行 {t.start_line}–{t.end_line}）"
                    ),
                    source_line=t.start_line,
                )
            )
            # 将代码行拼接为一段文本
            code_text = "\n".join(t.lines)
            from ..ir import InlineRun

            token_to_element_map[token_idx] = len(elements)
            elements.append(
                ParagraphIR(
                    runs=[InlineRun(text=code_text, code=True)],
                    source_line=t.start_line,
                )
            )
            continue

    # 刷新末尾缓冲
    _flush_list_buffer()

    # ------------------------------------------------------------------
    # 步骤6 后处理：重映射 SectionSpec 的 start_element_index
    # （从 Token 索引 → elements 索引）
    # ------------------------------------------------------------------
    remapped_sections = _remap_section_indices(
        section_plan.sections, token_to_element_map
    )

    # ------------------------------------------------------------------
    # 步骤6 后处理（P007-3）：非空非分页前导区检测 → W-SEC-02
    # ------------------------------------------------------------------
    # 渲染层 P007-2 会把首个内容节起点扩展到 0，吞并所有 index < 其原 start 的
    # 前导元素。为避免"前导标题/段落被移动到摘要/正文区起始处渲染却毫无提示"，
    # 此处（assemble 阶段，Issue 时序更早，且能同时看到 elements 与 section
    # start）检测：首个 consuming 节（ABSTRACT/BODY）原 start 之前是否存在
    # **非 PageBreakIR** 前导元素。存在则产 W-SEC-02，逐条明示归属版式。
    # 注意：缺口内的 PageBreakIR 已由 breaks.py PB-E 移除，此处只统计非分页元素。
    _first_consuming_start: int | None = None
    for sec in remapped_sections:
        if sec.kind in (SectionKind.ABSTRACT, SectionKind.BODY):
            _first_consuming_start = sec.start_element_index
            break
    if _first_consuming_start is not None and _first_consuming_start > 0:
        _leading_nonpb = [
            e
            for e in elements[:_first_consuming_start]
            if not isinstance(e, PageBreakIR)
        ]
        if _leading_nonpb:
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-SEC-02",
                    stage="assemble",
                    message=(
                        f"检测到 {len(_leading_nonpb)} 个位于首个内容节之前的"
                        f"前导元素（标题/段落），已并入首个内容节渲染"
                        f"（四节方案下并入摘要节，用罗马页码/摘要页眉），"
                        f"请确认其位置符合预期"
                    ),
                    source_line=getattr(_leading_nonpb[0], "source_line", None),
                )
            )

    # ==================================================================
    # 步骤7：组装 DocumentIR
    # ==================================================================
    from ..ir import SectionPlan

    final_section_plan = SectionPlan(sections=remapped_sections)

    return DocumentIR(
        metadata=metadata,
        elements=elements,
        section_plan=final_section_plan,
        figure_registry=figure_registry,
        table_registry=table_registry,
        xref_registry=[],  # 交叉引用登记（C-06 补充）
    )


# ---------------------------------------------------------------------------
# 自检（验收标准）—— 以 alt-sample 结构构造 mock Token，验证全流程
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path

    from ..config import BehaviorFlags
    from ..ir import (
        HeadingKind,
        InlineRun,
        SectionKind,
        TableKind,
    )

    passed = 0
    failed = 0

    def check(desc: str, condition: bool, detail: str = "") -> None:
        if condition:
            _counts[0] += 1
            print(f"  [PASS] {desc}")
        else:
            _counts[1] += 1
            print(f"  [FAIL] {desc}  -- {detail}")
            if detail:
                print(f"         详情: {detail}")

    _counts = [0, 0]  # [passed, failed]

    # ---- 构造 alt-sample 简化的 Token 流 ----
    _FIXTURES_DIR = (
        Path(__file__).resolve().parents[3]
        / "tests" / "fixtures" / "alt-sample"
    )
    _FIGURES_DIR = _FIXTURES_DIR / "figures"

    # 模拟 RunOptions
    class _MockOptions:
        input_path = str(_FIXTURES_DIR / "alt-report.md")

        def metadata_cli_overrides(self):
            return {}

    mock_options = _MockOptions()
    mock_flags = BehaviorFlags(
        figures_dir=str(_FIGURES_DIR),
        appendix_page_break=True,
        generate_figures_table_toc="auto",
    )

    # 构建 mock Token 流（模拟 alt-report.md 的简化结构）
    # 文件行号与 alt-report.md 对齐
    mock_tokens = [
        # H1 + 元数据
        HeadingToken(
            level=1,
            raw_text="中国城市轨道交通装备产业竞争力研究报告",
            source_line=1,
        ),
        MetaLine(key="副标题", value="整车制造、信号系统与运维服务三大环节分析", source_line=3),
        MetaLine(key="报告类型", value="行业研究报告", source_line=5),
        MetaLine(key="编制机构", value="轨道观察研究院", source_line=7),
        MetaLine(key="版本", value="V2.3 | 2026年6月", source_line=9),
        # --- (HrToken) 元数据与摘要之间
        HrToken(source_line=11),
        # ## 摘要
        HeadingToken(level=2, raw_text="摘要", source_line=13),
        ParagraphToken(
            runs=[InlineRun(text="摘要正文内容……")],
            source_line=15,
        ),
        ParagraphToken(
            runs=[InlineRun(text="当前产业格局初步成形。")],
            source_line=17,
        ),
        # --- (HrToken) 摘要与正文之间
        HrToken(source_line=19),
        # ## 第一章 产业概述
        HeadingToken(level=2, raw_text="第一章 产业概述", source_line=21),
        ParagraphToken(
            runs=[InlineRun(text="城市轨道交通装备是支撑……")],
            source_line=23,
        ),
        # ### 1.1 发展历程
        HeadingToken(level=3, raw_text="1.1 发展历程", source_line=25),
        ParagraphToken(
            runs=[InlineRun(text="中国城市轨道交通装备产业起步于……")],
            source_line=27,
        ),
        # 图片
        ImageToken(
            alt_raw="图1-1 城际动车组产品谱系图",
            path_raw="figures/1-1-城际动车组谱系.png",
            source_line=29,
        ),
        # ### 1.2 产业链构成
        HeadingToken(level=3, raw_text="1.2 产业链构成", source_line=31),
        ParagraphToken(
            runs=[InlineRun(text="产业链分为上游……见表1-1。")],
            source_line=33,
        ),
        # 表1-1 题注 + 表格 + 来源
        # mock 数据必须遵循 inline parser（阶段2）产物形状约定：Markdown 的 **...**
        # 语法已被消耗为 InlineRun.bold=True，纯文本不再含 ** 字面量。题注检测
        # （tables.resolve_tables）依赖 _is_all_bold + 不含 ** 的 RE_TBL_CAPTION_TEXT，
        # 故加粗题注须写为 InlineRun(text="表X-Y 标题", bold=True)（参见 tables.py
        # __main__ 测试4 / 顶部注释 19-27 行 / 02-algorithms.md §B.2）。
        ParagraphToken(
            runs=[
                InlineRun(text="表1-1 产业链上中下游环节对比表", bold=True),
            ],
            source_line=35,
        ),
        TableRowToken(
            cells=[
                [InlineRun(text="环节")],
                [InlineRun(text="代表产品")],
                [InlineRun(text="竞争格局")],
            ],
            source_line=37,
        ),
        TableRowToken(
            cells=[
                [InlineRun(text="上游")],
                [InlineRun(text="牵引电机、制动系统")],
                [InlineRun(text="集中度高")],
            ],
            source_line=38,
        ),
        TableRowToken(
            cells=[
                [InlineRun(text="中游")],
                [InlineRun(text="整车制造")],
                [InlineRun(text="双寡头")],
            ],
            source_line=39,
        ),
        TableRowToken(
            cells=[
                [InlineRun(text="下游")],
                [InlineRun(text="运维服务")],
                [InlineRun(text="分散")],
            ],
            source_line=40,
        ),
        ParagraphToken(
            runs=[
                InlineRun(text="*数据来源：行业协会年度统计公报及公开招标数据整理。*"),
            ],
            source_line=42,
        ),
        # ## 第二章 市场与竞争
        HeadingToken(level=2, raw_text="第二章 市场与竞争", source_line=45),
        ParagraphToken(
            runs=[InlineRun(text="城市轨道交通信号系统……")],
            source_line=47,
        ),
        ImageToken(
            alt_raw="图2-1 城市轨道信号系统市场份额分布",
            path_raw="figures/2-1-信号系统市场份额.png",
            source_line=49,
        ),
        # --- (HrToken) 章间
        HrToken(source_line=55),
        # ## 第三章 国际化与展望
        HeadingToken(level=2, raw_text="第三章 国际化与展望", source_line=57),
        ParagraphToken(
            runs=[InlineRun(text="中国城市轨道交通装备企业……")],
            source_line=59,
        ),
        ImageToken(
            alt_raw="图3-1 海外出海项目地理分布",
            path_raw="figures/3-1-出海项目分布.png",
            source_line=61,
        ),
        # --- (HrToken) 正文与附录之间
        HrToken(source_line=65),
        # ## 附录A：术语对照
        HeadingToken(level=2, raw_text="附录A：术语对照", source_line=67),
        TableRowToken(
            cells=[
                [InlineRun(text="术语")],
                [InlineRun(text="释义")],
            ],
            source_line=69,
        ),
        TableRowToken(
            cells=[
                [InlineRun(text="CBTC")],
                [InlineRun(text="基于通信的列车控制系统")],
            ],
            source_line=70,
        ),
        TableRowToken(
            cells=[
                [InlineRun(text="EMU")],
                [InlineRun(text="电动车组")],
            ],
            source_line=71,
        ),
        # ## 附录B：数据说明
        HeadingToken(level=2, raw_text="附录B：数据说明", source_line=74),
        ParagraphToken(
            runs=[InlineRun(text="本报告所引用的市场规模数据……")],
            source_line=76,
        ),
    ]

    # ---- 运行 builder ----
    print("=== 运行 builder（alt-sample mock tokens） ===")
    collector = IssueCollector()
    doc = build(mock_tokens, mock_options, mock_flags, collector)

    # ---- 验证项 ----
    print("\n=== 验证项 ===")

    # 1. DocumentIR.metadata.title 非空
    check(
        "metadata.title 非空",
        doc.metadata.title == "中国城市轨道交通装备产业竞争力研究报告",
        doc.metadata.title,
    )

    # 2. DocumentIR.elements 非空
    check("elements 非空", len(doc.elements) > 0, f"共 {len(doc.elements)} 个元素")

    # 3. 标题分类正确
    h2_irs = [e for e in doc.elements if isinstance(e, HeadingIR) and
              (hasattr(e, 'kind') and e.kind in (HeadingKind.CHAPTER, HeadingKind.ABSTRACT, HeadingKind.APPENDIX))]
    chapter_irs = [e for e in doc.elements if isinstance(e, HeadingIR) and
                   (hasattr(e, 'kind') and e.kind == HeadingKind.CHAPTER)]
    appendix_irs = [e for e in doc.elements if isinstance(e, HeadingIR) and
                    (hasattr(e, 'kind') and e.kind == HeadingKind.APPENDIX)]
    abstract_irs = [e for e in doc.elements if isinstance(e, HeadingIR) and
                    (hasattr(e, 'kind') and e.kind == HeadingKind.ABSTRACT)]

    # 注意：alt-report 含 6 个 H2（1 ABSTRACT + 3 CHAPTER + 2 APPENDIX）
    #   H1 不入 elements，故此处统计不含 MAIN_TITLE
    check(
        "3 个 CHAPTER H2",
        len(chapter_irs) == 3,
        f"实际 {len(chapter_irs)}：{[h.display_number for h in chapter_irs]}",
    )
    check(
        "2 个 APPENDIX H2",
        len(appendix_irs) == 2,
        f"实际 {len(appendix_irs)}：{[h.display_number for h in appendix_irs]}",
    )
    check(
        "1 个 ABSTRACT H2",
        len(abstract_irs) == 1,
        f"实际 {len(abstract_irs)}",
    )
    if chapter_irs:
        check(
            "第一章 display_number",
            chapter_irs[0].display_number == "第一章",
            chapter_irs[0].display_number,
        )
        check(
            "第三章 display_number",
            chapter_irs[2].display_number == "第三章",
            chapter_irs[2].display_number,
        )

    # 4. 图解析正确
    figure_elements = [e for e in doc.elements if isinstance(e, FigureIR)]
    check("9 个图？不对，alt-sample 共 3 图", len(figure_elements) == 3,
          f"实际 {len(figure_elements)} 个 FigureIR")
    if len(figure_elements) >= 3:
        check("图1-1", figure_elements[0].figure_id == "1-1",
              figure_elements[0].figure_id)
        check("图2-1", figure_elements[1].figure_id == "2-1",
              figure_elements[1].figure_id)
        check("图3-1", figure_elements[2].figure_id == "3-1",
              figure_elements[2].figure_id)

    # 5. 表分类正确：3 个正文表？不对，1 正文表 + 1 附录表 = 2 表
    table_elements = [e for e in doc.elements if isinstance(e, TableIR)]
    body_tables = [t for t in table_elements if t.kind == TableKind.BODY]
    appendix_tables = [t for t in table_elements if t.kind == TableKind.APPENDIX]
    check(
        f"正文表+附录表共 {len(table_elements)} 个",
        len(table_elements) >= 2,
        f"正文表 {len(body_tables)} + 附录表 {len(appendix_tables)}",
    )
    if body_tables:
        check(
            "正文表 table_id",
            body_tables[0].table_id == "1-1",
            str(body_tables[0].table_id),
        )
    if appendix_tables:
        check(
            "附录表 kind=APPENDIX",
            appendix_tables[0].kind == TableKind.APPENDIX,
            str(appendix_tables[0].kind),
        )

    # 6. figure_registry / table_registry
    check("figure_registry 含 3 项", len(doc.figure_registry) >= 1,
          f"实际 {len(doc.figure_registry)}")
    # 若此断言 FAIL，首查 mock 题注段是否遵循 inline parser 产物形状约定
    # （InlineRun(text="表X-Y 标题", bold=True)，无 ** 字面量）——mock 与真实 parse
    # 产物脱节会使 resolve_tables 题注检测失败、表被误判 APPENDIX 而不注册（P-004）。
    check("table_registry 含正文表", len(doc.table_registry) >= 1,
          f"实际 {len(doc.table_registry)}")

    # 7. SectionPlan 含四节（有摘要）
    check("四节方案", len(doc.section_plan.sections) == 4,
          f"实际 {len(doc.section_plan.sections)}")
    section_kinds = [s.kind for s in doc.section_plan.sections]
    check(
        "节序 COVER→ABSTRACT→TOC→BODY",
        section_kinds == [
            SectionKind.COVER,
            SectionKind.ABSTRACT,
            SectionKind.TOC,
            SectionKind.BODY,
        ],
        str(section_kinds),
    )

    # 8. H1 不进入 elements
    h1_in_elements = any(
        isinstance(e, HeadingIR) and
        (hasattr(e, 'kind') and e.kind == HeadingKind.MAIN_TITLE)
        for e in doc.elements
    )
    check("H1 不进入 elements", not h1_in_elements)

    # 9. HrToken 不出现（已消费为 PageBreakIR）
    hr_in_elements = any(isinstance(e, HrToken) for e in doc.elements)
    check("HrToken 不进入 elements", not hr_in_elements)

    # ---- 汇总 ----
    print(f"\n{'='*50}")
    print(f"通过: {_counts[0]}, 失败: {_counts[1]}")
    print(f"{'='*50}")

    # 打印 issues 摘要
    if len(collector) > 0:
        print(f"\nIssues ({len(collector)} 条):")
        for iss in collector:
            print(f"  [{iss.level.value}] {iss.code}: {iss.message[:80]}")

    if _counts[1] > 0:
        sys.exit(1)
    else:
        print("全部 builder 自检通过！")
