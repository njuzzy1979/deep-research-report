# Markdown → Word (.docx) 格式转换引擎设计文档

> 版本：V1.0  
> 日期：2026-07-19  
> 设计编排器产出  
> 上游技能：deep-research-report (阶段 9：定稿整合)  
> 设计依据：研究报告格式规范 V3.0 + md-to-docx-pitfalls.md + markdown_to_docx.py 源码审查

---

## 目录

1. [设计概述](#1-设计概述)
2. [格式规范审查](#2-格式规范审查)
3. [架构设计](#3-架构设计)
4. [模块详细设计](#4-模块详细设计)
5. [关键算法设计](#5-关键算法设计)
6. [格式合规对照表](#6-格式合规对照表)
7. [Markdown 源文件约定规范](#7-markdown-源文件约定规范)
8. [配置化方案](#8-配置化方案)
9. [实现优先级与工作量估算](#9-实现优先级与工作量估算)
10. [改动清单](#10-改动清单)
11. [分布式要求登记表](#11-分布式要求登记表)
12. [已知限制与风险](#12-已知限制与风险)

---

## 1. 设计概述

### 1.1 设计目标

将任意符合约定的 Markdown 研究报告，自动转换为严格遵循《研究报告格式规范 V3.0》的 Word (.docx) 文档。

### 1.2 设计范围

- **输入**：符合约定的 Markdown 文件 + 配置参数 + 图片资源目录
- **输出**：格式合规的 .docx 文件
- **核心约束**：零硬编码、完全可配置、逐条对标格式规范 11 章

### 1.3 当前状态评估

| 维度 | 状态 | 评分 |
|------|------|------|
| 基本转换（标题/正文/表格） | 可用，质量高 | 7/10 |
| 字体方案（中英混排） | 基本正确，有修复 | 7/10 |
| TOC 域代码 | 结构正确，功能可用 | 8/10 |
| 表格渲染 | 全框线+交替行灰底已实现 | 8/10 |
| 通用性 | 严重硬编码 | 2/10 |
| 分节/页码切换 | 完全缺失 | 0/10 |
| 特殊元素 | 仅表格和图 | 3/10 |
| 参考文献 | 基本未处理 | 1/10 |
| 交叉引用 | 未实现 | 0/10 |

### 1.4 设计原则

1. **配置驱动**：所有可变参数（字体、字号、间距、颜色、机构名、元数据字段）从配置文件读取，不在代码中硬编码
2. **数据驱动**：图表编号和题注由 Markdown 源文档驱动，不依赖硬编码映射表
3. **管道可拆分**：预处理 → 解析 → 构建 → 后处理 四阶段可独立运行和调试
4. **保留精华**：当前脚本的表格边框控制、中英文字体混合设置、二进制安全管道等已验证逻辑应保留重用
5. **规范对标**：每个模块能追溯到格式规范的具体条款

---

## 2. 格式规范审查

逐条审查 V3.0 规范，标记问题并提供修正建议。

### 2.1 规范本身的问题

#### P0-1. 正文字号表述歧义（§3.3 正文样式表）

**问题**：表格中"正文"行写 `五号(10.5pt)→正文用11pt`。这个箭头语法在同表中没有在其他行出现，读者可能困惑——到底用 10.5pt 还是 11pt？

**修正建议**：去掉"五号(10.5pt)→"前缀，直接写"11pt"。如果希望保留"为什么从五号调整到 11pt"的解释，放入脚注或变更记录。

**实现决策**：当前脚本已使用 11pt（常量 `SIZE_BODY = 11`），保持。

---

#### P0-2. 表体字号与正文不一致无说明（§5.1 vs §3.3）

**问题**：§5.1 规定表体数据行 10.5pt，但 §3.3 正文样式表中没有"表格内容"这一行。规范中没有解释为什么表体比正文小 0.5pt。

**修正建议**：在 §3.3 正文样式表中补充"表格内容"行（10.5pt 宋体/TNR）。学术惯例中表格字号可小于正文半号，这是合理的，但需要显式声明。

**实现决策**：按规范执行——正文 11pt，表体 10.5pt。

---

#### P0-3. "章起始另页"含义不精确（§3.2 + §9.4）

**问题**：§3.2 说 H1"章起始另页"，§9.4 说"章间：分页符"。在 Word OOXML 中，"分页符"（`w:br w:type="page"`）只是换页；"分节符（下一页）"（`w:sectPr` 跟在分节符后）除了换页还允许独立的页眉/页脚/页码设置。如果规范意图是每章可以有独立页眉（显示章标题），则需要分节符而非简单分页符。

**修正建议**：明确写"章间插入 `w:sectPr` 分节符（类型：下一页）"，并说明是否需要每章独立页眉。

**实现决策**：除非规范升级要求每章独立页眉，否则先用分页符（`doc.add_page_break()`）。原因：(1) 符合当前§9.4的"分页符"措辞；(2) 每章独立 section 会使页码编号管理变复杂；(3) 当前文档只需要两段页码格式（摘要罗马+正文阿拉伯），可以通过在正文第一页前插入一个分节符实现。

---

#### P0-4. 表格交替行的算法定义缺失（§5.1）

**问题**：§5.1 说"数据行：白底，交替行浅灰底"。没有说明：(a) 从表头后第一行数据起算（第一行白、第二行灰）；(b) 数据行按 0-based index 算奇偶。两种算法结果相同，但明确可避免实现偏差。

**修正建议**：明确为"数据行从第一行起算，奇数行白底，偶数行浅灰底 #F2F2F2"。

**实现决策**：`is_even = (i % 2 == 1)`，即数据行索引 0（第一行）白底，索引 1（第二行）灰底。

---

#### P0-5. 目录格式未定义（§1）

**问题**：§1 说目录"自动生成，含三级标题，可点击跳转"，但未说明目录本身的字体格式（各级标题的字号、缩进、行距）。

**修正建议**：补充目录样式定义。参考学术界惯例：目录一级标题 12pt Bold，二级 12pt，三级 10.5pt，各级依次缩进。

**实现决策**：使用 Word TOC 域自动生成——让 Word 使用内置 TOC 样式渲染，不做手动干预。

---

#### P1-6. 缺少修订记录表

**问题**：正式研究报告通常需要版本修订记录表（列出各版本的修改日期、修改内容、修改人）。规范未涉及。

**修正建议**：在 §1 文档结构中补充"修订记录"（可选，位于封面后、摘要前）。

**实现决策**：暂时不增加。原因是本工具的版本管理由 git 负责，报告中可选项通过 Markdown 源文件自行添加。如果需要自动化，在 Markdown 约定中定义元数据块。

---

#### P1-7. 索引/术语表生成规则缺失（§1）

**问题**：§1 列了"索引/术语表（可选）"，但未提供任何生成规则——哪些术语应入索引？索引格式是什么？

**修正建议**：如果规范意在支持自动生成，需要定义术语标记语法。如果只是"用户可以手工添加"，标注为"可选，手动编写"。

**实现决策**：P2 优先级——定义 Markdown 约定中的术语标记语法（如 `[术语]{.term}`），转换器扫描全文收集术语并生成术语表附录。

---

#### P1-8. 页眉底线实现未说明（§6.1）

**问题**：§6.1 说"黑色底线(1pt)"，但未说明是通过段落下边框（`w:pBdr`）还是通过形状（`w:drawing`）实现。两者效果相似但 OOXML 结构不同。

**修正建议**：建议明确用 `w:pBdr` 的 `w:bottom` 实现，更简洁。

**实现决策**：当前脚本已使用 `w:pBdr` 方案（pitfalls 问题5已验证），保持不变。

---

#### P1-9. 封面"顶部留白 6cm"的转换问题（§7.1）

**问题**：规范用 ASCII art 示意 `(顶部留白 6cm)`，但 OOXML 中无法精确设置"顶部留白 6cm"——只能通过空段落的段前间距累加来近似。

**修正建议**：明确为"通过 10 个段前间距为 0 的空段落实现近似的顶部留白"，或使用 `w:spacing w:before` 在第一个段落上设置 6cm 段前。

**实现决策**：改用第一个段落的 `w:spacing w:before="3403"` (6cm = 3403 twips) 精确控制，替代当前 10 个空段落的近似方案。

---

### 2.2 规范未涉及的内容（缺口）

| 缺口 | 重要性 | 建议 |
|------|--------|------|
| 脚注的 OOXML 实现方式 | P1 | 使用 python-docx 的 `add_footnote` 或手动构建 `w:footnoteReference` |
| 交叉引用（REF 域）的编号引用 | P1 | 使用 SEQ 域 + 书签方案 |
| 图表目录（TOF 域） | P2 | 使用 Word 的 `TOC \c "Figure"` 和 `TOC \c "Table"` 域 |
| 表格跨页自动重复表头的触发条件 | P1 | 规范已提"长表跨页时自动重复"，但多长算长？>1 页自动触发即可 |

### 2.3 与外部标准的一致性检查

| 标准 | 与规范的一致性 | 差异说明 |
|------|---------------|---------|
| GB/T 7713.1-2022（学位论文） | 基本一致 | 规范采用了相同的 A4/字体/编号体系。差异：规范用 11pt 正文（学位论文用 10.5pt 五号） |
| 中国社科院皮书编写手册 | 一致 | 章起始另页、中文数字编号等均符合 |
| 麦肯锡/BCG 排版惯例 | 部分差异 | 商业咨询报告通常不用"第一章"中文数字、章另页、装订侧 3.17cm——这些是学术出版风格。规范的定位更接近学术智库报告而非纯商业文档 |

---

## 3. 架构设计

### 3.1 总体架构

```
┌──────────────────────────────────────────────────────────┐
│                      CLI 入口 (cli.py)                    │
│   python -m md2docx input.md -o output.docx               │
│   --config report.yaml --images figures/ --org "机构名"   │
└──────────────┬───────────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │   Config Loader     │  ← 读取 YAML/JSON 配置，合并 CLI 参数
    │   (config.py)       │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Preprocessor      │  ← 二进制安全读取 → BOM/CR/LF 处理
    │   (preprocessor.py) │     Markdown 清理 → 规范化
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Parser            │  ← Markdown → AST (元素列表)
    │   (parser.py)       │     增强：识别特殊标记/元数据
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   IR Builder        │  ← AST → 中间表示 (Document IR)
    │   (ir.py)           │     包含：结构化章节、图/表元数据
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Renderer          │  ← IR → python-docx Document
    │   (renderer/)       │     子模块：cover/heading/body/
    │                     │     table/image/toc/reference/
    │                     │     special_element/section
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Postprocessor     │  ← 图/表题注修复、交叉引用链路
    │   (postprocessor.py)│     清理孤立引用、格式验证
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   output.docx       │
    └─────────────────────┘
```

### 3.2 数据管道（参考 pitfalls 架构图）

```
原始 Markdown（任意编码/行尾）
         │
    [二进制读取] → strip BOM → CRLF→LF → standalone CR→LF
         │
    [正则清理] → 剥离手动编号 → 删除 HTML 标签 → 删除占位文本
         │              ↓ 二进制写入 (LF only)
    清理后 Markdown
         │
    [parse_markdown] → 元素列表 (Heading/Paragraph/Table/...)
         │
    [IR Builder] → 章节树 + 图/表注册表 + 元数据
         │
    [Renderer] → 封面 → TOC → 摘要 section → 正文 sections → 附录 section
         │
    [Postprocessor] → 图片嵌入 → 题注修复 → 交叉引用验证
         │
    最终 .docx
```

### 3.3 中间表示 (IR) 数据模型

```python
@dataclass
class ChapterInfo:
    """章节元数据"""
    number: int            # 章序号 (1-based)
    cn_number: str         # 中文数字 ("一")
    title: str             # 章标题（无编号）
    h2_counter: int        # 节计数器
    h3_counters: dict      # {h2_number: h3_counter}
    fig_counter: int       # 图序号计数器
    tbl_counter: int       # 表序号计数器
    fn_counter: int        # 脚注计数器

@dataclass
class FigureMeta:
    """图元数据"""
    id: str                # 图号 "2-1"
    chapter: int           # 所属章号
    seq: int               # 章内序号
    caption: str           # 题注文本
    file_path: str         # 图片文件路径
    alt_text: str          # 替代文本

@dataclass
class TableMeta:
    """表元数据"""
    id: str                # 表号 "2-1"
    chapter: int           # 所属章号
    seq: int               # 章内序号
    caption: str           # 题注文本
    header_text: str       # 表头文本（用于匹配）
    source_note: str       # 数据来源注释

@dataclass
class DocumentIR:
    """文档中间表示"""
    metadata: dict                   # 封面元数据 {title, subtitle, org, date, version}
    front_matter: List[Element]      # 摘要、目录（不编号）
    chapters: List[ChapterElements]  # 各章内容
    back_matter: List[Element]       # 参考文献、附录
    figure_registry: Dict[str, FigureMeta]  # 图注册表
    table_registry: Dict[str, TableMeta]    # 表注册表
    term_index: List[str]            # 术语索引
```

### 3.4 Section 布局策略

核心设计：通过 Word OOXML 的 `sectPr` 实现不同段的独立页码格式。

```
Section 1: 封面 + 目录
  - 无页眉
  - 无页脚（或后续设置）
  - 不编页码

  [连续分节符] → Section 2

Section 2: 执行摘要
  - 无页眉
  - 页码：罗马数字 (i, ii, iii...)
  - 页脚居中 9pt

  [下一页分节符] → Section 3

Section 3: 正文（可能包含多个子 section，每章一个）
  - 页眉：报告简称右对齐 + 1pt 黑线
  - 页码：阿拉伯数字 (1, 2, 3...)，从 1 开始
  - 页脚居中 9pt

  [下一页分节符] → Section 4

Section 4: 参考文献 + 附录
  - 页眉：同正文
  - 页码：阿拉伯数字，续正文
  - 页脚居中 9pt
```

**Section 之间页码连续性**：Section 3 的页码从 1 开始（通过 `w:pgNumType w:start="1"`），Section 4 继承 Section 3 的页码序列。

### 3.5 技术选型决策

| 组件 | 选型 | 理由 |
|------|------|------|
| 主力引擎 | python-docx 全手工（保留当前方案） | 已积累 13 个问题修复经验；TOC/表格/字体等核心能力已验证；没有其他方案能提供同等精细控制 |
| 配置格式 | YAML | 人类可读写，支持注释，适合非程序员维护格式参数 |
| Markdown 解析 | 增强现有手写解析器 | AST 简单，不需要完整的 CommonMark 解析；增强特殊标记识别（定义框、案例框等） |
| 图片处理 | python-docx 原生 add_picture + 后处理匹配 | 当前方案已验证；改进：从 Markdown 中提取图号→文件名映射，消去 FIGURE_MAP 硬编码 |
| 表题注匹配 | 正则匹配表头特征（保留方案，改为数据驱动） | 当前 TABLE_MATCHERS 的思路正确（基于表头内容匹配题注），问题在于正则硬编码在代码中。改进：将正则模式从 Markdown 源文件中以标注方式提取 |

---

## 4. 模块详细设计

### 4.1 Config Loader (`config.py`)

**职责**：加载 YAML/JSON 配置文件，合并 CLI 参数覆盖，提供全局配置单例。

**配置文件结构** (`report.yaml`):

```yaml
# 报告元数据
metadata:
  title: ""                             # 报告标题（必填）
  subtitle: ""                          # 英文副标题
  subtype: "深度研究报告"               # 报告类型标签
  org: ""                               # 编制机构（必填）
  version: "V1.0"                       # 版本号
  date: ""                              # 日期，留空=今天

# 字体方案（按 V3.0 §3.1）
fonts:
  body:
    cjk: "宋体"
    latin: "Times New Roman"
  heading:
    cjk: "微软雅黑"
    latin: "Times New Roman"
  mono:
    cjk: "宋体"
    latin: "Consolas"
  table_header:
    cjk: "微软雅黑"
    latin: "Times New Roman"
  table_body:
    cjk: "宋体"
    latin: "Times New Roman"

# 字号 (pt)
sizes:
  cover_title: 28
  cover_subtitle: 14
  cover_type: 16
  cover_info: 11
  h1: 24
  h2: 16
  h3: 14
  h4: 12
  body: 11                             # 正文
  table_header: 10
  table_body: 10.5
  quote: 10.5
  caption: 9                           # 图注/表注
  footnote: 9
  header_footer: 9

# 页面布局（V3.0 §2）
page:
  width: 21.0                           # cm
  height: 29.7
  margin_top: 2.54
  margin_bottom: 2.54
  margin_left: 3.17
  margin_right: 2.54
  header_distance: 1.27
  footer_distance: 1.27

# 行距
line_spacing:
  body: 1.5
  heading: 1.0
  caption: 1.0                         # 单倍
  footnote: 1.0
  quote: 1.5

# 缩进
indent:
  body_first_line: 0.74                # cm（2字符近似）
  quote_left: 1.0
  list_left: 1.5
  list_hang: 0.75

# 段间距（V3.0 §3.2）
spacing:
  h1_before: 0                         # pt
  h1_after: 18
  h2_before: 24
  h2_after: 12
  h3_before: 18
  h3_after: 8
  h4_before: 12
  h4_after: 6
  h5_before: 8
  h5_after: 4
  body_before: 0
  body_after: 0

# 配色方案（V3.0 §11）
colors:
  primary: "000000"                     # 黑色
  secondary: "555555"                   # 辅助文字
  bg_light: "F2F2F2"                    # 背景浅灰
  accent: "333333"                      # 强调深灰
  separator: "BBBBBB"                   # 封面分隔线

# 页眉页脚
header_footer:
  header_text: "{title}"               # 模板变量：{title} = 报告标题
  header_show_on_cover: false
  header_show_on_toc: false
  page_number_summary: "roman"          # roman / arabic
  page_number_body: "arabic"

# 表格
table:
  width_pct: 90                         # 页宽百分比
  border_outer: 1.5                     # pt (顶线/底线)
  border_header_sep: 1.0               # pt (表头下)
  border_inner: 0.5                     # pt (内部)
  alt_row_color: "F2F2F2"
  repeat_header: true

# 封面
cover:
  top_spacing_cm: 6.0                  # 顶部留白
  show_separator: true
  separator_char: "━"

# TOC
toc:
  levels: 3                             # 目录级数
  show_page_numbers: true
  hyperlinks: true

# Markdown 约定识别
markdown:
  enable_front_matter: true             # 识别 YAML front matter
  heading_auto_number: true             # 自动编号
  strip_manual_numbering: true          # 剥离手动编号
  recognize_special_blocks: true        # 识别定义框/案例框
```

**CLI 参数优先级**：CLI `--title "xxx"` > 配置文件 `metadata.title` > 从 Markdown 第一个 H1 推断

**输入**：YAML 文件路径 + CLI argparse Namespace  
**输出**：`Config` dataclass 单例

---

### 4.2 Preprocessor (`preprocessor.py`)

**职责**：二进制安全读取、编码规范化、Markdown 清理。

**保留逻辑**（来自当前 `clean_markdown`）：

- 二进制读取 + BOM 剥离 + CRLF/CR → LF（问题 1 的修复）
- HTML div 标签删除（问题 5）
- 图表占位符删除（问题 6）
- 印刷页数建议行删除（问题 7）
- TOC 指示文字删除
- 封面元数据行删除
- "全文完"删除
- 手动标题编号剥离（H1:`第X章`、H2:`X.X`、H3:`X.X.X`）——问题 4 修复
- 列表图引用剥离（- 图X-Y: ... → 图X-Y: ...）——问题 8 修复
- 孤立表引用删除（无实际 Markdown 表格跟随的表X-Y 行）
- `---` 水平线删除（统一由新逻辑插入分页标记）

**改进逻辑**：

| 改进项 | 当前问题 | 新方案 |
|--------|---------|--------|
| 章节检测 | 硬编码 CHAPTER_TITLES | 运行时扫描 H1 标题，自动识别章节边界 |
| 分页标记插入 | 在 `# 目录`/`# 各章`/`# 附录` 前插入 `---` | 根据 H1 内容和位置自动判断：第一个 H1 前的内容是 front matter；从第二个 H1 开始每章前插入 `---`；检测到"参考"/"附录"/"术语"关键词的 H1 也插入 |
| 英文副标题 | 硬编码 COVER 正则 `China.+Deep-Dive Analysis` | 从 Markdown front matter 的 `subtitle` 字段读取，无 front matter 时从第二个 H2 推断 |
| 封面元数据 | 用 `RE_META` 正则匹配"版本""日期"等行删除 | 改为从 front matter 提取后删除，不再依赖正则 |
| 证据等级说明 | 在 `## 证据等级说明` 前插入分页符 | 去掉硬编码——如果此词出现在任何报告中，由用户通过 Markdown 约定（元数据块）标记哪些 front matter 节需要分页 |

**关键改进：YAML Front Matter 支持**

Markdown 源文件支持可选 YAML front matter：

```markdown
---
title: "中国商业航天产业链深度研究报告"
subtitle: "China Commercial Space Industry Chain Deep-Dive Report"
org: "遨天科技"
date: "2026-07-19"
version: "V1.0"
header_short: "中国商业航天产业链研究"
---

# 中国商业航天产业链深度研究报告
```

优先级：front matter > CLI 参数 > 配置文件 > 推断

**输入**：文件路径  
**输出**：清理后的文本行列表 + 提取的元数据 dict

---

### 4.3 Parser (`parser.py`)

**职责**：将清理后的 Markdown 文本解析为 AST 元素列表。

**基础解析**（保留当前 `parse_markdown` 逻辑）：

- `Heading`（1-5 级）
- `Paragraph`（正文段落）
- `CodeBlock`（围栏代码块）
- `BlockQuote`（引用块）
- `HorizontalRule`（水平线 → 分页标记）
- `ListItem`（有序/无序列表）
- `TableElement`（Markdown 表格）
- `ImageElement`（`![alt](url)` 语法）

**新增解析能力**：

| 新元素 | Markdown 语法 | IR 表示 |
|--------|-------------|---------|
| 定义框 | `::: definition 定义 1-1` | `DefinitionBox(id, title, lines)` |
| 案例框 | `::: case` | `CaseBox(title, lines)` |
| 趋势提示 | 内联 `▲` `▼` `◆` `⚠` | 保留为内联标记，渲染为加粗 |
| 表来源注释 | `[来源: ...]` 或表后一行 `*数据来源: ...*` | `TableMeta.source_note` |
| 术语标记 | `[术语]{.term}` | 注册到 `term_index` |
| 脚注引用 | `[^1]` 或 `^[注释文本]` | `FootnoteRef(id)` / `Footnote(id, text)` |
| 参考文献引用 | `[1]` 上标或 `^[1]^` | `CitationRef(num)` |
| 绘图引用 | `![图2-1 市场规模](figures/2-1-market.png)` | `ImageElement + FigureMeta` |
| 表题注 | 表前一行 `**表2-1 市场规模**` | `TableMeta` 绑定到下一张表 |

**关键设计决策**：图表编号由 Markdown 源文档驱动。图片的 `alt` 文本被解析为题注，从中提取图号（`图2-1`）。Markdown 表格前如有加粗文本行且匹配 `表X-Y` 格式，则作为该表的题注。

**输入**：清理后的文本行列表  
**输出**：元素列表 + `{figures: List[FigureMeta], tables: List[TableMeta], terms: List[str], footnotes: List[FootnoteRef]}`

---

### 4.4 IR Builder (`ir.py`)

**职责**：将 AST 元素列表重组为结构化文档 IR。

**核心逻辑**：

```python
def build_ir(elements, metadata):
    ir = DocumentIR(metadata=metadata)
    current_chapter = None
    state = "front"  # front | body | back

    for elem in elements:
        if isinstance(elem, Heading):
            if elem.level == 1:
                if state == "front" and not _is_back_matter(elem.text):
                    # 第一个非 front/back 的 H1 → 进入正文
                    state = "body"
                    current_chapter = ChapterInfo(...)
                    ir.body_chapters.append(current_chapter)
                elif _is_back_matter(elem.text):
                    state = "back"
                    current_chapter = None
                continue

            # 根据 state 分配到 front/body/back
            ...

        # 提取图/表元数据
        if isinstance(elem, ImageElement):
            fig = _extract_figure_meta(elem, current_chapter)
            ir.figure_registry[fig.id] = fig

        if isinstance(elem, TableElement):
            tbl = _extract_table_meta(adjacent_caption, current_chapter)
            ir.table_registry[tbl.id] = tbl

    return ir
```

**关键改进**：不再依赖 `CHAPTER_TITLES` 硬编码列表。`_is_back_matter()` 通过关键词检测（"参考文献"/"附录"/"术语表"/"索引"/"资料清单"），不区分报告内容。

**输入**：AST 元素列表 + 元数据  
**输出**：`DocumentIR` 实例

---

### 4.5 Renderer (`renderer/`)

#### 4.5.1 文档结构管理 (`renderer/document.py`)

**职责**：管理 python-docx Document 的 section 创建和切换。

```python
class DocumentBuilder:
    def __init__(self, config):
        self.doc = Document()
        self.config = config
        self.current_section = self.doc.sections[0]
        self._setup_page(self.current_section)

    def add_section_break(self, type_="next_page"):
        """插入分节符并返回新 section"""
        new_section = self.doc.add_section()
        self._setup_page(new_section)
        return new_section

    def set_page_number_format(self, section, fmt="roman", start=1):
        """设置 section 的页码格式"""
        sectPr = section._sectPr
        pgNumType = OxmlElement('w:pgNumType')
        pgNumType.set(qn('w:fmt'), fmt)       # 'roman' / 'decimal'
        pgNumType.set(qn('w:start'), str(start))
        # 移除旧的 pgNumType（如果有）
        ...
        sectPr.append(pgNumType)

    def set_header_text(self, section, text, show_line=True):
        """为 section 设置页眉"""
        header = section.header
        header.is_linked_to_previous = False  # ⚠ 关键：断开与前节的链接
        ...

    def set_footer_page_number(self, section, alignment=CENTER):
        """为 section 设置页脚页码"""
        footer = section.footer
        footer.is_linked_to_previous = False
        # 插入 PAGE 域
        ...
```

**关键实现细节**（来自 pitfalls 问题 5）：
- 每个新 section 必须设置 `header.is_linked_to_previous = False` 和 `footer.is_linked_to_previous = False`，否则修改页眉页脚会影响前一个 section
- 封面和目录 section 的页眉清空（`header.paragraphs[0].clear()`）
- 罗马数字页码用 `w:pgNumType w:fmt="lowerRoman"`

#### 4.5.2 封面 (`renderer/cover.py`)

**改进**（相比当前 `_render_cover`）：
- 机构名从 `config.metadata.org` 读取，不再硬编码"遨天科技"
- 顶部留白改用 `w:spacing w:before="3403"` (6cm) 精确控制，替代 10 个空段落
- 封面要素全部从 config 驱动

```python
def render_cover(doc, config):
    p = doc.add_paragraph()
    p.alignment = CENTER
    p.paragraph_format.space_before = Cm(6.0)  # 精确 6cm

    r = p.add_run(config.metadata.title)
    set_run_font(r, ..., SIZE_TITLE, bold=True)

    if config.metadata.subtitle:
        _add_centered_line(doc, config.metadata.subtitle, SIZE_SUBTITLE)

    _add_centered_line(doc, config.metadata.subtype, SIZE_COVER_TYPE)

    # 分隔线
    if config.cover.show_separator:
        sep = doc.add_paragraph()
        ...

    _add_centered_line(doc, config.metadata.org, 14, bold=True)
    _add_centered_line(doc, f"{config.metadata.version} | {date_str}", 11)
```

#### 4.5.3 标题编号 (`renderer/headings.py`)

**改进**（相比当前 `ChapterNum`）：
- 支持 >10 章（当前 CN_NAMES 只有 1-10）
- H4 不入目录（不添加 `w:outlineLvl`）
- H5 实现

```python
class HeadingNumbering:
    CN_MAP = {1:'一',2:'二',...,10:'十',11:'十一',...}  # 扩展到 20

    def h1(self, ch): return f"第{self.CN_MAP[ch]}章"
    def h2(self, ch, sec): return f"{ch}.{sec}"
    def h3(self, ch, sec, sub): return f"{ch}.{sec}.{sub}"
```

#### 4.5.4 TOC (`renderer/toc.py`)

**改进**：增加图表目录（TOF）支持。

```python
def add_toc(doc, levels=3):
    """插入 TOC 域（V3.0 §10.1: 禁止手动输入目录）"""
    p = doc.add_paragraph()
    for tag in ['begin', 'instr', 'separate', 'result', 'end']:
        run = p.add_run()
        if tag == 'instr':
            el = OxmlElement('w:instrText')
            el.set(qn('xml:space'), 'preserve')
            el.text = f'TOC \\o "1-{levels}" \\h \\z'
            run._element.append(el)
        elif tag == 'result':
            run.text = ''
        else:
            el = OxmlElement('w:fldChar')
            el.set(qn('w:fldCharType'), tag)
            run._element.append(el)

def add_figure_toc(doc):
    """插入图表目录——仅当图表数 >= 10"""
    ...

def add_table_toc(doc):
    """插入表目录"""
    ...
```

#### 4.5.5 表格 (`renderer/tables.py`)

**保留**：当前 `_add_table` 的边框控制、交替行灰底、表头重复逻辑（已验证稳定）。
**改进**：表题注从 `TableMeta.caption` 读取，不再依赖硬编码 `TABLE_MATCHERS`。

#### 4.5.6 图片 (`renderer/images.py`)

**完全重写**：不再使用 `FIGURE_MAP` 硬编码。

**新方案**：在 Markdown 解析阶段（parser.py）从 `![图X-Y 题注](path.png)` 提取图号→文件路径→题注的映射，存入 `FigureMeta`。渲染时用 `FigureMeta.file_path` 嵌入图片，用 `FigureMeta.caption` 生成题注。

```python
def embed_image(doc, fig_meta: FigureMeta):
    """嵌入单张图片 + 图注"""
    # 图片段落（居中）
    img_p = doc.add_paragraph()
    img_p.alignment = CENTER
    run = img_p.add_run()
    run.add_picture(fig_meta.file_path, width=Inches(5.2))

    # 图题注（V3.0 §3.3: 9pt #555555 居中）
    cap_p = doc.add_paragraph()
    cap_p.alignment = CENTER
    r = cap_p.add_run(f"图{fig_meta.id}  {fig_meta.caption}")
    set_run_font(r, ...)
```

#### 4.5.7 参考文献 (`renderer/references.py`)

**职责**：将文末参考文献列表格式化为 GB/T 7714-2015 适配版格式。

**输入**：Markdown 中"参考文献"章节的结构化数据。支持两种输入方式：

1. **结构化 Markdown**——推荐：
```markdown
## 参考文献

[1] [L2] 张三, 李四. 商业航天产业链分析[J]. 航天经济, 2025, 12(3): 45-58.
[2] [L4] SpaceX. Starship User's Guide[R]. Hawthorne: SpaceX, 2024.
[3] [L3] Reuters. China's commercial space sector sees record investment[EB/OL]. (2025-06-15)[2026-07-01]. https://...
```

2. **自动格式化**——解析非标准格式的参考文献行，按 GB/T 7714 规则重新格式化（P2 优先级，需要 NLP 能力）

**信源分级处理**：识别 `[L1]`-`[L5]` 前缀，在渲染时转换为信源分级标注。

#### 4.5.8 特殊元素 (`renderer/special_elements.py`)

**定义框**（V3.0 §9.1）：
```python
def add_definition_box(doc, box_id, title, content_lines):
    """浅灰底 #F2F2F2 + 黑色左边框 3pt"""
    for i, line in enumerate(content_lines):
        p = doc.add_paragraph()
        # 设置段落下边框（通过表格模拟）
        # 左缩进 + 3pt 左边框 + 灰底
        ...
```

**实现策略**：用单行单列表格模拟框——表格单元格设底色 #F2F2F2、左边框 3pt 粗。

**案例框**（V3.0 §9.2）：
```python
def add_case_box(doc, title, content_lines):
    """白底 + 黑色边框 1.5pt + 浅灰顶边框 3pt"""
    ...
```

**趋势提示**（V3.0 §9.3）：前缀 ▲/▼/◆/⚠ 在正文内联渲染为加粗，无需特殊段落处理。

#### 4.5.9 脚注 (`renderer/footnotes.py`)

**实现**：python-docx 没有直接的脚注 API，需通过手动构建 `w:footnoteReference` 和 `w:footnote` 元素实现。

**方案**：
- 每章维护一个脚注计数器
- 解析 Markdown 中的 `^[脚注文本]` 或 `[^n]` 语法
- 在正文插入 `w:footnoteReference w:id="n"` 
- 在文档末尾添加 `w:footnote` 部分

#### 4.5.10 交叉引用 (`renderer/cross_refs.py`)

**职责**：实现"如图 X-Y 所示"的自动引用。

**方案**（P2 优先级）：
- 图和表渲染时添加 `w:bookmarkStart/w:bookmarkEnd` 书签
- 正文中 `如图 X-Y 所示` 识别后，查找对应书签，插入 REF 域

---

### 4.6 Postprocessor (`postprocessor.py`)

**职责**：后处理修复和验证。

**保留逻辑**：
- 图片题注附近孤立引用清理（当前 `_embed_images` 的 Phase 3）
- 表题注修复（当前 `_fix_table_captions`——但改为读取 `TableMeta` 而非匹配 `TABLE_MATCHERS`）

**新增验证**：
```python
def validate_output(doc, ir):
    """对照 IR 验证 docx 输出的完整性"""
    warnings = []
    # 检查：所有注册的图是否都已嵌入
    # 检查：所有注册的表是否都已渲染
    # 检查：交叉引用是否有效
    # 检查：章节编号连续性
    return warnings
```

---

### 4.7 CLI (`cli.py`)

```bash
python -m md2docx input.md -o output.docx \
    --config report.yaml \
    --title "报告题名" \
    --org "机构名" \
    --images figures/ \
    --version "V1.0"
```

**参数优先级**：CLI > YAML config > 推断

**运行模式**：
- `--dry-run`：只做预处理和解析，输出清理后的 Markdown 和 AST 统计
- `--validate-only`：验证 Markdown 是否符合约定规范
- `--debug`：保留中间产物（cleaned.md, ir.json）

---

## 5. 关键算法设计

### 5.1 章节自动检测与分页标记插入

```
输入：清理后的 Markdown 行列表
输出：插入了 --- 分页标记的行列表

算法：
1. 扫描所有 H1 标题，构建 chapter_list = [(行号, 标题文本)]
2. 对每个 H1 标题，判断其类型：
   - 如果标题含"摘要"/"目录"/"前言"且是前两个 H1 → front matter
   - 如果标题含"参考"/"附录"/"术语"/"索引" → back matter
   - 否则 → body chapter
3. 按降序在以下位置插入 ---：
   - 第一个 body chapter 的 H1 前（正文第一页）
   - 第一个 back matter 的 H1 前
   - 如果 front matter 中有"目录"H1：目录 H1 前、目录 H1 后
4. 返回插入了 --- 的行列表
```

### 5.2 图表编号自动注册

```
输入：AST 元素列表
输出：figure_registry + table_registry

算法 (在 parser 阶段)：
1. 维护 chapter_counters = {}  # {章节号: {fig: n, tbl: m}}
2. 遍历元素：
   a. 遇到 H1 → current_ch = 递增章节计数器 → 重置 fig/tbl 计数器
   b. 遇到 ![](path) 且 alt 文本匹配 "图X-Y 题注" 格式：
      - 从 alt 提取图号 (X-Y) 和题注
      - 验证 X == current_ch 且 Y 连续
      - 注册到 figure_registry[X-Y] = FigureMeta(...)
   c. 遇到 TableElement 且前一段落匹配 "表X-Y 题注"：
      - 提取表号和题注
      - 注册到 table_registry[X-Y] = TableMeta(...)
3. 返回注册表
```

### 5.3 表题注自动匹配（替代 TABLE_MATCHERS 硬编码）

```
方案 A（推荐，P0）：Markdown 驱动
  - 规范 Markdown 约定：表格前一行必须是题注行
  - 格式：**表X-Y 题注文本**
  - parser 在解析 TableElement 时回溯前一个非空元素，如果是加粗段落且匹配 "表X-Y" 格式，则作为该表的题注

方案 B（保留，P1）：正则匹配降级
  - 如果 Markdown 中没有显式题注行，则使用正则匹配表头文本
  - 但正则模式不是硬编码在代码中——而是从 ir.table_registry 中查找已注册表
  - 匹配逻辑：在 table_registry 中查找与当前表头文本 Jaccard 相似度最高的表
```

### 5.4 分节页码切换

```python
def build_sections(doc, ir, config):
    """构建文档的分节结构"""

    # Section 1: 封面 + 目录（无页码）
    # 渲染封面 → page_break → TOC → 连续分节符

    # Section 2: 执行摘要（罗马数字页码）
    sec2 = doc.add_section()
    sec2.header.is_linked_to_previous = False
    sec2.footer.is_linked_to_previous = False
    # 设置罗马数字页码，从 i 开始
    _set_page_number_format(sec2, fmt='lowerRoman', start=1)
    # 渲染摘要内容

    # 如果摘要存在，插入下一页分节符
    if has_summary:
        doc.add_section()

    # Section 3: 正文（阿拉伯数字页码，从 1 开始）
    sec3 = doc.add_section() if not has_summary else doc.sections[-1]
    sec3.header.is_linked_to_previous = False
    sec3.footer.is_linked_to_previous = False
    # 设置页眉（报告简称 + 底线）
    _setup_body_header(sec3, config)
    # 设置阿拉伯数字页码，从 1 开始
    _set_page_number_format(sec3, fmt='decimal', start=1)
    # 渲染各章正文
    for chapter in ir.body_chapters:
        _render_chapter(doc, chapter, config)

    # Section 4: 参考文献 + 附录（阿拉伯数字，续正文）
    doc.add_section()
    sec4 = doc.sections[-1]
    sec4.header.is_linked_to_previous = True  # 继承正文页眉
    # 页脚继承 Section 3 的页码格式（libre office / word 默认行为）
    # 渲染 back matter
    for elem in ir.back_matter:
        _render_back_element(doc, elem, config)
```

**关键 OOXML 细节**（来自 research）：
- `w:pgNumType w:fmt="lowerRoman"` 设置罗马小写数字
- `w:pgNumType w:start="1"` 重置起始页码
- Section 之间通过 `w:sectPr` 的 `w:type` 属性控制（`nextPage` / `continuous`）
- 页脚的 `is_linked_to_previous = False` 必须在修改页脚内容之前设置，否则会破坏前一个 section 的页脚

### 5.5 GB/T 7714 参考文献格式化

```
算法（P2，自动识别）：
1. 读取"参考文献"章节的所有行
2. 尝试正则识别每条参考文献的格式：
   - [序号] 作者. 题名[J]. 刊名, 年, 卷(期): 起止页.
   - [序号] 作者. 书名[M]. 出版地: 出版社, 年.
   - [序号] 作者/机构. 题名[EB/OL]. (发布日期)[引用日期]. URL.
   - [序号] 机构. 报告名称[R]. 出版地: 机构, 年.
3. 提取信源分级标记 [L1]-[L5]
4. 对已标注格式的引用：直接保留并格式化
5. 对未标注格式的行：尝试根据模式推断类型并补标格式
6. 渲染：每条引用作为一个段落，序号加粗，URL 作为可点击链接
```

---

## 6. 格式合规对照表

标注表示实现方式：
- ✅ = 已实现/保留
- 🔄 = 改进（保留逻辑但重构）
- 🆕 = 新实现
- ⬜ = 不在本次范围/可选

### 6.1 文档结构（§1）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 封面 | 五要素（标题/副标题/机构/日期/版本号） | `renderer/cover.py` | 🔄 参数化 |
| 执行摘要 | 1-2页，罗马数字页码 | `renderer/document.py` | 🆕 分节+页码格式 |
| 目录 | 自动生成，三级标题，可跳转 | `renderer/toc.py` | ✅ 保留 |
| 图表目录 | >=10 个图表时自动生成 | `renderer/toc.py` | 🆕 |
| 正文 | 章起始另页，阿拉伯数字页码 | `renderer/document.py` | 🔄 分节 |
| 参考文献 | 按出现顺序编号 | `renderer/references.py` | 🆕 |
| 附录 | 字母编号（附录A/B/C） | `renderer/headings.py` | 🔄 |
| 索引/术语表 | 可选 | `renderer/special_elements.py` | 🆕 P2 |
| 严禁标密 | 全篇禁止密级标注 | `preprocessor.py` | ✅ 保留 |

### 6.2 页面布局（§2）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| A4 纸张 | 210x297mm | `renderer/document.py` | ✅ |
| 纵向 | portrait | `renderer/document.py` | ✅ |
| 上/下边距 | 2.54cm | `renderer/document.py` | ✅ |
| 左边距 | 3.17cm | `renderer/document.py` | ✅ |
| 右边距 | 2.54cm | `renderer/document.py` | ✅ |
| 页眉 | 1.27cm | `renderer/document.py` | ✅ |
| 页脚 | 1.27cm | `renderer/document.py` | ✅ |
| 行距 | 1.5倍 | `renderer/body.py` | ✅ |
| 首行缩进 | 2字符 | `renderer/body.py` | ✅ |

### 6.3 字体与标题体系（§3）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 正文字体 | 宋体+TNR 11pt | `renderer/body.py` | ✅ |
| 标题字体 | 微软雅黑+TNR | `renderer/headings.py` | ✅ |
| 代码字体 | Consolas | `renderer/body.py` | ✅ |
| H1 章标题 | 小一24pt Bold 居中，段前0pt 段后18pt | `renderer/headings.py` | ✅ |
| H2 节标题 | 三号16pt Bold 两端对齐，段前24pt 段后12pt | `renderer/headings.py` | ✅ |
| H3 小节 | 四号14pt Bold 两端对齐，段前18pt 段后8pt | `renderer/headings.py` | ✅ |
| H4 段落小标题 | 小四12pt Bold 无编号，段前12pt 段后6pt | `renderer/headings.py` | ✅ 不入目录 |
| H5 | 12pt Bold Italic 无编号 | `renderer/headings.py` | 🆕 |
| 引用/导语 | 10.5pt 斜体 左缩进 | `renderer/body.py` | 🔄 |
| 图注/表注 | 9pt 单倍行距 居中 | `renderer/tables.py`, `renderer/images.py` | ✅ |
| 脚注 | 9pt 单倍行距 | `renderer/footnotes.py` | 🆕 |
| 页眉/页脚 | 小五9pt | `renderer/document.py` | ✅ |

### 6.4 编号系统（§4）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 章节编号 H1 | 中文数字 "第X章" | `renderer/headings.py` | ✅ |
| 章节编号 H2 | X.Y | `renderer/headings.py` | ✅ |
| 章节编号 H3 | X.Y.Z | `renderer/headings.py` | ✅ |
| H4/H5 不编号 | - | `renderer/headings.py` | ✅ |
| 图表编号 | 图X-Y / 表X-Y | `parser.py` + `ir.py` | 🔄 数据驱动 |
| 公式编号 | 式(X-Y) | `renderer/special_elements.py` | 🆕 P2 |
| 脚注编号 | 每章独立 ①②③ | `renderer/footnotes.py` | 🆕 P2 |
| 参考文献 | 上标 [1] 关联文末 | `renderer/references.py` | 🆕 |

### 6.5 图表规范（§5）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 表格宽度 | 页宽90%居中 | `renderer/tables.py` | ✅ |
| 表头格式 | 白底 + 黑色加粗 10pt | `renderer/tables.py` | ✅ |
| 数据行交替灰底 | #F2F2F2 | `renderer/tables.py` | ✅ |
| 全框线含竖线 | 顶底1.5pt 表头下1pt 内部0.5pt | `renderer/tables.py` | ✅ |
| 数据10.5pt | 宋体+TNR | `renderer/tables.py` | ✅ |
| 文字左对齐/数字右对齐 | - | `renderer/tables.py` | ✅ |
| 跨页表头重复 | tblHeader | `renderer/tables.py` | ✅ |
| SVG优先 PNG备选 | 300dpi+ | `renderer/images.py` | ⬜ 不实施 |
| 单栏≤14cm | - | `renderer/images.py` | ⬜ 不实施 |
| 图内文字≥9pt | - | ⬜ 不实施 |
| 来源标注 | 图注末尾 | `parser.py` + `renderer/images.py` | 🆕 P1 |

### 6.6 页眉页脚（§6）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 页眉右对齐 + 1pt底线 | 小五9pt | `renderer/document.py` | ✅ |
| 封面/目录无页眉 | - | `renderer/document.py` | 🆕 |
| 摘要罗马数字页码 | 居中 | `renderer/document.py` | 🆕 |
| 正文阿拉伯数字页码 | 居中 | `renderer/document.py` | ✅ |

### 6.7 封面设计（§7）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 顶部留白6cm | - | `renderer/cover.py` | 🔄 精确控制 |
| 标题28pt Bold | 黑色居中 | `renderer/cover.py` | ✅ |
| 副标题14pt | 黑色居中 | `renderer/cover.py` | ✅ |
| 报告类型16pt | 黑色居中 | `renderer/cover.py` | ✅ |
| 机构名14pt Bold | 黑色居中 | `renderer/cover.py` | 🔄 参数化 |
| 版本+日期11pt | 黑色居中 | `renderer/cover.py` | ✅ |

### 6.8 参考文献（§8）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| GB/T 7714格式 | [J]/[M]/[EB/OL] | `renderer/references.py` | 🆕 |
| 信源分级 | L1-L5 | `renderer/references.py` | 🆕 |
| 上标引用 | ^[1]^ | `renderer/references.py` | 🆕 P1 |
| 双轨制 | 正文可点击链接+文末完整列表 | `renderer/references.py` | 🆕 P1 |

### 6.9 特殊元素（§9）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 定义框 | #F2F2F2 + 黑色左边框3pt | `renderer/special_elements.py` | 🆕 P1 |
| 案例框 | 白底+黑色边框1.5pt+灰顶3pt | `renderer/special_elements.py` | 🆕 P1 |
| 趋势提示 | ▲▼◆⚠ 加粗 | `renderer/special_elements.py` | 🆕 P1 |
| 章间分页符 | 不使用分隔线 | `renderer/document.py` | ✅ |

### 6.10 Word技术实现（§10）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| TOC域 | 自动生成，禁止手动输入 | `renderer/toc.py` | ✅ |
| 多级列表 | 绑定标题样式 | `renderer/headings.py` | ✅ outlineLvl |
| 交叉引用 | REF域 | `renderer/cross_refs.py` | 🆕 P2 |
| 图表编号 | SEQ域+题注样式 | - | ⬜ 暂用手动编号 |
| 页码 | PAGE域 | `renderer/document.py` | ✅ |
| 书签 | Bookmark+超链接 | - | ⬜ P2 |

### 6.11 配色方案（§11）

| 规范条款 | 要求 | 实现模块 | 方式 |
|---------|------|---------|------|
| 主色 #000000 | 标题/表头/边框/正文 | `config.py` | ✅ 配置化 |
| 辅助 #555555 | 图注/表注/脚注 | `config.py` | ✅ |
| 背景 #F2F2F2 | 表格交替行/定义框 | `config.py` | ✅ |
| 强调 #333333 | 特殊强调 | `config.py` | ✅ |

---

## 7. Markdown 源文件约定规范

为确保 Markdown 能被正确转换为格式合规的 Word 文档，源文件需遵循以下约定。

### 7.1 必须遵循的约定（违反将导致转换错误）

| # | 约定 | 说明 |
|---|------|------|
| M1 | **标题不手动编号** | H1 不要写"第一章 xxx"，只写"xxx"；H2 不要写"1.1 xxx"，只写"xxx"。转换器自动添加编号 |
| M2 | **YAML front matter 提供元数据** | 文档开头使用 `---` 包裹的 YAML 块，提供 title/subtitle/org/date/version |
| M3 | **图片使用 alt 标注图号** | `![图2-1 题注描述](figures/2-1.png)`，图号格式为 `图章号-序号` |
| M4 | **表格前写题注行** | 表格前一行使用加粗段落标注题注：`**表2-1 题注描述**`（紧跟表格，中间最多空一行） |
| M5 | **禁止 HTML 标签** | 不使用 `<div>`、`<br/>` 等 HTML 标签（会被清理掉） |
| M6 | **用 `---` 标记分页意图** | 需要分页的位置（摘要/目录/各章/附录之间）使用 `---` 分隔（或由预处理自动插入） |
| M7 | **表格用 Markdown 标准语法** | `| col1 | col2 |` + `|---|---|` 分隔行 |
| M8 | **封面元数据放在 front matter** | 机构名、版本号、日期通过 YAML front matter 或 CLI 参数传入，不在正文中单独手写封面内容 |

### 7.2 推荐遵循的约定（提升转换质量）

| # | 约定 | 说明 |
|---|------|------|
| R1 | 参考文献在独立章节 `## 参考文献` 中列出 | 每条以 `[序号]` 开头 |
| R2 | 引用块使用 `>` 前缀 | 自动渲染为引用样式（斜体、左缩进） |
| R3 | 趋势提示使用内联符号 | `▲上升趋势` `▼下降趋势` `◆判断` `⚠风险` |
| R4 | 数据来源标注在表格后 | `*数据来源：NSR, 2025 [链接](URL)*` |
| R5 | 每章末尾写"本章对主论点的贡献" | 使用 `### X.Y 本章对主论点的贡献` 小节标题 |
| R6 | 图表引用用明确编号 | 用"如图 3-2 所示"而非"下图"（因排版后位置可能变化） |

### 7.3 特殊元素语法（P1 实现）

| 元素 | Markdown 语法 | 示例 |
|------|-------------|------|
| 定义框 | `::: definition 定义 1-1` | `::: definition 定义 1-1\n**在轨服务**\n指一个航天器对...\n:::` |
| 案例框 | `::: case` | `::: case\n**案例：MEV-1延寿任务**\n客户：Intelsat\n:::` |
| 术语标记 | `[术语名]{.term}` | `[在轨服务]{.term}` → 自动收集到术语表 |
| 脚注 | `^[脚注文本]` | `这是一段正文^[此处为脚注说明]。` |

### 7.4 完整的 Markdown 模板

```markdown
---
title: "报告题名"
subtitle: "English Subtitle"
org: "编制机构"
date: "2026-07-19"
version: "V1.0"
header_short: "报告简称"
---

# 报告题名

---

## 执行摘要

摘要内容...

---

## 目录

<!-- 自动生成 TOC -->

---

# 第一章标题

> **本章结论**：一句话结论。

## 1.1 节标题

正文内容...

### 1.1.1 小节标题

![图1-1 图表题注](figures/1-1-figure.png)

**表1-1 表格题注**

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| A   | B   | C   |

*数据来源：机构名, 年份 [链接](URL)*

---

# 第二章标题

...

---

## 参考文献

[1] [L2] 作者. 题名[J]. 刊名, 年, 卷(期): 起止页.

---

## 附录A：图表索引

...

## 附录B：术语表

...
```

---

## 8. 配置化方案

### 8.1 配置文件体系

```
report.yaml           → 报告级配置（字体/字号/间距/颜色/机构名等）
  ↑ CLI --config 参数可指定

Markdown front matter → 报告级元数据（title/subtitle/org/date/version）
  ↑ 优先级：front matter > YAML > 默认值

CLI 参数              → 运行时覆盖（--title, --org, --images 等）
  ↑ 优先级最高
```

### 8.2 默认配置

提供 `default_config.yaml` 作为内置默认值：

```yaml
# 默认配置（与 V3.0 规范完全对齐）
# 用户提供的 report.yaml 中的项会覆盖此默认值
fonts:
  body: { cjk: "宋体", latin: "Times New Roman" }
  heading: { cjk: "微软雅黑", latin: "Times New Roman" }
  # ... (完整默认值与 §4.1 的 YAML 示例相同)
```

### 8.3 配置文件管理策略

- 项目根目录的 `report.yaml` 作为项目默认配置
- 用户可以为不同报告类型创建不同的配置（如 `report-academic.yaml`、`report-industry.yaml`）
- CLI `--config` 参数覆盖默认配置路径

---

## 9. 实现优先级与工作量估算

### P0（必须实现，阻塞交付）

| 编号 | 任务 | 预估工时 | 说明 |
|------|------|---------|------|
| P0-1 | 消除硬编码：参数化机构名/标题/副标题 | 2h | config + cover 参数化 |
| P0-2 | 消除硬编码：数据驱动图表匹配 | 4h | parser 从 Markdown 提取图/表元数据，消去 FIGURE_MAP 和 TABLE_MATCHERS |
| P0-3 | 消除硬编码：章节自动检测 | 2h | 扫描 H1 自动判断 front/body/back，消去 CHAPTER_TITLES |
| P0-4 | 分节 + 页码格式切换 | 6h | 摘要罗马数字 + 正文阿拉伯数字 |
| P0-5 | 封面/目录 section 无页眉 | 2h | is_linked_to_previous + 清空页眉 |
| P0-6 | YAML front matter 支持 | 3h | 读取 front matter 作为元数据源 |
| P0-7 | YAML 配置文件加载 | 3h | config.py + 完整默认配置 |
| P0-8 | 增强 Markdown 约定：表前题注行解析 | 2h | `**表X-Y 题注**` 语法 |
| P0-9 | 增强 Markdown 约定：图片 alt 解析 | 2h | `![图X-Y 题注](path)` 提取图号 |

**P0 合计**：约 26h

### P1（应该实现，显著提升质量）

| 编号 | 任务 | 预估工时 | 说明 |
|------|------|---------|------|
| P1-1 | 定义框渲染 | 3h | OOXML 模拟定义框 |
| P1-2 | 案例框渲染 | 3h | OOXML 模拟案例框 |
| P1-3 | 趋势提示内联渲染 | 1h | ▲▼◆⚠ 加粗 |
| P1-4 | 图表目录自动生成 | 2h | TOC 域变体（\c "Figure"） |
| P1-5 | 参考文献 GB/T 7714 结构化处理 | 6h | 解析+格式化 |
| P1-6 | 信源分级 L1-L5 标注 | 2h | 识别 [L1]-[L5] 前缀 |
| P1-7 | 表来源注释处理 | 1h | `*数据来源: ...*` 识别 |
| P1-8 | 表题注降级匹配（无显式标注时） | 3h | 基于表头文本相似度匹配 |
| P1-9 | 代码块等宽字体渲染 | 1h | Consolas 8pt-9pt |
| P1-10 | 封面上标副标题处理 | 1h | 正确处理上标/下标 |

**P1 合计**：约 23h

### P2（可选增强，锦上添花）

| 编号 | 任务 | 预估工时 | 说明 |
|------|------|---------|------|
| P2-1 | 术语索引自动收集 | 4h | `[术语]{.term}` 语法 |
| P2-2 | 交叉引用 REF 域 | 4h | 书签 + REF 域 |
| P2-3 | 脚注支持 | 6h | w:footnoteReference |
| P2-4 | 参考文献上标引用 | 3h | ^[1]^ 渲染为上标 |
| P2-5 | 图表 SEQ 域自动编号 | 4h | 替代手动编号 |
| P2-6 | 多节页眉独立配置 | 3h | 每章页眉显示章标题 |
| P2-7 | Markdown 约定验证器 | 3h | 提示源文件不符合约定之处 |
| P2-8 | 输出格式合规验证 | 2h | 对照规范检查输出 docx |

**P2 合计**：约 29h

**总计（P0+P1+P2）**：约 78h

---

## 10. 改动清单

改动清单供执行编排器消费，每条含改动ID、目标文件、内容、依赖、关键路径标志。

| ID | 优先级 | 目标 | 内容 | 依赖 | 关键路径 | 验收标准 |
|----|--------|------|------|------|---------|---------|
| C01 | P0 | 新建 `scripts/md2docx/` 目录 | 创建 Python 包结构 | - | Y | 包可导入 |
| C02 | P0 | 新建 `scripts/md2docx/config.py` | 配置加载模块（YAML + 默认值 + CLI合并） | C01 | Y | 默认配置加载正确；CLI覆盖生效 |
| C03 | P0 | 新建 `scripts/md2docx/default_config.yaml` | 默认配置文件（与 V3.0 对齐） | C01 | Y | 包含所有字体/字号/间距/颜色项 |
| C04 | P0 | 新建 `scripts/md2docx/preprocessor.py` | 预处理模块（二进制安全 + 清理 + front matter） | C01,C02 | Y | 嵌入CR处理正确；front matter解析正确 |
| C05 | P0 | 新建 `scripts/md2docx/parser.py` | Markdown解析器（增强：图表元数据提取） | C01 | Y | 图号/表号从 Markdown 提取正确 |
| C06 | P0 | 新建 `scripts/md2docx/ir.py` | IR 数据模型和构建器 | C01,C05 | Y | DocumentIR 构建正确；图/表注册表完整 |
| C07 | P0 | 新建 `scripts/md2docx/renderer/__init__.py` | 渲染器包入口 | C01 | Y | - |
| C08 | P0 | 新建 `scripts/md2docx/renderer/document.py` | 文档结构管理（section/分页/页码格式） | C01,C07 | Y | 摘要罗马+正文阿拉伯页码正确 |
| C09 | P0 | 新建 `scripts/md2docx/renderer/cover.py` | 封面渲染（参数化） | C01,C02,C07 | Y | 机构名/标题从配置读取 |
| C10 | P0 | 新建 `scripts/md2docx/renderer/headings.py` | 标题编号与渲染 | C01,C07 | Y | H1-H5编号正确；H4不入目录 |
| C11 | P0 | 新建 `scripts/md2docx/renderer/toc.py` | TOC 和图表目录渲染 | C01,C07 | Y | TOC 域结构正确（begin→instr→separate→end） |
| C12 | P0 | 新建 `scripts/md2docx/renderer/body.py` | 正文/引用/列表渲染 | C01,C07 | Y | 首行缩进2字符；1.5倍行距 |
| C13 | P0 | 新建 `scripts/md2docx/renderer/tables.py` | 表格渲染（保留边框/交替行逻辑） | C01,C06,C07 | Y | 全框线含竖线；交替行灰底正确 |
| C14 | P0 | 新建 `scripts/md2docx/renderer/images.py` | 图片嵌入与图注（数据驱动） | C01,C06,C07 | Y | 图号从 Markdown 驱动；题注在下方居中 |
| C15 | P0 | 新建 `scripts/md2docx/renderer/helpers.py` | 通用渲染辅助函数（set_run_font / set_para_spacing 等） | C01,C07 | Y | 中英文字体混合设置正确 |
| C16 | P0 | 新建 `scripts/md2docx/postprocessor.py` | 后处理（图/表题注修复+验证） | C01,C06 | N | 孤立引用被清理；图/表数量与IR一致 |
| C17 | P0 | 新建 `scripts/md2docx/cli.py` | CLI 入口 | C01-C16 | Y | 完整参数支持；--dry-run可运行 |
| C18 | P0 | 新建 `scripts/md2docx.py` | 顶层入口脚本（兼容旧接口） | C01-C17 | Y | `python scripts/md2docx.py input.md -o out.docx` 可用 |
| C19 | P1 | 新建 `scripts/md2docx/renderer/special_elements.py` | 定义框/案例框/趋势提示 | C01,C07 | N | 定义框灰底左边框正确 |
| C20 | P1 | 新建 `scripts/md2docx/renderer/references.py` | 参考文献格式化 | C01,C07 | N | GB/T 7714 格式正确；L1-L5标注 |
| C21 | P1 | 新建 `scripts/md2docx/renderer/footnotes.py` | 脚注支持 | C01,C07 | N | 每章独立编号 |
| C22 | P2 | 新建 `scripts/md2docx/renderer/cross_refs.py` | 交叉引用 REF 域 | C01,C07 | N | "如图 X-Y" 可点击跳转 |
| C23 | P2 | 新建 `scripts/md2docx/validator.py` | Markdown 约定验证器 | C01 | N | 抛出不符合约定的行号和原因 |
| C24 | P0 | 修改 `references/研究报告格式规范.md` | 补充正文字号说明（去掉"五号"歧义） | - | N | §3.3 正文行直接写 11pt |
| C25 | P0 | 新建 `report.yaml` | 项目默认配置文件 | C03 | N | 含机构/字体等完整默认值 |

---

## 11. 分布式要求登记表

供 G6（执行编排器）的前置输入——记录本次设计涉及的所有跨模块约束。

| 要求编号 | 类型 | 描述 | 涉及模块 | 验收方式 |
|---------|------|------|---------|---------|
| DR-01 | 字体一致性 | 所有模块使用统一字体配置（config.fonts），不硬编码字体名 | 所有 renderer | 搜索代码中无硬编码"宋体""微软雅黑"字样 |
| DR-02 | 字号一致性 | 所有模块使用统一字号配置（config.sizes），不硬编码字号值 | 所有 renderer | 搜索代码中无硬编码 Pt(11) 等值 |
| DR-03 | 颜色一致性 | 所有模块使用统一颜色配置（config.colors） | 所有 renderer | 搜索代码中无直接写 "F2F2F2" 等色值 |
| DR-04 | 图号连续 | 图号在全文中连续不重不漏 | parser + ir + renderer/images | 输出 docx 中所有图编号连续 |
| DR-05 | 表号连续 | 表号在全文中连续不重不漏 | parser + ir + renderer/tables | 输出 docx 中所有表编号连续 |
| DR-06 | Section 隔离 | 封面/目录 section 的页眉页脚不影响正文 section | renderer/document | 输出 docx 中前段无页眉、后段有页眉 |
| DR-07 | TOC 域完整性 | TOC 域包含 begin→instrText→separate→end 四态 | renderer/toc | Word 中右键更新域可正常生成页码 |
| DR-08 | 分页标记 | 仅从 `---` 触发分页，不在其他地方隐式分页 | preprocessor + renderer/document | 输出 docx 中分页符数量 = `---` 数量 |
| DR-09 | 二进制安全 | 所有文件读写使用二进制模式 | preprocessor | CR 嵌入字符不导致标题截断 |
| DR-10 | 手动编号剥离 | 所有 H1/H2/H3 的手动编号在预处理阶段剥离 | preprocessor | 输出 docx 中无"第一章第一章"重复 |

---

## 12. 已知限制与风险

### 12.1 技术限制

| 限制 | 影响 | 缓解措施 |
|------|------|---------|
| python-docx 无原生脚注 API | 脚注需手动构建 OOXML，复杂度高 | P2 实现；先在 Markdown 中不强制要求脚注 |
| python-docx 无原生 REF/SEQ 域 API | 交叉引用需手动构建 | P2 实现；先用手动编号 |
| 页码格式切换依赖 Word 正确理解分节符 | 若 WPS 或 Word 旧版本不支持可能失败 | 标注最低版本要求 Word 2016+ / WPS 2019+ |
| 表格交替行与分页场景的灰底 | 跨页时首行灰底可能在 Word 中显示不一致 | 当前方案已验证稳定；不做修改 |
| 中文字体在未安装微软雅黑的系统上降级 | Linux/WPS 环境下可能字体不对 | 在输出检查清单中提示字体要求 |
| 图片嵌入依赖 PNG 格式 | SVG 图片需提前转换为 PNG | 在脚本说明中标注"请确保 figures/ 中为 PNG 格式" |

### 12.2 设计风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| 重构引入新 bug | 中 | 影响所有输出文档 | 保留当前脚本；新旧脚本并行运行时对比输出 |
| Markdown 约定不被用户遵守 | 高 | 图表匹配失败 | 约定验证器（P2-7）提前报错 |
| 分节页码在 WPS 中不兼容 | 中 | 页码格式错误 | 提前在 WPS 中测试 |
| 多 section 页眉复杂度超出预期 | 低 | 开发延期 | 简化方案：只用两段（前段无页眉/后段统一页眉） |

### 12.3 迁移策略

1. **Phase 1**（P0 完成后）：新脚本 `scripts/md2docx/` 与旧脚本 `scripts/markdown_to_docx.py` 并行
2. **Phase 2**（P0 验证通过）：替换 SKILL.md 阶段 9 的调用命令
3. **Phase 3**（P1 完成后）：旧脚本归档为 `scripts/markdown_to_docx_legacy.py`
4. **Phase 4**（P2 可选）：持续增强，按需求优先级迭代

---

## 附录：设计追溯表

每个设计决策都可追溯到格式规范的具体条款或踩坑记录的具体问题。

| 设计决策 | 格式规范条款 | Pitfalls 问题 | 说明 |
|---------|------------|--------------|------|
| 二进制安全管道 | - | 问题 1, 3 | CR/LF 统一处理 + BOM 剥离 |
| TOC 域四态结构 | §10.1 | 问题 2 | begin→instrText→separate→end |
| 统一分页控制（仅 `---` 触发） | §9.4 | 问题 3 | 消除多处隐式分页 |
| 剥离手动标题编号 | §4.1 | 问题 4 | 避免"第一章第一章"重复 |
| 表题注匹配（基于内容） | §4.2 | 问题 9 | 替代硬编码 TABLE_MATCHERS |
| 图题注数据驱动 | §4.2 | 问题 8 | 消去 FIGURE_MAP 硬编码 |
| 分节页眉页脚独立配置 | §6.1, §6.2 | 问题 5 | is_linked_to_previous=False |
| 正文字号 11pt | §3.3 | 问题 13 | 对照规范明确 11pt（非五号/10.5pt） |
| 中英文字体混合设置 | §3.1 | 问题 11 | w:eastAsia + w:ascii + w:hAnsi |
| 封面顶部留白精确控制 | §7.1 | 问题 12 | 改用 w:spacing w:before 替代空段落 |
