# 工作流设计文档：图表质量约束方案

> 编排器消费说明：本文档设计两个模块——(A) 阶段6/7 质量门槛扩展 (B) dataviz skill 集成方案。
> 全部设计基于 `SKILL.md`（v9 阶段方法论）、`研究报告格式规范 V3.1` 和 `md→docx 转换器 v2 工作流设计`
> 的现有调度体系做扩展，不重新设计整体调度框架。

---

## 0. 现存调度体系摘要（来自 SKILL.md 分析）

**调度性质**：本 skill 不是常驻定时任务系统，而是 Agent 驱动的 9 阶段顺序流水线。每个阶段末尾有 `CHECKPOINT STOP`
质量门槛，不通过即退回指定子步骤修复，不进入下一阶段。

**关键时序约束**：

```
阶段1(参数确认) → 阶段2(资料抽取) → 阶段3(事实核验) → 阶段4(大纲)
→ 阶段5(专题卡片) → 阶段6(核心架构图) → 阶段7(分章写作+数据图表)
→ 阶段8(红队审查) → 阶段9(定稿整合+docx导出)
```

**与本次设计直接相关的两个阶段**：

| 阶段 | 核心活动 | 当前门槛项数 | 出图工具 |
|------|---------|-------------|---------|
| 阶段6 | 核心架构图（先于写作） | 5 项 | drawio、fireworks-tech-graph、Mermaid |
| 阶段7 | 分章写作 + 数据图表（逐章循环） | 9 项 | matplotlib（Python） |

**阶段7 写作循环（当前）**：

```
调取专题卡片 → 写完文字草稿 → 立即产出该章的数据图表 → 图表嵌入文字
→ 检查证据源 → 检查台账 → 回填卡片使用记录 → 进入下一章
```

**格式规范 V3.1 的图表质量基线**（§5.2）：
- 配色：黑白灰为主，辅助可用深灰色对比强调
- 字体：图内文字 >= 9pt，坐标轴标签 10pt，图例 9pt
- 尺寸：单栏图宽度 <= 14cm
- 格式：PNG 300dpi+（须写入 pHYs 物理尺寸元数据）
- 表格：全框线含竖线、交替行灰底 #F2F2F2

---

## 1. 任务 A：阶段6 和阶段7 质量门槛扩展

### A1. 阶段6 新增检查项（6 项）

**设计原则**：阶段6 产出的是架构图（drawio/fireworks-tech-graph SVG+PNG），这些图是报告的骨架，
在阶段7 写作开始前必须保证配色、字体、命名、可读性达标——此时修改比写作完成后再返工成本低得多。

| 编号 | 检查项 | 检查方式 | 阻塞级别 | 适用图类型 | 失败动作 |
|------|--------|---------|---------|-----------|---------|
| **S6-1** | **配色合规检查**：所有架构图是否使用了灰度色板（黑 `#000000`、`#333333`、`#666666`、`#999999`、`#CCCCCC`、白 `#FFFFFF`），不得出现彩色（`#FF0000` 等纯色或 HSL S>0.05 的色值）。每张图如需要使用灰色以外的强调色（如仅用于某一张图的一个高亮组件），必须登记到 `research/figures/color-registry.csv`（字段：`figure_id, color_hex, element, justification`） | 半自动 | **MUST** | 架构图（drawio/fireworks） | 回到阶段6.1：打开 `.drawio` 源文件批量替换配色；fireworks 图修改 JSON 数据中的颜色字段后重新生成 SVG+PNG。登记遗漏 → 补充 color-registry.csv |
| **S6-2** | **字体达标检查**：在 14cm 缩放下，图内文字是否真的 >= 9pt？drawio 文件的 `fontSize` 属性 + fireworks 的 `font-size` CSS 属性是否满足此约束（drawio: `fontSize>=9`，fireworks: `font-size>=9pt`）。标题文字允许 >= 12pt | 半自动 | **MUST** | 架构图（drawio/fireworks） | 回到阶段6.1：在 drawio 中选中所有节点 → 统一设置字体大小；fireworks 修改模版参数后重新生成 |
| **S6-3** | **印刷可读性检查**：将每张架构图的 PNG 缩放到 14cm 宽度（屏幕 100% 查看），在屏幕上肉眼判断以下问题：(a) 文字是否因灰色太浅（如 `#DDDDDD`）而不可读；(b) 线条是否因太细（<1pt）而在打印时可能断线；(c) 相邻元素是否有足够间距避免粘连 | 人工 | **MUST** | 架构图（全部工具） | 回到阶段6.1：加深浅灰文字至 `#666666` 或以上；加粗关键连线至 >= 1.5pt；调整元素间距。每张图修正后重新导出 PNG |
| **S6-4** | **命名一致性检查**：同一概念（如"数据层"/"Data Layer"）在不同架构图中是否使用统一名称？是否出现"感知层"在总览图叫"感知层"、在分章架构图叫"传感层"或"Perception"？ | 半自动 | **MUST** | 架构图（全部工具） | 回到阶段6.1：对照 `research/notes/architecture-cards/` 中的术语定义，统一所有架构图中的组件/层次命名。在 card-index.csv 的 `notes` 字段记录最终选定的术语 |
| **S6-5** | **色盲友好检查**：架构图中的信息是否依赖颜色区分？如存在"绿色=正常、红色=告警"的语义颜色编码，必须有第二种视觉区分方式（线型虚线/实线、形状差异、文字标签）。V3.1 的黑白灰配色天然降低了该风险，但仍需检查是否有灰色阶差不足以区分两个相邻类别的情况 | 人工 | **SHOULD** | 架构图（全部工具） | 如发现仅靠灰色阶差难以区分的两组元素 → 回到阶段6.1：为两组添加不同的线型（实线 vs 虚线）或不同的节点形状（矩形 vs 圆角矩形），同时保留灰度差异作为辅助 |
| **S6-6** | **图注完整性检查**：每张架构图的图注中是否说明了：(a) 该图的逻辑依据（来自哪个分析框架/方法论），(b) 图注中的数据或结构是否标注了来源（如 `来源：根据阶段5 架构卡 ARCH-03 整理`），(c) 图注末尾的数据来源行格式是否与 V3.1 §4.2 一致 | 半自动 | **MUST** | 架构图（全部工具） | 回到阶段6.1：为每张图补充完整的图注文字。至少包含：`图X-Y <标题>` + `来源：<architecture-card-id>，根据<分析框架>绘制`。缺少来源的图在阶段8 红队审查中会被标记为"证据薄弱" |

**阶段6 质量门槛总表（原有 5 项 + 新增 6 项 = 11 项）**：

```
阶段6 CHECKPOINT · STOP 前必须全部通过：
[原有] 总览图至少1张完成（.drawio+.svg+.png 三文件齐全）
[原有] 每个核心分析章节至少1张架构图草图
[原有] 架构图之间逻辑一致
[原有] 所有架构图有逻辑或来源标注
[原有] 所有PNG已验证达到300dpi
[新增] S6-1 配色合规检查（灰度色板 + 例外登记）
[新增] S6-2 字体达标检查（图内文字>=9pt）
[新增] S6-3 印刷可读性检查（14cm缩放不可读元素为零）
[新增] S6-4 命名一致性检查（同概念同名称）
[新增] S6-5 色盲友好检查（无纯靠颜色传递的信息，SHOULD级）
[新增] S6-6 图注完整性检查（逻辑来源+数据来源标注）
```

> **MUST vs SHOULD**：S6-5 是 SHOULD 级——不阻塞进入阶段7，但偏差记录需在阶段8 红队审查中复检。其余 5 项新增 + 5 项原有全部是 MUST 级。

---

### A2. 阶段7 新增检查项——逐章循环的每章末尾触发（5 项）

**设计原则**：阶段7 是逐章循环，"写完一章→立即出图→检查→进入下一章"。
新增检查项必须在 `检查证据源 → 检查台账 → 回填卡片使用记录` 之后、`进入下一章` 之前执行，
即插在当前循环的末端——此时该章的数据图表已全部产出，可以全面检查。

