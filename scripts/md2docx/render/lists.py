"""列表渲染模块（C-07d）：将 ListBlockIR 渲染为 Word 列表段落。

支持无序列表（List Bullet 样式）和有序列表（List Number 样式）。
列表项内容可能包含行内加粗/斜体/代码，需逐 InlineRun 渲染。
"""
from __future__ import annotations

from ..ir import InlineRun, ListBlockIR


def _render_inline_runs(paragraph, item_runs: list[InlineRun]) -> None:
    """将一组 InlineRun 渲染到段落中，处理行内格式（加粗/斜体/代码）。

    Args:
        paragraph: python-docx Paragraph 对象。
        item_runs: 该列表项的行内文本片段列表。
    """
    for irun in item_runs:
        run = paragraph.add_run(irun.text)
        if irun.bold:
            run.font.bold = True
        if irun.italic:
            run.font.italic = True
        if irun.code:
            run.font.name = 'Consolas'


def render_bullet_list(doc, token: ListBlockIR, styles: dict) -> None:
    """渲染无序列表。

    每个列表项为一个段落，使用 List Bullet 样式。
    列表项内容逐 InlineRun 渲染，保留行内加粗/斜体/代码格式。

    Args:
        doc: python-docx Document 对象。
        token: 列表 IR（ListBlockIR），items 为 list[list[InlineRun]]。
        styles: 样式名 → 样式对象映射（build_styles 产出）。
    """
    for item_runs in token.items:
        p = doc.add_paragraph()
        p.style = styles['List Bullet']
        _render_inline_runs(p, item_runs)


def render_numbered_list(doc, token: ListBlockIR, styles: dict) -> None:
    """渲染有序列表。

    每个列表项为一个段落，使用 List Number 样式。
    列表项内容逐 InlineRun 渲染，保留行内加粗/斜体/代码格式。

    Args:
        doc: python-docx Document 对象。
        token: 列表 IR（ListBlockIR），items 为 list[list[InlineRun]]。
        styles: 样式名 → 样式对象映射（build_styles 产出）。
    """
    for item_runs in token.items:
        p = doc.add_paragraph()
        p.style = styles['List Number']
        _render_inline_runs(p, item_runs)
