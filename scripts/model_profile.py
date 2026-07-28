#!/usr/bin/env python3
"""model-profile.json 能力档加载器（跨模型兼容性优化方案 §C1，审查层 Critical-1 修复的代码载体）。

职责：加载 skill 根目录的 ``model-profile.json``，实现方案 §C1 明确要求的
四情形兜底（区分"未配置"与"配置坏了"，二者风险性质不同，不应同等处理）：

    1. 文件不存在（用户误删/旧版仓库）        -> fallback 到 tier A（=当前 Claude 行为），写台账
    2. 文件存在但 JSON 解析失败                -> 降 tier C，写台账
    3. 文件存在但 schema 校验失败              -> 降 tier C，写台账
    4. 文件存在且合法                          -> 按声明的 tier 运行

原设计"文件缺失 -> tier C"会导致现有 Claude 用户不创建该文件就被静默降级
（完整档禁用、红线砍至 5 条、Phase A 退化为确认式），直接推翻本方案"Claude
路径字节级不变"的核心保证。本模块是该修复的必要代码载体——兜底规则若只停留
在文档，运行时无从体现。

同时提供：
    - ``derive_phase_a_mode``：phase_a_mode 由 ``limits.max_output_tokens``
      派生（方案 §C4），是派生量，不作为配置字段出现在 schema / profile 中。
    - ``resolve_collaboration_mode``：C2"模型能力档 × 报告规模档"二维决策
      矩阵的硬规则实现——``Tier C × 完整多 Agent`` 强制降级为"分层多 Agent"，
      ``host.agent_delegation=false`` 强制降级为"单 Agent 极速"。模式命名与
      ``SKILL.md`` §三档协同模式 / ``references/multiagent-orchestration.md``
      §7 保持一致。

schema 校验复用 ``scripts/schema_validate.py`` 的 ``load_schema`` /
``validate_instance``，不重复实现校验逻辑。解析失败/缺失时写台账复用
``scripts/degradation_log.py`` 的 ``record_degradation``（容错导入，沿用
``scripts/output_envelope_check.py`` 同款模式）。

用法：
    python scripts/model_profile.py [--path <model-profile.json>] [--json]

退出码：0 = 正常加载（含合法声明的 tier A/B/C）；
       1 = 因解析/校验失败被迫降级到 tier C（``_source == fallback_tier_c_invalid``）；
       2 = 读取过程出现意外错误。
"""
from __future__ import annotations

import argparse
import json
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
# 避免可观测性依赖影响主流程（沿用 output_envelope_check.py:61-65 同款模式）。
try:
    from degradation_log import record_degradation
except ImportError:
    def record_degradation(**kwargs):  # type: ignore[no-redef]
        pass

# schema 校验复用 schema_validate.py，不重复实现校验逻辑。
try:
    import schema_validate as sv
except ImportError:
    sv = None  # 极端情况下不可用时，load_profile 会跳过 schema 校验并容错降级

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_PATH = _PROJECT_ROOT / "model-profile.json"

# phase_a_mode 派生阈值（方案 §C4：max_output_tokens < 16000 -> confirm，否则 free）
PHASE_A_MODE_THRESHOLD = 16000

# 兜底默认值（内存态，不依赖磁盘文件；与 model-profile.json / *.example.json 的
# 字段结构保持一致，均可通过 schemas/model-profile.schema.json 校验）
TIER_A_DEFAULT = {
    "capability_tier": "A",
    "host": {"agent_delegation": True},
    "limits": {"max_output_tokens": 64000},
    "policy": {"hard_rule_budget": 0, "envelope_nonce": False, "template_fill_mode": "off"},
}

TIER_C_DEFAULT = {
    "capability_tier": "C",
    "host": {"agent_delegation": True},
    "limits": {"max_output_tokens": 8000},
    "policy": {"hard_rule_budget": 5, "envelope_nonce": True, "template_fill_mode": "on"},
}

# C2 二维决策矩阵：模式命名取自 SKILL.md §三档协同模式 /
# references/multiagent-orchestration.md §7，代码里的模式名必须与文档一致。
MODE_FULL = "完整多 Agent"
MODE_LAYERED = "分层多 Agent"
MODE_SOLO = "单 Agent 极速"
VALID_MODES = {MODE_FULL, MODE_LAYERED, MODE_SOLO}