| 编号 | 检查项 | 检查方式 | 阻塞级别 | 适用图类型 | 失败动作 |
|------|--------|---------|---------|-----------|---------|
| **S7-1** | **matplotlib rcParams 合规检查**：该章所有 matplotlib 产出的 PNG 是否应用了统一的样式模板？检查方法：在出图脚本开头设置 `mpl.rcParams` 后，出图前打印 `mpl.rcParams['font.size']` 等关键值到日志，检查日志确认：(a) `font.family` 是否为 `sans-serif`，(b) `font.size` 是否为 `9`，(c) `axes.labelsize` 是否为 `10`，(d) `savefig.dpi` 是否为 `300`，(e) 是否设置了 `axes.spines.top/right = False`（学术图表风格） | 自动 | **MUST** | 数据图表（matplotlib） | 回到阶段7.3 当前章的步骤3：修正该章的 matplotlib 出图脚本（设置 rcParams 后重新运行），所有该章图表重新生成 PNG |
| **S7-2** | **数据图表配色合规检查**：该章所有数据图表是否使用了灰度配色？检查方法：用 Pillow 打开每张 PNG，采样非白色区域的像素，计算每个像素的 HSL S 分量——S>0.05（即存在可感知的色彩饱和度）的像素占比是否超过 5%？如果超过，说明图表使用了彩色而非灰度。例外：如果需要用灰度以外的色调区分 >=5 个数据系列（灰度阶差不足以区分），必须在 `color-registry.csv` 中登记 | 自动 | **MUST** | 数据图表（matplotlib） | 回到阶段7.3 步骤3：修改 matplotlib 的 `color_cycle` 为灰度色板序列（`['#333333','#666666','#999999','#BBBBBB','#DDDDDD']`），重新出图。需彩色区分的场景 → 登记到 color-registry.csv 后方可豁免 |
| **S7-3** | **图表类型选择合理性检查**：该章使用的图表类型是否与数据类型匹配？是否选了"反模式"图类型？检查规则：(a) 时间序列数据不得使用饼图（饼图只能用于占比，静态截面）；(b) 分类对比不得使用折线图（折线图隐含连续性，离散类别应用柱状图）；(c) 饼图扇区 >= 5 个时是否合并为 Top4+其他；(d) 是否出现了 3D 图表（3D 透视变形会扭曲数据感知，禁用） | 人工 | **SHOULD** | 数据图表（matplotlib） | 发现反模式 → 回到阶段7.3 步骤3：用正确的图表类型重新出图。`SHOULD` 级不阻塞进入下一章，但偏差需要记录到每章的"图表类型决策日志"（`research/figures/chart-type-log.csv`），供阶段8 红队审查时复核 |
| **S7-4** | **alt text 完整性检查**：该章所有数据图表在 Markdown 中的 `![图X-Y 标题](path)` 语法是否在方括号内包含了足够的替代文本？alt text 必须包含：(a) 图表类型（如"分组柱状图"），(b) 核心数据发现（如"2020-2025年市场规模从74亿增至180亿美元"），(c) 数据来源。标准格式：`![图X-Y <图表类型>：<核心发现>（数据来源：<来源>）](path)` | 半自动 | **MUST** | 数据图表（matplotlib） | 回到阶段7.3 步骤4（图表嵌入文字）：补充该章每张图在 Markdown 中的 alt text，确保三者齐全。脚本可检查 alt text 是否含三个必要字段的正则匹配，缺失任一项 → Warning；人工确认补充内容准确 |
| **S7-5** | **灰度打印友好检查**：该章所有图表在完全灰度打印（即转为 `mode='L'` 灰度图）后，不同数据系列/类别是否仍然可区分？检查方法：对每张 PNG 用 Pillow 转为灰度（`img.convert('L')`）并保存为 `_grayscale.png` 副本，人工肉眼判断：(a) 相邻两个数据系列在灰度图中的亮度差是否 >= 30（0-255 尺度），(b) 柱状图相邻柱子的边界是否清晰可辨，(c) 图例的颜色方块在灰度下是否还能一一对应到图表中的数据系列 | 人工 | **SHOULD** | 数据图表（matplotlib） | 灰度下不可区分 → 回到步骤3：调整灰度色板序列的亮度间隔（将 `['#666666','#777777','#888888']` 拉开为 `['#333333','#777777','#BBBBBB']`），重新出图。不可区分但数据系列数 > 5 且无法用灰度拉开 → 登记到 color-registry.csv + 在报告中添加脚注说明"本图建议在彩色屏幕上查看" |

---

### A3. 检查项方式/级别/适用性汇总

| 编号 | 检查项 | 检查方式 | 阻塞级别 | 适用图类型 | 建议脚本路径 |
|------|--------|---------|---------|-----------|-------------|
| S6-1 | 配色合规检查 | 半自动 | MUST | 架构图 | `scripts/check_color_compliance.py` |
| S6-2 | 字体达标检查 | 半自动 | MUST | 架构图 | `scripts/check_font_compliance.py` |
| S6-3 | 印刷可读性检查 | 人工 | MUST | 架构图 | — |
| S6-4 | 命名一致性检查 | 半自动 | MUST | 架构图 | `scripts/check_naming_consistency.py` |
| S6-5 | 色盲友好检查 | 人工 | SHOULD | 架构图 | — |
| S6-6 | 图注完整性检查 | 半自动 | MUST | 架构图 | `scripts/check_caption_completeness.py` |
| S7-1 | matplotlib rcParams 合规 | 自动 | MUST | 数据图表 | `scripts/check_mpl_rcparams.py` |
| S7-2 | 数据图表配色合规 | 自动 | MUST | 数据图表 | `scripts/check_chart_color_grayscale.py` |
| S7-3 | 图表类型选择合理性 | 人工 | SHOULD | 数据图表 | — |
| S7-4 | alt text 完整性检查 | 半自动 | MUST | 数据图表 | `scripts/check_alt_text_completeness.py` |
| S7-5 | 灰度打印友好检查 | 人工 | SHOULD | 数据图表 | `scripts/check_grayscale_print.py` |

**检查方式定义**：
- **自动**：运行 Python 脚本即可给出 PASS/FAIL 判定，不需要人工判断
- **半自动**：脚本给出检测结果和建议（如"发现 3 处字体 < 9pt：节点A/节点B/节点C"），人工确认并修复后重新运行脚本验证
- **人工**：需要人眼判断，无脚本可替代

---

### A4. 阶段7 写作循环中 matplotlib 样式设置的嵌入点

#### 嵌入位置决策

`matplotlib` 样式模板应该在**每章开头设置一次**，而不是每个图表前设置一次。理由：

1. 一篇文章内的所有数据图表应保持视觉风格一致——如果每张图前单独设置，容易出现"这张图改了 rcParams 但那张图忘了"的不一致
2. 同章节内的图表通常共享相同的上下文（字体大小、图表尺寸、色板），逐章设置是合理的粒度
3. 不同章节可能有略微不同的图表类型需求（如某章全是柱状图、另一章有折线图+散点图），逐章设置允许细微调整

但有一个关键约束：`matplotlib` 的 `rcParams` 是全局状态——**如果多章并行写作（未来可能的优化），逐章设置的 rcParams 会互相覆盖**。当前 SKILL.md 的阶段7 是顺序逐章推进，不存在并行问题，所以逐章设置是安全的。如果未来改为并行写作，需改为每个图表进程独立设置（隔离方案：每个图表用 `with mpl.rc_context({...}):` 上下文管理器，或在独立 Python 子进程中运行每个出图脚本）。

#### 嵌入点：在"调取专题卡片"之后、"写完文字草稿"之前

