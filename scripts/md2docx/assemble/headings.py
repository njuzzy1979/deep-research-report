"""标题语义分类、编号剥离与结构化重编（C-05a）。

将文本阶段产出的 HeadingToken 列表，按文档结构语义分类为
HeadingKind 各变体，剥离原始手动编号，重编结构化 display_number，
并对原编号做连续性校验。

设计依据：02-algorithms.md §C（全部正则 N-01~N-07、编号剥离、中文数字转换、
连续性校验均照此规格实现）。
"""
from __future__ import annotations

import re

from ..config import (
    CJK_NUMERAL_LIANG,
    CJK_NUMERALS,
    FRONT_BACK_WORDS,
    M6_H3_SINGLE_LEVEL,
    M6_H4_TWO_LEVEL,
    N_01_CHAPTER_CN,
    N_02_CHAPTER_ARABIC,
    N_03_SUBSECTION,
    N_04_SECTION,
    N_05_CHAPTER_DUNHAO,
    N_06_CHAPTER_CN_DUNHAO,
    N_07_APPENDIX,
)
from ..ir import HeadingIR, HeadingKind, HeadingNumber
from ..issues import Issue, IssueCollector, Level
from ..textstage.tokens import HeadingToken
from .outline_reader import build_structure_manifest, _build_structure_lookup

# ---------------------------------------------------------------------------
# 编译正则（来自 config.py 的单一事实来源）
# ---------------------------------------------------------------------------
_RE_N01 = re.compile(N_01_CHAPTER_CN)
_RE_N02 = re.compile(N_02_CHAPTER_ARABIC)
_RE_N03 = re.compile(N_03_SUBSECTION)
_RE_N04 = re.compile(N_04_SECTION)
_RE_N05 = re.compile(N_05_CHAPTER_DUNHAO)
_RE_N06 = re.compile(N_06_CHAPTER_CN_DUNHAO)
_RE_N07 = re.compile(N_07_APPENDIX)
_RE_M6_H3 = re.compile(M6_H3_SINGLE_LEVEL)
_RE_M6_H4 = re.compile(M6_H4_TWO_LEVEL)

# ---------------------------------------------------------------------------
# 中文数字转换（02 §C.4）
# ---------------------------------------------------------------------------

_DIGIT_MAP: dict[str, int] = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "两": 2,
}
_CN_CHARS = set(_DIGIT_MAP) | {"十", "百"}


def int_to_cn(n: int) -> str:
    """整数 1..999 → 中文数字（02 §C.4 伪代码实现）。

    >>> int_to_cn(1)
    '一'
    >>> int_to_cn(10)
    '十'
    >>> int_to_cn(11)
    '十一'
    >>> int_to_cn(21)
    '二十一'
    >>> int_to_cn(100)
    '一百'
    >>> int_to_cn(101)
    '一百零一'
    """
    if n <= 0 or n > 999:
        return str(n)

    # 数字字符表来自 config.CJK_NUMERALS（单一事实来源，§C.4；出处：02 §C.4）——
    # 取前 10 位即"零..九"，避免在业务模块内重复硬编码数字串。
    digits = CJK_NUMERALS[:10]

    if n == 10:
        return "十"

    if n < 10:
        return digits[n]

    if n < 20:
        return "十" + digits[n - 10]

    if n < 100:
        tens = n // 10
        ones = n % 10
        result = digits[tens] + "十"
        if ones > 0:
            result += digits[ones]
        return result

    # 100-999
    hundreds = n // 100
    remainder = n % 100
    result = digits[hundreds] + "百"
    if remainder == 0:
        return result
    if remainder < 10:
        result += "零" + digits[remainder]
        return result
    tens = remainder // 10
    ones = remainder % 10
    result += digits[tens] + "十"
    if ones > 0:
        result += digits[ones]
    return result


def cn_to_int(s: str) -> int | None:
    """中文数字 → int（02 §C.4 伪代码实现）。

    支持格式：一、十、十一、二十、二十一、一百、一百一十、一百零一 等。
    解析失败返回 None。

    >>> cn_to_int("一")
    1
    >>> cn_to_int("十一")
    11
    >>> cn_to_int("一百一十")
    110
    """
    s = s.strip()
    if not s:
        return None

    # 检查是否全是合法中文数字字符
    for ch in s:
        if ch not in _CN_CHARS:
            return None

    # 纯数字（≤9）
    if s in _DIGIT_MAP:
        return _DIGIT_MAP[s]

    # 十 / 十X
    if "十" in s and "百" not in s:
        parts = s.split("十")
        if s == "十":
            return 10
        if s.startswith("十"):
            # 十X
            ones = _DIGIT_MAP.get(parts[1]) if len(parts) > 1 and parts[1] else None
            if ones is not None:
                return 10 + ones
            return None
        if s.endswith("十"):
            # X十
            tens = _DIGIT_MAP.get(parts[0])
            if tens is not None:
                return tens * 10
            return None
        # X十Y
        if len(parts) == 2:
            tens = _DIGIT_MAP.get(parts[0])
            ones = _DIGIT_MAP.get(parts[1]) if parts[1] else 0
            if tens is not None:
                return tens * 10 + ones
        return None

    # X百Y...
    if "百" in s:
        parts = s.split("百", 1)
        hundreds = _DIGIT_MAP.get(parts[0])
        if hundreds is None:
            return None
        result = hundreds * 100
        rest = parts[1] if len(parts) > 1 else ""
        if not rest:
            return result
        # 零X
        if rest.startswith("零"):
            rest = rest[1:]
            if not rest:
                return result
            ones = _DIGIT_MAP.get(rest)
            if ones is not None:
                return result + ones
            return None
        # Y十Z / Y
        if "十" in rest:
            rparts = rest.split("十")
            tens = _DIGIT_MAP.get(rparts[0]) if rparts[0] else 1
            ones = _DIGIT_MAP.get(rparts[1]) if len(rparts) > 1 and rparts[1] else 0
            return result + tens * 10 + ones
        # 纯个位
        ones = _DIGIT_MAP.get(rest)
        if ones is not None:
            return result + ones
        return None

    return None


