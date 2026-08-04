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
    HeadingKind.SECTION: 2,
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
#
# PLAIN 映射到 Heading 4，该样式未绑定任何 numPr，无需覆盖（自然无编号）。
_NUMPR_OVERRIDE: dict[HeadingKind, tuple[int, int]] = {
    HeadingKind.APPENDIX: (0, _numbering.APPENDIX_NUM_ID),
    HeadingKind.MAIN_TITLE: (0, _numbering.NO_NUMBERING_ID),
}


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def render_heading(doc, heading: HeadingIR, styles: dict) -> None:
    """渲染一个标题（H1~H5）。

    编号由 Word 原生多级列表驱动（Phase 6.2）：CHAPTER/SECTION/SUBSECTION
    三类直接继承 Heading 1/2/3 样式级绑定的默认 numPr；其余复用同一样式但
    不应显示章节编号的 kind（APPENDIX/MAIN_TITLE）在段落级显式覆盖 numPr。
    段落本身只写入纯标题文字。

    Args:
        doc: python-docx Document 对象
        heading: 标题中间表示（来自 assemble/* 产出）
        styles: 样式名→样式对象字典（render/styles.py register_styles() 产出）
    """
    level = _KIND_TO_LEVEL.get(heading.kind, 4)
    style_name = f"Heading {level}"
    style = styles.get(style_name)
    if style is not None:
        p = doc.add_paragraph(style=style)
    else:
        # 防御性降级：样式字典未包含目标样式名时仍尝试按名引用
        p = doc.add_paragraph()
        p.style = doc.styles[style_name]

    # 静态 numPr 覆盖（APPENDIX / MAIN_TITLE）
    override = _NUMPR_OVERRIDE.get(heading.kind)
    if override is not None:
        ilvl, num_id = override
        _numbering.set_heading_numPr(p, ilvl=ilvl, num_id=num_id)

    add_run_segments(p, heading.text)