def derive_phase_a_mode(max_output_tokens: int) -> str:
    """phase_a_mode 由 max_output_tokens 派生（方案 §C4），非配置字段。

    ``phase_a_mode = "confirm" if max_output_tokens < 16000 else "free"``
    """
    return "confirm" if max_output_tokens < PHASE_A_MODE_THRESHOLD else "free"


def _normalize(raw: dict, source: str) -> dict:
    """归一化为返回形态：深拷贝 + 附加 _source 与派生的 phase_a_mode。"""
    normalized = json.loads(json.dumps(raw))  # 深拷贝，避免调用方修改内置默认字典
    normalized["_source"] = source
    normalized["phase_a_mode"] = derive_phase_a_mode(normalized["limits"]["max_output_tokens"])
    return normalized


def load_profile(path: Optional[str] = None) -> dict:
    """加载 model-profile.json，实现四情形兜底（方案 §C1）。

    Args:
        path: 显式指定的 model-profile.json 路径；不传则用 skill 根目录默认路径。

    Returns:
        归一化后的 profile dict，含 capability_tier / host / limits / policy /
        phase_a_mode（派生）/ _source（"file" | "fallback_tier_a_missing" |
        "fallback_tier_c_invalid"）。
    """
    target = Path(path) if path else DEFAULT_PROFILE_PATH

    # 用户级本地覆盖：model-profile.local.json（不提交到仓库，供个人按需配置）
    # 仓库默认值永远是 tier A（Claude 安全基线），本地覆盖文件由 .gitignore 排除。
    # --path 显式传参时不走覆盖逻辑（调用方已明确指定文件，尊重其选择）。
    local_override = target.parent / "model-profile.local.json"
    if path is None and local_override.exists():
        target = local_override

    # 情形 1：文件不存在 -> fallback 到 tier A（=当前 Claude 行为），写台账
    if not target.exists():
        record_degradation(
            stage="init",
            component="model_profile",
            reason="profile_file_missing",
            level="L-记录",
            fallback_used="fallback_tier_a",
            impact="未找到 model-profile.json，已按 tier A 运行（=当前 Claude 行为，Claude 路径不受影响）",
            input_path=str(target),
        )
        return _normalize(TIER_A_DEFAULT, "fallback_tier_a_missing")

    # 情形 2：JSON 解析失败 -> 降 tier C，写台账
    try:
        raw_bytes = target.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            raw_bytes = raw_bytes[3:]
        instance = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        record_degradation(
            stage="init",
            component="model_profile",
            reason="profile_json_parse_failed",
            level="L-显著",
            fallback_used="fallback_tier_c",
            impact=f"model-profile.json 解析失败（{e}），配置意图不明，已降级为 tier C",
            input_path=str(target),
        )
        return _normalize(TIER_C_DEFAULT, "fallback_tier_c_invalid")

    # 情形 3：schema 校验失败 -> 降 tier C，写台账（复用 schema_validate.py，不重复实现校验逻辑）
    if sv is not None:
        try:
            schema = sv.load_schema("model-profile")
            result = sv.validate_instance(instance, schema)
        except Exception as e:
            record_degradation(
                stage="init",
                component="model_profile",
                reason="schema_validator_unavailable",
                level="L-显著",
                fallback_used="fallback_tier_c",
                impact=f"schema 校验器不可用（{e}），配置意图不明，已降级为 tier C",
                input_path=str(target),
            )
            return _normalize(TIER_C_DEFAULT, "fallback_tier_c_invalid")

        if not result["valid"]:
            record_degradation(
                stage="init",
                component="model_profile",
                reason="profile_schema_invalid",
                level="L-显著",
                fallback_used="fallback_tier_c",
                impact=f"model-profile.json 未通过 schema 校验（{result['error_count']} 处错误），配置意图不明，已降级为 tier C",
                input_path=str(target),
            )
            return _normalize(TIER_C_DEFAULT, "fallback_tier_c_invalid")

    # 情形 4：文件存在且合法 -> 按声明的 tier 运行
    _src = "file_local_override" if local_override.exists() and target == local_override else "file"
    return _normalize(instance, _src)


