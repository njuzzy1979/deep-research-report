"""IR（中间表示）dataclass 全集（C-03）。

纯数据、零逻辑（01-architecture.md §4.1 设计原则）：本文件只包含 dataclass 与
Enum 定义，不 import 本包任何其他模块，不含任何计算/校验/解析函数。

H-05 硬约束：内容性字段（题注、路径、标题文本、编号等）一律无默认值，构造时
必须由 assemble/*（未来任务）从文档解析结果显式传入——这使"硬编码兜底"在
schema 层面没有安放位置。唯一例外是 InlineRun 的纯格式布尔字段（bold/italic/
code/superscript）与 link_url：H-05 只约束"内容性"字段，不约束格式开关本身
（00-master-design.md 任务说明已明确此边界）。

V-05 说明：textstage/* 与 render/*（均为未来任务）都会 import 本文件，这不违反
"两域互不 import"的架构红线——V-05 禁止的是 textstage 与 render 互相 import
对方，二者各自 import 纯数据的 ir.py 是允许的（ir.py 不属于任何一侧）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# 行内格式（textstage/inline.py 产出，render/paragraphs.py 消费）
# ---------------------------------------------------------------------------


@dataclass
class InlineRun:
    """行内文本片段。

    text 为内容性字段，构造时必须显式提供；bold/italic/code/superscript/
    link_url 是纯格式开关，允许默认值（H-05 边界说明见模块 docstring）。
    """

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    superscript: bool = False
    link_url: str | None = None


# ---------------------------------------------------------------------------
# 标题
# ---------------------------------------------------------------------------


class HeadingKind(Enum):
    """标题语义分类（01-architecture.md §4.3）。"""

    MAIN_TITLE = "main_title"  # md H1 唯一 → 封面标题（不渲染为正文标题）
    ABSTRACT = "abstract"  # "摘要"/"执行摘要" H2 → 无编号，罗马页码节
    FRONT_MATTER = "front_matter"  # 前言/导论章内的 H2/H3 → 不参与正文编号（V2.1 新增）
    CHAPTER = "chapter"  # 正文章 H2 → "第X章"（中文数字）
    SECTION = "section"  # H3 → "X.Y"
    SUBSECTION = "subsection"  # H4 → "X.Y.Z"（样本 0 处，规范支持）
    APPENDIX = "appendix"  # "附录X：" H2 → 字母编号
    PLAIN = "plain"  # 段落小标题（不编号不入目录）


# 结构化编号的联合类型：章=int｜节=(章,节)｜小节=(章,节,小节)｜附录=字母 str｜无编号=None
# （01-architecture.md §4.3 HeadingIR.number 字段原始表述）
HeadingNumber = int | tuple[int, int] | tuple[int, int, int] | str | None


@dataclass
class HeadingIR:
    kind: HeadingKind
    raw_text: str  # 剥离前原文（报告/审计用）
    text: str  # 剥离编号后的纯标题文字
    number: HeadingNumber  # 结构化编号，供连续性校验；无编号或解析失败为 None
    display_number: str  # 渲染文本："第三章" / "3.1" / "附录A" / ""（Assembler 算好，Renderer 只拼接）
    source_line: int


# ---------------------------------------------------------------------------
# 段落 / 列表 / 引用块（防御性）
# ---------------------------------------------------------------------------


@dataclass
class ParagraphIR:
    runs: list[InlineRun]
    source_line: int


@dataclass
class ListBlockIR:
    ordered: bool
    items: list[list[InlineRun]]  # 样本仅 1 级，schema 不设嵌套（防御：嵌套输入降级平铺+WARNING）
    source_line: int


@dataclass
class QuoteIR:
    """引用块（`>` 语法防御性支持；样本 0 处触发，04-interface-spec.md §2.9）。"""

    runs: list[InlineRun]
    source_line: int


# ---------------------------------------------------------------------------
# 图（FigureAssembler 产出，D1 三元组 100% 动态解析）
# ---------------------------------------------------------------------------


@dataclass
class FigureIR:
    figure_id: str  # "1-1"（来自 alt 正则捕获组）
    chapter_no: int  # 1
    seq_no: int  # 1
    caption_text: str  # 图号后空格分隔的剩余全文；标题内部冒号原样保留
    alt_raw: str  # 完整 alt 原文（审计用）
    path_raw: str  # md 中的原始相对路径
    path_resolved: str  # 以 md 文件所在目录为基准解析出的绝对路径
    file_exists: bool  # 阶段3 探测结果
    bookmark_name: str  # "fig_1_1"；用途见下方注释（04-interface-spec.md §6 修订）
    px_w: int | None  # R13：PNG IHDR 头解析得到的像素宽；不可用时为 None
    px_h: int | None  # R13：同上，像素高
    source_line: int
    # 注意：无"目标尺寸"字段——宽度是渲染策略（config.figure_max_width_cm），不是
    # 文档数据；px_w/px_h 是"解析得到的原始像素事实"，与目标尺寸是两个不同概念
    # （R13 裁决明确区分，00-master-design.md §4 R13 行）。
    # bookmark_name 用途（04-interface-spec.md §6 修订注释）：
    #   Tier1 下消费，仅供图表目录 PAGEREF；Tier2 下额外供正文 REF。


# ---------------------------------------------------------------------------
# 表（TableAssembler 产出，D1 邻接语法关联）
# ---------------------------------------------------------------------------


class TableKind(Enum):
    BODY = "body"  # 正文表：有 **表X-Y** 题注行（数据来源行可有可无）
    APPENDIX = "appendix"  # 附录表：无题注行、无来源行（两类惯例之一，非错误）


@dataclass
class TableIR:
    kind: TableKind
    table_id: str | None  # "2-1"；附录表为 None
    caption_text: str | None  # 题注行剥离 "表X-Y " 前缀后的标题；附录表 None
    source_note: list[InlineRun] | None  # M9：改为 list[InlineRun]（承载未来 [来源](URL) 链接语法）
    header_cells: list[list[InlineRun]]
    body_rows: list[list[list[InlineRun]]]
    n_cols: int
    bookmark_name: str | None  # 用途见下方注释（04-interface-spec.md §6 修订）
    source_line: int
    # bookmark_name 用途（04-interface-spec.md §6 修订注释）：
    #   Tier1 下消费，仅供图表目录 PAGEREF；Tier2 下额外供正文 REF。


# ---------------------------------------------------------------------------
# 分页（breaks.py 唯一生成点消费的 IR 元素，D5/N1）
# ---------------------------------------------------------------------------


class BreakOrigin(Enum):
    EXPLICIT_HR = "explicit_hr"  # 来自文档中的 ---
    AUTO_APPENDIX = "auto_appendix"  # 附录 H2 边界自动补插（R14/R18 前置条件）
    AUTO_TOC = "auto_toc"  # M1："目录→图表目录"换页，breaks.py 规划
    AUTO_RULE = "auto_rule"  # 其他规则补插（保留枚举位）


@dataclass
class PageBreakIR:
    origin: BreakOrigin  # 报告中区分"文档自带 / 自动补插"来源
    source_line: int | None


# ---------------------------------------------------------------------------
# 分节规划（breaks.py 产出，headerfooter/document 消费；04-interface-spec.md §2.4 I1）
# ---------------------------------------------------------------------------


class SectionKind(Enum):
    """04-interface-spec.md §2.4 I1：四节方案（架构默认三节草案的回填细化）。"""

    COVER = "cover"
    ABSTRACT = "abstract"
    TOC = "toc"  # 含目录 + 图表目录（若生成）
    BODY = "body"  # 正文各章 + 附录


class PageNumFormat(Enum):
    NONE = "none"
    LOWER_ROMAN = "lowerRoman"
    DECIMAL = "decimal"


class HeaderMode(Enum):
    NONE = "none"
    TITLE_SHORT = "title_short"


@dataclass
class SectionSpec:
    kind: SectionKind
    page_num_fmt: PageNumFormat
    page_num_restart: bool
    header_mode: HeaderMode
    start_element_index: int  # 该节在 DocumentIR.elements 中的起始索引


@dataclass
class SectionPlan:
    """breaks.py（未来任务）产出。

    默认四节：COVER（无页眉脚）/ ABSTRACT（有页眉，罗马页码 start=1）/
    TOC（无页眉，罗马页码续接）/ BODY（有页眉，阿拉伯页码 start=1）。

    M9 无摘要降级规则：若文档中不存在 ABSTRACT 类 H2（HeadingKind.ABSTRACT），
    则退化为三节方案（COVER/TOC/BODY），此时前置罗马页码节（TOC）仅含目录本身
    （不含摘要正文）。本 dataclass 只是数据容器，三节/四节的具体判定逻辑由
    assemble/breaks.py（未来任务）实现，此处不作数据驱动之外的假设。
    """

    sections: list[SectionSpec]


# ---------------------------------------------------------------------------
# 交叉引用登记（阶段3 从段落文本登记，阶段4 消费，只读校验用）
# ---------------------------------------------------------------------------


@dataclass
class XRefMention:
    ref_id: str  # "图1-1" / "表4-1"
    ref_type: str  # "figure" | "table"
    mention_line: int
    style: str  # "paren"（图X-Y） | "asshown"（如图X-Y所示） | "positional"（下图/上表, 违规）


# ---------------------------------------------------------------------------
# 文档头元数据
# ---------------------------------------------------------------------------


@dataclass
class MetadataIR:
    title: str  # H1 文本；md 无 H1 是 FATAL 场景，故此字段构造时必然非空
    subtitle: str | None
    report_type: str | None
    organization: str | None
    version_raw: str | None  # "V1.0 | 2026年7月"
    version: str | None  # "V1.0"（二次拆分）
    date: str | None  # "2026年7月"（二次拆分，允许 None——无独立日期字段是实测事实）
    title_short: str | None  # 页眉简称（来源策略从 metadata/配置取，不硬编码）


# ---------------------------------------------------------------------------
# 顶层文档结构
# ---------------------------------------------------------------------------

# 有序正文元素流的成员类型（01-architecture.md §4.3："不存在 HorizontalRule 类型"——
# `---` 在阶段3 已被 breaks.py 消费为 PageBreakIR，渲染器分派字典中没有 HR 分支）。
BlockIR = HeadingIR | ParagraphIR | FigureIR | TableIR | ListBlockIR | PageBreakIR | QuoteIR


@dataclass
class DocumentIR:
    metadata: MetadataIR  # 文档头元数据（供封面/页眉简称）
    elements: list[BlockIR]  # 有序正文元素流（含 PageBreakIR）
    section_plan: SectionPlan  # 分节规划（breaks.py 产出）
    figure_registry: dict[str, FigureIR]  # "1-1" → FigureIR（校验用索引，与 elements 同对象引用）
    table_registry: dict[str, TableIR]  # "2-1" → TableIR（仅含有编号的正文表）
    xref_registry: list[XRefMention]  # 正文图表提及登记（先文后图检测用）
