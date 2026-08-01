# -*- coding: utf-8 -*-
"""agents/*.md 的静态契约测试（跨模型兼容性优化方案 §C3 Prompt 红线分级 + §D4 可移植性声明）。

只测**结构完整性**，不测语义——对标既有 L1 静态契约测试的定位：
- 红线节存在，且红线条数 <= front matter 声明的 hard_rules_count
- front matter 的 model / portability 字段合法
- 红线编号连续无缺号（R1..Rn / A1..An）
- "规则锚点摘要"引用的 `{skill路径}/...` 文件路径在仓库中真实存在

红线节相关测试（存在性/条数上限/编号连续）仅覆盖 `chapter_writer_agent.md`
（R 前缀）与 `chapter_auditor_agent.md`（A 前缀）——这两个文件是 §C3 本批改造
的对象，也是目前唯一声明了 `hard_rules_count` front matter 字段的文件。后续若
有更多 agent 补充该字段，可把文件名加入 ``RED_LINE_AGENT_FILES`` 参数化列表。

`portability` 字段合法性检查（§D4）覆盖 `agents/` 目录下**全部** Agent 定义文件
（``ALL_AGENT_FILES``，不含已废弃的 `agents/deprecated/diagram_agent.md`，也不含
`finalizer_agent.md`——后者由并行任务负责 portability 标注，尚未落地，此处显式
跳过而非误判为失败）。

本文件末尾另含跨模型兼容性优化方案 §C4（Phase A/B 输出规模应对）的补充测试：
- L1 静态检查加强：全库 grep ``stdout``，断言无"贴完整 stdout"残留表述
- `auditor_contract.json` 的 29 个维度条目 hint 字段全覆盖
- `batch_grouping` 覆盖全部维度 id，无重复无遗漏
- `derive_phase_a_mode` 被复用（定义仅存在于 `model_profile.py`），非重新实现
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = PROJECT_ROOT / "agents"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

VALID_PORTABILITY = {"core", "claude-enhanced", "claude-only"}

# 本批 §C3 改造的两个文件及其红线编号前缀——仅这两个文件声明了
# hard_rules_count / 红线（RED LINES）小节，红线相关测试只对它们做参数化。
RED_LINE_AGENT_FILES = [
    ("chapter_writer_agent.md", "R"),
    ("chapter_auditor_agent.md", "A"),
]

# §D4：agents/ 目录下需要检查 portability 字段的全部文件。
# finalizer_agent.md 由并行任务负责标注 portability，本批未触碰，显式排除
# （而非漏检——若该任务完成后仍未补齐，应把文件名加回此列表）。
_FINALIZER_PENDING = {"finalizer_agent.md"}


def _discover_all_agent_files() -> list[str]:
    names = sorted(
        p.name for p in AGENTS_DIR.glob("*.md")
        if p.name not in _FINALIZER_PENDING
    )
    return names


ALL_AGENT_FILES = _discover_all_agent_files()


def _parse_front_matter(text: str) -> dict:
    """解析 Markdown 文件开头的 YAML front matter（``---`` 包裹的首块）。"""
    m = re.match(r"^---\s*\n(.*?\n)---\s*\n", text, flags=re.DOTALL)
    assert m is not None, "front matter 未找到（文件必须以 --- ... --- 开头）"
    return yaml.safe_load(m.group(1))


def _read_agent(filename: str) -> tuple[dict, str]:
    path = AGENTS_DIR / filename
    text = path.read_text(encoding="utf-8")
    return _parse_front_matter(text), text


def _extract_red_line_section(text: str) -> str:
    """截取"红线（RED LINES）"一级 `##` 小节的完整正文（到下一个 `##` 为止）。"""
    m = re.search(
        r"^## 🔴 红线（RED LINES）.*?\n(.*?)(?=^## )",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert m is not None, "未找到红线（RED LINES）小节"
    return m.group(1)


def _extract_red_line_numbers(section_text: str, prefix: str) -> list[str]:
    """从红线小节的表格中提取形如 `**R1**` / `**A1**` 的编号列表（按表格行序）。"""
    return re.findall(rf"\*\*({prefix}\d+)\*\*", section_text)


# ---------------------------------------------------------------------------
# front matter 字段合法性
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,_prefix", RED_LINE_AGENT_FILES)
def test_front_matter_has_required_fields(filename, _prefix):
    fm, _ = _read_agent(filename)

    assert "name" in fm and fm["name"], f"{filename} 缺少 name 字段"
    assert "model" in fm and fm["model"], f"{filename} 缺少 model 字段"
    assert "portability" in fm, f"{filename} 缺少 portability 字段"
    assert "hard_rules_count" in fm, f"{filename} 缺少 hard_rules_count 字段"


@pytest.mark.parametrize("filename", ALL_AGENT_FILES)
def test_portability_field_is_valid_enum(filename):
    """§D4：agents/ 下全部文件（finalizer_agent.md 除外，见上方说明）
    都必须声明合法的 portability 字段。"""
    fm, _ = _read_agent(filename)
    assert "portability" in fm, f"{filename} 缺少 portability 字段"
    assert fm["portability"] in VALID_PORTABILITY, (
        f"{filename} 的 portability={fm['portability']!r} 不在合法枚举 "
        f"{VALID_PORTABILITY} 中"
    )


@pytest.mark.parametrize("filename,_prefix", RED_LINE_AGENT_FILES)
def test_hard_rules_count_is_positive_int(filename, _prefix):
    fm, _ = _read_agent(filename)
    assert isinstance(fm["hard_rules_count"], int) and fm["hard_rules_count"] > 0


# ---------------------------------------------------------------------------
# 红线节存在性 + 条数上限
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,prefix", RED_LINE_AGENT_FILES)
def test_red_line_section_exists(filename, prefix):
    _, text = _read_agent(filename)
    section = _extract_red_line_section(text)
    assert section.strip(), f"{filename} 的红线小节为空"


@pytest.mark.parametrize("filename,prefix", RED_LINE_AGENT_FILES)
def test_red_line_count_within_budget(filename, prefix):
    fm, text = _read_agent(filename)
    section = _extract_red_line_section(text)
    numbers = _extract_red_line_numbers(section, prefix)

    assert len(numbers) > 0, f"{filename} 红线小节未解析出任何编号（前缀 {prefix}）"
    assert len(numbers) <= fm["hard_rules_count"], (
        f"{filename} 红线条数 {len(numbers)} 超过 front matter 声明的 "
        f"hard_rules_count={fm['hard_rules_count']}"
    )


# ---------------------------------------------------------------------------
# 红线编号连续无缺号
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,prefix", RED_LINE_AGENT_FILES)
def test_red_line_numbering_is_contiguous(filename, prefix):
    _, text = _read_agent(filename)
    section = _extract_red_line_section(text)
    numbers = _extract_red_line_numbers(section, prefix)

    indices = [int(n[len(prefix):]) for n in numbers]
    expected = list(range(1, len(indices) + 1))
    assert indices == expected, (
        f"{filename} 红线编号不连续或有缺号：实际 {numbers}，期望 "
        f"{[f'{prefix}{i}' for i in expected]}"
    )


# ---------------------------------------------------------------------------
# 规则锚点摘要引用的文件路径真实存在
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,_prefix", RED_LINE_AGENT_FILES)
def test_anchor_summary_referenced_paths_exist(filename, _prefix):
    _, text = _read_agent(filename)

    # 形如 `{skill路径}/references/xxx.md` 或 `{skill路径}/research/xxx.md`
    refs = re.findall(r"\{skill路径\}/([\w\-./%一-鿿]+\.\w+)", text)
    assert refs, f"{filename} 未找到任何 {{skill路径}}/... 锚点引用"

    # research/glossary.md 是阶段 5 运行时产出文件，仓库中不预置，单独豁免
    runtime_produced = {"research/glossary.md"}

    missing = []
    for rel in refs:
        if rel in runtime_produced:
            continue
        candidate = PROJECT_ROOT / rel
        if not candidate.exists():
            missing.append(rel)

    assert not missing, f"{filename} 锚点摘要引用的文件不存在：{missing}"


# ===========================================================================
# 跨模型兼容性优化方案 §C4：Phase A/B 输出规模应对——补充测试
# ===========================================================================

AUDITOR_CONTRACT_PATH = PROJECT_ROOT / "agents" / "contracts" / "auditor_contract.json"

# 全库 grep 时排除的目录：design/（方案文档本身，允许提及旧措辞做对照）、
# tests/（测试代码里含"stdout"关键字属正常断言用词，非文档残留）。
STDOUT_GREP_EXCLUDE_DIRS = {"design", "tests", ".git"}

# 判定为"要求粘贴完整 stdout"残留表述的模式——命中即视为方案 §C4 手段 3
# 未落地（全量 stdout 应由 orchestrator 落盘，报告正文只贴 JSON 摘要 + 路径）。
# 注意：现有正确措辞里大量出现"非贴完整原始输出"/"不贴全量原始输出"这类**否定句**
# （明确禁止旧行为），必须用负向前瞻排除"非/不/无/未"等否定词，否则会把方案
# 本身要求的正确新措辞误判为残留。
STALE_STDOUT_PATTERNS = [
    re.compile(r"(?<![非不无未])粘贴.{0,6}完整.{0,10}stdout", re.IGNORECASE),
    re.compile(r"(?<![非不无未])完整.{0,10}stdout.{0,6}粘贴", re.IGNORECASE),
    re.compile(r"(?<![非不无未])把输出贴进"),
    re.compile(r"(?<![非不无未])贴完整.{0,4}stdout", re.IGNORECASE),
    re.compile(r"(?<![非不无未])贴.{0,4}原始输出"),
    re.compile(r"(?<![非不无未])贴.{0,4}原始.{0,4}stdout", re.IGNORECASE),
]


def _iter_markdown_files():
    for path in PROJECT_ROOT.rglob("*.md"):
        rel_parts = path.relative_to(PROJECT_ROOT).parts
        if rel_parts and rel_parts[0] in STDOUT_GREP_EXCLUDE_DIRS:
            continue
        yield path


def test_no_stale_stdout_paste_instruction_in_docs():
    """L1 加强：全库（排除 design/tests）grep stdout 相关表述，确认无

    "要求粘贴完整 stdout" 的残留措辞——方案 §C4 手段 3 要求全量 stdout 由
    orchestrator 落盘，Agent 报告正文只贴 JSON 摘要 + 落盘路径引用。
    """
    offenders = []
    for path in _iter_markdown_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "stdout" not in text.lower():
            continue
        for pattern in STALE_STDOUT_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {pattern.pattern}")

    assert not offenders, f"发现残留的'贴完整 stdout'表述：{offenders}"


def _load_auditor_contract() -> dict:
    raw = AUDITOR_CONTRACT_PATH.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


def test_auditor_contract_dimension_count_unchanged():
    """dimensions=25、proposal_extra=5，共 30——2026-08-02 新增 negative_evidence_check 维度。"""
    contract = _load_auditor_contract()
    assert len(contract["dimensions"]) == 25
    assert len(contract.get("proposal_extra", [])) == 5


def test_auditor_contract_all_dimensions_have_three_hints():
    """核心交付断言：全部 30 个维度条目都具备 3 个 hint 字段。"""
    contract = _load_auditor_contract()
    required_hints = {
        "what_to_look_for_hint",
        "what_triggers_warn_hint",
        "what_triggers_block_hint",
    }
    all_entries = contract["dimensions"] + contract.get("proposal_extra", [])
    assert len(all_entries) == 30

    missing = []
    for entry in all_entries:
        gap = required_hints - set(entry.keys())
        if gap:
            missing.append((entry.get("id", "<无id>"), sorted(gap)))

    assert not missing, f"以下维度缺少 hint 字段：{missing}"


def test_auditor_contract_batch_grouping_covers_all_ids_without_overlap():
    """batch_grouping 覆盖全部 29 个维度 id，无重复无遗漏（按严重度分 3 批）。"""
    contract = _load_auditor_contract()
    all_ids = {d["id"] for d in contract["dimensions"]}
    all_ids |= {d["id"] for d in contract.get("proposal_extra", [])}

    batch_grouping = contract.get("batch_grouping", {})
    batch1 = batch_grouping.get("batch1_high", [])
    batch2 = batch_grouping.get("batch2_mid", [])
    batch3 = batch_grouping.get("batch3_low", [])

    combined = batch1 + batch2 + batch3
    assert len(combined) == len(set(combined)), "batch_grouping 存在重复的维度 id"

    combined_set = set(combined)
    assert combined_set == all_ids, (
        f"batch_grouping 覆盖不完整：缺失 {sorted(all_ids - combined_set)}，"
        f"多余 {sorted(combined_set - all_ids)}"
    )


def test_derive_phase_a_mode_defined_only_in_model_profile():
    """确认 derive_phase_a_mode 只在 scripts/model_profile.py 定义一处，

    其余脚本（如 phase_a_to_json.py）通过 import 复用，不重新实现同名函数。
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))

    definition_sites = []
    for path in SCRIPTS_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^def derive_phase_a_mode\(", text, flags=re.MULTILINE):
            definition_sites.append(path.name)

    assert definition_sites == ["model_profile.py"], (
        f"derive_phase_a_mode 应仅在 model_profile.py 定义一处，实际定义于：{definition_sites}"
    )

    import model_profile as mp
    import phase_a_to_json as p

    assert p.__name__ != "model_profile"
    # phase_a_to_json.py 不重新实现该函数，只在需要时通过 model_profile 复用
    assert not hasattr(p, "derive_phase_a_mode")
    assert mp.derive_phase_a_mode(8000) == "confirm"
    assert mp.derive_phase_a_mode(64000) == "free"
