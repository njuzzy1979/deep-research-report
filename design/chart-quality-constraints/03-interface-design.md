# 功能设计文档：图表质量约束方案 —— 接口与渲染规格

> 设计者：InterfaceDesigner
> 输入依据：V3.1《研究报告格式规范》全文、SKILL.md 阶段6/7、fireworks-tech-graph style-1-flat-icon.md
> 状态：只设计不实现；本文档定义 (A) matplotlib .mplstyle 样式模板、(B) drawio/fireworks-tech-graph/Mermaid 出图约束、(C) 图表可访问性规范
> 定位：本文档是 chart-quality-constraints 的 03 号文档，消费 system-architect 的架构接口（待产出）与 model-designer 的配色约束输出（待产出），产出的 .mplstyle 文件与约束模板直接供阶段 6/7 使用

---

## 0. 本文档新增/裁决的关键决策点一览

| # | 决策 | 说明 | 是否需编排器确认 |
|---|------|------|:---:|
| I1 | 图内字号基准：≥9pt（不是 7pt 或 8pt），与 V3.1 §5.2 一致，不与麦肯锡惯例 7-8pt 妥协 | 见 §A | 否（V3.1 权威最高） |
| I2 | 图表默认宽度 14cm(5.51in)，不是 16cm——单栏是默认，双栏需显式指定 | 见 §A.2 | 否 |
| I3 | 网格线默认关闭（`axes.grid: False`）——学术报告惯例，按需开启 | 见 §A.2 | 否 |
| I4 | drawio 自动生成图的文字字号基准：标签 12pt、标题 14pt——比标准 SVG 14/16 各降 2pt，因为 drawio SVG 导出无 dpi 缩放控制，在 300dpi PNG 重采样后尺寸会放大 | 见 §B.1 | 否 |
| I5 | drawio MCP 生成时注入 MUST 约束文本（prompt 级约束），SHOULD 约束仅在生成后由人工检查 | 见 §B.1 | 否 |
| I6 | fireworks-tech-graph 箭头颜色全部改为灰度——原 style-1 的蓝/红/绿/紫语义色全部废弃，改用线型（实线/虚线/点线）区分 | 见 §B.2 | 否（V3.1 §5.2 黑白灰为主色） |
| I7 | Mermaid 图表灰度化不依赖 `%%{init}%%` 主题变量——Mermaid 原生灰度支持有限，保留尽力而为的 `themeVariables` 约束，其余靠生成后 SVG 颜色替换脚本兜底 | 见 §B.3 | 是（是否需要开发 SVG 颜色替换脚本） |
| I8 | alt text 分为"架构图"与"数据图表"两类模板，前者侧重"图中展示了什么结构/层次/关系"，后者侧重"数据来源/主要发现/关键数值" | 见 §C.2 | 否 |
| I9 | 灰度可区分性检查函数设计为 Python 函数签名 + 实现逻辑说明，不实际运行——因为该检查依赖已渲染的 PNG 像素数据，与 matplotlib figure 对象不是同一抽象层 | 见 §C.3 | 否 |

---

## A. matplotlib 完整 RC 样式模板

### A.0 设计说明

本模板设计为 `plt.style.use()` 直接加载的 `.mplstyle` 文件。所有参数值均标注了来源（V3.1 条款号或自主推断）。**中文字体路径不做硬编码**，通过 `font.sans-serif` 回退链实现——matplotlib 会按顺序查找第一个可用的字体。

模板文件位置建议：`design/chart-quality-constraints/deep-research-report.mplstyle`。阶段 7 出图时，在 `plt.style.use('path/to/deep-research-report.mplstyle')` 后创建图形。

### A.1 字体设置

所有字体设置来源于 V3.1 §3.1 字体方案与 §5.2 图内文字字号要求。

```ini
# ============================================================
# deep-research-report.mplstyle
# 深度研究报告专用 matplotlib 样式模板
# 依据：V3.1《研究报告格式规范》
# 使用方式：plt.style.use('path/to/deep-research-report.mplstyle')
# ============================================================

# ---- A1. 字体体系 (V3.1 §3.1) ----
# 中文字体：宋体（SimSun）为首选
# 西文字体：Times New Roman（或 STIXGeneral 作后备）
# 注：SimSun 在 Windows 预装；macOS/Linux 无 SimSun 时，回退链自动尝试
#     Noto Serif CJK SC → Songti SC → serif
#     （matplotlib 按 font.sans-serif 列表顺序查找第一个可用字体）
font.sans-serif: SimSun, Noto Serif CJK SC, Songti SC, DejaVu Sans, serif
font.serif: Times New Roman, STIXGeneral, DejaVu Serif, serif

# 正文字体族：默认使用 sans-serif 回退链（宋体是 serif，但 matplotlib
# 对中文字体的查找路径统一走 sans-serif 列表——这是 mpl 的已知惯例）
font.family: sans-serif

# 数学字体（V3.1 §3.1）：使用 STIXGeneral 与正文 TNR 协调
# stix 是 matplotlib 内置的 STIX 字体，风格接近 Times
mathtext.fontset: stix

# 中文负号正确显示（V3.1 无直接条款，但 matplotlib 默认 Unicode 负号
# 在部分中文字体下显示为方框，关闭后使用 ASCII 连字符 "-" 代替）
axes.unicode_minus: False
```

### A.2 图表元素样式

```ini
# ---- A2. 图表元素样式 ----

# ----- 图形尺寸 ----- (V3.1 §5.2 单栏图宽度≤14cm)
# 14cm / 2.54 ≈ 5.51 inch → 取 5.5 inch（含坐标轴标签和标题的容纳空间）
# 默认高宽比：1/1.618（黄金比例）→ 高度约 3.4 inch；正方形图用 (5.5, 5.5)
figure.figsize: 5.5, 3.4
# DPI 300 作为渲染分辨率，配合 savefig.dpi 保证 PNG 输出达标
figure.dpi: 150
# 图形背景透明（嵌入 docx 时无白框冲突）
figure.facecolor: white

# ----- 轴线 ----- (V3.1 §5.2 黑白灰为主色，自主推断)
axes.linewidth: 0.8
axes.edgecolor: #333333
axes.facecolor: white
# 默认不显示网格线（学术报告惯例——网格线增加视觉噪音；
# 如有特殊需要，按图单独开启：ax.grid(True, ...)）
axes.grid: False

# ----- 刻度线 ----- (自主推断，学术图表惯例)
# 刻度线朝内（in），避免与轴线重叠时视觉混淆
xtick.direction: in
ytick.direction: in
# 主刻度线的长度和宽度
xtick.major.size: 3.5
ytick.major.size: 3.5
xtick.major.width: 0.8
ytick.major.width: 0.8
# 次刻度线（如有）
xtick.minor.size: 2.0
ytick.minor.size: 2.0
xtick.minor.width: 0.6
ytick.minor.width: 0.6
# 刻度标签字号（V3.1 §5.2 坐标轴标签 10pt，此处为刻度数字，比轴标签小半号，取 9pt）
xtick.labelsize: 9
ytick.labelsize: 9
xtick.color: #000000
ytick.color: #000000

# ----- 坐标轴标签 ----- (V3.1 §5.2 坐标轴标签 10pt)
axes.labelsize: 10
axes.labelcolor: #000000

# ----- 标题 ----- (自主推断：图内标题介于正文 11pt 与图注 9pt 之间，取 10pt)
axes.titlesize: 10
axes.titlecolor: #000000
axes.titleweight: bold

# ----- 图例 ----- (V3.1 §5.2 图例 9pt)
legend.fontsize: 9
# 图例边框：浅灰细线或无边框（无边框更干净，推荐）
legend.frameon: True
legend.edgecolor: #cccccc
legend.framealpha: 0.8
legend.fancybox: False
# 图例默认位置：best（自动选择最少遮挡的位置）
legend.loc: best

# ----- 网格线（当用户显式开启时）----- (自主推断：浅灰虚线)
# 不在默认 mplstyle 中开启，但定义推荐参数供参考：
# grid.color: #e0e0e0
# grid.linestyle: --
# grid.linewidth: 0.5
# grid.alpha: 0.7
```

