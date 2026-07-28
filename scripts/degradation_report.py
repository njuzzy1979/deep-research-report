#!/usr/bin/env python3
"""降级事件台账汇总与交付阻断检查（跨模型兼容性优化方案 §三 B5，CP6 交付门禁）。

职责边界（与 ``degradation_log.py`` 的分工）：
    ``degradation_log.py`` 负责"写"——各消费者（outline_reader / merge_drafts /
    outline_title_extract 等）在遇到降级路径时调用 ``record_degradation()``
    追加一条事件记录。
    本脚本负责"读 + 汇总 + 阻断"——在 CP6（阶段 9 前的最终检查点）读取整份
    台账，把"三级延迟阻断"设计中悬而未决的 L-显著事件逐条摆出来，未确认
    (acknowledged) 的一律阻断交付；L-记录事件不阻断，仅汇总展示供人工核对。

路径解析（**关键回归防线**）：本脚本**直接 import** ``degradation_log.py``
的 ``_resolve_log_path()``，不重新实现路径解析逻辑。第 2 批 D2 教训——
写台账与读台账若各自实现一遍"显式参数 > 环境变量 DRR_DEGRADATION_LOG >
默认路径 <项目根>/research/.degradation-log.jsonl"的优先级链，两处实现
一旦出现细微差异（例如默认路径锚定基准不同），CP6 就会读到空台账、
延迟阻断机制静默失效而不自知。直接复用同一函数从根本上消除这一风险。

确认（acknowledge）落盘设计（**关键设计决策，务必读完**）：
    没有采用"原地改写台账中对应事件那一行的 acknowledged 字段"的方案，而是
    ``--acknowledge <event_id>`` 触发时**追加**一条独立的 acknowledgement
    记录（``{"record_type": "acknowledgement", "event_id": ..., "ts": ...}``），
    读取时按 event_id 归并计算每个事件的最终确认状态
    （``final_acknowledged = 原始记录.acknowledged OR 该 event_id 出现过
    acknowledgement 记录``）。

    选择这个方案而不是原地改写，原因：
    1. 台账的 append-only 语义是 ``degradation_log.py`` 明确的设计承诺
       （模块 docstring："为 CP6 交付门禁在阻断前逐条核对"提供的是一份
       只增不改的审计轨迹）。原地改写会破坏这个承诺——一旦允许"读+改写
       同一行"，台账就不再能充当"事件发生时的原始快照"，且并发写入
       （理论上多个阶段/多个人同时在跑）下原地改写天然有覆盖丢失风险，
       而 append 天然无冲突。
    2. 保留了"谁在什么时候确认了什么"的完整轨迹（多条 acknowledgement
       记录 = 多次确认动作的历史），原地改写会抹掉这段历史，只留下最终
       态。对于一份用于交付门禁审计的台账，保留过程比只留结果更重要。
    3. 与 ``record_degradation()`` 自身的写入方式保持同构（同样是
       "构造 dict → 序列化一行 JSON → 以 'a' 模式追加"），不需要额外的
       "定位到某一行 → 原地替换 → 整体重写文件"这套更复杂、更易出 bug
       的逻辑。

用法：
    python scripts/degradation_report.py [--log <path>] [--json]
    python scripts/degradation_report.py --acknowledge <event_id>

退出码：
    0 = 不存在未确认的 L-显著事件（可交付，含台账文件不存在的情况——
        视为"无降级事件"，不是错误）
    1 = 存在至少一条未确认的 L-显著事件（阻断交付）
    2 = 读取错误（台账文件存在但读取失败，如权限被拒绝/路径实际是目录）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py:42-48 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 路径解析：直接复用 degradation_log.py 的实现，不复制逻辑（见模块 docstring）。
from degradation_log import LEVEL_RECORD, LEVEL_SIGNIFICANT, _resolve_log_path

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

# acknowledgement 记录与原始降级事件记录共用一份 JSONL 文件，靠这个字段区分
# 两种行类型——原始事件记录（degradation_log.record_degradation 写入）没有
# 这个字段，故取不到时按 False 处理，天然不会误判。
_ACK_RECORD_TYPE = "acknowledgement"


def _append_acknowledgement(path: Path, event_id: str) -> dict:
    """追加一条确认记录（append-only，见模块 docstring 的设计决策说明）。

    只接受单个 event_id——CLI 层面不提供 ``--acknowledge-all``，调用方
    每次只能确认一条，这是方案"强制逐条列出 impact，不支持批量确认"的
    落地方式之一（另一半落地在 ``format_text_report()`` 的逐条展开逻辑）。
    """
    record = {
        "record_type": _ACK_RECORD_TYPE,
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _read_raw_lines(path: Path) -> list[dict]:
    """逐行读取 JSONL，解析失败的行静默跳过（容错，同 degradation_log._existing_event_ids）。"""
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                records.append(obj)
    return records


def summarize(path: Path) -> dict:
    """读取台账并汇总为 CP6 检查所需的结构化结果。

    台账文件不存在时返回"无降级事件"的空汇总（不抛异常）——由调用方
    ``main()`` 的 exit code 语义体现"这不是错误，是 0 = 可交付"。
    """
    if not path.exists():
        return {
            "log_path": str(path),
            "log_exists": False,
            "total_events": 0,
            "significant_events": [],
            "significant_unacknowledged": [],
            "record_events": [],
            "other_events": [],
            "blocking": False,
        }

    raw_records = _read_raw_lines(path)

    events: dict[str, dict] = {}  # event_id -> 原始事件记录（后写覆盖先写，理论上幂等不会重复）
    acknowledged_ids: set[str] = set()

    for obj in raw_records:
        if obj.get("record_type") == _ACK_RECORD_TYPE:
            eid = obj.get("event_id")
            if eid:
                acknowledged_ids.add(eid)
        else:
            eid = obj.get("event_id")
            if eid:
                events[eid] = obj

    significant_events: list[dict] = []
    significant_unacknowledged: list[dict] = []
    record_events: list[dict] = []
    other_events: list[dict] = []

    for eid, ev in events.items():
        final_acknowledged = bool(ev.get("acknowledged", False)) or (eid in acknowledged_ids)
        entry = {**ev, "final_acknowledged": final_acknowledged}
        level = ev.get("level")
        if level == LEVEL_SIGNIFICANT:
            significant_events.append(entry)
            if not final_acknowledged:
                significant_unacknowledged.append(entry)
        elif level == LEVEL_RECORD:
            record_events.append(entry)
        else:
            other_events.append(entry)

    return {
        "log_path": str(path),
        "log_exists": True,
        "total_events": len(events),
        "significant_events": significant_events,
        "significant_unacknowledged": significant_unacknowledged,
        "record_events": record_events,
        "other_events": other_events,
        "blocking": len(significant_unacknowledged) > 0,
    }


def format_text_report(summary: dict, just_acknowledged: Optional[str] = None) -> str:
    """人读报告：未确认 L-显著事件必须逐条展开 impact 全文（不允许只给计数）。"""
    lines = [f"=== 降级事件台账汇总（CP6 交付门禁）：{summary['log_path']} ===", ""]

    if just_acknowledged:
        lines.append(f"{OK} 已确认事件: {just_acknowledged}（已追加 acknowledgement 记录）")
        lines.append("")

    if not summary["log_exists"]:
        lines.append(f"{OK} 台账文件不存在，视为无降级事件，可交付")
        return "\n".join(lines)

    lines.append(f"总事件数: {summary['total_events']}")
    lines.append(
        f"  L-显著: {len(summary['significant_events'])} 条"
        f"（未确认: {len(summary['significant_unacknowledged'])} 条）"
    )
    lines.append(f"  L-记录: {len(summary['record_events'])} 条（仅汇总展示，不阻断）")
    if summary["other_events"]:
        lines.append(f"  其他级别: {len(summary['other_events'])} 条（未识别的 level 值，供人工核对）")
    lines.append("")

    if summary["significant_unacknowledged"]:
        lines.append(f"{FAIL} 以下 L-显著事件尚未确认，阻断交付——逐条列出 impact，需逐一 --acknowledge：")
        for ev in summary["significant_unacknowledged"]:
            lines.append(f"  - event_id: {ev.get('event_id')}")
            lines.append(f"    stage={ev.get('stage')} component={ev.get('component')} reason={ev.get('reason')}")
            lines.append(f"    fallback_used: {ev.get('fallback_used', '')}")
            lines.append(f"    impact: {ev.get('impact', '')}")
            lines.append(f"    ts: {ev.get('ts', '')}")
            lines.append("")
    else:
        lines.append(f"{OK} 无未确认的 L-显著事件")
        lines.append("")

    # 已确认的 L-显著事件：不阻断，但仍展示供审计追溯
    acknowledged_significant = [
        ev for ev in summary["significant_events"] if ev["final_acknowledged"]
    ]
    if acknowledged_significant:
        lines.append(f"{OK} 已确认的 L-显著事件（不阻断，供审计追溯）：")
        for ev in acknowledged_significant:
            lines.append(f"  - event_id: {ev.get('event_id')}  impact: {ev.get('impact', '')}")
        lines.append("")

    if summary["record_events"]:
        lines.append(f"{OK} L-记录事件（仅记录，不阻断）：")
        for ev in summary["record_events"]:
            lines.append(
                f"  - event_id: {ev.get('event_id')}  "
                f"component={ev.get('component')} reason={ev.get('reason')}  "
                f"impact: {ev.get('impact', '')}"
            )
        lines.append("")

    if summary["blocking"]:
        lines.append("=== 总判定: FAIL（存在未确认 L-显著事件，阻断交付） ===")
    else:
        lines.append("=== 总判定: PASS（可交付） ===")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="降级事件台账汇总与交付阻断检查（CP6 交付门禁，B5）"
    )
    parser.add_argument(
        "--log", default=None, help="显式指定台账文件路径（覆盖环境变量与默认路径）"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 delivery_checklist_check.py 等聚合脚本消费）")
    parser.add_argument(
        "--acknowledge",
        default=None,
        metavar="EVENT_ID",
        help="确认单个降级事件（追加一条 acknowledgement 记录）；不支持批量确认，"
        "每次只能传一个 event_id",
    )
    args = parser.parse_args()

    path = _resolve_log_path(args.log)

    if args.acknowledge:
        try:
            _append_acknowledgement(path, args.acknowledge)
        except Exception as e:
            print(f"{FAIL} 确认记录写入失败: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        summary = summarize(path)
    except Exception as e:
        print(f"{FAIL} 台账读取失败: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(summary, just_acknowledged=args.acknowledge))

    sys.exit(1 if summary["blocking"] else 0)


if __name__ == "__main__":
    main()
