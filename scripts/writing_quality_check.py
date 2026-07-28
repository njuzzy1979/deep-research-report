#!/usr/bin/env python3
"""写作质量增强层检查脚本（跨模型兼容性优化方案 §五之二 Phase E，聚合 E1-E4）。

E1 标准 20 信息密度检查（扩展 QS4）：
    复用 contract_check.split_paragraphs() 的段落切分口径（不重新实现切分逻辑，
    避免与 QS4 出现两份切分规则互相漂移）。对每个自然段统计"数据点"数量——
    writing-standards.md:417-420 给出的精确定义：数字（含百分比/金额/数量）、
    带有明确出处的声称、引用文献编号 `[N]`。脚本层面只能可靠捕捉前者与后者
    （数字模式 + `[N]` 引用编号模式）两类字面模式；"带明确出处的声称"是语义
    判断，超出正则可判定范围，本脚本**不**尝试识别，如实在此声明这一局限。
    输出 QS5_density：每段数据点数、"每 300 字至少 1 个数据点"密度判定、
    "连续 500 字无数据点"的具体段落定位。

E2 标准 18 章间/节间过渡存在性检查（非质量判断）：
    章间——非最后一章的章节结尾是否存在 `> **本章小结与过渡**：` 引用块
    （最后一章例外：只需 ≥1 句本章小结，无需引出下一章，故句数门槛降为 1）。
    节间——同章内相邻 H3 节之间是否存在非空过渡文本（存在性代理：该区间内
    是否有非标题/非表格/非图片的自然段文本，而非直接标题→标题或图片→标题
    的"硬切换"）。**只做存在性检查，不判断过渡内容写得好不好**——质量判断
    仍由 chapter_auditor_agent 承担。

E3 标准 0 后台泄露黑名单检查：
    检索式取自 references/stage-7-writing.md:148（已核实与 contract_check.py
    现有 C10/C11(F7/F8) 正则完全一致的部分直接 import 复用，不重复定义）。
    本脚本新增的是 F7/F8 未覆盖的"裸词习语"部分：分级用语裸词（"A 级"/
    "B 级"/"C 级"/"D 级"）、"证据强度"、"信源分级"、"本报告采用…不采用"
    句式、"尚未见独立信源"、"本次核验范围内"。
    天花板（如实声明）：黑名单只能拦已知习语，拦不住新造句式；且存在与
    领域术语撞车的可能（如旅游报告中"5A 级景区"），命中项需人工复核，
    非阻断。

E4 标准 19 缩写展开检查（带白名单，误报风险最高——最后实现）：
    全大写缩写（`[A-Z]{2,6}`）首次出现（按扫描顺序，排除标题/引用块/表格
    行/图片行）时，前后 30 字窗口内是否有中文全称/括号释义。白名单来源：
    references/glossary.md 的 aliases 字段（通过 term_consistency_check.py
    的 extract_yaml_glossary() 复用解析逻辑）+ 硬编码通用缩写表（NASA/ESA/
    GDP/AI/API 等）。另外对形如 "GB/T" 的国标编号前缀做启发式豁免（缩写
    后紧跟 "/" 视为标准编号而非需要展开的术语缩写）。

E5 定位声明（务必读完，决定本脚本在整体质量门禁体系中的角色）：
    - 受益对象：全部 tier，含 Claude 用户——这是本方案对 Claude 用户唯一的
      正向增量（其余改造对 tier A 大多是 no-op）。
    - 不受 tier 门控：质量检查与模型能力无关，任何 tier 都应运行本脚本。
    - 全部第一阶段非阻塞：E1-E4 severity 统一为 low/mid，只报告不阻断，
      观察期后再决定是否升级为阻塞检查（与 contract_check.py 的 C10/C11
      同一设计先例）。
    - 不替代审计 Agent：E1-E4 是**代理指标**（proxy metrics），语义质量
      判断仍由 chapter_auditor_agent 承担，本脚本只提供确定性的"存在性/
      计数型"信号供审计参考。

用法：
    python scripts/writing_quality_check.py <file.md>
    python scripts/writing_quality_check.py <file.md> --json
    python scripts/writing_quality_check.py <file.md> --glossary research/glossary.md

退出码（⚠️ 非阻塞语义，务必与 contract_check.py 的阻断语义区分）：
    0 = 正常执行完成（无论 E1-E4 是否命中任何质量信号，只要脚本本身跑通
        就是 0——因为全部检查项 severity=low/mid，只报告不阻断）
    1 = 保留位，当前版本不使用（E1-E4 命中不触发 1，避免误导调用方以为
        这是硬性质量门禁）
    2 = 文件不存在 / 读取失败 / 执行过程中抛出未预期异常（用法错误层面）
"""
from __future__ import annotations