### A.3 配色绑定——灰度色板

```ini
# ---- A3. 配色绑定 (V3.1 §11 配色方案) ----
# 将灰度色板绑定到 axes.prop_cycle
# 来源：V3.1 §11——主色 #000000, 辅助 #555555, 背景 #F2F2F2, 强调 #333333
# 灰度序列基于 V3.1 色板派生 8 级灰度，相邻级亮度差异 ≥15%（可辨识）

# <!--REF:02-model-design.md#A1--> 配色约束等级说明：
# 当 model-designer 产出 02-model-design.md 后，以下 8 色序列应
# 替换为 model-designer 正式定义的调色板。当前序列为接口设计阶段
# 的占位值，基于 V3.1 §11 灰度约束自主推断。
#
# 约束等级：
#   LEVEL-1（硬性）: 所有颜色必须落在灰度空间（R=G=B），禁止使用彩色
#   LEVEL-2（硬性）: 最浅色 L* ≥ 20（保证在白底上可辨识）
#   LEVEL-3（推导）: 相邻色 L* 差值 ≥ 15%（保证灰度打印时可区分）
#   LEVEL-4（建议）: 序列长度 6-10（覆盖大多数图表的系列数需求）

# 8 级灰度（从深到浅）——占位值，供 model-designer 替换
# #1C1C1C  #333333  #4D4D4D  #666666  #808080  #999999  #B3B3B3  #CCCCCC
#    L*≈10   L*≈20    L*≈30    L*≈40    L*≈50    L*≈60    L*≈70    L*≈78

# 折线图颜色循环（line.cycler）
axes.prop_cycle: cycler('color', ['#1C1C1C', '#4D4D4D', '#808080', '#B3B3B3',
                                   '#333333', '#666666', '#999999', '#CCCCCC'])

# 注意：柱状图的颜色也受 axes.prop_cycle 控制（matplotlib 中 patch.cycler
# 默认与 axes.prop_cycle 绑定），无需单独设置 patch.cycler
# 如需折线图用线型区分而柱状图用填充密度区分，可在创建 axes 后单独设置：
#   ax.set_prop_cycle(color=gray_colors, hatch=['', '//', '\\\\', 'xx', '..', 'oo', '**', '++'])
```

### A.4 印刷可读性验证

```ini
# ---- A4. 印刷可读性验证 (V3.1 §5.2) ----

# savefig 配置：每次保存时强制 300dpi + tight bbox
# V3.1 §5.2 要求 PNG 300dpi+ 含 pHYs 元数据
# matplotlib 的 savefig.dpi=300 直接写正确的 pHYs，无需 Pillow 二次处理
savefig.dpi: 300
savefig.bbox: tight
savefig.pad_inches: 0.1
# PNG 格式（唯一嵌入格式，V3.1 §5.2）
savefig.format: png
```

**配套验证函数**（Python 函数签名 + 实现逻辑，写在 `.py` 文件而非 `.mplstyle` 中）：

