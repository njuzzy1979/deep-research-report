#!/usr/bin/env python3
"""drawio 布局质量校验器 —— 源文件层几何门禁（G1+G2+G6+G7+G10a+G12 实现）。

范围声明（G2+G12 补批，非完整 B1''/B3）：
  本版本实现 02 号设计文档定义的 CLI 契约中的以下子集：
    --figures-dir / --file / --ir / --exemptions / --report-out / --json
    / --mode / --strict
  接入的判据为 G1（几何完整性）+ G2（节点硬重叠，01 号文档 §3.3 三态判定
  完整版：ink-inflate + MIN_INK_THICKNESS 灰区 + 白名单式豁免机制）+ G6
  （内嵌图注）+ G7（伪图检测）+ G10a（拓扑-模式一致性，零参数判据）+ G12
  （跨图引用检测，SKILL.md 反例 26，零参数判据，检测节点文本内容中出现的
  "图N-N"形式图号引用，且排除本图自身图号的自我标注）。
  G3/G5/G11（含拟合参数）不在本批次范围内，留待 B1''/B3 批次扩展。

  G10a 的 mode 参数来源（02 号文档 §9 I-1）：G10a 判据算法本身只需边集
  （从 .drawio 本身可解析），不依赖 rank，故不受 --ir 缺失限制；但判据
  参数 mode（flow/star/grid/quadrant）的唯一权威来源是 IR JSON 的
  layout_mode 字段（03 号文档 §4.1）。未提供 --ir 时，本版本不臆测 mode，
  G10a 记为 not_applicable 并计入 summary.g10a_skipped_no_ir 计数器，不
  新增游离于 IR schema 之外的第二数据源（如 --layout-mode-map 映射文件）。
  layout_mode 为 stack/pyramid/manual 时 G10a 同样不适用（01 号文档
  §3.7.1：stack/pyramid 交 G10b，B4 后依赖 rank 字段启用）。

  G2 已知局限（01 号文档 M-6/M-8/D5-08，如实继承，非本次引入）：
    - INK_INFLATE=1.15 在同一批 7 对样本上标定，存在过拟合风险，安全窗口
      仅约 6%（真实假阴性率未知，见design docs §3.3.3）。
    - MIN_INK_THICKNESS=3px 依据 strokeWidth=1 的视觉吸收推断，未经渲染
      验证。
    - 两参数方向对冲，不应各自独立调整。
  这些是"如实继承的已知局限"，不是"因未实现而空白"——与 G1/G6/G7/G10a
  同属已交付判据，只是精度边界已知且被诚实标注。

  G6 已知局限（R2，06 号文档 §3.3.3 已裁决不在本批次修复）：对
  `<b>图注：</b>` 类 HTML 标签包裹的图注文本存在假阴性（未先 strip_html()
  再匹配 CAPTION_PAT）。本版本原样移植 rearrange_11_1.py 的实现，不修复。

  G12 已知局限（新引入，如实标注）：图号识别仅支持"图N-N"半角数字+连字符
  形式（含全角横线/破折号变体），不识别"图三-一"中文数字或"Figure 3-1"
  英文形式；自身图号从文件名 `<图号>-<描述>.drawio` 解析，若文件命名不
  遵循此约定（如手工重命名过的文件），own_figure_no 解析为 None，此时
  退化为"任何图号引用都算跨图引用"（更严格而非更宽松，不会漏报）。

退出码约定（02 号文档 §3.2，三档）：
    0 = PASS（无 error；或目录下无 .drawio 且未声明架构图）
    1 = 校验失败（存在几何损坏/硬重叠/内嵌图注/伪图/拓扑不一致/跨图引用；或声明 >0 张架构图但目录为空）
    2 = 部分校验（本版本暂无 skip 场景，预留位）

用法：
    python drawio_layout_validator.py --figures-dir research/figures
    python drawio_layout_validator.py --file a.drawio --file b.drawio --json
    python drawio_layout_validator.py --figures-dir research/figures --report-out out.json
    python drawio_layout_validator.py --file a.drawio --ir a.ir.json
    python drawio_layout_validator.py --figures-dir research/figures --exemptions research/figures/layout-exemptions.yaml
"""

import re
import sys
import html
import json
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import xml.etree.ElementTree as ET

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCHEMA_VERSION = "d5-layout-1"
VALIDATOR_VERSION = "0.4.1-g2-ancestor-fix"

BAD_LITERALS = {"None", "nan", "NaN", "null", "NULL", "undefined", ""}

# G6：图注特征正则 + 已知专用 id 集合（原样移植自 rearrange_11_1.py，不修复 R2）
CAPTION_PAT = re.compile(r"^\s*(图\s*\d+\s*[-–—]\s*\d+|图注)")
CAPTION_IDS = {"title", "note", "caption", "bottomNote"}

# G7：Mermaid 源码关键字（07 号设计文档 G 节口径，逐字沿用）
MERMAID_KEYWORDS = ("flowchart", "graph TD", "subgraph", "-->")

# G10a：不适用 mode 集合（stack/pyramid 交 G10b，manual 无拓扑一致性可言）
G10A_NOT_APPLICABLE_MODES = {"stack", "pyramid", "stack/pyramid", "manual"}

# G2：ink-box 计算参数（01 号设计文档 §3.3.1，如实继承已标定值，见模块 docstring 已知局限）
INK_INFLATE = 1.15
MIN_INK_THICKNESS = 3

# G2：自动豁免的 style 特征（01 号设计文档 §3.3.2/§6.1，无需人工登记）
AUTO_EXEMPT_STYLE_MARKERS = ("swimlane", "group", "container=1")


# ---------------------------------------------------------------------------
# G1：几何完整性判据（复用 rearrange_11_1.py 已验证的判据逻辑，独立重写、
# 不 importlib 依赖临时脚本 —— 正式仓库脚本不应依赖 _scratch_d5 临时产物）
# ---------------------------------------------------------------------------