import argparse
import json
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

# 复用 contract_check.py 的段落切分口径与 read_text（同一份切分/读取规则，
# 避免与 QS4 出现两份实现互相漂移——见 contract_check.split_paragraphs 的
# docstring）；同时复用 F7/F8 正则，E3 只新增习语部分，不重复定义已覆盖项。
try:
    from contract_check import (
        read_text,
        split_paragraphs,
        F7_SOURCE_TIER_PREFIX_PATTERN,
        F8_CLAIM_ID_LEAK_PATTERN,
    )
except ImportError:
    def read_text(path: str) -> str:  # type: ignore[no-redef]
        raw = Path(path).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8", errors="replace")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def split_paragraphs(text: str) -> list:  # type: ignore[no-redef]
        clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        paras, cur = [], []
        for line in clean.split("\n"):
            s = line.strip()
            if not s:
                if cur:
                    ptext = "".join(cur)
                    if re.findall(r"[一-鿿]", ptext):
                        paras.append(ptext)
                    cur = []
                continue
            if s.startswith("#") or s.startswith(">") or s.startswith("|") or s.startswith("!["):
                continue
            cur.append(s)
        if cur:
            ptext = "".join(cur)
            if re.findall(r"[一-鿿]", ptext):
                paras.append(ptext)
        return paras

    F7_SOURCE_TIER_PREFIX_PATTERN = re.compile(r"^\s*\[[ABCD]\]", re.MULTILINE)
    F8_CLAIM_ID_LEAK_PATTERN = re.compile(r"\[[A-Z]{1,3}\d{3}\]")

# 术语表白名单解析：容错兜底为空白名单（glossary 不可用时 E4 只用通用表，
# 不阻断——白名单越窄误报越多，但不影响脚本本身可执行性）。
try:
    from term_consistency_check import extract_yaml_glossary
except ImportError:
    def extract_yaml_glossary(glossary_path: str) -> list:  # type: ignore[no-redef]
        return []


# ── E1：标准 20 信息密度检查 ──────────────────────────────────────

# "数据点"定义（writing-standards.md:417-420）可脚本化的两类：
#   1) 引用文献编号 [N]（含逗号分隔 [1,2]）—— 先于数字模式匹配，避免与
#      括号内的数字重复计数
#   2) 数字（含百分比/金额/数量）—— 阿拉伯数字序列，可带小数点/百分号
CITATION_REF_PATTERN = re.compile(r"\[\d+(?:,\s*\d+)*\]")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")

# 标准 20：连续 500 字无数据点需定位；密度基线为每 300 字至少 1 个数据点
DENSITY_MIN_CHARS_PER_POINT = 300
CONTINUOUS_NO_DATA_THRESHOLD = 500


def count_data_points(paragraph: str) -> int:
    """统计单段落中的数据点数量（引用编号 + 数字，去重避免括号内数字被重复计数）。"""
    citations = CITATION_REF_PATTERN.findall(paragraph)
    remainder = CITATION_REF_PATTERN.sub("", paragraph)
    numbers = NUMBER_PATTERN.findall(remainder)
    return len(citations) + len(numbers)


def check_density(text: str) -> dict:
    """E1：标准 20 信息密度检查（QS5_density）。"""
    paragraphs = split_paragraphs(text)
    total_chars = 0
    total_data_points = 0
    running_no_data_chars = 0
    continuous_violations = []
    para_stats = []

    already_flagged = False
    for i, p in enumerate(paragraphs):
        chars = len(re.findall(r"[一-鿿]", p))
        dp = count_data_points(p)
        total_chars += chars
        total_data_points += dp
        if dp > 0:
            running_no_data_chars = 0
            already_flagged = False
        else:
            running_no_data_chars += chars
            # 同一段连续无数据点的"运行"只在首次越过阈值时报告一次，
            # 避免运行持续时对每个后续段落重复报告同一处违规。
            if running_no_data_chars >= CONTINUOUS_NO_DATA_THRESHOLD and not already_flagged:
                continuous_violations.append({
                    "paragraph_index": i,
                    "running_no_data_chars": running_no_data_chars,
                    "excerpt": p[:80],
                })
                already_flagged = True
        para_stats.append({"index": i, "chars": chars, "data_points": dp})

    chars_per_data_point = (
        round(total_chars / total_data_points, 1) if total_data_points > 0 else None
    )
    # 未达标：全文有正文字数但零数据点，或密度超过基线（每 300 字应有 1 个）
    below_min_density = (total_data_points == 0 and total_chars > 0) or (
        chars_per_data_point is not None and chars_per_data_point > DENSITY_MIN_CHARS_PER_POINT
    )

    return {
        "total_cjk_chars": total_chars,
        "total_data_points": total_data_points,
        "chars_per_data_point": chars_per_data_point,
        "min_required_density": DENSITY_MIN_CHARS_PER_POINT,
        "below_min_density": below_min_density,
        "continuous_no_data_violations": continuous_violations,
        "paragraph_count": len(paragraphs),
        "paragraphs": para_stats,
    }