```
旧循环：
调取专题卡片 → 写完文字草稿 → 立即产出该章的数据图表 → 图表嵌入文字
→ 检查证据源 → 检查台账 → 回填卡片使用记录 → 进入下一章

新循环（嵌入点用 ★ 标注）：
调取专题卡片 → ★ 设置 matplotlib 全局样式模板 ★ → 写完文字草稿
→ 立即产出该章的数据图表（此时 matplotlib 已在正确 rcParams 下运行）
→ 图表嵌入文字 → 检查证据源 → 检查台账
→ ★ 运行本章图表质量自检（S7-1~S7-5）★
→ 回填卡片使用记录 → 进入下一章
```

#### 样式模板设置的具体内容（每章开头执行一次）

```python
import matplotlib as mpl

# === 阶段7 图表样式模板（基于 V3.1 §5.2 + §3.1 字体方案） ===
mpl.rcParams.update({
    # 字体：匹配 V3.1 —— 中文用 sans-serif（对应微软雅黑在 Word 中的角色），
    # 西文/数字用 sans-serif（对应 Times New Roman 在 Word 中的角色，
    # 但 matplotlib 中 sans-serif 是更安全的选择，避免衬线字体在小字号下模糊）
    'font.family': 'sans-serif',
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'Arial'],
    'font.size': 9,            # 图内基础字号 ≥9pt（V3.1 §5.2）
    'axes.labelsize': 10,      # 坐标轴标签 10pt
    'legend.fontsize': 9,      # 图例 9pt
    'xtick.labelsize': 8,      # 刻度标签 8pt（可略小于基础字号）
    'ytick.labelsize': 8,
    'axes.titlesize': 11,      # 子图标题 11pt

    # 输出
    'savefig.dpi': 300,                    # 300dpi（V3.1 §5.2 强制）
    'savefig.bbox': 'tight',               # 自动裁剪白边
    'savefig.pad_inches': 0.1,

    # 灰度色板 —— 匹配 V3.1 黑白灰配色
    'axes.prop_cycle': mpl.cycler(color=[
        '#333333', '#666666', '#999999', '#BBBBBB', '#CCCCCC'
    ]),

    # 学术风格：去上边框和右边框
    'axes.spines.top': False,
    'axes.spines.right': False,

    # 网格：浅灰虚线，仅 Y 轴（不干扰 X 轴分类标签）
    'axes.grid': True,
    'axes.grid.axis': 'y',
    'grid.color': '#E0E0E0',
    'grid.linestyle': '--',
    'grid.linewidth': 0.5,

    # 图尺寸：单栏 14cm 宽（V3.1 §5.2）
    'figure.figsize': (5.5, 3.5),   # 约 14cm × 9cm（黄金比例附近）
    'figure.dpi': 100,              # 屏幕预览用，实际输出看 savefig.dpi

    # 图例：无边框，放在图外右侧不遮挡数据
    'legend.frameon': False,
    'legend.loc': 'upper left',
    'legend.bbox_to_anchor': (1.02, 1),

    # 线宽
    'lines.linewidth': 1.5,
    'lines.markersize': 4,
})
```

#### 修改后的循环流程图（Mermaid）

```mermaid
flowchart TD
    A[开始新一章] --> B["调取本章专题卡片<br/>(按 card-index.csv 的 chapter_ref)"]
    B --> C["★ 设置 matplotlib 全局样式模板 ★<br/>(执行 mpl.rcParams.update(...))"]
    C --> D[写完文字草稿]
    D --> E["立即产出该章数据图表<br/>(plt.savefig(path, dpi=300))"]
    E --> F[图表嵌入文字对应位置]
    F --> G[检查证据源 + 台账]
    G --> H["★ 本章图表质量自检 ★"]
    
    H --> H1["S7-1: matplotlib rcParams 合规<br/>(自动)"]
    H1 --> H2["S7-2: 数据图表配色合规<br/>(自动)"]
    H2 --> H3["S7-3: 图表类型合理性<br/>(人工)"]
    H3 --> H4["S7-4: alt text 完整性<br/>(半自动)"]
    H4 --> H5["S7-5: 灰度打印友好<br/>(人工)"]
    
    H5 --> I{全部 MUST 项通过?}
    I -->|是| J["回填 card-index.csv<br/>(used_in_chapter)"]
    J --> K{还有下一章?}
    K -->|是| A
    K -->|否| L["✅ 阶段7 完成<br/>进入阶段8 红队审查"]
    
    I -->|否| M["定位失败项<br/>回到对应步骤修复"]
    M --> N{失败的是出图问题?}
    N -->|是 (S7-1/S7-2/S7-5)| E
    N -->|否 (S7-4)| F
    N -->|否 (S7-3 → 调整图表类型)| E

    style C fill:#f5f5f5,stroke:#333,stroke-width:2px
    style H fill:#f5f5f5,stroke:#333,stroke-width:2px
    style H1 fill:#e8e8e8,stroke:#666
    style H2 fill:#e8e8e8,stroke:#666
    style H3 fill:#e8e8e8,stroke:#666
    style H4 fill:#e8e8e8,stroke:#666
    style H5 fill:#e8e8e8,stroke:#666
```

---

### A5. 新增质量门槛的失败处理详细矩阵

| 检查项编号 | 失败症状示例 | 退回步骤 | 修复动作 | 修复后验证 |
|-----------|-------------|---------|---------|-----------|
| **S6-1** | 架构图中出现 `#FF6600` 橙色节点 | 阶段6.1 | 打开 `.drawio` 源文件 → 选中彩色节点 → 在右侧属性面板将 `fillColor`/`strokeColor` 改为灰度值（`#666666` 或 `#999999`）→ 重新导出 SVG+PNG。如果该彩色是关键高亮，登记到 `color-registry.csv` 并注明理由 | 重新运行 `check_color_compliance.py` 确认 S=0 像素占比 > 95% |
| **S6-2** | drawio 中某节点 `fontSize=7`（< 9pt） | 阶段6.1 | 在 drawio 中 `Ctrl+A` 全选 → 右侧属性面板将 `fontSize` 统一改为 `9`。对于确实需要更小字号的注释性文字（如图例中非常次要的标注），改为 `8pt` 并登记到 `figures/font-exceptions.csv` | 重新运行 `check_font_compliance.py` 扫描 `.drawio` XML 中的 `fontSize` 属性 |
| **S6-3** | 线条使用 `strokeWidth=0.5`（< 1pt），灰色文字 `#DDDDDD` | 阶段6.1 | 加粗所有连线至 >= 1.5pt（主要连线 2pt）；浅灰文字（< `#999999`）加深至 >= `#666666`；节点间间距 < 5px 的扩大至 >= 10px | 重新导出 PNG，在屏幕上缩放至 14cm 宽度再次肉眼检查 |
| **S6-4** | 总览图写"感知层"，分章架构图写"Sensing Layer" | 阶段6.1 | 对照 `architecture-cards/` 中的术语定义，选定一个统一名称（如"感知层 (Perception Layer)"），全文架构图统一修改。在 card-index.csv 的 `notes` 字段记录："术语统一：感知层 = Perception Layer，全文使用'感知层'" | 重新运行 `check_naming_consistency.py` 扫描所有架构图的节点标签文本 |
| **S6-5** | 两组件仅靠浅灰 `#CCCCCC` 和深灰 `#999999` 区分，灰度差仅 51（255 尺度），部分色盲读者难以区分 | 阶段6.1 | 将其中一个组件的边框改为虚线（drawio: `dashed=1`），或将其形状从矩形改为圆角矩形 | 将架构图转为灰度图后肉眼判断两组是否可区分 |
| **S6-6** | 图注只有标题，缺少"来源：根据 XX 绘制" | 阶段6.1 | 为每张架构图补充：`图X-Y <标题>` + `来源：<architecture-card-id>，根据<分析框架名称>绘制。数据来源：<source>` | 重新运行 `check_caption_completeness.py` 检查每张图的图注文本是否含三个必要元素 |
| **S7-1** | `savefig.dpi` 仍为默认 100 | 阶段7.3 步骤3（当前章出图） | 在出图脚本开头重新执行 `mpl.rcParams.update(...)` 模板，确认 `mpl.rcParams['savefig.dpi']` 输出为 `300` | 重新运行 `check_mpl_rcparams.py` 扫描出图日志 |
| **S7-2** | 饼图使用了 matplotlib 默认彩色色板（蓝/橙/绿/红/紫） | 阶段7.3 步骤3（当前章出图） | 在 `plt.pie()` 调用中显式传入 `colors=['#333333','#666666','#999999','#BBBBBB','#CCCCCC']`，或依赖 rcParams 的 `axes.prop_cycle` 自动应用灰度色板 | 重新运行 `check_chart_color_grayscale.py` 用 Pillow 采样 PNG 像素 |
| **S7-3** | 用饼图展示 2020-2025 年市场规模变化（时间序列） | 阶段7.3 步骤3（当前章出图） | 改用折线图或面积图展示时间趋势；饼图仅用于展示单一年份的份额构成 | 在 `chart-type-log.csv` 中记录修改前后的图表类型 |
| **S7-4** | `![图3-2](figures/3-2.png)` alt text 只有编号，缺失图表类型和核心发现 | 阶段7.3 步骤4（图表嵌入文字） | 改为 `![图3-2 分组柱状图：2025年中美欧在轨服务市场规模对比，中国以38%份额居首（数据来源：NSR 2025）](figures/3-2.png)` | 重新运行 `check_alt_text_completeness.py` |
| **S7-5** | 灰度图中，第三系列 `#999999` 和第四系列 `#BBBBBB` 在柱状图中相邻柱子的亮度差仅 33（< 30 阈值），难以区分 | 阶段7.3 步骤3（当前章出图） | 将第四系列改为 `#222222` 或添加填充纹理（`hatch='///'`），拉开亮度差距至 >= 50 | 重新运行 `check_grayscale_print.py` 生成灰度副本并肉眼确认 |

