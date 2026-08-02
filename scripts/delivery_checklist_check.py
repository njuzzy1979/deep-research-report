#!/usr/bin/env python3
"""阶段 9 交付清单聚合检查脚本（跨模型兼容性优化方案 §五 D6）。

职责边界（务必读完）：本脚本是**聚合调用器**，不重新实现任何检查逻辑——
逐项复用已有脚本（`contract_check.py` / `term_consistency_check.py` /
`convert_references.py` / `figure_gate.py` / `degradation_report.py`），
汇总为 JSON + exit code。方案 §D6 原文："新增 `scripts/delivery_checklist_check.py`：
作为聚合调用器，不重新实现检查逻辑，依次调用上述已有脚本，汇总 JSON + exit code。"

13 项清单构成（12 项交付清单 + degradation_report 的第 13 项，见方案 §D1
"G(交付)" 行："12 项 → 13 项清单"）：

  10 项可脚本化：
    01 术语一致性                  —— term_consistency_check.run_check()
    02 引用格式 + 无分级前缀        —— contract_check C6 + C10
    03 参考文献去重与一一对应       —— 对合并终稿正文做 SRC_REF_PATTERN 存在性检测
       （代理指标：合并终稿中不再残留 [SRC-XXX]，说明 convert_references.py
        的 OrderedDict 去重转换已完成；本项不重新实现去重算法。只检测合并
        终稿本身，不检测原始分章草稿目录——原始分章文件按设计永远不会被
        回写转换结果，检测它等于检测一个恒定包含 [SRC-XXX] 的目录）
    04 图表编号统一                —— figure_gate.run_figure_gate() + C3/C4
    05 输出隔离标记剥离             —— contract_check C5（含 F1 标记残留）
    06 写作者自声明剥离             —— 本地正则（与 clean.py R-12 逐字一致）
    07 红队批注剥离                —— 本地正则（与 clean.py R-14 逐字一致）
    08 字数统计残留                —— contract_check C8
    09 局部参考文献                —— contract_check C9
    10 交叉引用一致（部分）         —— 本地正则（与 paragraphs.py _RE_XREF 逐字
       一致），仅做存在性/格式校验，语义指对与否仍需人工抽查（方案原文）

  03 的配套项（新增，非原 13 项之一，紧邻 03 之后）：
    03b 参考文献一一对应完整性     —— 正文唯一 [N] 引用编号集合与参考文献
       条目编号集合的完整性比对（存在性/编号断裂/孤儿条目），不依赖
       source-index.csv。与 03 职责边界：03 只做"[SRC-XXX] 残留"代理指标，
       03b 做"参考文献章节是否存在 + 编号是否一一对应"的实质性检测

  2 项不可脚本化（显式标记为 manual_required，**不能**静默跳过或标记为 pass）：
    11 红队风险清单处理确认         —— 需人工核对 research/redteam-resolution-diff.md
    12 全文通读                    —— 强制人在环，orchestrator 不得自行宣称已完成

  第 13 项（方案 §D1 "G(交付)" 行明确要求纳入）：
    13 降级台账确认                —— degradation_report.summarize()，
       未确认 L-显著事件 → 阻断

关键实现约束（三处 sys.exit 陷阱，均已规避——见方案调研结论）：
  - `convert_references.load_source_index()` 在 CSV 缺失/格式错误时直接
    `sys.exit(2)`——本脚本不调用该函数（03 直接对 merged_text 做正则检测，
    不读 source-index.csv）。
  - `term_consistency_check.run_check()` 本身无 sys.exit 但也无 try/except
    包裹内部调用——本脚本调用时自行包裹 try/except。
  - `figure_gate.py` 顶部对 PIL/PyYAML 的 import 失败会在**模块导入阶段**
    直接 `sys.exit(1)`——本脚本用 `importlib.util.find_spec` 预检测，不可用
    时该项降级为 skipped，不拖垮整个聚合脚本。

用法：
    python scripts/delivery_checklist_check.py <merged_file.md>
    python scripts/delivery_checklist_check.py <merged_file.md> --json \\
        --glossary research/glossary.md --drafts-dir research/drafts \\
        --outline research/outline.md --figures-dir research/figures \\
        --redteam-diff research/redteam-resolution-diff.md

退出码：0 = 10 项可脚本化项全部通过（manual_required 项不计入自动判定，
           仍需人工在 CP6 确认）；
       1 = 至少一项可脚本化检查失败；
       2 = merged_file 不存在 / 执行过程中抛出未预期异常。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py:42-48 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"
MANUAL_REQUIRED = "manual_required"

# ---------------------------------------------------------------------------
# 函数级 import 复用（不重新实现检查逻辑，见模块 docstring）
# ---------------------------------------------------------------------------

# contract_check.py 是核心复用对象，硬依赖（与 degradation_report.py 对
# degradation_log.py 的硬依赖同一先例）——两者同处 scripts/ 目录，缺失即
# 视为环境损坏，不做容错兜底。
from contract_check import check_contract, read_text

# term_consistency_check.run_check() 本身无 sys.exit 也无 try/except 包裹，
# 本脚本在调用处自行包裹（见 check_term_consistency）。import 本身容错。
try:
    from term_consistency_check import run_check as _term_run_check
except ImportError:
    _term_run_check = None

# SRC_REF_PATTERN / PURE_NUM_REF_PATTERN 复用 convert_references.py 的定义，
# 避免两处正则各自演进产生漂移（03 的存在性检测 + 03b 的编号拆解均依赖）。
try:
    from convert_references import SRC_REF_PATTERN, PURE_NUM_REF_PATTERN
except ImportError:
    SRC_REF_PATTERN = re.compile(r"\[SRC-\d+(?:\s*,\s*SRC-\d+)*\]")
    PURE_NUM_REF_PATTERN = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")

# 降级台账汇总（第 13 项，方案 §D1 "G(交付)" 行）。
try:
    from degradation_report import summarize as _degradation_summarize
    from degradation_log import _resolve_log_path
except ImportError:
    _degradation_summarize = None
    _resolve_log_path = None

# figure_gate.py 顶部对 PIL/PyYAML 的 import 失败会在模块导入阶段直接
# sys.exit(1)（见 scripts/figure_gate.py:31-41）——聚合脚本不能让这个副作用
# 拖垮整个聚合检查，因此先用 importlib.util.find_spec 预检测，可用时才 import。
_FIGURE_GATE_AVAILABLE = (
    importlib.util.find_spec("PIL") is not None
    and importlib.util.find_spec("yaml") is not None
)
run_figure_gate = None
if _FIGURE_GATE_AVAILABLE:
    try:
        from figure_gate import run_figure_gate
    except ImportError:
        _FIGURE_GATE_AVAILABLE = False
        run_figure_gate = None

# ---------------------------------------------------------------------------
# 本地正则常量（与源脚本逐字一致，注明出处；不 import 私有下划线前缀符号）
# ---------------------------------------------------------------------------

# 与 scripts/md2docx/textstage/clean.py 的 _RX_HEADING（第81行）/
# _RX_WRITER_SELFCLAIM_TEXT（第82行）逐字一致 —— R-12 写作者自声明兜底验证。
RX_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)?\s*$")
RX_WRITER_SELFCLAIM_TEXT = re.compile(r"^(写作者自声明|作者自声明)$")

# 与 scripts/md2docx/textstage/clean.py 的 _RX_REDTEAM_BLOCKQUOTE（第85行）
# 逐字一致 —— R-14 红队/阶段9批注块兜底验证。
RX_REDTEAM_BLOCKQUOTE = re.compile(r"^\s*>\s*\[(?:红队|阶段9)[^\]]*\].*$")

# 与 scripts/md2docx/render/paragraphs.py 的 _RE_XREF（第21行）逐字一致 ——
# 交叉引用存在性/格式校验（语义指对与否仍需人工抽查，方案 §D6 原文）。
RE_XREF = re.compile(r"(图|表)(\d{1,2})-(\d{1,2})")
FIGURE_CAPTION_PATTERN = re.compile(r"!\[图\s*(\d{1,2}-\d{1,2})")
TABLE_CAPTION_PATTERN = re.compile(r"\*\*表\s*(\d{1,2}-\d{1,2})")

# 03b 专用：参考文献章节标题定位 —— 支持 H1/H2/H3（{1,3}），同时覆盖
# generate_bibliography() 修复前的 H1 现状与修复后的 H2 目标形态，避免
# 03b 的章节定位依赖另一处改动是否已落地（interface-designer 回炉结论：
# 两处改动互不阻塞，03b 不应把正则收窄为只匹配 H2）。要求标题独占一行、
# 标题文本恰为"参考文献"（允许尾随空白），不匹配正文中出现"参考文献"
# 字样的普通段落（如"详见参考文献列表"这类非标题行）。
RX_BIBLIOGRAPHY_HEADING = re.compile(r"^#{1,3}\s+参考文献\s*$", re.MULTILINE)

# 03b 专用：参考文献条目行首编号提取 —— 条目侧编号恒为单个整数
# （generate_bibliography() 的 format_gbt7714() 每条固定 f"[{num}]" 单编号
# 开头，不存在合并编号写法），逐行匹配即可，不需要逗号拆分。
RX_ENTRY_LINE_LENIENT = re.compile(r"^\[(\d+)\]")


# ---------------------------------------------------------------------------
# 10 项可脚本化检查
# ---------------------------------------------------------------------------


def check_term_consistency(merged_file: str, glossary_path: Optional[str]) -> dict:
    """01 术语一致性 —— term_consistency_check.run_check()，调用处自行 try/except
    （该函数本身不包裹异常，见模块 docstring）。"""
    if _term_run_check is None:
        return {"status": "error", "reason": "term_consistency_check 模块不可用（import 失败）"}
    if not glossary_path or not Path(glossary_path).exists():
        return {"status": "skipped", "reason": f"glossary 文件不存在或未提供: {glossary_path}"}
    try:
        return _term_run_check(merged_file, glossary_path)
    except Exception as e:  # noqa: BLE001 —— run_check 本身无 try/except，聚合脚本必须兜底
        return {"status": "error", "reason": f"术语一致性检查执行异常: {e}"}


def check_reference_dedup(merged_text: str, drafts_dir: Optional[str]) -> dict:
    """03 参考文献去重与一一对应 —— 代理指标：合并终稿中不再残留 [SRC-XXX]
    引用，说明 convert_references.py 的去重转换已完成。

    只检测 merged_text（合并终稿），不检测 drafts_dir（原始分章草稿目录）。
    ``drafts_dir`` 参数保留仅为向后兼容调用方签名，本函数不再读取它——
    原始分章文件按设计**永远不会**被回写转换结果（merge_drafts.py::
    clean_draft() B6 注释："在 merge 阶段暂时保留 SRC，由 convert_references.py
    在阶段 F 统一处理"；finalize_pipeline.py 步骤4 同样只对 work_path 合并
    副本做 [SRC-XXX]→[N] 替换，不回写 drafts_dir）。检测 drafts_dir 等于
    检测一个按设计恒定包含 [SRC-XXX] 的目录，会让任何含真实引用的报告在
    本项上恒定判负，与"引用转换是否已完成"这一本项真实意图无关——这不是
    边界情形，是此前实现的根本性检测对象错误，已修复。"""
    found = bool(SRC_REF_PATTERN.search(merged_text))
    return {"status": "fail" if found else "pass", "src_residue_found": found, "checked": "merged_text"}


def check_reference_completeness(text: str) -> dict:
    """03b 参考文献一一对应完整性 —— 正文唯一 [N] 引用编号集合 与 参考文献
    条目编号集合 的完整性比对，不依赖 source-index.csv（两个集合都直接从
    merged_file 文本本身抽取）。

    与 03（check_reference_dedup）的职责边界：03 是"正文 [SRC-XXX] 残留"
    的代理指标；03b 是"参考文献章节是否存在 + 编号是否一一对应"的实质性
    检测，二者互补，不重叠。

    拆解算法（interface-designer 回炉核实）：正文侧用 PURE_NUM_REF_PATTERN
    先定位每个完整的 [...] 块，再对块内容用 \\d+ 提取所有数字子串——这一手法
    与 convert_references.py::extract_src_ids() 同构（外层定位块+内层提取
    数字子串），能正确处理 [2, 4] 这类合并引用，不会把整个复合字符串当作
    不可分割元素。显式采用 convert_references.py 的宽松版本 PURE_NUM_REF_
    PATTERN（逗号前后均允许空格），不采用 contract_check.py 的窄版本
    （不接受逗号前有空格的 [1 ,3] 变体），避免技术债传导产生假阳性。
    """
    bib_match = RX_BIBLIOGRAPHY_HEADING.search(text)
    if bib_match is None:
        # 消歧：区分"本来就无引用的合法报告"（如纯叙事类无需引用）与"该注入
        # 参考文献节但漏注入"（bug 场景）——用同一个 PURE_NUM_REF_PATTERN 检
        # 查全文是否存在任何 [N] 引用，低成本消歧，不需要新依赖。
        if not PURE_NUM_REF_PATTERN.search(text):
            return {
                "status": "pass",
                "reason": "全文无 [N] 引用，无需参考文献节，判定合规",
            }
        return {
            "status": "fail",
            "reason": (
                "全文存在 [N] 引用，但未找到参考文献章节标题（支持 H1/H2/H3，"
                "需独占一行）——说明参考文献节本应生成却未被正确插入，需检查"
                "convert_refs 步骤的插入逻辑"
            ),
        }
    body_text = text[: bib_match.start()]
    bib_section_text = text[bib_match.end():]

    body_ref_numbers: set = set()
    for m in PURE_NUM_REF_PATTERN.finditer(body_text):
        for num_str in re.findall(r"\d+", m.group(0)):
            body_ref_numbers.add(int(num_str))

    entry_numbers = []
    for line in bib_section_text.split("\n"):
        m = RX_ENTRY_LINE_LENIENT.match(line.strip())
        if m is None:
            continue
        entry_numbers.append(int(m.group(1)))
    entry_number_set = set(entry_numbers)

    missing_in_bibliography = sorted(body_ref_numbers - entry_number_set)
    orphan_entries = sorted(entry_number_set - body_ref_numbers)
    duplicate_entry_numbers = sorted({n for n in entry_numbers if entry_numbers.count(n) > 1})

    issues = []
    if missing_in_bibliography:
        issues.append(f"编号断裂：正文引用了 {missing_in_bibliography} 但参考文献列表中无对应条目")
    if orphan_entries:
        issues.append(f"孤儿条目：参考文献列表存在 {orphan_entries} 但正文从未引用")
    if duplicate_entry_numbers:
        issues.append(f"重复编号：参考文献列表中编号 {duplicate_entry_numbers} 重复出现")

    return {
        "status": "fail" if issues else "pass",
        "body_ref_numbers": sorted(body_ref_numbers),
        "entry_numbers": sorted(entry_number_set),
        "missing_in_bibliography": missing_in_bibliography,
        "orphan_entries": orphan_entries,
        "duplicate_entry_numbers": duplicate_entry_numbers,
        "issues": issues,
    }


def check_figure_numbering(
    contract_result: dict, outline_path: Optional[str], figures_dir: Optional[str]
) -> dict:
    """04 图表编号统一 —— figure_gate.run_figure_gate() + C3/C4 复用。"""
    c3 = contract_result["contract"]["C3_image_syntax"]
    c4 = contract_result["contract"]["C4_table_caption"]
    entry: dict = {"c3_image_syntax": c3, "c4_table_caption": c4, "figure_gate": None}

    if not _FIGURE_GATE_AVAILABLE or run_figure_gate is None:
        entry["figure_gate"] = {
            "status": "skipped",
            "reason": "PIL/PyYAML 不可用，figure_gate.py 降级跳过（不阻断聚合脚本本身）",
        }
        entry["status"] = "pass" if (c3["pass"] and c4["pass"]) else "fail"
        return entry

    if not outline_path or not figures_dir:
        entry["figure_gate"] = {"status": "skipped", "reason": "未提供 --outline / --figures-dir"}
        entry["status"] = "pass" if (c3["pass"] and c4["pass"]) else "fail"
        return entry

    fg_result = run_figure_gate(Path(outline_path), Path(figures_dir), stage="stage9")
    entry["figure_gate"] = fg_result
    entry["status"] = "pass" if (c3["pass"] and c4["pass"] and fg_result.get("passed", False)) else "fail"
    return entry


def check_writer_selfclaim_stripped(text: str) -> dict:
    """06 写作者自声明剥离 —— 验证剥离后不含匹配 R-12 标题模式的残留标题。"""
    hits = []
    for i, line in enumerate(text.split("\n")):
        m = RX_HEADING.match(line)
        if m is not None and RX_WRITER_SELFCLAIM_TEXT.match((m.group(2) or "").strip()):
            hits.append({"line": i + 1, "text": line.strip()})
    return {"status": "fail" if hits else "pass", "hits": hits}


def check_redteam_annotation_stripped(text: str) -> dict:
    """07 红队批注剥离 —— 验证 R-14 兜底生效，不含红队/阶段9批注块残留。"""
    hits = []
    for i, line in enumerate(text.split("\n")):
        if RX_REDTEAM_BLOCKQUOTE.match(line):
            hits.append({"line": i + 1, "text": line.strip()})
    return {"status": "fail" if hits else "pass", "hits": hits}


def check_xref_consistency(text: str) -> dict:
    """10 交叉引用一致（部分）—— 仅做存在性/格式校验，语义指对与否仍需人工
    抽查（方案 §D6 原文明确声明的天花板，不在此处冒充语义判断）。orphan_refs
    仅供人工抽查参考，不导致本项 fail（避免正文引用早于图表插入等正常写作
    顺序被误判为缺陷）。"""
    referenced = set()
    for m in RE_XREF.finditer(text):
        referenced.add(f"{m.group(1)}{m.group(2)}-{m.group(3)}")
    actual_figures = {f"图{n}" for n in FIGURE_CAPTION_PATTERN.findall(text)}
    actual_tables = {f"表{n}" for n in TABLE_CAPTION_PATTERN.findall(text)}
    actual = actual_figures | actual_tables
    orphan_refs = sorted(referenced - actual)
    return {
        "status": "pass",
        "referenced_count": len(referenced),
        "actual_figure_table_count": len(actual),
        "orphan_refs": orphan_refs,
        "note": "语义指对与否需人工抽查，本项仅做存在性/格式校验",
    }


# ---------------------------------------------------------------------------
# 2 项不可脚本化（manual_required，方案 §D6 明确要求不能静默跳过或标记为 pass）
# ---------------------------------------------------------------------------


def check_redteam_resolution_confirmation(diff_path: Optional[str]) -> dict:
    """11 红队风险清单处理确认 —— 不可脚本化。本函数只能确认中间产物
    research/redteam-resolution-diff.md 是否存在，不能替代人工核对"变了什么"
    这一确认动作本身。"""
    exists = bool(diff_path) and Path(diff_path).exists()
    return {
        "status": MANUAL_REQUIRED,
        "diff_artifact_path": diff_path,
        "diff_artifact_exists": exists,
        "note": (
            "红队风险清单处理确认——必须人工核对 research/redteam-resolution-diff.md"
            "（方案 §D6），本脚本仅能确认该中间产物是否存在，不能替代人工确认动作"
        ),
    }


def check_full_read_confirmation() -> dict:
    """12 全文通读 —— 强制人在环，orchestrator 不得自行宣称已完成通读，必须
    在 CP6 显式列为待用户确认项（方案 §D6 原文："这是所有脚本/审计/红队机制
    都无法覆盖的最后一道防线"）。"""
    return {
        "status": MANUAL_REQUIRED,
        "note": (
            "全文通读——强制人在环，orchestrator 不得自行宣称已完成通读，"
            "必须在 CP6 显式列为待用户确认项（方案 §D6）"
        ),
    }


