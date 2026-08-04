#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_figure_path_map.py —— figure-path-map.json 增量写入与完成确认工具。

用法:
  # 追加一条图片记录
  python update_figure_path_map.py --action add \
      --map-file research/figures/figure-path-map.json \
      --figure-no "1-1" --title "空间环境复杂度演化对比" \
      --type "architecture" --chapter 1 \
      --drawio "research/figures/1-1-xxx.drawio" \
      --drawio-png "research/figures/1-1-xxx.drawio.png" \
      --drawio-svg "research/figures/1-1-xxx.drawio.svg"

  # 完成确认——写入统计并转正
  python update_figure_path_map.py --action finalize \
      --map-file research/figures/figure-path-map.json \
      --total-architecture 42 --total-data 2
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _partial_path(map_file: str) -> str:
    """给定最终 .json 路径，返回对应的 .partial 路径。"""
    if map_file.endswith(".json"):
        return map_file[:-5] + ".json.partial"
    return map_file + ".partial"


def _load_json(path: str) -> dict:
    """加载 JSON 文件，不存在则返回空 dict。"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_json(path: str, data: dict) -> None:
    """写入 JSON 文件（美化输出，确保目录存在）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# action: add
# ---------------------------------------------------------------------------

def action_add(args: argparse.Namespace) -> None:
    """追加一条 figure 记录到 .partial 文件。"""
    partial = _partial_path(args.map_file)
    data = _load_json(partial)

    # 初始化 figures 字典
    if "figures" not in data:
        data["figures"] = {}

    figure_no = args.figure_no

    # 生成 markdown_ref
    png_basename = os.path.basename(args.drawio_png)
    markdown_ref = f"![图{figure_no} {args.title}](figures/{png_basename})"

    entry = {
        "figure_no": figure_no,
        "title": args.title,
        "type": args.type,
        "chapter": args.chapter,
        "files": {
            "drawio": args.drawio,
            "drawio_png": args.drawio_png,
        },
        "markdown_ref": markdown_ref,
    }

    # drawio_svg 是可选的
    if args.drawio_svg:
        entry["files"]["drawio_svg"] = args.drawio_svg

    data["figures"][figure_no] = entry

    _save_json(partial, data)
    print(f"[OK] 已追加图 {figure_no} → {partial}")


# ---------------------------------------------------------------------------
# schema 验证
# ---------------------------------------------------------------------------

REQUIRED_TOP_KEYS = {"figure_no", "title", "type", "files", "markdown_ref"}
REQUIRED_FILE_KEYS = {"drawio_png"}


def _validate_entry(figure_no: str, entry: dict) -> list[str]:
    """验证单条 figure 条目，返回错误信息列表。"""
    errors = []

    # required 顶层字段
    for key in REQUIRED_TOP_KEYS:
        if key not in entry or not entry[key]:
            errors.append(f"图 {figure_no}: 缺少 required 字段 '{key}'")

    # files 子字段
    if "files" in entry and isinstance(entry["files"], dict):
        for key in REQUIRED_FILE_KEYS:
            if key not in entry["files"] or not entry["files"][key]:
                errors.append(f"图 {figure_no}: files 中缺少 required 字段 '{key}'")
    else:
        errors.append(f"图 {figure_no}: 'files' 字段缺失或格式错误")

    # markdown_ref 中的文件名与 files.drawio_png 一致性
    if "markdown_ref" in entry and "files" in entry and isinstance(entry["files"], dict):
        png_path = entry["files"].get("drawio_png", "")
        png_basename = os.path.basename(png_path)
        ref = entry["markdown_ref"]
        # markdown_ref 格式: ![图X-X 标题](figures/xxx.png)
        if png_basename and png_basename not in ref:
            errors.append(
                f"图 {figure_no}: markdown_ref 中的文件名与 files.drawio_png 不一致 "
                f"(expected '{png_basename}' in ref)"
            )

    return errors


def _validate_all(data: dict) -> list[str]:
    """验证整个 figure-path-map 数据，返回所有错误信息列表。"""
    errors = []
    figures = data.get("figures", {})
    if not figures:
        errors.append("figures 字典为空，没有任何图片条目")
    for fig_no, entry in figures.items():
        errors.extend(_validate_entry(fig_no, entry))
    return errors


# ---------------------------------------------------------------------------
# action: finalize
# ---------------------------------------------------------------------------

def action_finalize(args: argparse.Namespace) -> None:
    """完成确认：写入统计、时间戳，schema 验证，原子转正。"""
    partial = _partial_path(args.map_file)

    if not os.path.exists(partial):
        print(f"[ERROR] .partial 文件不存在: {partial}", file=sys.stderr)
        sys.exit(1)

    data = _load_json(partial)

    # Schema 验证
    errors = _validate_all(data)
    if errors:
        print(f"[ERROR] Schema 验证失败 ({len(errors)} 项):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # 写入统计
    data["total_architecture_figures"] = args.total_architecture
    data["total_data_figures"] = args.total_data

    # 写入时间戳
    data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 先写回 .partial
    _save_json(partial, data)

    # 原子转正：重命名 .partial → .json
    final_path = args.map_file
    # 确保目标目录存在
    os.makedirs(os.path.dirname(final_path) or ".", exist_ok=True)
    # Windows 下如果目标已存在需先删除
    if os.path.exists(final_path):
        os.remove(final_path)
    os.rename(partial, final_path)

    total = len(data.get("figures", {}))
    print(
        f"[OK] 已转正: {final_path}\n"
        f"     架构图: {args.total_architecture}, 数据图: {args.total_data}, "
        f"总计: {total}"
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="figure-path-map.json 增量写入与完成确认工具"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["add", "finalize"],
        help="操作类型: add（追加图片记录）/ finalize（完成确认并转正）",
    )
    parser.add_argument(
        "--map-file",
        required=True,
        help="figure-path-map.json 的目标路径（脚本自动处理 .partial 后缀）",
    )

    # add 参数
    parser.add_argument("--figure-no", help="图号（add 必需）")
    parser.add_argument("--title", help="图片标题（add 必需）")
    parser.add_argument(
        "--type", choices=["architecture", "data"], help="图片类型（add 必需）"
    )
    parser.add_argument("--chapter", type=int, help="章节号（add 必需）")
    parser.add_argument("--drawio", help=".drawio 文件路径（add 必需）")
    parser.add_argument("--drawio-png", help=".drawio.png 文件路径（add 必需）")
    parser.add_argument("--drawio-svg", help=".drawio.svg 文件路径（add 可选）")

    # finalize 参数
    parser.add_argument("--total-architecture", type=int, help="finalize 必需")
    parser.add_argument("--total-data", type=int, help="finalize 必需")

    args = parser.parse_args()

    if args.action == "add":
        # 验证 add 必需参数
        missing = []
        for field in ["figure_no", "title", "type", "chapter", "drawio", "drawio_png"]:
            if getattr(args, field.replace("-", "_"), None) is None:
                missing.append(f"--{field}")
        if missing:
            parser.error(f"add 操作缺少参数: {', '.join(missing)}")
        action_add(args)

    elif args.action == "finalize":
        # 验证 finalize 必需参数
        missing = []
        for field in ["total_architecture", "total_data"]:
            if getattr(args, field.replace("-", "_"), None) is None:
                missing.append(f"--{field}")
        if missing:
            parser.error(f"finalize 操作缺少参数: {', '.join(missing)}")
        action_finalize(args)


if __name__ == "__main__":
    main()
