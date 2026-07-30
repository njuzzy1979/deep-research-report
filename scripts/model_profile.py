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

    sync: 新增 `auto_configure()` + `MODEL_CONFIG_MAP`（方案甲：模型名 → 档位自动配置）——
    Orchestrator 初始化时传入模型名，自动生成 `model-profile.local.json`，
    用户零干预。未知模型降级为 tier C 保守安全网。

用法：
    python scripts/model_profile.py [--path <model-profile.json>] [--json]
    python scripts/model_profile.py --model "<模型标识符>"  # 自动配置 → 写入 model-profile.local.json

退出码：0 = 正常加载（含合法声明的 tier A/B/C）；
       1 = 因解析/校验失败被迫降级到 tier C（``_source == fallback_tier_c_invalid``）；
       2 = 读取过程出现意外错误。
"""
from __future__ import annotations

import argparse
import json
import os
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

# ---------------------------------------------------------------------------
# 模型名 → 配置映射表（方案甲："--model 自动检测"的数据源）
#
# 正则按列表顺序匹配（re.search，忽略大小写），首次命中即停。
# 未命中任何规则 → tier C（最保守安全网，写台账）。
# 新增厂商/模型只需在此表追加一行，不改代码逻辑。
# ---------------------------------------------------------------------------
_MODEL_RULES: list[tuple[str, str, dict]] = [
    # --- Claude 系列（全部归 tier A）---
    (r"claude", "claude-series", {
        "capability_tier": "A",
        "host": {"agent_delegation": True},
        "limits": {"max_output_tokens": 64000},
        "policy": {"hard_rule_budget": 0, "envelope_nonce": False, "template_fill_mode": "off"},
    }),

    # --- DeepSeek V4 系列（380K 输出 → phase_a_mode=free）---
    # 实测证据：2026-07-29 drawio MCP 四层通过 + 280 passed 全量回归
    (r"deepseek.?v4", "deepseek-v4-series", {
        "capability_tier": "B",
        "host": {"agent_delegation": True},
        "limits": {"max_output_tokens": 380000},
        "policy": {"hard_rule_budget": 5, "envelope_nonce": True, "template_fill_mode": "on"},
    }),

    # --- DeepSeek V3 / 其他 DeepSeek（8K 输出 → phase_a_mode=confirm）---
    (r"deepseek", "deepseek-generic", {
        "capability_tier": "B",
        "host": {"agent_delegation": True},
        "limits": {"max_output_tokens": 8000},
        "policy": {"hard_rule_budget": 5, "envelope_nonce": True, "template_fill_mode": "on"},
    }),

    # --- GLM-4 系列 ---
    (r"glm[ -]?4", "glm-4-series", {
        "capability_tier": "B",
        "host": {"agent_delegation": True},
        "limits": {"max_output_tokens": 8000},
        "policy": {"hard_rule_budget": 5, "envelope_nonce": True, "template_fill_mode": "on"},
    }),

    # --- Qwen3 系列 ---
    (r"qwen[ -]?3", "qwen3-series", {
        "capability_tier": "B",
        "host": {"agent_delegation": True},
        "limits": {"max_output_tokens": 8000},
        "policy": {"hard_rule_budget": 5, "envelope_nonce": True, "template_fill_mode": "on"},
    }),
]

# 未知模型的兜底配置（映射表未命中时使用）
_UNKNOWN_MODEL_FALLBACK = {
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


def auto_configure(model_name: str) -> dict:
    """根据模型标识符匹配对应的能力档配置（方案甲核心）。

    匹配规则：
        - 在 ``_MODEL_RULES`` 中按顺序做 ``re.search(pattern, model_name, re.I)``，
          首次命中即停，返回 ``(配置字典, 匹配规则名, tier)``。
        - 未命中 → 返回 ``_UNKNOWN_MODEL_FALLBACK``，tier C，写台账。

    Args:
        model_name: 模型标识符（如 ``"deepseek-v4-pro-guan-cc"``、
            ``"claude-sonnet-5"``、``"glm-4.6"``）。

    Returns:
        dict，含 ``config``（待落盘的 profile 字典）、``matched_rule``（规则名）、
        ``tier``（最终档位）、``is_unknown``（是否未知模型兜底）。
    """
    for pattern, rule_name, config in _MODEL_RULES:
        if re.search(pattern, model_name, re.IGNORECASE):
            return {
                "config": config,
                "matched_rule": rule_name,
                "tier": config["capability_tier"],
                "is_unknown": False,
            }

    record_degradation(
        stage="init",
        component="model_profile",
        reason="unknown_model_fallback_tier_c",
        level="L-记录",
        fallback_used="tier_c_unknown_model",
        impact=f"模型 '{model_name}' 不在已知映射表中，已降级为 tier C（最保守安全网）。"
               f"如需升级，请在 ``_MODEL_RULES`` 中追加该模型的规则，或手动创建 "
               f"model-profile.local.json",
        input_path="(内存匹配，非磁盘文件)",
    )
    return {
        "config": _UNKNOWN_MODEL_FALLBACK,
        "matched_rule": "unknown-fallback",
        "tier": "C",
        "is_unknown": True,
    }


def _write_local_override(config: dict, target_dir: Optional[Path] = None) -> Path:
    """将配置写入 ``model-profile.local.json``（带 schema 校验）。

    Args:
        config: 待写入的 profile 字典（不含 _source / phase_a_mode 等运行时字段）。
        target_dir: 目标目录，默认 skill 根目录。

    Returns:
        实际写入的文件路径。

    Raises:
        ValueError: 生成的配置未通过 schema 校验（不应发生——映射表内的配置经人工审核）。
    """
    out_dir = target_dir or _PROJECT_ROOT
    out_path = out_dir / "model-profile.local.json"

    # 写入前做 schema 校验（防御性：映射表内配置若出错，在这里拦下而不写脏文件）
    if sv is not None:
        schema = sv.load_schema("model-profile")
        result = sv.validate_instance(config, schema)
        if not result["valid"]:
            raise ValueError(
                f"auto_configure 生成的配置未通过 schema 校验（此为代码 bug，"
                f"请检查 ``_MODEL_RULES`` 映射表）: {result['errors']}"
            )

    out_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def format_text_report(profile: dict) -> str:
    """把生效的 profile 渲染为人类可读的多行文本报告（无 --json 时的默认输出）。"""
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
    parser = argparse.ArgumentParser(
        description="model-profile.json 能力档加载器 / 自动配置器",
        epilog=(
            "示例:\n"
            "  python scripts/model_profile.py                         # 加载生效配置\n"
            '  python scripts/model_profile.py --model "deepseek-v4-pro-guan-cc"  # 自动配置\n'
            "  python scripts/model_profile.py --model auto              # 从环境变量探测"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", default=None, help="显式指定 model-profile.json 路径（默认 skill 根目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 orchestrator 解析）")
    parser.add_argument(
        "--model", default=None,
        help=(
            "模型标识符（如 'deepseek-v4-pro-guan-cc'、'claude-sonnet-5'），"
            "匹配 _MODEL_RULES 映射表后自动写入 model-profile.local.json。"
            "传 'auto' 则从 CLAUDE_CODE_MODEL / LLM_MODEL 环境变量自动探测。"
            "已存在 model-profile.local.json 时跳过（不覆盖已有配置）。"
        ),
    )
    args = parser.parse_args()

    # --model 模式：自动配置 → 写入 → 退出
    if args.model is not None:
        model_name = args.model.strip()
        if model_name.lower() == "auto":
            model_name = _detect_model_from_env()
            if model_name is None:
                print(
                    f"{FAIL} --model auto 未能从环境变量探测到模型名"
                    f"（尝试了 CLAUDE_CODE_MODEL / LLM_MODEL），"
                    f"请显式传入 --model \"<模型标识符>\"",
                    file=sys.stderr,
                )
                sys.exit(2)

        out_path = _PROJECT_ROOT / "model-profile.local.json"
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8-sig"))
            print(f"model-profile.local.json 已存在（当前 tier={existing.get('capability_tier','?')}），"
                  f"跳过自动配置。如需重新生成，请先删除该文件。")
            sys.exit(0)

        result = auto_configure(model_name)
        config = result["config"]

        try:
            written = _write_local_override(config)
        except ValueError as e:
            print(f"{FAIL} {e}", file=sys.stderr)
            sys.exit(2)

        tier = config["capability_tier"]
        rule = result["matched_rule"]
        phase_a = derive_phase_a_mode(config["limits"]["max_output_tokens"])
        tokens = config["limits"]["max_output_tokens"]

        lines = [
            f"{OK} 模型 '{model_name}' → 规则 '{rule}' → tier {tier}",
            f"    max_output_tokens: {tokens}  →  phase_a_mode: {phase_a}",
            f"    nonce={config['policy']['envelope_nonce']}  "
            f"红线预算={config['policy']['hard_rule_budget']}  "
            f"模板填空={config['policy']['template_fill_mode']}",
            f"",
            f"    已写入: {written}",
        ]
        if result["is_unknown"]:
            lines.append(
                f"    {WARN} 该模型不在已知映射表中，已按 tier C 最保守安全网运行。"
            )
        print("\n".join(lines))
        sys.exit(0)

    # 常规模式：加载并展示生效配置
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


def _detect_model_from_env() -> Optional[str]:
    """从环境变量自动探测当前运行的模型标识符。

    探测顺序：
        1. ``CLAUDE_CODE_MODEL`` —— Claude Code / VSCode 扩展注入的当前模型名
        2. ``LLM_MODEL`` —— 通用回退变量
    """
    for var in ("CLAUDE_CODE_MODEL", "LLM_MODEL"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return None


if __name__ == "__main__":
    main()
