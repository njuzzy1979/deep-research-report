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

# 降级台账（跨模型兼容性优化方案 §二 A2）：outline_reader.py 位于
# scripts/md2docx/assemble/ 包内，degradation_log.py 位于 scripts/ 下。
# 转换器运行时 cwd 通常是 scripts/（md2docx 包可导入即说明 scripts/ 已在
# sys.path 上），此时可直接导入；万一不可导入（如被其他调用方式引入），
# 容错降级为 no-op，只丢失台账观测性，不影响转换主流程。
try:
    from degradation_log import record_degradation
except ImportError:
    def record_degradation(**kwargs):  # type: ignore[no-redef]
        pass

# ---------------------------------------------------------------------------
# YAML front matter 提取
# ---------------------------------------------------------------------------

_RE_YAML_BOUNDARY = re.compile(r"^---\s*$")


def extract_yaml_front_matter(
    text: str, outline_path: str | None = None
) -> tuple[dict | None, str]:
    """从 Markdown 文本中提取 YAML front matter。

    Args:
        text: 原始 Markdown 文本。
        outline_path: 真实的 outline.md 路径，透传给内部 record_degradation()
            调用的 input_path 参数（G1 交叉验证 D3 附带修复：本函数原先内部
            台账写死字面量 "outline.md"）。默认 None 时回退到旧字面量，保证
            不破坏既有调用方（如测试用例仅传 text）。

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
        record_degradation(
            stage="assemble",
            component="outline_reader",
            reason="yaml_parse_failed",
            level="L-显著",
            fallback_used="heuristic_text_match",
            impact="结构清单不可用，heading 分类/编号回退到推断模式",
            input_path=outline_path if outline_path is not None else "outline.md",
        )
        return None, body

    if not isinstance(parsed, dict):
        return None, body

    return parsed, body


# ---------------------------------------------------------------------------
# 键名归一化（D1-1）
# ---------------------------------------------------------------------------


def _coerce_chapter_no(raw) -> int:
    """把 '1' / '1.0' / 1 / '0.1' 等安全转为 int；不可解析返回 0（不抛异常）。

    历史缺陷背景：``finalize_pipeline.py`` 曾用 ``int(item.get("section_no", "?"))``
    做适配，对**已合规**的输入（含 chapter_no 而无 section_no）会 ``int("?")``
    抛 ValueError——即"修好上游反而崩溃"的反模式。本函数一律不抛异常。
    """
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).strip().split(".")[0])
    except (ValueError, AttributeError, TypeError):
        return 0


def normalize_outline_structure(
    structure: dict, outline_path: str | None = None
) -> dict:
    """将旧键名 outline 归一化为 schema 权威键名（非破坏性，返回新 dict）。

    ``schemas/outline-structure.schema.json`` 是权威契约：
    ``bodymatter`` 的 items required = ``['chapter_no', 'chapter_title']``，
    ``appendix`` 的 items required = ``['appendix_letter', 'appendix_title']``。
    真实产出端曾写成 ``section_no``/``section_title``，导致
    ``_build_structure_lookup()`` 按权威键名读取时全部落空（lookup size = 0），
    结构注入静默失效。本函数在**消费端入口**统一把旧键名补齐为权威键名。

    映射规则（**按层级映射，不做全局替换**——``sections[*].section_no`` 是
    合法的节编号，不能被误改）：

    ==================  ====================================================
    层级                 映射
    ==================  ====================================================
    ``bodymatter[*]``    ``section_no``→``chapter_no``、
                         ``section_title``→``chapter_title``
    ``appendix[*]``      ``section_no``→``appendix_letter``、
                         ``section_title``→``appendix_title``
    ``frontmatter[*]``   ``section_title``→``chapter_title``
    ==================  ====================================================

    **``subsections`` 刻意不映射为 ``sections``**（D1 §十第 4 条裁决）：
    schema 中二者内层键名不同（``sections`` 为 ``{section_no, section_title}``，
    ``subsections`` 为 ``{parent_section_no, subsection_no, subsection_title}``），
    且 ``_build_structure_lookup()``（本文件 sections 分支 vs subsections 分支）
    与 ``outline_title_extract.build_title_tree()`` 都把二者当作**独立层级**
    分别消费。若按原设计整体赋值 ``c["sections"] = c["subsections"]``，非空时
    会把 subsection 结构塞进 sections 位置，``section_title`` 取到 ``None``。

    "章无 sections 时如何找到该章草稿文件"属于**合并期**的兜底语义，不是
    结构归一化的职责，已下沉到 ``merge_drafts.assemble_merged()`` 处理——
    在此注入虚拟 section 会污染 lookup（虚拟 section 的标题与章标题相同，
    而 lookup 以标题文本为键，会把 CHAPTER 条目覆盖成 SECTION）。

    双向兼容：权威键优先，缺失才回落旧键；回落事实写降级台账，**不静默接受**。
    对已合规的 outline 是**恒等变换**（幂等）。

    Args:
        structure: YAML 解析后的 ``structure`` 节点。
        outline_path: 真实 outline.md 路径，透传给降级台账的 input_path。

    Returns:
        归一化后的**新** dict（不就地 mutate 入参——原实现的就地 mutate 使
        同一份 structure 被多个消费端反复改写，难以定位状态来源）。
    """
    if not isinstance(structure, dict):
        return structure

    _input_path = outline_path if outline_path is not None else "outline.md"
    legacy_hits: list[str] = []
    out = {k: v for k, v in structure.items()}

    body: list = []
    for ch in structure.get("bodymatter", []) or []:
        if not isinstance(ch, dict):
            continue
        c = dict(ch)
        if "chapter_no" not in c and "section_no" in c:
            c["chapter_no"] = _coerce_chapter_no(c.get("section_no"))
            legacy_hits.append("bodymatter.section_no->chapter_no")
        if "chapter_title" not in c and "section_title" in c:
            c["chapter_title"] = c.get("section_title") or ""
            legacy_hits.append("bodymatter.section_title->chapter_title")
        body.append(c)
    if "bodymatter" in structure or body:
        out["bodymatter"] = body

    apx: list = []
    for a in structure.get("appendix", []) or []:
        if not isinstance(a, dict):
            continue
        x = dict(a)
        if "appendix_letter" not in x and "section_no" in x:
            x["appendix_letter"] = str(x.get("section_no") or "").strip()
            legacy_hits.append("appendix.section_no->appendix_letter")
        if "appendix_title" not in x and "section_title" in x:
            x["appendix_title"] = x.get("section_title") or ""
            legacy_hits.append("appendix.section_title->appendix_title")
        apx.append(x)
    if "appendix" in structure or apx:
        out["appendix"] = apx

    front: list = []
    for f in structure.get("frontmatter", []) or []:
        if not isinstance(f, dict):
            continue
        y = dict(f)
        if "chapter_title" not in y and "section_title" in y:
            y["chapter_title"] = y.get("section_title") or ""
            legacy_hits.append("frontmatter.section_title->chapter_title")
        front.append(y)
    if "frontmatter" in structure or front:
        out["frontmatter"] = front

    if legacy_hits:
        record_degradation(
            stage="assemble",
            component="outline_reader",
            reason="outline_legacy_key_names_normalized",
            level="L-记录",
            fallback_used="normalize_outline_structure",
            impact=(
                "outline.md 使用了非权威键名，已在消费端归一化为 schema 权威键名"
                f"（命中: {sorted(set(legacy_hits))}）。建议产出端直接输出 "
                "chapter_no/chapter_title/appendix_letter/appendix_title"
            ),
            input_path=_input_path,
        )

    return out


# ---------------------------------------------------------------------------
# 结构展平
# ---------------------------------------------------------------------------


def _find_parent_section_idx(
    sections: list, parent_identifier: str, parent_is_title_text: bool
) -> int | None:
    """在本章 ``sections`` 列表中查找 parent 的 1-based 序号。

    支持两种 sections 形态（规范文档 stage-4-outline.md §4.1.x）：
    - dict 形态（规范）：``{section_no, section_title}``
    - str 形态（旧）：直接文本匹配

    以及两种 parent 标识语义：
    - 新格式（``parent_is_title_text=False``）：``parent_identifier`` 是编号
      （如 ``"1.1"``），优先用 ``section_no == parent_identifier`` 匹配；
      若命中的 section 的 ``section_no`` 为空字符串（frontmatter 场景下
      section_no 可能为空），或找不到编号匹配，回退用
      ``section_title == parent_identifier`` 做文本匹配（兼容旧语义）。
    - 旧格式（``parent_is_title_text=True``）：``parent_identifier`` 是标题
      文本，直接按文本匹配。

    Args:
        sections: 本章的 sections 列表（dict 或 str 元素混合）。
        parent_identifier: parent 的标识值（编号或标题文本，取决于
            ``parent_is_title_text``）。
        parent_is_title_text: True 表示 ``parent_identifier`` 语义为标题文本
            （旧字段名路径）；False 表示语义为编号（规范字段名路径）。

    Returns:
        parent 在 sections 中的 1-based 序号；未找到返回 None。
    """
    ident = parent_identifier.strip()
    if not ident:
        return None

    if parent_is_title_text:
        # 旧语义：直接按标题文本匹配（dict 形态取 section_title，str 形态直接比较）
        for si, s in enumerate(sections):
            if isinstance(s, dict):
                if str(s.get("section_title", "")).strip() == ident:
                    return si + 1
            elif isinstance(s, str):
                if s.strip() == ident:
                    return si + 1
        return None

    # 新语义：优先用 section_no 匹配；str 形态没有编号元数据，直接跳过编号匹配。
    for si, s in enumerate(sections):
        if isinstance(s, dict):
            section_no = str(s.get("section_no", "")).strip()
            if section_no and section_no == ident:
                return si + 1

    # 编号匹配未命中（或 section_no 为空）：回退用 section_title 做文本匹配
    for si, s in enumerate(sections):
        if isinstance(s, dict):
            if str(s.get("section_title", "")).strip() == ident:
                return si + 1
        elif isinstance(s, str):
            if s.strip() == ident:
                return si + 1

    return None


def _build_structure_lookup(
    structure: dict, outline_path: str | None = None
) -> dict[str, tuple[HeadingKind, HeadingNumber]]:
    """将 YAML structure 节点展平为 {标题文本: (HeadingKind, 编号)} 查找表。

    对 bodymatter 中的每个章/节/小节、frontmatter 中的每个 H2/H3、
    appendix 中的每个附录标题，生成一条映射。

    Args:
        structure: YAML 解析后的 ``structure`` 节点，格式见 stage-4-outline.md §4.1.x。
        outline_path: 真实的 outline.md 路径，透传给内部 record_degradation()
            调用的 input_path 参数（G1 交叉验证 D3 附带修复：原先本函数内部
            五处台账全部写死字面量 "outline.md"，与其他消费者传真实路径不一致，
            既削弱 event_id 区分度也不利于遥测排查）。默认 None 时回退到旧的
            字面量 "outline.md"，保证不破坏既有调用方行为。

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

    # D1-1 调用点 1：先归一化键名，再按 schema 权威键名读取。本函数对字段的
    # 读取语义**完全符合权威契约、不得修改**；违规方是产出端与适配层，故修在入口。
    structure = normalize_outline_structure(structure, outline_path)

    # 真实 outline 路径优先；未传入时回退旧字面量，保证既有调用方行为不变。
    _input_path = outline_path if outline_path is not None else "outline.md"

    # ── frontmatter ──
    front_items: list[dict] = structure.get("frontmatter", [])
    if isinstance(front_items, list):
        for item in front_items:
            if not isinstance(item, dict):
                continue
            title = item.get("chapter_title", "")
            if title:
                lookup[title.strip()] = (HeadingKind.FRONT_MATTER, None)
            for sec_entry in item.get("sections", []):
                if isinstance(sec_entry, dict):
                    sec_title = sec_entry.get("section_title", "")
                elif isinstance(sec_entry, str):
                    sec_title = sec_entry
                else:
                    continue
                if sec_title.strip():
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

            sections: list = ch.get("sections", [])
            for i, sec_entry in enumerate(sections, start=1):
                if isinstance(sec_entry, dict):
                    sec_title = sec_entry.get("section_title", "")
                elif isinstance(sec_entry, str):
                    sec_title = sec_entry
                else:
                    continue
                if sec_title.strip():
                    lookup[sec_title.strip()] = (
                        HeadingKind.SECTION,
                        (ch_no, i),
                    )

            subsections: list[dict] = ch.get("subsections", [])
            if isinstance(subsections, list):
                # 该章内每个 parent（按 sections 中的 1-based 序号）下 subsection
                # 的递增计数器——用于生成 lookup 内部自洽的三元组占位编号。
                # 注意：此编号最终会被 headings.py Phase 7b 按文档序重算覆盖
                # （见方案「方案甲」决策），这里只保证 lookup 内部不出现 None /
                # 硬编码 1 这种退化值，便于调试与未来兜底逻辑变更。
                parent_seq_counter: dict[int, int] = {}
                for sub in subsections:
                    if not isinstance(sub, dict):
                        continue

                    legacy_used = False

                    # ── parent 标识：优先规范字段名 parent_section_no（编号语义），
                    #    读不到则降级到旧字段名 parent（标题文本语义）──
                    if "parent_section_no" in sub:
                        parent_identifier = str(sub.get("parent_section_no") or "")
                        parent_is_title_text = False
                    elif "parent" in sub:
                        parent_identifier = str(sub.get("parent") or "")
                        parent_is_title_text = True
                        legacy_used = True
                    else:
                        parent_identifier = ""
                        parent_is_title_text = False

                    # ── 小节标题：优先规范字段名 subsection_title，
                    #    读不到则降级到旧字段名 title ──
                    if "subsection_title" in sub:
                        sub_title = str(sub.get("subsection_title") or "")
                    elif "title" in sub:
                        sub_title = str(sub.get("title") or "")
                        legacy_used = True
                    else:
                        sub_title = ""

                    if legacy_used:
                        # G1 交叉验证 D3 附带裁决：与 subsection_parent_not_found /
                        # subsection_missing_or_empty_fields 同理，同一份 outline
                        # 中多条 subsection 都使用旧字段名时也会被折叠成 1 条记录，
                        # 存在同样的"事件粒度过粗"风险，故一并传 instance_key。
                        # sub_title 此时可能已解析出来；解析不出时退化用 repr(sub)
                        # 兜底，保证仍能区分不同的原始条目。
                        record_degradation(
                            stage="assemble",
                            component="outline_reader",
                            reason="subsection_legacy_field_names",
                            level="L-记录",
                            fallback_used="legacy_field_names(parent/title)",
                            impact=(
                                "subsection 使用了旧字段名 parent/title，"
                                "建议迁移到 parent_section_no/subsection_title"
                            ),
                            input_path=_input_path,
                            instance_key=sub_title.strip() or repr(sub),
                        )

                    if not parent_identifier.strip() or not sub_title.strip():
                        import sys as _sys
                        print(
                            f"[WARN] outline_reader: 跳过一条 subsection —— "
                            f"parent 或 title 字段缺失/为空: {sub!r}",
                            file=_sys.stderr,
                        )
                        record_degradation(
                            stage="assemble",
                            component="outline_reader",
                            reason="subsection_missing_or_empty_fields",
                            level="L-显著",
                            fallback_used="skip_subsection",
                            impact="subsection 因字段缺失/为空未能入表",
                            input_path=_input_path,
                            # 标题/parent 字段本身缺失，无法用标题区分实例；退化
                            # 用整条原始 sub dict 的 repr 作为实例标识（不同的
                            # 残缺条目 repr 不同，能区分开；两条内容完全相同的
                            # 残缺条目折叠为 1 条是可接受的，因为它们确实是
                            # 同一件事）。
                            instance_key=repr(sub),
                        )
                        continue

                    parent_idx = _find_parent_section_idx(
                        sections, parent_identifier, parent_is_title_text
                    )

                    if parent_idx is None:
                        # 匹配失败：不静默丢弃，写台账 + stderr 诊断
                        import sys as _sys
                        print(
                            f"[WARN] outline_reader: subsection "
                            f"{sub_title.strip()!r} 的 parent 标识 "
                            f"{parent_identifier!r} 未在本章 sections 中找到匹配",
                            file=_sys.stderr,
                        )
                        record_degradation(
                            stage="assemble",
                            component="outline_reader",
                            reason="subsection_parent_not_found",
                            level="L-显著",
                            fallback_used="skip_subsection",
                            impact=(
                                f"subsection {sub_title.strip()!r} 未能入表，"
                                f"结构覆盖将丢失该条目"
                            ),
                            input_path=_input_path,
                            # G1 交叉验证 D3：instance_key 传 subsection 标题，
                            # 使同一 outline 中多个不同的孤儿 subsection 各自
                            # 产生独立的台账记录，而不是被同一 event_id 折叠。
                            instance_key=sub_title.strip(),
                        )
                        continue

                    seq = parent_seq_counter.get(parent_idx, 0) + 1
                    parent_seq_counter[parent_idx] = seq

                    lookup[sub_title.strip()] = (
                        HeadingKind.SUBSECTION,
                        (ch_no, parent_idx, seq),
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


def build_structure_manifest(
    structure: dict,
    outline_path: str | None = None,
    lookup: dict[str, tuple[HeadingKind, HeadingNumber]] | None = None,
) -> dict:
    """构建结构清单的摘要信息（供 Issue 记录和调试）。

    跨模型兼容性优化方案 §二 A1：``subsection_count`` 曾经直接用
    ``len(ch.get("subsections", []))`` 统计 YAML 声明条数，与
    ``_build_structure_lookup()`` 实际成功入表的条目数脱节（例如某条
    subsection 因 parent 匹配失败被跳过，manifest 却仍然把它计入总数），
    对 builder.py 的 INFO 日志构成"谎报"。这里改为内部调用
    ``_build_structure_lookup()`` 做统一展平，``subsection_count`` 语义
    调整为"实际成功入表数"，另外新增 ``subsection_declared_count`` 保留
    YAML 声明数，二者不等时写台账（L-记录，供人工核对丢弃了哪些条目——
    具体丢弃原因已由 ``_build_structure_lookup()`` 内部逐条写过更详细的
    台账事件，这里只做一次汇总级别的提示）。

    经核对：``chapter_count``/``section_count`` 是直接从 ``bodymatter``
    的章/节列表长度中入表的（``_build_structure_lookup()`` 对章/节不存在
    "匹配失败被跳过"的分支，章节标题即使为空也不影响计数逻辑本身），
    不存在类似"声明数 vs 实际入表数"的脱节，因此保持原有直接统计方式。

    Args:
        structure: YAML 解析后的 ``structure`` 节点。
        outline_path: 真实的 outline.md 路径，透传给内部台账写入（同
            ``_build_structure_lookup()`` 的同名参数，D3 附带修复）。
        lookup: 可选的、调用方已经算好的 ``_build_structure_lookup()`` 结果。
            传入时直接复用，不再内部重新解析一遍（G1 交叉验证 D5 裁决）：
            一次转换中 builder.py/headings.py 会多次需要展平结果，若各自
            都重新调用 ``_build_structure_lookup()``，其内部的逐条 stderr
            诊断（如"孤儿 subsection 未找到匹配"）会随调用次数成倍重复
            打印，让用户误以为存在多个问题。不传时（默认 None）内部按
            旧逻辑自行计算，不影响任何现有调用方。

    Returns:
        {"frontmatter_count": N, "chapter_count": N, "section_count": N,
         "subsection_count": N, "subsection_declared_count": N,
         "appendix_count": N}
        其中 ``subsection_count`` 为实际成功入表数（与 lookup 一致），
        ``subsection_declared_count`` 为 YAML 声明数。
    """
    manifest: dict[str, int] = {
        "frontmatter_count": 0,
        "chapter_count": 0,
        "section_count": 0,
        "subsection_count": 0,
        "subsection_declared_count": 0,
        "appendix_count": 0,
    }
    if not isinstance(structure, dict):
        return manifest

    # D1-1 调用点 2：台账路径同样先归一化，否则 chapter_count 等统计会与
    # lookup（已归一化）口径不一致，manifest 再次沦为"谎报"。
    structure = normalize_outline_structure(structure, outline_path)

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
                manifest["subsection_declared_count"] += len(
                    ch.get("subsections", [])
                )

    app: list = structure.get("appendix", [])
    if isinstance(app, list):
        manifest["appendix_count"] = len(app)

    # 实际成功入表数：优先复用调用方传入的 lookup（D5），否则按旧逻辑
    # 现算一遍——两条路径统计口径完全一致，只是是否重复解析的区别。
    if lookup is None:
        lookup = _build_structure_lookup(structure, outline_path)
    manifest["subsection_count"] = sum(
        1 for kind, _number in lookup.values() if kind == HeadingKind.SUBSECTION
    )

    if manifest["subsection_count"] != manifest["subsection_declared_count"]:
        record_degradation(
            stage="assemble",
            component="outline_reader",
            reason="subsection_count_mismatch",
            level="L-记录",
            fallback_used="subsection_count_reflects_actual_lookup_entries",
            impact=(
                f"YAML 声明 {manifest['subsection_declared_count']} 条 subsection，"
                f"实际入表 {manifest['subsection_count']} 条，差异条目的具体原因见"
                f"更早的 subsection_* 台账事件"
            ),
            input_path=outline_path if outline_path is not None else "outline.md",
        )

    return manifest
