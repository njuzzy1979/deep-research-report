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
    03 参考文献去重与一一对应       —— convert_references.has_any_src_refs()
       （代理指标：合并终稿中不再残留 [SRC-XXX]，说明 convert_references.py
        的 OrderedDict 去重转换已完成；本项不重新实现去重算法）
    04 图表编号统一                —— figure_gate.run_figure_gate() + C3/C4
    05 输出隔离标记剥离             —— contract_check C5（含 F1 标记残留）
    06 写作者自声明剥离             —— 本地正则（与 clean.py R-12 逐字一致）
    07 红队批注剥离                —— 本地正则（与 clean.py R-14 逐字一致）
    08 字数统计残留                —— contract_check C8
    09 局部参考文献                —— contract_check C9
    10 交叉引用一致（部分）         —— 本地正则（与 paragraphs.py _RE_XREF 逐字
       一致），仅做存在性/格式校验，语义指对与否仍需人工抽查（方案原文）

  2 项不可脚本化（显式标记为 manual_required，**不能**静默跳过或标记为 pass）：
    11 红队风险清单处理确认         —— 需人工核对 research/redteam-resolution-diff.md
    12 全文通读                    —— 强制人在环，orchestrator 不得自行宣称已完成

  第 13 项（方案 §D1 "G(交付)" 行明确要求纳入）：
    13 降级台账确认                —— degradation_report.summarize()，
       未确认 L-显著事件 → 阻断

关键实现约束（三处 sys.exit 陷阱，均已规避——见方案调研结论）：
  - `convert_references.load_source_index()` 在 CSV 缺失/格式错误时直接
    `sys.exit(2)`——本脚本改用不会 sys.exit 的 `has_any_src_refs()`。
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

# 用 has_any_src_refs() 代替 load_source_index()，避开后者 CSV 缺失时的
# sys.exit(2) 陷阱（见模块 docstring）。
try:
    from convert_references import has_any_src_refs, SRC_REF_PATTERN
except ImportError:
    has_any_src_refs = None
    SRC_REF_PATTERN = re.compile(r"\[SRC-\d+(?:\s*,\s*SRC-\d+)*\]")

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
    """03 参考文献去重与一一对应 —— 代理指标：合并终稿（或分章草稿目录）中
    不再残留 [SRC-XXX] 引用，说明 convert_references.py 的去重转换已完成。
    优先用 has_any_src_refs(drafts_dir)（若提供），否则直接对合并文本做
    SRC_REF_PATTERN 存在性检测——两者均不触碰 load_source_index() 的
    sys.exit(2) 陷阱。"""
    if drafts_dir and has_any_src_refs is not None and Path(drafts_dir).is_dir():
        found = has_any_src_refs(drafts_dir)
        source = "drafts_dir"
    else:
        found = bool(SRC_REF_PATTERN.search(merged_text))
        source = "merged_text"
    return {"status": "fail" if found else "pass", "src_residue_found": found, "checked": source}


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
) -> dict:
    """执行 13 项交付清单聚合检查，返回结构化结果。不重新实现检查逻辑
    （见模块 docstring），只做调用 + 汇总。"""
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