# ---------------------------------------------------------------------------
# 标题分类与编号剥离辅助
# ---------------------------------------------------------------------------

def _is_front_back(text: str) -> bool:
    """判断标题文本是否匹配前后置件关键词白名单（02 §F.2 / §C.3 R-FM）。

    两级判定（后者仅在前者失败时启用，保证纯净标题的行为与旧版逐字一致）：

    1. 整体精确匹配（原语义）：剥离首尾空白与尾随全/半角冒号后，
       整串落在 FRONT_BACK_WORDS 白名单内即为前置件。
    2. 复合前置件标题：形如「前言/导论」「绪论、引言」这类以分隔符
       （/ 、 ， 及空白）连接的复合标题——按分隔符切分后，**每一个**
       非空段都必须精确命中白名单，才判为前置件。

    误伤边界（§C.3 R-FM 论证）：采用"全部段命中"而非"任一段命中"，
    且要求段与白名单词**整段相等**（非子串包含）。因此：
      - 「前言/导论」→ ["前言","导论"] 全命中 → True（目标场景）
      - 「研究方法目录结构」→ 无分隔符、整串不在白名单 → False（不因含"目录"二字误判）
      - 「背景/导论对比」→ ["背景","导论对比"] 有段未命中 → False（不因含"导论"误判）
    这样既修复复合前置件标题识别，又不放大对正文章节标题的误伤面。
    """
    clean = text.strip().rstrip("：:").strip()
    # 第1级：整体精确匹配（与旧实现等价，零行为漂移）
    if clean in FRONT_BACK_WORDS:
        return True
    # 第2级：复合前置件标题——分隔符切分后逐段精确匹配，要求全部命中
    segments = [
        seg.strip().rstrip("：:").strip()
        for seg in re.split(r"[/、，,\s]+", clean)
    ]
    segments = [s for s in segments if s]
    if len(segments) >= 2 and all(s in FRONT_BACK_WORDS for s in segments):
        return True
    return False


def _has_explicit_chapter_number(raw_text: str) -> bool:
    """探测 H2 标题是否携带显式章编号（N-01/N-02/N-05/N-06 任一命中）。

    仅做只读探测、不产生 Issue、不改写文本——供前言区（FRONT_MATTER）
    边界判定使用：前言区内一旦出现显式编号章标题，即视为正文开始的
    可靠信号，据此终止前言区（§C.3 R-FM）。
    """
    return bool(
        _RE_N01.match(raw_text)
        or _RE_N02.match(raw_text)
        or _RE_N05.match(raw_text)
        or _RE_N06.match(raw_text)
    )


def _strip_chapter(raw_text: str, source_line: int, issues: IssueCollector) -> tuple[str, int | None]:
    """对 H2 章标题尝试编号剥离（N-01/N-02/N-05/N-06 顺次）。

    Returns:
        (stripped_text, original_number_int | None)
    """
    # N-01：第X章（中文数字）
    m = _RE_N01.match(raw_text)
    if m:
        cn_num = m.group(1).replace(CJK_NUMERAL_LIANG, "二")
        orig = cn_to_int(cn_num)
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-01），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped, orig

    # N-02：第N章（阿拉伯数字）
    m = _RE_N02.match(raw_text)
    if m:
        orig = int(m.group(1))
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-02），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped, orig

    # N-05：N、N. N．（阿拉伯数字+顿号/句点）
    m = _RE_N05.match(raw_text)
    if m:
        orig = int(m.group(1))
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-05），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped, orig

    # N-06：X、X．X.（中文数字+顿号/句点）
    m = _RE_N06.match(raw_text)
    if m:
        cn_num = m.group(1)
        orig = cn_to_int(cn_num)
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-06），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped, orig

    # 无匹配 → 无原始编号
    return raw_text, None


def _strip_appendix(raw_text: str, source_line: int, issues: IssueCollector) -> tuple[str, str | None]:
    """对 H2 附录标题尝试编号剥离（N-07）。

    Returns:
        (stripped_text, original_letter | None)
    """
    m = _RE_N07.match(raw_text)
    if m:
        letter = m.group(1) or ""
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-07），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped, letter.upper() if letter else ""
    return raw_text, None


def _strip_section(raw_text: str, source_line: int, issues: IssueCollector) -> str:
    """对 H3 节标题尝试编号剥离（N-04 + M6_H3 增补规则）。

    Returns:
        stripped_text
    """
    # N-04：N.M 格式（标准 H3 编号）
    m = _RE_N04.match(raw_text)
    if m:
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-04），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped

    # M6_H3_SINGLE_LEVEL：单级数字前缀（如 "3、背景"）
    m = _RE_M6_H3.match(raw_text)
    if m:
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（M6_H3），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped

    return raw_text


def _strip_subsection(raw_text: str, source_line: int, issues: IssueCollector) -> str:
    """对 H4 小节标题尝试编号剥离（N-03 + M6_H4 增补规则）。

    Returns:
        stripped_text
    """
    # N-03：N.M.K 格式（标准 H4 编号）
    m = _RE_N03.match(raw_text)
    if m:
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（N-03），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped

    # M6_H4_TWO_LEVEL：二级前缀（如 "1.2 概述"）
    m = _RE_M6_H4.match(raw_text)
    if m:
        stripped = raw_text[m.end():].lstrip()
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="assemble",
                message=f"剥离标题编号「{m.group().rstrip()}」（M6_H4），"
                f"剥离后标题：{stripped!r}",
                source_line=source_line,
            )
        )
        return stripped

    return raw_text


# ---------------------------------------------------------------------------
# 结构注入（Phase 7a）
# ---------------------------------------------------------------------------


