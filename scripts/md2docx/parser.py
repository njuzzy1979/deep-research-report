"""
Markdown 解析器 — 将 Markdown 文本解析为 AST 元素列表，并提取图/表/术语/脚注元数据。

从 scripts/markdown_to_docx.py 提取并重构，保留原有解析逻辑，新增图表元数据提取、
特殊元素识别（定义框/案例框/术语标记）、表格来源注释提取、脚注引用提取等功能。

原始来源: markdown_to_docx.py L258-318
"""

import re
from typing import List, Optional, Dict, Union


# ═══════════════════════════════════════════════════════════
# AST 元素类（从 markdown_to_docx.py L258-274 搬移）
# ═══════════════════════════════════════════════════════════

class Heading:
    """标题元素。"""
    def __init__(self, level: int, text: str):
        self.level = level
        self.text = text


class Paragraph:
    """普通段落元素。"""
    def __init__(self, text: str):
        self.text = text


class CodeBlock:
    """代码块元素。"""
    def __init__(self, lang: str, lines: List[str]):
        self.language = lang
        self.lines = lines


class BlockQuote:
    """引用块元素。"""
    def __init__(self, lines: List[str]):
        self.lines = lines


class HorizontalRule:
    """水平分隔线元素。"""
    pass


class EmptyLine:
    """空行元素。"""
    pass


class ListItem:
    """列表项元素。"""
    def __init__(self, text: str, indent: int = 0, ordered: bool = False, num: Optional[int] = None):
        self.text = text
        self.indent_level = indent
        self.ordered = ordered
        self.order_num = num


class TableElement:
    """表格元素（表头行 + 数据行）。"""
    def __init__(self, header: List[str], rows: List[List[str]]):
        self.header = header
        self.rows = rows


class ImageElement:
    """图片元素。"""
    def __init__(self, alt_text: str, url: str):
        self.alt_text = alt_text
        self.url = url


# ── 支持的类型别名 ──
Element = Union[Heading, Paragraph, CodeBlock, BlockQuote, HorizontalRule,
                EmptyLine, ListItem, TableElement, ImageElement]


# ═══════════════════════════════════════════════════════════
# Markdown 解析（从 markdown_to_docx.py L277-318 搬移，逻辑保持一致）
# ═══════════════════════════════════════════════════════════