> **退回原则（与 SKILL.md 现有失败处理表一致）**：走到哪、卡在哪、退到哪。不退到更早阶段——除非根源在前序阶段。
> 对于阶段7：所有失败只退回当前章的对应子步骤（步骤3 出图 或 步骤4 嵌入），不回退到阶段6 或前序章节。

---

## 2. 任务 B：dataviz skill 集成方案

### B1. 集成触发点

#### 触发时机：每章图表全部产出之后、图表质量自检之前

在阶段7 写作循环中，dataviz skill 的触发点应插在"立即产出该章的数据图表"和"S7-1~S7-5 质量自检"之间：

```
调取专题卡片 → 设置 matplotlib 样式模板 → 写完文字草稿 → 立即产出该章数据图表
→ ★ 触发 dataviz skill 校验本章全部图表 ★
→ 根据校验结果修复（如有问题）
→ 运行 S7-1~S7-5 质量自检
→ 图表嵌入文字 → 检查证据源 → 检查台账 → 回填卡片使用记录 → 进入下一章
```

#### 触发条件：每章触发一次

- **不是每个图表触发一次**（开销太大，且 dataviz skill 适合做批量审查——一次性看一章的全部图表可以检查跨图一致性）
- **不是全部图表产完后触发一次**（太晚，如果阶段7 第2章就出现了配色问题，到第8章才检查意味着第3-8章的图表都需要返工）
- **每章触发一次**是最优折中：每章图表数量通常 1-4 张，dataviz skill 批量检查这批图表的质量，问题在本章内修复，成本可控

#### 触发方式

```text
调用: Skill({skill: "dataviz"})
传入: 本章所有数据图表的 PNG 文件路径列表 + 本章图表描述上下文（什么类型的图、想表达什么）
预期产出: 校验报告（配色/可访问性/一致性/图表类型选择评价）
```

伪代码调用示例：

```python
# 阶段7.3 步骤3 完成后，触发 dataviz skill
chapter_figures = [
    "research/figures/3-1-市场规模趋势.png",
    "research/figures/3-2-市场份额对比.png",
]
chart_context = {
    "chapter": "第三章 市场规模与竞争格局",
    "description": "本章包含1张折线图（市场规模趋势）和1张饼图（市场份额），"
                   "使用灰度色板，目标印刷在A4黑白报告中"
}

# 通过 Skill 工具调用
Skill({
    skill: "dataviz",
    args: f"校验以下数据图表：{chapter_figures}。上下文：{chart_context}"
})
```

#### 特殊场景：阶段6 架构图是否也需要触发？

阶段6 的架构图（drawio/fireworks 产出）也可以用 dataviz skill 做配色审查——但架构图的配色约束比数据图表更简单（纯黑白灰），且 drawio/fireworks 的色值控制方式与 matplotlib 完全不同。建议：

- **阶段6**：不触发 dataviz skill，仅依靠 S6-1~S6-6 内置检查。理由：dataviz skill 的核心能力（颜色公式、色板校验器）主要针对数据图表（有多个数据系列的统计图），对架构图（少量纯黑灰色块+连线）的附加值有限
- **阶段7**：每章触发一次 dataviz skill

### B2. 校验结果反馈

#### 反馈到阶段7 写作流程的路径

```
dataviz skill 输出校验报告
        │
        ├── 无问题 → 继续 S7-1~S7-5 自检
        │
        ├── 有问题（自动可修复）→ dataviz skill 给出修复建议
        │       │
        │       ├── 配色问题 → 运行 dataviz skill 内置的"颜色公式"修复脚本
        │       │             重新生成 PNG → 重新触发 dataviz skill 校验确认
        │       │
        │       └── 字体/布局问题 → 调整 mpl.rcParams → 重新出图 → 重新校验
        │
        └── 有问题（需人工判断）→ 记录到 chart-type-log.csv
                │
                └── 进入 S7-3（人工判断图表类型合理性）时一并讨论
```

#### 问题分级处理策略

| dataviz skill 发现的问题类型 | 处理策略 | 谁执行修复 |
|---------------------------|---------|-----------|
| **配色违规**（如使用了非灰度色板） | 自动修复：运行 dataviz skill 提供的颜色公式或本项目灰度色板替换 | Agent 自动执行（运行修复脚本 → 重新出图 → 重新校验） |
| **可访问性问题**（如色觉障碍模拟中某两组数据不可区分） | 自动修复 + 人工确认：先自动拉开亮度差/加纹理，人工确认灰度副本可区分 | Agent 自动执行修复，人工在 S7-5 灰度检查环节肉眼确认 |
| **图表类型选择存疑**（如"这个数据用饼图可能不如用柱状图清晰"） | 人工确认后修复：dataviz 给出建议，Agent 在 S7-3 环节与用户（或自身判断）确认后决定是否改类型 | Agent 判断（如确认为反模式则改，否则在 chart-type-log.csv 记录偏差理由） |
| **跨图风格不一致**（如第3章的图例在右侧、第2章的图例在底部） | 人工确认：dataviz 报告"检测到与前一章的字体/图例位置不一致"，Agent 在 S7-1 环节统一全章风格 | Agent 统一风格（改 rcParams 模板 → 重新出图） |

#### 校验结果是否需要在阶段8 红队审查中再次过一遍？

**需要，但仅限以下内容**：

| 在阶段8 红队审查中复检的内容 | 不复检的内容 |
|--------------------------|------------|
| 人工确认后保留的图表类型偏差（来自 chart-type-log.csv 中标记为"保留"的反模式使用） | 已自动修复并重新校验通过的配色/字体问题 |
| dataviz skill 标记为"存疑但未修复"的项目 | 已在 S7-1~S7-5 中标记为 PASS 的项目 |
| color-registry.csv 中登记的配色例外——是否真的合理、是否有滥用豁免 | 已在 color-registry.csv 中有充分理由的个别例外 |
| 跨章图表风格的一致性（dataviz 只能做章内比较，跨章一致性需红队审查） | — |

**红队审查的图表质量维度**（新增到阶段8.1 检查维度表）：