# ---------------------------------------------------------------------------
# 第 13 项：降级台账确认（方案 §D1 "G(交付)" 行）
# ---------------------------------------------------------------------------


def check_degradation_ledger(log_path: Optional[str]) -> dict:
    """13 降级台账确认 —— degradation_report.summarize()，存在未确认 L-显著
    事件即 fail（阻断 CP6，方案 §D1）。"""
    if _degradation_summarize is None or _resolve_log_path is None:
        return {"status": "error", "reason": "degradation_report/degradation_log 模块不可用（import 失败）"}
    try:
        path = _resolve_log_path(log_path)
        summary = _degradation_summarize(path)
        return {"status": "fail" if summary["blocking"] else "pass", "summary": summary}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": f"降级台账读取异常: {e}"}


# ---------------------------------------------------------------------------
# 聚合入口
# ---------------------------------------------------------------------------


def run_delivery_checklist(
    merged_file: str,
    glossary_path: Optional[str] = None,
    drafts_dir: Optional[str] = None,
    outline_path: Optional[str] = None,
    figures_dir: Optional[str] = None,
    redteam_diff_path: Optional[str] = None,
    log_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    delivery_paths: Optional[list] = None,
) -> dict:
    """执行 13 项交付清单聚合检查，返回结构化结果。不重新实现检查逻辑
    （见模块 docstring），只做调用 + 汇总。

    ``output_dir`` / ``delivery_paths``（D3-0）：交付目录感知入参。此前本脚本
    七个入参全部指向 research 侧，对交付目录零感知，导致 output 相关门禁
    （D3-2 provenance / D3-4 归档报告）无处落脚。``delivery_paths`` 为本次
    ``emit_delivery`` 实际写出的路径清单——D3-4 的 ``_is_skill_artifact``
    只能基于该清单或 sidecar provenance 判定，**禁止基于文件名正则**
    （按文件名判定会颠倒：违规的 SCIF_V1.0.docx 命中而合规的
    final-report.docx 反而不被识别）。
    """
    text = read_text(merged_file)
    contract_result = check_contract(text, merged=True, expect_figures=None, stage="stage9")

    items: dict = {}
    items["01_term_consistency"] = check_term_consistency(merged_file, glossary_path)

    # 02 引用格式 + 无分级前缀：C6 阻断，C10 保持 contract_check.py 既有的
    # 非阻塞观察期设计（severity=mid，第一阶段不升级为阻塞——见 contract_check.py
    # 注释），本项只以 C6 决定 status，C10 命中数仅作为观察信息附带展示。
    items["02_reference_format"] = {
        "status": "pass" if contract_result["contract"]["C6_reference_format"]["pass"] else "fail",
        "c6_reference_format": contract_result["contract"]["C6_reference_format"],
        "c10_source_tier_prefix_observation": contract_result["contract"]["C10_source_tier_prefix"],
    }

    items["03_reference_dedup"] = check_reference_dedup(text, drafts_dir)
    items["03b_reference_completeness"] = check_reference_completeness(text)
    items["04_figure_numbering"] = check_figure_numbering(contract_result, outline_path, figures_dir)

    items["05_output_isolation_marker"] = {
        "status": "pass" if contract_result["contract"]["C5_banned"]["pass"] else "fail",
        "c5_banned": contract_result["contract"]["C5_banned"],
    }

    items["06_writer_selfclaim_stripped"] = check_writer_selfclaim_stripped(text)
    items["07_redteam_annotation_stripped"] = check_redteam_annotation_stripped(text)

    items["08_word_count_residue"] = {
        "status": "pass" if contract_result["contract"]["C8_word_count_residue"]["pass"] else "fail",
        "c8_word_count_residue": contract_result["contract"]["C8_word_count_residue"],
    }
    items["09_local_bibliography"] = {
        "status": "pass" if contract_result["contract"]["C9_local_bibliography"]["pass"] else "fail",
        "c9_local_bibliography": contract_result["contract"]["C9_local_bibliography"],
    }

    items["10_xref_consistency"] = check_xref_consistency(text)

    items["11_redteam_resolution_confirmation"] = check_redteam_resolution_confirmation(redteam_diff_path)
    items["12_full_read_confirmation"] = check_full_read_confirmation()

    items["13_degradation_ledger"] = check_degradation_ledger(log_path)

    # overall_pass 判定：manual_required 项不计入自动 pass/fail——它们不是
    # "失败"，而是"必须人工确认"，由 CP6 流程强制拦截，不由本脚本静默判定
    # 通过（方案 §D6 明确要求）。"skipped" 视为非失败（配置项缺失，非缺陷）。
    manual_required_keys = [k for k, v in items.items() if v["status"] == MANUAL_REQUIRED]
    failed_keys = [
        k for k, v in items.items()
        if v["status"] not in ("pass", "skipped", MANUAL_REQUIRED)
    ]

    return {
        "merged_file": str(Path(merged_file).resolve()),
        "output_dir": str(Path(output_dir).resolve()) if output_dir else None,
        "delivery_paths": [str(Path(p).resolve()) for p in (delivery_paths or [])],
        "items": items,
        "failed_items": failed_keys,
        "manual_required_items": manual_required_keys,
        "overall_pass": len(failed_keys) == 0,
    }


