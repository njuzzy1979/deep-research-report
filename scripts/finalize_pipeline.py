#!/usr/bin/env python3
"""阶段 9 定稿顺序管道（跨模型兼容性优化方案 §五 D5）。

职责边界（务必读完）：本脚本把 finalizer_agent 阶段中**顺序强依赖且纯机械**的
6 个步骤串成单一 Python 流程，消除 Haiku 级 LLM 在这些步骤上的自由发挥空间。
方案 §D5 原文："`finalize_pipeline.py` 把顺序强依赖且纯机械的步骤（剥离标记 →
H1 检测替换 → 结构驱动合并 → convert_references → contract_check --merged
--stage stage9 → delivery_checklist）串成单一 Python 流程，`finalizer_agent`
（Haiku）职责收窄为'跑一个脚本 + 读 JSON + 按 `failure_step` 查固定路由表'。"

6 个步骤（与 `failure_step` 枚举值逐字对应）：
    1. strip_markers      —— 复用 `merge_drafts.clean_draft()`（B1-B6 清洗规则，
                              含剥离 Agent 输出隔离标记/字数残留/局部参考文献/
                              粗体伪标题检测），逐个 ch*.md 文件清洗并写回
                              （先备份为 .bak，与 merge_drafts.py 阶段 B 同款）。
    2. h1_check            —— 新写函数：扫描清洗后的 ch*.md 文件，检测 H1
                              （`^#\\s+\\S`）并自动替换为 H2（`## `），写回文件。
                              对应 stage-9-finalize.md §9.1.x 的 bash grep 语义。
    3. merge               —— 函数级 import `merge_drafts.parse_outline_yaml()` +
                              `merge_drafts.assemble_merged()`（均为纯函数），
                              按 outline.md 的 YAML structure 结构驱动拼接。
    4. convert_refs        —— 函数级 import `convert_references` 模块相关函数
                              （`load_source_index`/`scan_drafts`/
                              `find_slash_refs_in_file`/`find_all_refs_in_file`/
                              `build_numbering`/`replace_refs_in_file`/
                              `generate_bibliography`），自行编排 in-place 转换
                              流程，不调用其 main()、不用 subprocess。
    5. contract_check      —— 函数级 import `contract_check.check_contract()`，
                              显式传入 `merged=True, stage="stage9"`。
    6. delivery_checklist  —— 函数级 import
                              `delivery_checklist_check.run_delivery_checklist()`。

关键设计：与 merge_drafts.py 的反模式刻意区分——merge_drafts.py 的阶段
C/E/F 校验失败时只打印 WARN，main() 正常 return，exit code 恒为 0（不存在任何
sys.exit(1) 调用路径）。本脚本每一步失败都**真正提前终止**并在 JSON 中标记
精确的 `failure_step`，这正是 D5 存在的核心意义：给 orchestrator 一个可编程
路由的失败定位，而不是让它去翻 stdout 里的 WARN 文本。

sys.exit 陷阱规避（两处，均已捕获为 failure_step 而非让进程被杀）：
    - `merge_drafts.parse_outline_yaml()` 在 outline.md YAML 解析失败时直接
      `sys.exit(2)`（该函数内部已写降级台账）——本脚本用 `except SystemExit`
      捕获，转换为 `failure_step="merge"` 的结构化失败，不让整个管道进程被杀。
    - `convert_references.load_source_index()` 在 source-index.csv 缺失/格式
      错误时直接 `sys.exit(2)`——同样用 `except SystemExit` 捕获，转换为
      `failure_step="convert_refs"`。
  `contract_check.check_contract()` 与 `delivery_checklist_check.run_delivery_checklist()`
  两者都是纯函数（不 sys.exit，只有各自的 main() 才 sys.exit），可以直接调用。

用法：
    python scripts/finalize_pipeline.py \\
        --drafts-dir research/drafts --outline research/outline.md \\
        --source-index research/sources/source-index.csv \\
        --output research/drafts/final-report.md --json

退出码：0 = 6 步全部通过（overall_pass=True）；
       1 = 某一步内容层面失败（failure_step 指出具体哪一步，overall_pass=False）；
       2 = drafts-dir 不存在 / 执行过程中抛出未预期异常（用法错误层面）。
"""
from __future__ import annotations

import argparse
import json
import os
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

# failure_step 枚举（方案 §D5 明确要求的 6 个固定值，顺序即执行顺序）
FAILURE_STEPS = (
    "strip_markers", "h1_check", "merge", "convert_refs",
    "contract_check", "delivery_checklist",
)