def check_g1(vertex_elems):
    """对每个 vertex 的 x/y/width/height 做合法性检查，返回损坏 issue 列表。

    x/y 允许缺失（不计入损坏）：mxGeometry 的 x/y 在 drawio 格式中语义上默认
    为 0，被嵌套在 group/container 内、且恰好位于该容器原点（0,0）的子节点，
    draw.io 桌面版保存时会省略这两个属性——这是实测证实的合法产物（例如用
    draw.io 编组过的图例，其容器本身的第一个子节点常见此形态），不是几何
    损坏。width/height 没有这一默认语义（0 宽高的节点在视觉上无意义），
    缺失或非数值时仍判定为损坏。"""
    bad_cells = []
    for c in vertex_elems:
        g = c.find("mxGeometry")
        cid = c.get("id", "?")
        if g is None:
            bad_cells.append({"id": cid, "attr": "mxGeometry", "literal": None})
            continue
        for attr in ("x", "y", "width", "height"):
            raw = g.get(attr)
            if raw is None:
                if attr in ("x", "y"):
                    continue  # 合法默认值 0，见上方 docstring
                bad_cells.append({"id": cid, "attr": attr, "literal": None})
                continue
            if raw in BAD_LITERALS:
                bad_cells.append({"id": cid, "attr": attr, "literal": raw})
                continue
            try:
                float(raw)
            except ValueError:
                bad_cells.append({"id": cid, "attr": attr, "literal": raw})
    return bad_cells


# ---------------------------------------------------------------------------
# G2：节点硬重叠判据（01 号设计文档 §3.3 三态判定完整版：AABB 必要条件 +
# ink-box 膨胀后确认 + MIN_INK_THICKNESS 灰区，逐字移植 §3.3.1 算法）
# ---------------------------------------------------------------------------

def _strip_html_g2(s):
    """<br>/<div>/<p> 转换行符而非直接剥除（01 号文档 §3.3.1，误差不对称性
    实测：直接剥除会导致纵向漏报，见设计文档 3.3.1 <br> 处置表）。"""
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"</(div|p|li)\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def _parse_font_size_g2(style, default=16):
    m = re.search(r"fontSize=(\d+)", style or "")
    return int(m.group(1)) if m else default


def _parse_align_g2(style):
    m = re.search(r"(?<![a-zA-Z])align=(\w+)", style or "")
    return m.group(1) if m else "center"


def _char_w_g2(ch, fs):
    """按 Unicode 东亚宽度分段：CJK 全角/宽=1.0×fs，歧义宽度=0.85×fs，窄字符=0.55×fs
    （01 号文档 §3.3.1，比早期版本额外区分了 'A' 歧义宽度档）。"""
    if ch == "\n":
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return fs * 1.00
    if eaw == "A":
        return fs * 0.85
    return fs * 0.55


def _max_line_width_g2(text, fs):
    lines = text.split("\n")
    if not lines:
        return 0
    return max((sum(_char_w_g2(c, fs) for c in ln) for ln in lines), default=0)


