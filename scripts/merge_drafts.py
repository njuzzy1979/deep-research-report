#!/usr/bin/env python3
"""六阶段确定性合并管道 —— 将分章草稿合并为完整 final-report.md。

设计意图：finalizer_agent（Haiku 级 LLM）承担了本应由确定性脚本执行的合并操作。
本脚本把合并流程分解为 6 个确定性阶段，消除 LLM 在合并过程中的不确定行为。

阶段：
  A: 解析 outline.md 结构清单
  B: 逐文件清洗（6 步规则：剥离Agent标记→字数残留→局部参考文献→爬虫标记→粗体伪标题→SRC残留）
  C: 单文件合约校验（C2/C6/C7/C8）
  D: 结构驱动拼接（按章插入 H2 章容器）
  F: 引用转换（convert_references.py --in-place，对合并后 final-report.md 原地执行 SRC→[N]）
  E: 合并后终检（contract_check --merged --stage stage9，在转换后的文件上检查）

用法：
  python scripts/merge_drafts.py \
    --drafts-dir research/drafts \
    --outline research/outline.md \
    --source-index research/sources/source-index.csv \
    --output research/drafts/final-report.md \
    --cover research/cover.md
"""

import sys
import re
import os
import argparse
import subprocess
from pathlib import Path
from collections import OrderedDict

# Windows 中文环境编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ── 阶段 A：解析 outline.md 结构清单 ────────────────────────

def parse_outline_yaml(outline_path: str) -> dict:
    """从 outline.md 的 YAML front matter 提取 structure 节点。"""
    import yaml
    with open(outline_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 YAML front matter
    yaml_text = ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_text = parts[1]

    if not yaml_text:
        print("[ERROR] outline.md 中未找到 YAML front matter", file=sys.stderr)
        sys.exit(2)

    data = yaml.safe_load(yaml_text)
    if "structure" not in data:
        print("[ERROR] outline.md YAML 中缺少 structure 节点", file=sys.stderr)
        sys.exit(2)
    return data["structure"]


# ── 阶段 B：逐文件清洗 ────────────────────────────────────

def clean_draft(text: str) -> tuple:
    """6 步清洗规则。返回 (cleaned_text, cleaning_report)。"""
    report = []
    lines = text.split("\n")

    # B1: 剥离 Agent 输出隔离标记
    cleaned_lines = []
    for line in lines:
        s = line.strip()
        if s.startswith("[AGENT-OUTPUT-START]") or s.startswith("[AGENT-OUTPUT-END]"):
            report.append(f"B1-剥离标记: {s[:60]}")
            continue
        cleaned_lines.append(line)
    lines = cleaned_lines

    # B2: 剥离字数统计残留
    text_for_b2 = "\n".join(lines)
    b2_count = len(re.findall(r"全文约\s*\d+\s*字|本章字数", text_for_b2))
    text_for_b2 = re.sub(r"全文约\s*\d+\s*字", "", text_for_b2)
    text_for_b2 = re.sub(r"本章字数[^\n]*", "", text_for_b2)
    text_for_b2 = re.sub(r"^\s*>\s*\*\*篇幅预算\*\*[^\n]*\n?", "", text_for_b2, flags=re.MULTILINE)
    if b2_count:
        report.append(f"B2-字数残留: {b2_count} 处")
    lines = text_for_b2.split("\n")

    # B3: 剥离局部参考文献节
    text_for_b3 = "\n".join(lines)
    b3_count = len(re.findall(r"^#{2,3}\s+参考文献", text_for_b3, re.MULTILINE))
    # 删除从 "## 参考文献" 或 "### 参考文献" 到文件末尾之间的所有内容
    text_for_b3 = re.sub(
        r"^#{2,3}\s+参考文献[\s\S]*$", "", text_for_b3, flags=re.MULTILINE
    )
    if b3_count:
        report.append(f"B3-局部参考文献: {b3_count} 处")
    lines = text_for_b3.split("\n")

    # B4: 剥离爬虫标记（保持兼容——未来可能扩展）
    # 当前无特定规则，占位

    # B5: 粗体伪标题标记（改为 WARN 而不修改——保留正文由 Writer 修复）
    text_for_b5 = "\n".join(lines)
    bold_pat = re.compile(r"^\*\*[^*]+\*\*\s*$")
    bold_rows = []
    consecutive = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if bold_pat.match(s):
            consecutive += 1
            bold_rows.append(i + 1)
        else:
            consecutive = 0
    if len(bold_rows) >= 3:
        report.append(f"B5-粗体伪标题: {len(bold_rows)} 行 (L{min(bold_rows)}-L{max(bold_rows)}) — WARN，不自动修改")

    # B6: 剥离 SRC 残留（可选——仅 stage9 模式）
    # 在 merge 阶段暂时保留 SRC，由 convert_references.py 在阶段 F 统一处理
    # 此处只做检测计数
    text_for_b6 = "\n".join(lines)
    src_count = len(re.findall(r"\[SRC-\d+", text_for_b6))
    if src_count:
        report.append(f"B6-SRC引用: {src_count} 处（保留，由阶段F统一转换）")

    result = "\n".join(lines)
    return result, report


# ── 阶段 C：单文件合约校验 ────────────────────────────────

def validate_single_draft(file_path: str, script_dir: str) -> bool:
    """运行 contract_check.py 对单个草稿做 C2/C5/C6/C8 检查。"""
    check_script = os.path.join(script_dir, "contract_check.py")
    if not os.path.exists(check_script):
        print(f"[WARN] contract_check.py 未找到，跳过单文件校验: {check_script}", file=sys.stderr)
        return True  # 不阻断

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, check_script, file_path, "--json"],
        capture_output=True, text=True, encoding="utf-8", env=env
    )
    if result.returncode != 0:
        # 尝试解析 JSON 看哪些项失败
        try:
            import json
            data = json.loads(result.stdout)
            failed = [k for k, v in data.get("contract", {}).items() if not v.get("pass")]
            print(f"  [FAIL] {os.path.basename(file_path)}: {failed}")
        except Exception:
            print(f"  [FAIL] {os.path.basename(file_path)}: 脚本返回非零")
        return False
    return True


