"""段落与引用块渲染模块（C-07a 配套）。

将 ParagraphIR / QuoteIR 渲染为 Word 段落，支持行内格式（粗体、斜体、
行内代码、上标、超链接）。

本模块由 render/document.py（C-07c）调用 —— document 遍历 DocumentIR.elements，
对遇到的每个 ParagraphIR / QuoteIR 元素委托给本模块渲染。

引用块渲染（render_quote）也位于本模块，但 document.py 当前从 "special"
子模块导入 render_quote —— 两个入口签名保持一致，未来可统一分派路径。
"""
from __future__ import annotations

from ..config import INLINE_CODE_ASCII_FONT
from ..ir import InlineRun, ParagraphIR, QuoteIR
from .oxml_helpers import add_hyperlink


# ---------------------------------------------------------------------------
# 内部辅助：将 InlineRun 列表渲染为段落中的多个 Run
# ---------------------------------------------------------------------------


def _add_runs_to_paragraph(p, runs: list[InlineRun]) -> None:
    """将 InlineRun 列表逐个渲染到段落的 Run 序列中。

    对每个 InlineRun：
    - 若含 ``link_url``，通过 oxml_helpers.add_hyperlink 创建可点击超链接 run
    - 否则创建普通 run，按 InlineRun 的格式开关设置字体属性

    中文字体由段落样式控制，本函数不在 run 级额外设置 eastAsia 字体。

    Args:
        p: python-docx Paragraph 对象
        runs: 该段落的 InlineRun 列表（来自 ParagraphIR.runs 或 QuoteIR.runs）
    """
    for irun in runs:
        if irun.link_url:
            # 超链接：委托给 oxml_helpers，生成蓝色下划线可点击文本
            add_hyperlink(p, irun.link_url, irun.text)
        else:
            run = p.add_run(irun.text)
            if irun.bold:
                run.font.bold = True
            if irun.italic:
                run.font.italic = True
            if irun.code:
                # 行内代码：西文字体切换为 Consolas（等宽），中文维持样式默认
                run.font.name = INLINE_CODE_ASCII_FONT
            if irun.superscript:
                run.font.superscript = True


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def render_paragraph(doc, token: ParagraphIR, styles: dict) -> None:
    """渲染普通正文段落。

    段落应用 "Body Text" 样式（首行缩进 2 字符、1.5 倍行距、两端对齐），
    行内格式（粗体/斜体/代码/上标/超链接）通过 _add_runs_to_paragraph 逐 run 设置。

    Args:
        doc: python-docx Document 对象
        token: 段落中间表示（ParagraphIR，含 runs: list[InlineRun]）
        styles: 样式名→样式对象字典（render/styles.py register_styles() 产出）
    """
    p = doc.add_paragraph()
    style = styles.get("Body Text")
    if style is not None:
        p.style = style
    else:
        p.style = doc.styles["Body Text"]
    _add_runs_to_paragraph(p, token.runs)


def render_quote(doc, token: QuoteIR, styles: dict) -> None:
    """渲染引用块段落。

    段落应用 "Quote" 样式（10.5pt 斜体、左缩进 1cm、左侧 1pt #BFBFBF 竖线边框），
    行内格式处理同 render_paragraph。

    Args:
        doc: python-docx Document 对象
        token: 引用块中间表示（QuoteIR，含 runs: list[InlineRun]）
        styles: 样式名→样式对象字典（render/styles.py register_styles() 产出）
    """
    p = doc.add_paragraph()
    style = styles.get("Quote")
    if style is not None:
        p.style = style
    else:
        p.style = doc.styles["Quote"]
    _add_runs_to_paragraph(p, token.runs)
