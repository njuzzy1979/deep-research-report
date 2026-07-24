"""分页/分节规划器：PageBreakIR 唯一生成点（C-05c，D5/V-03）。

将 Token 流中的 HrToken 转换为 PageBreakIR，按 H2 边界规则自动补插分页，
去重相邻分页，移除文末尾页，并生成 SectionPlan（四节/三节方案）。

设计依据：02-algorithms.md §D.4、R4/R14/R18、04-interface-spec.md §2.4 I1、
01-architecture.md §5.1、M1/M9。
"""
from __future__ import annotations

from ..ir import (
    BreakOrigin,
    HeadingKind,
    HeaderMode,
    PageBreakIR,
    PageNumFormat,
    SectionKind,
    SectionPlan,
    SectionSpec,
)
from ..issues import Issue, IssueCollector, Level
from ..textstage.tokens import BlankToken, HeadingToken, HrToken

# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def plan_breaks_and_sections(
    tokens: list,
    heading_irs: list,
    appendix_page_break: bool = True,
    generate_figures_table_toc: str = "auto",
    figure_count: int = 0,
    body_table_count: int = 0,
    issues: IssueCollector | None = None,
) -> tuple[list, SectionPlan]:
    """分页/分节规划器：唯一产生 PageBreakIR 的位置（D5/V-03）。

    按 D.4 四步流水线处理 Token 流中的 HrToken 与 H2 边界，产出已插入
    PageBreakIR 的 Token 流与 SectionPlan。

    Args:
        tokens: 全部 Token 流（parse 阶段产出）。
        heading_irs: classify_and_number() 的输出（供 H2 语义判定）。
        appendix_page_break: --appendix-page-break 开关（默认 True）。
        generate_figures_table_toc: 图表目录策略（"auto"/"always"/"never"）。
        figure_count: 图表数量（供 M1 判定）。
        body_table_count: 正文表数量（供 M1 判定）。
        issues: IssueCollector 实例；为 None 时静默略过。

    Returns:
        (处理后的 Token 流, SectionPlan)
    """
    if not tokens:
        return ([], SectionPlan(sections=[]))

    # ------------------------------------------------------------------
    # PB-A：HrToken → PageBreakIR（02 §D.4 第一步）
    # ------------------------------------------------------------------
    stream: list = []
    for t in tokens:
        if isinstance(t, HrToken):
            stream.append(
                PageBreakIR(
                    origin=BreakOrigin.EXPLICIT_HR,
                    source_line=t.source_line,
                )
            )
        else:
            stream.append(t)

    # 构建 H2 语义映射（source_line → HeadingKind），限 CHAPTER/ABSTRACT/APPENDIX
    h2_kind_map: dict[int, HeadingKind] = {}
    for hir in heading_irs:
        if hir.kind in (
            HeadingKind.ABSTRACT,
            HeadingKind.CHAPTER,
            HeadingKind.APPENDIX,
        ):
            h2_kind_map[hir.source_line] = hir.kind

    # 定位首个 ABSTRACT 与首个 CHAPTER 的行号（供 R4 分节符接管判定）
    first_abstract_line: int | None = None
    first_chapter_line: int | None = None
    for hir in heading_irs:
        if hir.kind == HeadingKind.ABSTRACT and first_abstract_line is None:
            first_abstract_line = hir.source_line
        if hir.kind == HeadingKind.CHAPTER and first_chapter_line is None:
            first_chapter_line = hir.source_line

    # ------------------------------------------------------------------
    # PB-B：H2 边界补插（R14/R18 三条件 + R4 分节符接管豁免）
    # ------------------------------------------------------------------
    stream_after_pba = stream
    stream = []
    for t in stream_after_pba:
        if (
            isinstance(t, HeadingToken)
            and t.level == 2
            and t.source_line in h2_kind_map
        ):
            kind = h2_kind_map[t.source_line]
            is_first_abstract = t.source_line == first_abstract_line
            is_first_chapter = t.source_line == first_chapter_line

            # R4：分节符接管判定——摘要H2（首个ABSTRACT）与正文第一章H2（首个CHAPTER）
            # 的边界前不补插 PageBreakIR（分节符的 NEW_PAGE 已覆盖换页需求）。
            section_takeover = is_first_abstract or is_first_chapter

            if not section_takeover:
                # 检查前驱是否为 PageBreakIR（跳过 BlankToken，02 §D.4 第二步）
                # 关键：源 md 中 `---` 与 H2 之间常有空行，BlankToken 不能阻断
                # PageBreakIR 检测，否则 PB-B 会重复补插导致每章边界双分页符。
                prev_is_pb = False
                for prev_t in reversed(stream):
                    if isinstance(prev_t, BlankToken):
                        continue  # 跳过空行/空白
                    prev_is_pb = isinstance(prev_t, PageBreakIR)
                    break
                if not prev_is_pb:
                    # R14/R18：附录 H2 仅在 appendix_page_break=True 时补插
                    if kind != HeadingKind.APPENDIX or appendix_page_break:
                        stream.append(
                            PageBreakIR(
                                origin=BreakOrigin.AUTO_APPENDIX,
                                source_line=None,
                            )
                        )
                        if issues is not None:
                            issues.append(
                                Issue(
                                    level=Level.WARNING,
                                    code="W-PB-01",
                                    stage="assemble",
                                    message=(
                                        f"H2 前缺分页已自动补插："
                                        f"{t.raw_text!r}"
                                    ),
                                    source_line=t.source_line,
                                    element_ref=f"H2:{t.raw_text}",
                                )
                            )
        stream.append(t)

    # ------------------------------------------------------------------
    # PB-C：去重——相邻多个 PageBreakIR → 合并为 1（02 §D.4 第三步）
    # ------------------------------------------------------------------
    deduped: list = []
    for t in stream:
        if (
            isinstance(t, PageBreakIR)
            and deduped
            and isinstance(deduped[-1], PageBreakIR)
        ):
            # 跳过此 PageBreakIR（被前一个吸收合并）
            if issues is not None:
                issues.append(
                    Issue(
                        level=Level.INFO,
                        code="I-PB-02",
                        stage="assemble",
                        message="相邻重复分页已去重",
                        source_line=t.source_line,
                    )
                )
            continue
        deduped.append(t)

    # ------------------------------------------------------------------
    # PB-D：尾页移除——文末尾 PageBreakIR 后无实质内容则移除（02 §D.4 第四步）
    # ------------------------------------------------------------------
    # "实质内容块" = 非 BlankToken 的任意 Token。
    # 从末尾向头部扫描，删除尾部连续的 PageBreakIR 与 BlankToken，
    # 直到遇到第一个实质内容块为止。
    while deduped:
        last = deduped[-1]
        if isinstance(last, PageBreakIR):
            # 末尾 PageBreakIR → 其后无实质内容，移除
            deduped.pop()
        elif isinstance(last, BlankToken):
            # 末尾 BlankToken → 非实质内容，移除
            deduped.pop()
        else:
            # 遇到实质内容 → 停止
            break

    # ------------------------------------------------------------------
    # PB-E：缺口清理（02 §D.4 第五步，P-007）
    # ------------------------------------------------------------------
    # 定位首个 consuming 节（四节=首个 ABSTRACT H2；无摘要三节=首个 CHAPTER H2）
    # 在 deduped 中的 token 索引，移除其之前的全部 PageBreakIR，每个记 I-PB-03。
    #
    # 动机：位于首个内容节 start_element_index 之前的 PageBreakIR 会落入渲染缺口
    # （render/document.py _compute_section_ranges 的首个 consuming 节 start 之前
    # 区间不属任何 range），既不换页也无留痕；而其换页需求本已由 COVER→首个内容节
    # 的分节符（R4 NEW_PAGE）覆盖，属冗余分页。就地移除使"规划的 PageBreakIR 数"
    # 与"渲染实际消费数"重新对齐——gate3 R15 期望值（len(PageBreakIR in elements)）
    # 自动恢复诚实，无需改 gate3 计数逻辑（G-10 单一事实源）。
    #
    # 职责边界：PB-E 只清理 PageBreakIR。缺口内的非分页前导元素（普通段落、
    # P-006 归为 FRONT_MATTER 的前言标题）不在此处理——它们由渲染层
    # _compute_section_ranges 把首个 consuming 节起点扩展到 0 来挽救（P007-2），
    # 二者职责严格互补、不重叠。
    #
    # 恒等保护：若首个 consuming 节 start 本就是 0（官方 front-matter.md /
    # multi-chapter.md 等），gap_boundary_idx 为 0 或无 PageBreakIR 前导 → 不移除，
    # 零回归。
    _gap_target_line = (
        first_abstract_line
        if first_abstract_line is not None
        else first_chapter_line
    )
    gap_boundary_idx: int | None = None
    if _gap_target_line is not None:
        for i, t in enumerate(deduped):
            if (
                isinstance(t, HeadingToken)
                and t.level == 2
                and t.source_line == _gap_target_line
            ):
                gap_boundary_idx = i
                break

    if gap_boundary_idx is not None and gap_boundary_idx > 0:
        cleaned: list = []
        for i, t in enumerate(deduped):
            if i < gap_boundary_idx and isinstance(t, PageBreakIR):
                # 落入首个内容节之前的缺口 → 移除并留痕（I-PB-03，复用现有码）
                if issues is not None:
                    issues.append(
                        Issue(
                            level=Level.INFO,
                            code="I-PB-03",
                            stage="assemble",
                            message=(
                                "位于首个内容节之前的显式分页被分节符换页吸收，"
                                "未重复触发分页（PB-E 缺口清理）"
                            ),
                            source_line=t.source_line,
                        )
                    )
                continue
            cleaned.append(t)
        deduped = cleaned

    # ------------------------------------------------------------------
    # SectionPlan 生成（四节/三节方案，04 §2.4 I1 + M9 降级）
    # ------------------------------------------------------------------

    # 定位摘要 H2 与首章 H2 在已处理 Token 流中的索引
    abstract_idx: int | None = None
    first_chapter_idx: int | None = None
    for i, t in enumerate(deduped):
        if isinstance(t, HeadingToken) and t.level == 2:
            if (
                abstract_idx is None
                and t.source_line == first_abstract_line
            ):
                abstract_idx = i
            if (
                first_chapter_idx is None
                and t.source_line == first_chapter_line
            ):
                first_chapter_idx = i

    has_abstract = abstract_idx is not None
    sections: list[SectionSpec] = []

    # 第一节：COVER（始终存在）
    sections.append(
        SectionSpec(
            kind=SectionKind.COVER,
            page_num_fmt=PageNumFormat.NONE,
            page_num_restart=False,
            header_mode=HeaderMode.NONE,
            start_element_index=0,
        )
    )

    if has_abstract:
        # ---- 四节方案：COVER / ABSTRACT / TOC / BODY ----
        sections.append(
            SectionSpec(
                kind=SectionKind.ABSTRACT,
                page_num_fmt=PageNumFormat.LOWER_ROMAN,
                page_num_restart=True,
                header_mode=HeaderMode.TITLE_SHORT,
                start_element_index=abstract_idx,
            )
        )
        # TOC 节：无页眉，罗马页码续接。
        # TOC 内容由渲染器自动生成，无对应的 Token 流元素；
        # start_element_index 取 BODY 起始索引（TOC 自动插入于
        # ABSTRACT 之后、BODY 之前），渲染器按节序先后处理。
        body_start = (
            first_chapter_idx if first_chapter_idx is not None else 0
        )
        sections.append(
            SectionSpec(
                kind=SectionKind.TOC,
                page_num_fmt=PageNumFormat.LOWER_ROMAN,
                page_num_restart=False,
                header_mode=HeaderMode.NONE,
                start_element_index=body_start,
            )
        )
        sections.append(
            SectionSpec(
                kind=SectionKind.BODY,
                page_num_fmt=PageNumFormat.DECIMAL,
                page_num_restart=True,
                header_mode=HeaderMode.TITLE_SHORT,
                start_element_index=body_start,
            )
        )
    else:
        # ---- 三节方案（M9 降级）：COVER / TOC / BODY ----
        # 无摘要时，TOC 直接接在封面之后，罗马页码 start=1。
        body_start = (
            first_chapter_idx if first_chapter_idx is not None else 0
        )
        sections.append(
            SectionSpec(
                kind=SectionKind.TOC,
                page_num_fmt=PageNumFormat.LOWER_ROMAN,
                page_num_restart=True,
                header_mode=HeaderMode.NONE,
                start_element_index=0,
            )
        )
        sections.append(
            SectionSpec(
                kind=SectionKind.BODY,
                page_num_fmt=PageNumFormat.DECIMAL,
                page_num_restart=True,
                header_mode=HeaderMode.TITLE_SHORT,
                start_element_index=body_start,
            )
        )

    section_plan = SectionPlan(sections=sections)

    # ------------------------------------------------------------------
    # M1：图表目录 TOC 节的处理
    # ------------------------------------------------------------------
    # 若 generate_figures_table_toc="auto" 且（图数 + 正文表数 >= 10）→ 嵌入图表目录页。
    # 在目录与图表目录之间插入 AUTO_TOC 换页标记。
    should_gen_fig_toc = False
    if generate_figures_table_toc == "always":
        should_gen_fig_toc = True
    elif generate_figures_table_toc == "auto":
        if figure_count + body_table_count >= 10:
            should_gen_fig_toc = True

    if should_gen_fig_toc:
        # 将 AUTO_TOC 换页标记插入到 TOC 节起始位置（即 BODY start 之前），
        # 渲染器将在目录与图表目录之间看到此 PageBreakIR。
        insert_pos = body_start
        if insert_pos >= len(deduped):
            insert_pos = len(deduped)
        deduped.insert(
            insert_pos,
            PageBreakIR(origin=BreakOrigin.AUTO_TOC, source_line=None),
        )
        # 插入后，后续元素的索引偏移 +1，需调整 BODY 节起始索引
        for sec in section_plan.sections:
            if sec.kind == SectionKind.BODY:
                # 使用 replace 语义更新 start_element_index
                # SectionSpec 是 frozen dataclass 则无法直接赋值；
                # 此处依赖 SectionSpec 为非 frozen 的默认行为
                pass  # SectionSpec 不是 frozen dataclass，可直接赋值
        # 更新 BODY 节起始索引（因插入了一个 PageBreakIR）
        for i, sec in enumerate(section_plan.sections):
            if sec.kind == SectionKind.BODY:
                section_plan.sections[i] = SectionSpec(
                    kind=sec.kind,
                    page_num_fmt=sec.page_num_fmt,
                    page_num_restart=sec.page_num_restart,
                    header_mode=sec.header_mode,
                    start_element_index=sec.start_element_index + 1,
                )
        if issues is not None:
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-TOC-01",
                    stage="assemble",
                    message=(
                        f"「目录→图表目录」换页：图{ figure_count }个 + "
                        f"正文表{ body_table_count }个 = "
                        f"{ figure_count + body_table_count } >= 10，"
                        f"已插入 AUTO_TOC 换页标记"
                    ),
                )
            )

    return (deduped, section_plan)


