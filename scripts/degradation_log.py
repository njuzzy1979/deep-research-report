#!/usr/bin/env python3
"""降级事件台账模块（跨模型兼容性优化方案 §二 A2）。

职责：为"三级延迟阻断"设计提供统一的台账写入能力——当任一消费者
（outline_reader / merge_drafts / builder / figure_gate 等）遇到降级
路径（YAML 解析失败、结构清单丢弃字段、图表清单降级……）时，调用
``record_degradation()`` 写一条 append-only JSONL 记录，供 CP6 交付门禁
在阻断前逐条核对。

设计要点：
- 台账路径默认 ``<项目根>/research/.degradation-log.jsonl``（锚定到**项目根**，
  不随运行时工作目录漂移——见 G1 交叉验证 D2 裁决），可用参数 ``log_path``
  或环境变量 ``DRR_DEGRADATION_LOG`` 覆盖，优先级：显式参数 > 环境变量 > 默认。
- 幂等性：``event_id = sha1(stage + component + reason + input_path)``，
  写入前扫描已有文件，同 event_id 不重复写（同一场景多次触发只留一条）。
- **必须容错**：本模块是可观测性设施，不是主流程的一部分——任何写入异常
  （目录不可写、磁盘满……）都不得抛出到调用方，只在 stderr 打一行警告。
  目录不存在时自动创建。

用法：
    from degradation_log import record_degradation
    record_degradation(
        stage="assemble", component="outline_reader",
        reason="subsections_parent_not_found", level="L-显著",
        fallback_used="skip_subsection", impact="小节结构清单条目丢失",
        input_path=str(outline_path),
    )

调试：
    python scripts/degradation_log.py --list [--log-path <path>]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py:42-48 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 台账相对路径默认值；环境变量 DRR_DEGRADATION_LOG 可覆盖
_DEFAULT_LOG_RELPATH = "research/.degradation-log.jsonl"

# G1 交叉验证 D2 裁决：兜底路径必须锚定到项目根，不能是裸相对路径。
# degradation_log.py 位于 <项目根>/scripts/ 下，.parent.parent 即项目根。
# 原因：不同调用方式的运行时 cwd 不一致（如 `cd scripts && python -m md2docx`
# 与 `python scripts/md2docx.py` 分别落在 scripts/research/ 与 <根>/research/），
# 若兜底仍是裸相对路径，台账文件会随 cwd 漂移到两个不同位置。而 degradation_report.py
# （CP6 汇总台账并据此阻断交付）固定从项目根下的 research/ 读取，两处不一致会导致
# CP6 读到空台账、延迟阻断机制静默失效。锚定到项目根后，无论调用方 cwd 是什么，
# 兜底路径都落在同一个文件上。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 合法的降级级别（供调用方参考，不强制校验以免拖慢主流程）
LEVEL_RECORD = "L-记录"
LEVEL_SIGNIFICANT = "L-显著"


def _resolve_log_path(log_path: str | None) -> Path:
    """确定台账文件的实际路径：显式参数 > 环境变量 > 默认路径（锚定项目根）。"""
    if log_path:
        return Path(log_path)
    env_path = os.environ.get("DRR_DEGRADATION_LOG")
    if env_path:
        return Path(env_path)
    return _PROJECT_ROOT / _DEFAULT_LOG_RELPATH


def _compute_event_id(
    stage: str, component: str, reason: str, input_path: str, instance_key: str = ""
) -> str:
    """事件幂等键：同一 (stage, component, reason, input_path, instance_key) 组合视为同一事件。

    ``instance_key`` 用于区分"同一 stage/component/reason/input_path 组合下的
    不同实例"（G1 交叉验证 D3 裁决）：例如同一份 outline 中两个不同的孤儿
    subsection，若不加区分会被折叠成同一 event_id，只留下 1 条台账记录，第二条
    的 impact 完全丢失——这与方案要求的"强制逐条列出 impact，不支持批量确认"
    直接冲突。默认空串，不传时行为与旧版本完全一致（向后兼容）。
    """
    raw = f"{stage}|{component}|{reason}|{input_path}|{instance_key}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _existing_event_ids(path: Path) -> set[str]:
    """读取台账中已有的 event_id 集合，用于幂等判断。文件不存在或损坏行均容错跳过。"""
    ids: set[str] = set()
    if not path.exists():
        return ids
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = obj.get("event_id")
                if eid:
                    ids.add(eid)
    except Exception:
        # 读取失败不应阻止写入尝试；返回空集合意味着最坏情况下重复写一条，
        # 优于因为读失败而放弃记录降级事件。
        return ids
    return ids


def record_degradation(
    *,
    stage: str,
    component: str,
    reason: str,
    level: str,
    fallback_used: str = "",
    impact: str = "",
    input_path: str = "",
    instance_key: str | None = None,
    log_path: str | None = None,
    acknowledged: bool = False,
) -> None:
    """记录一条降级事件到台账（JSONL，append-only，幂等）。

    本函数承诺**永不抛出异常**——任何底层 I/O 失败都被吞掉，仅向 stderr
    打印一行警告，因为台账是可观测性设施，绝不能让它把主流程搞崩。

    Args:
        stage: 所处阶段标识（如 "assemble"、"merge"、"figure_gate"）。
        component: 触发降级的组件名（如 "outline_reader"）。
        reason: 降级原因的机器可读短标识（如 "yaml_parse_failed"）。
        level: 降级级别，取值 "L-记录" 或 "L-显著"。
        fallback_used: 实际采用的降级路径描述（如 "heuristic_text_match"）。
        impact: 对下游的影响描述（人读文本）。
        input_path: 触发该事件的输入文件路径，参与 event_id 幂等计算。
        instance_key: 可选的实例标识，参与 event_id 幂等计算，用于区分同一
            (stage, component, reason, input_path) 组合下的不同实例（如同一
            outline 中两个不同的孤儿 subsection，各自传入其标题作为
            instance_key，避免被折叠成同一条台账记录）。不传时为空串，
            行为与旧版本完全一致。
        log_path: 显式指定台账文件路径，覆盖环境变量与默认值。
        acknowledged: 该事件是否已被用户在 CP6 门禁确认，默认 False。
    """
    try:
        path = _resolve_log_path(log_path)
        event_id = _compute_event_id(
            stage, component, reason, input_path, instance_key or ""
        )

        existing_ids = _existing_event_ids(path)
        if event_id in existing_ids:
            return  # 幂等：同一事件已记录过，不重复写

        record = {
            "event_id": event_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "component": component,
            "reason": reason,
            "level": level,
            "fallback_used": fallback_used,
            "impact": impact,
            "acknowledged": acknowledged,
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 —— 台账写入绝不能影响主流程
        print(f"[WARN] 降级台账写入失败（不影响主流程）: {e}", file=sys.stderr)


def _list_log(log_path: str | None) -> None:
    """CLI 调试用：打印当前台账内容。"""
    path = _resolve_log_path(log_path)
    if not path.exists():
        print(f"台账文件不存在: {path}")
        return
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            print(f"[{i}] {line}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="降级事件台账调试工具")
    parser.add_argument("--list", action="store_true", help="打印当前台账内容")
    parser.add_argument("--log-path", default=None, help="显式指定台账文件路径")
    args = parser.parse_args()

    if args.list:
        _list_log(args.log_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