```python
# 文件位置建议：scripts/validate_figure_readability.py
# 供阶段 7 每张图 savefig 后调用

import matplotlib.pyplot as plt
import matplotlib.text as mtext
from typing import List, Tuple


def check_figure_text_legibility(
    fig: plt.Figure,
    output_width_cm: float = 14.0,
    min_text_size_pt: float = 9.0,
    min_axis_label_pt: float = 10.0,
    min_legend_pt: float = 9.0,
) -> List[str]:
    """检查 matplotlib figure 的文字可读性（V3.1 §5.2 合规性验证）。

    V3.1 §5.2 要求：
      - 图内文字 ≥ 9pt
      - 坐标轴标签 10pt
      - 图例 9pt
      - 单栏图宽度 ≤ 14cm

    本函数遍历 figure 中所有 Text 对象，对比实际字号与要求字号，
    返回所有不合规项的警告信息列表。返回空列表 = 全部通过。

    Args:
        fig: 已完成绑定的 matplotlib Figure 对象（在 savefig 之前调用）
        output_width_cm: 输出的目标宽度（厘米），默认 14cm（单栏）
        min_text_size_pt: 图内文字最小字号（pt），默认 9.0
        min_axis_label_pt: 坐标轴标签最小字号（pt），默认 10.0
        min_legend_pt: 图例文字最小字号（pt），默认 9.0

    Returns:
        List[str]: 不合规项的描述列表，每项格式如
                   "图例文字 'Series A' 字号 7.5pt < 要求 9.0pt"
                   空列表表示全部通过

    实现逻辑:
        1. 验证 fig.get_size_inches()[0] * 2.54 ≤ output_width_cm
           （Figure 宽度英寸值 × 2.54 = 厘米值）
        2. 遍历 fig.texts（全局文字）+ 每个 axes 的：
           - ax.title（标题）
           - ax.xaxis.label / ax.yaxis.label（坐标轴标签）
           - ax.xaxis.get_ticklabels() / ax.yaxis.get_ticklabels()（刻度标签）
           - ax.texts（ax 级文字注释）
           - ax.legend().get_texts()（图例文字，如存在）
        3. 对每个 Text 对象，读取 get_fontsize()
        4. 按文字角色对照阈值：
           - 坐标轴标签 → min_axis_label_pt
           - 图例文字 → min_legend_pt
           - 其他 → min_text_size_pt
        5. 收集所有字号不达标的项，格式化为警告信息返回
        6. 特殊处理：
           - 刻度标签：V3.1 无直接规定刻度数字字号，
             本函数取 min_text_size_pt - 0.5 = 8.5pt 作为刻度数字阈值
             （比图内文字低半号是学术图表的常见惯例）
           - 水印/脚注类文字（text 的 alpha < 0.3 或 zorder 很低的）：
             跳过不检查——这类不是图的数据内容

    注意：本函数是"检查"不是"修复"——它只返回警告列表，
    调用方自行决定是否调整后重新出图。
    典型调用模式：
        warnings = check_figure_text_legibility(fig)
        if warnings:
            for w in warnings:
                print(f"⚠ {w}")
    """
    warnings = []

    # Step 1: 宽度检查
    fig_width_inch = fig.get_size_inches()[0]
    fig_width_cm = fig_width_inch * 2.54
    if fig_width_cm > output_width_cm + 0.1:  # 0.1cm 容差
        warnings.append(
            f"图形宽度 {fig_width_cm:.1f}cm > 限制 {output_width_cm}cm"
        )

    # Step 2: 收集所有需要检查的 (文字对象, 角色类型) 对
    # 角色标识：'axis_label' | 'legend' | 'tick' | 'general'
    text_checks: List[Tuple[mtext.Text, str]] = []

    for ax in fig.axes:
        # 坐标轴标签 (V3.1 §5.2: 10pt)
        if ax.xaxis.label.get_text():
            text_checks.append((ax.xaxis.label, 'axis_label'))
        if ax.yaxis.label.get_text():
            text_checks.append((ax.yaxis.label, 'axis_label'))

        # 标题
        if ax.title.get_text():
            text_checks.append((ax.title, 'general'))

        # 刻度标签
        for label in ax.xaxis.get_ticklabels():
            if label.get_text():
                text_checks.append((label, 'tick'))
        for label in ax.yaxis.get_ticklabels():
            if label.get_text():
                text_checks.append((label, 'tick'))

        # 图例文字 (V3.1 §5.2: 9pt)
        legend = ax.get_legend()
        if legend is not None:
            for txt in legend.get_texts():
                if txt.get_text():
                    text_checks.append((txt, 'legend'))

        # ax 内的 text 注释
        for txt in ax.texts:
            # 跳过透明度极低的（可能是水印）
            if hasattr(txt, 'get_alpha') and txt.get_alpha() is not None and txt.get_alpha() < 0.3:
                continue
            text_checks.append((txt, 'general'))

    # 全局 texts（fig.texts，如 suptitle、fig-level 注释）
    for txt in fig.texts:
        text_checks.append((txt, 'general'))

    # Step 3: 逐项检查字号
    # 刻度数字阈值：比 min_text_size_pt 低 0.5pt（学术图表惯例）
    tick_threshold = max(min_text_size_pt - 0.5, 7.0)  # 不低于 7pt 绝对下限

    for txt, role in text_checks:
        actual_size = txt.get_fontsize()
        if role == 'axis_label':
            required = min_axis_label_pt
        elif role == 'legend':
            required = min_legend_pt
        elif role == 'tick':
            required = tick_threshold
        else:
            required = min_text_size_pt

        if actual_size < required - 0.1:  # 0.1pt 浮点容差
            text_preview = txt.get_text()[:30]  # 截断过长文字
            warnings.append(
                f"{role}文字 '{text_preview}' 字号 {actual_size:.1f}pt "
                f"< 要求 {required:.1f}pt"
            )

    return warnings
```

### A.5 完整 .mplstyle 文件

以上所有 `.mplstyle` 片段合并后即为完整文件。建议保存路径：`design/chart-quality-constraints/deep-research-report.mplstyle`。阶段 7 的典型使用模式：

```python
import matplotlib.pyplot as plt
plt.style.use('design/chart-quality-constraints/deep-research-report.mplstyle')

# 创建图形（使用样式中的默认 figsize: 5.5×3.4 inch）
fig, ax = plt.subplots()

# 绘图...
ax.plot(x, y1, label='系列 1')
ax.plot(x, y2, label='系列 2')
ax.set_xlabel('年份')
ax.set_ylabel('市场规模（十亿美元）')
ax.set_title('2020-2030年全球OOS市场规模趋势')
ax.legend()

# 保存前验证可读性
from scripts.validate_figure_readability import check_figure_text_legibility
warnings = check_figure_text_legibility(fig)
if warnings:
    for w in warnings:
        print(f"【图表可读性警告】{w}")
    # 根据警告调整后重新 savefig，或记录到 issue log

fig.savefig('research/figures/3-1-市场规模趋势.png')
plt.close(fig)
```

---

## B. drawio/fireworks-tech-graph/Mermaid 出图约束

### B.0 总则

所有架构图/流程图/技术架构图的输出必须符合 V3.1 的灰度配色要求（§5.2：黑白灰为主色，§11：主色 #000000 / 辅助 #555555 / 背景 #F2F2F2 / 强调 #333333）。以下按工具分别给出 MUST（硬性注入 prompt 的约束文本）和 SHOULD（生成后人工检查）两类约束。

MUST 约束必须原样嵌入生成 prompt 中；SHOULD 约束在生成后由人工核对，不阻断流程但记录到阶段 6 质量门槛检查中。

### B.1 drawio MCP prompt 约束

#### B.1.1 通用约束文本（MUST——注入所有 drawio MCP 调用）

以下文本**必须**逐字嵌入 `mcp__drawio__create_diagram` 调用时传入的 prompt 末尾（不论使用 mermaid 还是 xml 参数）：

```
【强制样式约束——不可违反】

1. 配色：
   - 所有填充色、线条色、文字色必须仅使用以下色值：
     文字：#000000（纯黑）
     节点边框：#333333（深灰，1.5pt 粗）
     节点填充：#FFFFFF（纯白）或 #F2F2F2（浅灰，用于区分层次/分组）
     箭头/连线：#333333（深灰，1.5pt 粗）
     强调区域背景：#F2F2F2（浅灰）
   - 禁止使用任何彩色（蓝/红/绿/紫/橙/黄等）
   - 不同层次或组件通过边框粗细（1pt/2pt）和填充密度区分，
     不使用颜色区分

2. 字体：
   - 节点标签：12pt
   - 子标签/注释：10pt
   - 标题：14pt Bold
   - 字体族：Arial（西文）/ 微软雅黑（中文），无衬线
   - 文字颜色：#000000

3. 节点样式：
   - 矩形节点：无圆角或 rx=4,ry=4（小圆角），边框 #333333
   - 分层容器（泳道/分组框）：边框 2pt #333333，填充 #F2F2F2，
     标签在左上角或顶部居中
   - 数据库/存储节点：圆柱形（如支持）或 rx=12 圆角矩形

4. 箭头样式：
   - 颜色：#333333
   - 线宽：1.5pt
   - 箭头类型：实心三角（block arrow）或不带箭头（取决于语义——
     数据流用箭头，结构关系用无箭头连线）
   - 虚线：用于异步/间接关系（stroke-dasharray: 8,4）
   - 不同流向通过线型区分：实线=主流程，虚线=辅助/异步流程，
     点线（stroke-dasharray: 2,2）=数据依赖

5. 背景：纯白 #FFFFFF

6. 布局：自顶向下（TB）优先于自左向右（LR），除非内容本身更适合横向
```