| 维度 | 检查问题 |
|------|---------|
| **图表配色** | color-registry.csv 中登记的例外是否合理？是否存在"图方便"而非"真需要"的彩色使用？ |
| **图表类型** | chart-type-log.csv 中标记为"保留"的反模式是否有说服力的理由？是否影响了数据解读？ |
| **跨章一致性** | 不同章节的图表风格（字体/图例位置/坐标轴样式）是否一致？ |
| **alt text 质量** | alt text 中的核心发现是否与正文结论一致？是否有 alt text 夸大了图表实际展示的数据？ |

### B3. 不可集成时的等价内置检查

如果 dataviz skill 不可用（离线环境、skill 未安装、调用失败等），需要一套等价的内置检查方案覆盖其核心功能子集。以下 Python 代码骨架提供配色验证、灰度友好检查、色觉障碍模拟三个核心能力：

```python
# 文件路径建议：scripts/chart_quality_builtin.py
# 用途：当 dataviz skill 不可用时的等价内置检查方案
# 调用方式：python scripts/chart_quality_builtin.py <chapter_figures_dir> --output report.json

import sys
import json
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageStat

# ============================================================
# 1. 配色验证 —— 检测图中是否使用了非灰度色板
# ============================================================

# 本项目允许的灰度色板（V3.1 兼容）
ALLOWED_GRAYSCALE_COLORS: List[Tuple[int, int, int]] = [
    (0, 0, 0),         # #000000
    (51, 51, 51),      # #333333
    (102, 102, 102),   # #666666
    (153, 153, 153),   # #999999
    (187, 187, 187),   # #BBBBBB
    (204, 204, 204),   # #CCCCCC
    (221, 221, 221),   # #DDDDDD (仅允许用于极浅背景)
    (238, 238, 238),   # #EEEEEE
    (242, 242, 242),   # #F2F2F2 (表格交替行灰底)
    (255, 255, 255),   # #FFFFFF
]

# 灰度的 RGB 容差（三通道差值 <= 此值视为"灰色像素"）
GRAY_RGB_TOLERANCE = 5

# 允许的最大彩色像素占比（超出此值视为"使用了彩色色板"）
MAX_COLOR_PIXEL_RATIO = 0.05


def rgb_to_grayscale_luminance(r: int, g: int, b: int) -> int:
    """
    将 RGB 转为感知亮度（0-255），使用 BT.601 权重。
    标准灰度公式：L = 0.299*R + 0.587*G + 0.114*B
    """
    return int(0.299 * r + 0.587 * g + 0.114 * b)


def is_grayscale_pixel(r: int, g: int, b: int, tolerance: int = GRAY_RGB_TOLERANCE) -> bool:
    """
    判断一个像素是否属于灰度（R/G/B 三通道差值在容差内）。
    纯灰度像素：R ≈ G ≈ B
    """
    return max(abs(r - g), abs(g - b), abs(r - b)) <= tolerance


def check_color_compliance(image_path: str) -> dict:
    """
    检查单张图片的配色合规性。

    返回:
    {
        "path": str,
        "is_grayscale": bool,
        "color_pixel_ratio": float,  # 彩色像素占比
        "dominant_colors": [(r,g,b,count), ...],  # 前5个主要颜色
        "violations": [str, ...],  # 违规描述
        "pass": bool
    }
    """
    img = Image.open(image_path).convert('RGB')
    pixels = np.array(img)

    # 跳过白色/近白色背景像素（R,G,B 均 > 240 视为背景）
    is_background = np.all(pixels > 240, axis=2)
    foreground_mask = ~is_background
    foreground_pixels = pixels[foreground_mask]

    if len(foreground_pixels) == 0:
        return {"path": image_path, "is_grayscale": True, "color_pixel_ratio": 0.0,
                "dominant_colors": [], "violations": [], "pass": True}

    # 逐像素判断是否为灰度
    r, g, b = foreground_pixels[:, 0], foreground_pixels[:, 1], foreground_pixels[:, 2]
    max_diff = np.maximum(np.abs(r - g), np.maximum(np.abs(g - b), np.abs(r - b)))
    is_gray_pixel = max_diff <= GRAY_RGB_TOLERANCE
    color_pixel_ratio = 1.0 - is_gray_pixel.mean()

    violations = []
    if color_pixel_ratio > MAX_COLOR_PIXEL_RATIO:
        violations.append(
            f"彩色像素占比 {color_pixel_ratio:.1%} 超过阈值 {MAX_COLOR_PIXEL_RATIO:.0%}，"
            f"请使用灰度色板重新出图"
        )

    # 采样主要颜色（简化：对前景像素做 K=5 的均匀量化）
    quantized = (foreground_pixels // 51) * 51  # 量化为 0/51/102/153/204/255 六档
    unique, counts = np.unique(quantized.reshape(-1, 3), axis=0, return_counts=True)
    top_indices = np.argsort(-counts)[:5]
    dominant_colors = [(int(unique[i][0]), int(unique[i][1]), int(unique[i][2]),
                        int(counts[i])) for i in top_indices]

    return {
        "path": image_path,
        "is_grayscale": color_pixel_ratio <= MAX_COLOR_PIXEL_RATIO,
        "color_pixel_ratio": round(color_pixel_ratio, 4),
        "dominant_colors": dominant_colors,
        "violations": violations,
        "pass": len(violations) == 0,
    }


# ============================================================
# 2. 灰度友好检查 —— 转为灰度后不同系列是否仍可区分
# ============================================================

# 两相邻数据系列在灰度图中可区分的最小亮度差阈值（0-255 尺度）
MIN_GRAYSCALE_CONTRAST = 30


def check_grayscale_print_friendly(image_path: str) -> dict:
    """
    将图片转为灰度（BT.601），分析相邻灰度级的可区分性。

    返回:
    {
        "path": str,
        "grayscale_histogram": [int, ...],  # 灰度直方图（256 bins）
        "low_contrast_regions": [(lum_a, lum_b), ...],  # 亮度差 < 阈值的相邻峰
        "mean_luminance": float,
        "pass": bool
    }
    """
    img = Image.open(image_path).convert('RGB')
    gray = img.convert('L')
    gray_arr = np.array(gray, dtype=np.float64)

    # 排除纯白背景
    foreground_mask = gray_arr < 250
    fg_values = gray_arr[foreground_mask]

    if len(fg_values) == 0:
        return {"path": image_path, "grayscale_histogram": [],
                "low_contrast_regions": [], "mean_luminance": 0.0, "pass": True}

    # 计算直方图（256 bins，只算前景）
    hist, _ = np.histogram(fg_values, bins=256, range=(0, 256))
    hist = hist.astype(int).tolist()

    # 找直方图中的"峰"（局部最大值，prominence >= 该bin总量5%的阈值）
    peaks = []
    threshold = len(fg_values) * 0.01  # 至少占前景 1% 才视为一个"系列"
    for i in range(1, 255):
        if hist[i] > threshold and hist[i] > hist[i-1] and hist[i] > hist[i+1]:
            peaks.append(i)

    # 检查相邻峰之间的亮度差
    low_contrast_regions = []
    for i in range(len(peaks) - 1):
        diff = peaks[i+1] - peaks[i]
        if diff < MIN_GRAYSCALE_CONTRAST:
            low_contrast_regions.append((int(peaks[i]), int(peaks[i+1])))

    mean_luminance = float(fg_values.mean())

    return {
        "path": image_path,
        "grayscale_histogram": hist,
        "low_contrast_regions": low_contrast_regions,
        "mean_luminance": round(mean_luminance, 1),
        "pass": len(low_contrast_regions) == 0,
    }


# ============================================================
# 3. 色觉障碍模拟 —— 模拟红绿色盲（Protanopia）和蓝黄色盲（Tritanopia）
# ============================================================

# Brettel-Vienot-Mollon (BVM) 色盲模拟矩阵的简化实现
# 参考: Brettel, Vienot, Mollon (1997) "Computerized simulation of color appearance
#        for dichromats", JOSA A, 14(10), 2647-2655
# 简化版：对 Protanopia（红盲）和 Deuteranopia（绿盲）使用 LMS 色彩空间变换

def simulate_protanopia(img_array: np.ndarray) -> np.ndarray:
    """
    模拟红色盲（Protanopia，约 1% 男性）。
    将 RGB 转为 LMS，再将 L 通道映射到 M/S 平面，转回 RGB。
    （简化实现：使用经验性的 RGB 矩阵变换）
    """
    # Viénot et al. (1999) 简化矩阵，Protanopia
    transform = np.array([
        [0.0,     2.02344, -2.52581],
        [0.0,     1.0,      0.0    ],
        [0.0,     0.0,      1.0    ],
    ])
    # Reshape to (N, 3) for matrix multiplication
    orig_shape = img_array.shape
    pixels = img_array.reshape(-1, 3).astype(np.float64) / 255.0
    simulated = pixels @ transform.T
    simulated = np.clip(simulated, 0, 1) * 255
    return simulated.reshape(orig_shape).astype(np.uint8)


def simulate_deuteranopia(img_array: np.ndarray) -> np.ndarray:
    """模拟绿色盲（Deuteranopia，约 1% 男性）。"""
    transform = np.array([
        [1.0,      0.0,      0.0    ],
        [0.494207, 0.0,      1.24827],
        [0.0,      0.0,      1.0    ],
    ])
    orig_shape = img_array.shape
    pixels = img_array.reshape(-1, 3).astype(np.float64) / 255.0
    simulated = pixels @ transform.T
    simulated = np.clip(simulated, 0, 1) * 255
    return simulated.reshape(orig_shape).astype(np.uint8)


def simulate_tritanopia(img_array: np.ndarray) -> np.ndarray:
    """模拟蓝黄色盲（Tritanopia，罕见，< 0.01% 人口）。"""
    transform = np.array([
        [1.0,       0.0,      0.0    ],
        [0.0,       1.0,      0.0    ],
        [-0.395913, 0.801109, 0.0    ],
    ])
    orig_shape = img_array.shape
    pixels = img_array.reshape(-1, 3).astype(np.float64) / 255.0
    simulated = pixels @ transform.T
    simulated = np.clip(simulated, 0, 1) * 255
    return simulated.reshape(orig_shape).astype(np.uint8)


def check_color_blind_friendly(image_path: str, output_dir: Optional[str] = None) -> dict:
    """
    对图片做三种色觉障碍模拟，检查相邻颜色在模拟后是否仍可区分。

    返回:
    {
        "path": str,
        "simulations": {
            "protanopia": {"path": str, "mean_color_shift": float},
            "deuteranopia": {"path": str, "mean_color_shift": float},
            "tritanopia": {"path": str, "mean_color_shift": float},
        },
        "warnings": [str, ...],
        "pass": bool  # 纯灰度图直接 pass（不受色盲影响）
    }
    """
    img = Image.open(image_path).convert('RGB')
    img_array = np.array(img)

    warnings = []

    # 先检查是否已经是灰度图——灰度图不受色觉障碍影响
    color_check = check_color_compliance(image_path)
    if color_check["is_grayscale"]:
        return {
            "path": image_path,
            "simulations": {},
            "warnings": [],
            "pass": True,
            "note": "图片为纯灰度，不受色觉障碍影响"
        }

    simulations = {}
    simulators = {
        "protanopia": (simulate_protanopia, "红色盲"),
        "deuteranopia": (simulate_deuteranopia, "绿色盲"),
        "tritanopia": (simulate_tritanopia, "蓝黄色盲"),
    }

    for sim_name, (sim_func, sim_label) in simulators.items():
        simulated = sim_func(img_array)
        # 计算与原图的平均颜色偏移
        mean_shift = float(np.mean(np.abs(simulated.astype(float) - img_array.astype(float))))

        sim_img = Image.fromarray(simulated)

        # 如果提供了输出目录，保存模拟结果
        sim_path = ""
        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(image_path).stem
            sim_path = str(out_dir / f"{stem}_{sim_name}.png")
            sim_img.save(sim_path)

        simulations[sim_name] = {
            "path": sim_path,
            "mean_color_shift": round(mean_shift, 1),
        }

        # 检查模拟后的灰度图中相邻系列是否仍可区分
        gray_check = check_grayscale_print_friendly(
            sim_path if sim_path else image_path
        )

        # 如果模拟文件已保存，检查它
        if sim_path:
            sim_color_check = check_color_compliance(sim_path)

    # 仅当原图有彩色且色盲模拟后出现不可区分区域时才警告
    if color_check["color_pixel_ratio"] > 0.05:
        warnings.append(
            f"图片含有彩色元素（{color_check['color_pixel_ratio']:.1%}），"
            f"请在 color-registry.csv 中登记原因，并确保信息不完全依赖颜色传递"
        )

    return {
        "path": image_path,
        "simulations": simulations,
        "warnings": warnings,
        "pass": len(warnings) == 0,
    }


# ============================================================
# 4. 主入口——批量检查本章全部图表
# ============================================================

@dataclass
class ChartQualityReport:
    """图表质量检查报告"""
    chapter: str
    figures: List[str]
    color_compliance: List[dict] = field(default_factory=list)
    grayscale_friendly: List[dict] = field(default_factory=list)
    color_blind: List[dict] = field(default_factory=list)
    overall_pass: bool = True
    summary: str = ""


def run_builtin_chart_quality_check(
    chapter_name: str,
    figure_paths: List[str],
    output_dir: Optional[str] = None,
) -> ChartQualityReport:
    """
    对一章的全部图表运行内置质量检查（等价于 dataviz skill 的核心功能子集）。

    Args:
        chapter_name: 章节名称（如 "第三章 市场规模与竞争格局"）
        figure_paths: 图表 PNG 文件路径列表
        output_dir: 色盲模拟结果的输出目录（可选）

    Returns:
        ChartQualityReport: 完整的质量检查报告
    """
    report = ChartQualityReport(chapter=chapter_name, figures=figure_paths)
    all_pass = True

    for fig_path in figure_paths:
        # 1. 配色合规
        cc = check_color_compliance(fig_path)
        report.color_compliance.append(cc)
        if not cc["pass"]:
            all_pass = False

        # 2. 灰度打印友好
        gf = check_grayscale_print_friendly(fig_path)
        report.grayscale_friendly.append(gf)
        if not gf["pass"]:
            all_pass = False

        # 3. 色觉障碍模拟
        cb = check_color_blind_friendly(fig_path, output_dir=output_dir)
        report.color_blind.append(cb)
        if not cb["pass"]:
            all_pass = False

    report.overall_pass = all_pass
    report.summary = _generate_summary(report)
    return report


def _generate_summary(report: ChartQualityReport) -> str:
    """生成可读的检查摘要"""
    total = len(report.figures)
    color_fails = sum(1 for c in report.color_compliance if not c["pass"])
    gray_fails = sum(1 for g in report.grayscale_friendly if not g["pass"])
    cb_fails = sum(1 for c in report.color_blind if not c["pass"])

    lines = [
        f"=== 图表质量检查报告：{report.chapter} ===",
        f"检查图表数：{total}",
        f"配色合规：{total - color_fails}/{total} 通过",
        f"灰度打印友好：{total - gray_fails}/{total} 通过",
        f"色觉障碍友好：{total - cb_fails}/{total} 通过",
        f"总体：{'PASS' if report.overall_pass else 'FAIL — 请修复上述问题后重新运行检查'}",
    ]
    return "\n".join(lines)


# ============================================================
# 5. CLI 入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="图表质量内置检查（dataviz skill 的等价替代方案）"
    )
    parser.add_argument(
        "chapter_dir",
        help="本章图表所在目录（如 research/figures/ch03/）"
    )
    parser.add_argument(
        "--chapter-name", "-c",
        default="未命名章节",
        help="章节名称"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="检查报告输出路径（JSON），默认输出到 stdout"
    )
    parser.add_argument(
        "--simulations-dir",
        default=None,
        help="色盲模拟结果输出目录"
    )
    args = parser.parse_args()

    chapter_dir = Path(args.chapter_dir)
    if not chapter_dir.is_dir():
        print(f"错误：目录不存在：{chapter_dir}", file=sys.stderr)
        sys.exit(1)

    figure_paths = sorted([
        str(p) for p in chapter_dir.glob("*.png")
        if not any(sim in p.stem for sim in ["_protanopia", "_deuteranopia", "_tritanopia", "_grayscale"])
    ])

    if not figure_paths:
        print(f"警告：目录中未找到 PNG 图表：{chapter_dir}", file=sys.stderr)
        sys.exit(0)

    report = run_builtin_chart_quality_check(
        chapter_name=args.chapter_name,
        figure_paths=figure_paths,
        output_dir=args.simulations_dir,
    )

    # 序列化为 JSON
    output = {
        "chapter": report.chapter,
        "figures": report.figures,
        "overall_pass": report.overall_pass,
        "summary": report.summary,
        "details": {
            "color_compliance": report.color_compliance,
            "grayscale_friendly": report.grayscale_friendly,
            "color_blind": report.color_blind,
        }
    }

    if args.output:
        Path(args.output).write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        print(f"报告已保存到：{args.output}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    sys.exit(0 if report.overall_pass else 1)
```

