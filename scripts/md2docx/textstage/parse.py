"""阶段2：行级块解析状态机 → 扁平 Token 流。

设计依据：01-architecture.md §2.3。

逐行扫描，按优先级匹配块级 Markdown 语法，产出类型闭集的扁平 Token 列表。
核心原则：
  1. 不做语义判断——只识别语法形状，不区分"摘要章/正文章"
  2. 不丢弃任何行——无法识别的行降级为 ParagraphToken + WARNING
  3. 行内解析委托给 inline.py——包含行内内容的 Token 都调用 parse_inline()
  4. 扁平 Token 流——输出是扁平的 list，不是嵌套 AST
  5. Token 类型闭集——只产出 tokens.py 中定义的 11 种类型

解析优先级（高→低）：
  围栏代码块 > 空行 > ATX标题 > 水平分隔线 > 图片行 > 管道表格 >
  无序列表 > 有序列表 > 引用块 > 元数据行 > 普通段落
"""
from __future__ import annotations

import re

from ..issues import Issue, IssueCollector, Level
from .inline import parse_inline
from .tokens import (
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

# ---------------------------------------------------------------------------
# 正则编译（模块级，避免逐行重复编译）
# ---------------------------------------------------------------------------

# ATX 标题：## 摘要 / ### 1.1 背景（可含尾随 #）
_RX_HEADING = re.compile(r'^(#{1,6})\s+(.+?)(?:\s+#+)?$')

# 水平分隔线：--- / *** / ___（与无序列表区分：后面无内容）
_RX_HR = re.compile(r'^(?:---|\*\*\*|___)\s*$')

# 整行图片：![alt](path)（行首到行尾均为图片语法）
_RX_IMAGE = re.compile(r'^!\[([^\]]*)\]\((.+)\)\s*$')

# 通用图片语法模式（用于行内混排检测；注意图片的 ! 前缀使 [text](url)
# 链接检测在 inline.py 中不生效——inline.py 只处理 [text](url) 不含 ! 前缀）
_RX_INLINE_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# 管道表格行：|...|（首尾均有 |）
_RX_TABLE_ROW = re.compile(r'^\|.+\|$')

# 表格分隔行：|---|:---:| 等
_RX_TABLE_SEP = re.compile(r'^\|[\s\-:]+\|(?:[\s\-:]+\|)*$')

# 无序列表项：- / * / + 开头
_RX_UNORDERED = re.compile(r'^(\s*)[-*+]\s+(.+)$')

# 有序列表项：数字. 或 数字．（中文句号）
_RX_ORDERED = re.compile(r'^(\s*)\d+[.．]\s+(.+)$')

# 元数据行：**key**：value（仅 H1 之后、首个 --- 之前）
_RX_META = re.compile(r'^\*\*([^*：:]+)\*\*\s*[：:]\s*(.+)$')

# 图片路径中的可选 title 剥离：(path "title") → 只保留 path
_RX_IMAGE_TITLE = re.compile(r'^(.+?)\s+"[^"]*"$')


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _flush_para(
    buf: list[tuple[str, int]],
    tokens: list,
    issues: IssueCollector,
) -> None:
    """将段落缓冲区刷出为一个 ParagraphToken。

    连续的"非特殊行"在遇到空行或特殊行时合并：各行之间用空格连接
    （与 CommonMark 段落规则一致），然后整体调 parse_inline()。
    """
    if not buf:
        return
    text = ' '.join(t for t, _ in buf)
    lineno = buf[0][1]
    runs = parse_inline(text, lineno, issues)
    tokens.append(ParagraphToken(runs=runs, source_line=lineno))
    buf.clear()


def _parse_table_cells(
    line: str,
    lineno: int,
    issues: IssueCollector,
) -> list[list]:
    """解析管道表格一行的所有 cell。

    剥离首尾 | 后按 | 分割，每个 cell 内文本调 parse_inline()
    （cell 内支持粗体/斜体/代码等行内格式）。
    """
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    cells: list[list] = []
    for cell_raw in s.split('|'):
        cell_text = cell_raw.strip()
        runs = parse_inline(cell_text, lineno, issues)
        cells.append(runs)
    return cells


def _finish_table(
    in_table: bool,
    table_data_rows: int,
    table_start_line: int,
    issues: IssueCollector,
) -> None:
    """结束表格模式：若表格只有分隔行无数据行则产生警告。"""
    if not in_table:
        return
    if table_data_rows == 0:
        issues.append(
            Issue(
                level=Level.WARNING,
                code='W-TBL-01',
                stage='parse',
                message=(
                    f'表格仅有分隔行无数据行'
                    f'（行{table_start_line}起）'
                ),
                source_line=table_start_line,
                suggestion='请确认表格是否完整',
            )
        )


# ---------------------------------------------------------------------------
# 阶段2 主函数
# ---------------------------------------------------------------------------


def parse(text: str, issues: IssueCollector) -> list:
    """阶段2：行级块解析状态机 → 扁平 Token 流。

    逐行扫描 Markdown 文本，按优先级匹配块级语法，产出类型闭集的
    扁平 Token 列表。行内格式解析委托给 inline.parse_inline()。

    Args:
        text: 清理后的 Markdown 文本（str，LF 行尾）
        issues: IssueCollector，用于报告 Warning/Info 级别问题

    Returns:
        list[Token]：Token 类型的扁平列表（Token 联合类型定义在 .tokens 中）
    """
    # 空文本直接返回空列表（''.split('\n') → [''] 会产生一个伪 BlankToken）
    if not text:
        return []

    lines = text.split('\n')
    tokens: list = []

    # ---- 状态变量 ----
    para_buf: list[tuple[str, int]] = []  # 段落缓冲区：(文本, 行号)
    in_fenced: bool = False               # 是否在围栏代码块内
    fenced_lang: str | None = None        # 代码块语言标识
    fenced_lines: list[str] = []          # 代码块内原始行
    fenced_start: int = 0                 # 代码块起始行号
    in_table: bool = False                # 是否在表格模式中
    table_data_rows: int = 0              # 当前表格的数据行计数
    table_start_line: int = 0             # 当前表格起始行号
    seen_h1: bool = False                 # 是否已遇到 H1 标题
    past_first_hr: bool = False           # 是否已越过首个水平分隔线

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        lineno = i + 1
        line = raw_line.lstrip()

        # ================================================================
        # 1. 围栏代码块处理（``` 配对）
        # ================================================================
        if raw_line.lstrip().startswith('```'):
            if not in_fenced:
                # 进入围栏代码块
                _flush_para(para_buf, tokens, issues)
                _finish_table(in_table, table_data_rows, table_start_line, issues)
                in_table = False
                in_fenced = True
                fenced_start = lineno
                lang_str = raw_line.lstrip()[3:].strip()
                fenced_lang = lang_str if lang_str else None
                fenced_lines = []
            else:
                # 退出围栏代码块
                tokens.append(
                    FencedCodeToken(
                        lang=fenced_lang,
                        lines=fenced_lines,
                        start_line=fenced_start,
                        end_line=lineno,
                    )
                )
                in_fenced = False
                fenced_lang = None
                fenced_lines = []
            i += 1
            continue

        if in_fenced:
            # 代码块内：原样收集，不做任何解析
            fenced_lines.append(raw_line)
            i += 1
            continue

        # ================================================================
        # 2. 空行 → BlankToken + 结束表格/段落模式
        # ================================================================
        if line == '':
            _flush_para(para_buf, tokens, issues)
            _finish_table(in_table, table_data_rows, table_start_line, issues)
            in_table = False
            tokens.append(BlankToken(source_line=lineno))
            i += 1
            continue

        # ================================================================
        # 3. ATX 标题（H1-H6）
        # ================================================================
        m_heading = _RX_HEADING.match(line)
        if m_heading:
            _flush_para(para_buf, tokens, issues)
            _finish_table(in_table, table_data_rows, table_start_line, issues)
            in_table = False
            level = len(m_heading.group(1))
            raw_text = m_heading.group(2).strip()
            tokens.append(
                HeadingToken(
                    level=level,
                    raw_text=raw_text,
                    source_line=lineno,
                )
            )
            if level == 1:
                seen_h1 = True
            i += 1
            continue

        # ================================================================
        # 4. 水平分隔线（在无序列表之前检查，避免 --- 被当列表）
        # ================================================================
        if _RX_HR.match(line):
            _flush_para(para_buf, tokens, issues)
            _finish_table(in_table, table_data_rows, table_start_line, issues)
            in_table = False
            tokens.append(HrToken(source_line=lineno))
            # 首个 HR 关闭元数据检测窗口
            if seen_h1 and not past_first_hr:
                past_first_hr = True
            i += 1
            continue

        # ================================================================
        # 5. 整行图片：![alt](path)
        # ================================================================
        m_img = _RX_IMAGE.match(line)
        if m_img:
            _flush_para(para_buf, tokens, issues)
            _finish_table(in_table, table_data_rows, table_start_line, issues)
            in_table = False
            alt_raw = m_img.group(1)
            path_raw = m_img.group(2)
            # 剥离可选 title：(path "title") → 只保留 path
            title_m = _RX_IMAGE_TITLE.match(path_raw)
            if title_m:
                path_raw = title_m.group(1)
            tokens.append(
                ImageToken(
                    alt_raw=alt_raw,
                    path_raw=path_raw,
                    source_line=lineno,
                )
            )
            i += 1
            continue

        # ================================================================
        # 行内混排图片检测（图片语法与其他文字同行，实测 0 处）
        # ================================================================
        if _RX_INLINE_IMAGE.search(line):
            _flush_para(para_buf, tokens, issues)
            _finish_table(in_table, table_data_rows, table_start_line, issues)
            in_table = False
            # 抽出图片为独立 ImageToken + 剩余文本为 ParagraphToken
            parts = _RX_INLINE_IMAGE.split(line)
            # re.split 含两个捕获组时模式：
            #   [text_before, alt1, path1, text_between, alt2, path2, ...]
            remaining: list[str] = []
            j = 0
            while j < len(parts):
                if j % 3 == 0:
                    # 文本片段
                    if parts[j]:
                        remaining.append(parts[j])
                    j += 1
                else:
                    # (alt, path) 对
                    alt = parts[j]
                    path = parts[j + 1] if j + 1 < len(parts) else ''
                    tokens.append(
                        ImageToken(
                            alt_raw=alt,
                            path_raw=path,
                            source_line=lineno,
                        )
                    )
                    j += 2
            remaining_text = ''.join(remaining).strip()
            if remaining_text:
                runs = parse_inline(remaining_text, lineno, issues)
                tokens.append(
                    ParagraphToken(runs=runs, source_line=lineno)
                )
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code='W-IMG-07',
                    stage='parse',
                    message=f'行内混排图片（已抽出为独立块渲染）：行{lineno}',
                    source_line=lineno,
                )
            )
            i += 1
            continue

        # ================================================================
        # 6. 管道表格（多行状态机）
        #    进入：遇到 |...| 行（行首尾均有 |）
        #    分隔行：跳过，不产出 Token
        #    数据行：按 | 分割 cell，每个 cell 调 parse_inline()
        #    退出：遇到空行或非 |...| 行
        # ================================================================
        if _RX_TABLE_ROW.match(line):
            _flush_para(para_buf, tokens, issues)
            if not in_table:
                in_table = True
                table_data_rows = 0
                table_start_line = lineno
            # 分隔行（|---|:---:| 等）：跳过，不产出 Token
            if _RX_TABLE_SEP.match(line):
                i += 1
                continue
            # 数据行
            table_data_rows += 1
            cells = _parse_table_cells(raw_line, lineno, issues)
            tokens.append(
                TableRowToken(cells=cells, source_line=lineno)
            )
            i += 1
            continue

        # 非表格行 → 若之前在表格模式中则退出
        if in_table:
            _finish_table(in_table, table_data_rows, table_start_line, issues)
            in_table = False

        # ================================================================
        # 7. 无序列表项：- / * / + 开头（与 HR 已在上方区分）
        # ================================================================
        m_ul = _RX_UNORDERED.match(line)
        if m_ul:
            _flush_para(para_buf, tokens, issues)
            text = m_ul.group(2)
            runs = parse_inline(text, lineno, issues)
            tokens.append(
                UnorderedItemToken(runs=runs, source_line=lineno)
            )
            i += 1
            continue

        # ================================================================
        # 8. 有序列表项：1. / 2．(中文句号)
        # ================================================================
        m_ol = _RX_ORDERED.match(line)
        if m_ol:
            _flush_para(para_buf, tokens, issues)
            text = m_ol.group(2)
            runs = parse_inline(text, lineno, issues)
            tokens.append(
                OrderedItemToken(runs=runs, source_line=lineno)
            )
            i += 1
            continue

        # ================================================================
        # 9. 引用块：> 文本（防御性支持，连续 > 行合并为一段）
        # ================================================================
        if line.startswith('>'):
            _flush_para(para_buf, tokens, issues)
            quote_lines: list[str] = []
            quote_start = lineno
            while i < len(lines) and lines[i].lstrip().startswith('>'):
                content = lines[i].lstrip()[1:].lstrip()
                quote_lines.append(content)
                i += 1
            quote_text = ' '.join(quote_lines)
            runs = parse_inline(quote_text, quote_start, issues)
            tokens.append(
                QuoteToken(runs=runs, source_line=quote_start)
            )
            continue  # i 已由内层 while 推进到非引用行

        # ================================================================
        # 10. 元数据行：**key**：value
        #     仅当出现在 H1 标题之后、第一个 --- 之前才识别
        # ================================================================
        m_meta = _RX_META.match(line)
        if m_meta and seen_h1 and not past_first_hr:
            _flush_para(para_buf, tokens, issues)
            key = m_meta.group(1).strip()
            value = m_meta.group(2).strip()
            tokens.append(
                MetaLine(key=key, value=value, source_line=lineno)
            )
            i += 1
            continue

        # ================================================================
        # 11. 默认：普通段落文本 → 积累到段落缓冲区
        #     连续的"非特殊行"合并为一个 ParagraphToken，
        #     遇到空行或任何特殊行时刷新缓冲区。
        # ================================================================
        para_buf.append((raw_line, lineno))
        i += 1

    # ================================================================
    # EOF 收尾：刷新所有未完成的缓冲区
    # ================================================================
    _flush_para(para_buf, tokens, issues)
    _finish_table(in_table, table_data_rows, table_start_line, issues)

    # 未闭合的围栏代码块（防御性处理：缺闭合 ``` → 仍产出）
    if in_fenced:
        tokens.append(
            FencedCodeToken(
                lang=fenced_lang,
                lines=fenced_lines,
                start_line=fenced_start,
                end_line=len(lines),
            )
        )

    return tokens


