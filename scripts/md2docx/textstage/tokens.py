"""阶段2 块解析产出的 Token 类型定义。

纯数据、零逻辑（与 ir.py 风格一致）：本文件只包含 dataclass 与类型别名，
不 import 本包任何其他模块，不含任何计算/校验/解析函数。

parse.py（未来任务）产出行内已解析的 Token 列表，assemble/*（未来任务）
消费这些 Token 组装为 IR。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..ir import InlineRun


# ---------------------------------------------------------------------------
# 块级 Token 类型
# ---------------------------------------------------------------------------


@dataclass
class MetaLine:
    """文档头元数据行：**字段名**：值。

    仅出现在文档开头、第一个非空白非元数据行之前。
    例：**副标题**：中国城市轨道交通...
    """

    key: str  # 字段名（不含 ** 标记），如 "副标题"
    value: str  # 字段值，如 "中国城市轨道交通..."
    source_line: int


@dataclass
class HeadingToken:
    """ATX 标题行：## 摘要 / ### 1.1 背景。

    raw_text 已剥离前导 # 和首尾空白，保留内部行内语法标记供后续解析。
    """

    level: int  # 1-6（H1-H6）
    raw_text: str  # 剥离前导 # 和首尾空白后的文本
    source_line: int


@dataclass
class ParagraphToken:
    """普通段落（行内已解析为 InlineRun 列表）。"""

    runs: list[InlineRun]
    source_line: int


@dataclass
class TableRowToken:
    """管道表格的一行（| cell | cell |）。

    cells 为 list[list[InlineRun]]，每个 cell 内的行内已解析。
    分隔行（|---|---|）由 parse.py 识别为分隔标记，不产 TableRowToken。
    """

    cells: list[list[InlineRun]]  # 每个 cell 的行内已解析
    source_line: int


@dataclass
class ImageToken:
    """图片行：![alt](path)。"""

    alt_raw: str  # 完整 alt 原文（含图号等，供图题注解析）
    path_raw: str  # 完整 path 原文（未解析，供图片定位）
    source_line: int


@dataclass
class HrToken:
    """水平分隔线：--- 或 ***。

    阶段3 由 breaks.py（未来任务）消费为 PageBreakIR，不直接渲染。
    """

    source_line: int


@dataclass
class OrderedItemToken:
    """有序列表项：1. 文本。"""

    runs: list[InlineRun]
    source_line: int


@dataclass
class UnorderedItemToken:
    """无序列表项：- 文本。"""

    runs: list[InlineRun]
    source_line: int


@dataclass
class BlankToken:
    """空行（块化后消失，仅作状态机标记）。

    parse.py 的状态机在处理空行时切换状态；assemble 阶段不再消费 BlankToken。
    """

    source_line: int


@dataclass
class QuoteToken:
    """引用块：> 文本（防御性支持，样本 0 处）。"""

    runs: list[InlineRun]
    source_line: int


@dataclass
class FencedCodeToken:
    """围栏代码块：```...```（防御性支持）。

    lines 为代码块内原始行（不解析行内格式）。
    """

    lang: str | None  # 语言标识（```python → "python"）；无标识时为 None
    lines: list[str]  # 代码块内原始行
    start_line: int  # 起始 ``` 所在行号
    end_line: int  # 结束 ``` 所在行号


# ---------------------------------------------------------------------------
# 联合类型别名（供 parse.py / assemble 使用）
# ---------------------------------------------------------------------------

Token = (
    MetaLine
    | HeadingToken
    | ParagraphToken
    | TableRowToken
    | ImageToken
    | HrToken
    | OrderedItemToken
    | UnorderedItemToken
    | BlankToken
    | QuoteToken
    | FencedCodeToken
)