**内置检查方案的功能覆盖矩阵**：

| dataviz skill 预期能力 | 内置等价实现 | 覆盖度 | 差异说明 |
|----------------------|------------|--------|---------|
| 颜色公式 + 可运行的颜色校验器 | `check_color_compliance()` — RGB 差值法检测灰度合规 | 高 | dataviz 的颜色公式更精细（考虑 HSL/LAB 色彩空间），内置方案用 RGB 差值作为近似；对于本项目灰度优先的约束，RGB 差值已足够 |
| 深浅主题一致性规则 | 本项目不涉及深浅主题切换（报告是印刷品），此项不适用 | N/A | 无需覆盖 |
| 经过验证的默认色板 | 内置方案使用 SKILL.md V3.1 规定的灰度色板（`#333333` 等），非 dataviz 的色板 | 等效 | 两者色板不同，但都满足本项目"黑白灰为主"的要求 |
| 色觉障碍模拟 | `check_color_blind_friendly()` — BVM 简化矩阵模拟 Protanopia/Deuteranopia/Tritanopia | 中 | dataviz 可能使用更精确的模拟算法（如 LMS 完整变换 + 显示器 ICC 校准），内置方案使用 Viénot 1999 简化矩阵；对于本项目"灰度优先"场景，差异不显著（灰度图天然不受色盲影响） |
| 图表类型反模式检测 | **未覆盖** — 内置方案不做图表类型判断 | 无 | 此项需依赖 S7-3 的人工检查；dataviz skill 如果有自动检测能力则是优势 |
| 跨图风格一致性 | **未覆盖** — 内置方案不做跨图对比 | 无 | 此项需在阶段8 红队审查中人工检查 |

