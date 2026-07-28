#!/usr/bin/env python3
"""跨项目通用的引用转换脚本 —— [SRC-XXX] → [N] 纯数字引用 + 生成统一参考文献列表。

将 Writer 阶段产出的 [SRC-XXX] 工作格式引用转换为交付阶段的 [N] 纯数字引用，
同时基于 source-index.csv 生成全报告统一的 GB/T 7714-2015 格式参考文献列表（bibliography.md）。

用法：
  python scripts/convert_references.py \
    --drafts-dir research/drafts \
    --source-index research/sources/source-index.csv \
    --output research/drafts

功能：
  1. 扫描 --drafts-dir 中所有 .md 文件，提取所有 [SRC-XXX] 引用
  2. 从 --source-index 读取来源元数据（source_id → 文献题名/作者/出版信息）
  3. 按首次出现顺序为每个 SRC-XXX 分配全局编号 [1], [2], ...
  4. 将所有 [SRC-XXX] 替换为 [N]（逗号分隔多引用：SRC-001,SRC-003 → [1,3]）
  5. 检测并报错斜杠分隔引用（[SRC-001/026]）——不支持，提示手动修复
  6. 幂等性保护：已是 [N] 纯数字格式的引用跳过转换
  7. 生成 bibliography.md（GB/T 7714-2015 格式参考文献列表）
  8. 输出转换报告：转换的引用数 / 未找到的来源 / 斜杠引用数

退出码：0 = 成功；1 = 存在斜杠分隔引用需手动修复；2 = source-index.csv 缺失或格式错误。
"""

import sys
import re
import csv
import argparse
import os
from pathlib import Path
from collections import OrderedDict

# Windows 中文环境编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── 模式定义 ────────────────────────────────────────────
# SRC 引用：单引用 + 多引用（逗号分隔）
SRC_REF_PATTERN = re.compile(r"\[SRC-\d+(?:\s*,\s*SRC-\d+)*\]")
# 斜杠分隔 SRC —— 不支持，需报错
SLASH_SRC_PATTERN = re.compile(r"\[SRC-\d+(?:\s*/\s*SRC-\d+)+\]")
# 单个 SRC 编号提取
SRC_ID_PATTERN = re.compile(r"SRC-(\d+)")
# 纯数字引用（幂等性检测）
PURE_NUM_REF_PATTERN = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def load_source_index(csv_path: str) -> dict:
    """从 source-index.csv 读取来源元数据。
    返回 {source_id: {title, author_or_org, publisher, publish_date, ...}}。
    """
    index = {}
    if not os.path.exists(csv_path):
        print(f"ERROR: source-index.csv 不存在: {csv_path}", file=sys.stderr)
        sys.exit(2)

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required_cols = {"source_id", "title"}
        if not required_cols.issubset(reader.fieldnames or []):
            print(f"ERROR: source-index.csv 缺少必要列 {required_cols}；现有列: {reader.fieldnames}", file=sys.stderr)
            sys.exit(2)
        for row in reader:
            sid = row.get("source_id", "").strip()
            if sid:
                index[sid] = row
    return index


def scan_drafts(drafts_dir: str) -> list:
    """扫描 drafts 目录中的 .md 文件，按文件名排序返回路径列表。"""
    draft_files = sorted(Path(drafts_dir).glob("*.md"))
    if not draft_files:
        print(f"WARNING: {drafts_dir} 中未找到 .md 文件", file=sys.stderr)
    return [str(f) for f in draft_files]


def find_all_refs_in_file(file_path: str) -> list:
    """从单个文件中提取所有 [SRC-XXX] 引用（按出现顺序，去重保留首次顺序）。"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    refs = []
    seen = set()
    for match in SRC_REF_PATTERN.finditer(text):
        ref_text = match.group(0)
        if ref_text not in seen:
            seen.add(ref_text)
            refs.append(ref_text)
    return refs


def find_slash_refs_in_file(file_path: str) -> list:
    """从单个文件中提取所有斜杠分隔的 SRC 引用（需要报错）。"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    return [m.group(0) for m in SLASH_SRC_PATTERN.finditer(text)]


def extract_src_ids(ref_text: str) -> list:
    """从 [SRC-001, SRC-003, SRC-012] 提取 ['SRC-001', 'SRC-003', 'SRC-012']。"""
    return [f"SRC-{m}" for m in SRC_ID_PATTERN.findall(ref_text)]


