#!/usr/bin/env python3
"""drawio 布局质量校验器 —— 源文件层几何门禁（B1' 实现：G1+G6+G7+G10a）。

范围声明（B1'，非 B1''/B3）：
  本版本实现 02 号设计文档定义的 CLI 契约中的以下子集：
    --figures-dir / --file / --ir / --report-out / --json / --mode / --strict
  接入的判据为 G1（几何完整性）+ G6（内嵌图注）+ G7（伪图检测）+ G10a
  （拓扑-模式一致性，零参数判据），均对应 02 号文档 §2 排名前四的零拟合
  参数判据。G2/G3/G5/G11（含拟合参数）、豁免机制、stage-6 agent 两级门禁
  接入均不在本批次范围内，留待 B1''/B3 批次扩展。

  G10a 的 mode 参数来源（02 号文档 §9 I-1）：G10a 判据算法本身只需边集
  （从 .drawio 本身可解析），不依赖 rank，故不受 --ir 缺失限制；但判据
  参数 mode（flow/star/grid/quadrant）的唯一权威来源是 IR JSON 的
  layout_mode 字段（03 号文档 §4.1）。未提供 --ir 时，本版本不臆测 mode，
  G10a 记为 not_applicable 并计入 summary.g10a_skipped_no_ir 计数器，不
  新增游离于 IR schema 之外的第二数据源（如 --layout-mode-map 映射文件）。
  layout_mode 为 stack/pyramid/manual 时 G10a 同样不适用（01 号文档
  §3.7.1：stack/pyramid 交 G10b，B4 后依赖 rank 字段启用）。

  G6 已知局限（R2，06 号文档 §3.3.3 已裁决不在本批次修复）：对
  `<b>图注：</b>` 类 HTML 标签包裹的图注文本存在假阴性（未先 strip_html()
  再匹配 CAPTION_PAT）。本版本原样移植 rearrange_11_1.py 的实现，不修复。

退出码约定（02 号文档 §3.2，三档）：
    0 = PASS（无 error；或目录下无 .drawio 且未声明架构图）
    1 = 校验失败（存在几何损坏/内嵌图注/伪图/拓扑不一致；或声明 >0 张架构图但目录为空）
    2 = 部分校验（本版本暂无 skip 场景，预留位）

用法：
    python drawio_layout_validator.py --figures-dir research/figures
    python drawio_layout_validator.py --file a.drawio --file b.drawio --json
    python drawio_layout_validator.py --figures-dir research/figures --report-out out.json
    python drawio_layout_validator.py --file a.drawio --ir a.ir.json
"""

import re
import sys
import html
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import xml.etree.ElementTree as ET

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCHEMA_VERSION = "d5-layout-1"
VALIDATOR_VERSION = "0.2.0-b1prime"

BAD_LITERALS = {"None", "nan", "NaN", "null", "NULL", "undefined", ""}

# G6：图注特征正则 + 已知专用 id 集合（原样移植自 rearrange_11_1.py，不修复 R2）
CAPTION_PAT = re.compile(r"^\s*(图\s*\d+\s*[-–—]\s*\d+|图注)")
CAPTION_IDS = {"title", "note", "caption", "bottomNote"}

# G7：Mermaid 源码关键字（07 号设计文档 G 节口径，逐字沿用）
MERMAID_KEYWORDS = ("flowchart", "graph TD", "subgraph", "-->")

# G10a：不适用 mode 集合（stack/pyramid 交 G10b，manual 无拓扑一致性可言）
G10A_NOT_APPLICABLE_MODES = {"stack", "pyramid", "stack/pyramid", "manual"}


# ---------------------------------------------------------------------------
# G1：几何完整性判据（复用 rearrange_11_1.py 已验证的判据逻辑，独立重写、
# 不 importlib 依赖临时脚本 —— 正式仓库脚本不应依赖 _scratch_d5 临时产物）
# ---------------------------------------------------------------------------