# ---------------------------------------------------------------------------
# 自检（模块直接运行时执行）
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print('=== parse.py 自检 ===')
    ic = IssueCollector()

    # ---- 测试输入（与规格验收标准一致） ----
    test_input = (
        '# 主标题\n'
        '\n'
        '**副标题**：测试副标题\n'
        '\n'
        '---\n'
        '\n'
        '## 第一章 概述\n'
        '\n'
        '这是第一段文字。\n'
        '这是第一段续行。\n'
        '\n'
        '### 1.1 背景\n'
        '\n'
        '- 列表项一\n'
        '- 列表项二\n'
        '\n'
        '1. 有序项一\n'
        '2. 有序项二\n'
        '\n'
        '![图1-1 测试图](figures/test.png)\n'
        '\n'
        '| 列A | 列B |\n'
        '|-----|-----|\n'
        '| 值1 | 值2 |\n'
        '\n'
        '---\n'
        '\n'
        '> 引用文本\n'
    )

    result = parse(test_input, ic)

    # 按类型分类统计
    non_blank = [t for t in result if not isinstance(t, BlankToken)]
    blank_count = sum(1 for t in result if isinstance(t, BlankToken))
    heading_tokens = [t for t in non_blank if isinstance(t, HeadingToken)]
    hr_tokens = [t for t in non_blank if isinstance(t, HrToken)]
    meta_tokens = [t for t in non_blank if isinstance(t, MetaLine)]
    para_tokens = [t for t in non_blank if isinstance(t, ParagraphToken)]
    img_tokens = [t for t in non_blank if isinstance(t, ImageToken)]
    tbl_tokens = [t for t in non_blank if isinstance(t, TableRowToken)]
    ul_tokens = [t for t in non_blank if isinstance(t, UnorderedItemToken)]
    ol_tokens = [t for t in non_blank if isinstance(t, OrderedItemToken)]
    quote_tokens = [t for t in non_blank if isinstance(t, QuoteToken)]

    # ---- 检查1：总 Token 数约 15（不含 BlankToken） ----
    assert 13 <= len(non_blank) <= 17, (
        f'FAIL: 非空白Token数期望约15，实际{len(non_blank)}'
    )
    print(f'  PASS: 非空白Token数={len(non_blank)}，空白Token数={blank_count}')

    # ---- 检查2：H1 → HeadingToken(level=1) ----
    assert len(heading_tokens) >= 1, 'FAIL: 缺少标题 Token'
    h1 = heading_tokens[0]
    assert h1.level == 1, f'FAIL: H1 level期望1，实际{h1.level}'
    assert h1.raw_text == '主标题', f'FAIL: H1文本期望"主标题"，实际{h1.raw_text!r}'
    print(f'  PASS: H1 → HeadingToken(level=1, raw_text={h1.raw_text!r})')

    # ---- 检查3：HrToken ×2（非列表项） ----
    assert len(hr_tokens) == 2, (
        f'FAIL: HrToken期望2个，实际{len(hr_tokens)}个'
    )
    print(f'  PASS: HrToken ×{len(hr_tokens)}（--- 未被误解析为列表项）')

    # ---- 检查4：H2 → HeadingToken(level=2) ----
    h2_list = [t for t in heading_tokens if t.level == 2]
    assert len(h2_list) >= 1, 'FAIL: 缺少 H2 标题'
    assert h2_list[0].raw_text == '第一章 概述', (
        f'FAIL: H2文本期望"第一章 概述"，实际{h2_list[0].raw_text!r}'
    )
    print(f'  PASS: H2 → HeadingToken(level=2, raw_text={h2_list[0].raw_text!r})')

    # ---- 检查5：ImageToken ----
    assert len(img_tokens) == 1, (
        f'FAIL: ImageToken期望1个，实际{len(img_tokens)}个'
    )
    assert img_tokens[0].alt_raw == '图1-1 测试图', (
        f'FAIL: alt期望"图1-1 测试图"，实际{img_tokens[0].alt_raw!r}'
    )
    assert img_tokens[0].path_raw == 'figures/test.png', (
        f'FAIL: path期望"figures/test.png"，实际{img_tokens[0].path_raw!r}'
    )
    print(f'  PASS: ImageToken(alt_raw={img_tokens[0].alt_raw!r}, '
          f'path_raw={img_tokens[0].path_raw!r})')

    # ---- 检查6：TableRowToken ×2（跳过分隔行） ----
    assert len(tbl_tokens) == 2, (
        f'FAIL: TableRowToken期望2个（跳过分隔行），实际{len(tbl_tokens)}个'
    )
    # 第一行：表头
    assert len(tbl_tokens[0].cells) == 2, (
        f'FAIL: 表头列数期望2，实际{len(tbl_tokens[0].cells)}'
    )
    # 验证 cell 内容（已被 parse_inline 解析为 InlineRun）
    header_texts = [
        ''.join(r.text for r in cell) for cell in tbl_tokens[0].cells
    ]
    assert header_texts == ['列A', '列B'], (
        f'FAIL: 表头内容期望["列A", "列B"]，实际{header_texts}'
    )
    data_texts = [
        ''.join(r.text for r in cell) for cell in tbl_tokens[1].cells
    ]
    assert data_texts == ['值1', '值2'], (
        f'FAIL: 数据行内容期望["值1", "值2"]，实际{data_texts}'
    )
    print(f'  PASS: TableRowToken ×{len(tbl_tokens)}（跳过分隔行，cell内联已解析）')

    # ---- 检查7：列表项 ----
    assert len(ul_tokens) == 2, (
        f'FAIL: UnorderedItemToken期望2个，实际{len(ul_tokens)}个'
    )
    assert len(ol_tokens) == 2, (
        f'FAIL: OrderedItemToken期望2个，实际{len(ol_tokens)}个'
    )
    ul_texts = [''.join(r.text for r in t.runs) for t in ul_tokens]
    assert ul_texts == ['列表项一', '列表项二'], (
        f'FAIL: 无序列表内容不匹配，实际{ul_texts}'
    )
    ol_texts = [''.join(r.text for r in t.runs) for t in ol_tokens]
    assert ol_texts == ['有序项一', '有序项二'], (
        f'FAIL: 有序列表内容不匹配，实际{ol_texts}'
    )
    print(f'  PASS: UnorderedItemToken ×{len(ul_tokens)} + '
          f'OrderedItemToken ×{len(ol_tokens)}')

    # ---- 检查8：MetaLine ----
    assert len(meta_tokens) == 1, (
        f'FAIL: MetaLine期望1个，实际{len(meta_tokens)}个'
    )
    assert meta_tokens[0].key == '副标题', (
        f'FAIL: MetaLine key期望"副标题"，实际{meta_tokens[0].key!r}'
    )
    assert meta_tokens[0].value == '测试副标题', (
        f'FAIL: MetaLine value期望"测试副标题"，实际{meta_tokens[0].value!r}'
    )
    print(f'  PASS: MetaLine(key={meta_tokens[0].key!r}, '
          f'value={meta_tokens[0].value!r})')

    # ---- 检查9：QuoteToken ----
    assert len(quote_tokens) == 1, (
        f'FAIL: QuoteToken期望1个，实际{len(quote_tokens)}个'
    )
    quote_text = ''.join(r.text for r in quote_tokens[0].runs)
    assert quote_text == '引用文本', (
        f'FAIL: 引用文本期望"引用文本"，实际{quote_text!r}'
    )
    print(f'  PASS: QuoteToken(runs_text={quote_text!r})')

    # ---- 检查10：段落合并正确（连续非特殊行合并为一个 ParagraphToken） ----
    assert len(para_tokens) == 1, (
        f'FAIL: ParagraphToken期望1个（两行合并），实际{len(para_tokens)}个'
    )
    para_text = ''.join(r.text for r in para_tokens[0].runs)
    assert '第一段文字' in para_text and '第一段续行' in para_text, (
        f'FAIL: 段落合并内容不匹配，实际{para_text!r}'
    )
    print(f'  PASS: 段落合并正确（{para_text!r}）')

    # ---- 检查11：行内格式正确 ----
    ic2 = IssueCollector()
    bold_input = '这是**粗体**文字\n'
    bold_result = parse(bold_input, ic2)
    bold_paras = [t for t in bold_result if isinstance(t, ParagraphToken)]
    assert len(bold_paras) == 1, 'FAIL: 粗体段落未产出'
    bold_runs = bold_paras[0].runs
    # 应至少有 3 个 run：'这是' + 粗体'粗体' + '文字'
    assert len(bold_runs) >= 3, (
        f'FAIL: 粗体段落run数期望≥3，实际{len(bold_runs)}'
    )
    bold_run = [r for r in bold_runs if r.bold]
    assert len(bold_run) >= 1, 'FAIL: 粗体段落中缺少 bold=True 的 run'
    assert bold_run[0].text == '粗体', (
        f'FAIL: 粗体文本期望"粗体"，实际{bold_run[0].text!r}'
    )
    print(f'  PASS: 段落行内格式正确（**粗体** → bold=True）')

    # ---- 检查12：图像路径含 title 时正确剥离 ----
    ic3 = IssueCollector()
    title_img_input = '![图](path/to/img.png "图片标题")\n'
    title_img_result = parse(title_img_input, ic3)
    title_imgs = [t for t in title_img_result if isinstance(t, ImageToken)]
    assert len(title_imgs) == 1, 'FAIL: 含title图片未产出ImageToken'
    assert title_imgs[0].path_raw == 'path/to/img.png', (
        f'FAIL: title剥离后期望"path/to/img.png"，实际{title_imgs[0].path_raw!r}'
    )
    print(f'  PASS: 图像路径 title 剥离（path_raw={title_imgs[0].path_raw!r}）')

    # ---- 检查13：HR 前后的元数据检测窗口正确 ----
    ic4 = IssueCollector()
    meta_window_input = (
        '# 标题\n'
        '**字段1**：值1\n'
        '---\n'
        '**字段2**：值2\n'  # 这个不应被识别为 MetaLine（已过 HR）
    )
    meta_window_result = parse(meta_window_input, ic4)
    meta_tokens2 = [t for t in meta_window_result if isinstance(t, MetaLine)]
    assert len(meta_tokens2) == 1, (
        f'FAIL: HR 后不应识别 MetaLine，期望1个实际{len(meta_tokens2)}个'
    )
    assert meta_tokens2[0].key == '字段1', (
        f'FAIL: 唯一 MetaLine key 期望"字段1"，实际{meta_tokens2[0].key!r}'
    )
    # **字段2**：值2 应降级为 ParagraphToken
    hr_after_paras = [t for t in meta_window_result if isinstance(t, ParagraphToken)]
    para_texts = [''.join(r.text for r in t.runs) for t in hr_after_paras]
    assert any('字段2' in pt for pt in para_texts), (
        f'FAIL: HR 后的 **字段2**：值2 应降级为段落，但未在段落中找到'
    )
    print(f'  PASS: HR 关闭元数据窗口（HR前={meta_tokens2[0].key!r}，HR后降级为段落）')

    # ---- 检查14：围栏代码块内容不解析 ----
    ic5 = IssueCollector()
    fenced_input = (
        '```\n'
        '# 这不是标题\n'
        '- 这不是列表\n'
        '![不是图片](x.png)\n'
        '```\n'
    )
    fenced_result = parse(fenced_input, ic5)
    fenced_tokens = [t for t in fenced_result if isinstance(t, FencedCodeToken)]
    assert len(fenced_tokens) == 1, 'FAIL: 缺少 FencedCodeToken'
    assert len(fenced_tokens[0].lines) == 3, (
        f'FAIL: 围栏代码块行数期望3，实际{len(fenced_tokens[0].lines)}'
    )
    # 验证代码块内的内容没有产生其他 Token
    heading_in_fenced = [t for t in fenced_result if isinstance(t, HeadingToken)]
    assert len(heading_in_fenced) == 0, (
        'FAIL: 围栏内的 # 不应被解析为标题'
    )
    print(f'  PASS: 围栏代码块内容不解析（{len(fenced_tokens[0].lines)}行代码）')

    # ---- 检查15：空输入不报错 ----
    ic6 = IssueCollector()
    empty_result = parse('', ic6)
    assert empty_result == [], (
        f'FAIL: 空输入应返回空列表，实际{empty_result}'
    )
    print(f'  PASS: 空输入不报错')

    # ---- 检查16：行内混排图片检测 (W-IMG-07) ----
    ic7 = IssueCollector()
    inline_img_input = '前面文字 ![内嵌图](path.png) 后面文字\n'
    inline_img_result = parse(inline_img_input, ic7)
    inline_imgs = [t for t in inline_img_result if isinstance(t, ImageToken)]
    assert len(inline_imgs) == 1, 'FAIL: 行内混排图片未抽出 ImageToken'
    assert inline_imgs[0].alt_raw == '内嵌图', (
        f'FAIL: 行内图片alt期望"内嵌图"，实际{inline_imgs[0].alt_raw!r}'
    )
    # 检查 W-IMG-07 Issue
    w_img07 = [iss for iss in ic7.issues if iss.code == 'W-IMG-07']
    assert len(w_img07) == 1, (
        f'FAIL: 行内混排图片应产生 W-IMG-07 警告，实际{len(w_img07)}条'
    )
    # 剩余文字应为 ParagraphToken
    inline_paras = [t for t in inline_img_result if isinstance(t, ParagraphToken)]
    para_all = ''.join(''.join(r.text for r in t.runs) for t in inline_paras)
    assert '前面文字' in para_all and '后面文字' in para_all, (
        f'FAIL: 行内混排剩余文本不完整，实际{para_all!r}'
    )
    print(f'  PASS: 行内混排图片检测（W-IMG-07）')

    print(f'\n=== 全部 16 项自检通过 ===')