#### B.1.2 Mermaid 语法的约束版本

当使用 `mermaid` 参数传入 Mermaid 语法时，上述约束转化为以下 Mermaid 直接可用的指令：

```
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryTextColor': '#000000',
    'primaryBorderColor': '#333333',
    'lineColor': '#333333',
    'secondaryColor': '#F2F2F2',
    'tertiaryColor': '#FFFFFF',
    'fontFamily': 'Arial, Microsoft YaHei, sans-serif',
    'fontSize': '12px'
  },
  'flowchart': {
    'nodeSpacing': 50,
    'rankSpacing': 60,
    'curve': 'basis'
  }
}}%%
```

**使用说明**：将以上 `%%{init: ...}%%` 块作为 Mermaid 代码块的**第一行**（在任何 `graph TD` 或 `flowchart TB` 之前）。后续写正常的 Mermaid 图语法。如果图中有多个流向，在 Mermaid 中用 `linkStyle` 设置线型：

```
linkStyle 0 stroke:#333333,stroke-width:2px          /* 主流程，实线 */
linkStyle 1 stroke:#333333,stroke-width:1.5px,stroke-dasharray:8  /* 辅助流程，虚线 */
```

#### B.1.3 mxGraphModel XML 的约束版本

当使用 `xml` 参数传入 draw.io XML 时，在根 `<mxGraphModel>` 后添加一个约束样式说明节点（作为注释或不可见图层），在 prompt 中明确要求：

```
【XML 生成约束】

1. 所有 mxCell 的 style 属性中：
   - fillColor 仅允许：#FFFFFF 或 #F2F2F2
   - strokeColor 仅允许：#333333
   - fontColor 仅允许：#000000
   - strokeWidth 取 1 或 2（节点边框）/ 1.5（连线）
   - fontSize 取 10 或 12 或 14

2. 连线（edge）的 style 中：
   - edgeStyle=orthogonalEdgeStyle（直角走线，最清晰）
   - 虚线用 dashed=1 属性
   - 点线用 dashed=1;dashPattern=2 2

3. 禁止出现 gradientColor、glass=1、shadow=1 等装饰性属性
4. 背景色通过 mxGraphModel 的 background 属性设为 #FFFFFF
5. 页面尺寸：background="#FFFFFF" pageWidth="960" pageHeight="720"
```

#### B.1.4 SHOULD 约束（生成后人工检查）

| # | 检查项 | 判断标准 |
|---|--------|---------|
| S1 | 所有文字可读 | 将 .drawio 导出为 PNG (300dpi) 后在 100% 缩放比例下查看，所有标签清晰可辨 |
| S2 | 无彩色残留 | 打开 .drawio 文件，检查所有元素的色值——不存在 #000000/#333333/#F2F2F2/#FFFFFF 以外的颜色 |
| S3 | 箭头方向正确 | 每条连线的起点和终点与源/目标节点对应 |
| S4 | 层次逻辑清晰 | 分层架构图中，同一层的节点水平/垂直对齐，不同层之间间距一致 |
| S5 | 图例完整（如有多种线型/填充） | 图中有虚线/点线/不同填充密度时，必须在左下角提供图例说明 |

### B.2 fireworks-tech-graph 样式参数

#### B.2.0 灰度色板映射

原 style-1-flat-icon.md 的色彩体系全部映射到 V3.1 §11 灰度色板：

| 原 style-1 色值 | 颜色语义 | 映射到 V3.1 灰度 | 灰度色值 |
|-----------------|---------|-----------------|---------|
| `#2563eb` (blue-600) | Flow A (main) | 强调深灰（实线） | `#333333` |
| `#dc2626` (red-600) | Flow B (alt) | 辅助深灰（虚线） | `#555555` |
| `#16a34a` (green-600) | Flow C (data) | 中灰（点线） | `#666666` |
| `#9333ea` (purple-600) | Flow D (async) | 浅灰（短虚线） | `#999999` |
| `#eff6ff / #dbeafe` | Blue tint bg | 浅灰背景 | `#F2F2F2` |
| `#fef2f2 / #fee2e2` | Red tint bg | 白色背景 | `#FFFFFF` |
| `#111827` (gray-900) | Text primary | 纯黑 | `#000000` |
| `#6b7280` (gray-500) | Text secondary | 辅助文字 | `#555555` |
| `#d1d5db` (gray-300) | Box stroke | 深灰 | `#333333` |
| `#ffffff` | Background | 白色（不变） | `#FFFFFF` |

#### B.2.1 三种模板的推荐 JSON 参数

**模板 1：architecture（架构图）**

```json
{
  "title": "六层技术架构全景",
  "global_style": {
    "font_family": "Microsoft YaHei, Arial, sans-serif",
    "title_font_size": 14,
    "node_label_font_size": 12,
    "sublabel_font_size": 10,
    "text_color": "#000000",
    "background": "#FFFFFF"
  },
  "nodes": [
    {
      "id": "layer1",
      "label": "感知层",
      "sublabel": "传感器 / 数据采集",
      "x": 40, "y": 40, "width": 880, "height": 80,
      "fill": "#FFFFFF",
      "stroke": "#333333",
      "stroke_width": 1.5,
      "corner_radius": 4
    }
  ],
  "arrows": [
    {
      "source": "layer1",
      "target": "layer2",
      "label": "原始数据流",
      "color": "#333333",
      "width": 1.5,
      "style": "solid",
      "arrow_type": "block"
    }
  ]
}
```

**模板 2：data-flow（数据流图）**

```json
{
  "global_style": {
    "font_family": "Microsoft YaHei, Arial, sans-serif",
    "font_size": 12,
    "text_color": "#000000",
    "background": "#FFFFFF"
  },
  "nodes": [
    {
      "id": "source",
      "label": "数据源",
      "shape": "cylinder",
      "fill": "#F2F2F2",
      "stroke": "#333333",
      "stroke_width": 1.5
    }
  ],
  "arrows": [
    {
      "source": "source",
      "target": "process",
      "label": "实时流 (Kafka)",
      "color": "#333333",
      "width": 1.5,
      "style": "solid",
      "arrow_type": "block"
    },
    {
      "source": "cache",
      "target": "process",
      "label": "批量同步 (每日)",
      "color": "#555555",
      "width": 1.5,
      "style": "dashed",
      "arrow_type": "open"
    }
  ]
}
```

