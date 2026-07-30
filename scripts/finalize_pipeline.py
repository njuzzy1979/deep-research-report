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
import hashlib
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

# failure_step 枚举（方案 §D5 原有 6 个固定值 + D2-7 新增第 7 步 verify_docx，
# 顺序即执行顺序）。verify_docx 只在传入 --verify-docx 时执行。
FAILURE_STEPS = (
    "strip_markers", "h1_check", "merge", "convert_refs",
    "contract_check", "delivery_checklist", "verify_docx",
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


def _promote_partial(partial_path: Path, final_path: Path) -> None:
    """把 ``.partial`` 原子转正。必须与最终目标同目录（避免跨卷 rename）。

    D2-8 核心不变量：**正式产物名的存在本身即等价于 overall_pass=True**，
    不需要任何人去判断。事故中管线失败却留下 388 字符的空 final-report.md，
    直接诱发了下游"我来手动修一下"的绕行行为。
    """
    try:
        os.replace(partial_path, final_path)  # 同盘原子，无中间态
    except PermissionError as e:
        # WinError 5：目标被占用（用户正开着 Word/VSCode 看上一版报告）
        raise RuntimeError(
            f"无法覆盖 {final_path}：文件正被其他程序占用。"
            f"请关闭后重跑。半成品已保留在 {partial_path}"
        ) from e
    except OSError as e:
        # EXDEV：跨卷 rename
        raise RuntimeError(
            f"跨卷移动失败（{partial_path} 与 {final_path} 不在同一磁盘）。"
            f"请将输出路径指向与草稿同盘的路径"
        ) from e


def _partial_path_for(output_path: str) -> Path:
    """``.partial`` 必须与最终目标**同目录**生成（否则转正时跨卷 rename 失败）。"""
    p = Path(output_path)
    return p.with_name(p.name + ".partial")


def _mark_stale_output(final_path: Path, run_id: str) -> Optional[str]:
    """失败且上次成功的正式产物仍在时，**主动改名**为 .stale-<run_id>。

    仅告警不够：用户不一定会去读告警，仍会拿旧产物当本次结果交付
    （事故中 output/ 下两个 docx 混放正是此形态）。
    """
    if not final_path.exists():
        return None
    stale = final_path.with_name(f"{final_path.name}.stale-{run_id}")
    try:
        os.replace(final_path, stale)
        return str(stale)
    except OSError:
        return None


def _derive_run_id(outline_path: str, drafts_dir: str) -> str:
    """由 outline + drafts 文件名派生 12 位 hex，**确定性、不用随机数/时间戳**。

    非确定性 run_id 会打破 md2docx 的 G-11 幂等要求
    （``00-master-design.md:202``）。
    """
    h = hashlib.sha1()
    try:
        h.update(Path(outline_path).read_bytes())
    except OSError:
        h.update(outline_path.encode("utf-8"))
    for fp in sorted(Path(drafts_dir).glob("ch*.md")):
        h.update(fp.name.encode("utf-8"))
    return h.hexdigest()[:12]


def verify_docx_structure(docx_path: str, expected_chapters: int) -> dict:
    """打开生成的 docx 回读，断言结构不变量（D2-7）。

    **为什么必须是 docx 层校验**：用户投诉的"章节都是空的"这一症状，在 md
    层面**无法发现**——``## 第X章`` 紧跟 ``## 本章结论`` 在 Markdown 里是完全
    合法的结构。只有渲染成 docx 才暴露为"Heading 1 下 0 字符"。

    实测背景：``finalize_pipeline`` 第 6 步结束后直接 return，docx 生成完全在
    管线之外（是 ``stage-9-finalize.md`` 里的一段 bash 示例），**最终交付物
    从未被任何门禁检查过**。

    ⚠ 正文收集**只累加非标题样式段落**：原设计的 ``elif prev is not None:``
    会把 ``Heading 2`` 的标题文本当作正文收集（``"Heading 2" != "Heading 1"``
    故走了 elif），后果是只要某个 ``Heading 1`` 后面跟着任一非空 ``Heading 2``，
    该章即被判为"有正文"。实测把原版跑在一份"只有封面+TOC+H1/H2、完全无正文"
    的骨架 docx 上得 ``pass=True``——即能捕获本次事故形态（H1 紧跟 H1），却
    捕获不到"全文只有骨架"形态。加 ``not startswith("Heading")`` 后修复。
    """
    try:
        from docx import Document
    except ImportError as e:  # noqa: BLE001
        return {"pass": False, "error": f"python-docx 不可用: {e}"}

    try:
        d = Document(docx_path)
    except Exception as e:  # noqa: BLE001
        return {"pass": False, "error": f"无法打开 docx: {e}"}

    h1s: list = []
    empty: list = []
    prev = None
    buf: list = []
    for p in d.paragraphs:
        style_name = p.style.name if p.style is not None else ""
        if style_name == "Heading 1":
            if prev is not None and not "".join(buf).strip():
                empty.append(prev)
            h1s.append(p.text)
            prev, buf = p.text, []
        elif prev is not None and not style_name.startswith("Heading"):
            buf.append(p.text)
    if prev is not None and not "".join(buf).strip():
        empty.append(prev)

    dup = sorted(t for t in set(h1s) if h1s.count(t) > 1)
    return {
        "pass": not empty and not dup and len(h1s) == expected_chapters,
        "empty_headings": empty,          # ← 直接对应用户投诉"章节都是空的"
        "duplicate_headings": dup,        # ← 13 个"本章结论"
        "h1_count": len(h1s),
        "expected": expected_chapters,
    }


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
    delivery_dir: Optional[str] = None,
    verify_docx_path: Optional[str] = None,
) -> dict:
    """执行 6 步定稿顺序管道，任一步失败立即提前 return（不同于
    precommit_consistency_check.py 的"最后统一 derive_overall"模式——本管道
    6 步顺序强依赖，后续步骤依赖前面步骤产出的文件，continue 没有意义）。"""
    steps: dict = {}
    run_id = _derive_run_id(outline_path, drafts_dir)
    # D2-8：全程写 .partial，6 步全通过后才原子 rename 转正。失败时 .partial
    # **保留不删**（供诊断与断点续传），正式产物名永不出现半成品。
    partial_path = _partial_path_for(output_path)
    work_path = str(partial_path)

    def _finish(failure_step: str, reason: str, detail: Optional[dict] = None) -> dict:
        entry = {"status": "fail", "reason": reason}
        if detail is not None:
            entry["detail"] = detail
        steps[failure_step] = entry
        # 失败时把上次成功的正式产物改名为 .stale-<run_id>，避免被当作本次结果
        stale = _mark_stale_output(Path(output_path), run_id)
        return {
            "overall_pass": False,
            "failure_step": failure_step,
            "failure_reason": reason,
            "steps": steps,
            "output_path": None,
            "run_id": run_id,
            "partial_path": str(partial_path) if partial_path.exists() else None,
            "staled_previous_output": stale,
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
        # 键名归一化已下沉到 merge_drafts.parse_outline_yaml()（D1-1 调用点 3）。
        # 原先此处有一份就地 mutate 的适配层（int(item.get("section_no","?"))
        # 对**已合规**输入必抛 ValueError，且适配结果只喂给 assemble_merged、
        # 没有流到 md2docx 的 lookup），两处适配必然漂移，已整段删除。
        structure = parse_outline_yaml(outline_path)
    except SystemExit as e:
        # parse_outline_yaml 在 YAML 解析失败时直接 sys.exit(2)（内部已写降级
        # 台账）——此处捕获转换为结构化失败，不让整个管道进程被杀。
        return _finish("merge", f"outline.md 解析失败（parse_outline_yaml sys.exit={e.code}）")
    except Exception as e:  # noqa: BLE001
        # 文案须区分"outline 内容有问题"与"键名适配/归一化脚本有问题"：原文案
        # 统一写"outline.md 解析异常"，而 int("?") 实际崩在适配层代码里，
        # 用户照文案只会去改 outline，缺陷却在脚本（D2-5 同步修正项）。
        return _finish(
            "merge",
            f"outline.md 结构读取/键名归一化异常（若 outline.md 语法正常，"
            f"则缺陷在 parse_outline_yaml/normalize_outline_structure 而非 outline 内容）: {e}",
        )

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
        Path(work_path).parent.mkdir(parents=True, exist_ok=True)
        Path(work_path).write_text(merged_content, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return _finish("merge", f"结构驱动合并执行异常: {e}")
    steps["merge"] = {
        "status": "pass",
        "output_path": str(Path(output_path).resolve()),
        "partial_path": str(partial_path),
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
        output_abs = os.path.abspath(work_path)
        if output_abs not in [os.path.abspath(f) for f in scan_files]:
            scan_files.append(work_path)

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
            replace_refs_in_file(work_path, src_to_num, in_place=True)
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
        merged_text = read_text(work_path)
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
            merged_file=work_path,
            glossary_path=glossary_path,
            drafts_dir=drafts_dir,
            outline_path=outline_path,
            figures_dir=figures_dir,
            redteam_diff_path=redteam_diff_path,
            log_path=log_path,
            output_dir=delivery_dir,
        )
    except Exception as e:  # noqa: BLE001
        return _finish("delivery_checklist", f"交付清单聚合检查执行异常: {e}")

    if not checklist_result["overall_pass"]:
        return _finish(
            "delivery_checklist", "交付清单聚合检查存在可脚本化项失败",
            detail=checklist_result,
        )
    steps["delivery_checklist"] = {"status": "pass", "detail": checklist_result}

    # ── 步骤 7: verify_docx —— 交付物结构回读校验（D2-7）─────────────────
    # 只对**实际传入的 docx 路径**生效（即 emit_delivery 写出的产物）。
    # 骨架 docx（D1-8）走独立入口、不经本管线，故天然不在检查范围内——
    # **零新增豁免逻辑**，不得按文件名正则豁免（理由见 D3 §六：按文件名判定
    # 会颠倒，违规的 SCIF_V1.0.docx 命中而合规的 final-report.docx 反而不被识别）。
    if verify_docx_path:
        expected_chapters = len(structure.get("bodymatter", []))
        docx_result = verify_docx_structure(verify_docx_path, expected_chapters)
        if not docx_result.get("pass"):
            return _finish(
                "verify_docx",
                "docx 结构回读校验未通过（空章标题/重复章标题/章数不符）",
                detail=docx_result,
            )
        steps["verify_docx"] = {"status": "pass", "detail": docx_result}

    # ── 全部通过：.partial 原子转正 ────────────────────────────────────────
    # 只有走到这一行才产生正式产物名，故"正式产物存在"即等价于 overall_pass。
    try:
        _promote_partial(partial_path, Path(output_path))
    except RuntimeError as e:
        return _finish("delivery_checklist", f"产物转正失败: {e}")

    return {
        "overall_pass": True,
        "failure_step": None,
        "failure_reason": None,
        "steps": steps,
        "output_path": str(Path(output_path).resolve()),
        "run_id": run_id,
        "partial_path": None,
        "staled_previous_output": None,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def format_text_report(result: dict) -> str:
    lines = ["=== 阶段9定稿顺序管道（D5，finalize_pipeline）===", ""]
    for step in FAILURE_STEPS:
        info = result["steps"].get(step)
        if info is None:
            if step == "verify_docx":
                # 第 7 步是可选步：未传 --verify-docx 时不算"被阻断"
                lines.append(f"{WARN} {step}: 未执行（未传 --verify-docx，docx 未被回读校验）")
            else:
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
    # 注意与既有 --output 区分：--output 是合并后 Markdown 路径，--output-dir 是
    # 最终交付物目录（docx/转换报告落位处）。符号一律用 delivery_ 前缀承接。
    parser.add_argument(
        "--output-dir", default=None,
        help="交付目录（如 output/），区别于 --output（合并后 Markdown 路径）",
    )
    parser.add_argument(
        "--verify-docx", dest="verify_docx", default=None,
        help="已生成的交付 docx 路径。传入时执行第 7 步 verify_docx 结构回读校验"
             "（D2-7：断言每个 Heading 1 下有非空正文、无重复章标题、章数与 outline 一致）",
    )
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
            delivery_dir=args.output_dir,
            verify_docx_path=args.verify_docx,
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
