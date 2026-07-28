#!/usr/bin/env python3
"""输出信封完整性 + nonce 配对 + 噪声比率检测（三合一，跨模型兼容性优化方案 §三 B1）。

职责（方案 §B1，P0-6 + P0-7）：
  1. 标记成对出现且恰为 1 对（`[AGENT-OUTPUT-START] ... [AGENT-OUTPUT-END]`）
  2. 标记内 agent 名称与期望一致（防跨 Agent 输出粘连）
  3. nonce 匹配（提供 ``--nonce`` 时；方案 §C5 输出信封 nonce 迁移）
  4. 噪声比率（编码错误 / 进度条残留字符占比）

信封正则同时接受**带 nonce**与**不带 nonce**两种格式（方案 §C5：nonce 是后缀，
前缀 `[AGENT-OUTPUT-START` 不变，Claude tier A 可继续输出无 nonce 旧格式）：
    `[AGENT-OUTPUT-START] chapter_writer_agent`                 （旧格式）
    `[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent`        （新格式，nonce 后缀）

nonce 误匹配防护三重约束：
  - 格式限定 `[0-9a-f]{6,16}`（十六进制，6-16 位）
  - 必须行首（``re.MULTILINE`` + ``^`` 锚定，防止正文中出现的类似串被误当作标记）
  - 必须带 agent 名后缀（标记行必须形如 `[...] <agent名>`，孤立的 `[AGENT-OUTPUT-START:xxx]`
    若捕获不到 agent 名，视为可疑标记，agent 校验时判为不匹配）

噪声检测的关键实现约束（方案明确要求）：
  **不能**按"非 ASCII 占比"判定噪声——那会把正常中文正文 100% 误判为噪声。
  必须精确匹配两类确定性噪声标志：
    - Unicode 替换字符 U+FFFD（编码错误的确定性标志）
    - 进度条专用字符集 ▕ █ ▏▎▍▌▋▊▉（终端渲染残留）
  中文字符（CJK）不参与噪声计数，思路对标 ``contract_check.py:128-147`` 的
  ``count_cjk_chars``——本脚本额外统计 CJK 字数（``cjk_chars`` 字段）仅作为
  可观测性信息，用于人工核验"这份输出确实是正常中文正文，不是误判"。

nonce 降级处理（方案 §C5）：提供 ``--nonce`` 但信封内 nonce 缺失或不匹配时，
**不阻断**（分类为 A2 表格中的 "L-记录" 级——"nonce 未匹配、可选字段缺失"），
而是降级为"无 nonce 匹配"（仅按标记配对 + agent 名判定），并写降级台账
（弱模型没照抄 nonce 的情况需要被计数，而非静默通过）。

用法：
    python scripts/output_envelope_check.py <raw_output.txt> --agent <name> [--nonce <hex>] [--json]
    python scripts/output_envelope_check.py <raw_output.txt> --agent <name> --extract-to <path>

退出码：0 = 信封与噪声检查均通过；1 = 信封配对/agent 校验或噪声比率超阈值失败；
       2 = 文件读取错误。
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

# 降级台账（跨模型兼容性优化方案 §二 A2）：容错兜底为 no-op，
# 避免可观测性依赖影响主流程（沿用 figure_gate.py:43-49 同款模式）。
try:
    from degradation_log import record_degradation
except ImportError:
    def record_degradation(**kwargs):  # type: ignore[no-redef]
        pass

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

# 噪声比率阈值（方案 §D1："噪声>30%→重试"）
NOISE_RATIO_THRESHOLD = 0.30

# 信封标记正则：放宽形式同时接受带 nonce 与不带 nonce 两种格式
# （方案 §C5：为第 6 批 C5 的 nonce 化预留）。
# 三重约束：格式限定 [0-9a-f]{6,16} + 必须行首（MULTILINE + ^ 锚定）+ 必须带 agent 名后缀。
ENVELOPE_MARKER_PATTERN = re.compile(
    r"^\[AGENT-OUTPUT-(START|END)(?::([0-9a-f]{6,16}))?\][ \t]*(\S+)?[ \t]*$",
    re.MULTILINE,
)

# 噪声字符集
REPLACEMENT_CHAR = "�"  # Unicode 替换字符：编码错误的确定性标志
PROGRESS_BAR_CHARS = set("▕█▏▎▍▌▋▊▉")  # 进度条专用字符集（终端渲染残留）

# CJK 统一表意文字（供可观测性字段展示，证明噪声比率未误伤中文）
CJK_PATTERN = re.compile(r"[一-鿿]")


def read_text(path: str) -> str:
    """二进制安全读取，处理 BOM / CRLF（与 contract_check.py:112-120 同款模式）。"""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_markers(text: str) -> list:
    """解析文本中全部信封标记，返回按出现顺序排列的 dict 列表。"""
    markers = []
    for m in ENVELOPE_MARKER_PATTERN.finditer(text):
        markers.append({
            "type": m.group(1),      # "START" | "END"
            "nonce": m.group(2),     # 十六进制串或 None（旧格式）
            "agent": m.group(3),     # agent 名或 None（标记格式异常）
            "span_start": m.start(),
            "span_end": m.end(),
        })
    return markers


def count_cjk_chars(text: str) -> int:
    """统计中文字符数，思路对标 contract_check.py:128-147，供噪声比率可观测性核验。"""
    return len(CJK_PATTERN.findall(text))


def compute_noise_ratio(text: str) -> dict:
    """计算噪声比率：仅精确匹配 U+FFFD 替换字符与进度条字符集，不按非 ASCII 占比判定。"""
    total = len(text)
    if total == 0:
        return {
            "noise_ratio": 0.0, "total_chars": 0, "noise_chars": 0,
            "replacement_char_count": 0, "progress_bar_char_count": 0,
            "cjk_chars": 0,
        }
    replacement_count = text.count(REPLACEMENT_CHAR)
    progress_bar_count = sum(1 for ch in text if ch in PROGRESS_BAR_CHARS)
    noise_chars = replacement_count + progress_bar_count
    return {
        "noise_ratio": round(noise_chars / total, 4),
        "total_chars": total,
        "noise_chars": noise_chars,
        "replacement_char_count": replacement_count,
        "progress_bar_char_count": progress_bar_count,
        "cjk_chars": count_cjk_chars(text),
    }


def check_envelope(text: str, expected_agent: str, expected_nonce: Optional[str]) -> dict:
    """核心校验逻辑：信封配对 + agent 一致性 + nonce 匹配（含降级）。

    Returns:
        dict，含 pairing_ok / agent_matched / nonce_matched / envelope_ok /
        payload（提取出的有效载荷，配对失败时为 None）/ degrade_reason（触发降级台账的原因，无降级时为 None）。
    """
    markers = _parse_markers(text)
    starts = [m for m in markers if m["type"] == "START"]
    ends = [m for m in markers if m["type"] == "END"]

    # 检查项 1：标记成对出现且恰为 1 对
    pairing_ok = (
        len(starts) == 1 and len(ends) == 1
        and starts[0]["span_start"] < ends[0]["span_start"]
    )

    agent_matched = False
    nonce_matched: Optional[bool] = None
    payload: Optional[str] = None
    degrade_reason: Optional[str] = None

    if pairing_ok:
        s, e = starts[0], ends[0]

        # 检查项 2：标记内 agent 名称与期望一致（防跨 Agent 输出粘连）
        # START/END 双方 agent 名必须一致且非空，且等于期望值。
        pair_agent_consistent = (s["agent"] is not None and s["agent"] == e["agent"])
        agent_matched = pair_agent_consistent and s["agent"] == expected_agent

        # 提取有效载荷：START 标记行结束 ~ END 标记行开始之间的内容
        payload = text[s["span_end"]:e["span_start"]].strip("\n")

        # 检查项 3：nonce 匹配（仅当调用方提供 --nonce 时才检查）
        if expected_nonce is not None:
            nonce_pair_consistent = (s["nonce"] is not None and s["nonce"] == e["nonce"])
            if nonce_pair_consistent and s["nonce"].lower() == expected_nonce.lower():
                nonce_matched = True
            else:
                nonce_matched = False
                # 降级：nonce 未命中 → 降级为无 nonce 匹配（方案 §C5），
                # 弱模型没照抄 nonce 的情况需被计数，而非静默通过。
                degrade_reason = "nonce_missing" if s["nonce"] is None else "nonce_mismatch"
    else:
        # 配对失败时仍尝试给出诊断信息，但无法安全提取 payload
        payload = None

    envelope_ok = pairing_ok and agent_matched

    return {
        "pairing_ok": pairing_ok,
        "start_count": len(starts),
        "end_count": len(ends),
        "agent_matched": agent_matched,
        "nonce_matched": nonce_matched,
        "envelope_ok": envelope_ok,
        "payload": payload,
        "degrade_reason": degrade_reason,
        "start_agent": starts[0]["agent"] if starts else None,
        "end_agent": ends[0]["agent"] if ends else None,
    }


def run_check(
    text: str,
    expected_agent: str,
    expected_nonce: Optional[str] = None,
    input_path: str = "",
    extract_to: Optional[str] = None,
) -> dict:
    """执行完整检查（信封 + 噪声），返回结构化结果，函数级可复用（方案 §D5）。"""
    envelope_result = check_envelope(text, expected_agent, expected_nonce)

    # 噪声比率：优先在提取出的有效载荷上计算（这是实际会流转下游的内容）；
    # 配对失败无法提取时，退化为在整份原始文本上计算，便于诊断。
    noise_target = envelope_result["payload"] if envelope_result["payload"] is not None else text
    noise_info = compute_noise_ratio(noise_target)
    noise_pass = noise_info["noise_ratio"] <= NOISE_RATIO_THRESHOLD

    # nonce 未命中 → 写降级台账（L-记录级，仅记录不阻断）
    if envelope_result["degrade_reason"]:
        record_degradation(
            stage="envelope_check",
            component="output_envelope_check",
            reason=envelope_result["degrade_reason"],
            level="L-记录",
            fallback_used="no_nonce_match",
            impact="弱模型未按预期回填 nonce，已降级为无 nonce 匹配（仅按标记配对+agent名判定）",
            input_path=input_path,
        )

    payload_path = None
    if extract_to and envelope_result["payload"] is not None:
        out_path = Path(extract_to)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(envelope_result["payload"], encoding="utf-8")
        payload_path = str(out_path)

    overall_pass = envelope_result["envelope_ok"] and noise_pass

    return {
        "file": input_path,
        "expected_agent": expected_agent,
        "envelope_ok": envelope_result["envelope_ok"],
        "pairing_ok": envelope_result["pairing_ok"],
        "start_count": envelope_result["start_count"],
        "end_count": envelope_result["end_count"],
        "agent_matched": envelope_result["agent_matched"],
        "start_agent": envelope_result["start_agent"],
        "end_agent": envelope_result["end_agent"],
        "nonce_matched": envelope_result["nonce_matched"],
        "degrade_reason": envelope_result["degrade_reason"],
        "noise_ratio": noise_info["noise_ratio"],
        "noise_pass": noise_pass,
        "noise_detail": noise_info,
        "payload_path": payload_path,
        "overall_pass": overall_pass,
    }


def format_text_report(r: dict) -> str:
    def mark(p):
        return OK if p else FAIL

    lines = [
        f"=== 输出信封检查：{r['file']} （期望 agent：{r['expected_agent']}）===",
        "",
        f"{mark(r['pairing_ok'])} 标记配对: START={r['start_count']} / END={r['end_count']} (应各恰为 1)",
        f"{mark(r['agent_matched'])} agent 一致性: START={r['start_agent']} / END={r['end_agent']} (期望={r['expected_agent']})",
    ]
    if r["nonce_matched"] is None:
        lines.append(f"     nonce 校验: 未提供 --nonce，跳过")
    else:
        nonce_mark = OK if r["nonce_matched"] else WARN
        lines.append(f"{nonce_mark} nonce 校验: {'匹配' if r['nonce_matched'] else '不匹配（已降级为无 nonce 匹配，已写台账）'}")
    nd = r["noise_detail"]
    lines.append(
        f"{mark(r['noise_pass'])} 噪声比率: {r['noise_ratio']:.4f} "
        f"(替换字符 {nd['replacement_char_count']} / 进度条字符 {nd['progress_bar_char_count']} "
        f"/ 总字符 {nd['total_chars']} / 中文字符 {nd['cjk_chars']}, 阈值 {NOISE_RATIO_THRESHOLD})"
    )
    if r["payload_path"]:
        lines.append(f"     有效载荷已提取至: {r['payload_path']}")
    lines.append("")
    lines.append(f"=== 总判定: {'PASS' if r['overall_pass'] else 'FAIL'} ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="输出信封完整性 + nonce 配对 + 噪声比率检测（三合一）"
    )
    parser.add_argument("file", help="待检查的原始输出文本文件")
    parser.add_argument("--agent", required=True, help="期望的 agent 名称（防跨 Agent 输出粘连）")
    parser.add_argument("--nonce", default=None, help="期望的 nonce 十六进制串（可选，提供时才校验）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 orchestrator 解析）")
    parser.add_argument("--extract-to", default=None, help="将信封内有效载荷提取写入该路径")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"{FAIL} 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(2)

    try:
        text = read_text(args.file)
    except Exception as e:
        print(f"{FAIL} 文件读取失败: {e}", file=sys.stderr)
        sys.exit(2)

    result = run_check(
        text, args.agent, args.nonce,
        input_path=args.file, extract_to=args.extract_to,
    )

    if args.json:
        # JSON 输出契约字段：{envelope_ok, nonce_matched, noise_ratio, agent_matched, payload_path}
        # 另附加诊断字段供人工核验，不破坏契约字段集合。
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