# ── E2：标准 18 章间/节间过渡存在性检查 ──────────────────────────

CHAPTER_HEADING_PATTERN = re.compile(
    r"^#{1,2}\s*第[0-9一二三四五六七八九十百]+章\S*", re.MULTILINE
)
SECTION_HEADING_PATTERN = re.compile(r"^###\s+\S.*$", re.MULTILINE)
APPENDIX_HEADING_PATTERN = re.compile(r"^#{1,2}\s*附录", re.MULTILINE)
# 过渡块格式与 writing-standards.md 标准 18 原文逐字一致：
#   "在 Markdown 中以 `> **本章小结与过渡**：...` 引用块形式书写"
TRANSITION_BLOCK_PATTERN = re.compile(r"^>\s*\*\*本章小结与过渡\*\*[：:]", re.MULTILINE)


def _split_sentences(text: str) -> list:
    parts = re.split(r"[。！？]", text)
    return [p for p in parts if p.strip()]


def _extract_blockquote(span_text: str, match_start: int) -> str:
    """从匹配位置起，收集连续的 `>` 引用块行，拼接为纯文本（去掉 `>` 前缀）。"""
    lines = span_text[match_start:].split("\n")
    quote_parts = []
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            quote_parts.append(s.lstrip(">").strip())
        else:
            break
    return "".join(quote_parts)


def check_transitions(text: str) -> dict:
    """E2：章间过渡（≥2 句，最后一章 ≥1 句）+ 节间过渡（存在性代理）。"""
    chapter_heads = list(CHAPTER_HEADING_PATTERN.finditer(text))
    appendix_starts = [m.start() for m in APPENDIX_HEADING_PATTERN.finditer(text)]
    issues = []

    for i, m in enumerate(chapter_heads):
        start = m.end()
        candidates = [len(text)]
        if i + 1 < len(chapter_heads):
            candidates.append(chapter_heads[i + 1].start())
        for a_start in appendix_starts:
            if a_start > start:
                candidates.append(a_start)
                break
        end = min(candidates)
        span_text = text[start:end]
        is_last = (i == len(chapter_heads) - 1)
        title = m.group(0).strip()

        # 章间过渡
        tmatches = list(TRANSITION_BLOCK_PATTERN.finditer(span_text))
        if not tmatches:
            issues.append({
                "level": "chapter", "chapter": title,
                "issue": "missing_transition_block", "is_last": is_last,
            })
        else:
            quote_text = _extract_blockquote(span_text, tmatches[-1].start())
            sentences = _split_sentences(quote_text)
            required = 1 if is_last else 2
            if len(sentences) < required:
                issues.append({
                    "level": "chapter", "chapter": title,
                    "issue": "insufficient_sentences",
                    "found": len(sentences), "required": required, "is_last": is_last,
                })

        # 节间过渡（同章内相邻 H3 之间，存在性代理：区间内是否有非空自然段）
        section_heads = list(SECTION_HEADING_PATTERN.finditer(span_text))
        for j in range(len(section_heads) - 1):
            s_start = section_heads[j].end()
            s_end = section_heads[j + 1].start()
            between = span_text[s_start:s_end]
            paras = split_paragraphs(between)
            if not paras:
                issues.append({
                    "level": "section", "chapter": title,
                    "issue": "missing_section_transition",
                    "between": (
                        f"{section_heads[j].group(0).strip()} -> "
                        f"{section_heads[j + 1].group(0).strip()}"
                    ),
                })

    return {
        "chapters_checked": len(chapter_heads),
        "issues": issues,
    }


