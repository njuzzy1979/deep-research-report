"""阶段4：渲染前只读校验（C-06）。

对已构建的 DocumentIR 做只读校验，所有问题走 Issue，不修改 IR。
唯一例外：填充 document_ir.xref_registry（交叉引用登记结果），这是校验的
产出而非对 IR 的修改。

设计依据：
  - 01-architecture.md §2.4（校验项：图片存在性复核、编号连续性、密级兜底）
  - 02-algorithms.md §E（交叉引用一致性校验，W-REF-01~04）
  - 02-algorithms.md §C.5（标题编号连续性兜底复核）

校验项：
  1. 图片文件存在性复核（阶段3 探测后到阶段4 前可能被删除）
  2. 图编号连续性（章内序号跳号/重复、章号一致性）
  3. 表编号连续性（同图编号逻辑，仅正文表）
  4. 标题编号连续性（兜底复核——headings.py 已在阶段3 做过）
  5. 交叉引用一致性校验（引用存在性、先文后图、位置性指代、孤立引用行）
  6. 密级字样兜底扫描（清理层第二道闸）
  7. title_short 合理性
"""
from __future__ import annotations

import os
import re

from .ir import (
    DocumentIR,
    FigureIR,
    HeadingIR,
    HeadingKind,
    ListBlockIR,
    ParagraphIR,
    QuoteIR,
    TableIR,
    TableKind,
    XRefMention,
)
from .issues import Issue, IssueCollector, Level

# ---------------------------------------------------------------------------
# 正则模式（02 §E.3）
# ---------------------------------------------------------------------------

# 引用模式核心："图1-1" / "表4-1"。不枚举句式前缀，靠核心模式命中全部句式
# （"如图X-Y所示"、"（图X-Y）"、"见表X-Y"、"详见第四章图4-2"等）。
_RE_REF = re.compile(r"(图|表)(\d{1,2})-(\d{1,2})")

# 位置性指代；(?<!以) 防"以下图表"误报（02 §E.3）
_RE_POS = re.compile(r"(?<!以)[上下]图|(?<!以)[上下]表")

# 孤立图引用行形状（R-07 剥离列表前缀后的残留段）
_RE_ORPH = re.compile(r"^图\d{1,2}-\d{1,2}(?:[：:]|[ 　]).{0,80}$")

# 密级弱信号关键词（同 clean.py R-09弱 的词表，02 §D.2 / config.py）
_SECRECY_WEAK_RE = re.compile(
    r"绝密|机密|内部资料|内部参考|限内部使用|仅供内部|密级"
)

# 从 display_number 中提取中文数字（用于标题兜底复核）
_RE_CN_CHAPTER = re.compile(r"第([一二三四五六七八九十百]+)章")

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def validate(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """阶段4：渲染前只读校验。所有问题走 Issue，不修改 IR。

    校验完成后在 document_ir.xref_registry 中填充交叉引用登记结果
    （这是校验的产出，不违背只读性——它是校验的登记结果）。
    """
    # 1. 图片文件存在性复核
    _check_figure_files(document_ir, issues)

    # 2. 图编号连续性
    _check_figure_numbering(document_ir, issues)

    # 3. 表编号连续性（仅正文表）
    _check_table_numbering(document_ir, issues)

    # 4. 标题编号连续性（兜底复核）
    _check_heading_numbering(document_ir, issues)

    # 5. 交叉引用一致性校验（含 xref_registry 填充）
    _check_xref_consistency(document_ir, issues)

    # 6. 密级字样兜底扫描
    _check_secrecy_keywords(document_ir, issues)

    # 7. title_short 合理性
    _check_title_short(document_ir, issues)


# ---------------------------------------------------------------------------
# 1. 图片文件存在性复核
# ---------------------------------------------------------------------------


def _check_figure_files(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """对 figure_registry 中已标记 file_exists=True 的图做 os.path.isfile 复核。

    若阶段3 探测到文件存在但阶段4 前被删除（解析→校验之间的时间窗口），
    报 ERROR(E-IMG-01)。file_exists=False 的图已在阶段3 登记过，不重复报。
    """
    for fig_id, fig in document_ir.figure_registry.items():
        if not fig.file_exists:
            # 阶段3 已记录为不存在，不重复报
            continue
        if not os.path.isfile(fig.path_resolved):
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-IMG-01",
                    stage="validate",
                    message=f"图片文件在解析后到校验前被删除：{fig.path_resolved!r}",
                    source_line=fig.source_line,
                    element_ref=f"图{fig_id}",
                    suggestion="请确认 figures 目录下该文件未被误删，"
                    "或更新 md 中的图片路径后重新转换",
                )
            )


