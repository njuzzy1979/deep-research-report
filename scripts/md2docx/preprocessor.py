"""
Markdown 预处理模块。

从原始 Markdown 文档到清洗后的行列表 + 元数据的完整管道。
功能：二进制安全读取、编码规范化、清理、YAML front matter 提取、章节边界检测与分页标记插入。

原始来源：scripts/markdown_to_docx.py L172-251（clean_markdown 函数）
"""

import re
import os
from typing import List, Tuple, Optional, Dict, Any

# ───────────────────────────────────────────────────────
# 正则表达式（从旧脚本 scripts/markdown_to_docx.py L176-187 直接搬移）
# ───────────────────────────────────────────────────────

# 中文数字字符集（供 RE_PAGE / RE_H1_CH 使用）
CN_NUMS = r'一二三四五六七八九十'
CN = r'[' + CN_NUMS + r']+'

RE_HTML    = re.compile(r"^<div\s+style=['\"]page-break-before:\s*always;?['\"]>\s*</div>\s*$", re.I)
RE_CHART   = re.compile(r'\*{0,2}图表占位\*{0,2}[：:]\s*')
RE_PAGE    = re.compile(r'^[（(](?:第' + CN + r'章完|摘要完)[，,]建议印刷页数[：:]\s*\d+\s*页[）)]\s*$')
RE_TOC     = re.compile(r'[（(]在Word/WPS')
RE_META    = re.compile(r'^\*\*(?:版本|日期|定位|规模|核心问题)\*\*[：:].*$')
RE_FULL    = re.compile(r'^\*《中国商业空间态势感知领域深度分析报告》全文完\*\s*$')
RE_H1_CH   = re.compile(r'^(#\s+)第' + CN + r'章[：:]\s*')
RE_H2_SEC  = re.compile(r'^(##\s+)\d+\.\d+\s+')
RE_H3_SUB  = re.compile(r'^(###\s+)\d+\.\d+\.\d+\s+')
RE_TBL_REF = re.compile(r'^表\s*\d+[-−]\s*\d+[：:]')
RE_LIST_FIG = re.compile(r'^[-*]\s+(图\s*\d+[-−]\s*\d+[：:].*)$')
RE_COVER  = re.compile(r'^\*\*China.+Deep-Dive Analysis\*\*\s*$')

# 通用 H1 检测正则
RE_H1 = re.compile(r'^#\s+(.+)')


# ───────────────────────────────────────────────────────
# 章节边界检测关键词
# 与 ir.py 的 BACK_MATTER_KEYWORDS 保持一致
# ───────────────────────────────────────────────────────

FRONT_MATTER_KEYWORDS = ['摘要', '目录', '前言', '序言', '导言', '声明']

BACK_MATTER_KEYWORDS = [
    '参考文献', '参考书目', '附录', '术语表', '术语', '索引',
    '图表索引', '资料清单', '证据等级',
]


# ───────────────────────────────────────────────────────
# 步骤函数
# ───────────────────────────────────────────────────────

def _binary_read(input_path: str) -> str:
    """二进制安全读取文件，剥离 BOM，统一行尾为 LF。

    Args:
        input_path: 输入文件路径

    Returns:
        UTF-8 解码后的文本内容
    """
    with open(input_path, 'rb') as f:
        raw = f.read()

    # 剥离 UTF-8 BOM
    if raw[:3] == b'\xef\xbb\xbf':
        raw = raw[3:]

    # 统一行尾：CRLF → LF, CR → LF
    raw = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')

    return raw.decode('utf-8')


def _clean_content(lines: List[str]) -> List[str]:
    """清理行列表：删除 HTML/图表占位符/印刷页数/元数据行，剥离手动编号。

    原始来源：clean_markdown() 中的逐行清理逻辑（L198-216）

    Args:
        lines: 预处理后的行列表

    Returns:
        清理后的行列表
    """
    out = []
    for line in lines:
        s = line.strip()

        # 删除 HTML div 分页标签
        if RE_HTML.match(s):
            continue

        # 删除印刷页数建议行
        if RE_PAGE.match(s) or re.match(r'^[（(]摘要完', s):
            continue

        # 删除 TOC 指示文字
        if RE_TOC.search(line):
            continue

        # 删除封面元数据行（**版本**:**日期** 等）
        if RE_META.match(s):
            continue

        # 删除"全文完"标记
        if RE_FULL.match(s):
            continue

        # 剥离图表占位符前缀
        if '图表占位' in line:
            line = RE_CHART.sub('', line)

        # 列表图引用剥离：`- 图X-Y: ...` → `图X-Y: ...`
        m = RE_LIST_FIG.match(line)
        if m:
            line = m.group(1)

        # 剥离手动标题编号（H1: 第X章、H2: X.X、H3: X.X.X）
        m = RE_H1_CH.match(line)
        if m:
            line = m.group(1) + line[m.end():]

        m = RE_H2_SEC.match(line)
        if m:
            line = m.group(1) + line[m.end():]

        m = RE_H3_SUB.match(line)
        if m:
            line = m.group(1) + line[m.end():]

        out.append(line)

    return out