**模板 3：flowchart（流程图）**

```json
{
  "global_style": {
    "font_family": "Microsoft YaHei, Arial, sans-serif",
    "font_size": 12,
    "text_color": "#000000",
    "background": "#FFFFFF"
  },
  "nodes": [
    {
      "id": "start",
      "label": "开始",
      "shape": "rounded_rect",
      "fill": "#333333",
      "text_color": "#FFFFFF",
      "stroke": "#333333",
      "stroke_width": 1.5,
      "corner_radius": 16
    },
    {
      "id": "decision",
      "label": "满足条件?",
      "shape": "diamond",
      "fill": "#FFFFFF",
      "stroke": "#333333",
      "stroke_width": 1.5
    },
    {
      "id": "process",
      "label": "处理步骤",
      "shape": "rect",
      "fill": "#FFFFFF",
      "stroke": "#333333",
      "stroke_width": 1.5
    }
  ],
  "arrows": [
    {
      "source": "start",
      "target": "process",
      "color": "#333333",
      "width": 1.5,
      "style": "solid",
      "arrow_type": "block"
    },
    {
      "source": "decision",
      "target": "process",
      "label": "否",
      "color": "#555555",
      "width": 1.5,
      "style": "dashed",
      "arrow_type": "open"
    }
  ]
}
```

**箭头样式约定（三种模板通用）**：

| 流向类型 | 线型 | 颜色 | 线宽 | 箭头 | 说明 |
|---------|------|------|------|------|------|
| 主流/同步 | 实线 (solid) | `#333333` | 1.5pt | block（实心三角） | 主线数据流/调用链/正常路径 |
| 辅助/异步 | 虚线 (dashed, 8,4) | `#555555` | 1.5pt | open（空心三角） | 异步消息/批处理/后台任务 |
| 数据依赖 | 点线 (dotted, 2,2) | `#666666` | 1pt | none（无箭头） | 配置依赖/数据源引用 |
| 反馈/回环 | 点划线 (dashdot) | `#999999` | 1pt | open | 反馈回路/迭代循环 |

### B.3 Mermaid 主题约束

Mermaid 通过 `%%{init: {...}}%%` 控制主题。但 Mermaid 的 `themeVariables` 覆盖能力有限——部分元素（如子图背景、甘特图任务条）不完全受 `themeVariables` 控制。以下配置做到"尽力而为"，**不满足的项由 SVG 颜色替换脚本兜底**（见 §B.3.2）。

#### B.3.1 推荐主题配置

```
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryTextColor': '#000000',
    'primaryBorderColor': '#333333',
    'lineColor': '#333333',
    'secondaryColor': '#F2F2F2',
    'tertiaryColor': '#FFFFFF',
    'noteBkgColor': '#F2F2F2',
    'noteTextColor': '#000000',
    'noteBorderColor': '#333333',
    'fontFamily': 'Arial, Microsoft YaHei, sans-serif',
    'fontSize': '12px',
    'labelTextColor': '#000000',
    'labelBoxBkgColor': '#F2F2F2',
    'labelBoxBorderColor': '#333333',
    'altBackground': '#FFFFFF',
    'errorBkgColor': '#F2F2F2',
    'errorTextColor': '#000000',
    'classText': '#000000',
    'signalColor': '#333333',
    'signalTextColor': '#000000'
  },
  'flowchart': {
    'nodeSpacing': 40,
    'rankSpacing': 50,
    'curve': 'basis',
    'htmlLabels': true,
    'useMaxWidth': true
  },
  'sequence': {
    'actorMargin': 50,
    'boxMargin': 10,
    'boxTextMargin': 5,
    'diagramMarginX': 50,
    'diagramMarginY': 10,
    'messageMargin': 40,
    'mirrorActors': true,
    'width': 150
  }
}}%%
```

**已知局限**（Mermaid 主题变量无法完全覆盖的元素）：
- `subgraph` 的标题栏背景色：部分 Mermaid 版本不支持 themeVariable 覆盖，可能保留浅蓝色
- `gantt` 的任务条颜色：`themeVariables` 对该图类型支持不完整
- `pie` 的扇区颜色：完全不支持通过 themeVariables 控制——需要依赖默认 `%%init%%` 的 `theme: 'base'` + 灰度调色板，但 Mermaid 的 `base` 主题 pie 颜色仍可能含彩色

#### B.3.2 SVG 颜色替换脚本（兜底，需编排器确认 I7）

由于 Mermaid 的灰度化能力有限，**推荐**在 Mermaid SVG 生成后运行一个 Python 脚本，将 SVG 中所有非灰度颜色（R != G 或 R != B 的像素/填充色/描边色）替换为最接近的灰度值。脚本不在此处详设（复杂度较高，涉及 XML 解析 + 颜色空间转换），但给出接口签名：

```python
# 文件位置建议：scripts/mermaid_grayscale.py

def mermaid_svg_to_grayscale(
    input_svg_path: str,
    output_svg_path: str,
    color_map: dict = None,
) -> str:
    """将 Mermaid 生成的 SVG 转换为纯灰度版本。

    替换策略：
    1. 解析 SVG XML，遍历所有带 fill / stroke / color 属性的元素
    2. 将非灰度颜色（hex 或 rgb()）转换为 L* 最接近的灰度值
    3. 保留白色 (#FFFFFF / #FFF / white) 和黑色 (#000000 / #000 / black) 不变
    4. 已有的灰度值（R == G == B）保持不变

    Args:
        input_svg_path: Mermaid 原始生成的 SVG 文件路径
        output_svg_path: 灰度化后的 SVG 输出路径
        color_map: 可选的颜色映射字典，{'#原色值': '#目标灰度值'}，
                   缺省使用 luminance 公式自动转换

    Returns:
        处理报告字符串，列出替换了多少个颜色值
    """
    pass  # 实现细节不在此处展开（见 I7 裁决）
```

---

## C. 图表可访问性规范

### C.1 图注（figure caption）规范

#### C.1.1 图注必须包含的信息

与 V3.1 §4.2/§5.2 对齐，图注必须包含以下信息（按出现顺序）：

| 要素 | 格式 | 是否必须 | 示例 |
|------|------|:---:|------|
| 编号 | `图X-Y`（X=章号，Y=章内序号） | 是 | `图3-2` |
| 标题 | 简洁描述图表内容的一句话 | 是 | `2025-2030年全球OOS市场规模预测` |
| 单位（如有） | `（单位：XX）` | 数据图表必须有 | `（单位：十亿美元）` |
| 数据来源 | `数据来源：来源机构, 日期` | 是 | `数据来源：NSR, Euroconsult [链接](URL)` |
| 关键说明（可选） | 解释图表中需要读者注意的细节 | 否 | `注：2026年后的数据为预测值` |
| 灰度打印提示（条件触发） | 当多个系列的填充在灰度下可能混淆时 | 条件触发 | 见下方 C.1.2 |

