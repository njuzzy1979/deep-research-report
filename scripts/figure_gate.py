#!/usr/bin/env python3
"""图表存在性门禁脚本 —— 全自动文件系统级图表清单检查。

从 outline.md 的 YAML figures_manifest 或 Markdown 正文标记中提取图表规划清单，
逐文件检查 research/figures/ 中的存在性，对 PNG 验证有效性（PIL 可打开）。

作者：deep-research-report skill 图表生成子系统优化 (2026-07-28)
用途：阶段6 CHECKPOINT（架构图完成后）和阶段9转换前（终稿需所有图表就位）各运行一次。
阻断强度：FATAL——exit code 非零即阻断，零人工干预。

用法：
    python scripts/figure_gate.py --outline research/outline.md --figures-dir research/figures/
    python scripts/figure_gate.py --outline research/outline.md --figures-dir research/figures/ --stage stage6
    python scripts/figure_gate.py --outline research/outline.md --figures-dir research/figures/ --stage stage9 --strict
    python scripts/figure_gate.py --help
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

# Windows 中文环境编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from PIL import Image
except ImportError:
    print("错误：需要 Pillow 库。pip install Pillow")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("错误：需要 PyYAML 库。pip install PyYAML")
    sys.exit(1)

# 降级台账（跨模型兼容性优化方案 §二 A2）：figure_gate.py 与 degradation_log.py
# 同处 scripts/ 目录下；容错兜底为 no-op，避免观测性依赖影响主流程。
try:
    from degradation_log import record_degradation
except ImportError:
    def record_degradation(**kwargs):  # type: ignore[no-redef]
        pass


# ---------------------------------------------------------------------------
# YAML figures_manifest 提取
# ---------------------------------------------------------------------------

def extract_manifest_from_yaml(outline_path: Path) -> Optional[dict]:
    """从 outline.md 的 YAML front matter 中提取 figures_manifest 字段。

    返回包含 architecture_figures / data_figures / tables 三个子清单的 dict，
    若 YAML 中不存在 figures_manifest 则返回 None。
    """
    content = outline_path.read_text(encoding="utf-8")
    # 提取 YAML front matter（--- 之间的内容）
    if not content.startswith("---"):
        return None
    # 找到第二个 ---
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return None
    yaml_text = content[3:end_idx].strip()
    try:
        fm = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        # 跨模型兼容性优化方案 §二 A2：原为静默 return None，调用方无法得知
        # 图表清单降级到 Markdown 正文标记提取的原因。这里只补诊断输出和
        # 台账写入，返回值语义（None）保持不变，不改变调用方行为。
        print(
            f"[WARN] figure_gate: outline.md YAML 解析失败，"
            f"figures_manifest 不可用，将回退到 Markdown 正文标记提取: {e}",
            file=sys.stderr,
        )
        record_degradation(
            stage="figure_gate",
            component="figure_gate",
            reason="yaml_parse_failed",
            level="L-显著",
            fallback_used="markdown_body_marker_extraction",
            impact="figures_manifest 不可用，图表清单回退到 Markdown 正文标记提取",
            input_path=str(outline_path),
        )
        return None
    if not isinstance(fm, dict):
        return None
    manifest = fm.get("figures_manifest")
    if manifest is None:
        return None
    # D3-1 入口修复：真实 outline.md 的 figures_manifest 是 **YAML 列表**
    # （`- fig_id: ...`），条目键名为 fig_id/fig_title/fig_type/chapter/
    # description；而本函数原先 `not isinstance(manifest, dict) -> return None`
    # 把 list 判为格式不符直接丢弃 → 清单 total=0 → 下游返回 passed:True →
    # exit 0。真实项目声明了 15 张图，**一张都没检查过**。
    if isinstance(manifest, list):
        return {"architecture_figures": _normalize_list_manifest(manifest, outline_path)}
    if not isinstance(manifest, dict):
        return None
    return manifest


def _normalize_list_manifest(entries: list, outline_path=None) -> list[dict]:
    """把 list 形态 figures_manifest 的条目键名映射为本脚本的内部权威键名。

    映射：``fig_id``→``figure_id``、``fig_title``→``title``、
    ``fig_type`` 含"架构"→``architecture``（否则 ``data``）。
    ``figure_no`` 取 ``fig_id`` 中的 ``N-M`` 形状编号（真实数据形如 ``fig-3-1``
    或直接 ``3-1``），取不到则回落原值——glob_pattern 依赖它。
    """
    import re as _re

    out: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        # 已是权威键名的条目原样通过（混合形态兼容）
        fid = e.get("figure_id") or e.get("fig_id") or "?"
        title = e.get("title") or e.get("fig_title") or ""
        raw_type = str(e.get("fig_type") or e.get("type") or "")
        fno = e.get("figure_no")
        if not fno:
            m = _re.search(r"(\d+-\d+)", str(fid))
            fno = m.group(1) if m else str(fid)
        out.append({
            "figure_id": fid,
            "figure_no": fno,
            "title": title,
            "type": "architecture" if "架构" in raw_type else (
                e.get("type") if e.get("type") in ("architecture", "data") else "data"
            ),
            "tool": e.get("tool", "drawio"),
            "priority": e.get("priority", "required"),
            "chapter": e.get("chapter"),
            "description": e.get("description", ""),
            "output_files": e.get("output_files", []),
            "source": "figures_manifest_list",
        })
    return out


# ---------------------------------------------------------------------------
# Markdown 正文标记提取（无 figures_manifest 时的降级方案）
# ---------------------------------------------------------------------------

def extract_figures_from_markdown_body(outline_text: str) -> list[dict]:
    """从 outline.md 的 Markdown 正文中提取图表规划。

    识别两种标记：
    1. 🏗️ **核心架构图**：图 X-Y ...
    2. **图表规划**：架构图 X-Y / 数据图方向 ...
    """
    figures = []
    # 跳过 YAML front matter
    if outline_text.startswith("---"):
        end_idx = outline_text.find("---", 3)
        if end_idx != -1:
            outline_text = outline_text[end_idx + 3:]

    import re
    # 匹配 "🏗️ **核心架构图**" 后的图号
    arch_section = re.search(r"🏗️.*?核心架构图.*?\n(.*?)(?:\n\n|\n##|\Z)", outline_text, re.DOTALL)
    if arch_section:
        # 提取 "图 X-Y" 模式
        fig_refs = re.findall(r"图\s*(\d+-\d+)", arch_section.group(1))
        for ref in fig_refs:
            figures.append({
                "figure_id": f"fig-arch-{ref}",
                "figure_no": ref,
                "title": f"核心架构图 {ref}",
                "type": "architecture",
                "source": "markdown_body",
            })

    # 匹配 "**图表规划**" 行
    chart_plan_lines = re.findall(
        r"\*\*图表规划\*\*[：:]\s*(.*?)(?:\n|$)",
        outline_text
    )
    for line in chart_plan_lines:
        arch_refs = re.findall(r"架构图\s*(\d+-\d+)", line)
        for ref in arch_refs:
            if not any(f["figure_no"] == ref for f in figures):
                figures.append({
                    "figure_id": f"fig-arch-{ref}",
                    "figure_no": ref,
                    "title": f"架构图 {ref}",
                    "type": "architecture",
                    "source": "markdown_body",
                })
        data_refs = re.findall(r"数据图[：:]\s*(.*?)(?:$|。)", line)
        for desc in data_refs:
            figures.append({
                "figure_id": f"fig-data-{len(figures)}",
                "figure_no": "(阶段7分配)",
                "title": desc.strip(),
                "type": "data",
                "source": "markdown_body",
            })

    return figures


# ---------------------------------------------------------------------------
# 从 figures_manifest YAML 生成扁平文件检查清单
# ---------------------------------------------------------------------------

def _declared_architecture_figure_count(outline_path) -> int:
    """读取 outline.md YAML 中声明的核心架构图张数（``core_architecture_figures``）。

    供"空清单判 FAIL"使用：只有 outline 自己声明了要出图，空清单才是缺陷；
    确实不需要图表的项目不应被误伤。解析不出一律返回 0（宽松侧）。
    """
    try:
        import yaml as _yaml
        text = outline_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return 0
        parts = text.split("---", 2)
        if len(parts) < 3:
            return 0
        fm = _yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return 0
        raw = fm.get("core_architecture_figures")
        if isinstance(raw, bool):
            return 0
        if isinstance(raw, int):
            return raw
        return int(str(raw).strip())
    except Exception:  # noqa: BLE001
        return 0


def build_checklist_from_manifest(manifest: dict, stage: str) -> list[dict]:
    """从 figures_manifest 结构生成统一的文件检查清单。

    每个条目包含 file_pattern（用于 glob 匹配）和元数据。
    """
    checklist = []
    # 架构图：在 stage6 CHECKPOINT 和 stage9 都需要检查
    # stage6 产出为 .drawio 原始文件；stage9 产出为 .png 导出版本
    arch_ext = "drawio" if stage in ("stage6",) else "png"
    for fig in manifest.get("architecture_figures", []):
        fid = fig.get("figure_id", "?")
        fno = fig.get("figure_no", "?")
        checklist.append({
            "figure_id": fid,
            "figure_no": fno,
            "title": fig.get("title", ""),
            "type": "architecture",
            "tool": fig.get("tool", "drawio"),
            "priority": fig.get("priority", "required"),
            "glob_pattern": f"*{fno}*.{arch_ext}",
            "source": "figures_manifest",
        })
    # 数据图表：stage9 才检查（stage6 时尚未产出）
    if stage in ("stage9",):
        for fig in manifest.get("data_figures", []):
            fid = fig.get("figure_id", "?")
            fno = fig.get("figure_no", "?")
            checklist.append({
                "figure_id": fid,
                "figure_no": fno,
                "title": fig.get("title", ""),
                "type": "data",
                "tool": fig.get("tool", "matplotlib"),
                "priority": fig.get("priority", "optional"),
                "glob_pattern": f"*{fno}*.png" if fno != "?" else None,
                "source": "figures_manifest",
            })
    return checklist


# ---------------------------------------------------------------------------
# 文件系统检查
# ---------------------------------------------------------------------------

def _validate_png(png_path: Path) -> tuple:
    """校验单个 PNG，返回 ``(errors, warnings)`` 两个描述列表。

    D3 §3.6：此逻辑原先在 ``check_figure_exists()`` 内**出现两遍**（主 glob 分支
    与模糊回退分支）且**不等价**——主分支多一个 ``w<1 or h<1`` 尺寸异常检查。
    只改一处则另一处成为绕过路径，故抽为单一函数。合并口径取**较严的主分支**。

    dpi 处置：原 ``if dpi[0] and dpi[0] < 300`` 的短路使 dpi 元数据为 ``(0,0)``
    的 PNG 被**静默放行**（真实项目 11/19 张如此）。现改为进入 ``warnings``
    通道——**刻意不进 errors**：实测真实项目 15/15 架构图均无 dpi 元数据，
    若计入硬失败会使门禁 15/15 全红，验收永不通过，反向逼迫实施者放宽门禁
    （D3 §3.4 明确警示的反模式）。warnings 只提升可观测性，不改变 pass/fail。

    DPI 容差：draw.io 桌面版 CLI 导出时 pHYs chunk 使用整数像素/米（11811），
    导致 DPI = 11811 × 0.0254 = 299.9994。为此增加 0.5 浮点容差：
    - dpi < 299.5 → 硬错误 (INVALID)
    - 299.5 ≤ dpi < 300 → 仅 warning，不放行阻断
    """
    errors: list[str] = []
    warnings: list[str] = []
    try:
        img = Image.open(png_path)
        img.verify()
        # verify 后需要重新打开才能读取 size/info
        img = Image.open(png_path)
        w, h = img.size
        dpi = img.info.get("dpi", (0, 0))
    except Exception as e:  # noqa: BLE001
        return [f"{png_path.name}: PIL 无法打开 - {e}"], warnings

    if w < 1 or h < 1:
        errors.append(f"{png_path.name}: 尺寸异常 ({w}x{h})")
    elif w < 1102:
        errors.append(f"{png_path.name}: 宽度 {w}px < 1102px 最低要求")

    if not dpi or not dpi[0]:
        warnings.append(f"{png_path.name}: 缺少 DPI 元数据，无法核验 300dpi 要求")
    elif dpi[0] < 299.5:
        errors.append(f"{png_path.name}: DPI={dpi[0]} < 300")
    elif dpi[0] < 300:
        warnings.append(
            f"{png_path.name}: [WARN] DPI 略低于 300（实测 {dpi[0]:.1f}），"
            f"但仍在容差范围内已放行"
        )
    return errors, warnings


def check_figure_exists(figures_dir: Path, entry: dict) -> dict:
    """检查单个图表条目对应的文件是否存在且有效。

    返回 {figure_id, figure_no, title, type, found, files, valid, errors}
    """
    result = {
        "figure_id": entry["figure_id"],
        "figure_no": entry["figure_no"],
        "title": entry["title"],
        "type": entry["type"],
        "priority": entry.get("priority", "required"),
        "found": False,
        "files": [],
        "valid": False,
        "errors": [],
        "warnings": [],
    }

    pattern = entry.get("glob_pattern")
    if pattern:
        matches = sorted(figures_dir.glob(pattern))
        if matches:
            result["found"] = True
            result["files"] = [m.name for m in matches]
            for png_path in matches:
                if png_path.suffix.lower() == ".drawio":
                    # drawio 文件跳过像素级校验，但标记为有效（已由 drawio_layout_validator 验证）
                    result["valid"] = True
                    continue
                if png_path.suffix.lower() != ".png":
                    continue
                errs, warns = _validate_png(png_path)
                result["errors"].extend(errs)
                result["warnings"].extend(warns)
        else:
            # 尝试模糊匹配（按图号部分匹配）
            fno = entry["figure_no"]
            if fno and fno != "?":
                fuzzy = sorted(figures_dir.glob(f"*{fno.replace('-', '?')}*.png"))
                if not fuzzy:
                    fuzzy = sorted(figures_dir.glob(f"*{fno.replace('-', '')}*.png"))
                if fuzzy:
                    result["found"] = True
                    result["files"] = [m.name for m in fuzzy]
                    for png_path in fuzzy:
                        errs, warns = _validate_png(png_path)
                        result["errors"].extend(errs)
                        result["warnings"].extend(warns)
    # D3-5：删除原 `else: result["found"]=True; result["valid"]=True` 无条件放行分支。
    # 无 glob_pattern 的条目不再被视为"已通过"——它只是"无法定位文件"，
    # 应保持 found=False 由汇总逻辑按 priority 处置。
    # （对真实项目 0 影响：build_checklist_from_manifest 对架构图无条件生成
    #  f"*{fno}*.png"，归一化后 15/15 条目全都有 glob_pattern。）

    result["valid"] = result["found"] and len(result["errors"]) == 0
    return result


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def check_figure_path_consistency(
    outline_path: Path,
    figures_dir: Path,
    merged_md_path: Path = None,
) -> dict:
    """检查图片文件名的三方一致性：manifest vs 磁盘 vs markdown 引用。

    Returns:
        dict: {passed, items[], summary}
    """
    from pathlib import Path as _Path
    import unicodedata as _ud

    items = []
    manifest = extract_manifest_from_yaml(outline_path)
    if not manifest:
        return {"passed": True, "items": [], "summary": "无 figures_manifest，跳过一致性检查"}

    arch_figs = manifest.get("architecture_figures", [])
    all_entries = list(arch_figs)

    if not all_entries:
        return {"passed": True, "items": [], "summary": "figures_manifest 为空"}

    # 收集 markdown 引用路径
    md_refs = {}  # figure_no → set of referenced basenames
    if merged_md_path and _Path(merged_md_path).exists():
        import re as _re
        md_text = _Path(merged_md_path).read_text(encoding="utf-8", errors="replace")
        for m in _re.finditer(r'!\[图\s*(\d+-\d+)[^\]]*\]\(([^)]+)\)', md_text):
            fno = m.group(1)
            ref_path = m.group(2)
            ref_basename = _Path(ref_path).name
            md_refs.setdefault(fno, set()).add(ref_basename)

    for entry in all_entries:
        fno = entry.get("figure_no", "?")
        output_files = entry.get("output_files", [])
        # 从 output_files 提取期望的 .png 文件名
        expected_names = {_Path(f).name for f in output_files if f.endswith('.png')}

        item = {
            "figure_id": entry.get("figure_id", "?"),
            "figure_no": fno,
            "title": entry.get("title", ""),
            "passed": True,
            "issues": [],
        }

        # 检查1: manifest 声明的精确文件名在磁盘上是否存在
        disk_matches = set()
        for ename in expected_names:
            fp = figures_dir / ename
            if fp.exists():
                disk_matches.add(ename)
            else:
                item["passed"] = False
                item["issues"].append(
                    f"[FATAL] manifest 声明文件不存在: {ename}"
                )

        # 检查2: markdown 引用的 basename 与磁盘文件名是否一致
        refs = md_refs.get(fno, set())
        for ref in refs:
            disk_path = figures_dir / ref
            if not disk_path.exists():
                item["passed"] = False
                item["issues"].append(
                    f"[FATAL] markdown 引用文件不存在: {ref}"
                )
            elif expected_names and ref not in expected_names:
                item["issues"].append(
                    f"[WARN] markdown 引用 {ref} 与 manifest 声明不一致，"
                    f"manifest 声明: {expected_names}"
                )

        # 检查3: glob 诊断——列出磁盘上同图号的实际文件
        if fno and fno != "?":
            glob_matches = sorted(figures_dir.glob(f"*{fno}*.png"))
            if len(glob_matches) > 1 and not item["passed"]:
                item["issues"].append(
                    f"[INFO] 磁盘上存在 {len(glob_matches)} 个同图号文件: "
                    f"{[p.name for p in glob_matches]}"
                )

        items.append(item)

    failed = [i for i in items if not i["passed"]]
    return {
        "passed": len(failed) == 0,
        "items": items,
        "failed_count": len(failed),
        "summary": (
            f"三方一致性: {len(items) - len(failed)}/{len(items)} 通过"
            if items else "无条目可检查"
        ),
    }


def run_figure_gate(
    outline_path: Path,
    figures_dir: Path,
    stage: str = "stage6",
    strict: bool = False,
    markdown_path: Path = None,
    check_consistency: bool = False,
) -> dict:
    """运行图表门禁检查。

    Args:
        outline_path: outline.md 文件路径
        figures_dir: research/figures/ 目录路径
        stage: "stage6"（仅架构图）或 "stage9"（架构图+数据图表）
        strict: 严格模式——optional 图表缺失也报 FAIL

    Returns:
        {passed, total, found, missing, invalid, items, stage}
    """
    if not outline_path.exists():
        return {
            "passed": False,
            "total": 0, "found": 0, "missing": 0, "invalid": 0,
            "items": [],
            "stage": stage,
            "error": f"outline.md 不存在: {outline_path}",
        }

    if not figures_dir.exists():
        return {
            "passed": False,
            "total": 0, "found": 0, "missing": 0, "invalid": 0,
            "items": [],
            "stage": stage,
            "error": f"figures/ 目录不存在: {figures_dir}",
        }

    # 1. 试图从 YAML figures_manifest 提取
    manifest = extract_manifest_from_yaml(outline_path)
    if manifest:
        checklist = build_checklist_from_manifest(manifest, stage)
        source = "figures_manifest"
    else:
        # 2. 降级：从 Markdown 正文标记提取
        outline_text = outline_path.read_text(encoding="utf-8")
        raw_figures = extract_figures_from_markdown_body(outline_text)
        checklist = [
            {
                "figure_id": f["figure_id"],
                "figure_no": f["figure_no"],
                "title": f["title"],
                "type": f["type"],
                "tool": "unknown",
                "priority": "required" if f["type"] == "architecture" else "optional",
                "glob_pattern": f"*{f['figure_no']}*.png" if f["figure_no"] != "(阶段7分配)" else None,
                "source": "markdown_body",
            }
            for f in raw_figures
        ]
        source = "markdown_body"

    if not checklist:
        # D3-1 第 2 条：清单为空时**不再一律 PASS**。原先无条件返回
        # passed:True → exit 0，是"门禁存在但从不生效"的典型形态：真实项目
        # outline 明写 core_architecture_figures: 15，却因入口解析失败得到
        # 空清单并静默放行。stage9 且 outline 声明了图表数 > 0 时判 FAIL。
        declared = _declared_architecture_figure_count(outline_path)
        if declared > 0:
            return {
                "passed": False,
                "total": 0, "found": 0, "missing": declared, "invalid": 0,
                "items": [],
                "stage": stage,
                "source": source,
                "error": (
                    f"outline.md 声明了 {declared} 张核心架构图"
                    f"（core_architecture_figures），但解析出的图表检查清单为空——"
                    f"figures_manifest 键名/结构与本脚本预期不符，门禁实际未检查任何图表。"
                    f"请检查 outline.md 的 figures_manifest 格式"
                ),
            }
        return {
            "passed": True,
            "total": 0, "found": 0, "missing": 0, "invalid": 0,
            "items": [],
            "stage": stage,
            "source": source,
            "note": "未找到图表规划清单（outline.md 中无 figures_manifest 且 Markdown 正文中无图表标记），且 outline 未声明图表数",
        }

    # 3. 逐项检查
    results = []
    for entry in checklist:
        result = check_figure_exists(figures_dir, entry)
        results.append(result)

    # 4. 汇总
    required_results = [r for r in results if r["priority"] == "required"]
    optional_results = [r for r in results if r["priority"] != "required"]

    missing_required = [r for r in required_results if not r["found"]]
    invalid_required = [r for r in required_results if r["found"] and not r["valid"]]
    missing_optional = [r for r in optional_results if not r["found"]]
    invalid_optional = [r for r in optional_results if r["found"] and not r["valid"]]

    if strict:
        missing_total = missing_required + missing_optional
        invalid_total = invalid_required + invalid_optional
    else:
        missing_total = missing_required
        invalid_total = invalid_required

    passed = len(missing_total) == 0 and len(invalid_total) == 0

    consistency_result = None
    if check_consistency:
        consistency_result = check_figure_path_consistency(
            outline_path, figures_dir, markdown_path
        )

    return {
        "passed": passed,
        "total": len(checklist),
        "found": sum(1 for r in results if r["found"]),
        "missing": len(missing_total),
        "invalid": len(invalid_total),
        "missing_items": [
            {"figure_id": r["figure_id"], "figure_no": r["figure_no"],
             "title": r["title"], "type": r["type"]}
            for r in missing_total
        ],
        "invalid_items": [
            {"figure_id": r["figure_id"], "figure_no": r["figure_no"],
             "title": r["title"], "type": r["type"], "errors": r["errors"]}
            for r in invalid_total
        ],
        "optional_missing": [
            {"figure_id": r["figure_id"], "figure_no": r["figure_no"],
             "title": r["title"], "type": r["type"]}
            for r in missing_optional
        ],
        "items": results,
        "stage": stage,
        "source": source,
        "consistency": consistency_result,
    }


def format_report(result: dict) -> str:
    """格式化门禁报告为可读文本。"""
    lines = [
        f"{'='*60}",
        f"图表门禁报告 (figure_gate) — 阶段: {result['stage']}",
        f"{'='*60}",
        "",
    ]

    if "error" in result:
        lines.append(f"[FAIL] 致命错误: {result['error']}")
        return "\n".join(lines)

    if "note" in result:
        lines.append(f"[INFO] {result['note']}")
        return "\n".join(lines)

    lines.append(f"来源: {result.get('source', 'unknown')}")
    lines.append(f"图表规划总数: {result['total']}")
    lines.append(f"  已找到且有效: {result['found'] - result['invalid']}")
    lines.append(f"  缺失: {result['missing']}")
    lines.append(f"  存在但无效: {result['invalid']}")
    lines.append("")

    if result["missing_items"]:
        lines.append("--- 缺失图表 (FATAL) ---")
        for item in result["missing_items"]:
            lines.append(
                f"  [MISSING] {item['type']} 图 {item['figure_no']}: "
                f"{item['title']}"
            )
        lines.append("")

    if result["invalid_items"]:
        lines.append("--- 无效图表 (FATAL) ---")
        for item in result["invalid_items"]:
            lines.append(
                f"  [INVALID] {item['type']} 图 {item['figure_no']}: "
                f"{item['title']}"
            )
            for err in item["errors"]:
                lines.append(f"    -> {err}")
        lines.append("")

    if result.get("optional_missing"):
        lines.append("--- 可选图表缺失 (WARN, 非阻断) ---")
        for item in result["optional_missing"]:
            lines.append(
                f"  [WARN] {item['type']} 图 {item['figure_no']}: "
                f"{item['title']}"
            )
        lines.append("")

    # 逐项详情
    lines.append("--- 逐项详情 ---")
    for item in result["items"]:
        status = "[OK]" if item["valid"] else (
            "[MISSING]" if not item["found"] else "[INVALID]"
        )
        priority_mark = " *" if item.get("priority") == "required" else ""
        lines.append(
            f"  {status}{priority_mark} {item['type']} 图 {item['figure_no']}: "
            f"{item['title']}"
        )
        if item["files"]:
            lines.append(f"         文件: {', '.join(item['files'])}")
        if item["errors"]:
            for err in item["errors"]:
                lines.append(f"         问题: {err}")

    lines.append("")
    if result["passed"]:
        lines.append("=== 总判定: PASS ===")
    else:
        lines.append("=== 总判定: FAIL (存在缺失或无效的必选图表) ===")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="图表存在性门禁 —— 全自动文件系统级图表清单检查。"
    )
    parser.add_argument(
        "--outline", required=True,
        help="outline.md 文件路径（含 YAML figures_manifest 和图表规划标记）"
    )
    parser.add_argument(
        "--figures-dir", default="research/figures",
        help="figures/ 目录路径（默认: research/figures）"
    )
    parser.add_argument(
        "--stage", choices=["stage6", "stage9"], default="stage6",
        help="检查阶段: stage6（仅架构图）| stage9（架构图+数据图表，默认: stage6）"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="严格模式: 可选图表缺失也报 FAIL"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="输出 JSON 格式"
    )

    args = parser.parse_args()

    outline_path = Path(args.outline)
    figures_dir = Path(args.figures_dir)

    result = run_figure_gate(
        outline_path=outline_path,
        figures_dir=figures_dir,
        stage=args.stage,
        strict=args.strict,
    )

    if args.json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