def apply_structure_overlay(
    results: list[HeadingIR],
    structure: dict,
    issues: IssueCollector,
    outline_path: str | None = None,
    lookup: dict | None = None,
) -> list[HeadingIR]:
    """用 outline.md 结构清单覆盖 HeadingIR 的分类和编号。

    工作原理：
    1. 将 structure YAML 展平为 ``{标题文本: (HeadingKind, 编号)}`` 查找表
    2. 遍历 results 中的 HeadingIR，用 ``heading.text`` 精确匹配查找表
    3. 匹配成功 → 用结构清单中的 kind 和 number 覆盖推断值，原有 kind/number
       备份到 result._original_kind / result._original_number（调试用属性名）
    4. 匹配失败（正文有但结构清单无）→ 保留推断值，记录 W-HDR-04
    5. 结构清单中未被正文匹配的条目 → 记录 W-HDR-05

    Args:
        results: classify_and_number() 产出（已完成推断分类和编号）
        structure: outline.md YAML 的 ``structure`` 节点（plain dict）
        issues: IssueCollector 实例
        outline_path: 真实的 outline.md 路径，透传给 build_structure_manifest()
            的台账写入（D3 附带修复）。默认 None 回退旧字面量，兼容既有调用方。
        lookup: 可选的、调用方已算好的 ``_build_structure_lookup()`` 结果。
            传入时直接复用，不再内部重新调用一遍（G1 交叉验证 D5 裁决：一次
            转换中 builder.py 会先算一次 manifest，这里若再算一次 lookup，
            `_build_structure_lookup()` 内部的逐条 stderr 诊断会重复打印）。
            不传时（默认 None）内部自行计算，行为与旧版本一致。

    Returns:
        修改后的 results（原地修改并返回同一列表引用）
    """
    if not isinstance(structure, dict) or not results:
        return results

    if lookup is None:
        # _build_structure_lookup 在 outline_reader.py 中定义
        lookup = _build_structure_lookup(structure, outline_path)

    if not lookup:
        return results

    # 统计
    override_count = 0
    unmatched_headings: list[HeadingIR] = []

    for ir in results:
        key = ir.text.strip()
        if key in lookup:
            expected_kind, expected_number = lookup[key]
            # 覆盖分类和编号
            ir.kind = expected_kind
            ir.number = expected_number
            # 更新 display_number
            ir.display_number = _display_number_for(expected_kind, expected_number)
            override_count += 1
        elif ir.kind in (
            HeadingKind.CHAPTER,
            HeadingKind.SECTION,
            HeadingKind.SUBSECTION,
            HeadingKind.APPENDIX,
        ):
            # 只在正文结构类 heading 未匹配时记录——跳过 MAIN_TITLE/ABSTRACT/
            # FRONT_MATTER/PLAIN（这些不需要结构覆盖）
            unmatched_headings.append(ir)

    # 记录 Issue
    if override_count > 0:
        # D5：复用本函数已持有的 lookup，避免 build_structure_manifest()
        # 内部再次调用 _build_structure_lookup() 重复解析 + 重复打印诊断。
        manifest = build_structure_manifest(structure, outline_path, lookup=lookup)
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-HDR-07",
                stage="assemble",
                message=(
                    f"结构注入模式已启用：{override_count} 个 heading 的分类/编号"
                    f"由 outline.md 结构清单覆盖"
                ),
                element_ref=(
                    f"chapters={manifest['chapter_count']}, "
                    f"sections={manifest['section_count']}, "
                    f"subsections={manifest['subsection_count']}, "
                    f"appendices={manifest['appendix_count']}"
                ),
            )
        )

    for ir in unmatched_headings:
        issues.append(
            Issue(
                level=Level.WARNING,
                code="W-HDR-04",
                stage="assemble",
                message=(
                    f"heading「{ir.text}」（行{ir.source_line}）在 outline.md "
                    f"结构清单中未找到精确匹配，保持原推断分类为 "
                    f"{ir.kind.name}，编号={ir.display_number!r}"
                ),
                source_line=ir.source_line,
                element_ref=f"heading:{ir.text}",
                suggestion="请确认标题文本与 outline.md 中的声明完全一致（含标点、空格）",
            )
        )

    # W-HDR-05：结构清单中声明但正文未出现的条目
    matched_texts = {ir.text.strip() for ir in results}
    for struct_title in lookup:
        if struct_title not in matched_texts:
            _kind, _number = lookup[struct_title]
            kind_name = _kind.name if _kind else "UNKNOWN"
            num_str = str(_number) if _number is not None else "—"
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-HDR-05",
                    stage="assemble",
                    message=(
                        f"outline.md 结构清单声明的 heading「{struct_title}」"
                        f"（类型={kind_name}，编号={num_str}）在正文中缺失"
                    ),
                    suggestion="检查分章写作是否覆盖了该节，或 outline.md 是否需要更新",
                )
            )

    # --------------------------------------------------------------
    # Phase 7b: 重算 SUBSECTION (H4) 三级编号
    # --------------------------------------------------------------
    # overlay 只覆盖了 H2 (CHAPTER) 和 H3 (SECTION) 的 kind/number，
    # H4 (SUBSECTION) 的三级编号在 classify_and_number Pass 2 中
    # 已经固化为 (0, 0, N)（因为推断阶段的 chapter_index/section_index
    # 可能是错误的）。此处基于 overlay 修正后的 CHAPTER/SECTION 编号，
    # 重新计算 SUBSECTION 的 (chapter_no, section_no, subsection_no)。
    current_chapter: int | None = None
    current_section: int | None = None
    subsection_counter = 0

    for ir in results:
        if ir.kind == HeadingKind.CHAPTER:
            current_chapter = ir.number if isinstance(ir.number, int) else None
            current_section = None
            subsection_counter = 0
        elif ir.kind == HeadingKind.SECTION:
            if isinstance(ir.number, tuple) and len(ir.number) == 2:
                current_section = ir.number[1]
            else:
                # fallback: 安全递增（理论上 overlay 后的 SECTION number
                # 一定是 (ch_no, sec_no) 二元组，此处仅防御）
                current_section = (current_section or 0) + 1
            subsection_counter = 0
        elif ir.kind == HeadingKind.SUBSECTION:
            subsection_counter += 1
            if current_chapter is not None and current_section is not None:
                ir.number = (current_chapter, current_section, subsection_counter)
                ir.display_number = (
                    f"{current_chapter}.{current_section}.{subsection_counter}"
                )
        # FRONT_MATTER / ABSTRACT / MAIN_TITLE / APPENDIX / PLAIN 不参与重算

    return results


