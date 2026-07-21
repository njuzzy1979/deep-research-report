"""阶段1：规则表驱动的文本清理。

设计依据：02-algorithms.md §D.1/D.2/D.5。

本模块是 pipeline 的第二个阶段，负责：
  - 围栏代码块识别与保护（``` 配对区间内跳过所有规则）
  - 行级删除规则（R-03 div/span、R-04 占位符、R-05 印刷页数、
    R-09强① 密级元数据、R-09强② 独立密级、R-10 全文完）
  - 行内改写规则（R-06a 红队标记、R-06b 修正标记、R-07 列表图引用前缀、
    R-09强③ 行内密级片段）
  - 纯检测规则（R-03 行内 HTML 残留、R-09弱 密级弱信号、R-11 文末斜体段）

设计原则：
  1. 只删除/替换文本，不插入结构性标记
  2. 整行锚定优先：删行类规则必须 ^...$ 整行匹配
  3. 代码上下文保护：围栏内跳过一切规则；行内规则跳过 `...` 定界内
  4. 删除三分级：确定性残留→自动删；疑似残留→warn-and-keep
  5. 全动作台账：每次删除/剥离记录一条 I-CLN-05
"""
from __future__ import annotations

import re

from ..iotools import write_text
from ..issues import Issue, IssueCollector, Level

# ---------------------------------------------------------------------------
# 正则规则表（02-algorithms.md §D.2）
# ---------------------------------------------------------------------------

# R-03：整行 div/span 标签残留
_RX_HTML_DIV_SPAN = re.compile(
    r"^\s*</?div[^>]*>\s*$|^\s*</?span[^>]*>\s*$"
)

# R-03：行内其他 HTML 标签样残留（纯检测，不删）
_RX_HTML_OTHER = re.compile(r"<[a-zA-Z/][^>]*>")

# R-04：图表占位符
_RX_PLACEHOLDER = re.compile(r"^\s*\*{0,2}图表占位\*{0,2}[：:].*$")

# R-05：印刷页数建议
_RX_PRINTHINT = re.compile(r"^\s*[（(][^（()）]*建议印刷页数[：:]\s*\d+\s*页[）)]\s*$")

# R-06a：红队过程标记（含前导空白）
_RX_REDTEAM = re.compile(r"\s*\[红队\s*R\d{1,4}[^\[\]]*\]")

# R-06b：修正标记（含前导空白）
_RX_CORRECTION = re.compile(r"\s*\[已修正[：:][^\[\]]*\]")

# R-07：列表形式图引用前缀
_RX_LIST_FIG = re.compile(
    r"^(\s*[-*+]\s+)(?=图\d{1,2}-\d{1,2}(?:[：:]|[ 　]))"
)

# R-09强①：元数据密级字段（**密级**：xxx）
_RX_SECRECY_META = re.compile(r"^\*\*密级\*\*\s*[：:].*$")

# R-09强②：整行独立密级（绝密/机密/秘密）
_RX_SECRECY_LINE = re.compile(
    r"^\s*[（(【\[]?\s*(?:绝密|机密|秘密)\s*[】\])）]?\s*$"
)

# R-09强③：行内密级字段片段
_RX_SECRECY_INLINE = re.compile(r"密级\s*[：:]\s*\S{1,12}")

# R-09弱：密级弱信号关键词（纯检测，不改文本）
_SECRECY_WEAK_WORDS = re.compile(
    r"绝密|机密|内部资料|内部参考|限内部使用|仅供内部|密级"
)

# R-10："全文完"
_RX_FULL_END = re.compile(r"^\s*[（(]?\s*全文完\s*[)）]?\s*$")


# ---------------------------------------------------------------------------
# 围栏代码块区间识别
# ---------------------------------------------------------------------------


def _find_fenced_ranges(lines: list[str]) -> list[tuple[int, int]]:
    """扫描全文，找到所有 ``` 配对区间（闭区间 [start, end]）。

    配对规则：从第一个 ``` 开始，依次两两配对。不成对的孤立 ``` 不标记为
    保护区间（该行之后的代码块保护失效，但不会因此把全文后半都当成保护区）。

    Args:
        lines: 所有行（已按 \\n 分割）

    Returns:
        list of (start, end) 闭区间，start/end 均为 0-indexed 行号
    """
    fenced: list[tuple[int, int]] = []
    open_line: int | None = None

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if open_line is None:
                open_line = i
            else:
                fenced.append((open_line, i))
                open_line = None

    return fenced