def check_g1(vertex_elems):
    """对每个 vertex 的 x/y/width/height 做合法性检查，返回损坏 issue 列表。"""
    bad_cells = []
    for c in vertex_elems:
        g = c.find("mxGeometry")
        cid = c.get("id", "?")
        if g is None:
            bad_cells.append({"id": cid, "attr": "mxGeometry", "literal": None})
            continue
        for attr in ("x", "y", "width", "height"):
            raw = g.get(attr)
            if raw is None:
                bad_cells.append({"id": cid, "attr": attr, "literal": None})
                continue
            if raw in BAD_LITERALS:
                bad_cells.append({"id": cid, "attr": attr, "literal": raw})
                continue
            try:
                float(raw)
            except ValueError:
                bad_cells.append({"id": cid, "attr": attr, "literal": raw})
    return bad_cells


# ---------------------------------------------------------------------------
# G6：内嵌图注判据（原样移植自 rearrange_11_1.py 的 check_g6()，未修复 R2）
#
# 已知局限 R2（06 号文档 §3.3.3 已裁决不在本批次修复）：对 `<b>图注：</b>`
# 类 HTML 标签包裹的图注文本存在假阴性 —— CAPTION_PAT 直接匹配 value 原文，
# 未先 strip_html() 剥离标签再匹配。
# ---------------------------------------------------------------------------

def check_g6(all_cell_elems):
    """检测内嵌图注 mxCell，返回命中的 cell id 列表。"""
    hits = []
    for c in all_cell_elems:
        cid = c.get("id", "")
        value = c.get("value") or ""
        if cid in CAPTION_IDS or CAPTION_PAT.search(value):
            hits.append(cid)
    return hits


# ---------------------------------------------------------------------------
# G7：伪图检测判据（新写，口径依据 07 号设计文档 G 节：检索 Mermaid 源码
# 关键字 flowchart / graph TD / subgraph / --> ，全库 376 个节点 value 中
# 0 命中，故本判据的现实基线预期为"全部 PASS"）
# ---------------------------------------------------------------------------

def check_g7(all_cell_elems):
    """检测 value 中残留的 Mermaid 源码关键字，返回命中的 (cell_id, keyword) 列表。"""
    hits = []
    for c in all_cell_elems:
        value = c.get("value") or ""
        unescaped = html.unescape(value)
        for kw in MERMAID_KEYWORDS:
            if kw in unescaped:
                hits.append((c.get("id", "?"), kw))
    return hits


# ---------------------------------------------------------------------------
# G10a：拓扑-模式一致性判据（官方 mode-dispatch 完整版，逐字移植自
# g10a_official_check_3x.py 的 g10a_official(mode, V, E)，替换掉
# rearrange_11_1.py 内联的 quadrant 专用简化版 —— 该简化版是已确认的 R1
# 问题根源，本判据不重蹈覆辙）
#
# mode 的唯一权威来源是 IR JSON 的 layout_mode 字段（--ir 参数）。未提供
# --ir 时不臆测 mode，调用方应改用 g10a_not_applicable() 的 not_applicable
# 路径，不得凭空指定 mode 调用本函数。
# ---------------------------------------------------------------------------

def _degree_maps(E):
    outd, ind, deg = defaultdict(int), defaultdict(int), defaultdict(int)
    for s, t in E:
        outd[s] += 1
        ind[t] += 1
        deg[s] += 1
        deg[t] += 1
    return outd, ind, deg


def extract_topology(all_cell_elems):
    """从 cell 元素列表提取顶点集合 V 与边集合 E（仅保留 source/target 均引用顶点的边）。"""
    V = {c.get("id") for c in all_cell_elems if c.get("vertex") == "1"}
    E = [(c.get("source"), c.get("target")) for c in all_cell_elems if c.get("edge") == "1"
         and c.get("source") and c.get("target")]
    E = [(s, t) for s, t in E if s in V and t in V]
    return V, E