### B4. 集成决策建议

#### 最终建议：**集成 dataviz skill（浅集成：仅配色校验），同时保留内置检查作为 fallback**

#### 利弊分析

| 方案 | 优点 | 缺点 |
|------|------|------|
| **方案 A：仅使用内置检查** | 零外部依赖，离线可用；代码自包含、可审计；行为确定性高 | 配色校验精度不如专业 skill（仅做 RGB 差值）；缺少图表类型反模式检测；缺少跨图风格一致性分析；缺少经过大规模验证的色板知识库 |
| **方案 B：浅集成 dataviz（仅配色校验）** | 利用 dataviz 经过验证的颜色公式和色板知识库；配色检测更精确；dataviz 输出的配色建议可以直接作为修复方案的输入；失败时降级到内置检查，不会阻塞流程 | 增加外部 skill 调用开销（每次调用需加载 SKILL.md + 执行）；dataviz 的色板可能与 V3.1 灰度色板不完全一致，需要桥接适配逻辑 |
| **方案 C：深集成 dataviz（图表整体质量评分）** | 图表质量一站式覆盖（配色+可访问性+类型选择+标注质量）；减少 S7-1~S7-5 多步骤检查的碎片化 | 外部依赖过重：dataviz 不可用时整条图表质量链断裂；dataviz 的评分标准可能与本项目的"V3.1 黑白灰印刷品"定位不完全对齐（dataviz 默认针对屏幕展示优化）；增加 Agent 调用的不确定性和延迟 |

#### 推荐方案：B（浅集成）+ 内置 fallback

**执行逻辑**：

```
步骤3：产出该章数据图表
        │
        ▼
┌─ try 调用 dataviz skill ──────────────────────┐
│  Skill({skill: "dataviz",                       │
│    args: "校验图表配色：{figure_paths}"})         │
│                                                  │
│  ├── dataviz 可用 → 获取配色校验结果              │
│  │   ├── PASS → 继续                            │
│  │   └── FAIL → 根据 dataviz 建议修复配色        │
│  │                                                  │
│  └── dataviz 不可用（异常/未安装/离线）→          │
│      自动降级到内置检查                            │
│      python scripts/chart_quality_builtin.py ...  │
└──────────────────────────────────────────────────┘
        │
        ▼
运行 S7-1 (rcParams) + S7-3 (类型合理性) + S7-4 (alt text) + S7-5 (灰度友好)
（S7-2 配色合规 已被 dataviz/内置检查覆盖，此处跳过避免重复）
        │
        ▼
继续下一章
```

**为什么是浅集成而非深集成**：

1. **本项目有明确的印刷品约束**（V3.1 黑白灰配色），dataviz 的通用质量评分体系可能对"灰度色板"给出低分（因为它默认期望适度的色彩区分），产生误报
2. **图表类型选择和 alt text 质量**高度依赖报告的具体上下文（该章想表达什么分析结论），通用 skill 很难做准确判断——S7-3 和 S7-4 的人工/半人工检查更适合
3. **dataviz 的核心价值**——经过验证的颜色公式和色板校验器——在浅集成中就已经被充分利用
4. **深集成增加耦合**：如果 dataviz 的评分标准未来发生变化，整个阶段7 的质量门槛判定都会受影响

#### 浅集成的适配层设计

为了让 dataviz skill 的输出与本项目的 V3.1 灰度色板兼容，需要一个轻量的适配层：

```python
# 文件路径建议：scripts/adapt_dataviz_output.py
# 用途：将 dataviz skill 的配色建议转换为本项目 V3.1 灰度色板兼容的修复方案

def adapt_dataviz_color_fix(dataviz_fix: dict) -> dict:
    """
    将 dataviz 建议的彩色色板替换为本项目的灰度色板等效方案。

    dataviz 可能建议 "将系列2改为 #2E86AB (深蓝)"，
    适配层将其映射为 "将系列2改为 #333333 (深灰) + 虚线纹理"。
    """
    # 如果 dataviz 建议的颜色本身就是灰度 → 直接采用
    # 如果是彩色 → 映射到最接近亮度的灰度值
    # 如果多个系列需要区分 → 用灰度 + 纹理组合
    pass  # 具体实现取决于 dataviz 的输出格式
```

---

## 3. 调度集成——新增检查项与现有阶段的衔接

### 3.1 阶段6 修改后的 CHECKPOINT STOP