def _is_in_fenced(
    lines: list[str],
    line_idx: int,
    fenced_ranges: list[tuple[int, int]],
) -> bool:
    """判断行是否在围栏代码块内。

    Args:
        lines: 所有行（仅用于未来扩展，当前实现仅依赖 fenced_ranges）
        line_idx: 待检查的行号（0-indexed）
        fenced_ranges: _find_fenced_ranges 返回的区间列表

    Returns:
        True 如果该行位于某个围栏代码块内部
    """
    _ = lines  # 保留参数供未来扩展
    for start, end in fenced_ranges:
        if start < line_idx < end:
            return True
    return False


# ---------------------------------------------------------------------------
# 行内代码 span 保护
# ---------------------------------------------------------------------------


def _has_inline_code_span(text: str, pos: int) -> bool:
    """判断 pos 位置是否在行内代码 span `...` 内部。

    从行首扫描到 pos，每遇到一个反引号切换 in_code 状态。
    若 pos 到达时 in_code 为 True，说明该位置处于配对反引号内部。

    Args:
        text: 单行文本
        pos: 待检查的字符位置（0-indexed）

    Returns:
        True 如果 pos 在行内代码 span 内部
    """
    in_code = False
    i = 0
    while i < pos:
        if text[i] == "`":
            in_code = not in_code
        i += 1
    return in_code


# ---------------------------------------------------------------------------
# CJK 接缝修复（M2 接缝规则）
# ---------------------------------------------------------------------------


def _is_cjk_or_punct(ch: str) -> bool:
    """判断字符是否为 CJK 统一汉字或 CJK 标点。

    覆盖范围：
      - CJK Unified Ideographs: U+4E00–U+9FFF
      - CJK Extended A: U+3400–U+4DBF
      - CJK Symbols/Punctuation: U+3000–U+303F
      - Halfwidth/Fullwidth Forms: U+FF00–U+FFEF
      - General Punctuation: U+2000–U+206F
    """
    if not ch:
        return False
    cp = ord(ch)
    return (
        (0x4E00 <= cp <= 0x9FFF)
        or (0x3400 <= cp <= 0x4DBF)
        or (0x3000 <= cp <= 0x303F)
        or (0xFF00 <= cp <= 0xFFEF)
        or (0x2000 <= cp <= 0x206F)
    )


def _cjk_seam_repair(text: str, start: int, end: int) -> str:
    """修复删除 text[start:end] 后的接缝。

    根据断点两侧字符类型决定空白处理策略：
      - 两侧均为 CJK/CJK 标点 → 吞并空白（返回 ""）
      - 两侧均为 ASCII 字母数字 → 补 1 个半角空格（返回 " "）
      - 混合（一侧 CJK 一侧 ASCII）→ 保留原状（返回 ""）

    Args:
        text: 原始文本
        start: 删除区间的起始位置
        end: 删除区间的结束位置（可能已扩展以包含尾部空白）

    Returns:
        替换删除区间的字符串（"" 或 " "）
    """
    if start == 0 or end >= len(text):
        return ""
    left_ch = text[start - 1]
    right_ch = text[end] if end < len(text) else ""
    if not right_ch:
        return ""
    left_cjk = _is_cjk_or_punct(left_ch)
    right_cjk = _is_cjk_or_punct(right_ch)
    if left_cjk and right_cjk:
        return ""  # 两侧CJK → 吞空白
    elif (
        (not left_cjk)
        and (not right_cjk)
        and left_ch.isascii()
        and right_ch.isascii()
    ):
        return " "  # 两侧ASCII → 补空格
    else:
        return ""  # 混合 → 保留原状


def _extend_past_whitespace(text: str, pos: int) -> int:
    """从 pos 开始跳过空白字符，返回第一个非空白字符的位置。

    仅跳过半角空格和制表符。
    """
    while pos < len(text) and text[pos] in (" ", "\t"):
        pos += 1
    return pos


# ---------------------------------------------------------------------------
# 行内改写辅助：应用正则删除并修复接缝
# ---------------------------------------------------------------------------