def _display_number_for(
    kind: HeadingKind, number: HeadingNumber
) -> str:
    """根据 HeadingKind 和编号值生成 display_number 字符串。

    函数体与 classify_and_number() Pass 2 逻辑一致——复用此处以避免重复。
    """
    if kind == HeadingKind.CHAPTER and isinstance(number, int):
        return f"第{int_to_cn(number)}章"
    if kind == HeadingKind.SECTION and isinstance(number, tuple) and len(number) == 2:
        return f"{number[0]}.{number[1]}"
    if kind == HeadingKind.SUBSECTION and isinstance(number, tuple) and len(number) == 3:
        return f"{number[0]}.{number[1]}.{number[2]}"
    if kind == HeadingKind.APPENDIX and isinstance(number, str):
        return f"附录{number}"
    return ""


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def classify_and_number(
    heading_tokens: list[HeadingToken],
    issues: IssueCollector,
) -> list[HeadingIR]:
    """对标题 Token 流执行语义分类、编号剥离与结构化重编。

    Args:
        heading_tokens: Token 流中所有标题 Token（保持文档序）。
        issues: IssueCollector 实例。

    Returns:
        按文档序排列的 HeadingIR 列表，每个标题均已完成分类与编号。
    """
    if not heading_tokens:
        return []

    # --------------------------------------------------------------
    # 第一遍：分类 + 编号剥离，收集中间结构
    # --------------------------------------------------------------

    # 中间结构：(kind, raw_text, text, source_line, orig_num_info)
    # orig_num_info: int|None for CHAPTER, str|None for APPENDIX
    rows: list[dict] = []
    h1_seen = False
    # R-FM（§C.3）：前置件区（FRONT_MATTER）跟踪。
    # 区间起点 = 首个 H1 文本命中前后置件词表（如「前言/导论」）；
    # 区间终点 = 首个"正文信号"H2（携带显式章编号，或附录前缀）。
    # 不再使用魔法数量上限——区间边界由结构信号驱动，可容纳任意数量前言 H2。
    in_front_matter = False
    # R-FM 起点扩展（P006-1，§2.4）：支持"标题 H1 + 紧邻前言 H1"双 H1 结构。
    #   title_h1_pending：首个 H1 是报告标题（未命中前置词）时置 True，开启一次性
    #     窗口，允许紧随其后、正文尚未开始时出现的第二个前置词 H1 作为前置件起点。
    #   body_started：一旦处理到任何 H2/H3/H4/H5/H6（进入内容层）置 True——窗口
    #     随即关闭，确保只有"标题 H1 紧邻前言 H1"这一结构能激活，中间已插入 H2
    #     后再出现的 H1、或第三个及以后的 H1 都走常规 W-HDR-03。
    title_h1_pending = False
    body_started = False
    # W-FM-01 累计告警（P006-3 候选 C1）：统计前置件区内无编号 H2 数量。
    front_matter_h2_count = 0

    for h in heading_tokens:
        raw = h.raw_text
        line = h.source_line

        # -- H1 --
        if h.level == 1:
            if not h1_seen:
                h1_seen = True
                # R-FM（§C.3）：H1 文本命中前后置件词表（含「前言/导论」复合
                # 形式）时，开启前置件区，其后的无编号 H2 归为 FRONT_MATTER。
                if _is_front_back(raw):
                    in_front_matter = True
                else:
                    # 首个 H1 是报告标题 → 开启一次性窗口，允许紧邻前言 H1 起点。
                    title_h1_pending = True
                rows.append({
                    "kind": HeadingKind.MAIN_TITLE,
                    "raw_text": raw,
                    "text": raw,
                    "source_line": line,
                    "markdown_level": h.level,
                    "orig_num": None,
                    "orig_letter": None,
                })
            elif title_h1_pending and not body_started and _is_front_back(raw):
                # P006-1：标题 H1 紧邻的前置词 H1（如「前言/导论」）→ 前置件区起点。
                # 归 FRONT_MATTER（不编号、不占章序，渲染为 Heading 2，见 §2.4 裁决a）；
                # 不发 W-HDR-03（它不是"重复的正文章"，是被识别的前置件起点），
                # 改发 INFO 级 I-HDR-06 留痕。窗口一次性消费。
                in_front_matter = True
                title_h1_pending = False
                issues.append(
                    Issue(
                        level=Level.INFO,
                        code="I-HDR-06",
                        stage="assemble",
                        message=f"识别到标题后的前置件 H1「{raw}」，"
                        f"已作为前置件区起点，未按多余 H1 降级",
                        source_line=line,
                    )
                )
                rows.append({
                    "kind": HeadingKind.FRONT_MATTER,
                    "raw_text": raw,
                    "text": raw,
                    "source_line": line,
                    "orig_num": None,
                    "orig_letter": None,
                    "markdown_level": h.level,
                })
            else:
                # 多余 H1（非前置词、或正文已开始、或窗口已消费）→ 降级为 CHAPTER。
                title_h1_pending = False  # 第二个 H1 已处理，窗口失效
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-HDR-03",
                        stage="assemble",
                        message=f"出现多个 H1「{raw!r}」，首个为主标题，"
                        f"本标题降级为章处理",
                        source_line=line,
                    )
                )
                stripped, orig_num = _strip_chapter(raw, line, issues)
                rows.append({
                    "kind": HeadingKind.CHAPTER,
                    "raw_text": raw,
                    "text": stripped,
                    "source_line": line,
                    "markdown_level": h.level,
                    "orig_num": orig_num,
                    "orig_letter": None,
                })
            continue

        # 进入内容层（任何 H2~H6）：正文已开始，关闭前言 H1 起点窗口（P006-1）。
        body_started = True

        # -- H2 --
        if h.level == 2:
            # 优先1：前后置件关键词匹配
            if _is_front_back(raw):
                kind = HeadingKind.ABSTRACT
                # 特例："目录" H2 → 记 I-CLN-05
                clean = raw.rstrip("：:")
                if clean == "目录":
                    issues.append(
                        Issue(
                            level=Level.INFO,
                            code="I-CLN-05",
                            stage="assemble",
                            message=f"检测到手动「目录」标题（行{line}），"
                            f"自动目录将覆盖手动条目",
                            source_line=line,
                        )
                    )
                rows.append({
                    "kind": kind,
                    "raw_text": raw,
                    "text": raw,
                    "source_line": line,
                    "orig_num": None,
                    "orig_letter": None,
                    "markdown_level": h.level,
                })
                continue

            # R-FM（§C.3）：前置件区内的 H2。
            # 边界终止条件（任一即退出前置件区，本 H2 按正文/附录处理）：
            #   (a) 携带显式章编号（第X章 / N、 等）→ 可靠的正文开始信号；
            #   (b) 附录前缀（N-07）→ 附录属后置件，走 APPENDIX 分支。
            # 未命中终止条件的无编号 H2 → 归为 FRONT_MATTER（不编号、不占章计数）。
            if in_front_matter:
                if _has_explicit_chapter_number(raw) or _RE_N07.match(raw):
                    in_front_matter = False  # 命中正文信号，退出前置件区
                else:
                    # 候选 C1（§2.4，U-1 裁定）：终止条件维持"显式章编号 / 附录前缀"
                    # 两项不变，不做启发式自动分层；仅累计无编号 H2 数量，收尾发
                    # W-FM-01 告警，把"是否含未编号正文章"的判断权交回作者。
                    front_matter_h2_count += 1
                    rows.append({
                        "kind": HeadingKind.FRONT_MATTER,
                        "raw_text": raw,
                        "text": raw,
                        "source_line": line,
                        "orig_num": None,
                        "orig_letter": None,
                        "markdown_level": h.level,
                    })
                    continue

            # 优先2：附录匹配
            if _RE_N07.match(raw):
                stripped, orig_letter = _strip_appendix(raw, line, issues)
                rows.append({
                    "kind": HeadingKind.APPENDIX,
                    "raw_text": raw,
                    "text": stripped,
                    "source_line": line,
                    "markdown_level": h.level,
                    "orig_num": None,
                    "orig_letter": orig_letter,
                })
                continue

            # 默认：章
            stripped, orig_num = _strip_chapter(raw, line, issues)
            rows.append({
                "kind": HeadingKind.CHAPTER,
                "raw_text": raw,
                "text": stripped,
                "source_line": line,
                "markdown_level": h.level,
                "orig_num": orig_num,
                "orig_letter": None,
            })
            continue

        # -- H3 --
        if h.level == 3:
            # R-FM（§C.3）：前置件区内的 H3 保持 FRONT_MATTER（不编号渲染）。
            if in_front_matter:
                stripped = _strip_section(raw, line, issues)
                rows.append({
                    "kind": HeadingKind.FRONT_MATTER,
                    "raw_text": raw,
                    "text": stripped,
                    "source_line": line,
                    "orig_num": None,
                    "orig_letter": None,
                    "markdown_level": h.level,
                })
                continue
            stripped = _strip_section(raw, line, issues)
            rows.append({
                "kind": HeadingKind.SECTION,
                "raw_text": raw,
                "text": stripped,
                "source_line": line,
                "markdown_level": h.level,
                "orig_num": None,
                "orig_letter": None,
            })
            continue

        # -- H4 --
        if h.level == 4:
            # R-FM（§C.3）：前置件区内的 H4 保持 FRONT_MATTER（不编号渲染）。
            if in_front_matter:
                stripped = _strip_subsection(raw, line, issues)
                rows.append({
                    "kind": HeadingKind.FRONT_MATTER,
                    "raw_text": raw,
                    "text": stripped,
                    "source_line": line,
                    "orig_num": None,
                    "orig_letter": None,
                    "markdown_level": h.level,
                })
                continue
            stripped = _strip_subsection(raw, line, issues)
            rows.append({
                "kind": HeadingKind.SUBSECTION,
                "raw_text": raw,
                "text": stripped,
                "source_line": line,
                "markdown_level": h.level,
                "orig_num": None,
                "orig_letter": None,
            })
            continue

        # -- H5/H6 --
        rows.append({
            "kind": HeadingKind.PLAIN,
            "raw_text": raw,
            "text": raw,
            "source_line": line,
            "markdown_level": h.level,
            "orig_num": None,
            "orig_letter": None,
        })

    # --------------------------------------------------------------
    # 第一遍收尾：W-FM-01 前置件区无编号 H2 累计告警（P006-3 候选 C1）
    # --------------------------------------------------------------
    # 前置件区内出现过无编号 H2 → 提示作者：若其中包含正文章，请为正文首章补显式
    # 编号以标示正文起点。此为"只告警不猜测"——无编号正文章与前言 H2 在信息论上
    # 不可判定，转换器不做启发式分层（U-1 裁定用 C1，不引入候选 C2）。
    if front_matter_h2_count >= 1:
        issues.append(
            Issue(
                level=Level.WARNING,
                code="W-FM-01",
                stage="assemble",
                message=f"前置件区内累计 {front_matter_h2_count} 个无编号 H2；"
                f"若含正文章请为正文首章补显式编号（第X章 / 一、）以标示正文起点",
            )
        )

    # --------------------------------------------------------------
    # 第二遍：结构化重编
    # --------------------------------------------------------------

    chapter_index = 0
    section_index = 0
    subsection_index = 0
    appendix_index = 0

    # 收集原始编号用于连续性校验
    orig_chapter_nums: list[int | None] = []
    orig_appendix_letters: list[str | None] = []

    results: list[HeadingIR] = []

    for row in rows:
        kind: HeadingKind = row["kind"]
        raw_text: str = row["raw_text"]
        text: str = row["text"]
        source_line: int = row["source_line"]
        orig_num: int | None = row["orig_num"]
        orig_letter: str | None = row["orig_letter"]
        markdown_level: int | None = row.get("markdown_level")

        number: HeadingNumber = None
        display_number = ""

        if kind == HeadingKind.CHAPTER:
            chapter_index += 1
            section_index = 0
            subsection_index = 0
            number = chapter_index
            display_number = f"第{int_to_cn(chapter_index)}章"
            orig_chapter_nums.append(orig_num)

        elif kind == HeadingKind.SECTION:
            section_index += 1
            subsection_index = 0
            number = (chapter_index, section_index)
            display_number = f"{chapter_index}.{section_index}"

        elif kind == HeadingKind.SUBSECTION:
            subsection_index += 1
            number = (chapter_index, section_index, subsection_index)
            display_number = f"{chapter_index}.{section_index}.{subsection_index}"

        elif kind == HeadingKind.APPENDIX:
            appendix_index += 1
            letter = chr(ord("A") + appendix_index - 1)
            number = letter
            display_number = f"附录{letter}"
            orig_appendix_letters.append(orig_letter)

        elif kind == HeadingKind.MAIN_TITLE:
            pass  # number=None, display_number=""

        elif kind == HeadingKind.ABSTRACT:
            pass  # number=None, display_number=""

        elif kind == HeadingKind.FRONT_MATTER:
            pass  # number=None, display_number=""

        elif kind == HeadingKind.PLAIN:
            pass  # number=None, display_number=""

        results.append(
            HeadingIR(
                kind=kind,
                raw_text=raw_text,
                text=text,
                number=number,
                display_number=display_number,
                source_line=source_line,
                markdown_level=markdown_level,
            )
        )

    # --------------------------------------------------------------
    # 第三遍：编号连续性校验（02 §C.5）
    # --------------------------------------------------------------

    # 章编号连续性
    _check_chapter_continuity(results, orig_chapter_nums, issues)

    # 附录字母连续性
    _check_appendix_continuity(results, orig_appendix_letters, issues)

    # 重复检测
    _check_duplicate_numbers(results, issues)

    return results


