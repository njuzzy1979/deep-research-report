#!/usr/bin/env python3
"""Phase A/B 承诺一致性机械校验（跨模型兼容性优化方案 §三 B4）。

背景（方案 §B4，本批被刻意排在 C4 之后——§七修订 Critical-2 裁决）：本脚本是
"消费者"，消费的正是 `scripts/phase_a_to_json.py`（第 7 批 C4）落盘的 Phase A/B
JSON 结构化格式（`schemas/auditor-phase-a.schema.json` / `auditor-phase-b.schema.json`）。
排在 C4 之后，才能保证格式定义先于消费逻辑存在。

职责：**机械**校验 Phase A（盲态预承诺）与 Phase B（明态打分）之间的一致性，
替代"模型自查自"的自证循环——具体对应 `agents/chapter_auditor_agent.md` 的红线
**A5**（"Phase B 每个 block/warn 判定必须包含 Phase A 对应触发词原文子串"）。

────────────────────────────────────────────────────────────────────────────
⚠️ 天花板声明（如实标注，不得宣称"已解决盲态问题"，务必读完再使用本脚本）

    本脚本检查的是"文字层面是否复述了关键词"，**不能证明**模型真的做到了
    "先承诺后打分"，而不是"先看稿再回填一份看似匹配 Phase A 的文本"。这是
    substring/token-overlap 匹配机制的**固有天花板**——Claude 上如此，弱模型
    上更甚。真正堵死这条漂移路径需要**架构级隔离**：orchestrator 保证 Phase B
    的 prompt 拼接顺序是"先注入 Phase A 落盘文件 → 再注入草稿"，且 Phase A
    阶段物理上拿不到草稿正文（`chapter_auditor_agent.md` 已有此项流程约束，
    但那是流程层面的隔离，不是本脚本能验证的）。

    本脚本的价值是**显著提高作弊成本**（从"纯自律"升级为"文本要对得上落盘
    证据"）——**不是 100% 保证**。orchestrator/审阅者不应把"本脚本判定通过"
    等同于"盲态纪律确实被遵守"。
────────────────────────────────────────────────────────────────────────────

⚠️ 调用者声明：本脚本由 **orchestrator** 调用，不由 `chapter_auditor_agent`
自调（方案明确要求）。让被检查者运行检查自己的脚本，在弱模型上等于没检查
——弱模型完全可能"先看到自己会被 lint 检查"就调整输出让 lint 通过，而不
是真正遵守盲态纪律。调用时机见 `references/workflow-stage7.md`
"Phase A/B 输出规模应对"节的编排步骤。

────────────────────────────────────────────────────────────────────────────
分词集合交集比例算法（红线 A5 的执行方式，而非严格 substring）

方案原文明确要求："用分词后集合交集比例而非严格 substring——严格 substring
对措辞变化过于脆弱"。本脚本自研轻量分词（不依赖 jieba，环境中未安装）：
    - 英文/数字 token：正则 `[A-Za-z][A-Za-z0-9_.]*|\\d+`，长度 ≥2 才计入
    - 中文字符 2-gram：CJK 字符先剔除非 CJK 噪声，再按相邻 2 字符滑窗切分

相似度采用**覆盖率式**（非对称，以 Phase A 触发词为分母）：
    ratio = |tokens(Phase A 触发词) ∩ tokens(Phase B 判定文本)| / |tokens(Phase A 触发词)|
这比对称 Jaccard 更贴合"Phase B 是否复述了 Phase A 关键词"这一语义——不惩罚
Phase B 判定文本比触发词长（附带证据描述本就该更长）。

阈值默认 **0.4**，依据是对 `auditor_contract.json` 真实触发词样本的实测：
    - 同义改写（措辞变化但语义保留）：ratio ≈ 0.52 ~ 0.61
    - 无关/未复述文本：ratio ≈ 0.0 ~ 0.05
    - 原文子串（含前缀包裹）：ratio = 1.0
0.4 留出足够安全边际（低于全部同义改写样本、高于全部无关样本），可用
`--threshold` 调整。严格 substring 做法会把全部同义改写样本误判为不匹配
（因为不是原文子串），这正是方案要求"分词交集比例而非严格 substring"的
价值所在（见 tests/test_precommit_consistency_check.py 的鲁棒性对比用例）。

────────────────────────────────────────────────────────────────────────────
批次完整性校验的复用方式（不重复实现，见下方"设计决策"）

`scripts/phase_a_to_json.py` 已实现"批次是否完整"的机械校验
（`merge_batch_files()`：核对元数据 phase/chapter 一致、批次号覆盖 1/2/3
且不重复、声明 dims 数与实际维度小节数一致、维度 id 集合与 `batch_grouping`
声明一致）——这发生在 **Phase A Markdown → JSON 转换**这一步，早于本脚本。
若批次不完整，`phase_a_to_json.py --merge` 会直接报错，压根不会产出
`chXX-precommit.json`，本脚本也就拿不到输入文件。

因此本脚本**不重复实现批次完整性校验**，而是做互补的检查——"维度完整性"：
即使批次机制本身完整（各批次 dims 数与 id 集合都对得上元数据声明），也要
确认最终合并出的 Phase A JSON 是否覆盖了审计合约要求的全部核心维度，以及
Phase A 与 Phase B 各自涉及的维度集合是否一致（Phase A 承诺了但 Phase B
没打分 / Phase B 打分了 Phase A 未承诺的维度，两者都违反盲态预承诺纪律）。
这是两个不同层次的检查，不冗余：
    - phase_a_to_json.py 的批次校验：关注"每一批声明的 dims 与实际是否一致"
    - 本脚本的维度完整性检查：关注"最终 JSON 是否覆盖了应审计的全部维度，
      以及 A/B 两阶段的维度集合是否一致"

用法：
    python scripts/precommit_consistency_check.py <phaseA.json> <phaseB.json> [--json]
    python scripts/precommit_consistency_check.py <phaseA.json> <phaseB.json> \\
        --threshold 0.4 --phase-b-report research/chapter-reports/chXX-audit-phaseB.md

（文件名不做硬编码约定，两个位置参数均按调用方传入的实际路径读取。
`references/workflow-stage7.md` 中 orchestrator 的实际落盘约定为 Phase A ->
`research/chapter-reports/chXX-precommit.json`（`phase_a_to_json.py` 既有产物，
第 7 批 C4 已确立）、Phase B -> `research/chapter-reports/chXX-audit-phaseB.json`
（本批新增，②b 步由 orchestrator 从 Phase B 报告的 3 项裁决相关小节抽取组装）。）

`--phase-b-report` 为可选参数：红线 **A1**（量化维度数字须逐字复制自脚本输出，
代理指标为"检测报告是否含脚本输出特征串"）与 **A4**（恰好一行
verdict=PASS/REVISE）历史上都是针对 Phase B **原始 Markdown 报告文本**设计的
lint，而本脚本的主接口消费的是结构化 JSON（`verdict` 是 JSON 字段，其"恰好
一个值"在 JSON 对象模型下天然成立，不构成有意义的文本格式检查）。若
orchestrator 同时提供了 Phase B 的原始 Markdown 报告路径，本脚本会额外对
该文本执行 A1 代理指标检测（对齐 C4 后的新形态：检测是否含 JSON 摘要字段
引用 + `chXX-scripts.json` 落盘路径引用，**不是**检测已废弃的"贴完整 stdout"
形态）与 A4 检测（`verdict=PASS`/`verdict=REVISE` 恰好一行）；不提供时，
这两项在输出中显式标记为 `"skipped"`（不是静默跳过，也不计入 pass/fail）。

退出码：0 = Phase A/B 一致（含 schema 校验通过、维度完整、A5 一致性达标、
           verdict_rule 交叉核对一致，以及提供 --phase-b-report 时 A1/A4 达标）；
       1 = 存在不一致（schema 校验失败 / 维度不完整 / A5 未达阈值 /
           verdict_rule 不符 / A1 或 A4 检测未通过）；
       2 = 文件不存在 / JSON 解析失败 / 契约或 schema 加载异常 /
           两份输入文件的章节标识不匹配（用法错误，非内容不一致）。
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

# schema 校验复用 schema_validate.py，不重复实现校验逻辑
try:
    import schema_validate as sv
except ImportError:
    sv = None

# 维度 id 合法性 + 已知核心维度集合复用 phase_a_to_json.py，不重复实现契约解析
try:
    from phase_a_to_json import load_known_dimension_ids, read_text as _read_text_bom_safe
except ImportError:
    load_known_dimension_ids = None
    _read_text_bom_safe = None

# 降级台账（容错导入，沿用 scripts/output_envelope_check.py:61-64 同款模式）
try:
    from degradation_log import record_degradation
except ImportError:
    def record_degradation(**kwargs):  # type: ignore[no-redef]
        pass

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDITOR_CONTRACT_PATH = _PROJECT_ROOT / "agents" / "contracts" / "auditor_contract.json"

CHAPTER_ID_PATTERN = re.compile(r"^ch\d{2,3}$")

# A5 一致性判定的默认阈值（依据见模块 docstring 的实测数据）
DEFAULT_THRESHOLD = 0.4

# 英文/数字 token（长度 >=2 才计入，避免单字母噪声）
_EN_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.]*|\d+")
# CJK 字符范围（与 contract_check.py 的 count_cjk_chars 同一区间习惯一致）
_NON_CJK_PATTERN = re.compile(r"[^一-鿿]")

# A4（可选 Markdown 报告模式）：`verdict=PASS` / `verdict=REVISE` 独占一行
RE_VERDICT_LINE = re.compile(r"^\s*verdict\s*=\s*(PASS|REVISE)\s*$", re.MULTILINE)
# A1 代理指标（可选 Markdown 报告模式，对齐 C4 后新形态）：落盘路径引用
RE_SCRIPTS_JSON_PATH_REF = re.compile(r"chapter-reports[/\\]ch\d{2,3}-scripts\.json")
# A1 代理指标：JSON 摘要特征（裁决相关字段名 或 JSON 代码块）
RE_JSON_SUMMARY_HINT = re.compile(
    r"```json|\b(C1_h1|C2_manual_number|C3_image_syntax|C4_table_caption|C5_banned|"
    r"QS1_cjk_chars|QS2_figures|QS3_tables)\b"
)


# ---------------------------------------------------------------------------
# 分词 + 交集比例（红线 A5 的核心算法，见模块 docstring）
# ---------------------------------------------------------------------------


def tokenize(text: str) -> set:
    """轻量分词：英文/数字 token（正则）+ 中文字符 2-gram（jieba 未安装，见方案调研）。"""
    tokens: set = set()
    for m in _EN_TOKEN_PATTERN.finditer(text or ""):
        tok = m.group(0).lower()
        if len(tok) >= 2:
            tokens.add(tok)
    cjk_text = _NON_CJK_PATTERN.sub("", text or "")
    for i in range(len(cjk_text) - 1):
        tokens.add(cjk_text[i : i + 2])
    if len(cjk_text) == 1:
        tokens.add(cjk_text)
    return tokens


def token_overlap_ratio(reference_tokens: set, candidate_tokens: set) -> float:
    """覆盖率式相似度：reference（Phase A 触发词）token 有多少比例出现在 candidate 中。

    reference 为空集时返回 1.0（无触发词可比对，视为无约束通过，由调用方在
    维度完整性检查中另行捕捉"Phase A 缺该维度触发词"的情形，不在此处重复报错）。
    """
    if not reference_tokens:
        return 1.0
    return len(reference_tokens & candidate_tokens) / len(reference_tokens)


# ---------------------------------------------------------------------------
# 契约元数据加载（维度 hint + severity，供 A5 参考文本构造与 verdict_rule 核对）
# ---------------------------------------------------------------------------


def load_dimension_meta(contract_path: Optional[Path] = None) -> dict:
    """读取 auditor_contract.json 全部维度的 severity + 三个 hint 字段。

    返回 {dim_id: {"severity", "what_to_look_for_hint", "what_triggers_warn_hint",
    "what_triggers_block_hint"}}，覆盖 dimensions + proposal_extra（29 个）。
    """
    path = contract_path or AUDITOR_CONTRACT_PATH
    contract = json.loads(path.read_text(encoding="utf-8-sig"))
    meta = {}
    for d in contract["dimensions"] + contract.get("proposal_extra", []):
        meta[d["id"]] = {
            "severity": d.get("severity"),
            "what_to_look_for_hint": d.get("what_to_look_for_hint", ""),
            "what_triggers_warn_hint": d.get("what_triggers_warn_hint", ""),
            "what_triggers_block_hint": d.get("what_triggers_block_hint", ""),
        }
    return meta


def load_core_dimension_ids(contract_path: Optional[Path] = None) -> set:
    """核心 24 维度 id（不含 proposal_extra 的 5 个立项专属维度——非立项报告不适用）。"""
    path = contract_path or AUDITOR_CONTRACT_PATH
    contract = json.loads(path.read_text(encoding="utf-8-sig"))
    return {d["id"] for d in contract["dimensions"]}


# ---------------------------------------------------------------------------
# 内容级检查项
# ---------------------------------------------------------------------------


def extract_phase_a_chapter(phase_a_obj: dict) -> tuple:
    """从 phaseA JSON 顶层提取唯一章节 key 及其维度字典。

    本脚本逐章调用（对应 orchestrator 逐章串行编排），要求 phaseA JSON 顶层
    恰好含 1 个章节键；不满足视为用法错误（传错文件/误合并多章），非内容
    不一致，由调用方按 exit code 2 处理。
    """
    if len(phase_a_obj) != 1:
        raise ValueError(
            f"phaseA JSON 顶层应恰好含 1 个章节键，实际 {len(phase_a_obj)} 个：{sorted(phase_a_obj)}"
        )
    chapter_id = next(iter(phase_a_obj))
    return chapter_id, phase_a_obj[chapter_id]


def build_phase_a_reference_texts(phase_a_dims: dict, dim_meta: dict) -> dict:
    """为每个维度构造 A5 一致性核对用的参考文本 {dim_id: {"block": str, "warn": str}}。

    confirm 模式：直接用契约预置的 what_triggers_block_hint / what_triggers_warn_hint。
    adjust 模式：契约 hint 与 adjust 说明文本取并集（token 层面拼接），因为
    `chapter_auditor_agent.md`（"本章为何需要调整预置的 what_to_look_for/
    what_triggers_block/what_triggers_warn"）中 adjust 描述的是对基线 hint 的
    修正/补充而非整体替换——这是本脚本的一处设计决策：若之后确认理解有误，
    需要在 auditor_contract.json 或 Phase A schema 补充结构化的
    adjust_block/adjust_warn 分离字段，而不是共用一个 text。
    """
    refs = {}
    for dim_id, entry in phase_a_dims.items():
        hint = dim_meta.get(dim_id, {})
        block_hint = hint.get("what_triggers_block_hint", "")
        warn_hint = hint.get("what_triggers_warn_hint", "")
        if entry.get("mode") == "adjust":
            adjust_text = entry.get("text", "")
            block_ref = f"{block_hint}\n{adjust_text}"
            warn_ref = f"{warn_hint}\n{adjust_text}"
        else:
            block_ref = block_hint
            warn_ref = warn_hint
        refs[dim_id] = {"block": block_ref, "warn": warn_ref}
    return refs


def check_dimension_completeness(phase_a_dims: set, phase_b_dims: set, core_ids: set) -> dict:
    """维度完整性检查（互补于 phase_a_to_json.py 的批次完整性校验，见模块 docstring）。"""
    missing_in_phase_b = sorted(phase_a_dims - phase_b_dims)
    extra_in_phase_b = sorted(phase_b_dims - phase_a_dims)
    missing_core_in_phase_a = sorted(core_ids - phase_a_dims)
    return {
        "missing_in_phase_b": missing_in_phase_b,
        "extra_in_phase_b": extra_in_phase_b,
        "missing_core_in_phase_a": missing_core_in_phase_a,
        "passed": not missing_in_phase_b and not extra_in_phase_b and not missing_core_in_phase_a,
    }


def check_a5_consistency(phase_a_dims: dict, phase_b_scores: dict, dim_meta: dict, threshold: float) -> dict:
    """红线 A5：Phase B 每个 block/warn 判定须 token 交集比例达阈值复述 Phase A 触发词。

    pass 判定不检查（未触发 block/warn，无需复述触发词）。
    """
    refs = build_phase_a_reference_texts(phase_a_dims, dim_meta)
    results = []
    for dim_id, score_entry in phase_b_scores.items():
        verdict = score_entry.get("verdict")
        if verdict not in ("block", "warn"):
            continue
        evidence = score_entry.get("evidence", "")
        ref_text = refs.get(dim_id, {}).get(verdict, "")
        if not ref_text.strip():
            results.append({
                "dimension": dim_id, "verdict": verdict, "ratio": None,
                "passed": False,
                "reason": "phase A 缺少该维度对应触发词参考文本，无法比对（维度完整性检查另行捕捉）",
            })
            continue
        ratio = token_overlap_ratio(tokenize(ref_text), tokenize(evidence))
        results.append({
            "dimension": dim_id, "verdict": verdict, "ratio": round(ratio, 4),
            "passed": ratio >= threshold, "threshold": threshold,
        })
    return {
        "threshold": threshold,
        "results": results,
        "passed": all(r["passed"] for r in results),
    }


def check_verdict_rule(dimension_scores: dict, dim_meta: dict, actual_verdict: str) -> dict:
    """交叉核对 auditor_contract.json 的 verdict_rule：任一 high 严重度维度 block → REVISE，否则 PASS。"""
    high_block_dims = sorted(
        d for d, s in dimension_scores.items()
        if dim_meta.get(d, {}).get("severity") == "high" and s.get("verdict") == "block"
    )
    expected_verdict = "REVISE" if high_block_dims else "PASS"
    return {
        "expected_verdict": expected_verdict,
        "actual_verdict": actual_verdict,
        "high_block_dims": high_block_dims,
        "passed": expected_verdict == actual_verdict,
    }


def check_a1_script_output_proxy(report_text: str) -> dict:
    """红线 A1 代理指标（可选，需 --phase-b-report）：对齐 C4 后的新形态。

    C4 已把"贴完整 stdout"改为"贴 JSON 摘要 + 落盘路径"，因此本检测对齐新
    形态——检测报告是否含裁决相关字段名/JSON 代码块 + `chXX-scripts.json`
    落盘路径引用；不检测已废弃的"完整 stdout"形态。
    """
    has_path_ref = bool(RE_SCRIPTS_JSON_PATH_REF.search(report_text))
    has_json_summary = bool(RE_JSON_SUMMARY_HINT.search(report_text))
    return {
        "has_scripts_json_path_ref": has_path_ref,
        "has_json_summary_fields": has_json_summary,
        "passed": has_path_ref and has_json_summary,
    }


def check_a4_single_verdict_line(report_text: str) -> dict:
    """红线 A4（可选，需 --phase-b-report）：恰好一行 `verdict=PASS`/`verdict=REVISE`。"""
    matches = RE_VERDICT_LINE.findall(report_text)
    return {
        "verdict_line_count": len(matches),
        "matched_values": matches,
        "passed": len(matches) == 1,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_check(phase_a_obj: dict, phase_b_obj: dict, threshold: float,
              phase_b_report_text: Optional[str], contract_path: Optional[Path] = None) -> dict:
    """执行全部内容级检查，返回结构化结果。不做文件 I/O（供测试直接构造对象调用）。"""
    chapter_id, phase_a_dims = extract_phase_a_chapter(phase_a_obj)

    phase_b_chapter_id = phase_b_obj.get("chapter_id")
    if phase_b_chapter_id != chapter_id:
        raise ValueError(
            f"章节标识不匹配：phaseA={chapter_id!r} vs phaseB={phase_b_chapter_id!r}（两份输入文件配对错误）"
        )

    dim_meta = load_dimension_meta(contract_path)
    core_ids = load_core_dimension_ids(contract_path)

    phase_b_scores = phase_b_obj.get("dimension_scores", {})

    dim_completeness = check_dimension_completeness(
        set(phase_a_dims), set(phase_b_scores), core_ids
    )
    a5 = check_a5_consistency(phase_a_dims, phase_b_scores, dim_meta, threshold)
    verdict_rule = check_verdict_rule(phase_b_scores, dim_meta, phase_b_obj.get("verdict"))

    a1 = check_a1_script_output_proxy(phase_b_report_text) if phase_b_report_text is not None else None
    a4 = check_a4_single_verdict_line(phase_b_report_text) if phase_b_report_text is not None else None

    return {
        "chapter_id": chapter_id,
        "dimension_completeness": dim_completeness,
        "a5_consistency": a5,
        "verdict_rule": verdict_rule,
        "a1_script_output_proxy": a1 if a1 is not None else {"status": "skipped", "reason": "未提供 --phase-b-report"},
        "a4_single_verdict_line": a4 if a4 is not None else {"status": "skipped", "reason": "未提供 --phase-b-report"},
    }


def derive_overall(schema_a: dict, schema_b: dict, content: dict) -> dict:
    """汇总 schema 校验 + 内容级检查，得出 overall_pass 与可路由的 failure_stage。"""
    dim_completeness = content["dimension_completeness"]
    a5 = content["a5_consistency"]
    verdict_rule = content["verdict_rule"]
    a1 = content["a1_script_output_proxy"]
    a4 = content["a4_single_verdict_line"]

    a1_checked = "passed" in a1
    a4_checked = "passed" in a4

    phase_a_ok = schema_a["valid"] and not dim_completeness["missing_core_in_phase_a"]
    phase_b_ok = (
        schema_b["valid"]
        and not dim_completeness["missing_in_phase_b"]
        and not dim_completeness["extra_in_phase_b"]
        and a5["passed"]
        and verdict_rule["passed"]
        and (not a1_checked or a1["passed"])
        and (not a4_checked or a4["passed"])
    )

    overall_pass = phase_a_ok and phase_b_ok
    failure_stage = None
    if not phase_a_ok:
        failure_stage = "phaseA"
    elif not phase_b_ok:
        failure_stage = "phaseB"

    return {
        "overall_pass": overall_pass,
        "failure_stage": failure_stage,
        "phase_a_ok": phase_a_ok,
        "phase_b_ok": phase_b_ok,
    }


def format_text_report(result: dict) -> str:
    lines = [f"=== Phase A/B 承诺一致性机械校验：chapter={result.get('chapter_id')} ==="]

    sa = result["schema_phase_a"]
    sb = result["schema_phase_b"]
    sa_desc = "通过" if sa["valid"] else "失败({}处)".format(sa["error_count"])
    sb_desc = "通过" if sb["valid"] else "失败({}处)".format(sb["error_count"])
    lines.append(f"{OK if sa['valid'] else FAIL} Phase A schema 校验: {sa_desc}")
    lines.append(f"{OK if sb['valid'] else FAIL} Phase B schema 校验: {sb_desc}")

    dc = result["dimension_completeness"]
    lines.append(f"{OK if dc['passed'] else FAIL} 维度完整性: "
                 f"缺失于B={dc['missing_in_phase_b']} 多余于B={dc['extra_in_phase_b']} "
                 f"A未覆盖核心维度={dc['missing_core_in_phase_a']}")

    a5 = result["a5_consistency"]
    lines.append(f"{OK if a5['passed'] else FAIL} A5一致性(阈值={a5['threshold']}): 共{len(a5['results'])}项block/warn判定")
    for r in a5["results"]:
        mark = OK if r["passed"] else FAIL
        lines.append(f"      {mark} {r['dimension']} ({r['verdict']}): ratio={r.get('ratio')}")

    vr = result["verdict_rule"]
    lines.append(f"{OK if vr['passed'] else FAIL} verdict_rule核对: 预期={vr['expected_verdict']} 实际={vr['actual_verdict']} "
                 f"(high严重度block维度={vr['high_block_dims']})")

    a1 = result["a1_script_output_proxy"]
    if "passed" in a1:
        lines.append(f"{OK if a1['passed'] else FAIL} A1代理指标: scripts.json路径引用={a1['has_scripts_json_path_ref']} "
                     f"JSON摘要字段={a1['has_json_summary_fields']}")
    else:
        lines.append(f"{WARN} A1代理指标: 已跳过（{a1['reason']}）")

    a4 = result["a4_single_verdict_line"]
    if "passed" in a4:
        lines.append(f"{OK if a4['passed'] else FAIL} A4恰一行verdict: 计数={a4['verdict_line_count']}")
    else:
        lines.append(f"{WARN} A4恰一行verdict: 已跳过（{a4['reason']}）")

    lines.append("")
    if result["overall_pass"]:
        lines.append("=== 总判定: PASS（Phase A/B 一致） ===")
    else:
        lines.append(f"=== 总判定: FAIL（failure_stage={result['failure_stage']}） ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase A/B 承诺一致性机械校验（跨模型兼容性优化方案 §B4）——由 orchestrator 调用，不由 chapter_auditor_agent 自调"
    )
    parser.add_argument("phase_a", help="Phase A JSON 文件路径（符合 auditor-phase-a.schema.json）")
    parser.add_argument("phase_b", help="Phase B JSON 文件路径（符合 auditor-phase-b.schema.json）")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"A5 token 交集比例阈值，默认 {DEFAULT_THRESHOLD}（依据见模块 docstring）")
    parser.add_argument("--phase-b-report", default=None,
                        help="可选：Phase B 原始 Markdown 报告路径，提供后额外执行 A1/A4 检测")
    parser.add_argument("--contract", default=None, help="可选：覆盖 auditor_contract.json 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    phase_a_path = Path(args.phase_a)
    phase_b_path = Path(args.phase_b)

    for p in (phase_a_path, phase_b_path):
        if not p.exists():
            print(f"{FAIL} 文件不存在: {p}", file=sys.stderr)
            sys.exit(2)

    try:
        phase_a_obj = json.loads(phase_a_path.read_text(encoding="utf-8-sig"))
        phase_b_obj = json.loads(phase_b_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"{FAIL} JSON 读取/解析失败: {e}", file=sys.stderr)
        record_degradation(
            stage="stage7", component="precommit_consistency_check",
            reason="json_parse_failed", level="L-记录",
            fallback_used="abort", impact="Phase A/B 一致性校验无法执行",
            input_path=str(phase_a_path),
        )
        sys.exit(2)

    contract_path = Path(args.contract) if args.contract else None

    if sv is None:
        print(f"{FAIL} scripts/schema_validate.py 不可用，无法完成 schema 校验", file=sys.stderr)
        sys.exit(2)

    try:
        schema_a = sv.validate_instance(phase_a_obj, sv.load_schema("auditor-phase-a"))
        schema_b = sv.validate_instance(phase_b_obj, sv.load_schema("auditor-phase-b"))
    except Exception as e:
        print(f"{FAIL} schema 校验过程异常: {e}", file=sys.stderr)
        sys.exit(2)

    phase_b_report_text = None
    if args.phase_b_report:
        report_path = Path(args.phase_b_report)
        if not report_path.exists():
            print(f"{FAIL} --phase-b-report 指定的文件不存在: {report_path}", file=sys.stderr)
            sys.exit(2)
        try:
            if _read_text_bom_safe is not None:
                phase_b_report_text = _read_text_bom_safe(str(report_path))
            else:
                phase_b_report_text = report_path.read_text(encoding="utf-8-sig")
        except Exception as e:
            print(f"{FAIL} --phase-b-report 读取失败: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        content = run_check(phase_a_obj, phase_b_obj, args.threshold, phase_b_report_text, contract_path)
    except ValueError as e:
        print(f"{FAIL} {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"{FAIL} 校验过程异常: {e}", file=sys.stderr)
        record_degradation(
            stage="stage7", component="precommit_consistency_check",
            reason="check_exception", level="L-记录",
            fallback_used="abort", impact="Phase A/B 一致性校验未完成",
            input_path=str(phase_a_path),
        )
        sys.exit(2)

    overall = derive_overall(schema_a, schema_b, content)

    result = {
        "chapter_id": content["chapter_id"],
        "schema_phase_a": schema_a,
        "schema_phase_b": schema_b,
        "dimension_completeness": content["dimension_completeness"],
        "a5_consistency": content["a5_consistency"],
        "verdict_rule": content["verdict_rule"],
        "a1_script_output_proxy": content["a1_script_output_proxy"],
        "a4_single_verdict_line": content["a4_single_verdict_line"],
        "overall_pass": overall["overall_pass"],
        "failure_stage": overall["failure_stage"],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