def _apply_inline_deletions(
    line: str,
    pattern: re.Pattern,
    code: str,
    message_prefix: str,
    issues: IssueCollector,
    line_num: int,
) -> str:
    """对单行应用行内正则删除，每次命中记录 Issue 并修复 CJK 接缝。

    从右到左处理所有匹配，确保索引不被前序删除打乱。
    对每一处命中：
      1. 检查是否在行内代码 span 内（是则跳过）
      2. 检查两侧字符类型，若为 CJK-CJK 则扩展 end 越过尾部空白
      3. 调用 _cjk_seam_repair 决定接缝补白
      4. 执行删除 + 接缝替换

    Args:
        line: 当前行文本
        pattern: 匹配待删除片段的正则
        code: Issue 代码（"I-CLN-05" 或 "I-CLN-02"）
        message_prefix: Issue 消息前缀（如 "R-06a 删除红队标记"）
        issues: IssueCollector
        line_num: 当前行号（1-indexed）

    Returns:
        处理后的行文本
    """
    matches = list(pattern.finditer(line))
    for m in reversed(matches):
        start, end = m.start(), m.end()

        # 跳过行内代码 span 内命中
        if _has_inline_code_span(line, start):
            continue

        # CJK-CJK 接缝：扩展 end 越过尾部空白
        ext_end = end
        if start > 0:
            left_ch = line[start - 1]
            trail_pos = _extend_past_whitespace(line, end)
            right_ch = line[trail_pos] if trail_pos < len(line) else ""
            if _is_cjk_or_punct(left_ch) and _is_cjk_or_punct(right_ch):
                ext_end = trail_pos

        # 确定替换字符串
        replacement = _cjk_seam_repair(line, start, ext_end)
        matched_text = line[start:end]

        # 执行删除
        line = line[:start] + replacement + line[ext_end:]

        # 记录台账
        issues.append(
            Issue(
                level=Level.INFO,
                code=code,
                stage="clean",
                message=f"{message_prefix}：{matched_text!r}",
                source_line=line_num,
                element_ref=None,
                suggestion=None,
            )
        )

    return line


# ---------------------------------------------------------------------------
# 阶段1 主函数
# ---------------------------------------------------------------------------