# ---------------------------------------------------------------------------
# 2. 图编号连续性
# ---------------------------------------------------------------------------


def _check_figure_numbering(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """校验 figure_registry 中图的编号连续性。

    - 章内 seq_no 跳号/乱序 → W-IMG-06
    - 同 figure_id 出现两次 → W-IMG-05（理论上 dict key 唯一，此检查防御性保留）
    - 图号章号与所在章序不一致 → W-IMG-04
    """
    if not document_ir.figure_registry:
        return

    # 构建元素→所属章序的映射（用于 W-IMG-04）
    chapter_of_element = _build_element_chapter_map(document_ir)

    # 按章分组
    chapters: dict[int, list[FigureIR]] = {}
    for fig in document_ir.figure_registry.values():
        chapters.setdefault(fig.chapter_no, []).append(fig)

    for ch_no, figs in sorted(chapters.items()):
        # 章内按 seq_no 排序
        figs_sorted = sorted(figs, key=lambda f: f.seq_no)
        seqs = [f.seq_no for f in figs_sorted]

        # 重复检测（同 chapter_no + seq_no 出现两次；由于 dict key 是 figure_id，
        # 同一 figure_id 不会重复进入 registry，但不同 figure_id 可能共享相同编号）
        seen_seqs: set[int] = set()
        for f in figs_sorted:
            if f.seq_no in seen_seqs:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-IMG-05",
                        stage="validate",
                        message=f"图编号重复：图{f.chapter_no}-{f.seq_no} 出现多次",
                        source_line=f.source_line,
                        element_ref=f"图{f.figure_id}",
                        suggestion="请检查 md 中图片 alt 的图号是否重复",
                    )
                )
            seen_seqs.add(f.seq_no)

        # 跳号/乱序检测：期望 1, 2, 3, ...
        expected = list(range(1, len(figs_sorted) + 1))
        for i, (actual, exp) in enumerate(zip(seqs, expected)):
            if actual != exp:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-IMG-06",
                        stage="validate",
                        message=f"章内图号跳号或乱序：第{ch_no}章期望 seq={exp}，"
                        f"实际 seq={actual}",
                        source_line=figs_sorted[i].source_line,
                        element_ref=f"图{figs_sorted[i].figure_id}",
                        suggestion="请检查 md 中图片是否遗漏或 alt 图号是否跳号",
                    )
                )

        # 章号一致性：图号章号与所在章序是否一致（W-IMG-04）
        for f in figs_sorted:
            actual_chapter = chapter_of_element.get(id(f))
            if actual_chapter is not None and actual_chapter != f.chapter_no:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-IMG-04",
                        stage="validate",
                        message=f"图号章号与所在章序不一致：图{f.figure_id} 标注为第"
                        f"{f.chapter_no}章，但位于第{actual_chapter}章正文中",
                        source_line=f.source_line,
                        element_ref=f"图{f.figure_id}",
                        suggestion="请检查 md 中图片 alt 的图号章号是否正确",
                    )
                )


# ---------------------------------------------------------------------------
# 3. 表编号连续性
# ---------------------------------------------------------------------------