def _check_chapter_continuity(
    results: list[HeadingIR],
    orig_nums: list[int | None],
    issues: IssueCollector,
) -> None:
    """校验章原编号是否 1..n 连续（W-HDR-01）。"""
    # P0 修复（空真值陷阱）：区分两种"跳过"语义完全不同的情况——
    #   (a) orig_nums 为空列表：说明本文档一章 CHAPTER 级标题都没有识别到，
    #       这是上游标题分类环节的结构性异常（正常报告必有 ≥1 章），
    #       `all(on is None for on in [])` 会因空列表真值陷阱而返回 True，
    #       原实现据此直接 return，不产生任何 issue，属于假阴性。
    #   (b) orig_nums 非空但全为 None：说明章标题确实存在，只是原始 md
    #       文本中均未手写"第X章"式编号（完全依赖工具自动编号），这是
    #       正常、常见的写作方式，不代表任何缺陷，应继续跳过而不告警。
    if not orig_nums:
        chapter_irs = [r for r in results if r.kind == HeadingKind.CHAPTER]
        issues.append(
            Issue(
                level=Level.ERROR,
                code="W-HDR-01",
                stage="assemble",
                message="章编号连续性校验：未发现任何 CHAPTER 级标题，"
                "无法判定原始编号是否连续，判定为结构性异常而非'无需检查'",
                element_ref=f"chapters_found={len(chapter_irs)}",
                suggestion="检查标题分类环节是否正确识别出章级标题",
            )
        )
        return
    if all(on is None for on in orig_nums):
        return

    expected = list(range(1, len(orig_nums) + 1))
    # 比较时需要处理 None：将 None 映射为一个不会匹配的值
    for i, (orig, exp) in enumerate(zip(orig_nums, expected)):
        if orig is None:
            continue  # 无编号的章跳过单条校验
        if orig != exp:
            # 找到对应的 HeadingIR 用于定位
            chapter_irs = [r for r in results if r.kind == HeadingKind.CHAPTER]
            if i < len(chapter_irs):
                ir = chapter_irs[i]
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-HDR-01",
                        stage="assemble",
                        message=f"章原手动编号 {orig} 与重编结果 {exp} 不一致"
                        f"（标题：{ir.raw_text!r}）",
                        source_line=ir.source_line,
                        element_ref=f"H2:{ir.raw_text}",
                        suggestion="手动编号存在跳号、重复或乱序，已按文档序重编",
                    )
                )


