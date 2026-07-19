"""
IR（中间表示）数据模型和构建器。

将 AST 元素列表重组为结构化的 DocumentIR，包含：
- 结构化章节（front/body/back）
- 图/表注册表（从 Markdown 提取，数据驱动）
- 文档元数据

原始来源: 设计文档 §3.3 数据模型 + §4.4 IR Builder
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ChapterInfo:
    """章节元数据"""
    number: int                    # 章序号 (1-based)
    cn_number: str                 # 中文数字 ("一")
    title: str                     # 章标题（无编号）
    h2_counter: int = 0            # 节计数器
    h3_counters: Dict[int, int] = field(default_factory=dict)  # {h2_number: h3_counter}
    fig_counter: int = 0           # 图序号计数器
    tbl_counter: int = 0           # 表序号计数器
    fn_counter: int = 0            # 脚注计数器


@dataclass
class ChapterElements:
    """一章的所有元素"""
    chapter: ChapterInfo
    elements: List[Any] = field(default_factory=list)


@dataclass
class FigureMeta:
    """图元数据"""
    id: str                # 图号 "2-1"
    chapter: int           # 所属章号
    seq: int               # 章内序号
    caption: str           # 题注文本
    file_path: str         # 图片文件路径（绝对或相对）
    alt_text: str = ""     # 替代文本


@dataclass
class TableMeta:
    """表元数据"""
    id: str                # 表号 "2-1"
    chapter: int           # 所属章号
    seq: int               # 章内序号
    caption: str           # 题注文本
    header_text: str = ""  # 表头文本（用于降级匹配）
    source_note: str = ""  # 数据来源注释


@dataclass
class FootnoteMeta:
    """脚注元数据"""
    id: int                # 脚注编号（章内）
    chapter: int           # 所属章号
    text: str              # 脚注文本


@dataclass
class DocumentIR:
    """文档中间表示"""
    metadata: Dict[str, str] = field(default_factory=dict)
    front_matter: List[Any] = field(default_factory=list)       # 摘要、目录（不编号）
    body_chapters: List[ChapterElements] = field(default_factory=list)  # 各章内容
    back_matter: List[Any] = field(default_factory=list)         # 参考文献、附录
    figure_registry: Dict[str, FigureMeta] = field(default_factory=dict)  # 图注册表
    table_registry: Dict[str, TableMeta] = field(default_factory=dict)    # 表注册表
    footnotes: List[FootnoteMeta] = field(default_factory=list)  # 脚注列表
    term_index: List[str] = field(default_factory=list)          # 术语索引


# ── 中文数字映射 ──

CN_NUM_MAP = {
    1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
    6: '六', 7: '七', 8: '八', 9: '九', 10: '十',
    11: '十一', 12: '十二', 13: '十三', 14: '十四', 15: '十五',
    16: '十六', 17: '十七', 18: '十八', 19: '十九', 20: '二十',
}

# 扩展到 50 章（通用阿拉伯数字→中文数字转换）
def _num_to_cn(n: int) -> str:
    """阿拉伯数字 → 中文数字（1-99）"""
    if n in CN_NUM_MAP:
        return CN_NUM_MAP[n]
    if n <= 0:
        return str(n)
    if n < 100:
        tens = n // 10
        ones = n % 10
        if ones == 0:
            return f'{CN_NUM_MAP[tens]}十'
        if tens == 1:
            return f'十{CN_NUM_MAP[ones]}'
        return f'{CN_NUM_MAP[tens]}十{CN_NUM_MAP[ones]}'
    return str(n)


# ── 章节边界检测关键词 ──

BACK_MATTER_KEYWORDS = ['参考文献', '附录', '术语表', '索引', '图表索引', '资料清单']


def is_back_matter(text: str) -> bool:
    """判断标题文本是否属于 back matter"""
    return any(kw in text for kw in BACK_MATTER_KEYWORDS)


# ── IR Builder ──

def build_ir(elements: list, metadata: dict) -> DocumentIR:
    """将 AST 元素列表重组为结构化 DocumentIR。

    算法：
    1. 遍历元素，根据 H1/H2 标题判断 front/body/back 状态
    2. 第一个非 front/back 的 H1 → 进入 body 状态
    3. 遇到 back matter 关键词的标题 → 进入 back 状态
    4. 在 body 状态下，遇到 H1 创建新 ChapterInfo
    5. 提取图/表元数据注册到 figure_registry/table_registry

    Args:
        elements: parser.parse_markdown() 产出的 AST 元素列表
        metadata: 文档元数据 dict

    Returns:
        DocumentIR 实例
    """
    # 避免循环导入
    from .parser import Heading, Paragraph, ImageElement, TableElement, ListItem
    from .parser import extract_figure_meta, extract_table_caption

    ir = DocumentIR(metadata=metadata)
    current_chapter = None
    current_elements = ir.front_matter
    state = "front"  # front | body | back
    found_first_h1 = False

    # 章节计数器
    ch_counter = 0
    fig_counter = {}
    tbl_counter = {}

    for elem in elements:
        # --- 处理 Heading ---
        if isinstance(elem, Heading):
            text = elem.text if hasattr(elem, 'text') else str(elem)

            if elem.level == 1:
                if not found_first_h1:
                    # 第一个 H1 是封面标题（跳过，不加入任何 section）
                    found_first_h1 = True
                    continue

                if state == "front" and not is_back_matter(text):
                    # 第一个非 front/back 的 H1 → 进入正文
                    state = "body"
                    ch_counter += 1
                    cn = _num_to_cn(ch_counter)
                    current_chapter = ChapterInfo(
                        number=ch_counter,
                        cn_number=cn,
                        title=text
                    )
                    fig_counter[ch_counter] = 0
                    tbl_counter[ch_counter] = 0
                    chapter_elements = ChapterElements(chapter=current_chapter)
                    ir.body_chapters.append(chapter_elements)
                    current_elements = chapter_elements.elements
                    continue
                elif is_back_matter(text):
                    state = "back"
                    current_chapter = None
                    current_elements = ir.back_matter
                    continue
                elif state == "body":
                    # 新一章
                    ch_counter += 1
                    cn = _num_to_cn(ch_counter)
                    current_chapter = ChapterInfo(
                        number=ch_counter,
                        cn_number=cn,
                        title=text
                    )
                    fig_counter[ch_counter] = 0
                    tbl_counter[ch_counter] = 0
                    chapter_elements = ChapterElements(chapter=current_chapter)
                    ir.body_chapters.append(chapter_elements)
                    current_elements = chapter_elements.elements
                    continue

            current_elements.append(elem)
            continue

        # --- 提取图元数据 ---
        if isinstance(elem, ImageElement) and current_chapter:
            ch = current_chapter.number
            fig_counter.setdefault(ch, 0)
            fig_counter[ch] += 1
            meta = extract_figure_meta(elem.alt_text, ch, fig_counter[ch])
            if meta:
                fig = FigureMeta(
                    id=meta['id'],
                    chapter=ch,
                    seq=meta['seq'],
                    caption=meta['caption'],
                    file_path=elem.url,
                    alt_text=elem.alt_text
                )
                ir.figure_registry[fig.id] = fig

        # --- 提取表元数据 ---
        if isinstance(elem, TableElement) and current_chapter:
            ch = current_chapter.number
            tbl_counter.setdefault(ch, 0)
            tbl_counter[ch] += 1
            # 表题注由调用方在构建时传入，这里先占位
            tbl = TableMeta(
                id=f'{ch}-{tbl_counter[ch]}',
                chapter=ch,
                seq=tbl_counter[ch],
                caption='',
                header_text=' | '.join(elem.header)
            )
            ir.table_registry[tbl.id] = tbl

        current_elements.append(elem)

    return ir


def resolve_table_captions(ir: DocumentIR, pending_captions: Dict[int, str] = None) -> DocumentIR:
    """将解析阶段收集的表题注关联到 table_registry。

    遍历 IR 中的表，用 pending_captions（{表在body中的序号: caption}）填充 TableMeta.caption。

    Args:
        ir: DocumentIR 实例
        pending_captions: {表序号: 题注文本} 映射

    Returns:
        更新后的 DocumentIR（原地修改）
    """
    if not pending_captions:
        return ir

    tbl_list = list(ir.table_registry.values())
    for i, tbl in enumerate(tbl_list):
        if i in pending_captions:
            tbl.caption = pending_captions[i]

    return ir