def _check_table_numbering(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """校验 table_registry 中正文表的编号连续性（W-TBL-02）。

    仅检查 kind=BODY 的表（附录表无编号，不参与校验）。
    逻辑同图编号：跳号/乱序/重复/章号不一致。
    """
    if not document_ir.table_registry:
        return

    body_tables = {
        tid: t
        for tid, t in document_ir.table_registry.items()
        if t.kind == TableKind.BODY
    }
    if not body_tables:
        return

    chapter_of_element = _build_element_chapter_map(document_ir)

    # 按章分组（table_id 格式 "X-Y"）
    chapters: dict[int, list[tuple[str, TableIR]]] = {}
    for tid, tbl in body_tables.items():
        if tbl.table_id is None:
            continue
        # 从 table_id 解析章号
        parts = tbl.table_id.split("-")
        try:
            ch_no = int(parts[0])
        except (ValueError, IndexError):
            continue
        chapters.setdefault(ch_no, []).append((tid, tbl))

    for ch_no, items in sorted(chapters.items()):
        # 按 seq_no 排序（从 table_id 解析）
        def _seq(item: tuple[str, TableIR]) -> int:
            parts = item[0].split("-")
            try:
                return int(parts[1])
            except (ValueError, IndexError):
                return 0

        items_sorted = sorted(items, key=_seq)
        seqs = [_seq(it) for it in items_sorted]

        # 重复检测
        seen_seqs: set[int] = set()
        for tid, tbl in items_sorted:
            s = _seq((tid, tbl))
            if s in seen_seqs:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-TBL-02",
                        stage="validate",
                        message=f"表编号重复：表{tid} 出现多次",
                        source_line=tbl.source_line,
                        element_ref=f"表{tid}",
                        suggestion="请检查 md 中表题注的编号是否重复",
                    )
                )
            seen_seqs.add(s)

        # 跳号/乱序检测
        expected = list(range(1, len(items_sorted) + 1))
        for i, (actual, exp) in enumerate(zip(seqs, expected)):
            if actual != exp:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-TBL-02",
                        stage="validate",
                        message=f"章内表号跳号或乱序：第{ch_no}章期望 seq={exp}，"
                        f"实际 seq={actual}",
                        source_line=items_sorted[i][1].source_line,
                        element_ref=f"表{items_sorted[i][0]}",
                        suggestion="请检查 md 中表题注的编号是否跳号",
                    )
                )

        # 章号一致性
        for tid, tbl in items_sorted:
            actual_chapter = chapter_of_element.get(id(tbl))
            if actual_chapter is not None and actual_chapter != ch_no:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-TBL-02",
                        stage="validate",
                        message=f"表号章号与所在章序不一致：表{tid} 标注为第"
                        f"{ch_no}章，但位于第{actual_chapter}章正文中",
                        source_line=tbl.source_line,
                        element_ref=f"表{tid}",
                        suggestion="请检查 md 中表题注的章号是否正确",
                    )
                )


# ---------------------------------------------------------------------------
# 4. 标题编号连续性（兜底复核，02 §C.5）
# ---------------------------------------------------------------------------