def _remove_orphan_table_refs(lines: List[str]) -> List[str]:
    """删除孤立表引用行（后面没有实际表格的表引用）。

    原始来源：clean_markdown() L218-226

    算法：
    对于每个匹配 RE_TBL_REF 的行，检查后续 3 行内是否有表格行（以 | 开头和结尾）。
    如果没有，则认为是孤立引用，将其删除。

    Args:
        lines: 清理后的行列表

    Returns:
        删除孤立表引用后的行列表
    """
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if RE_TBL_REF.match(line.strip()):
            # 检查后续 3 行内是否有表格行
            has_table = any(
                lines[j].strip().startswith('|') and lines[j].strip().endswith('|')
                for j in range(i + 1, min(i + 4, len(lines)))
            )
            if not has_table:
                i += 1
                continue
        out.append(line)
        i += 1
    return out


def _fix_heading_levels(lines: List[str]) -> List[str]:
    """修正标题层级：英文副标题 → H2，目录 → H1，摘要 → H2。

    原始来源：clean_markdown() L228-235

    Args:
        lines: 清理后的行列表

    Returns:
        修正标题层级后的行列表
    """
    result = list(lines)  # 不修改原列表

    # 英文副标题 → H2
    for j, ln in enumerate(result):
        if RE_COVER.match(ln.strip()):
            result[j] = '## ' + ln.strip().strip('*')
            break

    # 目录 → H1, 摘要 → H2
    for j, ln in enumerate(result):
        if ln.strip() == '## 目录':
            result[j] = '# 目录'
        elif ln.strip() == '# 摘要':
            result[j] = '## 摘要'

    return result


def _remove_separators(lines: List[str]) -> List[str]:
    """删除所有独立的 `---` 分隔线行。

    原始来源：clean_markdown() L236-237

    Args:
        lines: 行列表

    Returns:
        删除 --- 行后的列表
    """
    return [ln for ln in lines if ln.strip() != '---']


def _insert_page_breaks(lines: List[str]) -> List[str]:
    """自动检测章节边界并插入 `---` 分页标记。

    设计文档 §5.1：分页标记插入算法
    - 在 first body chapter 的 H1 前插入 `---`
    - 在 first back matter 的 H1 前插入 `---`
    - 在 front matter 中的"目录"H1 前后各插入 `---`

    与旧脚本的区别：
    - 不再使用硬编码 CHAPTER_TITLES 列表
    - 改为扫描所有 H1 标题，通过关键词自动判断 front/body/back 边界

    Args:
        lines: 标题层级已修正的行列表

    Returns:
        插入分页标记后的行列表
    """
    # 收集所有 H1 行的 (索引, 清理后的标题文本)
    h1_entries: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = RE_H1.match(ln)
        if m:
            h1_entries.append((i, m.group(1).strip()))

    if not h1_entries:
        return list(lines)

    # 跳过第一个 H1 — 按项目约定，它始终是封面标题（见 ir.py build_ir 中
    # `if not found_first_h1: ... continue` 的处理），不应参与章节边界检测
    h1_start = 1 if len(h1_entries) > 1 else len(h1_entries)

    insertion_points: List[int] = []
    first_body_idx: Optional[int] = None
    first_back_idx: Optional[int] = None

    for i, text in h1_entries[h1_start:]:
        # 检测"目录"H1 — 在其前后插入分页标记
        if '目录' in text:
            insertion_points.append(i)       # 目录行之前
            insertion_points.append(i + 1)   # 目录行之后

        # 分类章节
        if any(kw in text for kw in FRONT_MATTER_KEYWORDS):
            continue  # front matter，不需要分页标记（目录已单独处理）
        elif any(kw in text for kw in BACK_MATTER_KEYWORDS):
            if first_back_idx is None:
                first_back_idx = i
        else:
            # body chapter
            if first_body_idx is None:
                first_body_idx = i

    # 在第一个 body chapter 前插入分页标记
    if first_body_idx is not None:
        insertion_points.append(first_body_idx)

    # 在第一个 back matter 前插入分页标记
    if first_back_idx is not None:
        insertion_points.append(first_back_idx)

    # 去重后降序插入（保证索引稳定）
    result = list(lines)
    for idx in sorted(set(insertion_points), reverse=True):
        result.insert(idx, '---')

    return result


# ───────────────────────────────────────────────────────
# YAML Front Matter 提取
# ───────────────────────────────────────────────────────

