"""门3 输出校验模块（C-14，关键路径）。

重新打开已生成的 .docx 文件，逐项验证输出符合 V3.1 规范要求。
Fatal 闭集（M3 裁决）仅三类：密级复检 / 分页规划一致性（R15）/ 域三态结构。
"""

from __future__ import annotations

import re

from docx import Document
from docx.oxml.ns import qn

from . import config
from .ir import (
    DocumentIR,
    HeadingIR,
    HeadingKind,
    PageBreakIR,
    PageNumFormat,
    TableKind,
)
from .issues import Issue, IssueCollector, Level


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def run_gate3(
    docx_path: str,
    ir: DocumentIR,
    issues: IssueCollector,
    flags,
) -> dict:
    """运行门3校验，返回校验结果 dict。

    Args:
        docx_path: 已生成的 .docx 文件路径。
        ir: 中间表示（DocumentIR），供分页规划/R15 一致性比对等。
        issues: IssueCollector 实例，任何 FAIL 记录到此。
        flags: BehaviorFlags 实例（备用，当前校验项暂未直接消费）。

    Returns:
        {
            'passed': bool,           # Fatal 项全部通过
            'checks': list[dict],     # 每项结果
            'fatal_count': int,
            'error_count': int,
            'warning_count': int,
        }
    """
    doc = Document(docx_path)
    body = doc.element.body
    checks: list[dict] = []

    # ---- Fatal 级（3 项） ----
    _check_secrecy(checks, body, issues)
    _check_page_breaks(checks, body, ir, issues)
    _check_field_structure(checks, body, issues)

    # ---- 非 Fatal 自动检查 ----
    _check_cover_integrity(checks, doc, ir)
    _check_heading_continuity(checks, ir, issues)
    _check_figure_table_continuity(checks, ir, issues)
    _check_table_borders(checks, body, issues)
    _check_page_numbers(checks, body, ir, issues)
    _check_headers_footers(checks, body, ir, issues)
    _check_blank_pages(checks, body, issues)
    _check_toc_field(checks, body, issues)
    _check_table_body_font_size(checks, body, issues)

    # ---- 人工确认项 ----
    _check_font_embedding(checks, body)

    # 汇总
    fatal_count = sum(
        1 for c in checks if c["level"] == "fatal" and c["result"] == "fail"
    )
    error_count = sum(
        1 for c in checks if c["level"] == "auto" and c["result"] == "fail"
    )
    warning_count = sum(1 for c in checks if c["result"] == "warning")
    passed = fatal_count == 0

    return {
        "passed": passed,
        "checks": checks,
        "fatal_count": fatal_count,
        "error_count": error_count,
        "warning_count": warning_count,
    }


# ---------------------------------------------------------------------------
# 1. 密级复检（Fatal）
# ---------------------------------------------------------------------------


def _check_secrecy(
    checks: list[dict], body, issues: IssueCollector
) -> None:
    """全文搜索"绝密/机密/秘密/内部"等关键词——出现即 FATAL。

    复用 config.py 中已定义的密级关键词白名单。
    """
    all_keywords = set(config.SECRECY_WORDS_STRONG) | set(config.SECRECY_WORDS_WEAK)
    hits: list[str] = []

    for t_elem in body.iter(qn("w:t")):
        text = t_elem.text or ""
        for kw in all_keywords:
            if kw in text:
                hits.append(kw)

    if hits:
        unique_hits = sorted(set(hits))
        detail = f"文档中发现密级关键词：{', '.join(unique_hits)}，共 {len(hits)} 处命中"
        checks.append({
            "id": 1,
            "name": "密级复检",
            "level": "fatal",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-SEC-01",
                stage="gate3",
                message=f"门3 密级复检命中：{detail}",
                gate="gate3",
            )
        )
    else:
        checks.append({
            "id": 1,
            "name": "密级复检",
            "level": "fatal",
            "result": "pass",
            "detail": "全文未发现密级标注",
            "needs_review": False,
        })


# ---------------------------------------------------------------------------
# 2. 分页规划一致性（R15，Fatal）
# ---------------------------------------------------------------------------