def _check_heading_numbering(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """对 headings.py 阶段3 已做的连续性校验做兜底复核。

    检查项：
      - CHAPTER 数量与编号最大值是否一致 → W-HDR-01
      - 章编号跳号/重复 → W-HDR-01
      - 附录字母不连续 → W-HDR-02

    注意：headings.py 已在阶段3 做完同样的校验，此处是渲染前的二次确认。
    """
    headings = [e for e in document_ir.elements if isinstance(e, HeadingIR)]

    # ---- 章编号连续性 ----
    chapters = [h for h in headings if h.kind == HeadingKind.CHAPTER]
    if chapters:
        chapter_nums: list[int] = []
        for h in chapters:
            if isinstance(h.number, int):
                chapter_nums.append(h.number)

        if chapter_nums:
            # check: len(chapter_nums) == max(chapter_nums)
            # 且序列为 1,2,3,...,n
            expected = list(range(1, len(chapter_nums) + 1))
            for i, (actual, exp) in enumerate(zip(chapter_nums, expected)):
                if actual != exp:
                    issues.append(
                        Issue(
                            level=Level.WARNING,
                            code="W-HDR-01",
                            stage="validate",
                            message=f"章编号跳号或乱序（兜底复核）：期望第{exp}章，"
                            f"实际编号为{actual}",
                            source_line=chapters[i].source_line,
                            element_ref=f"H2:{chapters[i].raw_text}",
                            suggestion="阶段3 重编应已修正渲染编号，此处提示"
                            "原手动编号与文档序不一致，请确认",
                        )
                    )

            # 重复检测（同一 number 出现多次）
            seen: set[int] = set()
            for i, num in enumerate(chapter_nums):
                if num in seen:
                    issues.append(
                        Issue(
                            level=Level.WARNING,
                            code="W-HDR-01",
                            stage="validate",
                            message=f"章编号重复（兜底复核）：编号{num}出现多次",
                            source_line=chapters[i].source_line,
                            element_ref=f"H2:{chapters[i].raw_text}",
                            suggestion="请检查 md 中章节标题的手动编号是否重复",
                        )
                    )
                seen.add(num)

    # ---- 附录字母连续性 ----
    appendixes = [h for h in headings if h.kind == HeadingKind.APPENDIX]
    if appendixes:
        app_letters: list[str] = []
        for h in appendixes:
            if isinstance(h.number, str):
                app_letters.append(h.number.upper())

        if app_letters:
            expected_letters = [chr(ord("A") + i) for i in range(len(app_letters))]
            for i, (actual, exp) in enumerate(zip(app_letters, expected_letters)):
                if actual != exp:
                    issues.append(
                        Issue(
                            level=Level.WARNING,
                            code="W-HDR-02",
                            stage="validate",
                            message=f"附录字母不连续（兜底复核）：期望附录{exp}，"
                            f"实际编号为附录{actual}",
                            source_line=appendixes[i].source_line,
                            element_ref=f"H2:{appendixes[i].raw_text}",
                            suggestion="阶段3 重编应已修正渲染编号，请确认",
                        )
                    )

            # 重复检测
            seen_letters: set[str] = set()
            for i, letter in enumerate(app_letters):
                if letter in seen_letters:
                    issues.append(
                        Issue(
                            level=Level.WARNING,
                            code="W-HDR-02",
                            stage="validate",
                            message=f"附录字母重复（兜底复核）：附录{letter}出现多次",
                            source_line=appendixes[i].source_line,
                            element_ref=f"H2:{appendixes[i].raw_text}",
                            suggestion="请检查 md 中附录标题的字母编号是否重复",
                        )
                    )
                seen_letters.add(letter)


# ---------------------------------------------------------------------------
# 5. 交叉引用一致性校验（02 §E）
# ---------------------------------------------------------------------------


def _check_xref_consistency(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """扫描正文段落，登记图/表引用并校验一致性。

    产出（唯一允许的"写"操作）：
      - 填充 document_ir.xref_registry

    校验项：
      - W-REF-01：图/表存在但从未在正文中被引用
      - W-REF-02：先见图后见文（首次正文引用晚于图/表位置）
      - W-REF-03：正文引用了不存在的图/表编号 / 孤立引用行
      - W-REF-04："上图/下图/上表/下表"位置性指代残留
    """
    # 清空并重建 xref_registry
    document_ir.xref_registry.clear()

    # ---- 确定扫描范围：FRONT_BACK + CHAPTER 区段（排除 APPENDIX 之后） ----
    # 找到第一个 APPENDIX 标题的位置
    first_appendix_idx: int | None = None
    for i, el in enumerate(document_ir.elements):
        if isinstance(el, HeadingIR) and el.kind == HeadingKind.APPENDIX:
            first_appendix_idx = i
            break

    # ---- 构建实体位置表 ----
    # figure 实体：(figure_id, FigureIR, 元素索引, source_line)
    figure_entities: dict[str, tuple[FigureIR, int, int]] = {}
    for i, el in enumerate(document_ir.elements):
        if isinstance(el, FigureIR):
            figure_entities[el.figure_id] = (el, i, el.source_line)

    # table 实体（仅正文表）：(table_id, TableIR, 元素索引, source_line)
    table_entities: dict[str, tuple[TableIR, int, int]] = {}
    for i, el in enumerate(document_ir.elements):
        if isinstance(el, TableIR) and el.kind == TableKind.BODY and el.table_id:
            table_entities[el.table_id] = (el, i, el.source_line)

    # ---- 扫描正文段落，登记引用 ----
    # refs: (ref_type, X, Y) → list[mention_source_line]
    refs: dict[tuple[str, int, int], list[int]] = {}
    scan_end = first_appendix_idx if first_appendix_idx is not None else len(
        document_ir.elements
    )

    for i in range(scan_end):
        el = document_ir.elements[i]
        if not isinstance(el, (ParagraphIR, ListBlockIR, QuoteIR)):
            continue

        text = _extract_element_text(el)
        source_line = _get_element_source_line(el)

        # 扫描引用模式
        for m in _RE_REF.finditer(text):
            ref_word = m.group(1)  # "图" or "表"
            ref_type = "figure" if ref_word == "图" else "table"
            x = int(m.group(2))
            y = int(m.group(3))
            key = (ref_type, x, y)
            refs.setdefault(key, []).append(source_line)

            # 登记到 xref_registry
            ref_id = f"{ref_word}{x}-{y}"
            document_ir.xref_registry.append(
                XRefMention(
                    ref_id=ref_id,
                    ref_type=ref_type,
                    mention_line=source_line,
                    style="paren",
                )
            )

        # 扫描位置性指代
        for m in _RE_POS.finditer(text):
            pos_word = m.group()
            # 获取上下文 ±15 字
            start = max(0, m.start() - 15)
            end = min(len(text), m.end() + 15)
            context = text[start:end]
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-REF-04",
                    stage="validate",
                    message=f"位置性指代残留：「{pos_word}」（上下文：…{context}…）",
                    source_line=source_line,
                    suggestion="请将位置性指代改为显式编号引用，"
                    "如「图X-Y」「表X-Y」",
                )
            )
            # 登记位置性指代到 xref_registry
            document_ir.xref_registry.append(
                XRefMention(
                    ref_id=pos_word,
                    ref_type="figure" if "图" in pos_word else "table",
                    mention_line=source_line,
                    style="positional",
                )
            )

        # 孤立图引用行检测（仅 ParagraphIR，且前后紧邻块均非图片块）
        if isinstance(el, ParagraphIR) and _RE_ORPH.match(text):
            prev_is_fig = (i > 0 and isinstance(
                document_ir.elements[i - 1], FigureIR
            ))
            next_is_fig = (
                i + 1 < len(document_ir.elements)
                and isinstance(document_ir.elements[i + 1], FigureIR)
            )
            if not prev_is_fig and not next_is_fig:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-REF-03",
                        stage="validate",
                        message=f"疑似孤立图引用行（前后无图片块，"
                        f"可能为占位残留）：{text[:60]!r}",
                        source_line=source_line,
                        suggestion="若该行确为图片说明，请用正确的 "
                        "![图X-Y 标题](路径) 语法替换",
                    )
                )

    # ---- 交叉校验：实体表中的每个条目是否有引用 ----
    # 合并 figure + table 实体
    all_entities: dict[str, tuple[str, int, int, int]] = {}
    # key → (ref_type, X, Y, source_line)
    for fid, (fig, elem_idx, src_line) in figure_entities.items():
        x, y = fig.chapter_no, fig.seq_no
        all_entities[fid] = ("figure", x, y, src_line)
    for tid, (tbl, elem_idx, src_line) in table_entities.items():
        parts = tid.split("-")
        try:
            x, y = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            continue
        all_entities[tid] = ("table", x, y, src_line)

    for ent_id, (ref_type, x, y, src_line) in all_entities.items():
        key = (ref_type, x, y)
        mentions = refs.get(key, [])

        if not mentions:
            # W-REF-01：从未被引用
            type_cn = "图" if ref_type == "figure" else "表"
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-REF-01",
                    stage="validate",
                    message=f"{type_cn}{x}-{y}（行{src_line}）从未在正文中"
                    f"被引用",
                    source_line=src_line,
                    element_ref=f"{type_cn}{x}-{y}",
                    suggestion=f"请确认该{type_cn}是否需要保留，"
                    f"或补充正文引用",
                )
            )
        elif min(mentions) > src_line:
            # W-REF-02：先见图后见文
            type_cn = "图" if ref_type == "figure" else "表"
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-REF-02",
                    stage="validate",
                    message=f"先见图后见文：{type_cn}{x}-{y}位于行{src_line}，"
                    f"首次正文引用在行{min(mentions)}",
                    source_line=src_line,
                    element_ref=f"{type_cn}{x}-{y}",
                    suggestion=f"建议在{type_cn}{x}-{y}之前添加正文引用",
                )
            )

    # ---- 孤立引用：refs 中存在但实体表中不存在的编号 ----
    for (ref_type, x, y), mentions in refs.items():
        # 检查实体表中是否存在
        # 实体表 key 格式为 figure_id ("1-1") 或 table_id ("2-1")
        entity_key = f"{x}-{y}"
        type_cn = "图" if ref_type == "figure" else "表"
        display_ref = f"{type_cn}{x}-{y}"

        if ref_type == "figure":
            exists = entity_key in figure_entities
        else:
            exists = entity_key in table_entities

        if not exists:
            for mention_line in mentions:
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-REF-03",
                        stage="validate",
                        message=f"正文引用了不存在的{type_cn}编号："
                        f"{display_ref}（行{mention_line}）",
                        source_line=mention_line,
                        element_ref=display_ref,
                        suggestion="请检查引用编号是否正确，"
                        "或补充对应的图表",
                    )
                )