def extract_front_matter(lines: List[str]) -> Tuple[Optional[dict], List[str]]:
    """从行列表中提取 YAML front matter。

    YAML front matter 格式：
        ---
        title: "报告标题"
        subtitle: "英文副标题"
        org: "机构名称"
        date: "2024-01-01"
        version: "V1.0"
        header_short: "简称"
        ---

    解析策略：
    1. 优先使用 PyYAML 解析
    2. 如果 PyYAML 不可用，使用简单的 key: "value" 正则解析

    支持的字段：title, subtitle, org, date, version, header_short

    Args:
        lines: 原始行列表

    Returns:
        (metadata_dict, remaining_lines)
        - metadata_dict: 解析出的元数据，如果无 front matter 则为 None
        - remaining_lines: 去除 front matter 后的剩余行
    """
    if len(lines) < 3:
        return None, lines

    # 检测开头是否有 `---`
    if lines[0].strip() != '---':
        return None, lines

    # 查找结束的 `---`
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        # 没有找到结束标记，不是有效的 front matter
        return None, lines

    # 提取 YAML 内容行
    yaml_lines = lines[1:end_idx]
    yaml_text = '\n'.join(yaml_lines)

    # 尝试 PyYAML 解析
    metadata = _parse_yaml_with_pyyaml(yaml_text)
    if metadata is None:
        # 降级：简单正则解析
        metadata = _parse_yaml_simple(yaml_text)

    # 返回元数据和剩余行
    remaining = lines[end_idx + 1:]
    return metadata, remaining


def _parse_yaml_with_pyyaml(yaml_text: str) -> Optional[dict]:
    """尝试用 PyYAML 解析 YAML 文本。

    Args:
        yaml_text: YAML 文本字符串

    Returns:
        解析出的 dict，如果 PyYAML 不可用或解析失败则返回 None
    """
    try:
        import yaml
        result = yaml.safe_load(yaml_text)
        if isinstance(result, dict):
            return {k: str(v) if v is not None else '' for k, v in result.items()}
        return None
    except ImportError:
        return None
    except Exception:
        return None


def _parse_yaml_simple(yaml_text: str) -> dict:
    """简单的 key: "value" 正则解析（PyYAML 不可用时的降级方案）。

    支持的格式：
        key: "value"
        key: 'value'
        key: value

    Args:
        yaml_text: YAML 文本字符串

    Returns:
        解析出的 dict
    """
    metadata: Dict[str, str] = {}
    # 匹配 key: "value" 或 key: 'value' 或 key: value
    pattern = re.compile(r'^(\w+)\s*:\s*["\']?(.*?)["\']?\s*$')

    for line in yaml_text.split('\n'):
        m = pattern.match(line)
        if m:
            key = m.group(1)
            value = m.group(2)
            metadata[key] = value

    return metadata if metadata else {}


# ───────────────────────────────────────────────────────
# 预处理管道
# ───────────────────────────────────────────────────────

def preprocess(input_path: str, config: Any = None) -> Tuple[List[str], dict]:
    """完整预处理管道。

    将原始 Markdown 文件处理为清洗后的行列表 + 文档元数据。

    管道步骤：
    1. 二进制安全读取 + BOM 剥离 + 行尾规范化
    2. YAML front matter 提取（如果存在）
    3. 内容清理（HTML div、图表占位符、印刷页数、元数据行等）
    4. 手动标题编号剥离
    5. 列表图引用剥离
    6. 孤立表引用删除
    7. 英文副标题 → H2，目录 → H1，摘要 → H2
    8. 删除所有 --- 分隔线
    9. 章节边界检测 + --- 分页标记插入

    Args:
        input_path: 输入 Markdown 文件路径
        config: 可选配置对象（暂未使用，保留接口）

    Returns:
        (lines, metadata) — 清理后的文本行列表 + 元数据 dict

    Example:
        >>> lines, meta = preprocess('report.md')
        >>> len(lines) > 0
        True
        >>> isinstance(meta, dict)
        True
    """
    # 1. 二进制安全读取
    text = _binary_read(input_path)
    lines = text.split('\n')

    # 2. 提取 YAML front matter
    metadata, lines = extract_front_matter(lines)
    if metadata is None:
        metadata = {}

    # 3-5. 内容清理 + 手动编号剥离 + 列表图引用剥离
    lines = _clean_content(lines)

    # 6. 删除孤立表引用
    lines = _remove_orphan_table_refs(lines)

    # 7. 修正标题层级
    lines = _fix_heading_levels(lines)

    # 8. 删除所有 --- 分隔线
    lines = _remove_separators(lines)

    # 9. 章节边界检测 + 插入分页标记
    lines = _insert_page_breaks(lines)

    return lines, metadata