def parse_markdown(text: str) -> List[Element]:
    """将 Markdown 文本解析为 AST 元素列表。

    支持的元素类型：标题(H1-H4)、段落、代码块、引用块、水平分隔线、
    空行、无序/有序列表、表格、图片。

    参数:
        text: 原始 Markdown 文本。

    返回:
        解析后的元素列表，顺序与原文一致。
    """
    lines = text.split('\n')
    elements: List[Element] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # 空行
        if line.strip() == '':
            elements.append(EmptyLine())
            i += 1
            continue

        # 代码块 ```lang ... ```
        if line.strip().startswith('```'):
            lang = line.strip()[3:].strip()
            clines: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                clines.append(lines[i])
                i += 1
            i += 1
            elements.append(CodeBlock(lang, clines))
            continue

        # 水平分隔线 --- / *** / ___
        if re.match(r'^[-\*_]{3,}\s*$', line.strip()):
            elements.append(HorizontalRule())
            i += 1
            continue

        # 标题 # ~ ####
        hm = re.match(r'^(#{1,4})\s+(.*)', line)
        if hm:
            elements.append(Heading(len(hm.group(1)), hm.group(2).strip()))
            i += 1
            continue

        # 表格（以 | 开头且下一行为分隔行）
        if '|' in line and i + 1 < len(lines) and re.match(r'^[\|\s\-:]+$', lines[i + 1].strip()):
            hdr = [c.strip() for c in line.split('|') if c.strip()]
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                row = [c.strip() for c in lines[i].split('|') if c.strip()]
                if row:
                    rows.append(row)
                i += 1
            elements.append(TableElement(hdr, rows))
            continue

        # 引用块 >
        if line.strip().startswith('>'):
            ql: List[str] = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                ql.append(lines[i].strip()[1:].strip())
                i += 1
            elements.append(BlockQuote(ql))
            continue

        # 无序列表 - / * / +
        if re.match(r'^(\s*)[-*+]\s+', line):
            li: List[ListItem] = []
            while i < len(lines) and re.match(r'^(\s*)[-*+]\s+', lines[i]):
                m = re.match(r'^(\s*)[-*+]\s+(.*)', lines[i])
                li.append(ListItem(m.group(2).strip(), indent=len(m.group(1)) // 2))
                i += 1
            elements.extend(li)
            continue

        # 有序列表 1. / 2. / 3.
        if re.match(r'^(\s*)\d+\.\s+', line):
            li: List[ListItem] = []
            while i < len(lines) and re.match(r'^(\s*)\d+\.\s+', lines[i]):
                m = re.match(r'^(\s*)(\d+)\.\s+(.*)', lines[i])
                li.append(ListItem(
                    m.group(3).strip(),
                    indent=len(m.group(1)) // 2,
                    ordered=True,
                    num=int(m.group(2))
                ))
                i += 1
            elements.extend(li)
            continue

        # 图片 ![alt](url)
        im = re.match(r'^!\[(.*?)\]\((.*?)\)\s*$', line.strip())
        if im:
            elements.append(ImageElement(im.group(1), im.group(2)))
            i += 1
            continue

        # 默认：普通段落
        elements.append(Paragraph(line.strip()))
        i += 1

    return elements


# ═══════════════════════════════════════════════════════════
# 图表元数据提取（新增）
# ═══════════════════════════════════════════════════════════

def extract_figure_meta(alt_text: str, chapter_num: int, fig_seq: int) -> Optional[Dict[str, object]]:
    """从 ImageElement 的 alt_text 中提取图元数据。

    识别 "图X-Y 题注文本" 格式，提取图号、章节号、序号、题注。
    支持全角/半角短横线（- 和 −）。

    参数:
        alt_text: 图片的 alt 文本。
        chapter_num: 当前章节号（备用，当 alt_text 无法解析时使用）。
        fig_seq: 当前图片序号（备用，当 alt_text 无法解析时使用）。

    返回:
        成功时返回 {'id': 图号, 'chapter': 章节号, 'seq': 序号, 'caption': 题注}，
        无法解析时返回 None。

    示例:
        >>> extract_figure_meta("图3-2 市场规模", 3, 2)
        {'id': '3-2', 'chapter': 3, 'seq': 2, 'caption': '市场规模'}
    """
    m = re.match(r'^图(\d+)[-−](\d+)\s*(.*)', alt_text)
    if not m:
        return None
    return {
        'id': f'{m.group(1)}-{m.group(2)}',
        'chapter': int(m.group(1)),
        'seq': int(m.group(2)),
        'caption': m.group(3).strip()
    }


def extract_table_caption(text: str) -> Optional[str]:
    """识别并提取表格题注行。

    匹配格式：**表X-Y 题注文本**（加粗的表题注行）。

    参数:
        text: 待检查的文本行。

    返回:
        提取的题注文本（不含 ** 标记），无法识别时返回 None。

    示例:
        >>> extract_table_caption("**表1-1 概念辨析**")
        '表1-1 概念辨析'
    """
    m = re.match(r'^\*\*(表\d+[-−]\d+\s+.*?)\*\*$', text.strip())
    if m:
        return m.group(1)
    return None


# ═══════════════════════════════════════════════════════════
# 特殊元素识别（P1 — 定义框/案例框/术语标记）
# ═══════════════════════════════════════════════════════════

def is_definition_box(line: str) -> bool:
    """识别 Markdown 定义框开始标记。

    参数:
        line: 待检查的行。

    返回:
        如果以 ::: definition 开头则返回 True。
    """
    return line.strip().startswith('::: definition')


def is_case_box(line: str) -> bool:
    """识别 Markdown 案例框开始标记。

    参数:
        line: 待检查的行。

    返回:
        如果以 ::: case 开头则返回 True。
    """
    return line.strip().startswith('::: case')


def is_box_end(line: str) -> bool:
    """识别 Markdown 自定义容器结束标记。

    参数:
        line: 待检查的行。

    返回:
        如果恰好为 ::: 则返回 True。
    """
    return line.strip() == ':::'


def is_term_marker(text: str) -> bool:
    """识别术语标记语法 [术语]{.term}。

    参数:
        text: 待检查的文本。

    返回:
        如果匹配 [术语]{.term} 格式则返回 True。
    """
    return bool(re.search(r'\[.+?\]\{\.term\}', text))


# ═══════════════════════════════════════════════════════════
# 表格来源注释提取（P1）
# ═══════════════════════════════════════════════════════════

def extract_source_note(text: str) -> Optional[str]:
    """提取斜体数据来源注释。

    匹配格式：*数据来源: ...* 或 *来源: ...* 或 *Source: ...*

    参数:
        text: 待检查的文本行。

    返回:
        提取的来源文本（不含 * 标记），无法识别时返回 None。

    示例:
        >>> extract_source_note("*数据来源: 中国航天科技集团年报 2024*")
        '数据来源: 中国航天科技集团年报 2024'
    """
    m = re.match(
        r'^\*((?:数据来源|来源|Source)\s*[:：]\s*.+?)\*$',
        text.strip()
    )
    if m:
        return m.group(1)
    return None


# ═══════════════════════════════════════════════════════════
# 脚注引用提取（P1）
# ═══════════════════════════════════════════════════════════

def extract_footnote_ref(text: str) -> List[Dict[str, str]]:
    """从文本中提取脚注引用。

    支持两种格式：
    - 内联脚注：^[脚注文本]
    - 引用脚注：[^n]（n 为数字标识）

    参数:
        text: 待检查的文本。

    返回:
        脚注引用列表，每项为 {'type': 'inline'|'ref', 'text': 脚注文本, 'start': 起始位置, 'end': 结束位置}。

    示例:
        >>> extract_footnote_ref("这是正文^[内联脚注]内容")
        [{'type': 'inline', 'text': '内联脚注', 'start': 4, 'end': 11}]
        >>> extract_footnote_ref("参见文献[^1]的论述")
        [{'type': 'ref', 'text': '1', 'start': 4, 'end': 7}]
    """
    refs: List[Dict[str, str]] = []

    # 内联脚注：^[脚注文本]
    for m in re.finditer(r'\^\[([^\]]*)\]', text):
        refs.append({
            'type': 'inline',
            'text': m.group(1),
            'start': str(m.start()),
            'end': str(m.end())
        })

    # 引用脚注：[^n]
    for m in re.finditer(r'\[\^(\d+)\]', text):
        refs.append({
            'type': 'ref',
            'text': m.group(1),
            'start': str(m.start()),
            'end': str(m.end())
        })

    return refs