# ── E3：标准 0 后台泄露黑名单检查 ────────────────────────────────

# stage-7-writing.md:148 检索式中，F7/F8 未覆盖的"裸词习语"部分（F7/F8 已在
# contract_check.py 中实现，此处 import 复用，不重复定义）。
E3_BLACKLIST_PATTERNS = {
    "分级用语裸词(A/B/C/D级)": re.compile(r"[ABCD]\s*级"),
    "证据强度": re.compile(r"证据强度"),
    "信源分级": re.compile(r"信源分级"),
    "采用不采用句式": re.compile(r"本报告采用.{0,6}不采用"),
    "尚未见独立信源": re.compile(r"尚未见独立信源"),
    "本次核验范围内": re.compile(r"本次核验范围内"),
}


def check_backstage_leak(text: str) -> dict:
    """E3：标准 0 后台内容泄露黑名单检查（含 F7/F8 复用 + 新增裸词习语）。"""
    hits = {}
    for name, pat in E3_BLACKLIST_PATTERNS.items():
        found = pat.findall(text)
        if found:
            hits[name] = len(found)

    # 复用 contract_check 的 F7/F8（与 C10/C11 观察层同源，避免重复实现）
    f7_hits = F7_SOURCE_TIER_PREFIX_PATTERN.findall(text)
    f8_hits = F8_CLAIM_ID_LEAK_PATTERN.findall(text)
    if f7_hits:
        hits["信源分级前缀(F7复用)"] = len(f7_hits)
    if f8_hits:
        hits["claim_id泄露(F8复用)"] = len(f8_hits)

    return {
        "hits": hits,
        "total_hits": sum(hits.values()),
    }


# ── E4：标准 19 缩写展开检查（带白名单） ──────────────────────────

GENERIC_ABBR_WHITELIST = {
    "NASA", "ESA", "GDP", "AI", "API", "GPS", "GB", "ISO", "UN", "EU",
    "CEO", "CFO", "CTO", "IT", "PDF", "URL", "HTML", "CSV", "JSON", "XML",
    "PPT", "OK", "VS", "ID", "APP", "USB", "LED", "PC", "TV", "WIFI",
}

# 全大写缩写候选：2-6 位连续大写字母，前后不与其他字母/数字直接相连
ABBR_CANDIDATE_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,6}(?![A-Za-z0-9])")


def _load_glossary_whitelist(glossary_path: Optional[str]) -> set:
    """从 glossary.md 的 aliases 字段构建白名单（容错：解析失败返回空集）。"""
    if not glossary_path or not Path(glossary_path).exists():
        return set()
    try:
        entries = extract_yaml_glossary(glossary_path)
    except Exception:
        return set()
    whitelist = set()
    for e in entries:
        for alias in (e.get("aliases") or []):
            if isinstance(alias, str) and alias.isalpha() and alias.isupper():
                whitelist.add(alias)
    return whitelist


