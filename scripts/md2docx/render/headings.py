"""标题渲染模块（C-07a 配套）：将 HeadingIR 渲染为 Word 命名标题样式段落。

编号文本已由 assemble 层写入 ``HeadingIR.display_number``，本模块只负责：
1. 根据 heading.kind 确定 Word 样式名（Heading 1~5）
2. 拼接 display_number + text 并写入段落

V-08 硬约束：本模块严禁设置 page_break_before —— 所有分页由 PageBreakIR 驱动。
G-02 说明：add_page_break 的调用点仅在 render/document.py 的 _dispatch_element 中。

本模块由 render/document.py（C-07c）调用 —— document 遍历 DocumentIR.elements，
对遇到的每个 HeadingIR 元素委托给本模块的 render_heading() 渲染。
"""
from __future__ import annotations

from ..ir import HeadingIR, HeadingKind


# ---------------------------------------------------------------------------
# HeadingKind → Word 样式级别映射
# ---------------------------------------------------------------------------
# Word 命名样式  Heading 1       Heading 2       Heading 3       Heading 4       Heading 5
# 中文语义       章（24pt 粗体） 节（16pt 粗体） 小节（14pt 粗体）段落小标题     斜体小标题
# display_number 第一章 / 附录A  1.1 / 2.3       1.1.1 / 3.2.1   ""（无编号）    ""（无编号）
#
# MAIN_TITLE 映射到 Heading 1 仅为防御性兜底 —— 封面标题由 cover.py 渲染，
# 正常情况下 MAIN_TITLE 不会出现在正文元素流中（已被 assemble 过滤或重新归类）。
# 若此处收到 MAIN_TITLE，按 Heading 1 样式渲染，display_number 为空时仅输出 text。

_KIND_TO_LEVEL: dict[HeadingKind, int] = {
    HeadingKind.CHAPTER: 1,
    HeadingKind.APPENDIX: 1,
    HeadingKind.MAIN_TITLE: 1,
    HeadingKind.SECTION: 2,
    HeadingKind.ABSTRACT: 2,
    # FRONT_MATTER（前言/导论区的无编号 H2/H3，§C.3 R-FM）：与 ABSTRACT 一致
    # 按 Heading 2 渲染——同属无编号前置件，display_number 恒为空，仅输出 text。
    # 显式登记以杜绝走 .get(kind, 4) 兜底导致的字号偏小/语义漂移。
    HeadingKind.FRONT_MATTER: 2,
    HeadingKind.SUBSECTION: 3,
    HeadingKind.PLAIN: 4,
}


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def render_heading(doc, heading: HeadingIR, styles: dict) -> None:
    """渲染一个标题（H1~H5）。

    编号文本已由 assemble 层写入 ``heading.display_number``，此处只拼接。
    中文字体由样式控制，无需在 run 级单独设置。

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

    # 拼接编号与标题文本
    if heading.display_number:
        display_text = heading.display_number + " " + heading.text
    else:
        display_text = heading.text

    p.add_run(display_text)
