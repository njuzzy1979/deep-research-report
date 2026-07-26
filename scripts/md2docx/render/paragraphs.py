"""段落与引用块渲染模块（C-07a 配套）。

将 ParagraphIR / QuoteIR 渲染为 Word 段落，支持行内格式（粗体、斜体、
行内代码、上标、超链接），及正文交叉引用的 REF 域自动替换（Phase 7a）。

本模块由 render/document.py（C-07c）调用 —— document 遍历 DocumentIR.elements，
对遇到的每个 ParagraphIR / QuoteIR 元素委托给本模块渲染。

引用块渲染（render_quote）也位于本模块，但 document.py 当前从 "special"
子模块导入 render_quote —— 两个入口签名保持一致，未来可统一分派路径。
"""
from __future__ import annotations

import re

from ..config import INLINE_CODE_ASCII_FONT
from ..ir import InlineRun, ParagraphIR, QuoteIR
from .oxml_helpers import add_hyperlink, add_run_segments, make_field

# 正文交叉引用模式：匹配"图X-Y"或"表X-Y"（X/Y = 1-2 位数字）
_RE_XREF = re.compile(r"(图|表)(\d{1,2})-(\d{1,2})")


def _build_ref_map(xref_registry: list) -> dict[str, str]:
    """从 xref_registry 构建 { "图1-1": "fig_1_1", "表2-3": "Tab2_3" } 查找表。
    只收录有书签、非位置性指代的条目。
    """
    ref_map: dict[str, str] = {}
    for xref in xref_registry:
        if xref.bookmark_name and xref.style != "positional":
            ref_map[xref.ref_id] = xref.bookmark_name
    return ref_map


# ---------------------------------------------------------------------------
# 内部辅助：将 InlineRun 列表渲染为段落中的多个 Run
# ---------------------------------------------------------------------------


def _add_runs_to_paragraph(p, runs: list[InlineRun]) -> None:
    """将 InlineRun 列表逐个渲染到段落的 Run 序列中。

    对每个 InlineRun：
    - 若含 ``link_url``，通过 oxml_helpers.add_hyperlink 创建可点击超链接 run
    - 否则通过 oxml_helpers.add_run_segments 按全角双引号拆分为多个 run，
      逐段应用格式（引号字符额外修正字体插槽为宋体，问题20）

    中文字体由段落样式控制，本函数不在 run 级额外设置 eastAsia 字体
    （引号字符除外，见 add_run_segments）。

    Args:
        p: python-docx Paragraph 对象
        runs: 该段落的 InlineRun 列表（来自 ParagraphIR.runs 或 QuoteIR.runs）
    """
    for irun in runs:
        if irun.link_url:
            # 超链接：委托给 oxml_helpers，生成蓝色下划线可点击文本
            add_hyperlink(p, irun.link_url, irun.text)
        else:
            def _apply_format(run, _is_quote, irun=irun):
                if irun.bold:
                    run.font.bold = True
                if irun.italic:
                    run.font.italic = True
                if irun.code:
                    # 行内代码：西文字体切换为 Consolas（等宽），中文维持样式默认
                    run.font.name = INLINE_CODE_ASCII_FONT
                if irun.superscript:
                    run.font.superscript = True

            add_run_segments(p, irun.text, _apply_format)


def _add_runs_with_refs(p, runs: list[InlineRun], ref_map: dict[str, str]) -> None:
    """将 InlineRun 列表渲染到段落，自动为匹配的"图X-Y"/"表X-Y"插入 REF 域。

    对每个 InlineRun 的文本做 _RE_XREF 正则扫描：
    - 匹配且在 ref_map 中有书签 → 插入 REF 域（placeholder_text = ref_text）
    - 匹配但无书签 → 回退为普通静态文本
    - 非匹配文本 → 按原 InlineRun 格式渲染

    Args:
        p: python-docx Paragraph 对象
        runs: InlineRun 列表
        ref_map: { "图1-1": "fig_1_1", ... } 查找表
    """
    for irun in runs:
        if irun.link_url:
            add_hyperlink(p, irun.link_url, irun.text)
            continue

        text = irun.text
        last_end = 0
        for m in _RE_XREF.finditer(text):
            # 匹配之前的文本（正常渲染）
            if m.start() > last_end:
                _emit_formatted_segment(p, text[last_end:m.start()], irun)

            ref_text = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
            bookmark = ref_map.get(ref_text)
            if bookmark:
                # REF 域：连接图表书签，Word 更新域后自动跟随编号
                make_field(
                    p,
                    f"REF {bookmark} \\h",
                    field_type="REF",
                    placeholder_text=ref_text,
                )
            else:
                # 无书签 → 回退静态文本
                _emit_formatted_segment(p, ref_text, irun)

            last_end = m.end()

        # 最后一个匹配之后的剩余文本
        if last_end < len(text):
            _emit_formatted_segment(p, text[last_end:], irun)


def _emit_formatted_segment(p, text: str, irun: InlineRun) -> None:
    """渲染一段文本，复用 InlineRun 的格式属性。"""
    def _apply_format(run, _is_quote, irun=irun):
        if irun.bold:
            run.font.bold = True
        if irun.italic:
            run.font.italic = True
        if irun.code:
            run.font.name = INLINE_CODE_ASCII_FONT
        if irun.superscript:
            run.font.superscript = True

    add_run_segments(p, text, _apply_format)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def render_paragraph(doc, token: ParagraphIR, styles: dict,
                     ref_map: dict[str, str] | None = None) -> None:
    """渲染普通正文段落。

    段落应用 "Body Text" 样式（首行缩进 2 字符、1.5 倍行距、两端对齐）。
    若提供 ref_map，将正文中的"图X-Y"/"表X-Y"静态文本替换为 REF 域
    （Phase 7a：交叉引用动态化）。

    Args:
        doc: python-docx Document 对象
        token: 段落中间表示（ParagraphIR，含 runs: list[InlineRun]）
        styles: 样式名→样式对象字典（render/styles.py register_styles() 产出）
        ref_map: { "图1-1": "fig_1_1", ... } 查找表，None 时不启用 REF 域替换
    """
    p = doc.add_paragraph()
    style = styles.get("Body Text")
    if style is not None:
        p.style = style
    else:
        p.style = doc.styles["Body Text"]
    if ref_map:
        _add_runs_with_refs(p, token.runs, ref_map)
    else:
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