# ── 阶段 D：结构驱动拼接 ──────────────────────────────────

def find_draft_files(drafts_dir: str, chapter_no: int, section_no: str) -> list:
    """查找属于 (chapter_no, section_no) 的分章文件。"""
    pattern = f"ch{chapter_no:02d}-{section_no.replace('.', '-')}-*.md"
    matches = sorted(Path(drafts_dir).glob(pattern))
    # 也尝试不包含 section_no 的模式
    if not matches:
        pattern2 = f"ch{chapter_no:02d}-*.md"
        matches = sorted(Path(drafts_dir).glob(pattern2))
    return matches


def assemble_merged(structure: dict, drafts_dir: str) -> str:
    """按 structure 拼接全报告，生成 final-report.md 内容。"""
    lines = []
    seen_warnings = []

    # 前置件
    fm = structure.get("frontmatter", [])
    for item in fm:
        c_title = item.get("chapter_title", "")
        if c_title:
            lines.append(f"# {c_title}")
            lines.append("")
        for s in item.get("sections", []):
            if isinstance(s, dict):
                st = s.get("section_title", "")
            else:
                st = str(s)
            if st:
                lines.append(f"## {st}")
                lines.append("")

    # 正文各章
    for chapter in structure.get("bodymatter", []):
        c_no = chapter.get("chapter_no", "?")
        c_title = chapter.get("chapter_title", f"第 {c_no} 章")

        # 插入章容器 H2
        lines.append(f"## 第 {c_no} 章：{c_title}")
        lines.append("")

        # 按 sections 列表依次查找并拼接分章文件
        for s in chapter.get("sections", []):
            if isinstance(s, dict):
                s_no = s.get("section_no", "")
                s_title = s.get("section_title", "")
            else:
                s_no = ""
                s_title = str(s)

            # 查找分章文件
            draft_files = find_draft_files(drafts_dir, c_no, s_no)
            if draft_files:
                for df in draft_files:
                    try:
                        with open(df, "r", encoding="utf-8") as f:
                            content = f.read()
                        # 剥离 YAML front matter（若存在）
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            content = parts[-1] if len(parts) >= 3 else content
                        lines.append(content.strip())
                        lines.append("")
                    except Exception as e:
                        seen_warnings.append(f"无法读取 {df}: {e}")
            else:
                # 未找到分章文件时，插入"空节"占位
                seen_warnings.append(f"未找到草稿对应 {c_no}.{s_no} ({s_title})")
                lines.append(f"### {s_title}")
                lines.append("")
                lines.append(f"> [WARN] 本节对应的大纲条目为 {s_no} {s_title}，但未在 drafts 目录中找到匹配的分章文件。")
                lines.append("")

        lines.append("")  # 章间空行

    # 附录
    for app in structure.get("appendix", []):
        letter = app.get("appendix_letter", "")
        title = app.get("appendix_title", "")
        if title:
            lines.append(f"## 附录{letter}：{title}")
            lines.append("")

    # 输出组装警告
    if seen_warnings:
        print("[WARN] 结构驱动拼接过程中遇到的问题：")
        for w in seen_warnings:
            print(f"  - {w}")

    return "\n".join(lines)


# ── 阶段 E：合并后终检 ────────────────────────────────────