# ---------------------------------------------------------------------------
# 6. 密级字样兜底扫描（清理层第二道闸）
# ---------------------------------------------------------------------------


def _check_secrecy_keywords(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """对 elements 中全部文本段落做密级关键词兜底扫描。

    使用与 clean.py R-09弱 相同的词表。阶段4 仅警告——真正的 FATAL 拦截在门3
    （E-SEC-01）。此处检出残留说明 clean.py 的规则存在缺口。

    词表来源：config.py SECRECY_WORDS_WEAK → R-09弱正则。
    """
    for el in document_ir.elements:
        if not isinstance(el, (ParagraphIR, ListBlockIR, QuoteIR)):
            continue

        text = _extract_element_text(el)
        source_line = _get_element_source_line(el)

        for m in _SECRECY_WEAK_RE.finditer(text):
            keyword = m.group()
            # 获取上下文 ±20 字
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            context = text[start:end].replace("\n", " ")
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-CLN-01",
                    stage="validate",
                    message=f"密级兜底扫描命中：关键词 {keyword!r}"
                    f"（上下文：…{context}…）",
                    source_line=source_line,
                    suggestion="该密级词在 clean.py 清理阶段未被过滤，"
                    "说明清理规则可能存在缺口，请人工复核",
                    needs_review=True,
                )
            )


