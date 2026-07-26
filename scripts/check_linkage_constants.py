#!/usr/bin/env python3
"""check_linkage_constants.py —— SSOT 数值一致性校验脚本

扫描各引用文件中的 HTML 注释标记 `<!-- linkage-const:<key>:<value> -->`，
与 `linkage-constants.json` 中的 SSOT 定义比对，报告不一致处。

设计原则（见 linkage-maintenance-optimization-proposal.md §7.3 修订 #3）：
- 不朴素 grep 纯数字——grep "46" 会在每份 Markdown 文件中命中大量无关数字（页码、年份、百分比等）
- 改为解析人工预置的 HTML 注释标记——误报率接近零

退出码：
    0 — 全部一致
    1 — 存在标记值与 JSON SSOT 不一致（ERROR）
    2 — 运行出错（文件缺失/JSON 格式错误）
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ── 常量 ──────────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parent.parent
CONSTANTS_FILE = SKILL_ROOT / "linkage-constants.json"

# 匹配两种注释格式的 linkage-const 标记：
#   HTML:     <!-- linkage-const:<key>:<value> -->
#   Python:   # linkage-const:<key>:<value>
MARKER_RE = re.compile(r"(?:<!--|#)\s*linkage-const:(\S+?):(\d+)\s*(?:-->)?")


def load_constants_json(path: Path) -> Dict[str, dict]:
    """加载 linkage-constants.json，返回 {key: {value, description, marker_files}} 字典。"""
    if not path.exists():
        print(f"[FATAL] 配置文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[FATAL] JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(2)
    constants = data.get("constants", {})
    return {k: {"value": v["value"], "files": v.get("marker_files", [])} for k, v in constants.items()}


def scan_markers_in_file(filepath: Path) -> List[Tuple[str, int, int]]:
    """扫描单个文件中的 linkage-const 标记，返回 [(key, value_in_marker, line_number), ...]。

    若文件不存在则跳过（标记文件列表中的某些文件可能尚未创建）。
    """
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[WARN] 无法读取 {filepath}: {e}", file=sys.stderr)
        return []
    results = []
    for i, line in enumerate(lines, start=1):
        for m in MARKER_RE.finditer(line):
            key = m.group(1)
            value = int(m.group(2))
            results.append((key, value, i))
    return results


def check_all(constants: Dict[str, dict]) -> int:
    """主校验逻辑。返回值: 0=全部通过, 1=有不一致。"""
    exit_code = 0
    total_markers = 0
    mismatches = 0
    missing_keys = []

    # 对每个常量的每个 marker_file 扫描标记
    for key, spec in constants.items():
        expected_value = spec["value"]
        found_in_files = set()

        for rel_path in spec["files"]:
            filepath = SKILL_ROOT / rel_path
            markers = scan_markers_in_file(filepath)
            found = False
            for mk_key, mk_val, line_no in markers:
                if mk_key == key:
                    total_markers += 1
                    found = True
                    found_in_files.add(rel_path)
                    if mk_val != expected_value:
                        mismatches += 1
                        print(
                            f"[ERROR] {rel_path}:{line_no}"
                            f"  key={key}"
                            f"  marker_value={mk_val}"
                            f"  expected_value={expected_value}"
                        )
            if not found and filepath.exists():
                print(
                    f"[WARN] {rel_path}"
                    f"  文件存在但未找到 key='{key}' 的标记（应有 <!-- linkage-const:{key}:{expected_value} -->）"
                )

        # 检查标记文件列表中哪些文件未包含此 key
        expected_files = set(spec["files"])
        missing = expected_files - found_in_files
        # 只对已存在的文件报告缺失；不存在的文件已由 scan_markers_in_file 静默跳过
        for mf in sorted(missing):
            fp = SKILL_ROOT / mf
            if fp.exists():
                missing_keys.append((key, mf, expected_value))

    # 汇总报告
    print(f"[INFO] 扫描完成: {total_markers} 个标记, {mismatches} 处不一致")

    if missing_keys:
        print("[WARN] 以下文件在 marker_files 中但缺少对应标记（可能是 P0 新增文件、标记尚未添加）：")
        for key, mf, exp_val in sorted(missing_keys):
            print(f"  {mf}  ← 缺少 <!-- linkage-const:{key}:{exp_val} -->")

    if mismatches > 0:
        exit_code = 1
        print(f"\n[RESULT] FAIL — {mismatches} 处标记值与 linkage-constants.json 不一致")
    else:
        print("[RESULT] PASS — 所有标记值与 linkage-constants.json 一致")

    if missing_keys:
        print(f"[RESULT] 另有 {len(missing_keys)} 个预期标记缺失（非阻塞，建议补加）")

    return exit_code


def main():
    constants = load_constants_json(CONSTANTS_FILE)
    print(f"[INFO] 加载 {len(constants)} 个常量定义: {', '.join(constants.keys())}")
    sys.exit(check_all(constants))


if __name__ == "__main__":
    main()