def clean(
    text: str,
    issues: IssueCollector,
    dump_path: str | None = None,
) -> str:
    """阶段1：规则表驱动的文本清理。

    执行顺序（严格按此）：
      1. 识别围栏代码块区间（``` 配对），标记为保护区
      2. 逐行执行行级删除规则（R-03 div/span、R-04、R-05、
         R-09强①、R-09强②、R-10）
      3. 逐行执行行内改写规则（R-06a、R-06b、R-07）
      4. 行内密级删除（R-09强③，放在 R-09弱 之前以避免重复报警）
      5. 逐行执行纯检测规则（R-03 行内HTML、R-09弱）
      6. 全文扫描：R-11 文末孤立斜体段检测

    Args:
        text: 规范化后的完整 Markdown 文本（str，LF 行尾）
        issues: IssueCollector，每条规则命中时记录 Issue
        dump_path: 若非 None，清理后将中间产物写出到此路径

    Returns:
        清理后的文本（str，LF 行尾）
    """
    lines = text.split("\n")
    fenced_ranges = _find_fenced_ranges(lines)
    result_lines: list[str] = []

    for line_idx, line in enumerate(lines):
        line_num = line_idx + 1  # 1-indexed for Issue reporting

        # ================================================================
        # 围栏代码块保护：跳过一切规则
        # ================================================================
        if _is_in_fenced(lines, line_idx, fenced_ranges):
            result_lines.append(line)
            continue

        # ================================================================
        # 步骤2：行级删除规则（命中的行直接丢弃，不进入后续步骤）
        # ================================================================
        deleted = False

        # R-03：整行 div/span 标签残留
        if _RX_HTML_DIV_SPAN.match(line):
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="clean",
                    message=f"R-03 删除HTML标签残留行：{line.strip()!r}",
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )
            deleted = True

        # R-04：图表占位符
        if not deleted and _RX_PLACEHOLDER.match(line):
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="clean",
                    message=f"R-04 删除图表占位符：{line.strip()!r}",
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )
            deleted = True

        # R-05：印刷页数建议
        if not deleted and _RX_PRINTHINT.match(line):
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="clean",
                    message=f"R-05 删除印刷页数建议：{line.strip()!r}",
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )
            deleted = True

        # R-09强①：元数据密级字段（**密级**：xxx）
        if not deleted and _RX_SECRECY_META.match(line):
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-02",
                    stage="clean",
                    message=f"R-09强① 删除密级元数据行：{line.strip()!r}",
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )
            deleted = True

        # R-09强②：整行独立密级（绝密/机密/秘密）
        if not deleted and _RX_SECRECY_LINE.match(line):
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-02",
                    stage="clean",
                    message=f"R-09强② 删除独立密级行：{line.strip()!r}",
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )
            deleted = True

        # R-10：全文完
        if not deleted and _RX_FULL_END.match(line):
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="clean",
                    message=f'R-10 删除"全文完"：{line.strip()!r}',
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )
            deleted = True

        if deleted:
            continue

        # ================================================================
        # 步骤3：行内改写规则（修改当前行文本）
        # ================================================================

        # R-06a：红队过程标记删除（含 M2 接缝规则）
        line = _apply_inline_deletions(
            line,
            _RX_REDTEAM,
            "I-CLN-05",
            "R-06a 删除红队标记",
            issues,
            line_num,
        )

        # R-06b：修正标记删除（含 M2 接缝规则）
        line = _apply_inline_deletions(
            line,
            _RX_CORRECTION,
            "I-CLN-05",
            "R-06b 删除修正标记",
            issues,
            line_num,
        )

        # R-07：列表形式图引用前缀剥离
        m_fig = _RX_LIST_FIG.match(line)
        if m_fig is not None:
            prefix = m_fig.group(1)
            line = line[m_fig.end() :]  # 删除列表前缀，保留图引用内容
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="clean",
                    message=f"R-07 剥离列表图引用前缀：{prefix!r}",
                    source_line=line_num,
                    element_ref=None,
                    suggestion=None,
                )
            )

        # ================================================================
        # 步骤4（前移）：R-09强③ 行内密级片段删除
        #   在 R-09弱 之前执行，避免弱信号对已删除片段重复报警
        # ================================================================
        line = _apply_inline_deletions(
            line,
            _RX_SECRECY_INLINE,
            "I-CLN-02",
            "R-09强③ 删除行内密级片段",
            issues,
            line_num,
        )

        # ================================================================
        # 步骤5：纯检测规则（仅发 Issue，不改文本）
        # ================================================================

        # R-03：行内其他 HTML 标签残留（纯检测）
        if _RX_HTML_OTHER.search(line) and not _RX_HTML_DIV_SPAN.match(line):
            # 跳过行内代码 span 内的命中
            in_code = False
            report_line = False
            for i, ch in enumerate(line):
                if ch == "`":
                    in_code = not in_code
                elif not in_code and _RX_HTML_OTHER.match(line, i):
                    report_line = True
                    break
            if report_line:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-CLN-04",
                        stage="clean",
                        message=f"R-03 行内HTML标签残留（不删除）：{line.strip()!r}",
                        source_line=line_num,
                        element_ref=None,
                        suggestion="请人工确认并移除残留HTML标签",
                    )
                )

        # R-09弱：密级弱信号检测（纯检测，不改文本）
        for m_weak in _SECRECY_WEAK_WORDS.finditer(line):
            # 跳过行内代码 span 内的命中
            if _has_inline_code_span(line, m_weak.start()):
                continue
            # 提取上下文（匹配位置前后各约20字符）
            ctx_start = max(0, m_weak.start() - 20)
            ctx_end = min(len(line), m_weak.end() + 20)
            context = line[ctx_start:ctx_end]
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-CLN-01",
                    stage="clean",
                    message=(
                        f"R-09弱 密级弱信号命中（{m_weak.group()!r}），"
                        f"上下文：...{context}..."
                    ),
                    source_line=line_num,
                    element_ref=None,
                    suggestion="请人工确认是否需要处理",
                    needs_review=True,
                )
            )

        result_lines.append(line)

    # ================================================================
    # 步骤6：R-11 文末孤立斜体段检测（全文扫描）
    # ================================================================
    _check_trailing_italic(result_lines, issues)

    # ================================================================
    # 组装结果
    # ================================================================
    result = "\n".join(result_lines)

    if dump_path is not None:
        write_text(dump_path, result)

    return result


