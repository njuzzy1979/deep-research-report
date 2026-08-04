"""标题渲染模块（C-07a 配套）：将 HeadingIR 渲染为 Word 命名标题样式段落。

Phase 6.2 起，编号不再由 assemble 层算好字符串、render 层拼接文本——而是
通过 ``render/numbering.py`` 定义的 Word 原生多级列表（``w:numPr``）驱动，
由 Word 在打开/打印/F9 更新域时自动计算编号值。段落本身只写入
``heading.text`` 纯标题文字，不含任何编号前缀。

``HeadingIR.display_number``（assemble/headings.py 计算）目前仍保留，供
Gate3 的编号连续性校验（字面值比对）使用，但**不再用于渲染**。

V-08 硬约束：本模块严禁设置 page_break_before —— 所有分页由 PageBreakIR 驱动。
G-02 说明：add_page_break 的调用点仅在 render/document.py 的 _dispatch_element 中。

本模块由 render/document.py（C-07c）调用 —— document 遍历 DocumentIR.elements，
对遇到的每个 HeadingIR 元素委托给本模块的 render_heading() 渲染。
"""
from __future__ import annotations

from ..ir import HeadingIR, HeadingKind
from . import numbering as _numbering
from .oxml_helpers import add_run_segments


# ---------------------------------------------------------------------------
# HeadingKind → Word 样式级别映射
# ---------------------------------------------------------------------------
# Word 命名样式  Heading 1       Heading 2       Heading 3       Heading 4       Heading 5
# 中文语义       章（14pt 粗体） 节（14pt 粗体） 小节（14pt 粗体）段落小标题     斜体小标题
# 编号来源       多级列表 ilvl0  多级列表 ilvl1  多级列表 ilvl2  无编号         无编号
#
# MAIN_TITLE 映射到 Heading 1 仅为防御性兜底 —— 封面标题由 cover.py 渲染，
# 正常情况下 MAIN_TITLE 不会出现在正文元素流中（已被 assemble 过滤或重新归类）。

_KIND_TO_LEVEL: dict[HeadingKind, int] = {
    HeadingKind.CHAPTER: 1,
    HeadingKind.APPENDIX: 1,
    HeadingKind.MAIN_TITLE: 1,
    HeadingKind.REFERENCES: 1,  # 报告级组成部分，与 CHAPTER/APPENDIX 同级
    HeadingKind.SECTION: 2,
    HeadingKind.ABSTRACT: 2,
    # FRONT_MATTER（前言/导论区的无编号标题，§C.3 R-FM）：默认 Heading 2，
    # 若 HeadingIR.markdown_level 已设置（来自 assemble 层），render_heading()
    # 会优先使用 markdown_level 作为 Word 标题级别，以保留 TOC 层级关系。
    # 此处登记的值 2 仅作为 markdown_level 缺失时的兜底。
    HeadingKind.FRONT_MATTER: 1,
    HeadingKind.SUBSECTION: 3,
    HeadingKind.PLAIN: 4,
}