**图注格式标准**（V3.1 §3.3/§4.2）：

```
图X-Y 标题（单位：XX）
数据来源：XXX
注：补充说明（如有）
```

例如：
```
图3-2 2025-2030年全球OOS市场规模预测（单位：十亿美元）
数据来源：NSR, Euroconsult [https://example.com/report](https://example.com/report)
注：2026年后数据为基于2020-2025年CAGR的趋势外推预测，非实际报告值。
灰度打印时系列3(柱状图填充)与系列4(柱状图填充)的密度差异较小，
建议参考线型区分（系列3=实线边框，系列4=虚线边框）。
```

#### C.1.2 灰度打印提示触发规则

**触发条件**：当一张图中有 ≥ 2 个数据系列使用**相同的几何形状**（如都是柱状图、都是折线、都是散点），且其**灰度填充亮度差 < 15% L\*** 时，必须添加灰度打印提示。

提示模板：
```
注：灰度打印时[系列名A]和[系列名B]的[填充/线型]差异较小，请参考[区分特征]。
```

**判定逻辑**（供阶段 7 出图时自查）：

```python
# 伪代码
def needs_grayscale_notice(series_colors: list[tuple[int,int,int]]) -> bool:
    """当任意两个系列的颜色亮度差 < 15% L* 时返回 True"""
    for i, c1 in enumerate(series_colors):
        for c2 in series_colors[i+1:]:
            l1 = rgb_to_L_star(c1)  # CIE L* 感知亮度
            l2 = rgb_to_L_star(c2)
            if abs(l1 - l2) < 15:
                return True
    return False
```

当返回 `True` 时，应在图注中添加一行"注：灰度打印时..."。

### C.2 alt text 规范

alt text 的设计目标：即使读者因视觉障碍使用屏幕阅读器、或因网络问题无法加载图片，也能通过 alt text 理解图表的核心内容。alt text **不是**图注的复读——它应提供与图注互补的信息。

#### C.2.1 架构图 alt text 模板

**结构**：图类型 → 图中展示的结构/层次 → 关键组件数量与名称 → 主要关系/流向

**模板**：
```
[图类型]展示了[系统/领域]的[层次数量]层架构。
从上到下依次为：[层次1]（含[N]个组件：[组件列表]）、
[层次2]（含[N]个组件：[组件列表]）...。
[层次A]通过[关系类型]与[层次B]相连。
主要数据流：[来源] → [经过的组件] → [目标]。
图的原始标题为"[图注标题]"。
```

**示例**：
```
架构图展示了星载边缘AI系统的六层技术架构。
从上到下依次为：应用层（含星上自主决策、实时目标识别2个组件）、
算法层（含模型推理引擎、在线学习模块2个组件）、
平台层（含容器运行时、资源调度器2个组件）、
数据层（含时序数据库、知识图谱2个组件）、
网络层（含星间链路管理、地面站通信2个组件）、
感知层（含多光谱传感器、姿态传感器2个组件）。
各层之间通过标准化API接口相连。
主要数据流：感知层 → 数据层 → 算法层 → 应用层，
控制反馈沿相反方向传递。
图的原始标题为"图2-1 星载边缘AI六层技术架构全景"。
```

#### C.2.2 数据图表 alt text 模板

**结构**：图类型 → 展示的数据维度 → 主要发现（趋势/对比/极值） → 数据来源 → 关键数值

**模板**：
```
[图类型]，展示[数据维度]。
主要发现：[关键趋势或对比结论]。
[系列名1]从[起始值] [增长/下降]至[终止值]（[时间段]）；
[系列名2]保持在[数值区间]。
数据来源：[来源名称]，图表原始标题为"[图注标题]"。
```

**示例（折线图）**：
```
折线图，展示2020至2030年全球在轨服务(OOS)市场规模的预测趋势。
主要发现：市场预计从2025年的48.3亿美元增长至2030年的74.5亿美元
（年均复合增长率约9.1%）。
三条预测曲线中：NSR预测最高（2030年74.5亿美元），
Euroconsult预测居中（2030年62.1亿美元），
Northern Sky Research预测最低（2030年55.8亿美元）。
2024年之前三条曲线基本吻合，之后分歧加大。
数据来源：NSR、Euroconsult、Northern Sky Research，
图表原始标题为"图3-2 2025-2030年全球OOS市场规模预测（单位：十亿美元）"。
```

**示例（分组柱状图）**：
```
分组柱状图，对比四家主要OOS企业在2024年和2025年的融资额。
Northrop Grumman融资额最高（2025年12亿美元），
Astroscale增长最快（从2024年1.2亿美元增至2025年4.5亿美元，增长275%），
Momentus融资额下降（从2024年2.8亿美元降至2025年1.9亿美元）。
四家企业合计融资从2024年11.2亿美元增至2025年25.5亿美元。
数据来源：各企业年报及SEC申报文件，
图表原始标题为"图3-4 主要OOS企业融资对比（2024 vs 2025，单位：亿美元）"。
```

#### C.2.3 alt text 生成流程

```
1. 数据图表：阶段 7 出图时，由生成图表的代码块同时产出 alt text 字符串
   架构图：阶段 6 出图时，由生成图的 Agent 在 prompt 中要求同时输出 alt text
2. alt text 写入 Markdown 的图片引用中：
   ![图3-2 2025-2030年全球OOS市场规模预测](research/figures/3-2-市场规模.png)
   改为：
   ![图3-2 2025-2030年全球OOS市场规模预测](research/figures/3-2-市场规模.png "折线图，展示2020至2030年全球在轨服务市场...")
   其中 title 属性（"..." 内的内容）即 alt text
3. md→docx 转换器（阶段 9）从 title 属性提取 alt text 写入 Word 图片的
   "替换文字"（Alt Text）属性
```

### C.3 灰度打印友好检查

#### C.3.1 检查函数设计