# H1 检测正则：与 contract_check.py 的 C1 判定口径（`^#\s+\S`）逐字一致，
# 避免本脚本与合约终检对"什么算 H1"产生两份互相漂移的定义。
H1_LINE_PATTERN = re.compile(r"^#\s+\S")


# ---------------------------------------------------------------------------
# 单步实现
# ---------------------------------------------------------------------------


def _replace_h1_with_h2(text: str) -> tuple:
    """扫描文本逐行，将 H1（`# 标题`）替换为 H2（`## 标题`）。返回 (新文本, 替换行数)。"""
    lines = text.split("\n")
    count = 0
    new_lines = []
    for line in lines:
        if H1_LINE_PATTERN.match(line):
            new_lines.append("#" + line)  # "# 标题" -> "## 标题"
            count += 1
        else:
            new_lines.append(line)
    return "\n".join(new_lines), count


def run_finalize_pipeline(
    drafts_dir: str,
    outline_path: str,
    source_index_path: str,
    output_path: str,
    *,
    glossary_path: Optional[str] = None,
    figures_dir: Optional[str] = None,
    redteam_diff_path: Optional[str] = None,
    log_path: Optional[str] = None,
) -> dict:
    """执行 6 步定稿顺序管道，任一步失败立即提前 return（不同于
    precommit_consistency_check.py 的"最后统一 derive_overall"模式——本管道
    6 步顺序强依赖，后续步骤依赖前面步骤产出的文件，continue 没有意义）。"""
    steps: dict = {}

    def _finish(failure_step: str, reason: str, detail: Optional[dict] = None) -> dict:
        entry = {"status": "fail", "reason": reason}
        if detail is not None:
            entry["detail"] = detail
        steps[failure_step] = entry
        return {
            "overall_pass": False,
            "failure_step": failure_step,
            "failure_reason": reason,
            "steps": steps,
            "output_path": None,
        }

    if not os.path.isdir(drafts_dir):
        return _finish("strip_markers", f"drafts-dir 不存在: {drafts_dir}")

    # ── 步骤 1: strip_markers —— 复用 merge_drafts.clean_draft() ──────────
    try:
        from merge_drafts import clean_draft
    except ImportError as e:
        return _finish("strip_markers", f"merge_drafts 模块不可用（import 失败）: {e}")

    draft_files = sorted(Path(drafts_dir).glob("ch*.md"))
    cleaning_reports: dict = {}
    try:
        for fp in draft_files:
            text = fp.read_text(encoding="utf-8")
            cleaned, report = clean_draft(text)
            cleaning_reports[str(fp)] = report
            # 先备份为 .bak（与 merge_drafts.py 阶段 B 同款约定），再覆写清洗后文本
            Path(str(fp) + ".bak").write_text(text, encoding="utf-8")
            fp.write_text(cleaned, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return _finish("strip_markers", f"标记剥离执行异常: {e}")
    steps["strip_markers"] = {
        "status": "pass", "files_cleaned": len(draft_files), "reports": cleaning_reports,
    }

    # ── 步骤 2: h1_check —— 新写函数，扫描+替换 H1→H2 ─────────────────────
    h1_summary: dict = {}
    try:
        for fp in draft_files:
            text = fp.read_text(encoding="utf-8")
            new_text, count = _replace_h1_with_h2(text)
            if count:
                fp.write_text(new_text, encoding="utf-8")
                h1_summary[str(fp)] = count
    except Exception as e:  # noqa: BLE001
        return _finish("h1_check", f"H1 检测替换执行异常: {e}")
    steps["h1_check"] = {"status": "pass", "files_with_h1_replaced": h1_summary}

    # ── 步骤 3: merge —— 函数级 import parse_outline_yaml + assemble_merged ──
    try:
        from merge_drafts import parse_outline_yaml, assemble_merged
    except ImportError as e:
        return _finish("merge", f"merge_drafts 模块不可用（import 失败）: {e}")

    try:
        structure = parse_outline_yaml(outline_path)
        # ── 键名适配：outline.md YAML 使用 section_no/section_title/subsections，
        #     但 assemble_merged 期望 chapter_no/chapter_title/sections。
        #     subections 为空列表时各章为单文件，需为其生成一个虚拟 section 条目
        #     以便 find_draft_files 通过 ch{XX}-*.md 通配符匹配。
        for item in structure.get("bodymatter", []):
            item["chapter_no"] = int(item.get("section_no", "?"))
            item["chapter_title"] = item.get("section_title", "")
            if item.get("subsections"):
                item["sections"] = item["subsections"]
            else:
                # 无小节时直接按章号匹配单文件
                item["sections"] = [{"section_no": str(item["chapter_no"]), "section_title": item["chapter_title"]}]
        for item in structure.get("frontmatter", []):
            item["chapter_title"] = item.get("section_title", "")
            if item.get("subsections"):
                item["sections"] = item["subsections"]
            else:
                item["sections"] = []
    except SystemExit as e:
        # parse_outline_yaml 在 YAML 解析失败时直接 sys.exit(2)（内部已写降级
        # 台账）——此处捕获转换为结构化失败，不让整个管道进程被杀。
        return _finish("merge", f"outline.md 解析失败（parse_outline_yaml sys.exit={e.code}）")
    except Exception as e:  # noqa: BLE001
        return _finish("merge", f"outline.md 解析异常: {e}")

    try:
        merged_content = assemble_merged(structure, drafts_dir)
        # 合并后处理：C1 要求至多 1 个 H1（# 标题），但 assemble_merged 按
        # frontmatter 条目生成了多个 H1（如"# 摘要"、"# 关键词与术语说明"）。
        # md2docx 恰好需要一个 H1 作为报告主标题，保留第一个，其余降级为 H2。
        lines = merged_content.split("\n")
        h1_count = 0
        for i, line in enumerate(lines):
            if H1_LINE_PATTERN.match(line):
                h1_count += 1
                if h1_count > 1:
                    lines[i] = "#" + line  # "# 标题" -> "## 标题"
        merged_content = "\n".join(lines)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(merged_content, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return _finish("merge", f"结构驱动合并执行异常: {e}")
    steps["merge"] = {
        "status": "pass",
        "output_path": str(Path(output_path).resolve()),
        "chapters": len(structure.get("bodymatter", [])),
    }

    # ── 步骤 4: convert_refs —— 函数级 import，自行编排 in-place 转换 ──────
    try:
        from convert_references import (
            load_source_index, scan_drafts, find_slash_refs_in_file,
            find_all_refs_in_file, build_numbering, replace_refs_in_file,
            generate_bibliography,
        )
    except ImportError as e:
        return _finish("convert_refs", f"convert_references 模块不可用（import 失败）: {e}")

    try:
        source_index = load_source_index(source_index_path)
    except SystemExit as e:
        # load_source_index 在 CSV 缺失/格式错误时直接 sys.exit(2)——同样捕获
        # 转换为结构化失败。
        return _finish("convert_refs", f"source-index.csv 加载失败（sys.exit={e.code}）")
    except Exception as e:  # noqa: BLE001
        return _finish("convert_refs", f"source-index.csv 加载异常: {e}")

    try:
        # 扫描 drafts_dir 中全部文件 + 确保合并输出文件本身在扫描列表中
        # （与 convert_references.py main() 第 281-292 行 in-place 模式同款约定），
        # 用于构建"按首次出现顺序"的全局编号；但只对 output_path 做实际替换。
        scan_files = scan_drafts(drafts_dir)
        output_abs = os.path.abspath(output_path)
        if output_abs not in [os.path.abspath(f) for f in scan_files]:
            scan_files.append(output_path)

        slash_hits = []
        for fp in scan_files:
            for sr in find_slash_refs_in_file(fp):
                slash_hits.append({"file": fp, "ref": sr})
        if slash_hits:
            return _finish(
                "convert_refs", "检测到斜杠分隔 SRC 引用，转换脚本不支持此格式，需人工修复为逗号分隔",
                detail={"slash_refs": slash_hits},
            )

        refs_by_file = []
        for fp in scan_files:
            refs = find_all_refs_in_file(fp)
            if refs:
                refs_by_file.append((fp, refs))

        if refs_by_file:
            src_to_num, num_to_src, missing = build_numbering(refs_by_file, source_index)
            replace_refs_in_file(output_path, src_to_num, in_place=True)
            bib_text = generate_bibliography(num_to_src, source_index, missing)
            bib_path = os.path.join(str(Path(output_path).parent), "bibliography.md")
            Path(bib_path).write_text(bib_text, encoding="utf-8")
            convert_detail = {
                "unique_sources": len(src_to_num),
                "missing_sources": sorted(missing),
                "bibliography_path": bib_path,
            }
        else:
            convert_detail = {
                "unique_sources": 0, "missing_sources": [], "bibliography_path": None,
                "note": "未检测到 [SRC-XXX] 引用，跳过转换（已是纯数字引用或无可转换引用）",
            }
    except Exception as e:  # noqa: BLE001
        return _finish("convert_refs", f"引用转换执行异常: {e}")
    steps["convert_refs"] = {"status": "pass", **convert_detail}

    # ── 步骤 5: contract_check —— check_contract(merged=True, stage="stage9") ──
    try:
        from contract_check import check_contract, read_text
    except ImportError as e:
        return _finish("contract_check", f"contract_check 模块不可用（import 失败）: {e}")

    try:
        merged_text = read_text(output_path)
        contract_result = check_contract(merged_text, merged=True, expect_figures=None, stage="stage9")
    except Exception as e:  # noqa: BLE001
        return _finish("contract_check", f"合约终检执行异常: {e}")

    if not contract_result["overall_pass"]:
        return _finish(
            "contract_check", "合约终检未通过（高严重度项：C1/C2/C5/C6/C9，stage9 下含 C7）",
            detail=contract_result,
        )
    steps["contract_check"] = {"status": "pass", "detail": contract_result}

    # ── 步骤 6: delivery_checklist —— run_delivery_checklist() ────────────
    try:
        from delivery_checklist_check import run_delivery_checklist
    except ImportError as e:
        return _finish("delivery_checklist", f"delivery_checklist_check 模块不可用（import 失败）: {e}")

    try:
        checklist_result = run_delivery_checklist(
            merged_file=output_path,
            glossary_path=glossary_path,
            drafts_dir=drafts_dir,
            outline_path=outline_path,
            figures_dir=figures_dir,
            redteam_diff_path=redteam_diff_path,
            log_path=log_path,
        )
    except Exception as e:  # noqa: BLE001
        return _finish("delivery_checklist", f"交付清单聚合检查执行异常: {e}")

    if not checklist_result["overall_pass"]:
        return _finish(
            "delivery_checklist", "交付清单聚合检查存在可脚本化项失败",
            detail=checklist_result,
        )
    steps["delivery_checklist"] = {"status": "pass", "detail": checklist_result}

    return {
        "overall_pass": True,
        "failure_step": None,
        "failure_reason": None,
        "steps": steps,
        "output_path": str(Path(output_path).resolve()),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def format_text_report(result: dict) -> str:
    lines = ["=== 阶段9定稿顺序管道（D5，finalize_pipeline）===", ""]
    for step in FAILURE_STEPS:
        info = result["steps"].get(step)
        if info is None:
            lines.append(f"{WARN} {step}: 未执行（前序步骤已阻断）")
            continue
        mark = OK if info.get("status") == "pass" else FAIL
        lines.append(f"{mark} {step}: {info.get('status')}")
        if info.get("status") != "pass":
            lines.append(f"      原因: {info.get('reason')}")
    lines.append("")
    if result["overall_pass"]:
        lines.append(f"=== 总判定: PASS，输出: {result['output_path']} ===")
    else:
        lines.append(f"=== 总判定: FAIL（失败步骤: {result['failure_step']}——{result['failure_reason']}） ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段9定稿顺序管道（D5：剥离标记→H1检测替换→结构驱动合并→引用转换→合约终检→交付清单）"
    )
    parser.add_argument("--drafts-dir", required=True, help="分章草稿目录（如 research/drafts）")
    parser.add_argument("--outline", required=True, help="outline.md 路径")
    parser.add_argument("--source-index", required=True, help="source-index.csv 路径")
    parser.add_argument("--output", required=True, help="合并后输出路径（如 research/drafts/final-report.md）")
    parser.add_argument("--glossary", default=None, help="research/glossary.md 路径（可选，传给 delivery_checklist）")
    parser.add_argument("--figures-dir", default=None, help="research/figures/ 目录（可选，传给 delivery_checklist）")
    parser.add_argument("--redteam-diff", default=None, help="research/redteam-resolution-diff.md 路径（可选）")
    parser.add_argument("--log", default=None, help="降级台账文件路径（可选，覆盖环境变量与默认路径）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not os.path.isdir(args.drafts_dir):
        print(f"{FAIL} drafts-dir 不存在: {args.drafts_dir}", file=sys.stderr)
        sys.exit(2)

    try:
        result = run_finalize_pipeline(
            drafts_dir=args.drafts_dir,
            outline_path=args.outline,
            source_index_path=args.source_index,
            output_path=args.output,
            glossary_path=args.glossary,
            figures_dir=args.figures_dir,
            redteam_diff_path=args.redteam_diff,
            log_path=args.log,
        )
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} 执行失败: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