def check_g10a(mode, V, E):
    """01 号设计文档 §3.7.1 官方 mode-dispatch 版判据，返回 (verdict, detail) 二元组。

    verdict 为 None 表示一致 OK；否则为 error_code 字符串。
    """
    outd, ind, deg = _degree_maps(E)
    N = len(V)
    if mode == "flow":
        if any(outd[n] > 1 for n in V) and any(ind[n] > 1 for n in V):
            return "FLOW_RECONVERGENT", {"n_vertex": N, "n_edge": len(E)}
        return None, {"n_vertex": N, "n_edge": len(E)}
    if mode == "star":
        if not E:
            return "STAR_NO_EDGES", {"n_vertex": N, "n_edge": len(E)}
        mx = max(deg.values())
        hubs = [n for n in V if deg[n] == mx]
        sec = max((deg[n] for n in V if deg[n] < mx), default=0)
        if len(hubs) != 1:
            return "STAR_NO_UNIQUE_HUB", {"n_vertex": N, "n_edge": len(E), "hubs": hubs}
        if mx < max(3, sec * 2):
            return "STAR_HUB_NOT_DOMINANT", {"n_vertex": N, "n_edge": len(E), "hub": hubs[0], "hub_degree": mx, "second_degree": sec}
        return None, {"n_vertex": N, "n_edge": len(E), "hub": hubs[0]}
    if mode in ("grid", "quadrant"):
        if not E:
            return None, {"n_vertex": N, "n_edge": len(E)}
        adj = defaultdict(set)
        for s, t in E:
            adj[s].add(t)
            adj[t].add(s)
        seen, best = set(), 0
        for v in V:
            if v in seen or v not in adj:
                continue
            stack = [v]
            seen.add(v)
            c = 0
            while stack:
                u = stack.pop()
                c += 1
                for w in adj[u]:
                    if w not in seen:
                        seen.add(w)
                        stack.append(w)
            best = max(best, c)
        if best > N / 3.0:
            return "GRID_HAS_CONNECTED_STRUCTURE(%d/%d)" % (best, N), {"n_vertex": N, "n_edge": len(E), "largest_component": best}
        return None, {"n_vertex": N, "n_edge": len(E), "largest_component": best}
    return "UNKNOWN_MODE(%s)" % mode, {"n_vertex": N, "n_edge": len(E)}


# ---------------------------------------------------------------------------
# 单文件校验
# ---------------------------------------------------------------------------

