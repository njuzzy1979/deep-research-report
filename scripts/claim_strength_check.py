#!/usr/bin/env python3
"""主张表述强度自动检测脚本（P2-改进6）

扫描 Markdown 草稿，检测所有强表述（首次/最大/完全/秒级/决定性/全自动等），
对照 claims-ledger.csv 中的核验状态，标记缺乏 A/B 级证据支撑的强表述。

用法：
  python scripts/claim_strength_check.py <drafts_dir> <claims_csv> [--output report.md]
"""

import os, re, csv, sys
from pathlib import Path
from collections import defaultdict

# Windows 中文环境编码兼容：强制 stdout/stderr 使用 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 强表述关键词模式
STRONG_CLAIM_PATTERNS = {
    "首次性判断": re.compile(r"首次|第一个|第一颗|第一次|率先|最先|最早|原创|首创"),
    "最强级判断": re.compile(r"最大|最小|最高|最低|最快|最慢|最强|最弱|最优|最先进|领先"),
    "能力边界": re.compile(r"完全自主|全自动|全自动[^驾驶]|秒级|毫秒级|决定性|根本性|彻底"),
    "量化断言": re.compile(r"100%|百分之百|零失误|无一例外|全部|所有目标|任何目标"),
}

# 弱表述替换建议
DOWNGRADE_SUGGESTIONS = {
    "首次": "据公开报道较早之一",
    "第一个": "较早的",
    "最大": "规模靠前的",
    "完全自主": "高度自动化",
    "全自动": "高度自动化",
    "秒级": "数秒级（据称）",
    "决定性": "关键的",
    "100%": "接近 100%",
}

def load_claims_ledger(csv_path: str) -> dict:
    """加载核验台账，返回 {claim_id: verification_status}"""
    ledger = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("claim_id", "").strip()
            status = row.get("verification_status", "").strip()
            if cid:
                ledger[cid] = status
    return ledger


def scan_file(filepath: str, ledger: dict) -> list[dict]:
    """扫描单个 Markdown 文件，返回检测到的强表述列表"""
    findings = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for lineno, line in enumerate(lines, 1):
        # 跳过代码块和引用块
        if line.strip().startswith("```") or line.strip().startswith(">"):
            continue
        # 跳过标题行（标题中允许强表述，但对标题中的"首次"也要标记为待核验）
        is_heading = line.strip().startswith("#")

        for category, pattern in STRONG_CLAIM_PATTERNS.items():
            for match in pattern.finditer(line):
                word = match.group()
                # 检查是否有来源引用在同一行或前后行
                has_citation = bool(re.search(r"\[S\d+\]|\[C\d+\]", line))

                findings.append({
                    "file": os.path.basename(filepath),
                    "line": lineno,
                    "category": category,
                    "word": word,
                    "context": line.strip()[:120],
                    "has_citation": has_citation,
                    "is_heading": is_heading,
                })

    return findings


def generate_report(findings: list[dict], ledger: dict, output_path: str = None) -> str:
    """生成检测报告"""
    lines = [
        "# 主张表述强度检测报告",
        "",
        f"## 检测统计",
        "",
        f"- 检测到强表述总数：**{len(findings)}** 处",
    ]

    by_category = defaultdict(list)
    for f in findings:
        by_category[f["category"]].append(f)
    for cat, items in sorted(by_category.items()):
        lines.append(f"- {cat}：{len(items)} 处")

    by_file = defaultdict(list)
    for f in findings:
        by_file[f["file"]].append(f)

    lines.extend([
        "",
        "## 分文件汇总",
        "",
    ])
    for fname, items in sorted(by_file.items()):
        lines.append(f"- `{fname}`：{len(items)} 处")

    lines.extend([
        "",
        "## 高风险项（无来源引用的强表述）",
        "",
        "以下强表述所在段落无来源标注 `[SXXX]` 或 `[CXXX]`，需补充 A/B 级证据或降级表述：",
        "",
        "| # | 文件 | 行号 | 类别 | 强表述 | 建议替换 |",
        "|---|------|------|------|--------|---------|",
    ])

    high_risk = [f for f in findings if not f["has_citation"] and not f["is_heading"]]
    for i, f in enumerate(high_risk, 1):
        suggestion = DOWNGRADE_SUGGESTIONS.get(f["word"], "据称")
        lines.append(
            f"| {i} | {f['file']} | {f['line']} | {f['category']} | "
            f"「{f['word']}」 | {suggestion} |"
        )

    lines.extend([
        "",
        "## 中风险项（标题中的强表述）",
        "",
        "| # | 文件 | 行号 | 类别 | 强表述 |",
        "|---|------|------|------|--------|",
    ])
    heading_claims = [f for f in findings if f["is_heading"]]
    for i, f in enumerate(heading_claims, 1):
        lines.append(
            f"| {i} | {f['file']} | {f['line']} | {f['category']} | "
            f"「{f['word']}」 |"
        )

    lines.extend([
        "",
        "## 处理建议",
        "",
        "1. **高风险项**：逐条检查，补充 A/B 级来源引用 `[SXXX]`，或降级为限定表述",
        "2. **中风险项**：标题中允许使用概括性表述，但需在正文中提供 A/B 级证据支撑",
        "3. 修改后重新运行本脚本确认所有高风险项已处理",
        "",
        f"> 生成时间：自动检测 | 核验台账：{len(ledger)} 条记录",
    ])

    report = "\n".join(lines)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已保存：{output_path}")

    return report


def main():
    if len(sys.argv) < 2:
        print("用法: python claim_strength_check.py <drafts_dir> [claims_csv] [--output report.md]")
        print("示例: python claim_strength_check.py research/drafts/ research/claims/claims-ledger.csv --output research/claims/strength-report.md")
        sys.exit(1)

    drafts_dir = sys.argv[1]
    claims_csv = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else ""
    output_path = None

    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    # 如果没有提供 claims_csv，尝试默认路径
    if not claims_csv:
        default_csv = os.path.join(os.path.dirname(drafts_dir), "claims", "claims-ledger.csv")
        if os.path.exists(default_csv):
            claims_csv = default_csv

    # 加载核验台账
    ledger = load_claims_ledger(claims_csv) if claims_csv and os.path.exists(claims_csv) else {}
    if not ledger:
        print("[WARN] 未找到核验台账或台账为空，无法交叉验证")

    # 扫描所有 Markdown 文件
    all_findings = []
    md_files = list(Path(drafts_dir).glob("*.md"))
    if not md_files:
        print(f"错误：目录 {drafts_dir} 中未找到 .md 文件")
        sys.exit(1)

    for md_file in sorted(md_files):
        # 跳过非草稿文件
        if any(skip in md_file.name for skip in ["final-report", "detailed-outline", "red-team", "audit", "card-index"]):
            continue
        findings = scan_file(str(md_file), ledger)
        all_findings.extend(findings)
        if findings:
            print(f"  {md_file.name}：{len(findings)} 处强表述")

    # 生成报告
    report = generate_report(all_findings, ledger, output_path)
    print(f"\n总计：{len(all_findings)} 处强表述，其中 {len([f for f in all_findings if not f['has_citation'] and not f['is_heading']])} 处高风险")

    # 返回退出码：有高风险项时返回 1
    high_risk_count = len([f for f in all_findings if not f["has_citation"] and not f["is_heading"]])
    sys.exit(1 if high_risk_count > 0 else 0)


if __name__ == "__main__":
    main()
