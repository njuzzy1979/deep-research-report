#!/usr/bin/env python3
"""转换器合约 + 量化统计自动检查脚本（v5 清单 #6，替代 v3 的 Bash 版）

对单章草稿或合并终稿执行两组确定性检查：
  合约层 C1-C9 —— 见 references/appendix-converter-contract.md 编号化检查规格
    C1 分章文件不含 H1 / 全文仅一个 H1
    C2 H2/H3/H4 标题无手动编号 + 粗体伪标题检测
    C3 图片使用标准 Markdown 语法（计数，可与大纲规划比对）
    C4 表格有加粗题注（题注数 vs 表格数）
    C5 无禁止内容（含密级词 / 输出隔离标记残留）
    C6 引用格式统一性（纯数字引用/斜杠分隔/S变体/独立参考文献节）
    C7 SRC 引用残留（合并后检查）
    C8 字数统计残留（全文约/本章字数/写作者自声明——2026-08-03 升级：自声明已移至独立文件）
    C9 局部参考文献节（每章独立参考文献体系）
  观察层 C10-C11（跨模型兼容性优化方案 §二 A3，第一阶段非阻塞）
    C10（F7）信源分级前缀泄露（如 "[A] xxx" 独占行首）——只计数不判负
    C11（F8）claim_id 泄露（如 [CM021]）——只计数不判负
    两项均 severity="mid"、pass 恒为 True、不纳入 high_severity_keys，
    仅用于收集真实报告语料的命中分布，供后续独立决策是否升级为阻塞检查。
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
  python scripts/contract_check.py <file.md> --merged        # 合并终稿模式（C1 允许 1 个 H1, C7 升级为 FATAL）
  python scripts/contract_check.py <file.md> --expect-figures N  # C3 与大纲规划图数比对
  python scripts/contract_check.py <file.md> --stage stage7  # 阶段 7 模式（C7=WARN 不阻断）
  python scripts/contract_check.py <file.md> --stage stage9  # 阶段 9 模式（C7=FATAL 阻断）

退出码：0 = 全部合约项通过；1 = 至少一项高严重度合约项失败（C1/C2/C5/C6/C9，合并模式下+C7）。
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

# 输出信封标记正则（跨模型兼容性优化方案 §C5：nonce 迁移）—— 共享常量，供其他脚本
# import 复用（Critical-5：scripts/merge_drafts.py 的 B1 剥离步骤必须与此保持一致，
# 否则带 nonce 的新格式标记不会被剥离，导致标记残留进入最终 Word 交付物）。
#
# nonce 是**后缀**，前缀 `[AGENT-OUTPUT-START` / `[AGENT-OUTPUT-END` 不变，因此对不含
# nonce 的旧格式（Claude tier A 默认）匹配行为与放宽前逐字节一致，只是**额外**能匹配到
# 带 nonce 的新格式 —— 这保证了 tests/golden/ 8 份快照在旧格式输入下的输出不变。
#
# 三重误匹配防护（与 scripts/output_envelope_check.py 的 ENVELOPE_MARKER_PATTERN 呼应）：
#   - nonce 格式限定 `[0-9a-f]{6,16}`（十六进制，6-16 位，全小写）
#   - 此处不强制行首/agent 名后缀（C5 是"检测残留"场景，任何位置出现即视为违规，
#     比 output_envelope_check.py 的信封配对语义更宽松是刻意的——宁可多报不可漏报）
RE_ENVELOPE_MARKER = re.compile(r"\[AGENT-OUTPUT-(?:START|END)(?::[0-9a-f]{6,16})?\]")

# 禁止内容模式（C5）—— 含密级词，门 3 安全机制前移到阶段 7
BANNED_PATTERNS = {
    "建议印刷页数": re.compile(r"建议印刷页数"),
    "图表占位": re.compile(r"图表占位|\[此处插入图|\[图\d+-\d+：|图表占位符"),
    "全文完": re.compile(r"全文完"),
    "HTML标签": re.compile(r"</?(div|span|table|br|img|p)\b", re.IGNORECASE),
    "封面元数据行": re.compile(r"^(编制单位|申报单位|编制日期)[:：]", re.MULTILINE),
    "密级标注": re.compile(r"绝密|机密|秘密|内部资料|\b内部\b|涉密"),
    # F1: 输出隔离标记残留（AGENT-OUTPUT-START/END 标记行，含可选 nonce 后缀）
    "输出隔离标记残留": RE_ENVELOPE_MARKER,
    # 2026-08-03: blockquote 章首标签变体检测（Writer 应写 `> **本章结论**：`，不得使用变体）
    "blockquote标签变体": re.compile(r"^>\s*\*\*本章(?:摘要|概览|要点|核心|概述|总结)\*\*", re.MULTILINE),
}

# 标题手动编号模式（C2）：H2-H4 后紧跟阿拉伯数字或中文数字编号
MANUAL_NUMBER_PATTERN = re.compile(
    r"^#{2,4}\s+(?:第?\s*[0-9一二三四五六七八九十百]+[\.、\s章节]|[0-9]+\.[0-9])"
)

# C2 增强：粗体伪标题模式 —— 连续 ≥3 行以 ** 开头且独占一行的粗体文本
BOLD_PSEUDO_HEADING_PATTERN = re.compile(r"^\*\*[^*]+\*\*\s*$")

# C2 豁免（仅 merged 合并终稿模式）：merge_drafts.py 按 stage-7-writing.md 规范
# 自动插入的标准章容器 H2（形如 `## 第 1 章：绪论`）。
#
# 立法意图辨析：C2 禁止的是**作者手写**编号前缀（编号应交由 Word 自动编号域生成，
# 手写会与域编号冲突产生"1.1 1.1 标题"这类重复）。而此处的章容器是**合并管道自身
# 按规范产出的结构性标记**（merge_drafts.assemble_merged() 生成），不是作者内容，
# 下游 md2docx 的 headings.py 会将其识别为 CHAPTER 并接管编号。
# 若不豁免，则任何含编号章节的真实报告在 `--merged --stage stage9` 下 C2 恒为
# fatal（且标注"不可降级放行"），交付门禁 CP6 永远无法通过——即检查器把自家管道
# 的标准输出判为致命错误。豁免范围严格限定为"章容器"这一种确定格式，
# 不放宽对作者手写编号（如 `## 1.1 xxx`、`### 二、xxx`）的拦截。
PIPELINE_CHAPTER_CONTAINER_PATTERN = re.compile(r"^##\s+第\s*\d+\s*章[：:]\s*\S")

# C6: 引用格式统一性检查
# 纯数字引用（如 [1]、[12]、[1,2,3]）
PURE_NUM_REF_PATTERN = re.compile(r"\[\d+(?:,\s*\d+)*\]")
# 斜杠分隔 SRC 引用（如 [SRC-001/026]）
SLASH_SRC_PATTERN = re.compile(r"\[SRC-\d+(?:/\d+)+\]")
# S 变体引用（如 [S001]、[S-001]）
S_VARIANT_REF_PATTERN = re.compile(r"\[S-?\d+\]")

# C7: SRC 残留检测
SRC_RESIDUE_PATTERN = re.compile(r"\[SRC-")

# C8: 字数统计/自声明残留（2026-08-03 升级为 FATAL：自声明已在独立文件 research/claims/各章节自声明.md，章草稿零容忍）
WORD_COUNT_RESIDUE_PATTERNS = {
    "全文约": re.compile(r"全文约\s*\d+\s*字"),
    "本章字数": re.compile(r"本章字数"),
    "写作者自声明": re.compile(r"写作者自声明"),
    "素材缺口标记": re.compile(r"素材缺口标记"),
    "used_in_chapter": re.compile(r"used_in_chapter"),
    "card_id": re.compile(r"引用的 card_id"),
    "篇幅预算残留": re.compile(r"^\s*>\s*\*\*篇幅预算\*\*", re.MULTILINE),
}

# C9: 局部参考文献节
# stage7 分章草稿 / 非 merged 场景专用：分章文件中"参考文献"标题（H2/H3，
# 任意后缀）一律不应出现，0 容忍——合规的全局参考文献节只应在 stage9
# finalize 阶段由流水线统一插入。
LOCAL_BIBLIOGRAPHY_PATTERN = re.compile(
    r"^#{2,3}\s+参考文献", re.MULTILINE
)

# 【仅 stage9+merged 分支使用】三个正则协同工作，任何一个都不单独参与判定，
# 必须在 check_contract() 内按判定表组合裁决（design-auditor 终审 Critical
# 修正：不得对 H2 候选做末尾锚定，否则"## 参考文献列表"这类变体后缀标题会
# 完全绕过检测——见判定表与 check_contract() 内的组合逻辑）。

# (a) H2 前缀族：圈定所有以"参考文献"开头的 H2 标题候选集合（不论后缀/是否
#     精确），仅用于统计候选总数，本身不是 pass/fail 依据。
PIPELINE_BIBLIOGRAPHY_H2_PREFIX_PATTERN = re.compile(
    r"^##\s+参考文献.*$", re.MULTILINE
)

# (b) H2 精确形式：generate_bibliography() 固定产出的标题形态（"参考文献"后
#     仅允许可选中/英文冒号，行尾无其他文字）——"是流水线自己插入的那一个"
#     的唯一可识别指纹。
PIPELINE_BIBLIOGRAPHY_H2_EXACT_PATTERN = re.compile(
    r"^##\s+参考文献\s*[:：]?\s*$", re.MULTILINE
)

# (c) H3-H6 前缀族：任何级别 H3 及以下的"参考文献"标题，不要求精确匹配——
#     流水线不产出 H3+ 级别的参考文献节，出现即是局部残留的直接证据，无
#     条件判负，优先级高于 H2 计数判定。
PIPELINE_BIBLIOGRAPHY_H3PLUS_PATTERN = re.compile(
    r"^#{3,6}\s+参考文献", re.MULTILINE
)

# C10（F7）: 信源分级前缀泄露（如 "[A] xxx"、"[C] xxx" 独占行首的分级标注）
# 参考出处：references/stage-7-writing.md:148
F7_SOURCE_TIER_PREFIX_PATTERN = re.compile(r"^\s*\[[ABCD]\]", re.MULTILINE)

# C11（F8）: claim_id 泄露（如 [CM021]、[CO012] 等草稿期内部标注残留正文）
# 参考出处：references/stage-7-writing.md:148
F8_CLAIM_ID_LEAK_PATTERN = re.compile(r"\[[A-Z]{1,3}\d{3}\]")


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


def split_paragraphs(text: str) -> list:
    """按自然段切分正文（排除标题/引用块/表格行/图片行/代码块）。

    从 compute_paragraph_stats 中提取的独立函数（跨模型兼容性优化方案 §E1）：
    QS4 段落长度分布只需要聚合统计量，而 scripts/writing_quality_check.py 的
    E1 信息密度检查（QS5_density）需要逐段文本本身（用于统计每段数据点数、
    定位"连续 500 字无数据点"的具体段落）。此函数是两处共同的段落切分口径，
    供二者 import 复用，避免切分规则出现两份实现互相漂移。
    """
    clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    paras, cur = [], []
    for line in clean.split("\n"):
        s = line.strip()
        if not s:
            if cur:
                ptext = "".join(cur)
                cnt = len(re.findall(r"[一-鿿]", ptext))
                if cnt > 0:
                    paras.append(ptext)
                cur = []
            continue
        if s.startswith("#") or s.startswith(">") or s.startswith("|") or s.startswith("!["):
            continue
        cur.append(s)
    if cur:
        ptext = "".join(cur)
        cnt = len(re.findall(r"[一-鿿]", ptext))
        if cnt > 0:
            paras.append(ptext)
    return paras


def compute_paragraph_stats(text: str) -> dict:
    """QS4: 段落长度分布。
    排除标题/引用块/表格行/图片行/代码块。

    段落切分逻辑已提取到 split_paragraphs()，本函数只做聚合统计——行为与提取
    前逐字节一致（不影响 tests/golden/ 快照）。"""
    paras = split_paragraphs(text)
    if not paras:
        return {"count": 0, "mean": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0,
                "over_600": 0, "under_150": 0, "ideal_range": 0, "longest": 0}
    lengths = sorted(len(re.findall(r"[\u4e00-\u9fff]", p)) for p in paras)
    n = len(lengths)
    def pct(data, pct):
        return data[max(0, min(n - 1, int(n * pct / 100)))]
    return {"count": n, "mean": round(sum(lengths) / n, 1),
            "p25": pct(lengths, 25), "p50": pct(lengths, 50),
            "p75": pct(lengths, 75), "p90": pct(lengths, 90),
            "over_600": sum(1 for l in lengths if l > 600),
            "under_150": sum(1 for l in lengths if l < 150),
            "ideal_range": sum(1 for l in lengths if 150 <= l <= 400),
            "longest": lengths[-1]}


def check_contract(text: str, merged: bool, expect_figures, stage: str = "stage7") -> dict:
    """执行 C1-C9 + QS1-QS3，返回结构化结果。"""
    clean = strip_code_blocks(text)
    lines = clean.split("\n")

    # C1: H1 数量
    h1_count = sum(1 for ln in lines if re.match(r"^#\s+\S", ln))
    c1_limit = 1 if merged else 0
    c1_pass = h1_count <= c1_limit

    # C2: H2-H4 手动编号
    # merged 模式下豁免管道自动生成的标准章容器（见 PIPELINE_CHAPTER_CONTAINER_PATTERN
    # 的立法意图辨析）；stage7 分章稿不应出现章容器，故不豁免。
    c2_hits = [
        ln.strip()
        for ln in lines
        if MANUAL_NUMBER_PATTERN.match(ln)
        and not (merged and PIPELINE_CHAPTER_CONTAINER_PATTERN.match(ln))
    ]
    # C2 增强：粗体伪标题检测 —— 连续 ≥3 行匹配模式
    c2_bold_hits = _detect_bold_pseudo_headings(lines)
    # C2 增强（2026-08-03）：分章文件中不应出现 H2（Writer 不写 H2，章容器由 merge 插入）
    # 注意：仅非 merged 模式生效——merged 模式下的章容器 H2 由管道合法生成，已有豁免
    if not merged:
        c2_h2_in_draft = [
            ln.strip() for ln in lines
            if re.match(r"^##\s+\S", ln)
        ]
        if c2_h2_in_draft:
            c2_hits.append(f"[H2在分章文件中违规] {c2_h2_in_draft[0][:80]}")
    c2_pass = len(c2_hits) == 0 and len(c2_bold_hits) == 0

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

    # C5: 禁止内容（含密级词 + 输出隔离标记残留 F1）
    c5_hits = {}
    for name, pat in BANNED_PATTERNS.items():
        found = pat.findall(clean)
        if found:
            c5_hits[name] = len(found)
    c5_pass = len(c5_hits) == 0

    # C6: 引用格式统一性检查（纯数字引用在 stage9 合并终稿中是预期产出，见函数 docstring）
    c6_result = _check_c6_references(clean, merged=merged, stage=stage)
    c6_pass = c6_result["pass"]

    # C7: SRC 引用残留检测
    c7_hits = SRC_RESIDUE_PATTERN.findall(clean)
    c7_count = len(c7_hits)
    # 阶段 7→WARN（Writer 应该保留 SRC），阶段 9→FATAL（finalizer 应已转换）
    c7_severity = "high" if stage == "stage9" else "mid"
    c7_pass = c7_count == 0 if stage == "stage9" else True  # stage7 不阻断

    # C8: 字数统计残留
    c8_hits = {}
    for name, pat in WORD_COUNT_RESIDUE_PATTERNS.items():
        found = pat.findall(clean)
        if found:
            c8_hits[name] = len(found)
    c8_pass = True  # WARN only，不阻断

    # C9: 局部参考文献节
    if merged and stage == "stage9":
        # --- stage9 + merged 专属分支：区分"流水线自己插入的合规参考文献节"
        # 与"别处残留的局部/变体参考文献节"（design-auditor 终审 Critical 修
        # 正后的判定表）：
        #   0 处                        → pass（合法退化，可能确无引用，交
        #                                  delivery_checklist 03b 进一步消歧）
        #   1 处且为精确形式             → pass（流水线插入的那一个）
        #   1 处但非精确形式（变体后缀） → fail（格式不确定的孤例不予放行）
        #   ≥2 处（无论精确/变体组合）   → fail（重复插入或局部残留混存）
        #   任意 H3-H6 命中              → fail（无条件，优先级最高，不因 H2
        #                                  层面合规而被抵消）
        h2_all_hits = PIPELINE_BIBLIOGRAPHY_H2_PREFIX_PATTERN.findall(clean)
        h2_exact_hits = PIPELINE_BIBLIOGRAPHY_H2_EXACT_PATTERN.findall(clean)
        h3plus_hits = PIPELINE_BIBLIOGRAPHY_H3PLUS_PATTERN.findall(clean)

        h2_total = len(h2_all_hits)
        h2_exact_total = len(h2_exact_hits)
        h2_variant_total = h2_total - h2_exact_total

        if h3plus_hits:
            c9_pass = False
        elif h2_total == 0:
            c9_pass = True
        elif h2_total == 1 and h2_exact_total == 1:
            c9_pass = True
        else:
            # h2_total == 1 且非精确形式，或 h2_total >= 2（含全精确重复场景）
            c9_pass = False

        c9_hits_paragraphs = h2_all_hits + h3plus_hits
        c9_extra_fields = {
            "h2_total": h2_total,
            "h2_exact_total": h2_exact_total,
            "h2_variant_total": h2_variant_total,
            "h3plus_total": len(h3plus_hits),
        }
    else:
        # stage7 分章草稿 / 非 merged 场景：语义不变，沿用旧版前缀匹配、0 容忍
        c9_hits_paragraphs = LOCAL_BIBLIOGRAPHY_PATTERN.findall(clean)
        c9_pass = len(c9_hits_paragraphs) == 0
        c9_extra_fields = {}

    # C10（F7）: 信源分级前缀泄露 —— 跨模型兼容性优化方案 §二 A3。
    # 第一阶段非阻塞（审查层 High-3 修订）：severity="mid"，pass 恒为 True，
    # 不纳入 high_severity_keys；仅用于收集真实报告语料的命中分布，
    # 供后续独立决策是否升级为阻塞检查（第二阶段）。
    c10_hits = [ln.strip() for ln in lines if F7_SOURCE_TIER_PREFIX_PATTERN.match(ln)]
    c10_pass = True

    # C11（F8）: claim_id 泄露 —— 同上，第一阶段非阻塞，仅计数。
    c11_hits = F8_CLAIM_ID_LEAK_PATTERN.findall(clean)
    c11_pass = True

    # QS1: 正文字数
    word_count = count_cjk_chars(text)

    result = {
        "file": None,
        "mode": "merged" if merged else "chapter",
        "stage": stage,
        "contract": {
            "C1_h1": {"count": h1_count, "limit": c1_limit, "pass": c1_pass, "severity": "high"},
            "C2_manual_number": {
                "hits": c2_hits, "count": len(c2_hits),
                "bold_pseudo_heading_hits": c2_bold_hits, "bold_pseudo_heading_count": len(c2_bold_hits),
                "pass": c2_pass, "severity": "fatal" if (merged and stage == "stage9") else "high"
            },
            "C3_image_syntax": {"figure_count": img_count, "loose_image_count": img_count_loose,
                                 "expect": expect_figures, "pass": c3_pass, "severity": "mid"},
            "C4_table_caption": {"caption_count": caption_count, "table_block_count": table_blocks,
                                  "pass": c4_pass, "severity": "mid"},
            "C5_banned": {"hits": c5_hits, "pass": c5_pass, "severity": "high"},
            "C6_reference_format": {**c6_result, "severity": "high"},
            "C7_src_residue": {"hits": c7_hits, "count": c7_count, "pass": c7_pass, "severity": c7_severity},
            "C8_word_count_residue": {"hits": c8_hits, "pass": c8_pass, "severity": "high"},
            "C9_local_bibliography": {"hits": c9_hits_paragraphs, "count": len(c9_hits_paragraphs),
                                       "pass": c9_pass, "severity": "high", **c9_extra_fields},
            "C10_source_tier_prefix": {"hits": c10_hits, "count": len(c10_hits),
                                        "pass": c10_pass, "severity": "mid"},
            "C11_claim_id_leak": {"hits": c11_hits, "count": len(c11_hits),
                                   "pass": c11_pass, "severity": "mid"},
        },
        "quant": {
            "QS1_cjk_chars": word_count,
            "QS1_est_pages": round(word_count / 800, 1),
            "QS2_figures": img_count,
            "QS3_tables": table_blocks,
            "QS4_paragraphs": compute_paragraph_stats(text),
        },
    }
    # 高严重度合约项（C1/C2/C5/C6/C9，stage9 下+C7）任一失败 → 整体 fail
    high_severity_keys = ["C1_h1", "C2_manual_number", "C5_banned", "C6_reference_format", "C8_word_count_residue", "C9_local_bibliography"]
    if stage == "stage9":
        high_severity_keys.append("C7_src_residue")
    # 致命级合约项（C2 在合并终稿模式下升级为 fatal）——失败直接阻断，不可降级
    fatal_keys = []
    for k in high_severity_keys:
        if result["contract"][k].get("severity") == "fatal":
            fatal_keys.append(k)
    result["overall_pass"] = all(result["contract"][k]["pass"] for k in high_severity_keys)
    result["fatal_keys"] = fatal_keys
    return result


def _detect_bold_pseudo_headings(lines: list) -> list:
    """C2 增强：检测粗体伪标题 —— 连续 ≥3 行以 ** 开头且独占一行的粗体文本。"""
    hits = []
    consecutive = 0
    chunk_start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if BOLD_PSEUDO_HEADING_PATTERN.match(s):
            if consecutive == 0:
                chunk_start = i
            consecutive += 1
        else:
            if consecutive >= 3:
                hits.append(f"粗体伪标题块 L{chunk_start + 1}-L{i}（{consecutive} 行连续粗体独占行）")
            consecutive = 0
    if consecutive >= 3:
        hits.append(f"粗体伪标题块 L{chunk_start + 1}-L{len(lines)}（{consecutive} 行连续粗体独占行）")
    return hits


def _check_c6_references(text: str, *, merged: bool = False, stage: str = "stage7") -> dict:
    """C6: 引用格式统一性检查。

    分阶段语义（与 C7 的 stage7/stage9 对称设计一致）：

    - **stage7（分章草稿）**：纯数字引用 ``[N]`` 是**违规** —— 写作 Agent 应统一写
      ``[SRC-XXX]``，编号由阶段 9 的 ``convert_references.py`` 按参考文献表统一生成。
      作者提前写死数字编号会与后续自动编号冲突。
    - **stage9 + merged（合并终稿）**：纯数字引用是**预期的正确输出** ——
      ``convert_references.py`` 按 GB/T 7714 顺序编码制正是把 ``[SRC-001]`` 转换为
      ``[1]``。此时若仍把 ``[N]`` 判为违规，则定稿管道会否定自己上一步的正确产出，
      导致任何含参考文献的报告都无法通过交付门禁（``delivery_checklist`` 不可达）。

    因此 ``pure_num`` 一项仅在非 stage9-merged 下参与判负；``slash_src``（如
    ``[SRC-001/026]``）与 ``s_variant``（如 ``[S001]``）两类是任何阶段都不合法的
    格式错误，始终参与判负。
    """
    result = {"pass": True, "pure_num_hits": [], "slash_src_hits": [], "s_variant_hits": [],
              "local_bib_hits": []}
    # 纯数字引用 —— 合并终稿中是 convert_references 的预期产出，不判负（仍如实记录）
    pure_num_is_expected = merged and stage == "stage9"
    result["pure_num_expected"] = pure_num_is_expected
    pure_nums = PURE_NUM_REF_PATTERN.findall(text)
    if pure_nums:
        result["pure_num_hits"] = pure_nums[:10]  # 最多记录 10 个样本
        result["pure_num_count"] = len(pure_nums)
        if not pure_num_is_expected:
            result["pass"] = False
    # 斜杠分隔 SRC
    slash_hits = SLASH_SRC_PATTERN.findall(text)
    if slash_hits:
        result["slash_src_hits"] = slash_hits[:10]
        result["slash_src_count"] = len(slash_hits)
        result["pass"] = False
    # S 变体
    s_variants = S_VARIANT_REF_PATTERN.findall(text)
    if s_variants:
        result["s_variant_hits"] = s_variants[:10]
        result["s_variant_count"] = len(s_variants)
        result["pass"] = False
    return result


def format_text_report(r: dict) -> str:
    c = r["contract"]
    q = r["quant"]

    def mark(p):
        return OK if p else FAIL

    lines = [
        f"=== 合约 + 量化检查：{r['file']} （模式：{r['mode']} / 阶段：{r.get('stage', 'stage7')}）===",
        "",
        "-- 合约层 C1-C9 --",
        f"{mark(c['C1_h1']['pass'])} C1 H1数量: {c['C1_h1']['count']} (上限 {c['C1_h1']['limit']})",
    ]
    c2 = c["C2_manual_number"]
    c2_total = c2.get("count", 0) + c2.get("bold_pseudo_heading_count", 0)
    lines.append(f"{mark(c2['pass'])} C2 标题手动编号: {c2.get('count', 0)} 处 / 粗体伪标题块: {c2.get('bold_pseudo_heading_count', 0)} 块 (共 {c2_total} 处，应为 0)")
    if c2.get("hits"):
        for h in c2["hits"][:5]:
            lines.append(f"      - {h}")
    if c2.get("bold_pseudo_heading_hits"):
        for h in c2["bold_pseudo_heading_hits"][:3]:
            lines.append(f"      - [粗体伪标题] {h}")

    c3 = c["C3_image_syntax"]
    exp = "" if c3["expect"] is None else f" / 大纲规划 {c3['expect']}"
    lines.append(f"{mark(c3['pass'])} C3 图片(标准语法): {c3['figure_count']} 张{exp}")
    c4 = c["C4_table_caption"]
    lines.append(f"{mark(c4['pass'])} C4 表格题注: {c4['caption_count']} 题注 / {c4['table_block_count']} 表格块")
    c5 = c["C5_banned"]
    lines.append(f"{mark(c5['pass'])} C5 禁止内容: {'无' if c5['pass'] else c5['hits']}")
    if not c5["pass"] and "密级标注" in c5["hits"]:
        lines.append(f"      {WARN} 检测到密级词 —— 红线，一律阻断（门 3 安全前移）")
    if not c5["pass"] and "输出隔离标记残留" in c5.get("hits", {}):
        lines.append(f"      {FAIL} 检测到输出隔离标记残留 [AGENT-OUTPUT-START/END]（含 nonce 变体）—— 阻断")

    c6 = c["C6_reference_format"]
    lines.append(f"{mark(c6['pass'])} C6 引用格式统一: {'无违规' if c6['pass'] else _c6_detail(c6)}")

    c7 = c["C7_src_residue"]
    c7_mark = OK if c7["pass"] else (FAIL if c7["severity"] == "high" else WARN)
    lines.append(f"{c7_mark} C7 SRC残留: {c7['count']} 处 (严重度={c7['severity']})")

    c8 = c["C8_word_count_residue"]
    c8_mark = FAIL if c8["hits"] else OK
    lines.append(f"{c8_mark} C8 字数统计/自声明残留(FATAL): {'无' if not c8['hits'] else c8['hits']}")

    c9 = c["C9_local_bibliography"]
    if "h2_total" in c9:
        lines.append(
            f"{mark(c9['pass'])} C9 局部参考文献节(stage9+merged专属判定): "
            f"H2精确={c9.get('h2_exact_total', 0)} "
            f"H2变体={c9.get('h2_variant_total', 0)} "
            f"H3+残留={c9.get('h3plus_total', 0)}"
        )
    else:
        lines.append(f"{mark(c9['pass'])} C9 局部参考文献节: {c9['count']} 处 (应为 0)")

    # C10/C11（跨模型兼容性优化方案 §二 A3）：第一阶段非阻塞，pass 恒为 True，
    # 仅计数展示——不用 mark()（会恒显示 OK），改用中性标记区分"有命中但不阻断"。
    c10 = c["C10_source_tier_prefix"]
    c10_mark = WARN if c10["count"] > 0 else OK
    lines.append(f"{c10_mark} C10 信源分级前缀泄露(F7，非阻塞观察期): {c10['count']} 处")
    if c10.get("hits"):
        for h in c10["hits"][:5]:
            lines.append(f"      - {h}")

    c11 = c["C11_claim_id_leak"]
    c11_mark = WARN if c11["count"] > 0 else OK
    lines.append(f"{c11_mark} C11 claim_id泄露(F8，非阻塞观察期): {c11['count']} 处")
    if c11.get("hits"):
        for h in c11["hits"][:5]:
            lines.append(f"      - {h}")

    lines.extend([
        "",
        "-- 量化层 QS1-QS4 --",
        f"     QS1 正文字数(中文): {q['QS1_cjk_chars']} 字 (约 {q['QS1_est_pages']} 页)",
        f"     QS2 图片引用数: {q['QS2_figures']}",
        f"     QS3 表格数: {q['QS3_tables']}",
    ])
    qs4 = q.get("QS4_paragraphs", {})
    if qs4 and qs4.get("count", 0) > 0:
        lines.extend([
            f"     QS4 段落总数: {qs4['count']} | 平均: {qs4['mean']} 字",
            f"     QS4 分位数: P25={qs4['p25']} P50={qs4['p50']} P75={qs4['p75']} P90={qs4['p90']}",
            f"     QS4 理想区间(150-400字): {qs4['ideal_range']}/{qs4['count']}",
            f"     QS4 超长段落(>600字): {qs4['over_600']} 个 (建议拆分)",
        ])
    lines.append("")
    high_keys = ["C1_h1", "C2_manual_number", "C5_banned", "C6_reference_format", "C9_local_bibliography"]
    if r.get("stage") == "stage9":
        high_keys.append("C7_src_residue")
    failed = [k for k in high_keys if not c[k]["pass"]]
    fatal_failed = [k for k in (r.get("fatal_keys", [])) if not c[k]["pass"]]
    if fatal_failed:
        lines.append(f"=== 总判定: FATAL (致命项 {fatal_failed} 失败——合并终稿中不可降级放行) ===")
    elif failed:
        lines.append(f"=== 总判定: FAIL (高严重度项 {failed} 存在失败) ===")
    else:
        lines.append(f"=== 总判定: PASS ===")
    return "\n".join(lines)


def _c6_detail(c6: dict) -> str:
    parts = []
    if c6.get("pure_num_hits"):
        parts.append(f"纯数字引用 {c6.get('pure_num_count', 0)} 处")
    if c6.get("slash_src_hits"):
        parts.append(f"斜杠分隔SRC {c6.get('slash_src_count', 0)} 处")
    if c6.get("s_variant_hits"):
        parts.append(f"S变体 {c6.get('s_variant_count', 0)} 处")
    return ", ".join(parts) if parts else "无违规"


def main():
    parser = argparse.ArgumentParser(description="转换器合约 C1-C9 + 量化 QS1-QS3 检查")
    parser.add_argument("file", help="待检查的 Markdown 文件（单章草稿或合并终稿）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供审计 Agent 解析）")
    parser.add_argument("--merged", action="store_true", help="合并终稿模式（C1 允许 1 个 H1）")
    parser.add_argument("--expect-figures", type=int, default=None, help="C3 与大纲规划图数比对")
    parser.add_argument("--stage", choices=["stage7", "stage9"], default="stage7",
                        help="检查阶段：stage7（C7=WARN不阻断）| stage9（C7=FATAL阻断）默认 stage7")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"{FAIL} 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(2)

    text = read_text(args.file)
    result = check_contract(text, args.merged, args.expect_figures, args.stage)
    result["file"] = args.file

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
