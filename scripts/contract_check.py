#!/usr/bin/env python3
"""转换器合约 + 量化统计自动检查脚本（v5 清单 #6，替代 v3 的 Bash 版）

对单章草稿或合并终稿执行两组确定性检查：
  合约层 C1-C5 —— 见 references/appendix-converter-contract.md 编号化检查规格
    C1 分章文件不含 H1 / 全文仅一个 H1
    C2 H2/H3/H4 标题无手动编号
    C3 图片使用标准 Markdown 语法（计数，可与大纲规划比对）
    C4 表格有加粗题注（题注数 vs 表格数）
    C5 无禁止内容（含密级词 —— 门 3 安全前移）
  量化层 QS1-QS3 —— 供阶段 7 审计 Agent 做字数/图/表统计
    QS1 正文字数（中文字符计数，供与大纲"约 N×800 字"预算比对）
    QS2 图片引用数
    QS3 表格数

设计意图（v4 §3.3.5 / v5 CF-3）：本脚本由**独立的 chapter_auditor_agent 调用**，
不是写作 Agent 自报。审计 Agent 只做"运行脚本 + 解读 stdout + 裁决"，字数/图数/表数
是脚本数出来的确定性结果，写作 Agent 无权自报通过——这消除了 V3 §7.1(2)"Agent 编造
字数"的漏洞。

用法：
  python scripts/contract_check.py <file.md>                 # 单章检查，人读文本输出
  python scripts/contract_check.py <file.md> --json          # 机读 JSON（审计 Agent 用）
  python scripts/contract_check.py <file.md> --merged        # 合并终稿模式（C1 允许 1 个 H1）
  python scripts/contract_check.py <file.md> --expect-figures N  # C3 与大纲规划图数比对

退出码：0 = 全部合约项通过；1 = 至少一项高严重度合约项失败（C1/C2/C5）。
"""

import sys
import re
import json
import argparse
from pathlib import Path

# Windows 中文环境编码兼容：强制 stdout/stderr 使用 UTF-8（遵循 claim_strength_check.py 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃 —— 即使已 reconfigure，管道重定向仍可能回落 GBK）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

# 禁止内容模式（C5）—— 含密级词，门 3 安全机制前移到阶段 7
BANNED_PATTERNS = {
    "建议印刷页数": re.compile(r"建议印刷页数"),
    "图表占位": re.compile(r"图表占位|\[此处插入图|\[图\d+-\d+：|图表占位符"),
    "全文完": re.compile(r"全文完"),
    "HTML标签": re.compile(r"</?(div|span|table|br|img|p)\b", re.IGNORECASE),
    "封面元数据行": re.compile(r"^(编制单位|申报单位|编制日期)[:：]", re.MULTILINE),
    "密级标注": re.compile(r"绝密|机密|秘密|内部资料|\b内部\b|涉密"),
}

# 标题手动编号模式（C2）：H2-H4 后紧跟阿拉伯数字或中文数字编号
MANUAL_NUMBER_PATTERN = re.compile(
    r"^#{2,4}\s+(?:第?\s*[0-9一二三四五六七八九十百]+[\.、\s章节]|[0-9]+\.[0-9])"
)


def read_text(path: str) -> str:
    """二进制安全读取，处理 BOM / CRLF。"""
    raw = Path(path).read_bytes()
    # 去 UTF-8 BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    # 统一换行
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_code_blocks(text: str) -> str:
    """移除 ``` 围栏代码块，避免代码块内的 # 或表格被误判。"""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def count_cjk_chars(text: str) -> int:
    """统计中文正文字数（QS1）：CJK 统一表意文字 + 常用标点，剔除标题/引用/表格/图片行。"""
    body_lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):           # 标题不计入正文字数
            continue
        if s.startswith(">"):           # 引用块（多为元数据/审计提示）
            continue
        if s.startswith("|"):           # 表格行
            continue
        if s.startswith("!["):          # 图片行
            continue
        if s.startswith("```"):
            continue
        body_lines.append(s)
    body = "".join(body_lines)
    return len(re.findall(r"[\u4e00-\u9fff]", body))