def _load_layout_mode(ir_path):
    """从 IR JSON 读取 layout_mode 字段（03 号文档 §4.1 唯一权威来源）。"""
    if ir_path is None:
        return None
    try:
        data = json.loads(Path(ir_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("layout_mode")


def validate_one_file(path: Path, ir_path=None) -> dict:
    """校验单个 .drawio 文件，返回 02 号文档 §4 schema 的单 item 结构。

    Args:
        path: 待校验的 .drawio 文件路径
        ir_path: 可选，配套 IR JSON 路径。提供时用其中的 layout_mode 字段
            驱动 G10a 做完整 mode-dispatch 判定；不提供时 G10a 记为
            not_applicable，不臆测 mode。
    """
    item = {
        "file": path.name,
        "format": "plain",
        "passed": True,
        "vertex_total": 0,
        "vertex_geometry_valid": 0,
        "checks": {
            "G1_geometry_integrity": "pass",
            "G6_embedded_caption": "pass",
            "G7_fake_diagram": "pass",
            "G10a_topology": "not_applicable",
        },
        "issues": [],
    }

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        item["passed"] = False
        item["checks"]["G1_geometry_integrity"] = "fail"
        item["issues"].append({
            "check": "G1_geometry_integrity",
            "error_code": "XML_PARSE_ERROR",
            "severity": "error",
            "message": f"XML 解析失败: {e}",
            "feedback": f"{path.name} 无法解析为合法 XML，需人工检查文件是否损坏或为压缩格式。",
            "retryable": False,
        })
        return item

    root = tree.getroot()
    all_cell_elems = list(root.iter("mxCell"))
    vertex_elems = [c for c in all_cell_elems if c.get("vertex") == "1"]
    item["vertex_total"] = len(vertex_elems)

    # --- G1 ---
    bad_cells = check_g1(vertex_elems)
    item["vertex_geometry_valid"] = len(vertex_elems) - len({b["id"] for b in bad_cells})

    if bad_cells:
        item["passed"] = False
        item["checks"]["G1_geometry_integrity"] = "fail"
        cell_ids = sorted({b["id"] for b in bad_cells})
        item["issues"].append({
            "check": "G1_geometry_integrity",
            "error_code": "GEOMETRY_INVALID",
            "severity": "error",
            "cells": bad_cells,
            "message": f"{len(cell_ids)} 个 vertex 的几何字面值非法（共 {len(bad_cells)} 处）",
            "feedback": (
                f"节点 {', '.join(cell_ids)} 的几何属性存在非数值字面值，"
                "此为生成器缺陷，不可通过重试修复。"
            ),
            "retryable": False,
        })

    # --- G6：内嵌图注 ---
    g6_hits = check_g6(all_cell_elems)
    if g6_hits:
        item["passed"] = False
        item["checks"]["G6_embedded_caption"] = "fail"
        item["issues"].append({
            "check": "G6_embedded_caption",
            "error_code": "EMBEDDED_CAPTION",
            "severity": "error",
            "cells": g6_hits,
            "message": f"{len(g6_hits)} 处内嵌图注 mxCell: {g6_hits}",
            "feedback": (
                f"节点 {', '.join(g6_hits)} 疑似把图注文本嵌入画布，"
                "应移除该 mxCell 并将文本移入 Markdown 正文题注。"
            ),
            "retryable": False,
        })

    # --- G7：伪图检测 ---
    g7_hits = check_g7(all_cell_elems)
    if g7_hits:
        item["passed"] = False
        item["checks"]["G7_fake_diagram"] = "fail"
        cell_ids = sorted({cid for cid, _ in g7_hits})
        item["issues"].append({
            "check": "G7_fake_diagram",
            "error_code": "FAKE_DIAGRAM",
            "severity": "error",
            "cells": g7_hits,
            "message": f"{len(cell_ids)} 个节点残留 Mermaid 源码关键字: {g7_hits}",
            "feedback": (
                f"节点 {', '.join(cell_ids)} 疑似把 Mermaid 源码文本内嵌为 text box，"
                "应重新出图为真实 drawio 图形元素，禁止文本框内嵌 Mermaid 源码。"
            ),
            "retryable": True,
        })

    # --- G10a：拓扑-模式一致性 ---
    layout_mode = _load_layout_mode(ir_path)
    if layout_mode is None:
        item["checks"]["G10a_topology"] = "not_applicable"
    elif layout_mode in G10A_NOT_APPLICABLE_MODES:
        item["checks"]["G10a_topology"] = "not_applicable"
    else:
        V, E = extract_topology(all_cell_elems)
        verdict, detail = check_g10a(layout_mode, V, E)
        if verdict is None:
            item["checks"]["G10a_topology"] = "pass"
        else:
            item["passed"] = False
            item["checks"]["G10a_topology"] = "fail"
            item["issues"].append({
                "check": "G10a_topology",
                "error_code": verdict.split("(")[0],
                "severity": "error",
                "detail": detail,
                "message": f"layout_mode={layout_mode} 下拓扑-模式判定={verdict}",
                "feedback": (
                    f"该图声明 layout_mode={layout_mode}，但边集拓扑与该模式不一致（{verdict}）。"
                    "禁止改模式重试，应强制转 layout_mode=manual 由人工排布。"
                ),
                "retryable": False,
            })

    return item


# ---------------------------------------------------------------------------
# 主校验流程
# ---------------------------------------------------------------------------

def run_validator(files: list, ir_files: list = None, mode: str = "block", strict: bool = False) -> dict:
    """对给定文件列表跑校验，返回 02 号文档 §4 schema 的完整结构。

    Args:
        files: 待校验的 .drawio 文件路径列表（Path 对象）
        ir_files: 与 files 一一对应的可选 IR JSON 路径列表（None 表示该文件无 IR
            输入，G10a 记为 not_applicable）；整体省略时按全 None 处理
        mode: warn（所有 error 降级为 warning，恒 exit 0）| block（正常判定）
        strict: warning 一并计入失败
    """
    if ir_files is None:
        ir_files = [None] * len(files)
    items = [validate_one_file(p, ir_path=ir) for p, ir in zip(files, ir_files)]

    total_errors = sum(len([i for i in it["issues"] if i["severity"] == "error"]) for it in items)
    total_warnings = sum(len([i for i in it["issues"] if i["severity"] == "warning"]) for it in items)

    vertex_total = sum(it["vertex_total"] for it in items)
    vertex_geometry_valid = sum(it["vertex_geometry_valid"] for it in items)

    files_failed = sum(1 for it in items if not it["passed"])
    files_passed = len(items) - files_failed

    if mode == "warn":
        passed = True
    elif strict:
        passed = (total_errors == 0) and (total_warnings == 0)
    else:
        passed = total_errors == 0

    exit_code = 0 if passed else 1

    g10a_skipped_no_ir = sum(1 for it in items if it["checks"].get("G10a_topology") == "not_applicable")

    return {
        "schema_version": SCHEMA_VERSION,
        "passed": passed,
        "exit_code": exit_code,
        "generated_at": None,  # 由 main() 填充（脚本内禁止 datetime.now() 以外的伪造）
        "validator_version": VALIDATOR_VERSION,
        "mode": mode,
        "summary": {
            "files_total": len(items),
            "files_passed": files_passed,
            "files_failed": files_failed,
            "files_skipped": 0,
            "errors": total_errors,
            "warnings": total_warnings,
            "vertex_total": vertex_total,
            "vertex_geometry_valid": vertex_geometry_valid,
            "vertex_geometry_broken": vertex_total - vertex_geometry_valid,
            "manual_ratio": None,
            "g10a_skipped_no_ir": g10a_skipped_no_ir,
        },
        "items": items,
        "skipped": [],
        "exemptions_applied": [],
    }


def format_report(result: dict) -> str:
    """对齐 figure_gate.py 的 format_report() 风格。"""
    lines = [
        "=" * 60,
        "布局质量门禁报告 (drawio_layout_validator) — B1'（G1+G6+G7+G10a）",
        "=" * 60,
        "",
    ]
    if "error" in result:
        lines.append(f"[FAIL] 致命错误: {result['error']}")
        return "\n".join(lines)
    if "note" in result:
        lines.append(f"[INFO] {result['note']}")
        return "\n".join(lines)

    s = result["summary"]
    lines.append(f"模式: {result['mode']}")
    lines.append(f"顶点统计: {s['vertex_total']} 总计 / {s['vertex_geometry_valid']} 几何可解析 / "
                 f"{s['vertex_geometry_broken']} 几何损坏")
    if s.get("g10a_skipped_no_ir"):
        lines.append(f"G10a: {s['g10a_skipped_no_ir']} 个文件因无 --ir 输入记为 not_applicable（未臆测 mode）")
    lines.append("")

    fail_items = [it for it in result["items"] if not it["passed"]]
    if fail_items:
        lines.append("--- 判据未通过 (FATAL 除 G7 外均不可重试) ---")
        for it in fail_items:
            lines.append(f"  [FAIL] {it['file']}")
            for issue in it["issues"]:
                lines.append(f"         {issue['message']}")
                lines.append(f"         -> {issue['feedback']}")
        lines.append("")

    lines.append("--- 逐项详情 ---")
    for it in result["items"]:
        status = "[OK]" if it["passed"] else "[FAIL]"
        checks = it["checks"]
        checks_str = " ".join(f"{k.split('_')[0]}={v}" for k, v in checks.items())
        lines.append(f"  {status} {it['file']}  {it['vertex_total']} 顶点  [{checks_str}]")

    lines.append("")
    if result["passed"]:
        lines.append(f"=== 总判定: PASS — exit {result['exit_code']} ===")
    else:
        lines.append(f"=== 总判定: FAIL ({s['errors']} errors, {s['warnings']} warnings) — exit {result['exit_code']} ===")
    if result.get("report_out"):
        lines.append(f"留痕: {result['report_out']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="drawio 布局质量门禁（源文件层，B1' 版：G1+G6+G7+G10a）。"
    )
    parser.add_argument(
        "--figures-dir", default="research/figures",
        help="批量校验目录下全部 *.drawio（默认: research/figures）"
    )
    parser.add_argument(
        "--file", action="append", default=None,
        help="只校验指定文件，可多次给出；与 --figures-dir 互斥"
    )
    parser.add_argument(
        "--ir", action="append", default=None,
        help="配套 IR JSON 路径，与 --file 按给出顺序一一对应；用于驱动 G10a 完整"
             "mode-dispatch 判定。省略时 G10a 记为 not_applicable，不臆测 mode。"
             "仅在配合 --file 使用时生效（--figures-dir 批量模式下无法一一对应，忽略本参数）。"
    )
    parser.add_argument(
        "--mode", choices=["warn", "block"], default="block",
        help="warn: 所有 error 降级为 warning，恒 exit 0（B1 上线用）；block: 正常判定"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="严格模式: warning 一并计入失败"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="输出 JSON 格式"
    )
    parser.add_argument(
        "--report-out", default=None,
        help="门禁留痕 JSON 落盘路径（默认: <figures-dir>/.layout-gate-report.json）"
    )

    args = parser.parse_args()

    ir_files = None
    if args.file:
        files = [Path(f) for f in args.file]
        missing = [f for f in files if not f.exists()]
        if missing:
            print(f"[FAIL] 致命错误: 文件不存在: {', '.join(str(m) for m in missing)}", file=sys.stderr)
            sys.exit(1)
        figures_dir_for_report = files[0].parent if files else Path(args.figures_dir)
        if args.ir:
            if len(args.ir) != len(files):
                print(
                    f"[FAIL] 致命错误: --ir 个数({len(args.ir)})与 --file 个数({len(files)})不一致，"
                    "两者须按给出顺序一一对应",
                    file=sys.stderr,
                )
                sys.exit(1)
            ir_missing = [f for f in args.ir if not Path(f).exists()]
            if ir_missing:
                print(f"[FAIL] 致命错误: --ir 文件不存在: {', '.join(ir_missing)}", file=sys.stderr)
                sys.exit(1)
            ir_files = [Path(f) for f in args.ir]
    else:
        figures_dir = Path(args.figures_dir)
        if not figures_dir.exists():
            print(f"[FAIL] 致命错误: figures/ 目录不存在: {figures_dir}", file=sys.stderr)
            sys.exit(1)
        files = sorted(figures_dir.glob("*.drawio"))
        figures_dir_for_report = figures_dir
        if args.ir:
            print(
                "[INFO] --figures-dir 批量模式下无法与 --ir 一一对应，本次运行忽略 --ir，"
                "G10a 记为 not_applicable",
                file=sys.stderr,
            )

    report_out = Path(args.report_out) if args.report_out else figures_dir_for_report / ".layout-gate-report.json"

    if not files:
        # 空目录一律按 02 号文档"未声明架构图"分支处理为 PASS + note。
        result = {
            "schema_version": SCHEMA_VERSION,
            "passed": True,
            "exit_code": 0,
            "generated_at": None,
            "validator_version": VALIDATOR_VERSION,
            "mode": args.mode,
            "summary": {
                "files_total": 0, "files_passed": 0, "files_failed": 0,
                "files_skipped": 0, "errors": 0, "warnings": 0,
                "vertex_total": 0, "vertex_geometry_valid": 0,
                "vertex_geometry_broken": 0, "manual_ratio": None,
                "g10a_skipped_no_ir": 0,
            },
            "items": [], "skipped": [], "exemptions_applied": [],
            "note": "目录下无 .drawio 文件，本版本不读取 outline.md 声明数，按 PASS 处理",
        }
    else:
        result = run_validator(files, ir_files=ir_files, mode=args.mode, strict=args.strict)

    tz = timezone(timedelta(hours=8))
    result["generated_at"] = datetime.now(tz).isoformat()
    result["tool_invocation"] = " ".join(["drawio_layout_validator.py"] + sys.argv[1:])
    result["report_out"] = str(report_out)

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