def _check_appendix_continuity(
    results: list[HeadingIR],
    orig_letters: list[str | None],
    issues: IssueCollector,
) -> None:
    """校验附录原字母与重编字母是否一致（W-HDR-02）。"""
    appendix_irs = [r for r in results if r.kind == HeadingKind.APPENDIX]
    if not appendix_irs:
        return

    for i, (orig_letter, ir) in enumerate(zip(orig_letters, appendix_irs)):
        expected = chr(ord("A") + i)
        if orig_letter and orig_letter.upper() != expected:
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-HDR-02",
                    stage="assemble",
                    message=f"附录原字母「{orig_letter}」与重编字母"
                    f"「{expected}」不一致（标题：{ir.raw_text!r}）",
                    source_line=ir.source_line,
                    element_ref=f"H2:{ir.raw_text}",
                )
            )


def _check_duplicate_numbers(
    results: list[HeadingIR],
    issues: IssueCollector,
) -> None:
    """检测同级同编号重复（W-HDR-01）。"""
    seen: dict[tuple[HeadingKind, str], HeadingIR] = {}
    for ir in results:
        if ir.display_number == "":
            continue
        key = (ir.kind, ir.display_number)
        if key in seen:
            prev = seen[key]
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-HDR-01",
                    stage="assemble",
                    message=f"标题编号重复：{ir.display_number!r} 出现多次"
                    f"（首次行{prev.source_line}，本次行{ir.source_line}）",
                    source_line=ir.source_line,
                    element_ref=f"H{'_'.join(ir.display_number)}",
                )
            )
        else:
            seen[key] = ir