def check_contract(text: str, merged: bool, expect_figures) -> dict:
    """执行 C1-C5 + QS1-QS3，返回结构化结果。"""
    clean = strip_code_blocks(text)
    lines = clean.split("\n")

    # C1: H1 数量
    h1_count = sum(1 for ln in lines if re.match(r"^#\s+\S", ln))
    c1_limit = 1 if merged else 0
    c1_pass = h1_count <= c1_limit

    # C2: H2-H4 手动编号
    c2_hits = [ln.strip() for ln in lines if MANUAL_NUMBER_PATTERN.match(ln)]
    c2_pass = len(c2_hits) == 0

    # C3: 图片标准语法计数
    img_count = len(re.findall(r"!\[图\s*\d+-\d+", clean))
    img_count_loose = len(re.findall(r"!\[[^\]]*\]\([^\)]+\)", clean))
    if expect_figures is not None:
        c3_pass = img_count >= expect_figures
    else:
        c3_pass = True  # 无预期值时仅计数，不判定

    # C4: 表格加粗题注 vs 表格块数
    caption_count = len(re.findall(r"\*\*表\s*\d+-\d+", clean))
    # 表格块 = 连续的以 | 开头的行组，且含分隔行 |---|
    table_blocks = len(re.findall(r"(?:^\|.*\|\s*$\n)(?:^\|[\s:\-|]+\|\s*$\n)", clean, re.MULTILINE))
    c4_pass = caption_count >= table_blocks  # 每个表格块至少一个题注

    # C5: 禁止内容
    c5_hits = {}
    for name, pat in BANNED_PATTERNS.items():
        found = pat.findall(clean)
        if found:
            c5_hits[name] = len(found)
    c5_pass = len(c5_hits) == 0

    # QS1: 正文字数
    word_count = count_cjk_chars(text)

    result = {
        "file": None,
        "mode": "merged" if merged else "chapter",
        "contract": {
            "C1_h1": {"count": h1_count, "limit": c1_limit, "pass": c1_pass, "severity": "high"},
            "C2_manual_number": {"hits": c2_hits, "count": len(c2_hits), "pass": c2_pass, "severity": "high"},
            "C3_image_syntax": {"figure_count": img_count, "loose_image_count": img_count_loose,
                                 "expect": expect_figures, "pass": c3_pass, "severity": "mid"},
            "C4_table_caption": {"caption_count": caption_count, "table_block_count": table_blocks,
                                  "pass": c4_pass, "severity": "mid"},
            "C5_banned": {"hits": c5_hits, "pass": c5_pass, "severity": "high"},
        },
        "quant": {
            "QS1_cjk_chars": word_count,
            "QS1_est_pages": round(word_count / 800, 1),
            "QS2_figures": img_count,
            "QS3_tables": table_blocks,
        },
    }
    # 高严重度合约项（C1/C2/C5）任一失败 → 整体 fail
    result["overall_pass"] = c1_pass and c2_pass and c5_pass
    return result


def format_text_report(r: dict) -> str:
    c = r["contract"]
    q = r["quant"]

    def mark(p):
        return OK if p else FAIL

    lines = [
        f"=== 合约 + 量化检查：{r['file']} （模式：{r['mode']}）===",
        "",
        "-- 合约层 C1-C5 --",
        f"{mark(c['C1_h1']['pass'])} C1 H1数量: {c['C1_h1']['count']} (上限 {c['C1_h1']['limit']})",
        f"{mark(c['C2_manual_number']['pass'])} C2 标题手动编号: {c['C2_manual_number']['count']} 处 (应为 0)",
    ]
    if c["C2_manual_number"]["hits"]:
        for h in c["C2_manual_number"]["hits"][:5]:
            lines.append(f"      - {h}")
    c3 = c["C3_image_syntax"]
    exp = "" if c3["expect"] is None else f" / 大纲规划 {c3['expect']}"
    lines.append(f"{mark(c3['pass'])} C3 图片(标准语法): {c3['figure_count']} 张{exp}")
    c4 = c["C4_table_caption"]
    lines.append(f"{mark(c4['pass'])} C4 表格题注: {c4['caption_count']} 题注 / {c4['table_block_count']} 表格块")
    c5 = c["C5_banned"]
    lines.append(f"{mark(c5['pass'])} C5 禁止内容: {'无' if c5['pass'] else c5['hits']}")
    if not c5["pass"] and "密级标注" in c5["hits"]:
        lines.append(f"      {WARN} 检测到密级词 —— 红线，一律阻断（门 3 安全前移）")
    lines.extend([
        "",
        "-- 量化层 QS1-QS3 --",
        f"     QS1 正文字数(中文): {q['QS1_cjk_chars']} 字 (约 {q['QS1_est_pages']} 页)",
        f"     QS2 图片引用数: {q['QS2_figures']}",
        f"     QS3 表格数: {q['QS3_tables']}",
        "",
        f"=== 总判定: {'PASS' if r['overall_pass'] else 'FAIL (高严重度 C1/C2/C5 存在失败项)'} ===",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="转换器合约 C1-C5 + 量化 QS1-QS3 检查")
    parser.add_argument("file", help="待检查的 Markdown 文件（单章草稿或合并终稿）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供审计 Agent 解析）")
    parser.add_argument("--merged", action="store_true", help="合并终稿模式（C1 允许 1 个 H1）")
    parser.add_argument("--expect-figures", type=int, default=None, help="C3 与大纲规划图数比对")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"{FAIL} 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(2)

    text = read_text(args.file)
    result = check_contract(text, args.merged, args.expect_figures)
    result["file"] = args.file

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