def resolve_collaboration_mode(profile: dict, requested_mode: str) -> tuple:
    """C2 二维决策矩阵的硬规则实现，返回 (实际生效模式, 降级原因|None)。

    模式命名与 ``SKILL.md`` §三档协同模式 / ``references/multiagent-orchestration.md``
    §7 保持一致："完整多 Agent" / "分层多 Agent" / "单 Agent 极速"。

    硬规则（方案 §C2）:
      - ``host.agent_delegation=false``：无 depth-1 底座，强制降级为单 Agent 极速档。
      - ``Tier C × 完整多 Agent``：不允许（完整档成本放大 3-5 倍 + 未知模型高失败
        风险叠加），自动降级为分层多 Agent，并写台账。
      - 其余组合：正交，不互相覆盖，按请求档位原样生效。

    Args:
        profile: ``load_profile()`` 返回的归一化 profile dict。
        requested_mode: 调用方原本打算使用的协同档位，取值须为 ``VALID_MODES`` 之一。

    Returns:
        (实际生效模式, 降级原因字符串或 None)。
    """
    if requested_mode not in VALID_MODES:
        raise ValueError(f"未知协同模式: {requested_mode!r}，应为 {VALID_MODES} 之一")

    # 硬规则 1：无 depth-1 底座 -> 强制单 Agent 极速档
    if not profile.get("host", {}).get("agent_delegation", True):
        reason = "host.agent_delegation=false，无 depth-1 底座，强制降级为单 Agent 极速档"
        if requested_mode != MODE_SOLO:
            record_degradation(
                stage="collaboration_mode",
                component="model_profile",
                reason="agent_delegation_disabled",
                level="L-显著",
                fallback_used=MODE_SOLO,
                impact=f"请求档位「{requested_mode}」被强制降级为「{MODE_SOLO}」：{reason}",
            )
            return MODE_SOLO, reason
        return MODE_SOLO, None

    # 硬规则 2：Tier C × 完整多 Agent 不允许 -> 自动降级为分层多 Agent
    if profile.get("capability_tier") == "C" and requested_mode == MODE_FULL:
        reason = (
            "Tier C（未知能力档）不允许「完整多 Agent」档，"
            "自动降级为「分层多 Agent」（完整档成本放大 3-5 倍 + 未知模型高失败风险）"
        )
        record_degradation(
            stage="collaboration_mode",
            component="model_profile",
            reason="tier_c_full_mode_forbidden",
            level="L-显著",
            fallback_used=MODE_LAYERED,
            impact=reason,
        )
        return MODE_LAYERED, reason

    # 正交：其余组合不降级，按请求档位原样生效
    return requested_mode, None


def format_text_report(profile: dict) -> str:
    lines = [
        "=== model-profile 生效配置 ===",
        f"来源(_source): {profile['_source']}",
        f"capability_tier: {profile['capability_tier']}",
        f"host.agent_delegation: {profile['host']['agent_delegation']}",
        f"limits.max_output_tokens: {profile['limits']['max_output_tokens']}",
        f"policy.hard_rule_budget: {profile['policy']['hard_rule_budget']}",
        f"policy.envelope_nonce: {profile['policy']['envelope_nonce']}",
        f"policy.template_fill_mode: {profile['policy']['template_fill_mode']}",
        f"phase_a_mode（派生，非配置字段）: {profile['phase_a_mode']}",
        "",
    ]
    if profile["_source"] == "fallback_tier_a_missing":
        lines.append(f"{WARN} 未找到 model-profile.json，已按 tier A 兜底运行（Claude 路径不受影响）")
    elif profile["_source"] == "fallback_tier_c_invalid":
        lines.append(f"{WARN} model-profile.json 存在但解析/校验失败，已降级为 tier C")
    else:
        lines.append(f"{OK} 已按声明的 model-profile.json 加载")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="model-profile.json 能力档加载器")
    parser.add_argument("--path", default=None, help="显式指定 model-profile.json 路径（默认 skill 根目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 orchestrator 解析）")
    args = parser.parse_args()

    try:
        profile = load_profile(args.path)
    except Exception as e:
        print(f"{FAIL} model-profile 加载出现意外错误: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(profile))

    # 仅"因解析/校验失败被迫降级"才算 exit 1；用户显式声明的合法 tier C 不算异常。
    sys.exit(1 if profile["_source"] == "fallback_tier_c_invalid" else 0)


if __name__ == "__main__":
    main()
