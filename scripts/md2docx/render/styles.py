"""Word 命名样式表的唯一构建点（C-07a render/styles.py）。

从 config.py 读取 STYLE_SPECS 和 BehaviorFlags，调用 python-docx API 一次性构建
全部命名样式并注册到 Document 对象。任何其他模块需要新建/修改样式，必须通过本模块
提供的 register_styles() 函数。

G-04 分布式要求：Pt() 和 Cm() 的 import 语句仅允许存在于 config.py、
render/styles.py、render/oxml_helpers.py 三个文件中——本文件是其中之一。

内置样式（已在空白 Document 中存在的）优先复用并修改其属性；自定义样式
（Caption Figure、Table Source、TOC Heading 等）用 add_style() 创建。
"""
from __future__ import annotations

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.styles.style import BaseStyle

from ..config import (
    ALIGN_CENTER,
    ALIGN_JUSTIFY,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    COLOR_QUOTE_BORDER,
    LINE_SPACING_ONE_HALF,
    LINE_SPACING_SINGLE,
    BehaviorFlags,
    StyleSpec,
    STYLE_SPECS,
)

# ---------------------------------------------------------------------------
# 对齐方式 / 行距 映射表
# ---------------------------------------------------------------------------

_ALIGN_MAP: dict[str, WD_ALIGN_PARAGRAPH] = {
    ALIGN_LEFT: WD_ALIGN_PARAGRAPH.LEFT,
    ALIGN_CENTER: WD_ALIGN_PARAGRAPH.CENTER,
    ALIGN_RIGHT: WD_ALIGN_PARAGRAPH.RIGHT,
    ALIGN_JUSTIFY: WD_ALIGN_PARAGRAPH.JUSTIFY,
}

# 空白 Document 中已存在的内置样式名（python-docx 默认提供，不需 add_style）
_BUILTIN_STYLE_NAMES: frozenset[str] = frozenset({
    "Normal",
    "Heading 1",
    "Heading 2",
    "Heading 3",
    "Heading 4",
    "Heading 5",
    "Body Text",
    "List Bullet",
    "List Number",
    "Quote",
    "TOC Heading",  # python-docx 空白 Document 中已内置
})


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _get_or_create_rFonts(rPr) -> OxmlElement:
    """从 <w:rPr> 元素中获取或创建 <w:rFonts> 子元素。"""
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    return rFonts


def _set_east_asian_font(style, font_name: str) -> None:
    """在样式 rPr 的 rFonts 元素上设置 w:eastAsia 属性。

    python-docx 不提供 eastAsia 字体的直接 API，必须通过 OXML 手写设置。
    """
    rPr = style.element.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        style.element.append(rPr)
    rFonts = _get_or_create_rFonts(rPr)
    rFonts.set(qn("w:eastAsia"), font_name)


def _apply_line_spacing(pf, line_spacing: str) -> None:
    """将 config 行距标记转换为 python-docx 行距值并写入 paragraph_format。"""
    if line_spacing == LINE_SPACING_SINGLE:
        pf.line_spacing = 1.0
    elif line_spacing == LINE_SPACING_ONE_HALF:
        pf.line_spacing = 1.5


def _apply_first_line_indent(pf, spec: StyleSpec) -> None:
    """首行缩进双写模式（V-07）：长度值（cm）兼容性兜底 + 字符模式（Word 优先读取）。

    spec.first_line_indent_cm 为 None 表示该样式不需要首行缩进。
    """
    if spec.first_line_indent_cm is None:
        return
    pf.first_line_indent = Cm(spec.first_line_indent_cm)
    if spec.first_line_chars is not None:
        # pf._element 对于样式是 <w:style>（CT_Style），需先 get_or_add_pPr()
        # 取得 <w:pPr>，再 get_or_add_ind() 取得 <w:ind>，在其上设置
        # w:firstLineChars 属性（字符数 × 100，如 200=2字符）。
        ind = pf._element.get_or_add_pPr().get_or_add_ind()
        ind.set(qn("w:firstLineChars"), str(spec.first_line_chars))


def _resolve_body_text_alignment(spec: StyleSpec, flags: BehaviorFlags) -> str:
    """Body Text 对齐方式按 BehaviorFlags.body_alignment 动态选择。

    其他样式直接返回 spec 中预设的对齐值。
    """
    if spec.name != "Body Text":
        return spec.alignment
    if flags.body_alignment == "left":
        return ALIGN_LEFT
    return ALIGN_JUSTIFY