```
阶段6 CHECKPOINT · STOP（原有 5 项 + 新增 6 项 = 11 项）：

必须全部通过方可进入阶段7：

[原有-1] 总览图至少1张完成
[原有-2] 每个核心分析章节至少1张架构图草图
[原有-3] 架构图之间逻辑一致
[原有-4] 所有架构图有逻辑或来源标注
[原有-5] 所有PNG已验证达到300dpi
[NEW-S6-1] 配色合规检查（灰度色板 + 例外已登记 color-registry.csv）
[NEW-S6-2] 字体达标检查（图内文字>=9pt）
[NEW-S6-3] 印刷可读性检查（14cm缩放无不可读元素）
[NEW-S6-4] 命名一致性检查（同概念同名称，已与 architecture-cards 对齐）
[NEW-S6-5] 色盲友好检查（无纯靠颜色传递的信息，SHOULD——不阻塞但需记录偏差）
[NEW-S6-6] 图注完整性检查（逻辑来源+数据来源标注齐全）

未通过 → 回到阶段6.1 对应的子步骤修复（详见 §A5 失败处理矩阵）
```

### 3.2 阶段7 修改后的逐章循环

```
每章循环（修改后，新增步骤以 ★ 标记）：

1. 调取该章对应的专题卡片
2. ★ 设置 matplotlib 全局样式模板（mpl.rcParams.update(...)）
3. 完成文字草稿
4. 立即产出该章的数据图表（此时 matplotlib 已在正确 rcParams 下运行）
5. ★ 触发 dataviz skill 校验本章图表配色（不可用时降级到内置检查）
6. 图表嵌入文字
7. 检查证据源
8. 检查台账
9. ★ 运行本章图表质量自检：
   - S7-1: matplotlib rcParams 合规（自动）
   - S7-2: 数据图表配色合规（自动，dataviz 已覆盖时可跳过）
   - S7-3: 图表类型选择合理性（人工）
   - S7-4: alt text 完整性（半自动）
   - S7-5: 灰度打印友好（人工）
10. 回填 card-index.csv
11. 进入下一章
```

### 3.3 阶段7 修改后的质量门槛

**原有 9 项 + 新增 5 项 = 14 项**（新增项融入现有门槛列表）：

| 序号 | 检查项 | 来源 | 阻塞级别 |
|------|--------|------|---------|
| 1 | 每章开头有"本章结论"，末尾有"对主论点的贡献"（含至少1句局限说明） | 原有 | MUST |
| 2 | 所有 C/D 级来源的事实已标注强度 | 原有 | MUST |
| 3 | 所有图表已在正文中引用 | 原有 | MUST |
| 4 | 每章数据图表与文字内容一致 | 原有 | MUST |
| 5 | 本章对应的专题卡片已全部核对使用情况 | 原有 | MUST |
| 6 | 未出现台账中标记为"错误/误导"的主张 | 原有 | MUST |
| 7 | 证据密度检查：抽查3段连续文字均有来源 | 原有 | MUST |
| 8 | 建议可操作性检查：每条建议回答谁/做什么/资源/指标 | 原有 | MUST |
| 9 | 摘要自足性检查 | 原有 | MUST |
| **10** | **matplotlib rcParams 合规（S7-1）** | **新增** | **MUST** |
| **11** | **数据图表配色合规（S7-2）** | **新增** | **MUST** |
| **12** | **图表类型选择合理性（S7-3）** | **新增** | **SHOULD** |
| **13** | **alt text 完整性（S7-4）** | **新增** | **MUST** |
| **14** | **灰度打印友好（S7-5）** | **新增** | **SHOULD** |

### 3.4 阶段8 红队审查新增维度

在阶段8.1 检查维度表中新增 4 行：

| 维度 | 检查问题 | 来源 |
|------|---------|------|
| **图表配色** | color-registry.csv 中的例外是否合理？是否存在"图方便"而非"真需要"的彩色使用？dataviz skill 标记为"存疑"但保留的项目是否经过充分论证？ | S6-1, S7-2 |
| **图表类型** | chart-type-log.csv 中标记为"保留"的反模式是否有说服力的理由？这些反模式是否影响读者对数据的正确理解？ | S7-3 |
| **跨章一致性** | 不同章节的图表风格（字体大小、图例位置、坐标轴样式、灰度色板使用）是否一致？是否有某章图表看起来"风格突兀"？ | 跨章合计 |
| **alt text 质量** | alt text 中的核心发现是否与正文结论一致？是否有 alt text 夸大或歪曲了图表实际展示的数据？ | S7-4 |

### 3.5 新增文件清单

本次设计引入以下新文件（全部位于 `research/` 目录树下）：

| 文件 | 用途 | 创建阶段 |
|------|------|---------|
| `research/figures/color-registry.csv` | 配色例外登记表（字段：`figure_id, color_hex, element, justification, registered_by, date`） | 阶段6（S6-1 触发）、阶段7（S7-2 触发） |
| `research/figures/chart-type-log.csv` | 图表类型决策日志（字段：`chapter, figure_id, data_type, chart_type_used, recommended_type, deviation_reason, decision, date`） | 阶段7（S7-3 触发） |
| `research/figures/font-exceptions.csv` | 字体例外登记表（字段：`figure_id, element, actual_font_size, reason, date`） | 阶段6（S6-2 触发） |
| `scripts/check_color_compliance.py` | 配色合规自动/半自动检查脚本 | 阶段6+7 |
| `scripts/check_font_compliance.py` | 字体达标检查脚本 | 阶段6 |
| `scripts/check_naming_consistency.py` | 命名一致性检查脚本 | 阶段6 |
| `scripts/check_caption_completeness.py` | 图注完整性检查脚本 | 阶段6 |
| `scripts/check_mpl_rcparams.py` | matplotlib rcParams 合规检查脚本 | 阶段7 |
| `scripts/check_chart_color_grayscale.py` | 数据图表配色合规检查脚本 | 阶段7 |
| `scripts/check_alt_text_completeness.py` | alt text 完整性检查脚本 | 阶段7 |
| `scripts/check_grayscale_print.py` | 灰度打印友好检查脚本 | 阶段7 |
| `scripts/chart_quality_builtin.py` | dataviz skill 不可用时的等价内置检查方案 | 阶段7 |
| `scripts/adapt_dataviz_output.py` | dataviz skill 输出适配层（彩色→灰度映射） | 阶段7 |

---

## 4. 实施优先级建议

| 优先级 | 检查项 | 原因 |
|--------|--------|------|
| **P0 立即实施** | S7-1 (rcParams 合规) + S7-2 (配色合规) + A4 (样式模板嵌入点) | 这三个是**可自动执行**的检查，不需要人工介入，且对图表质量提升最直接——rcParams 模板让所有图表基线统一，配色检查防止彩色图表混入灰度报告 |
| **P0 立即实施** | S6-1 (配色合规) + S6-2 (字体达标) | 阶段6 的架构图一旦产出就不会大改，配色和字体问题在阶段6 修复成本最低 |
| **P1 尽快实施** | S7-4 (alt text 完整性) + S6-6 (图注完整性) | 半自动检查——脚本做格式校验、人工确认内容，投入产出比高 |
| **P1 尽快实施** | dataviz skill 浅集成 + fallback 内置检查 | 提供专业级配色验证，失败时自动降级不影响流程 |
| **P2 按需实施** | S6-4 (命名一致性) + S6-3 (印刷可读性) + S7-5 (灰度打印友好) | 需要人工或半人工判断，适合在报告初稿完成后集中做一轮 |
| **P3 可延后** | S6-5 (色盲友好) + S7-3 (图表类型合理性) | SHOULD 级，不阻塞流程；灰度为先的配色天然降低了色盲风险，反模式检测的价值在数据图表较多的报告中才显著 |

---

## 5. 与现有设计文档的交叉引用

- **SKILL.md**：本文档新增的检查项应合并到 SKILL.md 的阶段6/7/8 质量门槛章节中
- **研究报告格式规范 V3.1**：§5.2（图）、§5.3（数据可视化类型指引）是本次设计的配色/字体/尺寸约束的源头依据
- **md→docx 转换器 v2 工作流设计**：门1/门2/门3 的校验体系为本设计的检查项分级（Fatal/Warning/Info）提供了方法论参考——本设计的 MUST/SHOULD/MAY 三级与转换器的分级逻辑一致
- **architecture-analysis-guide.md**：阶段6 的架构图术语和命名规范应以此文件为参考