# ---------------------------------------------------------------------------
# R-11 辅助函数
# ---------------------------------------------------------------------------


def _check_trailing_italic(
    result_lines: list[str],
    issues: IssueCollector,
) -> None:
    """R-11：检测文末孤立斜体段。

    规则：从文档末尾向前找，若最后一个 `---`（分页标记）之后存在整行
    斜体段（匹配 `^*.*$` 或 `^_.*_$` 且非空），则报告 W-CLN-03，
    保留渲染不删除。

    Args:
        result_lines: 清理后的所有行
        issues: IssueCollector
    """
    # 从末尾向前找最后一个 --- 行
    last_hr_idx = -1
    for i in range(len(result_lines) - 1, -1, -1):
        if result_lines[i].strip() == "---":
            last_hr_idx = i
            break

    if last_hr_idx < 0:
        return  # 没有分页标记，不适用

    # 收集 --- 之后的所有非空行
    trailing_lines = result_lines[last_hr_idx + 1 :]
    # 去头去尾空白后检查
    non_empty = [ln for ln in trailing_lines if ln.strip()]

    if not non_empty:
        return  # --- 之后没有内容

    # 检查是否为整行斜体段：整行被单层 * 或 _ 包裹
    italic_pattern = re.compile(r"^\*[^*\n]+\*$|^_[^_\n]+_$")
    for ln in non_empty:
        if italic_pattern.match(ln.strip()):
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-CLN-03",
                    stage="clean",
                    message=(
                        f"R-11 文末孤立斜体段疑似过程残留"
                        f"（保留渲染）：{ln.strip()!r}"
                    ),
                    source_line=None,
                    element_ref=None,
                    suggestion="请人工确认该斜体段是否为正文内容",
                    needs_review=True,
                )
            )
            break  # 每文档最多报告一次