def _apply_style_spec(style, spec: StyleSpec, flags: BehaviorFlags) -> None:
    """将单个 StyleSpec 的全部度量参数一次性施加到一个 Word 样式对象上。

    覆盖：字体（西文 + 中文字体）、字号、字重/斜体、颜色、行距、段前/段后、
    对齐、首行缩进（双写）、左缩进。
    """
    # ---- 字体 ----
    style.font.name = spec.latin_font  # 西文字体（python-docx 原生 API）
    _set_east_asian_font(style, spec.cjk_font)  # 中文字体（OXML 手写）

    # ---- 字号 ----
    style.font.size = Pt(spec.size_pt)

    # ---- 字重 / 斜体 ----
    style.font.bold = spec.bold
    style.font.italic = spec.italic

    # ---- 颜色 ----
    style.font.color.rgb = RGBColor.from_string(spec.color_hex.lstrip("#"))

    # ---- 段落格式 ----
    pf = style.paragraph_format

    # 行距
    _apply_line_spacing(pf, spec.line_spacing)

    # 段前 / 段后
    pf.space_before = Pt(spec.space_before_pt)
    pf.space_after = Pt(spec.space_after_pt)

    # 对齐（Body Text 按 BehaviorFlags 动态选择）
    alignment = _resolve_body_text_alignment(spec, flags)
    pf.alignment = _ALIGN_MAP[alignment]

    # 首行缩进（V-07 双写模式）
    _apply_first_line_indent(pf, spec)

    # 左缩进
    if spec.left_indent_cm is not None:
        pf.left_indent = Cm(spec.left_indent_cm)


def _set_left_border(style, color_hex: str, sz: int = 8) -> None:
    """在样式段落属性上设置左侧边框（Quote 样式专用，规格要求 1pt #BFBFBF）。

    产出 XML：
    <w:pPr>
      <w:pBdr>
        <w:left w:val="single" w:sz="8" w:space="4" w:color="BFBFBF"/>
      </w:pBdr>
    </w:pPr>

    Args:
        style: python-docx Style 对象
        color_hex: 边框颜色（#RRGGBB 格式）
        sz: 线宽（八分之一磅单位），默认 8 = 1pt
    """
    pPr = style.element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        style.element.append(pPr)
    pBdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(sz))
    left.set(qn("w:space"), "4")
    left.set(qn("w:color"), color_hex.lstrip("#"))
    pBdr.append(left)
    pPr.append(pBdr)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def register_styles(doc: Document) -> dict[str, BaseStyle]:
    """在空白 Document 上注册全部命名样式，返回样式名→Style 字典。

    先构建 Normal（作为其他样式的基样式），再逐个构建其余 18 个样式。
    内置样式（Normal / Heading 1~5 / Body Text / List Bullet / List Number /
    Quote）复用 doc.styles 中已存在的对象并修改属性；自定义样式（Caption Figure /
    Caption Table / Table Source / Body Text No Indent / Header Text / Footer Text /
    Table Header / Table Body / TOC Heading）通过 doc.styles.add_style() 新建。

    TOC Heading 虽为 Word 内置样式名，但其 outlineLevel 为 Body Text，
    不会被 TOC 域收录，满足"不入 TOC、不占编号"的规格要求（04-interface-spec.md §2.2）。

    Body Text No Indent 基于 Body Text 创建，仅覆盖首行缩进为零，
    其余属性全部从 Body Text 继承。

    根据 04-interface-spec.md §2.2，Quote 样式额外设置左侧 1pt #BFBFBF 段落边框。
    标题系（Heading 1~5）不设置 page_break_before（V-08 硬约束）。

    Args:
        doc: python-docx Document 对象

    Returns:
        dict[str, BaseStyle]: 样式名 → 样式对象的映射，供其他渲染模块按名引用
    """
    flags = BehaviorFlags()  # 使用内置默认行为开关
    style_map: dict[str, BaseStyle] = {}

    # ---- 1. 先构建 Normal（作为其他样式的基样式） ----
    normal_spec = STYLE_SPECS["Normal"]
    normal_style = doc.styles["Normal"]
    _apply_style_spec(normal_style, normal_spec, flags)
    style_map["Normal"] = normal_style

    # ---- 2. 构建 STYLE_SPECS 中其余命名样式 ----
    for name, spec in STYLE_SPECS.items():
        if name == "Normal":
            continue

        if name in _BUILTIN_STYLE_NAMES:
            # 复用已存在的内置样式并修改属性
            style = doc.styles[name]
        else:
            # 自定义样式（Caption Figure / Table Source / TOC Heading 等）
            style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)

        _apply_style_spec(style, spec, flags)

        # Quote 特殊处理：添加左侧边框（04-interface-spec.md §2.2，1pt #BFBFBF）
        if name == "Quote":
            _set_left_border(style, COLOR_QUOTE_BORDER, sz=8)  # 8 = 1pt

        style_map[name] = style

    # ---- 3. Body Text No Indent（基于 Body Text，仅覆盖首行缩进为零） ----
    # 该样式不在 STYLE_SPECS 中——它从 Body Text 继承全部属性，唯一差异是
    # 去除首行缩进（用于篇章首段等不需要缩进的场景，04-interface-spec.md §2.2）。
    body_text_style = style_map["Body Text"]
    bt_ni = doc.styles.add_style("Body Text No Indent", WD_STYLE_TYPE.PARAGRAPH)
    bt_ni.base_style = body_text_style
    # 清除首行缩进（继承自 Body Text 的 first_line_indent 需显式覆盖）
    bt_ni.paragraph_format.first_line_indent = Pt(0)
    # 同步清除 firstLineChars（OXML 字符模式值），否则 Word 可能仍读取该属性
    pPr_ni = bt_ni.paragraph_format._element.get_or_add_pPr()
    ind_ni = pPr_ni.find(qn("w:ind"))
    if ind_ni is not None and ind_ni.get(qn("w:firstLineChars")) is not None:
        del ind_ni.attrib[qn("w:firstLineChars")]
    style_map["Body Text No Indent"] = bt_ni

    return style_map