def run_merged_check(merged_path: str, script_dir: str) -> bool:
    """运行 contract_check.py --merged --stage stage9 做合并后终检。"""
    check_script = os.path.join(script_dir, "contract_check.py")
    print(f"\n[阶段 E] 合并后终检: {os.path.basename(merged_path)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, check_script, merged_path, "--merged", "--stage", "stage9"],
        capture_output=True, text=True, encoding="utf-8", env=env
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0


# ── 阶段 F：参考文献统一 ──────────────────────────────────

def run_convert_references(file_path: str, source_index: str, script_dir: str) -> bool:
    """运行 convert_references.py --in-place 对单个文件原地做 SRC→[N] 转换。"""
    convert_script = os.path.join(script_dir, "convert_references.py")
    drafts_dir = os.path.dirname(file_path)
    print(f"\n[阶段 F] 引用转换（原地）: {os.path.basename(file_path)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, convert_script,
         "--drafts-dir", drafts_dir,
         "--source-index", source_index,
         "--output", drafts_dir,
         "--in-place", file_path],
        capture_output=True, text=True, encoding="utf-8", env=env
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0


# ── 主流程 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="六阶段确定性合并管道")
    parser.add_argument("--drafts-dir", required=True, help="分章草稿目录")
    parser.add_argument("--outline", required=True, help="outline.md 路径")
    parser.add_argument("--source-index", required=True, help="source-index.csv 路径")
    parser.add_argument("--output", required=True, help="合并后输出路径（final-report.md）")
    parser.add_argument("--cover", default=None, help="cover.md 路径（可选）")
    parser.add_argument("--skip-f", action="store_true", help="跳过阶段 F（引用转换，手动执行）")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    drafts_dir = args.drafts_dir

    if not os.path.isdir(drafts_dir):
        print(f"[ERROR] drafts-dir 不存在: {drafts_dir}", file=sys.stderr)
        sys.exit(2)

    # 阶段 A: 解析大纲
    print("[阶段 A] 解析 outline.md 结构清单...")
    structure = parse_outline_yaml(args.outline)
    bodymatter = structure.get("bodymatter", [])
    print(f"  章数: {len(bodymatter)}")
    for ch in bodymatter:
        secs = ch.get("sections", [])
        print(f"  第{ch.get('chapter_no')}章: {len(secs)} 节")

    # 阶段 B: 清洗所有分章文件
    print("\n[阶段 B] 逐文件清洗...")
    all_draft_files = sorted(Path(drafts_dir).glob("ch*.md"))
    cleaning_reports = {}
    for fp in all_draft_files:
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()
        cleaned, report = clean_draft(text)
        cleaning_reports[str(fp)] = report
        # 写回清洗后文件（备份为 .bak）
        bak_path = str(fp) + ".bak"
        with open(bak_path, "w", encoding="utf-8") as f:
            f.write(text)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(cleaned)
        if report:
            print(f"  {os.path.basename(fp)}: {'; '.join(report)}")
        else:
            print(f"  {os.path.basename(fp)}: 无需清洗")

    # 阶段 C: 单文件合约校验
    print("\n[阶段 C] 单文件合约校验...")
    c_failures = 0
    for fp in all_draft_files:
        if not validate_single_draft(str(fp), script_dir):
            c_failures += 1
    if c_failures:
        print(f"  [WARN] {c_failures} 个文件合约校验未通过")
    else:
        print(f"  全部 {len(all_draft_files)} 个文件通过")

    # 阶段 D: 结构驱动拼接
    print("\n[阶段 D] 结构驱动拼接...")
    merged_content = assemble_merged(structure, drafts_dir)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(merged_content)
    print(f"  合并完成: {args.output}")

    # 阶段 F: 引用转换（在合并后、终检前，原地转换 final-report.md）
    if not args.skip_f:
        f_pass = run_convert_references(args.output, args.source_index, script_dir)
        if not f_pass:
            print("  [WARN] 引用转换未完全成功，请检查手动修复需求。")
    else:
        print("\n[阶段 F] 已跳过（--skip-f）")

    # 阶段 E: 合并后终检（在已转换的文件上执行）
    print("\n[阶段 E] 合并后终检...")
    e_pass = run_merged_check(args.output, script_dir)
    if not e_pass:
        print("  [WARN] 合并后终检未通过！请检查上述 FAIL 项。")

    print(f"\n=== 合并管道完成 ===")
    print(f"  输出: {args.output}")
    print(f"  来源索引: {args.source_index}")
    bak_count = len(list(Path(drafts_dir).glob("*.bak")))
    print(f"  清洗备份: {bak_count} 个 .bak 文件（清洗前原始草稿）")


if __name__ == "__main__":
    main()