def build_numbering(refs_by_file: list, source_index: dict) -> tuple:
    """构建全局编号映射。按首次出现顺序分配编号。
    返回 (src_to_num, num_to_src, missing)。
    """
    src_to_num = OrderedDict()
    num_to_src = OrderedDict()
    missing = set()
    next_num = 1

    for file_path, refs in refs_by_file:
        for ref_text in refs:
            src_ids = extract_src_ids(ref_text)
            for sid in src_ids:
                if sid not in src_to_num:
                    if sid in source_index:
                        src_to_num[sid] = next_num
                        num_to_src[next_num] = sid
                        next_num += 1
                    else:
                        missing.add(sid)
                        # 仍分配编号（用占位信息）
                        src_to_num[sid] = next_num
                        num_to_src[next_num] = sid
                        next_num += 1
    return src_to_num, num_to_src, missing


def replace_refs_in_file(file_path: str, src_to_num: dict, dry_run: bool = False) -> str:
    """替换文件中的 [SRC-XXX] 引用为 [N]。返回替换后的文本。"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    def replacer(match):
        ref_text = match.group(0)
        src_ids = extract_src_ids(ref_text)
        nums = [str(src_to_num[sid]) for sid in src_ids if sid in src_to_num]
        if not nums:
            return ref_text  # 无法替换，保留原样
        return "[" + ", ".join(nums) + "]"

    replaced = SRC_REF_PATTERN.sub(replacer, text)

    if not dry_run:
        # 写入同目录，加 _converted 后缀
        output_path = str(Path(file_path).with_suffix("")) + "_converted.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(replaced)
    return replaced


def format_gbt7714(source: dict, num: int) -> str:
    """将 source-index.csv 的一行格式化为 GB/T 7714-2015 参考文献条目。
    格式：[N] 主要责任者. 题名[文献类型标识]. 出版地: 出版者, 出版年.
    """
    title = source.get("title", "未知标题").strip()
    author = source.get("author_or_org", "").strip()
    publisher = source.get("publisher", "").strip()
    pub_date = source.get("publish_date", "").strip()
    source_type = source.get("source_type", "M").strip()  # 默认 M=专著

    # 文献类型标识映射
    type_map = {"journal": "J", "official": "EB/OL", "report": "R", "news": "N",
                "paper": "C", "book": "M", "M": "M", "J": "J", "R": "R",
                "C": "C", "N": "N", "EB/OL": "EB/OL"}
    type_tag = type_map.get(source_type, "M")

    parts = [f"[{num}]"]
    if author:
        parts.append(f"{author}.")
    parts.append(f"{title}[{type_tag}].")
    if publisher:
        parts.append(f"{publisher},")
    if pub_date:
        parts.append(f"{pub_date}.")

    # URL 如果有则追加
    url = source.get("url_or_path", "").strip()
    if url and source_type == "EB/OL":
        parts.append(f" {url}.")

    return " ".join(parts)


def generate_bibliography(num_to_src: dict, source_index: dict, missing: set) -> str:
    """生成 GB/T 7714-2015 格式的参考文献列表 Markdown 文本。"""
    lines = ["# 参考文献", "", "> 按首次出现顺序排列，格式遵循 GB/T 7714-2015。", ""]
    warn_lines = []

    for num, sid in num_to_src.items():
        if sid in source_index and source_index[sid].get("title", "").strip():
            lines.append(format_gbt7714(source_index[sid], num))
            lines.append("")
        else:
            lines.append(f"[{num}] [来源 {sid} — 元数据缺失，请手动补充]")
            lines.append("")
            warn_lines.append(f"  - {sid}: 在 source-index.csv 中无完整元数据")

    # 末尾警告
    if warn_lines:
        lines.append("---")
        lines.append("")
        lines.append("## 元数据缺失的来源（需手动补充）")
        lines.append("")
        lines.extend(warn_lines)
        lines.append("")

    return "\n".join(lines)


def has_any_src_refs(drafts_dir: str) -> bool:
    """快速检查 drafts 目录中是否存在需要转换的 [SRC-XXX] 引用。"""
    for f in sorted(Path(drafts_dir).glob("*.md")):
        with open(f, "r", encoding="utf-8") as fh:
            if SRC_REF_PATTERN.search(fh.read()):
                return True
    return False


def main():
    parser = argparse.ArgumentParser(description="引用转换：[SRC-XXX] → [N] 纯数字 + 生成统一参考文献")
    parser.add_argument("--drafts-dir", required=True, help="草稿文件目录（如 research/drafts）")
    parser.add_argument("--source-index", required=True, help="来源索引 CSV 路径（如 research/sources/source-index.csv）")
    parser.add_argument("--output", required=True, help="输出目录（转换后的 _converted.md 文件和 bibliography.md 将保存到此）")
    parser.add_argument("--dry-run", action="store_true", help="只检测不写入文件")
    parser.add_argument("--force", action="store_true", help="强制重写已转换文件（默认幂等跳过）")
    args = parser.parse_args()

    drafts_dir = args.drafts_dir
    output_dir = args.output

    if not os.path.isdir(drafts_dir):
        print(f"ERROR: drafts-dir 不存在: {drafts_dir}", file=sys.stderr)
        sys.exit(2)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 1. 幂等性检查
    if not args.force and not has_any_src_refs(drafts_dir):
        print("[OK] 草稿中未检测到 [SRC-XXX] 引用，无需转换（已是纯数字引用或无可转换引用）。")
        return

    # 2. 加载来源索引
    source_index = load_source_index(args.source_index)
    print(f"[INFO] 已加载 {len(source_index)} 条来源记录")

    # 3. 扫描草稿文件
    draft_files = scan_drafts(drafts_dir)
    print(f"[INFO] 已找到 {len(draft_files)} 个草稿文件")

    # 4. 检测斜杠引用
    all_slash_refs = []
    for fp in draft_files:
        slash_refs = find_slash_refs_in_file(fp)
        if slash_refs:
            for sr in slash_refs:
                all_slash_refs.append((os.path.basename(fp), sr))
    if all_slash_refs:
        print("[ERROR] 检测到斜杠分隔 SRC 引用——转换脚本不支持此格式，请手动修复为逗号分隔：")
        for fname, ref in all_slash_refs:
            print(f"  {fname}: {ref}")
        sys.exit(1)

    # 5. 提取所有引用
    refs_by_file = []
    total_refs = 0
    for fp in draft_files:
        refs = find_all_refs_in_file(fp)
        if refs:
            refs_by_file.append((fp, refs))
            total_refs += len(refs)

    if not refs_by_file:
        print("[OK] 草稿中未检测到 [SRC-XXX] 引用。")
        return

    print(f"[INFO] 检测到 {total_refs} 个引用位置")

    # 6. 构建全局编号
    src_to_num, num_to_src, missing = build_numbering(refs_by_file, source_index)
    print(f"[INFO] 全局编号映射: {len(src_to_num)} 个唯一来源 → [{1}]-[{len(src_to_num)}]")
    if missing:
        print(f"[WARN] {len(missing)} 个来源在 source-index.csv 中未找到: {sorted(missing)}")
        print(f"       这些来源仍分配了编号，但参考文献条目需手动补充。")

    # 7. 替换引用
    if not args.dry_run:
        for fp, _ in refs_by_file:
            replace_refs_in_file(fp, src_to_num)
            print(f"[OK] 已转换: {os.path.basename(fp)}")

    # 8. 生成参考文献
    bib_path = os.path.join(output_dir, "bibliography.md")
    bib_text = generate_bibliography(num_to_src, source_index, missing)
    if not args.dry_run:
        with open(bib_path, "w", encoding="utf-8") as f:
            f.write(bib_text)
        print(f"[OK] 参考文献列表已生成: {bib_path}")

    # 9. 转换报告
    print()
    print("=== 转换报告 ===")
    print(f"  处理文件数: {len(draft_files)}")
    print(f"  转换引用位置: {total_refs}")
    print(f"  唯一来源数: {len(src_to_num)}")
    print(f"  斜杠分隔引用: {len(all_slash_refs)} 处（需手动修复）")
    print(f"  source-index 缺失来源: {len(missing)} 个")
    if not args.dry_run:
        print(f"  转换后文件: *_converted.md（{len(draft_files)} 个）")
        print(f"  参考文献列表: {bib_path}")
    print(f"  输出目录: {output_dir}")
    print("=== 转换完成 ===")


if __name__ == "__main__":
    main()