# ---------------------------------------------------------------------------
# 自检（验收标准）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    passed = 0
    failed = 0

    def check(desc: str, condition: bool, detail: str = "") -> None:
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {desc}")
        else:
            failed += 1
            print(f"  [FAIL] {desc}  -- {detail}")
            if detail:
                print(f"         详情: {detail}")

    # --- 中文数字转换 ---
    print("\n=== 中文数字转换 ===")
    check("int_to_cn(1) == '一'", int_to_cn(1) == "一", int_to_cn(1))
    check("int_to_cn(10) == '十'", int_to_cn(10) == "十", int_to_cn(10))
    check("int_to_cn(11) == '十一'", int_to_cn(11) == "十一", int_to_cn(11))
    check("int_to_cn(21) == '二十一'", int_to_cn(21) == "二十一", int_to_cn(21))
    check("int_to_cn(100) == '一百'", int_to_cn(100) == "一百", int_to_cn(100))
    check("int_to_cn(101) == '一百零一'", int_to_cn(101) == "一百零一", int_to_cn(101))
    check("cn_to_int('一') == 1", cn_to_int("一") == 1, str(cn_to_int("一")))
    check("cn_to_int('十一') == 11", cn_to_int("十一") == 11, str(cn_to_int("十一")))
    check("cn_to_int('一百一十') == 110", cn_to_int("一百一十") == 110, str(cn_to_int("一百一十")))
    check("cn_to_int('二十') == 20", cn_to_int("二十") == 20, str(cn_to_int("二十")))
    check("cn_to_int('一百零一') == 101", cn_to_int("一百零一") == 101, str(cn_to_int("一百零一")))

    # --- 场景1：无编号 H2 → CHAPTER ---
    print("\n=== 场景1：无编号 H2 ===")
    c1 = IssueCollector()
    tokens1 = [HeadingToken(level=2, raw_text="研究方法", source_line=10)]
    r1 = classify_and_number(tokens1, c1)
    check("kind=CHAPTER", r1[0].kind == HeadingKind.CHAPTER, str(r1[0].kind))
    check("display_number='第一章'", r1[0].display_number == "第一章", r1[0].display_number)
    check("text='研究方法'", r1[0].text == "研究方法", r1[0].text)

    # --- 场景2：「## 第一章 导论」 → CHAPTER, text='导论', display_number='第一章' ---
    print("\n=== 场景2：第X章 H2 ===")
    c2 = IssueCollector()
    tokens2 = [HeadingToken(level=2, raw_text="第一章 导论", source_line=10)]
    r2 = classify_and_number(tokens2, c2)
    check("kind=CHAPTER", r2[0].kind == HeadingKind.CHAPTER, str(r2[0].kind))
    check("text='导论'", r2[0].text == "导论", r2[0].text)
    check("display_number='第一章'", r2[0].display_number == "第一章", r2[0].display_number)
    check("number=1", r2[0].number == 1, str(r2[0].number))
    # 剥离动作记 I-CLN-05
    check("有 I-CLN-05", any(i.code == "I-CLN-05" for i in c2), "剥离编号应产生 I-CLN-05")

    # --- 场景3：「## 附录A：事实核验」 → APPENDIX ---
    print("\n=== 场景3：附录 H2 ===")
    c3 = IssueCollector()
    tokens3 = [HeadingToken(level=2, raw_text="附录A：事实核验", source_line=10)]
    r3 = classify_and_number(tokens3, c3)
    check("kind=APPENDIX", r3[0].kind == HeadingKind.APPENDIX, str(r3[0].kind))
    check("text='事实核验'", r3[0].text == "事实核验", r3[0].text)
    check("display_number='附录A'", r3[0].display_number == "附录A", r3[0].display_number)
    check("number='A'", r3[0].number == "A", str(r3[0].number))

    # --- 场景4：「## 摘要」 → ABSTRACT ---
    print("\n=== 场景4：摘要 H2 ===")
    c4 = IssueCollector()
    tokens4 = [HeadingToken(level=2, raw_text="摘要", source_line=10)]
    r4 = classify_and_number(tokens4, c4)
    check("kind=ABSTRACT", r4[0].kind == HeadingKind.ABSTRACT, str(r4[0].kind))
    check("display_number=''", r4[0].display_number == "", r4[0].display_number)
    check("number=None", r4[0].number is None, str(r4[0].number))

    # --- 场景5：「### 1.1 背景」 → SECTION ---
    print("\n=== 场景5：H3 节 ===")
    c5 = IssueCollector()
    # 需要先有一个 CHAPTER 才能有正确的节编号。
    # 注意：父章标题须用非前后置件词（避免命中 FRONT_BACK_WORDS 被判为不编号），
    # 故用「研究方法」而非「导论」——后者作为裸 H2 属前置件，不占章计数。
    tokens5 = [
        HeadingToken(level=2, raw_text="研究方法", source_line=5),
        HeadingToken(level=3, raw_text="1.1 背景", source_line=10),
    ]
    r5 = classify_and_number(tokens5, c5)
    sec = r5[1]
    check("kind=SECTION", sec.kind == HeadingKind.SECTION, str(sec.kind))
    check("display_number='1.1'", sec.display_number == "1.1", sec.display_number)
    check("text='背景'", sec.text == "背景", sec.text)

    # --- 场景6：跳号 → W-HDR-01 ---
    print("\n=== 场景6：章跳号 → W-HDR-01 ===")
    c6 = IssueCollector()
    tokens6 = [
        HeadingToken(level=2, raw_text="第一章 导论", source_line=5),
        HeadingToken(level=2, raw_text="第三章 方法", source_line=15),
    ]
    r6 = classify_and_number(tokens6, c6)
    check("第一章 display_number", r6[0].display_number == "第一章", r6[0].display_number)
    check("第三章 display_number=第二章", r6[1].display_number == "第二章",
          f"expected 第二章, got {r6[1].display_number}")
    check("有 W-HDR-01", any(i.code == "W-HDR-01" for i in c6),
          "跳号应产生 W-HDR-01")

    # --- 场景7：多 H1 → W-HDR-03 ---
    print("\n=== 场景7：多个 H1 ===")
    c7 = IssueCollector()
    tokens7 = [
        HeadingToken(level=1, raw_text="主标题", source_line=1),
        HeadingToken(level=1, raw_text="多余的H1", source_line=3),
    ]
    r7 = classify_and_number(tokens7, c7)
    check("首个 H1=MAIN_TITLE", r7[0].kind == HeadingKind.MAIN_TITLE, str(r7[0].kind))
    check("第二个 H1=CHAPTER", r7[1].kind == HeadingKind.CHAPTER, str(r7[1].kind))
    check("有 W-HDR-03", any(i.code == "W-HDR-03" for i in c7),
          "多个 H1 应产生 W-HDR-03")

    # --- 场景8：H4 小节 ---
    print("\n=== 场景8：H4 小节 ===")
    c8 = IssueCollector()
    # 父章标题同场景5，用非前后置件词以确保占章计数。
    tokens8 = [
        HeadingToken(level=2, raw_text="研究方法", source_line=5),
        HeadingToken(level=3, raw_text="1.1 节标题", source_line=10),
        HeadingToken(level=4, raw_text="1.1.1 小节标题", source_line=15),
    ]
    r8 = classify_and_number(tokens8, c8)
    sub = r8[2]
    check("kind=SUBSECTION", sub.kind == HeadingKind.SUBSECTION, str(sub.kind))
    check("display_number='1.1.1'", sub.display_number == "1.1.1", sub.display_number)
    check("text='小节标题'", sub.text == "小节标题", sub.text)

    # --- 场景9："执行摘要" H2 → ABSTRACT ---
    print("\n=== 场景9：执行摘要 ===")
    c9 = IssueCollector()
    tokens9 = [HeadingToken(level=2, raw_text="执行摘要", source_line=10)]
    r9 = classify_and_number(tokens9, c9)
    check("kind=ABSTRACT", r9[0].kind == HeadingKind.ABSTRACT, str(r9[0].kind))

    # --- 场景10：附录编号连续性 ---
    print("\n=== 场景10：附录字母不连续 ===")
    c10 = IssueCollector()
    tokens10 = [
        HeadingToken(level=2, raw_text="附录B：补充数据", source_line=50),
        HeadingToken(level=2, raw_text="附录A：事实核验", source_line=60),
    ]
    r10 = classify_and_number(tokens10, c10)
    check("第一个附录 display='附录A'", r10[0].display_number == "附录A",
          r10[0].display_number)
    check("第二个附录 display='附录B'", r10[1].display_number == "附录B",
          r10[1].display_number)
    check("有 W-HDR-02", any(i.code == "W-HDR-02" for i in c10),
          "附录原字母与重编不一致应产生 W-HDR-02")

    # --- 场景11：FRONT_MATTER 复合前置件标题（§C.3 R-FM）---
    print("\n=== 场景11：前言/导论 复合前置件 ===")
    # _is_front_back 复合词判定单元测试
    check("_is_front_back('前言/导论')", _is_front_back("前言/导论"))
    check("_is_front_back('绪论、引言')", _is_front_back("绪论、引言"))
    check("_is_front_back('前言')", _is_front_back("前言"))
    check("not _is_front_back('研究方法目录结构')",
          not _is_front_back("研究方法目录结构"),
          "含'目录'子串但整串非白名单，不应误判")
    check("not _is_front_back('背景/导论对比')",
          not _is_front_back("背景/导论对比"),
          "复合中有段未命中白名单，不应误判")
    c11 = IssueCollector()
    tokens11 = [
        HeadingToken(level=1, raw_text="前言/导论", source_line=1),
        HeadingToken(level=2, raw_text="问题提出", source_line=5),
        HeadingToken(level=2, raw_text="研究目标", source_line=9),
    ]
    r11 = classify_and_number(tokens11, c11)
    fm11 = [r for r in r11 if r.kind == HeadingKind.FRONT_MATTER]
    check("2 个 FRONT_MATTER H2", len(fm11) == 2,
          f"实际 {len(fm11)}：{[r.kind.name for r in r11]}")
    check("FRONT_MATTER 无编号", all(r.display_number == "" for r in fm11),
          str([r.display_number for r in fm11]))
    check("FRONT_MATTER 未被编为第一章",
          not any(r.display_number.startswith("第") for r in fm11))

    # --- 场景12：FRONT_MATTER 区遇显式章编号即终止（边界，§C.3 R-FM）---
    print("\n=== 场景12：前言区边界终止 ===")
    c12 = IssueCollector()
    tokens12 = [
        HeadingToken(level=1, raw_text="前言/导论", source_line=1),
        HeadingToken(level=2, raw_text="研究背景", source_line=5),      # FRONT_MATTER
        HeadingToken(level=2, raw_text="第一章 正文", source_line=9),   # 显式编号→退出前言区
        HeadingToken(level=2, raw_text="市场分析", source_line=13),      # CHAPTER（正文续）
    ]
    r12 = classify_and_number(tokens12, c12)
    kinds12 = {r.source_line: r for r in r12}
    check("行5=FRONT_MATTER", kinds12[5].kind == HeadingKind.FRONT_MATTER,
          kinds12[5].kind.name)
    check("行9=CHAPTER 第一章", kinds12[9].kind == HeadingKind.CHAPTER
          and kinds12[9].display_number == "第一章",
          f"{kinds12[9].kind.name}/{kinds12[9].display_number}")
    check("行13=CHAPTER 第二章", kinds12[13].kind == HeadingKind.CHAPTER
          and kinds12[13].display_number == "第二章",
          f"{kinds12[13].kind.name}/{kinds12[13].display_number}")

    # --- 汇总 ---
    print(f"\n{'='*50}")
    print(f"通过: {passed}, 失败: {failed}")
    print(f"{'='*50}")

    if failed > 0:
        sys.exit(1)
    else:
        print("全部自检通过！")