def _estimate_lines_g2(text, box_w, fs):
    n = 0
    for ln in text.split("\n"):
        w = sum(_char_w_g2(c, fs) for c in ln)
        n += max(1, int(-(-w // box_w)) if box_w > 0 else 1)
    return max(1, n)


def _cell_aabb(cell):
    """从 mxCell 提取 (x, y, w, h) 四元组。调用前须先经过 G1 判定几何合法。

    x/y 缺失时按 drawio 语义默认取 0（见 check_g1 docstring）——这类 cell
    通常是 group/container 内部子节点，其 x/y 是相对父容器的坐标而非绝对
    画布坐标；本函数不做父子坐标换算，调用方需知悉：该 AABB 仅在"与同一
    父容器内的兄弟节点比较"时才是准确的，与画布上其他顶层节点比较可能不
    准确。当前 G2 的自动豁免机制（container=1 子节点整体豁免重叠检查）
    刚好覆盖了这一场景，故不需要更复杂的坐标换算。"""
    g = cell.find("mxGeometry")
    x = float(g.get("x")) if g.get("x") is not None else 0.0
    y = float(g.get("y")) if g.get("y") is not None else 0.0
    return (x, y, float(g.get("width")), float(g.get("height")))


def _centered_box(aabb, ink_w, ink_h, align):
    """按对齐方式把缩小后的 ink_w/ink_h 尺寸放回 AABB 内的对应位置
    （01 号文档 §3.3.1 centered_box()，仅 align 影响水平位置，垂直恒居中——
    与 draw.io whiteSpace=wrap 默认 verticalAlign=middle 的常见形态一致）。"""
    x, y, w, h = aabb
    if align == "left":
        ink_x = x
    elif align == "right":
        ink_x = x + (w - ink_w)
    else:
        ink_x = x + (w - ink_w) / 2.0
    ink_y = y + (h - ink_h) / 2.0
    return (ink_x, ink_y, ink_w, ink_h)


def _ink_box(cell):
    """计算节点的墨迹框（ink-box）。无文本的装饰形状回退为 AABB（01 号文档
    §3.3.2：无文本节点不豁免重叠检查，占据视觉空间同样构成缺陷）。"""
    aabb = _cell_aabb(cell)
    text = _strip_html_g2(cell.get("value") or "").strip()
    if not text:
        return aabb
    style = cell.get("style") or ""
    fs = _parse_font_size_g2(style)
    align = _parse_align_g2(style)
    x, y, w, h = aabb
    raw_w = _max_line_width_g2(text, fs) * INK_INFLATE
    lines = _estimate_lines_g2(text, w, fs)
    raw_h = lines * fs * 1.4 * INK_INFLATE
    ink_w = min(w, raw_w)
    ink_h = min(h, raw_h)
    return _centered_box(aabb, ink_w, ink_h, align)


def _participates_in_overlap(cell):
    """判定 cell 是否参与重叠检查（01 号文档 §3.3.2 H-4 防御性修订）。"""
    if cell.get("vertex") != "1":
        return False
    style = cell.get("style") or ""
    if "edgeLabel" in style:
        return False
    g = cell.find("mxGeometry")
    if g is not None and g.get("relative") == "1":
        return False
    return True


def _is_auto_exempt(cell, id_to_cell=None):
    """style 含 swimlane/group/container=1 → 自动豁免（01 号文档 §3.3.2/§6.1，
    无需人工登记）。

    向上追溯祖先链（实测证实必要）：draw.io 桌面版的普通 Group 操作产出的
    group 容器（style 恰为字面量 "group"，无 container=1）其子节点的 x/y
    是相对该 group 原点的坐标，而非绝对画布坐标——若只看子节点自身 style，
    子节点会被当成普通顶层节点参与重叠检测，用相对坐标误判与绝对坐标节点
    重叠（真实案例：1-1/1-2 图例内 swatchlbl 系列节点即是 group 的孙节点，
    只有其直接父 leg 容器带 container=1，group 本身只有字面量 "group"）。
    只要祖先链上任意一层命中 AUTO_EXEMPT_STYLE_MARKERS，该节点及其后代的
    坐标就不再是画布绝对坐标，必须整体豁免。"""
    style = cell.get("style") or ""
    if any(marker in style for marker in AUTO_EXEMPT_STYLE_MARKERS):
        return True
    if id_to_cell is None:
        return False
    seen = set()
    parent_id = cell.get("parent")
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = id_to_cell.get(parent_id)
        if parent is None:
            break
        parent_style = parent.get("style") or ""
        if any(marker in parent_style for marker in AUTO_EXEMPT_STYLE_MARKERS):
            return True
        parent_id = parent.get("parent")
    return False


def _aabb_intersect(a, b):
    ax1, ay1, aw, ah = a
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx1, by1, bw, bh = b
    bx2, by2 = bx1 + bw, by1 + bh
    ox = min(ax2, bx2) - max(ax1, bx1)
    oy = min(ay2, by2) - max(ay1, by1)
    if ox > 0 and oy > 0:
        return ox, oy
    return None


def check_g2_overlap(vertex_elems, exempt_cell_ids=None, id_to_cell=None):
    """01 号设计文档 §3.3.0 三态判定：

      AABB 不相交              → PASS（不产生 issue）
      AABB 相交 + ink 相交
        且 min(ox,oy) >= 3px   → FAIL（error, HARD_OVERLAP）
      AABB 相交，其余情况       → WARNING（灰区，SOFT_OVERLAP_GRAY_ZONE，不静默放行）

    Args:
        vertex_elems: 已通过 G1 几何校验（geometry 四值均可 float()）的 vertex 列表。
        exempt_cell_ids: 本次调用中应豁免的 cell id 集合（人工白名单，来自
            --exemptions；自动豁免见 _is_auto_exempt，在调用方过滤 candidates
            时一并处理，不在本函数内部重复判断）。
        id_to_cell: 全部 mxCell 的 id→element 映射，供 _is_auto_exempt 向上
            追溯祖先链判定祖先是否为 group/container（None 时退化为只看自身
            style，不追溯祖先——调用方应始终传入以避免 group 孙节点漏判）。

    Returns:
        (fail_issues, warn_issues) 二元组，均为 dict 列表。
    """
    exempt_cell_ids = exempt_cell_ids or set()
    candidates = [
        c for c in vertex_elems
        if _participates_in_overlap(c) and c.get("id") not in exempt_cell_ids
        and not _is_auto_exempt(c, id_to_cell=id_to_cell)
    ]

    fail_issues = []
    warn_issues = []
    n = len(candidates)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = candidates[i], candidates[j]
            aabb_a, aabb_b = _cell_aabb(a), _cell_aabb(b)
            aabb_hit = _aabb_intersect(aabb_a, aabb_b)
            if aabb_hit is None:
                continue  # AABB 不相交 → PASS，不产生 issue

            ink_a, ink_b = _ink_box(a), _ink_box(b)
            ink_hit = _aabb_intersect(ink_a, ink_b)

            id_a, id_b = a.get("id", "?"), b.get("id", "?")
            pair_detail = [
                {"id": id_a, "x": aabb_a[0], "y": aabb_a[1], "w": aabb_a[2], "h": aabb_a[3],
                 "ink": {"x": ink_a[0], "y": ink_a[1], "w": ink_a[2], "h": ink_a[3]}},
                {"id": id_b, "x": aabb_b[0], "y": aabb_b[1], "w": aabb_b[2], "h": aabb_b[3],
                 "ink": {"x": ink_b[0], "y": ink_b[1], "w": ink_b[2], "h": ink_b[3]}},
            ]

            if ink_hit is not None and min(ink_hit) >= MIN_INK_THICKNESS:
                ox, oy = ink_hit
                fail_issues.append({
                    "check": "G2_overlap",
                    "error_code": "HARD_OVERLAP",
                    "severity": "error",
                    "pair": pair_detail,
                    "overlap": {"w": round(ox, 1), "h": round(oy, 1),
                                "area": round(ox * oy, 1), "basis": "ink_inflated"},
                    "message": f"节点 {id_a} 与 {id_b} 墨迹相交 {ox:.1f}x{oy:.1f}px",
                    "feedback": (
                        f"节点 {id_a}(x={aabb_a[0]:.0f},y={aabb_a[1]:.0f},"
                        f"w={aabb_a[2]:.0f},h={aabb_a[3]:.0f}) 与 "
                        f"{id_b}(x={aabb_b[0]:.0f},y={aabb_b[1]:.0f},"
                        f"w={aabb_b[2]:.0f},h={aabb_b[3]:.0f}) 墨迹重叠 "
                        f"{ox:.1f}x{oy:.1f}px（面积{ox*oy:.0f}）。"
                        "建议：调整任一节点坐标使二者不再重叠，或重新排布该区域。"
                    ),
                    "retryable": True,
                })
            else:
                ox, oy = ink_hit if ink_hit is not None else (0.0, 0.0)
                warn_issues.append({
                    "check": "G2_overlap",
                    "error_code": "SOFT_OVERLAP_GRAY_ZONE",
                    "severity": "warning",
                    "pair": pair_detail,
                    "overlap": {"w": round(ox, 1), "h": round(oy, 1),
                                "area": round(ox * oy, 1), "basis": "ink_inflated"},
                    "message": (
                        f"节点 {id_a} 与 {id_b} AABB 相交但墨迹相交厚度不足 "
                        f"{MIN_INK_THICKNESS}px（灰区，非确定无害）"
                    ),
                    "feedback": (
                        f"节点 {id_a} 与 {id_b} 的包围盒相交，但估算的文字墨迹范围"
                        "相交很浅或不相交——可能是视觉安全间距不足，也可能是估算误差。"
                        "建议人工核查该区域排版，或如确认无害可加入 --exemptions 白名单。"
                    ),
                    "retryable": True,
                })

    return fail_issues, warn_issues


# ---------------------------------------------------------------------------
# G6：内嵌图注判据（原样移植自 rearrange_11_1.py 的 check_g6()，未修复 R2）
#
# 已知局限 R2（06 号文档 §3.3.3 已裁决不在本批次修复）：对 `<b>图注：</b>`
# 类 HTML 标签包裹的图注文本存在假阴性 —— CAPTION_PAT 直接匹配 value 原文，
# 未先 strip_html() 剥离标签再匹配。
# ---------------------------------------------------------------------------

def check_g6(all_cell_elems):
    """检测内嵌图注 mxCell，返回命中的 cell id 列表。"""
    hits = []
    for c in all_cell_elems:
        cid = c.get("id", "")
        value = c.get("value") or ""
        if cid in CAPTION_IDS or CAPTION_PAT.search(value):
            hits.append(cid)
    return hits


# ---------------------------------------------------------------------------
# G7：伪图检测判据（新写，口径依据 07 号设计文档 G 节：检索 Mermaid 源码
# 关键字 flowchart / graph TD / subgraph / --> ，全库 376 个节点 value 中
# 0 命中，故本判据的现实基线预期为"全部 PASS"）
# ---------------------------------------------------------------------------

def check_g7(all_cell_elems):
    """检测 value 中残留的 Mermaid 源码关键字，返回命中的 (cell_id, keyword) 列表。"""
    hits = []
    for c in all_cell_elems:
        value = c.get("value") or ""
        unescaped = html.unescape(value)
        for kw in MERMAID_KEYWORDS:
            if kw in unescaped:
                hits.append((c.get("id", "?"), kw))
    return hits


# ---------------------------------------------------------------------------
# G13：画布内引用标记检测（SKILL.md 反例 27，如 "[G-027]"/"[T-032]"/"[SRC-016]"
# 出现在画布节点文本中——这些是内部台账编号，导出 PNG 后固化为位图像素，
# 阶段 9 引用转换不会更新它们，且对读者无意义。应替换为人类可读证据描述。
# ---------------------------------------------------------------------------

CANVAS_CITATION_PAT = re.compile(
    r'\[(?:SRC|G|T|S|A|C)-\d+\]'    # [SRC-001] / [G-027] / [T-032] 等
    r'|\[(?:CM|CO|CASE)-\d+\]'       # claim_id 变体
)


def check_g13_canvas_citation(all_cell_elems):
    """检测节点文本内容中残留的内部引用编号，返回命中的 (cell_id, matched_text) 列表。

    与 G12（跨图引用）和 G6（内嵌图注）互补——G13 检测的不是图号引用，
    而是 claim_id/source_id 等内部质控编号。这些编号对读者无意义且不会在
    阶段 9 被转换（PNG 是位图）。
    """
    hits = []
    for c in all_cell_elems:
        value = c.get("value") or ""
        text = _strip_html_g2(value)
        matches = CANVAS_CITATION_PAT.findall(text)
        for m in matches:
            hits.append((c.get("id", "?"), m))
    return hits
# 内容中——真实案例：3-3 图的 in1/in2 引用了"图3-1"/"图3-2"，这种在画布内直接
# 指向其他图号的写法会增加读者跨图翻阅的阅读负担，应改写为不依赖图号的自足描述）
# ---------------------------------------------------------------------------

CROSS_FIGURE_REF_PAT = re.compile(r"图\s*(\d+\s*[-–—]\s*\d+)")
_FILE_FIGURE_NO_PAT = re.compile(r"^(\d+-\d+)")


def _normalize_figure_no(s):
    """把 "3-1"/"3 - 1"/"3—1" 等写法统一归一化为 "3-1" 便于比较。"""
    return re.sub(r"\s*[-–—]\s*", "-", s.strip())


def check_g12_cross_figure_ref(all_cell_elems, own_figure_no=None):
    """检测节点文本内容中残留的跨图引用（如"图3-1"），返回命中的 (cell_id, matched_text) 列表。

    与 G6（CAPTION_PAT，检测行首的"图N-N 标题"型图注）刻意区分：G12 不要求
    匹配出现在行首，只要节点文本任意位置包含"图N-N"形式的图号引用即命中——
    这类文本即使不是图注，也构成读者必须跨图翻阅才能理解本图的负担。

    Args:
        all_cell_elems: 全部 mxCell 列表
        own_figure_no: 本文件自身图号（如 "3-3"，从文件名 `<图号>-<描述>.drawio`
            解析而来）。命中的图号若与自身图号相同（如标题 cell 内"图3-3 xxx"
            自我标注本图图号），不算跨图引用，予以排除，避免与 G6 重复判定同
            一处内嵌标题文本。
    """
    own_norm = _normalize_figure_no(own_figure_no) if own_figure_no else None
    hits = []
    for c in all_cell_elems:
        value = c.get("value") or ""
        text = _strip_html_g2(value)
        m = CROSS_FIGURE_REF_PAT.search(text)
        if not m:
            continue
        matched_no = _normalize_figure_no(m.group(1))
        if own_norm is not None and matched_no == own_norm:
            continue
        hits.append((c.get("id", "?"), m.group(0)))
    return hits


def _load_own_figure_no(path: Path):
    """从文件名 `<图号>-<描述>.drawio` 解析本图自身图号（如 "3-3"）。"""
    m = _FILE_FIGURE_NO_PAT.match(path.stem)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# G10a：拓扑-模式一致性判据（官方 mode-dispatch 完整版，逐字移植自
# g10a_official_check_3x.py 的 g10a_official(mode, V, E)，替换掉
# rearrange_11_1.py 内联的 quadrant 专用简化版 —— 该简化版是已确认的 R1
# 问题根源，本判据不重蹈覆辙）
#
# mode 的唯一权威来源是 IR JSON 的 layout_mode 字段（--ir 参数）。未提供
# --ir 时不臆测 mode，调用方应改用 g10a_not_applicable() 的 not_applicable
# 路径，不得凭空指定 mode 调用本函数。
# ---------------------------------------------------------------------------

def _degree_maps(E):
    outd, ind, deg = defaultdict(int), defaultdict(int), defaultdict(int)
    for s, t in E:
        outd[s] += 1
        ind[t] += 1
        deg[s] += 1
        deg[t] += 1
    return outd, ind, deg


def extract_topology(all_cell_elems):
    """从 cell 元素列表提取顶点集合 V 与边集合 E（仅保留 source/target 均引用顶点的边）。"""
    V = {c.get("id") for c in all_cell_elems if c.get("vertex") == "1"}
    E = [(c.get("source"), c.get("target")) for c in all_cell_elems if c.get("edge") == "1"
         and c.get("source") and c.get("target")]
    E = [(s, t) for s, t in E if s in V and t in V]
    return V, E


def check_g10a(mode, V, E):
    """01 号设计文档 §3.7.1 官方 mode-dispatch 版判据，返回 (verdict, detail) 二元组。

    verdict 为 None 表示一致 OK；否则为 error_code 字符串。
    """
    outd, ind, deg = _degree_maps(E)
    N = len(V)
    if mode == "flow":
        if any(outd[n] > 1 for n in V) and any(ind[n] > 1 for n in V):
            return "FLOW_RECONVERGENT", {"n_vertex": N, "n_edge": len(E)}
        return None, {"n_vertex": N, "n_edge": len(E)}
    if mode == "star":
        if not E:
            return "STAR_NO_EDGES", {"n_vertex": N, "n_edge": len(E)}
        mx = max(deg.values())
        hubs = [n for n in V if deg[n] == mx]
        sec = max((deg[n] for n in V if deg[n] < mx), default=0)
        if len(hubs) != 1:
            return "STAR_NO_UNIQUE_HUB", {"n_vertex": N, "n_edge": len(E), "hubs": hubs}
        if mx < max(3, sec * 2):
            return "STAR_HUB_NOT_DOMINANT", {"n_vertex": N, "n_edge": len(E), "hub": hubs[0], "hub_degree": mx, "second_degree": sec}
        return None, {"n_vertex": N, "n_edge": len(E), "hub": hubs[0]}
    if mode in ("grid", "quadrant"):
        if not E:
            return None, {"n_vertex": N, "n_edge": len(E)}
        adj = defaultdict(set)
        for s, t in E:
            adj[s].add(t)
            adj[t].add(s)
        seen, best = set(), 0
        for v in V:
            if v in seen or v not in adj:
                continue
            stack = [v]
            seen.add(v)
            c = 0
            while stack:
                u = stack.pop()
                c += 1
                for w in adj[u]:
                    if w not in seen:
                        seen.add(w)
                        stack.append(w)
            best = max(best, c)
        if best > N / 3.0:
            return "GRID_HAS_CONNECTED_STRUCTURE(%d/%d)" % (best, N), {"n_vertex": N, "n_edge": len(E), "largest_component": best}
        return None, {"n_vertex": N, "n_edge": len(E), "largest_component": best}
    return "UNKNOWN_MODE(%s)" % mode, {"n_vertex": N, "n_edge": len(E)}


# ---------------------------------------------------------------------------
# 单文件校验
# ---------------------------------------------------------------------------

def _load_layout_mode(ir_path):
    """从 IR JSON 读取 layout_mode 字段（03 号文档 §4.1 唯一权威来源）。"""
    if ir_path is None:
        return None
    try:
        data = json.loads(Path(ir_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("layout_mode")


def _load_exemptions(exemptions_path):
    """加载 G2 豁免白名单（02 号文档 §6/§7 容错与降级）。

    返回 (by_file: dict[str, set[str]], warnings: list[str])：
      - 文件不存在 → 视为空白名单，不报错（豁免只会让门禁更宽松）
      - PyYAML 不可用 / YAML 解析失败 → 空白名单 + warning（同上，读不到反而更严）
      - 缺失 file/check/cells/reason 任一字段的条目 → 跳过该条 + warning（不整体失败）
      - check != "G2_overlap" 的条目 → 跳过该条 + warning（豁免机制仅对 G2 开放，02号文档§6.2）
    """
    by_file = defaultdict(set)
    warnings = []
    if exemptions_path is None:
        return by_file, warnings
    path = Path(exemptions_path)
    if not path.exists():
        return by_file, warnings

    try:
        import yaml
    except ImportError:
        warnings.append(f"PyYAML 不可用，豁免文件 {path} 无法解析，本次运行按空白名单处理（门禁更严，非失败）")
        return by_file, warnings

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        warnings.append(f"豁免文件 {path} 解析失败: {e}，本次运行按空白名单处理")
        return by_file, warnings

    if not isinstance(data, dict):
        warnings.append(f"豁免文件 {path} 顶层结构不是映射（期望含 exemptions 键的对象），本次运行按空白名单处理")
        return by_file, warnings

    entries = data.get("exemptions") or []
    for entry in entries:
        missing = [k for k in ("file", "check", "cells", "reason") if not entry.get(k)]
        if missing:
            warnings.append(f"豁免条目缺少必填字段 {missing}，已忽略该条: {entry}")
            continue
        if entry["check"] != "G2_overlap":
            warnings.append(f"豁免机制仅对 G2_overlap 开放，忽略条目声明的 check={entry['check']!r}: {entry}")
            continue
        by_file[entry["file"]].update(entry["cells"])

    return by_file, warnings


def validate_one_file(path: Path, ir_path=None, exempt_cell_ids=None) -> dict:
    """校验单个 .drawio 文件，返回 02 号文档 §4 schema 的单 item 结构。

    Args:
        path: 待校验的 .drawio 文件路径
        ir_path: 可选，配套 IR JSON 路径。提供时用其中的 layout_mode 字段
            驱动 G10a 做完整 mode-dispatch 判定；不提供时 G10a 记为
            not_applicable，不臆测 mode。
        exempt_cell_ids: 可选，本文件 G2 判据的人工豁免 cell id 集合（来自
            --exemptions，按文件名匹配后传入）。
    """
    item = {
        "file": path.name,
        "format": "plain",
        "passed": True,
        "vertex_total": 0,
        "vertex_geometry_valid": 0,
        "checks": {
            "G1_geometry_integrity": "pass",
            "G2_overlap": "pass",
            "G6_embedded_caption": "pass",
            "G7_fake_diagram": "pass",
            "G10a_topology": "not_applicable",
            "G12_cross_figure_ref": "pass",
            "G13_canvas_citation": "pass",
        },
        "issues": [],
        "exemptions_applied": [],
    }

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        item["passed"] = False
        item["checks"]["G1_geometry_integrity"] = "fail"
        item["checks"]["G2_overlap"] = "skip"
        item["issues"].append({
            "check": "G1_geometry_integrity",
            "error_code": "XML_PARSE_ERROR",
            "severity": "error",
            "message": f"XML 解析失败: {e}",
            "feedback": f"{path.name} 无法解析为合法 XML，需人工检查文件是否损坏或为压缩格式。",
            "retryable": False,
        })
        return item

    root = tree.getroot()
    all_cell_elems = list(root.iter("mxCell"))
    vertex_elems = [c for c in all_cell_elems if c.get("vertex") == "1"]
    item["vertex_total"] = len(vertex_elems)
    id_to_cell = {c.get("id"): c for c in all_cell_elems if c.get("id") is not None}

    # --- G1 ---
    bad_cells = check_g1(vertex_elems)
    item["vertex_geometry_valid"] = len(vertex_elems) - len({b["id"] for b in bad_cells})

    if bad_cells:
        item["passed"] = False
        item["checks"]["G1_geometry_integrity"] = "fail"
        item["checks"]["G2_overlap"] = "skip"  # G1 失败 → 后续几何判据无意义（02号文档 §4.1 skip 语义）
        cell_ids = sorted({b["id"] for b in bad_cells})
        item["issues"].append({
            "check": "G1_geometry_integrity",
            "error_code": "GEOMETRY_INVALID",
            "severity": "error",
            "cells": bad_cells,
            "message": f"{len(cell_ids)} 个 vertex 的几何字面值非法（共 {len(bad_cells)} 处）",
            "feedback": (
                f"节点 {', '.join(cell_ids)} 的几何属性存在非数值字面值，"
                "此为生成器缺陷，不可通过重试修复。"
            ),
            "retryable": False,
        })
    else:
        # --- G2：节点硬重叠（仅在 G1 通过、几何全部合法时才有意义） ---
        bad_ids = {b["id"] for b in bad_cells}
        clean_vertex_elems = [c for c in vertex_elems if c.get("id") not in bad_ids]
        exempt_cell_ids = exempt_cell_ids or set()
        g2_fail, g2_warn = check_g2_overlap(clean_vertex_elems, exempt_cell_ids=exempt_cell_ids, id_to_cell=id_to_cell)
        if g2_fail:
            item["passed"] = False
            item["checks"]["G2_overlap"] = "fail"
            item["issues"].extend(g2_fail)
        elif g2_warn:
            item["checks"]["G2_overlap"] = "warning"
            item["issues"].extend(g2_warn)
        else:
            item["checks"]["G2_overlap"] = "pass"

        # 留痕生效豁免（02号文档 §6.2 强制留痕，可被审计"是否靠加豁免让门禁变绿"）
        overlap_participants = [c for c in clean_vertex_elems if _participates_in_overlap(c)]
        manual_hit = sorted({c.get("id") for c in overlap_participants if c.get("id") in exempt_cell_ids})
        if manual_hit:
            item["exemptions_applied"].append({
                "check": "G2_overlap", "cells": manual_hit, "source": "layout-exemptions.yaml",
            })
        auto_hit = sorted({
            c.get("id") for c in overlap_participants
            if c.get("id") not in exempt_cell_ids and _is_auto_exempt(c, id_to_cell=id_to_cell)
        })
        if auto_hit:
            item["exemptions_applied"].append({
                "check": "G2_overlap", "cells": auto_hit, "source": "style:swimlane/group/container",
            })

    # --- G6：内嵌图注 ---
    g6_hits = check_g6(all_cell_elems)
    if g6_hits:
        item["passed"] = False
        item["checks"]["G6_embedded_caption"] = "fail"
        item["issues"].append({
            "check": "G6_embedded_caption",
            "error_code": "EMBEDDED_CAPTION",
            "severity": "error",
            "cells": g6_hits,
            "message": f"{len(g6_hits)} 处内嵌图注 mxCell: {g6_hits}",
            "feedback": (
                f"节点 {', '.join(g6_hits)} 疑似把图注文本嵌入画布，"
                "应移除该 mxCell 并将文本移入 Markdown 正文题注。"
            ),
            "retryable": False,
        })

    # --- G7：伪图检测 ---
    g7_hits = check_g7(all_cell_elems)
    if g7_hits:
        item["passed"] = False
        item["checks"]["G7_fake_diagram"] = "fail"
        cell_ids = sorted({cid for cid, _ in g7_hits})
        item["issues"].append({
            "check": "G7_fake_diagram",
            "error_code": "FAKE_DIAGRAM",
            "severity": "error",
            "cells": g7_hits,
            "message": f"{len(cell_ids)} 个节点残留 Mermaid 源码关键字: {g7_hits}",
            "feedback": (
                f"节点 {', '.join(cell_ids)} 疑似把 Mermaid 源码文本内嵌为 text box，"
                "应重新出图为真实 drawio 图形元素，禁止文本框内嵌 Mermaid 源码。"
            ),
            "retryable": True,
        })

    # --- G12：跨图引用检测（SKILL.md 反例 26） ---
    own_figure_no = _load_own_figure_no(path)
    g12_hits = check_g12_cross_figure_ref(all_cell_elems, own_figure_no=own_figure_no)
    if g12_hits:
        item["passed"] = False
        item["checks"]["G12_cross_figure_ref"] = "fail"
        cell_ids = sorted({cid for cid, _ in g12_hits})
        item["issues"].append({
            "check": "G12_cross_figure_ref",
            "error_code": "CROSS_FIGURE_REFERENCE",
            "severity": "error",
            "cells": g12_hits,
            "message": f"{len(cell_ids)} 个节点文本内容引用了其他图号: {g12_hits}",
            "feedback": (
                f"节点 {', '.join(cell_ids)} 的文本内容中出现了跨图引用（如"
                "\"图3-1\"），要求读者跨图翻阅才能理解本图，应改写为不依赖"
                "图号的自足描述（如直接概括被引用图的内容要点，而非仅给出图号）。"
            ),
            "retryable": True,
        })

    # --- G13：画布内引用标记检测（SKILL.md 反例 27） ---
    g13_hits = check_g13_canvas_citation(all_cell_elems)
    if g13_hits:
        item["passed"] = False
        item["checks"]["G13_canvas_citation"] = "fail"
        cell_ids = sorted({cid for cid, _ in g13_hits})
        item["issues"].append({
            "check": "G13_canvas_citation",
            "error_code": "CANVAS_CITATION_RESIDUE",
            "severity": "error",
            "cells": g13_hits,
            "message": f"{len(cell_ids)} 个节点文本含内部引用编号: {g13_hits}",
            "feedback": (
                f"节点 {', '.join(cell_ids)} 的文本中出现了 [SRC-XXX]/[G-XXX]/"
                "[T-XXX] 等内部台账编号。这些编号导出 PNG 后固化为位图像素，"
                "阶段 9 引用转换不会更新它们，且对读者无意义。应替换为人类可读"
                "的证据描述（机构+年份+关键发现），追溯路径留在正文 Markdown。"
            ),
            "retryable": True,
        })

    # --- G10a：拓扑-模式一致性 ---
    layout_mode = _load_layout_mode(ir_path)
    if layout_mode is None:
        item["checks"]["G10a_topology"] = "not_applicable"
    elif layout_mode in G10A_NOT_APPLICABLE_MODES:
        item["checks"]["G10a_topology"] = "not_applicable"
    else:
        V, E = extract_topology(all_cell_elems)
        verdict, detail = check_g10a(layout_mode, V, E)
        if verdict is None:
            item["checks"]["G10a_topology"] = "pass"
        else:
            item["passed"] = False
            item["checks"]["G10a_topology"] = "fail"
            item["issues"].append({
                "check": "G10a_topology",
                "error_code": verdict.split("(")[0],
                "severity": "error",
                "detail": detail,
                "message": f"layout_mode={layout_mode} 下拓扑-模式判定={verdict}",
                "feedback": (
                    f"该图声明 layout_mode={layout_mode}，但边集拓扑与该模式不一致（{verdict}）。"
                    "禁止改模式重试，应强制转 layout_mode=manual 由人工排布。"
                ),
                "retryable": False,
            })

    return item


# ---------------------------------------------------------------------------
# 主校验流程
# ---------------------------------------------------------------------------

def run_validator(files: list, ir_files: list = None, mode: str = "block", strict: bool = False,
                   exemptions_by_file: dict = None, exemption_warnings: list = None) -> dict:
    """对给定文件列表跑校验，返回 02 号文档 §4 schema 的完整结构。

    Args:
        files: 待校验的 .drawio 文件路径列表（Path 对象）
        ir_files: 与 files 一一对应的可选 IR JSON 路径列表（None 表示该文件无 IR
            输入，G10a 记为 not_applicable）；整体省略时按全 None 处理
        mode: warn（所有 error 降级为 warning，恒 exit 0）| block（正常判定）
        strict: warning 一并计入失败
        exemptions_by_file: 文件名（含扩展名，如 "11-1-xxx.drawio"）→ 豁免 cell id
            集合，来自 --exemptions（_load_exemptions() 产出）。None 视为空白名单。
        exemption_warnings: _load_exemptions() 产出的告警文案列表，原样并入
            summary（本函数不重复校验豁免文件本身）。
    """
    if ir_files is None:
        ir_files = [None] * len(files)
    exemptions_by_file = exemptions_by_file or {}
    items = [
        validate_one_file(p, ir_path=ir, exempt_cell_ids=exemptions_by_file.get(p.name))
        for p, ir in zip(files, ir_files)
    ]

    total_errors = sum(len([i for i in it["issues"] if i["severity"] == "error"]) for it in items)
    total_warnings = sum(len([i for i in it["issues"] if i["severity"] == "warning"]) for it in items)

    vertex_total = sum(it["vertex_total"] for it in items)
    vertex_geometry_valid = sum(it["vertex_geometry_valid"] for it in items)

    files_failed = sum(1 for it in items if not it["passed"])
    files_passed = len(items) - files_failed

    if mode == "warn":
        passed = True
    elif strict:
        passed = (total_errors == 0) and (total_warnings == 0)
    else:
        passed = total_errors == 0

    exit_code = 0 if passed else 1

    g10a_skipped_no_ir = sum(1 for it in items if it["checks"].get("G10a_topology") == "not_applicable")

    exemptions_applied = []
    for it in items:
        for entry in it.get("exemptions_applied", []):
            exemptions_applied.append({"file": it["file"], **entry})

    return {
        "schema_version": SCHEMA_VERSION,
        "passed": passed,
        "exit_code": exit_code,
        "generated_at": None,  # 由 main() 填充（脚本内禁止 datetime.now() 以外的伪造）
        "validator_version": VALIDATOR_VERSION,
        "mode": mode,
        "summary": {
            "files_total": len(items),
            "files_passed": files_passed,
            "files_failed": files_failed,
            "files_skipped": 0,
            "errors": total_errors,
            "warnings": total_warnings,
            "vertex_total": vertex_total,
            "vertex_geometry_valid": vertex_geometry_valid,
            "vertex_geometry_broken": vertex_total - vertex_geometry_valid,
            "manual_ratio": None,
            "g10a_skipped_no_ir": g10a_skipped_no_ir,
        },
        "items": items,
        "skipped": [],
        "exemptions_applied": exemptions_applied,
        "exemption_load_warnings": exemption_warnings or [],
    }


def format_report(result: dict) -> str:
    """对齐 figure_gate.py 的 format_report() 风格。"""
    lines = [
        "=" * 60,
        "布局质量门禁报告 (drawio_layout_validator) — G1+G2+G6+G7+G10a+G12+G13",
        "=" * 60,
        "",
    ]
    if "error" in result:
        lines.append(f"[FAIL] 致命错误: {result['error']}")
        return "\n".join(lines)
    if "note" in result:
        lines.append(f"[INFO] {result['note']}")
        return "\n".join(lines)

    s = result["summary"]
    lines.append(f"模式: {result['mode']}")
    lines.append(f"顶点统计: {s['vertex_total']} 总计 / {s['vertex_geometry_valid']} 几何可解析 / "
                 f"{s['vertex_geometry_broken']} 几何损坏")
    if s.get("g10a_skipped_no_ir"):
        lines.append(f"G10a: {s['g10a_skipped_no_ir']} 个文件因无 --ir 输入记为 not_applicable（未臆测 mode）")
    lines.append("")

    fail_items = [it for it in result["items"] if not it["passed"]]
    if fail_items:
        lines.append("--- 判据未通过 (FATAL 除 G2/G7 外均不可重试) ---")
        for it in fail_items:
            lines.append(f"  [FAIL] {it['file']}")
            for issue in it["issues"]:
                if issue["severity"] != "error":
                    continue
                lines.append(f"         {issue['message']}")
                lines.append(f"         -> {issue['feedback']}")
        lines.append("")

    warn_issues_by_file = [
        (it["file"], issue)
        for it in result["items"]
        for issue in it["issues"]
        if issue["severity"] == "warning"
    ]
    if warn_issues_by_file:
        lines.append("--- 灰区与告警 (WARN, 不阻断) ---")
        for fname, issue in warn_issues_by_file:
            lines.append(f"  [WARN] {fname}: {issue['message']}")
        lines.append("")

    if result.get("exemptions_applied"):
        lines.append("--- 生效豁免 (可审计) ---")
        for ex in result["exemptions_applied"]:
            lines.append(f"  {ex['file']}: {ex['check']} 豁免 {ex['cells']} (来源: {ex['source']})")
        lines.append("")

    if result.get("exemption_load_warnings"):
        lines.append("--- 豁免文件加载告警 ---")
        for w in result["exemption_load_warnings"]:
            lines.append(f"  [WARN] {w}")
        lines.append("")

    lines.append("--- 逐项详情 ---")
    for it in result["items"]:
        status = "[OK]" if it["passed"] else "[FAIL]"
        checks = it["checks"]
        checks_str = " ".join(f"{k.split('_')[0]}={v}" for k, v in checks.items())
        lines.append(f"  {status} {it['file']}  {it['vertex_total']} 顶点  [{checks_str}]")

    lines.append("")
    if result["passed"]:
        lines.append(f"=== 总判定: PASS — exit {result['exit_code']} ===")
    else:
        lines.append(f"=== 总判定: FAIL ({s['errors']} errors, {s['warnings']} warnings) — exit {result['exit_code']} ===")
    if result.get("report_out"):
        lines.append(f"留痕: {result['report_out']}")

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="drawio 布局质量门禁（源文件层，B1' 版：G1+G6+G7+G10a）。"
    )
    parser.add_argument(
        "--figures-dir", default="research/figures",
        help="批量校验目录下全部 *.drawio（默认: research/figures）"
    )
    parser.add_argument(
        "--file", action="append", default=None,
        help="只校验指定文件，可多次给出；与 --figures-dir 互斥"
    )
    parser.add_argument(
        "--ir", action="append", default=None,
        help="配套 IR JSON 路径，与 --file 按给出顺序一一对应；用于驱动 G10a 完整"
             "mode-dispatch 判定。省略时 G10a 记为 not_applicable，不臆测 mode。"
             "仅在配合 --file 使用时生效（--figures-dir 批量模式下无法一一对应，忽略本参数）。"
    )
    parser.add_argument(
        "--mode", choices=["warn", "block"], default="block",
        help="warn: 所有 error 降级为 warning，恒 exit 0（B1 上线用）；block: 正常判定"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="严格模式: warning 一并计入失败"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="输出 JSON 格式"
    )
    parser.add_argument(
        "--report-out", default=None,
        help="门禁留痕 JSON 落盘路径（默认: <figures-dir>/.layout-gate-report.json）"
    )
    parser.add_argument(
        "--exemptions", default=None,
        help="G2 豁免白名单 YAML 路径（默认: <figures-dir>/layout-exemptions.yaml）。"
             "文件不存在按空白名单处理，不报错；PyYAML 不可用同样降级为空白名单+警告。"
    )

    args = parser.parse_args()

    ir_files = None
    if args.file:
        files = [Path(f) for f in args.file]
        missing = [f for f in files if not f.exists()]
        if missing:
            print(f"[FAIL] 致命错误: 文件不存在: {', '.join(str(m) for m in missing)}", file=sys.stderr)
            sys.exit(1)
        figures_dir_for_report = files[0].parent if files else Path(args.figures_dir)
        if args.ir:
            if len(args.ir) != len(files):
                print(
                    f"[FAIL] 致命错误: --ir 个数({len(args.ir)})与 --file 个数({len(files)})不一致，"
                    "两者须按给出顺序一一对应",
                    file=sys.stderr,
                )
                sys.exit(1)
            ir_missing = [f for f in args.ir if not Path(f).exists()]
            if ir_missing:
                print(f"[FAIL] 致命错误: --ir 文件不存在: {', '.join(ir_missing)}", file=sys.stderr)
                sys.exit(1)
            ir_files = [Path(f) for f in args.ir]
    else:
        figures_dir = Path(args.figures_dir)
        if not figures_dir.exists():
            print(f"[FAIL] 致命错误: figures/ 目录不存在: {figures_dir}", file=sys.stderr)
            sys.exit(1)
        files = sorted(figures_dir.glob("*.drawio"))
        figures_dir_for_report = figures_dir
        if args.ir:
            print(
                "[INFO] --figures-dir 批量模式下无法与 --ir 一一对应，本次运行忽略 --ir，"
                "G10a 记为 not_applicable",
                file=sys.stderr,
            )

    report_out = Path(args.report_out) if args.report_out else figures_dir_for_report / ".layout-gate-report.json"
    exemptions_path = Path(args.exemptions) if args.exemptions else figures_dir_for_report / "layout-exemptions.yaml"
    exemptions_by_file, exemption_warnings = _load_exemptions(exemptions_path)

    if not files:
        # 空目录一律按 02 号文档"未声明架构图"分支处理为 PASS + note。
        result = {
            "schema_version": SCHEMA_VERSION,
            "passed": True,
            "exit_code": 0,
            "generated_at": None,
            "validator_version": VALIDATOR_VERSION,
            "mode": args.mode,
            "summary": {
                "files_total": 0, "files_passed": 0, "files_failed": 0,
                "files_skipped": 0, "errors": 0, "warnings": 0,
                "vertex_total": 0, "vertex_geometry_valid": 0,
                "vertex_geometry_broken": 0, "manual_ratio": None,
                "g10a_skipped_no_ir": 0,
            },
            "items": [], "skipped": [], "exemptions_applied": [],
            "note": "目录下无 .drawio 文件，本版本不读取 outline.md 声明数，按 PASS 处理",
        }
    else:
        result = run_validator(
            files, ir_files=ir_files, mode=args.mode, strict=args.strict,
            exemptions_by_file=exemptions_by_file, exemption_warnings=exemption_warnings,
        )

    tz = timezone(timedelta(hours=8))
    result["generated_at"] = datetime.now(tz).isoformat()
    result["tool_invocation"] = " ".join(["drawio_layout_validator.py"] + sys.argv[1:])
    result["report_out"] = str(report_out)

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
