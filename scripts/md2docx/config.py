"""唯一常量之家：样式度量常量、结构语义关键词白名单、行为开关、YAML 配置加载。

红线（01-architecture.md §3.2 config.py 职责卡）：本文件不含任何具体报告的标题/
题注/文件名（反硬编码红线）；不 import python-docx（G-04 的语义是"度量数值只定义
在 config→styles 通道"——本文件只存纯数值 pt/cm 的 float，由 render/styles.py
（未来任务）包装为 Pt()/Cm()）。

例外说明（本批次实现的显式解释性决策，见任务交付说明）：01-architecture.md §3.2
原表述"config.py……不含逻辑代码"，与本次任务书明确要求的"YAML 配置加载 + M7
严格校验……加载函数接受 IssueCollector 参数"存在字面张力。00-master-design.md
"分文档与裁决冲突时以本文档 §3/§4 裁决为准"，而本次任务书是对该冲突的进一步
裁决指令（要求 config.py 承担 YAML 加载与校验），故本文件包含 `load_yaml_config`/
`resolve_behavior_flags` 两个函数体，其余仍保持纯数据。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields, replace

from .iotools import read_bytes
from .issues import Issue, IssueCollector, Level

# ===========================================================================
# 1. 页面参数（04-interface-spec.md §2.1）
# ===========================================================================

PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7
MARGIN_TOP_CM = 2.54
MARGIN_BOTTOM_CM = 2.54
MARGIN_LEFT_CM = 3.17
MARGIN_RIGHT_CM = 2.54
HEADER_DISTANCE_CM = 1.27
FOOTER_DISTANCE_CM = 1.27
HEADER_FOOTER_FONT_SIZE_PT = 9.0  # 页眉页脚字号 (V3.1 §3.2)

# ===========================================================================
# 2. 颜色常量（04-interface-spec.md §2.2/§2.7/§2.9/§2.10，00-master-design.md M4/I6/I7）
# ===========================================================================

COLOR_BLACK = "#000000"
COLOR_CAPTION_GRAY = "#555555"  # 图注/表注/表来源行（V3.0 §十一；I6 裁决）
COLOR_QUOTE_BORDER = "#BFBFBF"  # 引用块左边框（V3.0 §3.3 未给色值，I7 推断值）
COLOR_CASE_BOX_TOP_BORDER = "#D9D9D9"  # 案例框顶边框（04 §2.9 推断值）
COLOR_TABLE_ALT_SHADE = "#F2F2F2"  # 表格交替行 / 定义框底纹（V3.0 §十一）
COLOR_HYPERLINK = "#0563C1"  # 超链接色（Word 默认色，04 §2.10）

# ===========================================================================
# 3. 对齐方式常量（不 import docx，styles.py 负责映射为 WD_ALIGN_PARAGRAPH）
# ===========================================================================

ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"
ALIGN_JUSTIFY = "justify"

# 行距标记（styles.py 负责映射为 WD_LINE_SPACING）
LINE_SPACING_SINGLE = "single"
LINE_SPACING_ONE_HALF = "1.5"

# 行内代码专用西文字体（04-interface-spec.md §2.10；eastAsia 仍用宋体，样本无中文行内代码）
INLINE_CODE_ASCII_FONT = "Consolas"


# ===========================================================================
# 4. 命名样式全参数表（04-interface-spec.md §2.2，16 个基础样式 + M1 TOC Heading + M4 Table Source）
# ===========================================================================


@dataclass(frozen=True)
class StyleSpec:
    """单个 Word 命名样式的全部度量参数。

    渲染层（render/styles.py，未来任务）据此一次性构建全部命名样式；本类只是
    数据容器，不含任何构建逻辑，也不 import docx。
    """

    name: str
    cjk_font: str
    latin_font: str
    size_pt: float
    bold: bool
    italic: bool
    color_hex: str
    line_spacing: str  # LINE_SPACING_SINGLE | LINE_SPACING_ONE_HALF
    space_before_pt: float
    space_after_pt: float
    alignment: str  # ALIGN_*
    first_line_indent_cm: float | None = None
    first_line_chars: int | None = None  # w:firstLineChars 原始单位（200 = 2 字符）
    left_indent_cm: float | None = None


# 首行缩进 2 字符的长度值兜底（tech#1）：按 11pt 正文两个汉字宽度估算，
# 2 字符 ≈ 2 × 11pt = 22pt ≈ 0.777cm，四舍五入取 0.74cm（与 04 §2.2 建议值一致）。
BODY_FIRST_LINE_INDENT_CM = 0.74
BODY_FIRST_LINE_CHARS = 200  # w:firstLineChars="200"，Word 优先读取此值

STYLE_SPECS: dict[str, StyleSpec] = {
    "Normal": StyleSpec(
        name="Normal", cjk_font="宋体", latin_font="Times New Roman", size_pt=11.0,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §3.1 基准
    "Body Text": StyleSpec(
        name="Body Text", cjk_font="宋体", latin_font="Times New Roman", size_pt=11.0,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_ONE_HALF,
        space_before_pt=0.0, space_after_pt=0.0,
        # 两端对齐是本设计对"未规定正文对齐"的惯例性默认（04 §2.2 决策说明），
        # 实际应用值由 BehaviorFlags.body_alignment 决定，此处仅为默认基线。
        alignment=ALIGN_JUSTIFY,
        first_line_indent_cm=BODY_FIRST_LINE_INDENT_CM, first_line_chars=BODY_FIRST_LINE_CHARS,
    ),  # V3.0 §2/§3.3
    "Heading 1": StyleSpec(
        name="Heading 1", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=24.0,
        bold=True, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=18.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §3.2（章，顶格左对齐）
    "Heading 2": StyleSpec(
        name="Heading 2", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=16.0,
        bold=True, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=24.0, space_after_pt=12.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §3.2（节）
    "Heading 3": StyleSpec(
        name="Heading 3", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=14.0,
        bold=True, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=18.0, space_after_pt=8.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §3.2（小节）
    "Heading 4": StyleSpec(
        name="Heading 4", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=12.0,
        bold=True, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=12.0, space_after_pt=6.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §3.2（段落小标题）
    "Heading 5": StyleSpec(
        name="Heading 5", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=12.0,
        bold=True, italic=True, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=8.0, space_after_pt=4.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §3.2
    "Quote": StyleSpec(
        name="Quote", cjk_font="宋体", latin_font="Times New Roman", size_pt=10.5,
        bold=False, italic=True, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_ONE_HALF,
        # 段前/段后 6pt/6pt 为推断值（V3.0 未给出，采用与正文段间距一致的保守值）
        space_before_pt=6.0, space_after_pt=6.0, alignment=ALIGN_LEFT,
        left_indent_cm=1.0,
    ),  # V3.0 §3.3；左边框色见 COLOR_QUOTE_BORDER（I7）
    "Caption Figure": StyleSpec(
        name="Caption Figure", cjk_font="宋体", latin_font="Times New Roman", size_pt=9.0,
        bold=False, italic=False, color_hex=COLOR_CAPTION_GRAY, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=6.0, space_after_pt=0.0, alignment=ALIGN_CENTER,
    ),  # V3.0 §3.3/§十一（I6）
    "Caption Table": StyleSpec(
        name="Caption Table", cjk_font="宋体", latin_font="Times New Roman", size_pt=9.0,
        bold=False, italic=False, color_hex=COLOR_CAPTION_GRAY, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=6.0, alignment=ALIGN_CENTER,
    ),  # V3.0 §3.3/§十一（I6）
    "Table Source": StyleSpec(
        name="Table Source", cjk_font="宋体", latin_font="Times New Roman", size_pt=9.0,
        bold=False, italic=True, color_hex=COLOR_CAPTION_GRAY, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=6.0, space_after_pt=0.0, alignment=ALIGN_LEFT,
    ),  # M4 新增："Table Source" 9pt 斜体 #555555 左对齐（表格来源行，位于表下方）
    "Header Text": StyleSpec(
        name="Header Text", cjk_font="宋体", latin_font="Times New Roman", size_pt=9.0,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_RIGHT,
    ),  # V3.0 §3.3/§6.1
    "Footer Text": StyleSpec(
        name="Footer Text", cjk_font="宋体", latin_font="Times New Roman", size_pt=9.0,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_CENTER,
    ),  # V3.0 §3.3/§6.2
    "List Bullet": StyleSpec(
        name="List Bullet", cjk_font="宋体", latin_font="Times New Roman", size_pt=11.0,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_ONE_HALF,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §10.2（结构继承 Word 内置悬挂缩进，不构建自定义 abstractNum）
    "List Number": StyleSpec(
        name="List Number", cjk_font="宋体", latin_font="Times New Roman", size_pt=11.0,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_ONE_HALF,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_LEFT,
    ),  # V3.0 §10.2
    "Table Header": StyleSpec(
        name="Table Header", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=10.0,
        bold=True, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_CENTER,
        first_line_indent_cm=0.0, left_indent_cm=0.0,
    ),  # V3.0 §5.1（首列对齐例外见 BehaviorFlags.table_first_col_left_align，I5）
    "Table Body": StyleSpec(
        name="Table Body", cjk_font="宋体", latin_font="Times New Roman", size_pt=10.5,
        bold=False, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        space_before_pt=0.0, space_after_pt=0.0, alignment=ALIGN_CENTER,
        first_line_indent_cm=0.0, left_indent_cm=0.0,
    ),  # V3.0 §5.1（历史问题13：表体字号 10.5pt，非 12pt）
    "TOC Heading": StyleSpec(
        name="TOC Heading", cjk_font="微软雅黑", latin_font="Times New Roman", size_pt=16.0,
        bold=True, italic=False, color_hex=COLOR_BLACK, line_spacing=LINE_SPACING_SINGLE,
        # 段前/段后未在 M1 中给出精确值，采用与 Heading 2（同级视觉权重的节标题）
        # 一致的间距作为合理推断，供实现阶段按实际排版效果微调。
        space_before_pt=0.0, space_after_pt=24.0, alignment=ALIGN_CENTER,
    ),  # M1：目录页/图表目录页标题专用样式，非 Heading 系不入 TOC 不占编号
}


# ===========================================================================
# 5. 封面规格（04-interface-spec.md §2.3，M4 分隔线）
# ===========================================================================

COVER_TOP_SPACING_CM = 6.0  # I11：单个空段落 space_before=Cm(6.0) 实现顶部留白


@dataclass(frozen=True)
class CoverElementSpec:
    size_pt: float
    bold: bool
    color_hex: str
    alignment: str
    space_before_pt: float
    space_after_pt: float


COVER_ELEMENTS: dict[str, CoverElementSpec] = {
    "title": CoverElementSpec(28.0, True, COLOR_BLACK, ALIGN_CENTER, 0.0, 12.0),
    "subtitle": CoverElementSpec(14.0, False, COLOR_BLACK, ALIGN_CENTER, 0.0, 24.0),
    "report_type": CoverElementSpec(16.0, False, COLOR_BLACK, ALIGN_CENTER, 0.0, 36.0),
    "organization": CoverElementSpec(14.0, True, COLOR_BLACK, ALIGN_CENTER, 0.0, 6.0),
    "version_date": CoverElementSpec(11.0, False, COLOR_BLACK, ALIGN_CENTER, 0.0, 0.0),
}


@dataclass(frozen=True)
class CoverSeparatorSpec:
    sz: int  # w:sz（八分之一磅单位），8 = 1pt
    color_hex: str
    width_cm: float
    alignment: str


# M4：封面分隔线（机构名上方，1pt 黑色横线，宽度约 5cm 居中——推断值待确认，00-master §4.1）
COVER_SEPARATOR = CoverSeparatorSpec(sz=8, color_hex=COLOR_BLACK, width_cm=5.0, alignment=ALIGN_CENTER)
COVER_SEPARATOR_SPACING_PT = 12.0  # 分隔线上下间距


# ===========================================================================
# 6. 表格规格（04-interface-spec.md §2.6，M4 表头下线/M5 优先级注记）
# ===========================================================================


@dataclass(frozen=True)
class TableBorderSpec:
    """全框线 sz 值表（w:sz 单位=八分之一磅）。

    M5：表头下分隔线（1pt）通过单元格级 tcBorders 覆盖表级 tblBorders.insideH
    （0.5pt）实现，OOXML 中单元格级边框优先级高于表格级——渲染层（render/tables.py，
    未来任务）实现细节，本类只存数值。
    """

    top_sz: int
    bottom_sz: int
    header_bottom_sz: int  # 单元格级 tcBorders，非 tblBorders.insideH
    inside_h_sz: int  # 表级 tblBorders.insideH（非表头下的内部横线）
    inside_v_sz: int
    left_sz: int
    right_sz: int
    color_hex: str


TABLE_BORDERS = TableBorderSpec(
    top_sz=12, bottom_sz=12, header_bottom_sz=8,
    inside_h_sz=4, inside_v_sz=4, left_sz=4, right_sz=4,
    color_hex=COLOR_BLACK,
)
TABLE_WIDTH_RATIO = 0.90  # 可用页宽 × 0.90（04 §2.6）


# ===========================================================================
# 7. 图片规格（04-interface-spec.md §2.7，02-algorithms.md §A.5）
# ===========================================================================

FIGURE_MAX_WIDTH_CM_DEFAULT = 14.0
FIGURE_MAX_WIDTH_CM_RANGE = (8.0, 16.0)  # CLI --figure-max-width-cm 校验范围
FIGURE_MAX_HEIGHT_CM = 20.0  # 防超高溢出版心的安全上限（非 V3.0 条款，本设计新增）
FIGURE_LOW_RES_PX_W_THRESHOLD = 1102  # <此值 → W-IMG-02（14cm 下不足 200dpi）
FIGURE_MED_RES_PX_W_THRESHOLD = 1654  # [1102,1654) → I-IMG-03；>=1654 不警告
FIGURE_PLACEHOLDER_FONT_SIZE_CM = 0.32  # 缺图占位框文字大小 ≈9pt (R1 裁决)


# ===========================================================================
# 8. 结构语义关键词白名单（M8：02-algorithms.md §F.2 全集为唯一权威，逐条注明出处）
# ===========================================================================
# 判别口诀（02 §F.2）：换一份完全不同主题的报告，该字符串是否仍必须出现在代码里？
# 是 → 结构关键词（允许）；否 → 内容硬编码（违规）。

FRONT_BACK_WORDS = ("摘要", "执行摘要", "目录", "图表目录", "参考文献", "索引", "术语表",
                      "前言", "导论", "绪论", "引言")
# 出处：V3.0 §一 文档结构表（结构件名）；02-algorithms.md §C.3 FRONT_BACK_WORDS
# V2.1 扩展：增加"前言/导论/绪论/引言"以支持前言章的正确识别

STRUCT_WORD_FIGURE = "图"  # 出处：02 §A 图三元组解析（图X-Y 前缀）
STRUCT_WORD_TABLE = "表"  # 出处：02 §B 表题注解析（表X-Y 前缀）
STRUCT_WORD_APPENDIX = "附录"  # 出处：V3.0 §一；02 §C.2 N-07
STRUCT_WORD_SOURCE_FULL = "数据来源"  # 出处：02 §B.2 RE_TBL_SOURCE
STRUCT_WORD_SOURCE_SHORT = "来源"  # 出处：同上（"(?:数据)?来源"允许省略"数据"二字）
CHAPTER_MARK_PREFIX = "第"  # 出处：02 §C.2 N-01/N-02
CHAPTER_MARK_SUFFIX = "章"  # 出处：同上
CJK_NUMERALS = "零一二三四五六七八九十百"  # 出处：02 §C.4 int_to_cn/cn_to_int
CJK_NUMERAL_LIANG = "两"  # 出处：02 §C.4 cn_to_int 支持"两"→2 的口语变体

SECRECY_WORDS_STRONG = ("绝密", "机密", "秘密")
# 出处：02 §D.2 R-09强②整行独立密级判定（D13 防御性过滤）

SECRECY_WORDS_WEAK = ("绝密", "机密", "内部资料", "内部参考", "限内部使用", "仅供内部", "密级")
# 出处：02 §D.2 R-09弱 正文扫描列表（D13"检测"半区，不改动仅报告）
# 出处：V2.1 §D.2 R-09弱 上下文感知补充——排除已知技术术语误报（下方假阳性模式表）
SECRECY_FALSE_POSITIVE_PATTERNS = (
    "高度机密",   # "其具体能力仍属高度机密"——军事描述术语，非密级标注
    "跨密级",     # "跨密级数据的安全融合"——技术术语，非密级标注
)

RED_TEAM_MARK_WORD = "红队"  # 出处：02 §D.2 R-06a（D12 新增）
CORRECTED_MARK_WORD = "已修正"  # 出处：02 §D.2 R-06b（D12 新增）
PLACEHOLDER_MARK_WORD = "图表占位"  # 出处：02 §D.2 R-04（历史问题6）
PRINT_HINT_MARK_WORD = "建议印刷页数"  # 出处：02 §D.2 R-05（历史问题7）
END_MARK_WORD = "全文完"  # 出处：02 §D.2 R-10


# ===========================================================================
# 9. 清理与解析用的格式正则模式字符串（供 textstage/assemble 未来任务编译使用）
# ===========================================================================
# 全部为"语法结构 + 正则元字符 + 数字类"构成的格式模式，不含任何具体报告内容
# （反硬编码白名单第3类，02 §F.2）。命名与 ID 对应 02-algorithms.md 原文，供追溯。

# ---- 02 §A 图三元组解析 ----
RE_IMG_LINE = r"^\s*!\[([^\]]*)\]\((.+)\)\s*$"
RE_FIG_ALT = r"^图(\d{1,2})-(\d{1,2})(?:[ 　]+|[：:][ 　]*)(.+)$"

# ---- 02 §B 表题注解析 ----
RE_TBL_CAPTION = r"^\*\*表(\d{1,2})-(\d{1,2})(?:[ 　]+|[：:][ 　]*)(.+?)\*\*$"
RE_TBL_SOURCE_WRAPPER = r"^\*([^*].*)\*$"  # 整段单星斜体外层
RE_TBL_SOURCE_PREFIX = r"^(?:数据)?来源[：:]"  # 内层内容需以"(数据)来源："开头

# ---- 02 §D.3 文档头元数据 ----
RE_META = r"^\*\*([^*：:]{1,10})\*\*\s*[：:]\s*(.+)$"
RE_VERSION_SPLIT = r"^(V[\d.]+)\s*[|｜]\s*(.+)$"

# ---- 02 §C.2 标题编号剥离正则集（N-01~N-07，兼容式） ----
N_01_CHAPTER_CN = r"^第\s*([一二三四五六七八九十百零两]{1,4})\s*章\s*[：:、．.]?\s*"
N_02_CHAPTER_ARABIC = r"^第\s*(\d{1,3})\s*章\s*[：:、．.]?\s*"
N_03_SUBSECTION = (
    r"^(\d{1,2})[.．](\d{1,2})[.．](\d{1,2})[.、]?(?:[ 　]+|(?=[一-鿿（【《“「]))"
)
N_04_SECTION = r"^(\d{1,2})[.．](\d{1,2})[.、]?(?:[ 　]+|(?=[一-鿿（【《“「]))"
N_05_CHAPTER_DUNHAO = r"^(\d{1,3})[.、．]\s*"
N_06_CHAPTER_CN_DUNHAO = r"^([一二三四五六七八九十]{1,3})[、．.]\s*"
N_07_APPENDIX = r"^附录\s*([A-Za-z]|[一二三四五六七八九十]{1,3})?\s*[：:、．.]?\s*"

# M6（00-master-design.md §4.1）：H3 增补单级编号剥离规则、H4 增补二级规则，限定作用域
# 各自仅限所在标题级别使用（assemble/headings.py 未来任务实现时须遵守此限定，命中但
# 形状可疑时报 W-HDR-04，杜绝低层级编号叠加）。
M6_H3_SINGLE_LEVEL = r"^(\d{1,3})[.、．]\s+"  # 限 H3：形似章编号的单级前缀，如"3、背景"
M6_H4_TWO_LEVEL = r"^(\d{1,2})[.．](\d{1,2})[.、]?\s+"  # 限 H4：二级前缀，如"1.2 概述"

# ---- 02 §D.2 清理规则集（R-03~R-11） ----
R_03_HTML_DIV = r"^\s*</?div[^>]*>\s*$"
R_03_HTML_SPAN = r"^\s*</?span[^>]*>\s*$"
R_03_HTML_RESIDUE = r"<[a-zA-Z/][^>]*>"  # 非整行残留，仅报警不删（W-CLN-04）
R_04_PLACEHOLDER = r"^\s*\*{0,2}图表占位\*{0,2}[：:].*$"
R_05_PRINT_HINT = r"^\s*[（(][^（()）]*建议印刷页数[：:]\s*\d+\s*页[）)]\s*$"
R_06A_REDTEAM = r"\s*\[红队\s*R\d{1,4}[^\[\]]*\]"
R_06B_CORRECTED = r"\s*\[已修正[：:][^\[\]]*\]"
R_07_LIST_FIG_PREFIX = r"^(\s*[-*+]\s+)(?=图\d{1,2}-\d{1,2}(?:[：:]|[ 　]))"
R_09_STRONG_FIELD = r"^\*\*密级\*\*\s*[：:].*$"
R_09_STRONG_STANDALONE = r"^\s*[（(【\[]?\s*(绝密|机密|秘密)\s*[】\])）]?\s*$"
R_09_STRONG_INLINE = r"密级\s*[：:]\s*\S{1,12}"
R_09_WEAK_SCAN = r"绝密|(?<!高度)机密|内部资料|内部参考|限内部使用|仅供内部|(?<!跨)密级"
R_10_END_MARK = r"^\s*[（(]?\s*全文完\s*[)）]?\s*$"

# ---- 02 §E 交叉引用一致性校验 ----
RE_REF = r"(图|表)(\d{1,2})-(\d{1,2})"
RE_POS = r"(?<!以)[上下]图|(?<!以)[上下]表"
RE_ORPH = r"^图\d{1,2}-\d{1,2}(?:[：:]|[ 　]).{0,80}$"

# ---- G-11 build_date 归一化（pipeline.py 消费；G1 交叉验证裁决要求集中存放，
#      否则 AST 反硬编码扫描会把 pipeline.py 中散落的中文正则字面量误判为差集违规）----
RE_BUILD_DATE_CN = re.compile(r"^(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?$")
RE_BUILD_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


# ===========================================================================
# 10. 行为开关（BehaviorFlags）
# ===========================================================================


@dataclass
class BehaviorFlags:
    """行为开关集合（00-master-design.md 任务书 config.py 段落逐字段列出）。

    字段默认值即"内置默认"；CLI 参数 > YAML behavior 块 > 此处默认值
    （04-interface-spec.md §3.1 分类表）。
    """

    strict: bool = False
    allow_missing_figures: bool = False
    appendix_page_break: bool = True
    caption_field_mode: str = "text"  # "text" | "field"
    dump_intermediate: bool = False
    figures_dir: str = ""
    figure_max_width_cm: float = FIGURE_MAX_WIDTH_CM_DEFAULT
    table_first_col_left_align: bool = False
    generate_figures_table_toc: str = "auto"  # "auto" | "always" | "never"
    claim_evidence_box: bool = False
    body_alignment: str = "justify"  # "justify" | "left"（04 §2.2 决策说明开关）


# ===========================================================================
# 11. YAML 配置 schema 与加载（04-interface-spec.md §3.2/§3.3，M7 严格校验）
# ===========================================================================

TOP_LEVEL_ALLOWED_KEYS = frozenset({"metadata_defaults", "behavior", "report"})

METADATA_DEFAULTS_ALLOWED_KEYS = frozenset({"organization", "report_type_default", "header_short"})

BEHAVIOR_ALLOWED_KEYS = frozenset(
    {f.name for f in fields(BehaviorFlags)}
)  # 与 BehaviorFlags 字段名保持单一事实来源，避免白名单与 dataclass 字段漂移

REPORT_ALLOWED_KEYS = frozenset({"path"})

_BLOCK_ALLOWED_KEYS = {
    "metadata_defaults": METADATA_DEFAULTS_ALLOWED_KEYS,
    "behavior": BEHAVIOR_ALLOWED_KEYS,
    "report": REPORT_ALLOWED_KEYS,
}

# G1 交叉验证 FAIL-2：behavior 块类型 + 值域校验表（单一事实来源，逐字段声明期望
# 类型/合法取值）。非法值 → ERROR 级 Issue + 该字段从 cleaned 中剔除（不写入，等价
# 于回退到 BehaviorFlags 的 dataclass 默认值——resolve_behavior_flags() 对不存在
# 于 yaml_data 中的字段本就会跳过覆盖）。
BEHAVIOR_BOOL_FIELDS = frozenset(
    {
        "strict",
        "allow_missing_figures",
        "appendix_page_break",
        "dump_intermediate",
        "table_first_col_left_align",
        "claim_evidence_box",
    }
)
BEHAVIOR_ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "caption_field_mode": ("text", "field"),
    "generate_figures_table_toc": ("auto", "always", "never"),
    "body_alignment": ("justify", "left"),
}
BEHAVIOR_STR_FIELDS = frozenset({"figures_dir"})  # 自由文本路径，仅校验类型
BEHAVIOR_FLOAT_RANGE_FIELDS: dict[str, tuple[float, float]] = {
    "figure_max_width_cm": FIGURE_MAX_WIDTH_CM_RANGE,
}


def _validate_behavior_value(key: str, value: object, issues: IssueCollector) -> bool:
    """校验单个 behavior 字段的类型/值域；不合法则产出 ERROR 并返回 False。

    返回 True 表示该字段合法，可写入 cleaned 字典；False 表示该字段应被剔除，
    调用方不得写入 cleaned（回退内置默认值，不中断整体加载流程）。
    """
    if key in BEHAVIOR_BOOL_FIELDS:
        if isinstance(value, bool):
            return True
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-YML-01",
                stage="config",
                message=f"配置字段 'behavior.{key}' 期望布尔类型，实际为 {value!r}"
                "（已忽略，回退内置默认值）",
            )
        )
        return False

    if key in BEHAVIOR_ENUM_FIELDS:
        allowed_values = BEHAVIOR_ENUM_FIELDS[key]
        if isinstance(value, str) and value in allowed_values:
            return True
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-YML-01",
                stage="config",
                message=f"配置字段 'behavior.{key}' 取值 {value!r} 不在允许范围 "
                f"{allowed_values} 内（已忽略，回退内置默认值）",
            )
        )
        return False

    if key in BEHAVIOR_FLOAT_RANGE_FIELDS:
        lo, hi = BEHAVIOR_FLOAT_RANGE_FIELDS[key]
        # bool 是 int 子类，isinstance(True, int) 为 True，须显式排除，否则
        # "figure_max_width_cm: true" 这类明显错误的配置会被误判为合法数字。
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-YML-01",
                    stage="config",
                    message=f"配置字段 'behavior.{key}' 期望数字类型，实际为 {value!r}"
                    "（已忽略，回退内置默认值）",
                )
            )
            return False
        if not (lo <= float(value) <= hi):
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-YML-01",
                    stage="config",
                    message=f"配置字段 'behavior.{key}' 取值 {value} 超出允许范围 "
                    f"[{lo}, {hi}]（已忽略，回退内置默认值）",
                )
            )
            return False
        return True

    if key in BEHAVIOR_STR_FIELDS:
        if isinstance(value, str):
            return True
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-YML-01",
                stage="config",
                message=f"配置字段 'behavior.{key}' 期望字符串类型，实际为 {value!r}"
                "（已忽略，回退内置默认值）",
            )
        )
        return False

    # 不应到达：字段已在上游白名单过滤中确认属于 BEHAVIOR_ALLOWED_KEYS，
    # 若到达此处说明校验表遗漏了该字段（BehaviorFlags 新增字段未同步登记），
    # 保守放行而非拒绝，避免因校验表滞后而误伤合法新字段。
    return True


class ConfigError(Exception):
    """--config 显式指定但文件不存在时抛出（04 §3.3："找不到文件即报参数错误"）。

    由调用方（pipeline.py）捕获并转换为 FATAL/exit 2，不在本模块内部处理退出逻辑
    （config.py 不掌握进程退出方式）。
    """


def _validate_block(
    block_name: str, block_data: dict, issues: IssueCollector
) -> dict:
    """M7：过滤掉块内白名单外字段，逐个产出 ERROR 级 Issue（E-YML-01）。

    G1 交叉验证 FAIL-2：对 "behavior" 块额外做类型/值域校验（_validate_behavior_value），
    非法值同样产出 ERROR 并从 cleaned 中剔除，不中断整体加载流程。
    """
    allowed = _BLOCK_ALLOWED_KEYS[block_name]
    cleaned: dict = {}
    for key, value in block_data.items():
        if key not in allowed:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-YML-01",
                    stage="config",
                    message=f"配置块 '{block_name}' 中的未知字段 '{key}' 已被忽略"
                    "（M7 严格校验：白名单外字段一律拒绝，防止 H-06 内容性数据绕道配置注入）",
                )
            )
            continue
        if block_name == "behavior" and not _validate_behavior_value(key, value, issues):
            continue
        cleaned[key] = value
    return cleaned


def _validate_yaml_schema(data: dict, issues: IssueCollector) -> dict:
    """M7：三块（metadata_defaults/behavior/report）之外的顶层键 → ERROR 并忽略。"""
    if not isinstance(data, dict):
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-YML-01",
                stage="config",
                message="配置文件顶层内容不是映射结构，已整体忽略并回退内置默认值",
            )
        )
        return {}
    cleaned: dict = {}
    for key, value in data.items():
        if key not in TOP_LEVEL_ALLOWED_KEYS:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-YML-01",
                    stage="config",
                    message=f"配置文件顶层未知键 '{key}' 已被忽略"
                    "（仅允许 metadata_defaults/behavior/report 三块，M7）",
                )
            )
            continue
        if not isinstance(value, dict):
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-YML-01",
                    stage="config",
                    message=f"配置块 '{key}' 的内容不是映射结构，已整体忽略",
                )
            )
            continue
        cleaned[key] = _validate_block(key, value, issues)
    return cleaned


def load_yaml_config(
    explicit_path: str | None, md_dir: str, issues: IssueCollector
) -> dict:
    """按 04-interface-spec.md §3.3 查找顺序定位并加载 YAML 配置文件。

    查找顺序：
        1. explicit_path 显式指定（找不到 → 抛 ConfigError，由调用方转为参数错误）
        2. md_dir 同目录的 report.yaml（存在则用）
        3. 均无 → 返回空字典，等价于全部使用内置默认值
           （本实现未额外分发独立的 default_config.yaml 文件——见任务交付说明中的
           解释性决策：BehaviorFlags 的 dataclass 字段默认值已经承担"内置默认"的
           角色，本批次产出文件清单不包含该文件）。

    PyYAML 为延迟 import（仅在确实定位到一个待加载文件时才 import），缺库时产出
    ERROR 并回退空字典。
    """
    path: str | None = None
    if explicit_path:
        if not os.path.isfile(explicit_path):
            raise ConfigError(f"指定的配置文件不存在：{explicit_path}")
        path = explicit_path
    else:
        candidate = os.path.join(md_dir, "report.yaml")
        if os.path.isfile(candidate):
            path = candidate

    if path is None:
        return {}

    try:
        import yaml  # noqa: PLC0415  延迟 import，仅在确需加载 YAML 时才发生
    except ImportError:
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-YML-01",
                stage="config",
                message=f"缺少 PyYAML 库，无法加载配置文件 {path}，已回退内置默认值",
            )
        )
        return {}

    raw = read_bytes(path)
    try:
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except Exception as exc:  # noqa: BLE001  YAML 解析异常种类繁多，统一降级处理
        issues.append(
            Issue(
                level=Level.ERROR,
                code="E-YML-01",
                stage="config",
                message=f"配置文件解析失败：{path}（{exc}），已回退内置默认值",
            )
        )
        return {}

    return _validate_yaml_schema(data, issues)


def resolve_behavior_flags(cli_values: dict, yaml_data: dict) -> BehaviorFlags:
    """按 CLI 参数 > YAML behavior 块 > 内置默认 的优先级合并出最终 BehaviorFlags。

    Args:
        cli_values: 字段名 → 用户显式传入的值；未显式传入的字段应为 None
            （cli.py 中对应 argparse 选项需以 default=None 实现"是否显式传入"的
            三态可辨识性，故意不用 argparse 的隐式 False 默认）。
        yaml_data: load_yaml_config() 校验后的三块字典。
    """
    behavior_yaml = yaml_data.get("behavior", {})
    flags = BehaviorFlags()
    for f in fields(flags):
        cli_v = cli_values.get(f.name)
        if cli_v is not None:
            setattr(flags, f.name, cli_v)
        elif f.name in behavior_yaml:
            setattr(flags, f.name, behavior_yaml[f.name])
    return flags


@dataclass
class MetadataDefaults:
    """YAML metadata_defaults 块的类型化视图（04-interface-spec.md §3.2）。

    供 assemble/metadata.py（未来任务）消费；本文件只负责把已校验的原始字典
    转换为类型化结构，不做优先级降级判断（降级判断需要 md 内容，超出本文件职责）。
    """

    organization: str = ""
    report_type_default: str = ""
    header_short: str = ""


def build_metadata_defaults(yaml_data: dict) -> MetadataDefaults:
    block = yaml_data.get("metadata_defaults", {})
    return replace(MetadataDefaults(), **block) if block else MetadataDefaults()