# ===========================================================================
# 自检块
# ===========================================================================
if __name__ == "__main__":
    doc = Document()
    result = register_styles(doc)

    # 1. 验证返回的字典包含全部样式名（含 Body Text No Indent）
    spec_names = set(STYLE_SPECS.keys())
    expected_names = spec_names | {"Body Text No Indent"}
    actual_names = set(result.keys())
    assert actual_names == expected_names, (
        f"样式名不匹配：期望 {expected_names - actual_names}，多余 {actual_names - expected_names}"
    )

    # 2. 验证 'Normal' 样式存在且字号为 11pt
    assert "Normal" in result
    normal_style = result["Normal"]
    assert normal_style.font.size == Pt(11.0), (
        f"Normal 字号期望 11pt，实际 {normal_style.font.size}"
    )

    # 3. 验证 'Heading 1' 字号为 24pt、bold=True
    assert "Heading 1" in result
    h1_style = result["Heading 1"]
    assert h1_style.font.size == Pt(24.0), (
        f"Heading 1 字号期望 24pt，实际 {h1_style.font.size}"
    )
    assert h1_style.font.bold is True, "Heading 1 bold 期望 True"

    # 4. 验证 'Body Text' 存在首行缩进
    assert "Body Text" in result
    body_style = result["Body Text"]
    assert body_style.paragraph_format.first_line_indent is not None, (
        "Body Text 缺少 first_line_indent"
    )

    # 5. 验证 'Body Text No Indent' 存在且无首行缩进
    assert "Body Text No Indent" in result
    bt_ni = result["Body Text No Indent"]
    fi = bt_ni.paragraph_format.first_line_indent
    assert fi is None or fi == 0 or fi == Pt(0), (
        f"Body Text No Indent first_line_indent 应为 0 或 None，实际 {fi}"
    )

    # 6. 验证 'TOC Heading' 存在（确保不是 Heading 系、不入 TOC）
    assert "TOC Heading" in result
    toc_heading = result["TOC Heading"]
    assert toc_heading.name == "TOC Heading"

    # 7. 验证 'Quote' 存在（含左侧边框）
    assert "Quote" in result
    quote_style = result["Quote"]
    # 验证段落属性中存在 w:pBdr
    pPr_quote = quote_style.element.find(qn("w:pPr"))
    assert pPr_quote is not None, "Quote 样式缺少 w:pPr"
    pBdr = pPr_quote.find(qn("w:pBdr"))
    assert pBdr is not None, "Quote 样式缺少左侧边框（w:pBdr）"

    # 8. 验证样式总数为 STYLE_SPECS 数量 + Body Text No Indent
    n = len(result)
    expected_count = len(STYLE_SPECS) + 1  # +1 for Body Text No Indent
    assert n == expected_count, (
        f"样式总数期望 {expected_count}，实际 {n}"
    )

    print(f"styles.py 自检通过：已构建 {n} 个样式（含 Body Text No Indent）")