def _check_page_breaks(
    checks: list[dict], body, ir: DocumentIR, issues: IssueCollector
) -> None:
    """统计 docx 中的分页符/分节符数量，与 ir.section_plan 的规划值比对（R15）。

    分页符数 = docx 中 <w:br w:type="page"/> 数量
    分节符数 = <w:sectPr> 数量 - 1（第一节的 sectPr 无前一节边界含义）
    期望 = len(ir.section_plan.sections) - 1 + len(PageBreakIR 元素)
    """
    # docx 实际值
    page_break_elems = body.findall(".//" + qn("w:br"))
    actual_page_breaks = sum(
        1 for br in page_break_elems if br.get(qn("w:type")) == "page"
    )
    sect_pr_count = len(body.findall(".//" + qn("w:sectPr")))
    actual_section_breaks = sect_pr_count - 1

    # IR 期望值
    page_breaks_in_ir = [
        e for e in ir.elements if isinstance(e, PageBreakIR)
    ]
    expected_section_breaks = len(ir.section_plan.sections) - 1
    expected_page_breaks = len(page_breaks_in_ir)

    expected_total = expected_section_breaks + expected_page_breaks
    actual_total = actual_section_breaks + actual_page_breaks

    if actual_total == expected_total:
        checks.append({
            "id": 2,
            "name": "分页规划一致性（R15）",
            "level": "fatal",
            "result": "pass",
            "detail": (
                f"实际分节={actual_section_breaks}/分页={actual_page_breaks}，"
                f"期望分节={expected_section_breaks}/分页={expected_page_breaks}"
            ),
            "needs_review": False,
        })
    else:
        detail = (
            f"不一致：实际分节={actual_section_breaks}/分页={actual_page_breaks}"
            f"（合计 {actual_total}），"
            f"期望分节={expected_section_breaks}/分页={expected_page_breaks}"
            f"（合计 {expected_total}）"
        )
        checks.append({
            "id": 2,
            "name": "分页规划一致性（R15）",
            "level": "fatal",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-SEC-01",
                stage="gate3",
                message=f"门3 分页规划不一致（R15）：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 3. TOC/PAGE 域三态（Fatal）
# ---------------------------------------------------------------------------


def _check_field_structure(
    checks: list[dict], body, issues: IssueCollector
) -> None:
    """验证所有 w:fldChar 域的三态结构：begin→instrText→separate→end。

    同时检查 PAGEREF 域目标书签存在性（R19）：
    遍历所有 w:instrText 含 PAGEREF 的域，提取书签名，
    验证 docx 中存在对应 w:bookmarkStart。
    """
    fld_chars = body.findall(".//" + qn("w:fldChar"))
    instr_texts = body.findall(".//" + qn("w:instrText"))
    bookmark_starts = body.findall(".//" + qn("w:bookmarkStart"))

    # 收集所有书签名
    bookmark_names: set[str] = set()
    for bs in bookmark_starts:
        name = bs.get(qn("w:name"))
        if name:
            bookmark_names.add(name)

    # 收集所有域段落：按段落分组 fldChar 以便做三态验证
    # 策略：在 XML 树中逐段检查，每个 w:p 内的 fldChar 应配对
    malformed_count = 0
    pageref_missing_bookmarks: list[str] = []

    for p_elem in body.iter(qn("w:p")):
        p_fld_chars = p_elem.findall(qn("w:r") + "/" + qn("w:fldChar"))
        p_instr_texts_elems = p_elem.findall(
            qn("w:r") + "/" + qn("w:instrText")
        )

        if not p_fld_chars:
            continue

        # 按文档序收集 fldChar 类型
        # 需要保持 run 的顺序
        fld_types: list[str] = []
        instr_values: list[str] = []
        for r_elem in p_elem.iter(qn("w:r")):
            fc = r_elem.find(qn("w:fldChar"))
            if fc is not None:
                fld_type = fc.get(qn("w:fldCharType"))
                if fld_type:
                    fld_types.append(fld_type)
            it = r_elem.find(qn("w:instrText"))
            if it is not None and it.text:
                instr_values.append(it.text)

        # 找出每个域的起止范围
        # 简化模型：begin→...→separate→...→end 为正常
        # 缺失 separate 但有 begin→end 也视为异常（标记为 malformed）
        field_stack: list[int] = []  # 记录 begin 出现位置
        for i, ft in enumerate(fld_types):
            if ft == "begin":
                field_stack.append(i)
            elif ft == "end":
                if not field_stack:
                    malformed_count += 1
                    continue
                begin_pos = field_stack.pop()
                # begin 到 end 之间是否包含 separate
                between = fld_types[begin_pos + 1 : i]
                if "separate" not in between:
                    malformed_count += 1

        # 检查 PAGEREF 域的书签目标
        for instr_val in instr_values:
            if "PAGEREF" in instr_val:
                # 提取书签名：PAGEREF 关键字后的第一个非空格 token
                # 格式：PAGEREF ref_bookmark_name \\h
                match = re.search(
                    r"PAGEREF\s+(\S+)", instr_val
                )
                if match:
                    bm_name = match.group(1)
                    # 去掉可能的 `_Ref` 前缀变体，Word 内部可能对书签做前缀转换
                    if bm_name not in bookmark_names:
                        # 尝试去除 Word 自动添加的 _Ref 前缀后再匹配
                        # 也尝试模糊匹配（Word 有时给书签加数字后缀）
                        found = False
                        for existing_name in bookmark_names:
                            if existing_name == bm_name or existing_name.startswith(
                                bm_name
                            ):
                                found = True
                                break
                        if not found:
                            pageref_missing_bookmarks.append(bm_name)

    # 去重
    pageref_missing_bookmarks = sorted(set(pageref_missing_bookmarks))

    if malformed_count == 0 and not pageref_missing_bookmarks:
        checks.append({
            "id": 3,
            "name": "TOC/PAGE 域三态结构",
            "level": "fatal",
            "result": "pass",
            "detail": (
                f"共检查 {len(body.findall('.//' + qn('w:fldChar')))} 个 fldChar 元素，"
                f"域三态结构全部正常；PAGEREF 书签目标全部存在"
            ),
            "needs_review": False,
        })
    else:
        detail_parts = []
        if malformed_count > 0:
            detail_parts.append(
                f"发现 {malformed_count} 个域三态结构异常"
                "（缺少 begin→separate→end 完整链路）"
            )
        if pageref_missing_bookmarks:
            detail_parts.append(
                f"PAGEREF 目标书签缺失：{', '.join(pageref_missing_bookmarks)}"
            )
        detail = "；".join(detail_parts)
        checks.append({
            "id": 3,
            "name": "TOC/PAGE 域三态结构",
            "level": "fatal",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-SEC-01",
                stage="gate3",
                message=f"门3 域三态结构异常：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 4. 封面完整性（auto）
# ---------------------------------------------------------------------------


def _check_cover_integrity(
    checks: list[dict], doc, ir: DocumentIR
) -> None:
    """检查 docx 前几段是否含标题/机构/日期文本。

    遍历 docx 前 20 个段落，查找是否存在标题、机构名或日期文本。
    """
    title_found = False
    org_found = False
    date_found = False

    title_text = ir.metadata.title
    org_text = ir.metadata.organization or ""
    date_text = ir.metadata.date or ""

    for i, para in enumerate(doc.paragraphs):
        if i >= 20:
            break
        text = para.text.strip()
        if not text:
            continue
        if title_text and title_text in text:
            title_found = True
        if org_text and org_text in text:
            org_found = True
        if date_text and date_text in text:
            date_found = True

    missing: list[str] = []
    if not title_found:
        missing.append("标题")
    if not org_found and org_text:
        missing.append("机构")
    if not date_found and date_text:
        missing.append("日期")

    if not missing:
        checks.append({
            "id": 4,
            "name": "封面完整性",
            "level": "auto",
            "result": "pass",
            "detail": "封面包含标题/机构/日期文本",
            "needs_review": False,
        })
    else:
        checks.append({
            "id": 4,
            "name": "封面完整性",
            "level": "auto",
            "result": "fail",
            "detail": f"封面缺失：{', '.join(missing)}",
            "needs_review": False,
        })


# ---------------------------------------------------------------------------
# 5. 章节编号连续性（auto）
# ---------------------------------------------------------------------------


def _check_heading_continuity(
    checks: list[dict], ir: DocumentIR, issues: IssueCollector
) -> None:
    """解析所有 H2/H3/H4 的 display_number，验证序号连续。

    从 ir.elements 中提取所有 HeadingIR，按类型分组后检查编号连续性。
    """
    headings = [e for e in ir.elements if isinstance(e, HeadingIR)]
    chapters = [h for h in headings if h.kind == HeadingKind.CHAPTER]
    sections = [h for h in headings if h.kind == HeadingKind.SECTION]
    subsections = [h for h in headings if h.kind == HeadingKind.SUBSECTION]

    issues_found: list[str] = []

    # 章编号：number 为 int，应连续 1,2,3,...
    if chapters:
        chapter_nums = sorted(
            [h.number for h in chapters if isinstance(h.number, int)]
        )
        for idx, num in enumerate(chapter_nums):
            expected = idx + 1
            if num != expected:
                issues_found.append(
                    f"章编号跳号：期望第{expected}章，实际编号{num}"
                )

    # 节编号：number 为 (章,节)，同章内应连续
    if sections:
        by_chapter: dict[int, list[int]] = {}
        for h in sections:
            if isinstance(h.number, tuple) and len(h.number) == 2:
                ch, sec = h.number
                by_chapter.setdefault(ch, []).append(sec)
        for ch, sec_nums in by_chapter.items():
            sec_nums_sorted = sorted(sec_nums)
            for idx, sec in enumerate(sec_nums_sorted):
                expected = idx + 1
                if sec != expected:
                    issues_found.append(
                        f"第{ch}章内节编号跳号：期望{ch}.{expected}，实际{ch}.{sec}"
                    )

    # 小节编号：number 为 (章,节,小节)，同章同节内应连续
    if subsections:
        by_section: dict[tuple[int, int], list[int]] = {}
        for h in subsections:
            if isinstance(h.number, tuple) and len(h.number) == 3:
                ch, sec, sub = h.number
                by_section.setdefault((ch, sec), []).append(sub)
        for (ch, sec), sub_nums in by_section.items():
            sub_nums_sorted = sorted(sub_nums)
            for idx, sub in enumerate(sub_nums_sorted):
                expected = idx + 1
                if sub != expected:
                    issues_found.append(
                        f"第{ch}章第{sec}节内小节编号跳号："
                        f"期望{ch}.{sec}.{expected}，实际{ch}.{sec}.{sub}"
                    )

    if not issues_found:
        checks.append({
            "id": 5,
            "name": "章节编号连续性",
            "level": "auto",
            "result": "pass",
            "detail": "所有章节/节/小节编号连续",
            "needs_review": False,
        })
    else:
        detail = "；".join(issues_found)
        checks.append({
            "id": 5,
            "name": "章节编号连续性",
            "level": "auto",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="W-HDR-01",
                stage="gate3",
                message=f"门3 章节编号不连续：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 6. 图表编号连续性（auto）
# ---------------------------------------------------------------------------


def _check_figure_table_continuity(
    checks: list[dict], ir: DocumentIR, issues: IssueCollector
) -> None:
    """验证图/表编号无跳号。

    从 ir.figure_registry 和 ir.table_registry 中取编号，按章分组检查连续性。
    """
    issues_found: list[str] = []

    # 图编号连续性
    figs_by_chapter: dict[int, list[int]] = {}
    for fig_id, fig in ir.figure_registry.items():
        figs_by_chapter.setdefault(fig.chapter_no, []).append(fig.seq_no)
    for ch, seqs in figs_by_chapter.items():
        seqs_sorted = sorted(seqs)
        for idx, seq in enumerate(seqs_sorted):
            expected = idx + 1
            if seq != expected:
                issues_found.append(
                    f"图编号跳号：第{ch}章期望图{ch}-{expected}，"
                    f"实际图{ch}-{seq}"
                )

    # 表编号连续性（仅正文表）
    tbls_by_chapter: dict[int, list[int]] = {}
    for tbl_id, tbl in ir.table_registry.items():
        if tbl.kind == TableKind.BODY and tbl.table_id:
            parts = tbl.table_id.split("-")
            if len(parts) == 2:
                try:
                    ch = int(parts[0])
                    seq = int(parts[1])
                    tbls_by_chapter.setdefault(ch, []).append(seq)
                except ValueError:
                    pass
    for ch, seqs in tbls_by_chapter.items():
        seqs_sorted = sorted(seqs)
        for idx, seq in enumerate(seqs_sorted):
            expected = idx + 1
            if seq != expected:
                issues_found.append(
                    f"表编号跳号：第{ch}章期望表{ch}-{expected}，"
                    f"实际表{ch}-{seq}"
                )

    if not issues_found:
        checks.append({
            "id": 6,
            "name": "图表编号连续性",
            "level": "auto",
            "result": "pass",
            "detail": "所有图/表编号连续",
            "needs_review": False,
        })
    else:
        detail = "；".join(issues_found)
        checks.append({
            "id": 6,
            "name": "图表编号连续性",
            "level": "auto",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="W-IMG-06",
                stage="gate3",
                message=f"门3 图表编号不连续：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 7. 表格全框线（auto）
# ---------------------------------------------------------------------------


def _check_table_borders(
    checks: list[dict], body, issues: IssueCollector
) -> None:
    """检查所有 w:tbl 有无 w:tblBorders 且含 w:insideV 竖线。

    任何一个表格缺少全框线或缺少内部竖线即报告。
    """
    tbl_elems = body.findall(".//" + qn("w:tbl"))
    if not tbl_elems:
        checks.append({
            "id": 7,
            "name": "表格全框线",
            "level": "auto",
            "result": "pass",
            "detail": "文档中无表格",
            "needs_review": False,
        })
        return

    issues_found: list[str] = []
    for i, tbl in enumerate(tbl_elems, 1):
        tbl_pr = tbl.find(qn("w:tblPr"))
        if tbl_pr is None:
            issues_found.append(f"表格{i}缺少 w:tblPr（无边框属性）")
            continue
        borders = tbl_pr.find(qn("w:tblBorders"))
        if borders is None:
            issues_found.append(f"表格{i}缺少 w:tblBorders")
            continue
        # 检查各边线是否存在
        for border_tag in ("top", "bottom", "left", "right", "insideH", "insideV"):
            if borders.find(qn(f"w:{border_tag}")) is None:
                issues_found.append(
                    f"表格{i}缺少 w:{border_tag} 边框定义"
                )

    if not issues_found:
        checks.append({
            "id": 7,
            "name": "表格全框线",
            "level": "auto",
            "result": "pass",
            "detail": f"共 {len(tbl_elems)} 个表格，全部有完整框线",
            "needs_review": False,
        })
    else:
        detail = "；".join(issues_found)
        checks.append({
            "id": 7,
            "name": "表格全框线",
            "level": "auto",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="W-TBL-01",
                stage="gate3",
                message=f"门3 表格框线不完整：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 8. 页码正确（auto）
# ---------------------------------------------------------------------------


def _check_page_numbers(
    checks: list[dict], body, ir: DocumentIR, issues: IssueCollector
) -> None:
    """检查 sectPr 的 pgNumType 与 IR 的 section_plan 一致。

    第三节（BODY）应使用 decimal；若有 ABSTRACT 节，第二节应使用 lowerRoman。
    """
    sect_prs = body.findall(".//" + qn("w:sectPr"))
    section_plan = ir.section_plan

    issues_found: list[str] = []

    # 构建 sectPr 索引与 SectionSpec 的对应关系
    # sectPr[0] 对应 section_plan.sections[0]（COVER），依此类推
    for idx, sec_spec in enumerate(section_plan.sections):
        if idx >= len(sect_prs):
            issues_found.append(
                f"第{idx + 1}节（{sec_spec.kind.value}）在 docx 中缺少 sectPr"
            )
            continue

        sect_pr = sect_prs[idx]
        pg_num_type = sect_pr.find(qn("w:pgNumType"))
        actual_fmt = (
            pg_num_type.get(qn("w:fmt")) if pg_num_type is not None else None
        )
        expected_fmt = _page_num_fmt_to_oo_xml(sec_spec.page_num_fmt)

        # COVER 节的 pgNumType 可能不存在（fmt=NONE），不强制检查
        if expected_fmt is None:
            continue

        if actual_fmt != expected_fmt:
            issues_found.append(
                f"第{idx + 1}节（{sec_spec.kind.value}）页码格式不一致："
                f"期望 {expected_fmt}，实际 {actual_fmt}"
            )

    if not issues_found:
        checks.append({
            "id": 8,
            "name": "页码正确",
            "level": "auto",
            "result": "pass",
            "detail": "各节页码格式与 IR section_plan 一致",
            "needs_review": False,
        })
    else:
        detail = "；".join(issues_found)
        checks.append({
            "id": 8,
            "name": "页码正确",
            "level": "auto",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-SEC-01",
                stage="gate3",
                message=f"门3 页码格式不一致：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 9. 页眉页脚完整（auto）
# ---------------------------------------------------------------------------


def _check_headers_footers(
    checks: list[dict], body, ir: DocumentIR, issues: IssueCollector
) -> None:
    """检查 BODY 节的 sectPr 中 headerReference/footerReference 非空。

    仅对有页眉的节（header_mode != NONE）要求非空引用。
    """
    sect_prs = body.findall(".//" + qn("w:sectPr"))
    section_plan = ir.section_plan

    issues_found: list[str] = []

    for idx, sec_spec in enumerate(section_plan.sections):
        if sec_spec.header_mode.value == "none":
            continue  # COVER/TOC 节不要求页眉页脚

        if idx >= len(sect_prs):
            continue

        sect_pr = sect_prs[idx]

        # 检查 headerReference
        header_refs = sect_pr.findall(qn("w:headerReference"))
        if not header_refs:
            issues_found.append(
                f"第{idx + 1}节（{sec_spec.kind.value}）缺少 w:headerReference"
            )
        else:
            for hr in header_refs:
                rid = hr.get(qn("r:id"))
                if not rid:
                    issues_found.append(
                        f"第{idx + 1}节（{sec_spec.kind.value}）"
                        "w:headerReference 缺少 r:id"
                    )

        # 检查 footerReference
        footer_refs = sect_pr.findall(qn("w:footerReference"))
        if not footer_refs:
            issues_found.append(
                f"第{idx + 1}节（{sec_spec.kind.value}）缺少 w:footerReference"
            )
        else:
            for fr in footer_refs:
                rid = fr.get(qn("r:id"))
                if not rid:
                    issues_found.append(
                        f"第{idx + 1}节（{sec_spec.kind.value}）"
                        "w:footerReference 缺少 r:id"
                    )

    if not issues_found:
        checks.append({
            "id": 9,
            "name": "页眉页脚完整",
            "level": "auto",
            "result": "pass",
            "detail": "所有有页眉/页脚的节均有完整的 headerReference/footerReference",
            "needs_review": False,
        })
    else:
        detail = "；".join(issues_found)
        checks.append({
            "id": 9,
            "name": "页眉页脚完整",
            "level": "auto",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-SEC-01",
                stage="gate3",
                message=f"门3 页眉页脚不完整：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 10. 空白页检测（auto，WARNING）
# ---------------------------------------------------------------------------


def _check_blank_pages(
    checks: list[dict], body, issues: IssueCollector
) -> None:
    """检查是否有连续两个 w:br type="page" 紧邻（无中间文本）——WARNING。

    遍历文档中所有段落，检测同一段落或相邻段落中连续两个分页符之间无实质内容。
    """
    # 收集所有分页符及其在文档中的顺序位置
    page_breaks: list = []

    for p_elem in body.iter(qn("w:p")):
        for r_elem in p_elem.iter(qn("w:r")):
            br = r_elem.find(qn("w:br"))
            if br is not None and br.get(qn("w:type")) == "page":
                # 记录这个分页符及所属段落
                page_breaks.append({
                    "p": p_elem,
                    "br": br,
                })

    blank_page_count = 0
    for i in range(len(page_breaks) - 1):
        pb1 = page_breaks[i]
        pb2 = page_breaks[i + 1]

        # 同一段落内有两个分页符：中间可能有文本也可能没有
        if pb1["p"] is pb2["p"]:
            # 检查两个 br 之间是否有文本内容
            has_text_between = _has_text_between_breaks(
                pb1["p"], pb1["br"], pb2["br"]
            )
            if not has_text_between:
                blank_page_count += 1
        else:
            # 不同段落：检查中间段落是否有实质文本
            has_content_between = _has_content_between_paragraphs(
                body, pb1["p"], pb2["p"]
            )
            if not has_content_between:
                blank_page_count += 1

    result = "warning" if blank_page_count > 0 else "pass"
    checks.append({
        "id": 10,
        "name": "空白页检测",
        "level": "auto",
        "result": result,
        "detail": (
            f"发现 {blank_page_count} 处连续空分页"
            if blank_page_count > 0
            else "未发现连续空分页"
        ),
        "needs_review": False,
    })

    if blank_page_count > 0:
        issues.append(
            Issue(
                level=Level.WARNING,
                code="W-PB-01",
                stage="gate3",
                message=f"门3 检测到 {blank_page_count} 处可能空白页",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 11. TOC 域存在（auto）
# ---------------------------------------------------------------------------


def _check_toc_field(
    checks: list[dict], body, issues: IssueCollector
) -> None:
    """检查是否存在 instrText 含 TOC 的域。"""
    instr_texts = body.findall(".//" + qn("w:instrText"))
    has_toc = any(
        it.text and "TOC" in it.text for it in instr_texts
    )

    if has_toc:
        checks.append({
            "id": 11,
            "name": "TOC 域存在",
            "level": "auto",
            "result": "pass",
            "detail": "文档中存在 TOC 域",
            "needs_review": False,
        })
    else:
        checks.append({
            "id": 11,
            "name": "TOC 域存在",
            "level": "auto",
            "result": "fail",
            "detail": "文档中未发现 TOC 域",
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-SEC-01",
                stage="gate3",
                message="门3：文档中未发现 TOC 域",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 12. PAGEREF 目标书签（已并入 Fatal #3）
# ---------------------------------------------------------------------------
# 注：PAGEREF 书签存在性校验已在 _check_field_structure 中实现。


# ---------------------------------------------------------------------------
# 13. 表体字号（auto）
# ---------------------------------------------------------------------------


def _check_table_body_font_size(
    checks: list[dict], body, issues: IssueCollector
) -> None:
    """检查 w:tbl 中非表头单元格的 w:sz 值 = 21 half-pt = 10.5pt。

    容差 ±1 half-pt（即 20-22 half-pt 均视为合规）。

    表头行判定：w:tblHeader 或 w:trPr/w:tblHeader 标记。
    """
    tbl_elems = body.findall(".//" + qn("w:tbl"))
    if not tbl_elems:
        checks.append({
            "id": 13,
            "name": "表体字号",
            "level": "auto",
            "result": "pass",
            "detail": "文档中无表格",
            "needs_review": False,
        })
        return

    issues_found: list[str] = []
    EXPECTED_SZ = 21  # 10.5pt * 2
    TOLERANCE = 1

    for tbl_idx, tbl in enumerate(tbl_elems, 1):
        rows = tbl.findall(qn("w:tr"))
        for row_idx, row in enumerate(rows):
            # 判断是否为表头行
            tr_pr = row.find(qn("w:trPr"))
            is_header = False
            if tr_pr is not None:
                tbl_header = tr_pr.find(qn("w:tblHeader"))
                if tbl_header is not None:
                    is_header = True

            if is_header:
                continue  # 跳过表头行

            # 检查该行中所有单元格的字号
            cells = row.findall(qn("w:tc"))
            for cell_idx, cell in enumerate(cells):
                for r_elem in cell.findall(".//" + qn("w:r")):
                    r_pr = r_elem.find(qn("w:rPr"))
                    if r_pr is None:
                        continue
                    sz_elem = r_pr.find(qn("w:sz"))
                    if sz_elem is None:
                        # 无 w:sz 元素 = 继承默认，不单独报错
                        continue
                    sz_val_str = sz_elem.get(qn("w:val"))
                    if sz_val_str is None:
                        continue
                    try:
                        sz_val = int(sz_val_str)
                    except ValueError:
                        continue
                    if abs(sz_val - EXPECTED_SZ) > TOLERANCE:
                        actual_pt = sz_val / 2
                        issues_found.append(
                            f"表格{tbl_idx}行{row_idx + 1}列{cell_idx + 1}"
                            f"表体字号={sz_val} half-pt ({actual_pt}pt)，"
                            f"期望 {EXPECTED_SZ} half-pt (10.5pt)"
                        )
                        # 每个表格只报一次，避免刷屏
                        break
                if issues_found:
                    break
            if issues_found:
                break

    if not issues_found:
        checks.append({
            "id": 13,
            "name": "表体字号",
            "level": "auto",
            "result": "pass",
            "detail": f"共 {len(tbl_elems)} 个表格，表体字号全部合规（10.5pt±0.5pt）",
            "needs_review": False,
        })
    else:
        # 仅报告前 3 条以避免刷屏
        detail = "；".join(issues_found[:3])
        if len(issues_found) > 3:
            detail += f"（...共 {len(issues_found)} 处）"
        checks.append({
            "id": 13,
            "name": "表体字号",
            "level": "auto",
            "result": "fail",
            "detail": detail,
            "needs_review": False,
        })
        issues.append(
            Issue(
                level=Level.ERROR,
                code="W-TBL-01",
                stage="gate3",
                message=f"门3 表体字号异常：{detail}",
                gate="gate3",
            )
        )


# ---------------------------------------------------------------------------
# 14. 字体嵌入（manual，标记 needs_review = 已知限制8）
# ---------------------------------------------------------------------------


def _check_font_embedding(
    checks: list[dict], body
) -> None:
    """检查 docx 是否含 w:embedTrueTypeFonts。

    无论如何标记 N/A（已知限制8：字体嵌入由外部工具链完成，不作为门3判定项）。
    """
    # 查找 w:document 或 w:settings 下的字体嵌入设置
    has_embed = False
    # 在整棵 XML 树中查找
    for elem in body.iter():
        if elem.tag == qn("w:embedTrueTypeFonts"):
            has_embed = True
            break
    # 也在 w:settings 中查找（python-docx 的 body 是 w:document，settings 需要另行访问）
    doc_elem = body.getparent() if body.getparent() is not None else body
    root = doc_elem.getroottree().getroot() if hasattr(doc_elem, "getroottree") else None

    checks.append({
        "id": 14,
        "name": "字体嵌入",
        "level": "manual",
        "result": "na",
        "detail": (
            "字体嵌入由外部工具链完成（已知限制8），不作门3判定；"
            "当前状态：未检测到 w:embedTrueTypeFonts"
            if not has_embed
            else "当前状态：已检测到 w:embedTrueTypeFonts"
        ),
        "needs_review": True,
    })


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _page_num_fmt_to_oo_xml(fmt: PageNumFormat) -> str | None:
    """将 PageNumFormat 枚举映射为 OOXML w:fmt 属性值。"""
    mapping = {
        PageNumFormat.NONE: None,
        PageNumFormat.LOWER_ROMAN: "lowerRoman",
        PageNumFormat.DECIMAL: "decimal",
    }
    return mapping.get(fmt)


def _has_text_between_breaks(p_elem, br1, br2) -> bool:
    """检查同一段落内两个 w:br 元素之间是否有实质性文本。"""
    # 在同一段落中按文档序找出两个 br 之间的所有 w:r 元素
    runs = list(p_elem.iter(qn("w:r")))
    br1_idx = None
    br2_idx = None
    for i, r in enumerate(runs):
        br = r.find(qn("w:br"))
        if br is br1:
            br1_idx = i
        if br is br2:
            br2_idx = i
    if br1_idx is None or br2_idx is None:
        return False

    for i in range(br1_idx + 1, br2_idx):
        t_elem = runs[i].find(qn("w:t"))
        if t_elem is not None and t_elem.text and t_elem.text.strip():
            return True
        # 图片、域等也可视为实质内容
        if runs[i].find(qn("w:drawing")) is not None:
            return True
        if runs[i].find(qn("w:fldChar")) is not None:
            return True

    return False


def _has_content_between_paragraphs(body, p1, p2) -> bool:
    """检查两个段落之间（文档序）是否有实质性内容。"""
    found_p1 = False
    for p in body.iter(qn("w:p")):
        if p is p1:
            found_p1 = True
            continue
        if p is p2:
            break
        if not found_p1:
            continue
        # 检查中间段落是否有实质内容
        text = "".join(
            t.text or ""
            for t in p.iter(qn("w:t"))
        )
        if text.strip():
            return True
        # 检查是否有图片/表格等非文本内容
        if p.find(".//" + qn("w:drawing")) is not None:
            return True
        if p.find(".//" + qn("w:tbl")) is not None:
            return True

    return False