# ---------------------------------------------------------------------------
# 自检（模块直接运行时执行）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== clean.py 自检 ===")
    ic = IssueCollector()

    # ---- 测试输入 ----
    test_input = """\
# Test Doc

<div>
</div>
<span>
</span>
some <font color="red">text</font> here

图表占位：此处应插入图X-Y

（建议印刷页数：42页）

正文包含[红队 R001 已改写]标记。还有[已修正：某个错误]。

- 图1-1：这是列表图引用

**密级**：内部
密级：绝密
正文中提到绝密和内部资料等词但不应被删。

全文完"""

    result = clean(test_input, ic)

    # ---- 检查1：div/span 空标签行被删除 ----
    assert "<div>" not in result, "FAIL: <div> 行未被删除"
    assert "</div>" not in result, "FAIL: </div> 行未被删除"
    assert "<span>" not in result, "FAIL: <span> 行未被删除"
    assert "</span>" not in result, "FAIL: </span> 行未被删除"
    # 但 <font> 等其他 HTML 标签残留应触发 W-CLN-04（不删除文本）
    assert "<font" in result, "FAIL: 行内HTML检测不应删文本"
    print("  PASS: R-03 div/span 行删除 + 其他HTML检测")

    # ---- 检查2：占位符行被删除 ----
    assert "图表占位" not in result, "FAIL: 图表占位符行未被删除"
    print("  PASS: R-04 图表占位符删除")

    # ---- 检查3：印刷页数行被删除 ----
    assert "建议印刷页数" not in result, "FAIL: 印刷页数行未被删除"
    print("  PASS: R-05 印刷页数删除")

    # ---- 检查4：红队标记被删除 ----
    assert "[红队" not in result, "FAIL: 红队标记未被删除"
    print("  PASS: R-06a 红队标记删除")

    # ---- 检查5：修正标记被删除 ----
    assert "[已修正" not in result, "FAIL: 修正标记未被删除"
    print("  PASS: R-06b 修正标记删除")

    # ---- 检查6：列表前缀被剥离 ----
    assert "- 图1-1" not in result, "FAIL: 列表前缀未被剥离"
    # 图引用内容本身应保留
    assert "图1-1：这是列表图引用" in result, (
        "FAIL: 图引用内容被错误删除"
    )
    print("  PASS: R-07 列表图引用前缀剥离")

    # ---- 检查7：密级元数据行被删除 ----
    assert "**密级**" not in result, "FAIL: 密级元数据行未被删除"
    print("  PASS: R-09强① 密级元数据行删除")

    # ---- 检查8：独立密级行被删除 ----
    lines_after = result.split("\n")
    secrecy_deleted = all(
        ln.strip() not in ("密级：绝密", "密级:绝密")
        for ln in lines_after
    )
    # 如果密级行被 R-09强① 删了就不在；如果没被 R-09强① 匹配，
    # R-09强② 会匹配"密级：绝密"吗？不会，"密级：绝密"不是独立密级格式
    # 但 R-09强③ 行内规则会删掉"密级：绝密"这个片段
    assert "密级：绝密" not in result, "FAIL: 密级字段未被删除"
    print("  PASS: R-09强③ 行内密级片段删除")

    # ---- 检查9：密级弱信号仅WARNING，不改文本 ----
    assert "绝密" in result, "FAIL: 密级弱信号文本被错误删除"
    assert "内部资料" in result, "FAIL: 内部资料弱信号文本被错误删除"
    print("  PASS: R-09弱 密级弱信号仅检测不改文")

    # ---- 检查10：全文完被删除 ----
    assert "全文完" not in result, "FAIL: 全文完未被删除"
    print("  PASS: R-10 全文完删除")

    # ---- 检查11：Issue 记录数量合理 ----
    assert len(ic.issues) > 0, "FAIL: 未产生任何 Issue"
    print(f"  PASS: 共产生 {len(ic.issues)} 条 Issue")

    # ---- 检查12：CJK 接缝规则 ----
    ic2 = IssueCollector()
    r2 = clean("使用。[红队 R001 已改写] 国家队", ic2)
    assert r2 == "使用。国家队", (
        f"FAIL: CJK接缝预期'使用。国家队'，实际{r2!r}"
    )
    print("  PASS: CJK接缝规则（两侧CJK→吞空白）")

    # ---- 检查13：ASCII 接缝规则 ----
    ic3 = IssueCollector()
    r3 = clean("data[红队 R001 已改写]analysis", ic3)
    assert r3 == "data analysis", (
        f"FAIL: ASCII接缝预期'data analysis'，实际{r3!r}"
    )
    print("  PASS: ASCII接缝规则（两侧ASCII→补空格）")

    # ---- 检查14：混合接缝规则 ----
    ic4 = IssueCollector()
    r4 = clean("中文[红队 R001 已改写]data", ic4)
    assert r4 == "中文data", (
        f"FAIL: 混合接缝预期'中文data'，实际{r4!r}"
    )
    print("  PASS: 混合接缝规则（CJK+ASCII→保留原状）")

    # ---- 检查15：空输入不报错 ----
    ic5 = IssueCollector()
    r5 = clean("", ic5)
    assert r5 == "", f"FAIL: 空输入应返回空串，实际{r5!r}"
    print("  PASS: 空输入不报错")

    # ---- 检查16：围栏代码块内规则不生效 ----
    ic6 = IssueCollector()
    fenced_input = "```\n<div>code</div>\n图表占位：test\n全文完\n```"
    r6 = clean(fenced_input, ic6)
    assert "<div>" in r6, "FAIL: 围栏内 div 被错误删除"
    assert "图表占位" in r6, "FAIL: 围栏内占位符被错误删除"
    assert "全文完" in r6, "FAIL: 围栏内全文完被错误删除"
    print("  PASS: 围栏代码块内规则不生效")

    # ---- 检查17：dump_path 写出中间产物 ----
    import tempfile, os
    ic7 = IssueCollector()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tf:
        tmp_path = tf.name
    try:
        r7 = clean("# Test\n", ic7, dump_path=tmp_path)
        assert os.path.exists(tmp_path), "FAIL: dump_path 未写出文件"
        from ..iotools import read_bytes
        dumped = read_bytes(tmp_path).decode("utf-8")
        assert dumped == "# Test\n", (
            f"FAIL: dump内容不匹配，实际{dumped!r}"
        )
        print("  PASS: dump_path 中间产物写出")
    finally:
        os.unlink(tmp_path)

    print(f"\n=== 全部 17 项自检通过 ===")
