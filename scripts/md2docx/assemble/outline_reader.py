"""outline.md YAML 结构清单读取模块（Phase 7a —— 结构注入）。

从 outline.md 的 YAML front matter 中解析机器可读的结构清单，将其展平为
(标题文本, HeadingKind, 编号) 三元组列表，供 ``assemble/headings.py`` 的
``apply_structure_overlay()`` 消费。

结构清单格式定义见 ``references/stage-4-outline.md`` §4.1.x。
"""
from __future__ import annotations

import re
import yaml

from ..ir import HeadingKind, HeadingNumber

# ---------------------------------------------------------------------------
# YAML front matter 提取
# ---------------------------------------------------------------------------

_RE_YAML_BOUNDARY = re.compile(r"^---\s*$")


def extract_yaml_front_matter(text: str) -> tuple[dict | None, str]:
    """从 Markdown 文本中提取 YAML front matter。

    Args:
        text: 原始 Markdown 文本。

    Returns:
        (parsed_dict | None, body_text)：
        - 若文本以 ``---`` 开头且之后有另一个 ``---``，返回 (解析结果, 正文部分)
        - 若解析失败或不存在 YAML front matter，返回 (None, 原文本)
    """
    if not text.startswith("---"):
        return None, text

    lines = text.split("\n")
    if len(lines) < 3:
        return None, text

    end_idx = None
    for i in range(1, len(lines)):
        if _RE_YAML_BOUNDARY.match(lines[i]):
            end_idx = i
            break

    if end_idx is None:
        return None, text

    yaml_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        import sys
        print(
            f"[FATAL] outline.md YAML 解析失败: {e}",
            file=sys.stderr,
        )
        if hasattr(e, 'problem_mark') and e.problem_mark is not None:
            line_no = e.problem_mark.line + 2
            print(
                f"  问题大约在第 {line_no} 行: {e.problem}",
                file=sys.stderr,
            )
        return None, body

    if not isinstance(parsed, dict):
        return None, body

    return parsed, body


# ---------------------------------------------------------------------------
# 结构展平
# ---------------------------------------------------------------------------


def _build_structure_lookup(structure: dict) -> dict[str, tuple[HeadingKind, HeadingNumber]]:
    """将 YAML structure 节点展平为 {标题文本: (HeadingKind, 编号)} 查找表。

    对 bodymatter 中的每个章/节/小节、frontmatter 中的每个 H2/H3、
    appendix 中的每个附录标题，生成一条映射。

    Args:
        structure: YAML 解析后的 ``structure`` 节点，格式见 stage-4-outline.md §4.1.x。

    Returns:
        标题文本 → (HeadingKind, number | None) 字典。
        例如: {"军事需求与现状分析": (HeadingKind.CHAPTER, 1),
               "非合作目标异动意图判断": (HeadingKind.SECTION, (1, 1)),
               "异动识别在导弹预警中的应用": (HeadingKind.SUBSECTION, (1, 1, 1)),
               "异动识别在导弹预警中的应用": (HeadingKind.SUBSECTION, (1, 1, 1))}
    """
    lookup: dict[str, tuple[HeadingKind, HeadingNumber]] = {}
    if not isinstance(structure, dict):
        return lookup

    # ── frontmatter ──
    front_items: list[dict] = structure.get("frontmatter", [])
    if isinstance(front_items, list):
        for item in front_items:
            if not isinstance(item, dict):
                continue
            title = item.get("chapter_title", "")
            if title:
                lookup[title.strip()] = (HeadingKind.FRONT_MATTER, None)
            for sec_title in item.get("sections", []):
                if isinstance(sec_title, str) and sec_title.strip():
                    lookup[sec_title.strip()] = (HeadingKind.FRONT_MATTER, None)

    # ── bodymatter ──
    body_items: list[dict] = structure.get("bodymatter", [])
    if isinstance(body_items, list):
        for ch in body_items:
            if not isinstance(ch, dict):
                continue
            ch_no = ch.get("chapter_no", 0)
            ch_title = ch.get("chapter_title", "")
            if ch_title and isinstance(ch_no, int) and ch_no > 0:
                lookup[ch_title.strip()] = (HeadingKind.CHAPTER, ch_no)

            sections: list[str] = ch.get("sections", [])
            for i, sec_title in enumerate(sections, start=1):
                if isinstance(sec_title, str) and sec_title.strip():
                    lookup[sec_title.strip()] = (
                        HeadingKind.SECTION,
                        (ch_no, i),
                    )

            subsections: list[dict] = ch.get("subsections", [])
            if isinstance(subsections, list):
                for sub in subsections:
                    if not isinstance(sub, dict):
                        continue
                    parent_title = sub.get("parent", "")
                    sub_title = sub.get("title", "")
                    if (
                        parent_title
                        and sub_title
                        and parent_title.strip() in lookup
                    ):
                        # 查找该 parent 在 sections 中的序号
                        parent_idx = None
                        for si, s in enumerate(sections):
                            if isinstance(s, str) and s.strip() == parent_title.strip():
                                parent_idx = si + 1
                                break
                        if parent_idx is not None:
                            lookup[sub_title.strip()] = (
                                HeadingKind.SUBSECTION,
                                (ch_no, parent_idx, 1),
                            )

    # ── appendix ──
    app_items: list[dict] = structure.get("appendix", [])
    if isinstance(app_items, list):
        for app in app_items:
            if not isinstance(app, dict):
                continue
            letter = app.get("appendix_letter", "")
            title = app.get("appendix_title", "")
            if letter and title:
                lookup[title.strip()] = (HeadingKind.APPENDIX, letter.upper())

    return lookup


def build_structure_manifest(structure: dict) -> dict:
    """构建结构清单的摘要信息（供 Issue 记录和调试）。

    Args:
        structure: YAML 解析后的 ``structure`` 节点。

    Returns:
        {"frontmatter_count": N, "chapter_count": N, "section_count": N,
         "subsection_count": N, "appendix_count": N}
    """
    manifest: dict[str, int] = {
        "frontmatter_count": 0,
        "chapter_count": 0,
        "section_count": 0,
        "subsection_count": 0,
        "appendix_count": 0,
    }
    if not isinstance(structure, dict):
        return manifest

    front: list = structure.get("frontmatter", [])
    if isinstance(front, list):
        for item in front:
            if isinstance(item, dict):
                manifest["frontmatter_count"] += len(
                    item.get("sections", [])
                )

    body: list = structure.get("bodymatter", [])
    if isinstance(body, list):
        for ch in body:
            if isinstance(ch, dict):
                manifest["chapter_count"] += 1
                manifest["section_count"] += len(ch.get("sections", []))
                manifest["subsection_count"] += len(ch.get("subsections", []))

    app: list = structure.get("appendix", [])
    if isinstance(app, list):
        manifest["appendix_count"] = len(app)

    return manifest