```python
# 文件位置建议：scripts/validate_grayscale_legibility.py
# 供阶段 7 每张数据图 savefig 后调用

from typing import List, Tuple, Optional
import numpy as np


def check_grayscale_distinguishability(
    png_path: str,
    min_luminance_diff: float = 15.0,
    series_mask_paths: Optional[List[str]] = None,
) -> List[str]:
    """检查 PNG 图表中不同数据系列在灰度下的视觉区分度。

    V3.1 §5.2 要求"黑白灰为主色"，这意味着所有颜色在灰度打印时
    必须可区分。本函数将 PNG 转换为 CIE L* 灰度空间，分析不同
    数据系列的亮度分布，检测"两个系列在灰度下无法区分"的情况。

    Args:
        png_path: 已导出的图表 PNG 文件路径（300dpi）
        min_luminance_diff: 两个系列之间的最小 L* 差值阈值
                           （CIE L* 范围 0-100，差值 < 15 通常难以区分）
        series_mask_paths: 可选。如果提供了每个系列的独立 mask PNG
                          （同尺寸的二值图，白色=该系列的像素区域），
                          则按 mask 精确分离各系列的像素进行分析。
                          如果不提供，则使用颜色聚类自动推断系列边界
                          （准确度较低，仅作近似检查）。

    Returns:
        List[str]: 不可区分的系列对列表，每项格式如
                   "系列1(L*≈45.2)与系列3(L*≈46.8)在灰度下难以区分
                   （L*差=1.6 < 阈值15），建议调整线型或填充密度"
                   空列表 = 全部可区分

    实现逻辑：
        Step 1: 加载 PNG，从 PIL Image 转为 numpy RGB 数组
        Step 2: 对每个像素计算 CIE L* 感知亮度：
                L* = 116 * f(Y/Yn) - 16
                其中 Y = 0.2126*R + 0.7152*G + 0.0722*B
                      Yn = 255（白点的 Y 值）
                      f(t) = t^(1/3) if t > 0.008856
                             else 7.787*t + 16/116
        Step 3: 按系列分离像素：
                - 如果有 series_mask_paths：每张 mask 的白像素区域
                  对应一个系列，收集这些像素的 L* 值
                - 如果没有 mask：使用 K-Means (K=系列数+1，+1 为背景)
                  在 RGB 空间聚类，每个聚类对应一个系列，
                  背景聚类（最浅色，L* > 85）自动排除
        Step 4: 对每对系列 (i, j)，计算：
                - mean_L_i, mean_L_j（各自 L* 均值）
                - L* 差值 |mean_L_i - mean_L_j|
                - 如果差值 < min_luminance_diff → 标记不可区分
        Step 5: 返回所有不可区分对的警告列表

    典型调用模式：
        warnings = check_grayscale_distinguishability(
            'research/figures/3-2-市场规模.png')
        if warnings:
            for w in warnings:
                print(f"【灰度可区分性警告】{w}")
            # 建议：
            # - 折线图：修改 line.cycler 中的线型（实线/虚线/点线/点划线）
            # - 柱状图：修改柱状图的 hatch 图案
            #   （'/' '\\\\' 'x' '.' 'o' '*' '+'）或边框线型
            # - 散点图：修改 marker 形状（'o' 's' '^' 'D' 'v' '<' '>' 'p'）
    """
    from PIL import Image

    warnings = []

    # Step 1: 加载图片
    img = Image.open(png_path).convert('RGB')
    pixels = np.array(img)  # shape: (H, W, 3), dtype=uint8

    # Step 2: RGB → CIE L* 转换
    # 先归一化到 [0, 1]
    rgb_norm = pixels.astype(np.float64) / 255.0
    # 线性 sRGB → 线性亮度 Y（使用 ITU-R BT.709 系数，与 matplotlib 一致）
    Y = 0.2126 * rgb_norm[:, :, 0] + 0.7152 * rgb_norm[:, :, 1] + 0.0722 * rgb_norm[:, :, 2]
    # CIE L* 公式
    delta = 6.0 / 29.0
    delta_cube = delta ** 3
    # Y/Yn，Yn = 1.0（归一化后白点 = 1）
    t = Y.copy()
    mask_linear = t <= delta_cube
    mask_nonlinear = ~mask_linear
    L_star = np.zeros_like(t)
    L_star[mask_nonlinear] = 116.0 * (t[mask_nonlinear] ** (1.0/3.0)) - 16.0
    L_star[mask_linear] = 116.0 * (t[mask_linear] / (3.0 * delta**2) + 4.0/29.0) - 16.0

    # Step 3: 按系列分离像素
    if series_mask_paths:
        # 精确模式：使用提供的 mask
        series_L_values = []
        for mask_path in series_mask_paths:
            mask = np.array(Image.open(mask_path).convert('L')) > 128
            series_L = L_star[mask]
            if len(series_L) > 0:
                series_L_values.append(series_L)
    else:
        # 近似模式：K-Means 聚类
        from sklearn.cluster import KMeans  # 可选依赖，如不可用则跳过
        try:
            # 只对非背景像素做聚类（L* < 90 的像素）
            fg_mask = L_star < 90
            fg_pixels = rgb_norm[fg_mask]  # (N, 3)
            if len(fg_pixels) < 100:
                return []  # 像素太少，无法做有意义的聚类分析
            # 尝试 K=2,3,4,5,... 用肘部法则选最优
            # 简化：假设 3-5 个系列，取最常见的 n_clusters
            n_series_guess = min(5, max(2, len(fg_pixels) // 500))
            kmeans = KMeans(n_clusters=n_series_guess, random_state=42, n_init=10)
            labels = kmeans.fit_predict(fg_pixels)
            series_L_values = []
            for i in range(n_series_guess):
                series_L = L_star[fg_mask][labels == i]
                if len(series_L) > 50:
                    series_L_values.append(series_L)
        except ImportError:
            # sklearn 不可用 → 退化为简单的 L* 直方图分箱
            # 找到 L* 直方图的峰值，每个峰对应一个系列
            hist, bins = np.histogram(L_star[L_star < 90], bins=50, range=(0, 90))
            # 找局部极大值 > 背景噪声
            peak_threshold = np.max(hist) * 0.1
            peaks = []
            for i in range(1, len(hist) - 1):
                if hist[i] > peak_threshold and hist[i] > hist[i-1] and hist[i] > hist[i+1]:
                    peaks.append((bins[i] + bins[i+1]) / 2)
            if len(peaks) < 2:
                return []  # 无法可靠地识别多个系列
            # 将每个峰附近的像素归为一个系列
            series_L_values = []
            for peak in peaks:
                half_width = 5  # L* ±5 范围内的像素归入此系列
                mask = (L_star > peak - half_width) & (L_star < peak + half_width)
                if np.sum(mask) > 50:
                    series_L_values.append(L_star[mask])

    # Step 4: 逐对比较 L* 均值
    n_series = len(series_L_values)
    if n_series < 2:
        return []  # 只有一个系列，无需比较

    means = [np.mean(vals) for vals in series_L_values]

    for i in range(n_series):
        for j in range(i + 1, n_series):
            diff = abs(means[i] - means[j])
            if diff < min_luminance_diff:
                warnings.append(
                    f"系列{i+1}(L*≈{means[i]:.1f})与系列{j+1}(L*≈{means[j]:.1f})"
                    f"在灰度下难以区分（L*差={diff:.1f} < 阈值{min_luminance_diff}），"
                    f"建议调整线型或填充密度"
                )

    return warnings
```