# ---------------------------------------------------------------------------
# 7. title_short 合理性
# ---------------------------------------------------------------------------


def _check_title_short(document_ir: DocumentIR, issues: IssueCollector) -> None:
    """若 metadata.title_short 为 None 或空，建议指定页眉简称。"""
    title_short = document_ir.metadata.title_short
    if not title_short:
        issues.append(
            Issue(
                level=Level.WARNING,
                stage="validate",
                code="",
                message="页眉简称（title_short）未指定，"
                "页眉将为空。建议在 md 元数据中补充「**页眉简称**：xxx」字段，"
                "或通过 CLI 指定",
                suggestion="在 md 头部 YAML/字段块中添加 title_short，"
                "或通过 --title-short 参数指定",
            )
        )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _extract_element_text(el: ParagraphIR | ListBlockIR | QuoteIR) -> str:
    """从段落/列表/引用块中提取纯文本（拼接所有 InlineRun.text）。

    用于正则扫描，不保留格式信息。
    """
    if isinstance(el, ParagraphIR) or isinstance(el, QuoteIR):
        return "".join(run.text for run in el.runs)
    elif isinstance(el, ListBlockIR):
        parts: list[str] = []
        for item in el.items:
            parts.append("".join(run.text for run in item))
        return " ".join(parts)
    return ""


def _get_element_source_line(
    el: ParagraphIR | ListBlockIR | QuoteIR | FigureIR | TableIR | HeadingIR,
) -> int:
    """获取任意 IR 元素的 source_line。"""
    return el.source_line


def _build_element_chapter_map(
    document_ir: DocumentIR,
) -> dict[int, int]:
    """构建 元素id → 所属章序 的映射。

    遍历 elements，跟踪当前章号（由 CHAPTER 类 HeadingIR 设定），
    将每个元素分配到其所属的章。返回 {id(element): chapter_no}。
    """
    result: dict[int, int] = {}
    current_chapter: int | None = None

    for el in document_ir.elements:
        if isinstance(el, HeadingIR) and el.kind == HeadingKind.CHAPTER:
            if isinstance(el.number, int):
                current_chapter = el.number

        if current_chapter is not None and isinstance(
            el, (FigureIR, TableIR, ParagraphIR, ListBlockIR)
        ):
            result[id(el)] = current_chapter

    return result