def format_text_report(result: dict) -> str:
    lines = [f"=== 阶段9交付清单聚合检查（13项，D6）：{result['merged_file']} ===", ""]
    for key, item in result["items"].items():
        status = item.get("status")
        if status == "pass":
            mark = OK
        elif status == MANUAL_REQUIRED:
            mark = "[MANUAL_REQUIRED]"
        elif status == "skipped":
            mark = WARN
        else:
            mark = FAIL
        lines.append(f"{mark} {key}: {status}")
        if status not in ("pass",):
            lines.append(f"      {item}")
    lines.append("")
    lines.append(f"manual_required 项（必须人工确认，不计入自动 pass/fail）: {result['manual_required_items']}")
    lines.append("")
    if result["overall_pass"]:
        lines.append("=== 总判定: PASS（可脚本化项全部通过；manual_required 项仍需人工在 CP6 确认） ===")
    else:
        lines.append(f"=== 总判定: FAIL（失败项: {result['failed_items']}） ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段9交付清单聚合检查（D6，13项：10项可脚本化 + 2项manual_required + 1项降级台账）"
    )
    parser.add_argument("merged_file", help="合并终稿文件路径（如 research/drafts/final-report.md）")
    parser.add_argument("--glossary", default=None, help="research/glossary.md 路径（术语一致性检查用，可选）")
    parser.add_argument("--drafts-dir", default=None, help="分章草稿目录（参考文献去重检查用，可选）")
    parser.add_argument("--outline", default=None, help="outline.md 路径（图表编号统一检查用，可选）")
    parser.add_argument("--figures-dir", default=None, help="research/figures/ 目录（图表编号统一检查用，可选）")
    parser.add_argument(
        "--redteam-diff", default=None,
        help="research/redteam-resolution-diff.md 路径（红队风险确认项存在性检查用，可选）",
    )
    parser.add_argument("--log", default=None, help="降级台账文件路径（覆盖环境变量与默认路径，可选）")
    parser.add_argument(
        "--output-dir", default=None,
        help="交付目录（如 output/）。注意与 research 侧入参区分：本参数指最终交付物目录（可选）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not Path(args.merged_file).exists():
        print(f"{FAIL} 文件不存在: {args.merged_file}", file=sys.stderr)
        sys.exit(2)

    try:
        result = run_delivery_checklist(
            merged_file=args.merged_file,
            glossary_path=args.glossary,
            drafts_dir=args.drafts_dir,
            outline_path=args.outline,
            figures_dir=args.figures_dir,
            redteam_diff_path=args.redteam_diff,
            log_path=args.log,
            output_dir=args.output_dir,
        )
    except Exception as e:
        print(f"{FAIL} 执行失败: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
