#!/usr/bin/env python3
"""卡片-正文重合度检测脚本（P0-6，方案 §4.3 机制三 + §4.3.1 阈值校准）

用途：阶段 7 审计 Agent 的"资产·转写维度"确定性检测半。对本章正文与本章引用的
每张卡片做滑动窗口 n-gram 重合检测，量化"卡片是否被消化转写而非誊抄"。

设计定位（方案 §4.3 机制三）：本脚本是"脚本 + 审计判读结合"里的脚本半——
它给出确定性的重合长度与初筛的专有事实标记，**最终是否豁免由审计 Agent 判读**
（脚本无法 100% 确定一段长重合是"权威原文直引"还是"应改写的判断句誊抄"）。
因此脚本同时输出 raw_overlap_hits（达长度阈值的卡片数）与 non_proprietary_hits
（初筛为非专有事实的卡片数），block 判定基于后者，审计可在判读后调整。

阈值（方案 §4.3.1 实测校准，替换原始 ≥20 字建议值）：
  - n = 12 汉字：仅作"候选重合"的探测粒度，不作判罚阈值。
  - block-len = 46 字（P75）：单张卡片与正文最长连续重合 ≥46 字，才算候选 OVERLAP-HIT。
  - block-count = 2：单章非专有事实 OVERLAP-HIT ≥2 处 → 该维度判 block(REVISE)。

专有事实豁免（方案 §4.3.1 豁免清单的启发式初筛）：
  外文原文直引 / 精确数字+单位主导 / 机构·项目专有名称 / 法条·标准编号。
  这类重合天然应逐字一致，不计入 block。脚本用启发式打 suspected_proprietary 标记，
  审计 Agent 复核后在 card-index.csv 的 transcription_check 写 waived-facts / overlap-flagged。

用法：
  python scripts/card_overlap_check.py --report research/drafts/chXX.md \\
      --cards research/notes/case-cards research/notes/tech-cards research/notes/theory-cards
  # 校准/全局模式（对合并终稿跑全部卡片，复现 §4.3.1）：--report final-report.md --cards ...
  # 机读：加 --json；调阈值：--n / --block-len / --block-count

退出码：0 = 该维度 pass（非专有 OVERLAP-HIT < block-count）；1 = block(REVISE)。
"""

import sys
import re
import json
import glob
import argparse
from pathlib import Path

# Windows 中文环境编码兼容（照 contract_check.py 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

# 专有名称/标准编号正则（法条·标准编号 + 常见机构/项目专有名，豁免清单的可判定部分）
PROPRIETARY_TERM_PATTERN = re.compile(
    r"GJB\s*\d+|ISO\s*\d+|IEC\s*\d+|IEEE\s*\d+|RFC\s*\d+|NIST|"
    r"NASA|ESA|CARA|OWASP|MetaGPT|AgentDojo|SafeReview|Starlink|Starling|"
    r"TRL\s*\d|SGP4|TLE|Cayley|Hanabi|ODP|MIT[\- ]?LL|DLR",
    re.IGNORECASE,
)


def read_text(path: str) -> str:
    """二进制安全读取，去 UTF-8 BOM、统一换行。"""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def strip_md_noise(text: str) -> str:
    """去掉 markdown 标记与字段标签、方括号引用（含 claim_id），保留纯内容并去空白。

    去空白是为了让"卡片字段值 vs 正文"的比对不受排版/换行影响；拉丁字母、数字字符
    仍完整保留，供后续专有事实启发式判断。
    """
    text = re.sub(r"\[.*?\]", "", text)   # 去方括号引用如 [CM021]
    text = re.sub(r"[#>*`_|]", "", text)  # 去 markdown 标记
    text = re.sub(r"\s+", "", text)       # 汉字比对忽略空白
    return text


def build_ngram_set(text: str, n: int) -> set:
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def classify_fragment(fragment: str):
    """对最长重合片段做专有事实启发式初筛。

    返回 (suspected_proprietary: bool, reason: str)。
    判据（任一命中即初筛为专有事实，倾向于"宁可标记、由审计人工确认"以免误杀合理引用）：
      - 外文原文直引：拉丁字母占比 > 30%（如 NASA/ESA 官方英文报告原句）
      - 精确数字+单位主导：数字字符占比 > 30%（如"从121天压缩至2.8天"一类数据串）
      - 机构/项目专有名称、法条/标准编号：命中 PROPRIETARY_TERM_PATTERN
    """
    if not fragment:
        return False, ""
    length = len(fragment)
    latin = len(re.findall(r"[A-Za-z]", fragment))
    digit = len(re.findall(r"\d", fragment))
    latin_ratio = latin / length
    digit_ratio = digit / length

    if latin_ratio > 0.30:
        return True, f"外文原文直引(拉丁字母占比{latin_ratio:.0%})"
    if digit_ratio > 0.30:
        return True, f"精确数字+单位主导(数字占比{digit_ratio:.0%})"
    m = PROPRIETARY_TERM_PATTERN.search(fragment)
    if m:
        return True, f"含专有名称/标准编号({m.group(0)})"
    return False, ""


def longest_overlap(card_clean: str, report_clean: str, hit_ngrams: set, n: int):
    """在 card_clean 上找最长连续重合片段（对 report_clean），返回 (max_len, fragment, hit_windows)。"""
    max_len = 0
    sample = ""
    hit_windows = 0
    checked_starts = set()
    for i in range(len(card_clean) - n + 1):
        frag = card_clean[i:i + n]
        if frag in hit_ngrams and i not in checked_starts:
            idx = report_clean.find(frag)
            if idx == -1:
                continue
            length = n
            while (i + length < len(card_clean) and idx + length < len(report_clean)
                   and card_clean[i + length] == report_clean[idx + length]):
                length += 1
            if length > max_len:
                max_len = length
                sample = card_clean[i:i + length]
            hit_windows += 1
            for k in range(i, i + length - n + 1):
                checked_starts.add(k)
    return max_len, sample, hit_windows


