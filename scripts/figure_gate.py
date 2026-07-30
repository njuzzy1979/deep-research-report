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
    # figures_manifest 存在但格式不符合预期（如列表而非
    # {architecture_figures: [...], data_figures: [...]} 字典结构），
    # 回退到 Markdown 正文标记提取，避免下游 build_checklist_from_manifest
    # 对非 dict 对象调用 .get() 导致 AttributeError。
    if manifest is not None and not isinstance(manifest, dict):
        return None
    return manifest


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

def build_checklist_from_manifest(manifest: dict, stage: str) -> list[dict]:
    """从 figures_manifest 结构生成统一的文件检查清单。

    每个条目包含 file_pattern（用于 glob 匹配）和元数据。
    """
    checklist = []
    # 架构图：在 stage6 CHECKPOINT 和 stage9 都需要检查
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
            "glob_pattern": f"*{fno}*.png",
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
    }

    pattern = entry.get("glob_pattern")
    if pattern:
        matches = sorted(figures_dir.glob(pattern))
        if matches:
            result["found"] = True
            result["files"] = [m.name for m in matches]
            # 验证找到的 PNG 文件
            for png_path in matches:
                if png_path.suffix.lower() != ".png":
                    continue
                try:
                    img = Image.open(png_path)
                    img.verify()
                    # 重新打开（verify 后需要重新加载）
                    img = Image.open(png_path)
                    w, h = img.size
                    dpi = img.info.get("dpi", (0, 0))
                    if w < 1 or h < 1:
                        result["errors"].append(f"{png_path.name}: 尺寸异常 ({w}x{h})")
                    elif w < 1102:
                        result["errors"].append(
                            f"{png_path.name}: 宽度 {w}px < 1102px 最低要求"
                        )
                    if dpi[0] and dpi[0] < 300:
                        result["errors"].append(
                            f"{png_path.name}: DPI={dpi[0]} < 300"
                        )
                except Exception as e:
                    result["errors"].append(f"{png_path.name}: PIL 无法打开 - {e}")
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
                        try:
                            img = Image.open(png_path)
                            img.verify()
                            img = Image.open(png_path)
                            w, h = img.size
                            dpi = img.info.get("dpi", (0, 0))
                            if w < 1102:
                                result["errors"].append(
                                    f"{png_path.name}: 宽度 {w}px < 1102px"
                                )
                            if dpi[0] and dpi[0] < 300:
                                result["errors"].append(
                                    f"{png_path.name}: DPI={dpi[0]} < 300"
                                )
                        except Exception as e:
                            result["errors"].append(f"{png_path.name}: 无效 - {e}")
    else:
        # 无明确文件模式（如阶段4只写方向的数据图）
        result["found"] = True  # 标记为"未规划具体文件"
        result["valid"] = True

    result["valid"] = result["found"] and len(result["errors"]) == 0
    return result


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def run_figure_gate(
    outline_path: Path,
    figures_dir: Path,
    stage: str = "stage6",
    strict: bool = False,
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
        return {
            "passed": True,
            "total": 0, "found": 0, "missing": 0, "invalid": 0,
            "items": [],
            "stage": stage,
            "source": source,
            "note": "未找到图表规划清单（outline.md 中无 figures_manifest 且 Markdown 正文中无图表标记）",
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
