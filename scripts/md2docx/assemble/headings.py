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

    digits = "零一二三四五六七八九"

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
    """判断标题文本是否匹配前后置件关键词白名单（02 §F.2）。

    精确匹配，允许尾随全/半角冒号（：或:）。
    """
    clean = text.rstrip("：:")
    return clean in FRONT_BACK_WORDS


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

    for h in heading_tokens:
        raw = h.raw_text
        line = h.source_line

        # -- H1 --
        if h.level == 1:
            if not h1_seen:
                h1_seen = True
                rows.append({
                    "kind": HeadingKind.MAIN_TITLE,
                    "raw_text": raw,
                    "text": raw,
                    "source_line": line,
                    "orig_num": None,
                    "orig_letter": None,
                })
            else:
                # 多余 H1 → 降级为 CHAPTER
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
                    "orig_num": orig_num,
                    "orig_letter": None,
                })
            continue

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
                "orig_num": orig_num,
                "orig_letter": None,
            })
            continue

        # -- H3 --
        if h.level == 3:
            stripped = _strip_section(raw, line, issues)
            rows.append({
                "kind": HeadingKind.SECTION,
                "raw_text": raw,
                "text": stripped,
                "source_line": line,
                "orig_num": None,
                "orig_letter": None,
            })
            continue

        # -- H4 --
        if h.level == 4:
            stripped = _strip_subsection(raw, line, issues)
            rows.append({
                "kind": HeadingKind.SUBSECTION,
                "raw_text": raw,
                "text": stripped,
                "source_line": line,
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
            "orig_num": None,
            "orig_letter": None,
        })

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
    # 纯 None 序列（所有章均无原始编号）→ 跳过校验
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
    # 需要先有一个 CHAPTER 才能有正确的节编号
    tokens5 = [
        HeadingToken(level=2, raw_text="导论", source_line=5),
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
    tokens8 = [
        HeadingToken(level=2, raw_text="导论", source_line=5),
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

    # --- 汇总 ---
    print(f"\n{'='*50}")
    print(f"通过: {passed}, 失败: {failed}")
    print(f"{'='*50}")

    if failed > 0:
        sys.exit(1)
    else:
        print("全部自检通过！")