def card_id_of(path: str, raw: str) -> str:
    """卡片标识：优先文件名 stem，其次首个 ## 标题。"""
    stem = Path(path).stem
    return stem


def check(report_path: str, card_dirs, n: int, block_len: int, block_count: int) -> dict:
    report_clean = strip_md_noise(read_text(report_path))
    report_ngrams = build_ngram_set(report_clean, n)

    card_paths = []
    for d in card_dirs:
        card_paths.extend(sorted(glob.glob(str(Path(d) / "*.md"))))

    results = []
    for path in card_paths:
        raw = read_text(path)
        # 去掉首行 meta（> card_id 之类），只留正文字段内容
        body = "\n".join(
            ln for ln in raw.splitlines() if not ln.strip().startswith("> card_id")
        )
        card_clean = strip_md_noise(body)
        if len(card_clean) < n:
            continue
        card_ngrams = build_ngram_set(card_clean, n)
        hit = card_ngrams & report_ngrams
        if not hit:
            continue
        max_len, sample, hit_windows = longest_overlap(card_clean, report_clean, hit, n)
        if max_len < n:
            continue
        is_hit = max_len >= block_len
        suspected_prop, reason = classify_fragment(sample) if is_hit else (False, "")
        results.append({
            "card": card_id_of(path, raw),
            "card_file": path,
            "max_overlap_len": max_len,
            "hit_windows": hit_windows,
            "overlap_hit": is_hit,                     # 达长度阈值（候选 OVERLAP-HIT）
            "suspected_proprietary": suspected_prop,   # 启发式初筛：疑似专有事实（待审计确认）
            "proprietary_reason": reason,
            "sample_fragment": sample[:80],
        })

    results.sort(key=lambda r: -r["max_overlap_len"])

    raw_overlap_hits = [r for r in results if r["overlap_hit"]]
    non_prop_hits = [r for r in raw_overlap_hits if not r["suspected_proprietary"]]
    verdict = "block" if len(non_prop_hits) >= block_count else "pass"

    return {
        "report": report_path,
        "params": {"n": n, "block_len": block_len, "block_count": block_count},
        "cards_scanned": len(card_paths),
        "cards_with_overlap": len(results),
        "raw_overlap_hits": len(raw_overlap_hits),
        "non_proprietary_overlap_hits": len(non_prop_hits),
        "verdict": verdict,
        "results": results,
    }


def format_report(r: dict) -> str:
    p = r["params"]
    lines = [
        f"=== 卡片-正文重合度检测：{r['report']} ===",
        f"参数：n={p['n']} 探测粒度 / block-len={p['block_len']}字 / block-count={p['block_count']}处",
        f"扫描卡片 {r['cards_scanned']} 张，有重合 {r['cards_with_overlap']} 张",
        f"达长度阈值(≥{p['block_len']}字)的候选 OVERLAP-HIT：{r['raw_overlap_hits']} 张",
        f"其中初筛为非专有事实（计入 block 判定）：{r['non_proprietary_overlap_hits']} 张",
        "",
        f"{'-- 候选 OVERLAP-HIT 明细（按重合长度降序）--'}",
    ]
    shown = [x for x in r["results"] if x["overlap_hit"]]
    if not shown:
        lines.append("  （无达阈值的重合）")
    for x in shown[:30]:
        tag = "专有事实?豁免待判读" if x["suspected_proprietary"] else "非专有→计入block"
        lines.append(
            f"  [{tag}] {x['card']} | 最长重合={x['max_overlap_len']}字 | "
            f"{x['proprietary_reason'] or ''}"
        )
        lines.append(f"      片段: {x['sample_fragment']}")
    lines.extend([
        "",
        f"=== 维度裁决: {r['verdict'].upper()} "
        f"（非专有 OVERLAP-HIT {r['non_proprietary_overlap_hits']} "
        f"{'≥' if r['verdict'] == 'block' else '<'} {p['block_count']}）===",
        "注：suspected_proprietary 为脚本启发式初筛，最终豁免由审计 Agent 判读后写入 "
        "card-index.csv 的 transcription_check（pass/overlap-flagged/waived-facts）。",
    ])
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="卡片-正文重合度检测（P0-6）")
    ap.add_argument("--report", required=True, help="本章草稿或合并终稿 md")
    ap.add_argument("--cards", nargs="+", required=True, help="卡片目录（可多个，架构卡不纳入检测）")
    ap.add_argument("--n", type=int, default=12, help="n-gram 探测粒度（默认 12，方案 §4.3.1）")  # linkage-const:card_overlap_n_gram:12
    ap.add_argument("--block-len", type=int, default=46, help="最长重合判罚门槛（默认 46=P75）")  # linkage-const:card_overlap_block_len:46
    ap.add_argument("--block-count", type=int, default=2, help="单章非专有 OVERLAP-HIT block 门槛（默认 2）")  # linkage-const:card_overlap_block_count:2
    ap.add_argument("--json", action="store_true", help="输出 JSON（供审计 Agent 解析）")
    args = ap.parse_args()

    if not Path(args.report).exists():
        print(f"{FAIL} report 文件不存在: {args.report}", file=sys.stderr)
        sys.exit(2)

    r = check(args.report, args.cards, args.n, args.block_len, args.block_count)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(format_report(r))
    sys.exit(1 if r["verdict"] == "block" else 0)


if __name__ == "__main__":
    main()