#### C.3.2 建议的处理措施速查

当 `check_grayscale_distinguishability` 返回非空结果时，按图表类型选择对应的修复策略：

| 图表类型 | 问题系列对不可区分时的修复策略 | 修改方式 |
|---------|---------------------------|---------|
| 折线图 | 修改线型 | `linestyle` 参数：`'-'` `'--'` `'-.'` `':'` 循环使用 |
| 分组柱状图 | 修改填充图案 | `hatch` 参数：`''` `'/'` `'\\\\'` `'x'` `'.'` `'o'` 循环使用 |
| 散点图 | 修改标记形状 | `marker` 参数：`'o'` `'s'` `'^'` `'D'` `'v'` `'p'` 循环使用 |
| 面积图 | 修改填充透明度 | `alpha` 参数：0.3 / 0.5 / 0.7 递进；或加 hatch 叠加 |
| 饼图/环形图 | 修改边框样式 | `wedgeprops` 中的 `edgecolor` 和 `linewidth` 变体 |

---

## D. 使用示例总览

### D.1 阶段 7 数据图表的完整出图流程

```python
# Step 1: 加载样式
import matplotlib.pyplot as plt
plt.style.use('design/chart-quality-constraints/deep-research-report.mplstyle')

# Step 2: 根据数据选择图表类型和尺寸
# 单栏图（默认）：使用 mplstyle 默认的 5.5×3.4 inch
# 双栏图：显式覆盖 figsize
# fig, ax = plt.subplots(figsize=(6.3, 3.9))  # 约 16cm 宽

fig, ax = plt.subplots()

# Step 3: 绘图（使用灰度色板中的颜色）
# 颜色序列直接使用 prop_cycle 自动分配的灰度色
import matplotlib as mpl
colors = mpl.rcParams['axes.prop_cycle'].by_key()['color']

ax.plot(x, y1, label='NSR预测', color=colors[0], linewidth=1.5)
ax.plot(x, y2, label='Euroconsult预测', color=colors[1],
        linewidth=1.5, linestyle='--')
ax.plot(x, y3, label='NSR保守预测', color=colors[2],
        linewidth=1.5, linestyle='-.')

ax.set_xlabel('年份')
ax.set_ylabel('市场规模（十亿美元）')
ax.set_title('2025-2030年全球OOS市场规模预测')
ax.legend()

# Step 4: 保存前验证
from scripts.validate_figure_readability import check_figure_text_legibility
warnings = check_figure_text_legibility(fig)
if warnings:
    for w in warnings:
        print(f"【图表可读性警告】{w}")

fig.savefig('research/figures/3-2-市场规模预测.png')
plt.close(fig)

# Step 5: 灰度可区分性检查
from scripts.validate_grayscale_legibility import check_grayscale_distinguishability
gray_warnings = check_grayscale_distinguishability(
    'research/figures/3-2-市场规模预测.png')
if gray_warnings:
    for w in gray_warnings:
        print(f"【灰度可区分性警告】{w}")
    # 调整线型/填充后重新 savefig

# Step 6: 生成图注和 alt text
caption = (
    "图3-2 2025-2030年全球OOS市场规模预测（单位：十亿美元）\n"
    "数据来源：NSR, Euroconsult [链接](URL)\n"
    "注：2026年后数据为预测值。"
)
if gray_warnings:
    caption += (
        "\n注：灰度打印时Euroconsult预测(虚线)与NSR保守预测(点划线)"
        "的线型可区分，注意图例对应关系。"
    )

alt_text = (
    "折线图，展示2020至2030年全球在轨服务(OOS)市场规模的预测趋势。"
    "主要发现：市场预计从2025年的48.3亿美元增长至2030年的74.5亿美元"
    "（年均复合增长率约9.1%）。"
    "三条预测曲线中：NSR预测最高（2030年74.5亿美元），"
    "Euroconsult预测居中（2030年62.1亿美元），"
    "NSR保守预测最低（2030年55.8亿美元）。"
    "数据来源：NSR、Euroconsult。"
)

# 写回 Markdown 时使用 alt text：
# ![图3-2 2025-2030年全球OOS市场规模预测](research/figures/3-2-市场规模预测.png "{alt_text}")
```

### D.2 阶段 6 drawio 架构图的完整出图流程

```
1. 准备 Mermaid 或 XML 内容
2. 构造 prompt = 图的内容描述 + B.1.1 的 MUST 约束文本
3. 调用 mcp__drawio__create_diagram(prompt, mermaid=..., xml=...)
4. 将返回的 XML 写入 research/figures/2-1-技术架构.drawio
5. 导出 SVG（人工编辑用）和 PNG（docx 嵌入用，300dpi）
6. 对照 B.1.4 SHOULD 约束表做人工检查
7. 产出 alt text（按 C.2.1 模板）
8. 在 Markdown 中嵌入图片引用（含 alt text）
```

---

## E. 与上下游的联动事项

| 联动对象 | 内容 |
|---------|------|
| model-designer（02-model-design.md） | A.3 的 8 色灰度序列为占位值，待 model-designer 产出正式配色后替换 `<!--REF:02-model-design.md#A1-->` |
| system-architect（01-architecture.md） | 待产出后确认 validate_figure_readability.py 和 validate_grayscale_legibility.py 在阶段 7/8 的调用位置和接口契约 |
| workflow-designer（03-workflow.md） | 图注/alt text/灰度可区分性检查应纳入阶段 7 质量门槛检查清单 |
| SKILL.md（阶段 6/7） | 本设计中的命令模板和参数约定需同步到 SKILL.md 的对应阶段 |
| fireworks-tech-graph（style-1-flat-icon.md） | B.2.0 的灰度色板映射表替代原彩色方案，需确认模板是否支持本设计中要求的线型参数（dashed/dotted/dashdot） |

---

## F. 待编排器裁决的决策点（汇总）

| # | 决策 | 影响 | 建议 |
|---|------|------|------|
| I7 | 是否需要开发 Mermaid SVG 灰度颜色替换脚本 | 如果不做，Mermaid 图可能含彩色（pie 图尤其明显），与 V3.1 §5.2 黑白灰要求冲突 | 建议优先级 P1：对 pie/gantt 等无法通过 themeVariables 完全控制的图类型必须有兜底方案；对 flowchart/sequence 图（themeVariables 覆盖较好）可暂缓 |
| 配色引用 | model-designer 产出 8 色灰度序列后，需有人更新本文档 A.3 的注释占位 | 当前占位色板"能用但不最优"——L* 间隔不够均匀 | 标注为 `<!--REF:02-model-design.md#A1-->`，编排器在 model-designer 完成后指派更新 |

