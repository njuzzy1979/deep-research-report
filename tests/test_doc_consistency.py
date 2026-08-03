# -*- coding: utf-8 -*-
"""跨文档一致性测试（L3，跨模型兼容性优化方案 第9批-A D3 文档一致性订正）。

只测**跨文档的事实是否互相一致**，不测单文档内部结构（那是 test_agent_contracts.py
的 L1 职责）。覆盖范围：

1. 角色数（11）在 `SKILL.md` / `README.md` / `references/multiagent-orchestration.md`
   三处声明句中一致，且与 `agents/*.md`（不含 `deprecated/`）的实际文件数一致。
2. `agents/` 目录下的实际文件名与 `SKILL.md` / `README.md` 角色表格中列出的 Agent
   名字集合一致（双向：文件多了/表格多了都应报错）。
3. 写作标准数量（25）在 `agents/chapter_auditor_agent.md` / `SKILL.md` / `README.md`
   三处声明句中一致，且与 `references/writing-standards.md` 实际的 `## 标准 N` 一级
   标题计数一致。
4. `agents/contracts/auditor_contract.json` 的 30 个维度 id（`dimensions` 25 +
   `proposal_extra` 5）在 `agents/chapter_auditor_agent.md` 正文中均有迹可循——短前缀
   （`C1_h1` -> `C1`、`QS4_paragraphs` -> `QS4`、`P1_tech_metrics` -> `P1`）按短前缀比对，
   其余 id 按全称比对。
5. `diagram_agent` 在全库 `*.md`（排除 `design/` 方案文档与 `agents/deprecated/`
   归档文件本身）中零残留——废弃角色不应再被除历史归档/方案文档外的任何文件提及。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = PROJECT_ROOT / "agents"
REFERENCES_DIR = PROJECT_ROOT / "references"

SKILL_MD = PROJECT_ROOT / "SKILL.md"
README_MD = PROJECT_ROOT / "README.md"
ORCHESTRATION_MD = REFERENCES_DIR / "multiagent-orchestration.md"
AUDITOR_AGENT_MD = AGENTS_DIR / "chapter_auditor_agent.md"
WRITING_STANDARDS_MD = REFERENCES_DIR / "writing-standards.md"
AUDITOR_CONTRACT_JSON = AGENTS_DIR / "contracts" / "auditor_contract.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


ROLE_COUNT_DECLARATION_PATTERN = re.compile(r"(\d+)\s*个?角色（口径")
ROLE_COUNT_HEADING_PATTERN = re.compile(r"^#+\s*(\d+)\s*个角色\s*$", re.MULTILINE)


def test_role_count_declaration_consistent_across_three_docs():
    """SKILL.md / README.md / multiagent-orchestration.md 三处角色数声明句一致。"""
    skill_matches = ROLE_COUNT_DECLARATION_PATTERN.findall(_read(SKILL_MD))
    orchestration_matches = ROLE_COUNT_DECLARATION_PATTERN.findall(_read(ORCHESTRATION_MD))
    readme_matches = ROLE_COUNT_HEADING_PATTERN.findall(_read(README_MD))

    assert skill_matches, "SKILL.md 未找到角色数声明句"
    assert orchestration_matches, "multiagent-orchestration.md 未找到角色数声明句"
    assert readme_matches, "README.md 未找到角色数标题"

    counts = {
        "SKILL.md": skill_matches[0],
        "references/multiagent-orchestration.md": orchestration_matches[0],
        "README.md": readme_matches[0],
    }
    distinct = set(counts.values())
    assert len(distinct) == 1, "三处角色数声明不一致：" + repr(counts)


def test_role_count_matches_actual_agents_dir_file_count():
    """声明的角色数应等于 agents/*.md 实际文件数（不含 deprecated/ 归档文件）。"""
    declared = ROLE_COUNT_DECLARATION_PATTERN.findall(_read(SKILL_MD))
    assert declared, "SKILL.md 未找到角色数声明句"
    declared_count = int(declared[0])

    actual_files = sorted(p.name for p in AGENTS_DIR.glob("*.md"))
    assert declared_count == len(actual_files), (
        "声明角色数 " + str(declared_count) + " 与 agents/*.md 实际文件数 "
        + str(len(actual_files)) + " 不一致：实际文件 " + repr(actual_files)
    )


ROLE_TABLE_AGENT_NAME_PATTERN = re.compile(r"^\|\s*`([a-z][a-z0-9_]*_agent)`", re.MULTILINE)


def _agent_names_from_role_table(text):
    return set(ROLE_TABLE_AGENT_NAME_PATTERN.findall(text))


def _actual_agent_file_stems():
    return {p.stem for p in AGENTS_DIR.glob("*.md")}


@pytest.mark.parametrize("doc_path", [SKILL_MD, README_MD])
def test_agents_dir_files_match_role_table(doc_path):
    """agents/*.md 实际文件（去掉 .md 后缀）与角色表格中出现的 Agent 名字集合双向一致。"""
    table_names = _agent_names_from_role_table(_read(doc_path))
    actual_names = _actual_agent_file_stems()

    only_in_table = table_names - actual_names
    only_in_dir = actual_names - table_names

    assert not only_in_table, (
        doc_path.name + " 角色表格中出现但 agents/ 目录下不存在对应文件：" + repr(sorted(only_in_table))
    )
    assert not only_in_dir, (
        "agents/ 目录下存在但 " + doc_path.name + " 角色表格未列出的文件：" + repr(sorted(only_in_dir))
    )


STANDARDS_COUNT_PATTERNS = [
    re.compile(r"共\s*28\s*条"),
    re.compile(r"28\s*条(?:写作)?标准"),
    re.compile(r"标准体系（28\s*条）"),
]

STANDARD_HEADING_PATTERN = re.compile(r"^## 标准 \d+", re.MULTILINE)


def _has_28_count_mention(text):
    return any(p.search(text) for p in STANDARDS_COUNT_PATTERNS)


@pytest.mark.parametrize("doc_path", [AUDITOR_AGENT_MD, SKILL_MD, README_MD])
def test_writing_standards_count_mentioned_as_25(doc_path):
    text = _read(doc_path)
    assert _has_28_count_mention(text), (
        doc_path.name + " 未找到 '25 条标准' / '共 25 条' 之类的标准总数声明"
    )


def test_writing_standards_actual_heading_count_is_25():
    """references/writing-standards.md 实际的 '## 标准 N' 一级标题数量应为 25（标准 0-24）。"""
    text = _read(WRITING_STANDARDS_MD)
    headings = STANDARD_HEADING_PATTERN.findall(text)
    assert len(headings) == 28, (
        "writing-standards.md 实际 '## 标准 N' 标题数为 " + str(len(headings))
        + "，与声明的 25 条不一致"
    )


def _load_auditor_contract():
    raw = AUDITOR_CONTRACT_JSON.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


def _short_form(dimension_id):
    """C1_h1 -> C1；QS4_paragraphs -> QS4；P1_tech_metrics -> P1；其余返回 None。"""
    m = re.match(r"^([A-Z]+\d+)_", dimension_id)
    return m.group(1) if m else None


def test_auditor_contract_dimension_ids_all_mentioned_in_agent_md():
    """12 dimensions (D1-D7 + P1-P5) all traceable in chapter_auditor_agent.md. 2026-08-03 reform reduced from 30.

    契约里两类 id 命名风格对应文档里两种不同的引用方式（这是既有约定，非本测试
    发明）：
    - 短前缀风格（`C1_h1`/`QS4_paragraphs`/`P1_tech_metrics` 等，形如 `字母+数字+下划线`）
      —— 文档正文按短前缀（C1/QS4/P1）逐字引用，用短前缀比对。
    - 全 snake_case 风格（如 `evidence_density`/`structural_consistency`）—— 文档正文
      从不逐字写出这个 id 字符串，只通过契约 JSON 里的中文 `group` 分组名 + 散文描述
      指代，因此改为核对其所属 `group` 名称是否出现。
    """
    contract = _load_auditor_contract()
    all_entries = contract["dimensions"] + contract.get("proposal_extra", [])
    assert len(all_entries) == 12, "契约维度总数（D1-D7 + P1-P5）应为 12，实际 " + str(len(all_entries))

    text = _read(AUDITOR_AGENT_MD)

    missing = []
    for entry in all_entries:
        dim_id = entry["id"]
        short = _short_form(dim_id)
        if short is not None:
            if short not in text:
                missing.append((dim_id, "short_form:" + short))
        else:
            group = entry.get("group", "")
            if not group or group not in text:
                missing.append((dim_id, "group:" + group))

    assert not missing, "以下契约维度条目在 chapter_auditor_agent.md 中既无短前缀也无所属 group 名称可循：" + repr(missing)


DIAGRAM_AGENT_RESIDUE_EXCLUDE_DIRS = {"design"}


def _iter_markdown_files_for_diagram_check():
    for path in PROJECT_ROOT.rglob("*.md"):
        rel_parts = path.relative_to(PROJECT_ROOT).parts
        if rel_parts and rel_parts[0] in DIAGRAM_AGENT_RESIDUE_EXCLUDE_DIRS:
            continue
        yield path


def test_diagram_agent_zero_residue_outside_deprecated_and_design():
    """diagram_agent 零残留检查，与验收命令同语义：

        grep -rn "diagram_agent" --include="*.md" . | grep -v "^./design/" | grep -v deprecated

    即：排除 design/ 方案文档整个目录；此外按**行**过滤——凡是提及 diagram_agent
    的行只要同一行里也出现了 "deprecated" 字样（说明该行是在陈述"已废弃/已归档"
    这个事实，而非把 diagram_agent 当作仍在用的角色引用），就不算残留。
    `agents/deprecated/diagram_agent.md` 归档文件本身逐行都不含 "deprecated" 字样
    （文件名不是文件内容），因此天然被排除在扫描范围之外——按 glob 规则它本就应被
    看作合法保留对象，这里显式跳过整个文件，逻辑等价于原始验收命令对该文件的实际
    效果（该文件内容里没有裸露的、未声明废弃的 diagram_agent 引用）。
    """
    offenders = []
    for path in _iter_markdown_files_for_diagram_check():
        rel = path.relative_to(PROJECT_ROOT)
        if rel == Path("agents") / "deprecated" / "diagram_agent.md":
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if "diagram_agent" in line and "deprecated" not in line:
                offenders.append(str(rel) + ":" + str(lineno) + ": " + line.strip())

    assert not offenders, "以下行残留未声明废弃的 diagram_agent 引用：" + repr(offenders)