def check_abbreviations(text: str, glossary_path: Optional[str] = None) -> dict:
    """E4：缩写首次出现是否展开（前后 30 字窗口内是否有中文释义），带白名单。"""
    whitelist = GENERIC_ABBR_WHITELIST | _load_glossary_whitelist(glossary_path)

    # 可扫描正文：排除标题/引用块/表格行/图片行（与 split_paragraphs 同款排除规则），
    # 避免附录术语对照表（`| CBTC | 基于通信的列车控制系统 |`）之类的表格行
    # 干扰"首次出现"判定与上下文窗口取值。
    scannable_lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|") or s.startswith("!["):
            continue
        scannable_lines.append(s)
    scannable = "\n".join(scannable_lines)

    first_seen = {}
    for m in ABBR_CANDIDATE_PATTERN.finditer(scannable):
        abbr = m.group(0)
        if abbr in first_seen:
            continue
        # 国标编号前缀启发式豁免（如 "GB/T 4754-2017" 中的 "GB"）：
        # 缩写候选紧跟 "/" 视为标准编号前缀，不是需要展开的术语缩写
        if scannable[m.end():m.end() + 1] == "/":
            continue
        first_seen[abbr] = m.span()

    violations = []
    whitelist_skipped = []
    checked = []
    for abbr, (s, e) in first_seen.items():
        if abbr in whitelist:
            whitelist_skipped.append(abbr)
            continue
        window = scannable[max(0, s - 30): e + 30]
        has_bracket = ("（" in window) or ("(" in window)
        has_cjk = len(re.findall(r"[一-鿿]", window)) >= 2
        explained = has_bracket and has_cjk
        entry = {"abbr": abbr, "explained_nearby": explained, "context": window}
        checked.append(entry)
        if not explained:
            violations.append(entry)

    return {
        "candidates_checked": len(first_seen),
        "whitelist_skipped": sorted(whitelist_skipped),
        "checked": checked,
        "violations": violations,
    }


# ── 聚合入口 ───────────────────────────────────────────────────

def check_writing_quality(text: str, glossary_path: Optional[str] = None) -> dict:
    """聚合 E1-E4，返回结构化结果。全部 severity=low/mid，只报告不阻断（E5）。"""
    e1 = check_density(text)
    e2 = check_transitions(text)
    e3 = check_backstage_leak(text)
    e4 = check_abbreviations(text, glossary_path)

    any_findings = (
        e1["below_min_density"]
        or bool(e1["continuous_no_data_violations"])
        or bool(e2["issues"])
        or bool(e3["hits"])
        or bool(e4["violations"])
    )

    return {
        "file": None,
        "E1_density": e1,
        "E2_transitions": e2,
        "E3_backstage_leak": e3,
        "E4_abbreviation": e4,
        "any_findings": any_findings,
    }


def format_text_report(r: dict) -> str:
    lines = [f"=== 写作质量增强层检查（Phase E，非阻塞）：{r['file']} ===", ""]

    e1 = r["E1_density"]
    mark1 = WARN if (e1["below_min_density"] or e1["continuous_no_data_violations"]) else OK
    lines.append(
        f"{mark1} E1 信息密度: {e1['total_data_points']} 数据点 / {e1['total_cjk_chars']} 字 "
        f"(密度={e1['chars_per_data_point']}, 基线={e1['min_required_density']}字/点)"
    )
    if e1["continuous_no_data_violations"]:
        lines.append(f"      连续 {CONTINUOUS_NO_DATA_THRESHOLD} 字无数据点位置:")
        for v in e1["continuous_no_data_violations"][:5]:
            lines.append(f"      - 段落#{v['paragraph_index']}: {v['excerpt']}...")

    e2 = r["E2_transitions"]
    mark2 = WARN if e2["issues"] else OK
    lines.append(f"{mark2} E2 章节过渡存在性: {e2['chapters_checked']} 章 / {len(e2['issues'])} 处问题")
    for issue in e2["issues"][:10]:
        if issue["level"] == "chapter":
            lines.append(f"      - [章间-{issue['chapter']}] {issue['issue']}")
        else:
            lines.append(f"      - [节间-{issue['chapter']}] {issue['issue']}: {issue.get('between', '')}")

    e3 = r["E3_backstage_leak"]
    mark3 = WARN if e3["hits"] else OK
    lines.append(f"{mark3} E3 后台泄露黑名单: {e3['total_hits']} 处命中")
    for name, count in e3["hits"].items():
        lines.append(f"      - {name}: {count} 处")

    e4 = r["E4_abbreviation"]
    mark4 = WARN if e4["violations"] else OK
    lines.append(
        f"{mark4} E4 缩写展开: {len(e4['violations'])}/{e4['candidates_checked']} 处未展开 "
        f"(白名单跳过 {len(e4['whitelist_skipped'])} 个)"
    )
    for v in e4["violations"][:10]:
        lines.append(f"      - {v['abbr']}: 首次出现附近未见释义")

    lines.append("")
    lines.append(
        "=== 总判定: 全部非阻塞（severity=low/mid），仅供 chapter_auditor_agent 参考 ==="
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="写作质量增强层检查（Phase E: E1-E4，非阻塞代理指标）"
    )
    parser.add_argument("file", help="待检查的 Markdown 文件（单章草稿或合并终稿）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument(
        "--glossary", default=None,
        help="research/glossary.md 路径（E4 白名单来源，缺省时只用通用缩写表）",
    )
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"{FAIL} 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(2)

    try:
        text = read_text(args.file)
        result = check_writing_quality(text, args.glossary)
    except Exception as e:
        print(f"{FAIL} 执行失败: {e}", file=sys.stderr)
        sys.exit(2)

    result["file"] = args.file

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    # 非阻塞语义（E5）：exit code 1 只保留位不使用，质量指标命中不导致非 0；
    # 只有上面 try 块中的读取/执行失败才会走 sys.exit(2)。
    sys.exit(0)


if __name__ == "__main__":
    main()