# HeadingKind → 段落级 numPr 覆盖表。
#
# render/styles.py 已在样式级（Heading 1/2/3）绑定了章节多级列表的默认
# ilvl/numId（ilvl 与 _KIND_TO_LEVEL 的 1/2/3 一一对应，见 numbering.py）。
# 但同一 Word 样式会被多种 HeadingKind 复用，其中只有 CHAPTER/SECTION/
# SUBSECTION 三类应当使用该默认绑定；其余复用同一样式的 kind 必须在段落级
# 显式覆盖，否则会被样式级的默认编号"污染"：
#   - APPENDIX 复用 Heading 1（与 CHAPTER 同级），须覆盖为独立的附录字母列表
#   - MAIN_TITLE 复用 Heading 1，不应显示章节编号 → 覆盖为关闭编号（numId=0）
#   - REFERENCES 复用 Heading 1（与 CHAPTER 同级），不应显示"第X章"编号，
#     也不像 APPENDIX 那样需要字母编号（参考文献全篇只有一节）→ 覆盖为
#     关闭编号（numId=0），与 MAIN_TITLE 同款处理
#   - ABSTRACT 复用 Heading 2（与 SECTION 同级），不应显示
#     "X.Y" 节编号 → 覆盖为关闭编号（numId=0）
#   - FRONT_MATTER 复用 Heading 2/3/4（取决于 markdown_level），
#     不应显示编号 → 由 render_heading() 动态计算 ilvl 并设置
#     numId=0（不在本表中静态登记）
#
# PLAIN 映射到 Heading 4，该样式未绑定任何 numPr，无需覆盖（自然无编号）。
_NUMPR_OVERRIDE: dict[HeadingKind, tuple[int, int]] = {
    HeadingKind.APPENDIX: (0, _numbering.APPENDIX_NUM_ID),
    HeadingKind.MAIN_TITLE: (0, _numbering.NO_NUMBERING_ID),
    HeadingKind.REFERENCES: (0, _numbering.NO_NUMBERING_ID),
    HeadingKind.ABSTRACT: (1, _numbering.NO_NUMBERING_ID),
    # FRONT_MATTER 不在本表中 —— 其 numPr 由 render_heading() 根据
    # heading.markdown_level 动态计算 ilvl，再统一设置 numId=NO_NUMBERING_ID。
}


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def render_heading(doc, heading: HeadingIR, styles: dict) -> None:
    """渲染一个标题（H1~H5）。

    编号由 Word 原生多级列表驱动（Phase 6.2）：CHAPTER/SECTION/SUBSECTION
    三类直接继承 Heading 1/2/3 样式级绑定的默认 numPr；其余复用同一样式但
    不应显示章节编号的 kind（APPENDIX/MAIN_TITLE/ABSTRACT/FRONT_MATTER）
    在段落级显式覆盖 numPr。段落本身只写入纯标题文字。

    FRONT_MATTER 标题的 Word 级别由其 markdown_level 决定（若 assemble 层
    已设置），以在 TOC 中保留原始文档层级关系；markdown_level 缺失时退回
    _KIND_TO_LEVEL 硬编码值 2（Heading 2）。

    Args:
        doc: python-docx Document 对象
        heading: 标题中间表示（来自 assemble/* 产出）
        styles: 样式名→样式对象字典（render/styles.py register_styles() 产出）
    """
    level = _KIND_TO_LEVEL.get(heading.kind, 4)
    # FRONT_MATTER: 优先使用 markdown_level（保留 TOC 层级关系），
    # 缺失时退回 _KIND_TO_LEVEL 的固定值 2。
    # markdown_level=1（H1 前端件如"# 摘要"）上封顶为 2，
    # 避免 Word Heading 1 吞并后续 Heading 2 形成虚假父子关系。
    if heading.kind == HeadingKind.FRONT_MATTER and heading.markdown_level is not None:
        # 将markdown层级减1映射到Word层级: ##→Heading1, ###→Heading2
        # "前言"等前置件章节在语义上与正文Chapter同级(Heading 1)
        level = max(1, heading.markdown_level - 1)
    style_name = f"Heading {level}"
    style = styles.get(style_name)
    if style is not None:
        p = doc.add_paragraph(style=style)
    else:
        # 防御性降级：样式字典未包含目标样式名时仍尝试按名引用
        p = doc.add_paragraph()
        p.style = doc.styles[style_name]

    # 静态 numPr 覆盖（APPENDIX / MAIN_TITLE / ABSTRACT）
    override = _NUMPR_OVERRIDE.get(heading.kind)
    if override is not None:
        ilvl, num_id = override
        _numbering.set_heading_numPr(p, ilvl=ilvl, num_id=num_id)

    # FRONT_MATTER: 动态关闭编号（ilvl = level - 1，随 markdown_level 变化；
    # markdown_level 缺失时 level 来自 _KIND_TO_LEVEL 兜底值 2 → ilvl=1）
    if heading.kind == HeadingKind.FRONT_MATTER:
        ilvl = level - 1
        _numbering.set_heading_numPr(p, ilvl=ilvl, num_id=_numbering.NO_NUMBERING_ID)

    add_run_segments(p, heading.text)