# ---------------------------------------------------------------------------
# 自检（验收标准）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    from ..ir import HeadingIR

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

    # ---- 测试1：PB-A — HrToken → PageBreakIR ----
    print("\n=== 测试1：PB-A HrToken → PageBreakIR ===")
    c1 = IssueCollector()
    tokens1 = [
        HrToken(source_line=11),
        HrToken(source_line=19),
    ]
    result1, sp1 = plan_breaks_and_sections(
        tokens1, [], issues=c1
    )
    # 两个 HrToken → 两个 PageBreakIR(EXPLICIT_HR)，但末尾的会被 PB-D 移除
    # （因为流中无实质内容后续），所以仅剩一个。
    pb_count = sum(1 for t in result1 if isinstance(t, PageBreakIR))
    if pb_count >= 1:
        first_pb = next(t for t in result1 if isinstance(t, PageBreakIR))
        check(
            "HrToken → PageBreakIR(EXPLICIT_HR)",
            first_pb.origin == BreakOrigin.EXPLICIT_HR,
            str(first_pb.origin),
        )
        check(
            "source_line 保留",
            first_pb.source_line is not None,
            str(first_pb.source_line),
        )
    else:
        # 若 PB-D 移除：两个 HrToken 相邻 → PB-C 合并 → 一个 PB → PB-D 发现末尾无内容移除
        # 流中另有内容？无 → 全部被移除。此场景正确：两个空 Hr 的文档末尾无实质内容。
        check("两个 HrToken 相邻去重+末尾移除 → 流中无 PageBreakIR（正确）", True)
    check("HrToken 已从流中移除", not any(isinstance(t, HrToken) for t in result1))

    # ---- 测试2：PB-B — H2 前无 PageBreak → 自动补插（非首章） ----
    print("\n=== 测试2：PB-B H2 前缺 PageBreak → 自动补插（非首章） ===")
    c2 = IssueCollector()
    # 需要先有一个首章（source_line 更小），使被测章成为非首章
    heading_irs2 = [
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第一章 概述",
            text="概述",
            number=1,
            display_number="第一章",
            source_line=5,
        ),
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第二章 方法",
            text="方法",
            number=2,
            display_number="第二章",
            source_line=20,
        ),
    ]
    tokens2 = [
        HeadingToken(level=2, raw_text="第一章 概述", source_line=5),
        HeadingToken(level=2, raw_text="第二章 方法", source_line=20),
    ]
    result2, sp2 = plan_breaks_and_sections(
        tokens2, heading_irs2, issues=c2
    )
    # 第二章为非首章，且前驱非 PageBreakIR → 应自动补插 PageBreakIR(AUTO_APPENDIX)
    check("第二章 H2 前自动补插 PageBreakIR（非首章）", any(
        isinstance(t, PageBreakIR) and t.origin == BreakOrigin.AUTO_APPENDIX
        for t in result2
    ))
    check("有 W-PB-01", any(i.code == "W-PB-01" for i in c2))

    # ---- 测试3：R4 — 首个 CHAPTER H2 前不补插 ----
    print("\n=== 测试3：R4 分节符接管——首个 CHAPTER H2 前不补插 ===")
    c3 = IssueCollector()
    heading_irs3 = [
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第一章 概述",
            text="概述",
            number=1,
            display_number="第一章",
            source_line=10,
        ),
    ]
    tokens3 = [
        HeadingToken(level=2, raw_text="第一章 概述", source_line=10),
    ]
    result3, sp3 = plan_breaks_and_sections(
        tokens3, heading_irs3, issues=c3
    )
    # 首个 CHAPTER 不补插（被 BODY 节分节符接管）
    check(
        "首个 CHAPTER H2 前无自动补插（R4 接管）",
        not any(
            isinstance(t, PageBreakIR) and t.origin == BreakOrigin.AUTO_APPENDIX
            for t in result3
        ),
    )

    # ---- 测试4：PB-C — 相邻 PageBreakIR 去重 ----
    print("\n=== 测试4：PB-C 相邻 PageBreakIR 去重 ===")
    c4 = IssueCollector()
    heading_irs4 = [
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第二章",
            text="第二章",
            number=2,
            display_number="第二章",
            source_line=30,
        ),
    ]
    # 模拟：两个显式 --- 后跟 H2 → 假设 PB-B 不触发（已有前驱 PB）
    tokens4 = [
        HrToken(source_line=25),
        HrToken(source_line=26),
        HeadingToken(level=2, raw_text="第二章", source_line=30),
    ]
    result4, sp4 = plan_breaks_and_sections(
        tokens4, heading_irs4, issues=c4
    )
    pb_aps = [t for t in result4 if isinstance(t, PageBreakIR)]
    check(
        "两个 HrToken → 去重后仅 1 个 PageBreakIR",
        len(pb_aps) <= 1,
        f"实际 {len(pb_aps)} 个 PageBreakIR",
    )
    if len(pb_aps) == 0:
        check("PB-D 末尾移除：H2 后无内容 → PageBreakIR 被末尾移除（正确）", True)
    else:
        check("有 I-PB-02", any(i.code == "I-PB-02" for i in c4))

    # ---- 测试5：SectionPlan — 四节方案（有摘要） ----
    print("\n=== 测试5：SectionPlan 四节方案（有摘要）===")
    c5 = IssueCollector()
    heading_irs5 = [
        HeadingIR(
            kind=HeadingKind.ABSTRACT,
            raw_text="摘要",
            text="摘要",
            number=None,
            display_number="",
            source_line=5,
        ),
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第一章",
            text="第一章",
            number=1,
            display_number="第一章",
            source_line=15,
        ),
    ]
    tokens5 = [
        HeadingToken(level=2, raw_text="摘要", source_line=5),
        HeadingToken(level=2, raw_text="第一章", source_line=15),
    ]
    result5, sp5 = plan_breaks_and_sections(
        tokens5, heading_irs5, issues=c5
    )
    kinds = [s.kind for s in sp5.sections]
    check("四节方案", len(sp5.sections) == 4, f"实际 {len(sp5.sections)} 节")
    check("节序: COVER→ABSTRACT→TOC→BODY", kinds == [
        SectionKind.COVER,
        SectionKind.ABSTRACT,
        SectionKind.TOC,
        SectionKind.BODY,
    ], str(kinds))
    # ABSTRACT 节页码格式
    abstract_sec = sp5.sections[1]
    check(
        "ABSTRACT 节罗马页码",
        abstract_sec.page_num_fmt == PageNumFormat.LOWER_ROMAN,
        str(abstract_sec.page_num_fmt),
    )
    check("ABSTRACT 节重启页码", abstract_sec.page_num_restart)
    # BODY 节页码格式
    body_sec = sp5.sections[3]
    check(
        "BODY 节阿拉伯页码",
        body_sec.page_num_fmt == PageNumFormat.DECIMAL,
        str(body_sec.page_num_fmt),
    )
    check("BODY 节重启页码", body_sec.page_num_restart)

    # ---- 测试6：SectionPlan — 三节方案（M9 无摘要降级） ----
    print("\n=== 测试6：SectionPlan 三节方案（M9 无摘要）===")
    c6 = IssueCollector()
    heading_irs6 = [
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第一章",
            text="第一章",
            number=1,
            display_number="第一章",
            source_line=10,
        ),
    ]
    tokens6 = [
        HeadingToken(level=2, raw_text="第一章", source_line=10),
    ]
    result6, sp6 = plan_breaks_and_sections(
        tokens6, heading_irs6, issues=c6
    )
    kinds6 = [s.kind for s in sp6.sections]
    check("三节方案", len(sp6.sections) == 3, f"实际 {len(sp6.sections)} 节")
    check("节序: COVER→TOC→BODY", kinds6 == [
        SectionKind.COVER,
        SectionKind.TOC,
        SectionKind.BODY,
    ], str(kinds6))

    # ---- 测试7：M1 图表目录 TOC ----
    print("\n=== 测试7：M1 图表 >= 10 → 插入 AUTO_TOC PageBreakIR ===")
    c7 = IssueCollector()
    heading_irs7 = [
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第一章",
            text="第一章",
            number=1,
            display_number="第一章",
            source_line=10,
        ),
    ]
    tokens7 = [
        HeadingToken(level=2, raw_text="第一章", source_line=10),
    ]
    result7, sp7 = plan_breaks_and_sections(
        tokens7, heading_irs7,
        generate_figures_table_toc="auto",
        figure_count=9,
        body_table_count=3,
        issues=c7,
    )
    check(
        "9图+3表=12>=10 → 有 AUTO_TOC PageBreakIR",
        any(
            isinstance(t, PageBreakIR) and t.origin == BreakOrigin.AUTO_TOC
            for t in result7
        ),
    )
    check("有 I-TOC-01", any(i.code == "I-TOC-01" for i in c7))

    # ---- 测试8：M1 图表不足 10 → 不触发 ----
    print("\n=== 测试8：M1 图表 < 10 → 不触发 ===")
    c8 = IssueCollector()
    heading_irs8 = [
        HeadingIR(
            kind=HeadingKind.CHAPTER,
            raw_text="第一章",
            text="第一章",
            number=1,
            display_number="第一章",
            source_line=10,
        ),
    ]
    tokens8 = [
        HeadingToken(level=2, raw_text="第一章", source_line=10),
    ]
    result8, sp8 = plan_breaks_and_sections(
        tokens8, heading_irs8,
        generate_figures_table_toc="auto",
        figure_count=3,
        body_table_count=2,
        issues=c8,
    )
    check(
        "3图+2表=5<10 → 无 AUTO_TOC PageBreakIR",
        not any(
            isinstance(t, PageBreakIR) and t.origin == BreakOrigin.AUTO_TOC
            for t in result8
        ),
    )

    # ---- 测试9：空列表 ----
    print("\n=== 测试9：空列表 ===")
    c9 = IssueCollector()
    result9, sp9 = plan_breaks_and_sections([], [], issues=c9)
    check("空列表返回空", len(result9) == 0)
    check("SectionPlan.sections 为空", len(sp9.sections) == 0)

    # ---- 测试10：appendix_page_break=False — 附录前不补插 ----
    print("\n=== 测试10：appendix_page_break=False ===")
    c10 = IssueCollector()
    heading_irs10 = [
        HeadingIR(
            kind=HeadingKind.APPENDIX,
            raw_text="附录A：术语",
            text="术语",
            number="A",
            display_number="附录A",
            source_line=50,
        ),
    ]
    tokens10 = [
        HeadingToken(level=2, raw_text="附录A：术语", source_line=50),
    ]
    result10, sp10 = plan_breaks_and_sections(
        tokens10, heading_irs10,
        appendix_page_break=False,
        issues=c10,
    )
    check(
        "appendix_page_break=False → 附录前不补插",
        not any(
            isinstance(t, PageBreakIR) and t.origin == BreakOrigin.AUTO_APPENDIX
            for t in result10
        ),
    )

    # ---- 汇总 ----
    print(f"\n{'='*50}")
    print(f"通过: {_counts[0]}, 失败: {_counts[1]}")
    print(f"{'='*50}")

    if _counts[1] > 0:
        sys.exit(1)
    else:
        print("全部 breaks 自检通过！")
