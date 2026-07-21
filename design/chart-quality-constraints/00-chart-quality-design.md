# 图表绘制质量约束方案 —— 主设计文档

> 产出方式：上游分析（现状缺口诊断）→ 直接设计定稿
> 日期：2026-07-21 ｜ 状态：待用户审批
> 适用范围：deep-research-report skill 阶段6（核心架构图）与阶段7（数据图表）

---

## 0. 文档集索引

| 文档 | 内容 |
|------|------|
| **00-chart-quality-design.md**（本文档） | 汇总索引、现状分析、裁决总表、约束等级体系、与 SKILL.md/V3.1 联动修订总览 |
| [matplotlib-report-style.mplstyle](matplotlib-report-style.mplstyle) | matplotlib rcParams 完整样式模板（灰度色板、中文字体、字号体系、色盲安全） |
| [chart-quality-checklist.md](chart-quality-checklist.md) | 架构图/数据图表质量检查清单（自动化/人工、阻塞级别、适用工具） |
| [skill-revision-proposal.md](skill-revision-proposal.md) | SKILL.md 阶段6/7 质量门槛修订建议（精确措辞+插入位置） |

---

## 1. 现状分析摘要

### 1.1 现有约束强度分布

```
约束强度
  ▲
  │  [强] PNG 300dpi+pHYs ─── 有自动检查 ✅
  │  [强] SVG 语法正确性 ─── 有自动检查 ✅
  │  [强] 三件套文件齐全 ─── 有自动检查 ✅
  │
  │  [弱] 单栏≤14cm ─── 声明式，无自动检查 ⚠️
  │  [弱] 图内文字≥9pt ─── 声明式，完全依赖工具默认值 ⚠️
  │  [弱] 配色"黑白灰为主" ─── 声明式，无精确色值 ⚠️
  │  [弱] 图表类型选择 ─── 有指引矩阵，无强制校验 ⚠️
  │
  │  [无] matplotlib 全局样式 ─── 除 dpi=300 外零约束 ❌
  │  [无] 跨图颜色一致性 ─── 没有注册表/命名规范 ❌
  │  [无] 色盲无障碍 ─── 完全没提及 ❌
  │  [无] 印刷可读性验证 ─── 没有 14cm 缩放下字号检查 ❌
  │  [无] dataviz skill 集成 ─── 未利用 ❌
  ▼
```

### 1.2 各工具的控制力梯度

| 工具 | 控制力 | 约束策略 |
|------|--------|---------|
| **matplotlib** | 完全可控（rcParams/代码级） | 提供 `.mplstyle` 模板文件 + 代码骨架，阶段7 Agent 必须加载 |
| **drawio** | 低——Mermaid 语法的样式能力有限，XML 可精确控制但复杂度高 | 提供 prompt 约束模板（结构化的样式要求文本），注入到出图 AI 的 prompt 中 |
| **fireworks-tech-graph** | 中等——颜色/字体由模板文件控制 | 传入 JSON 参数中补充约束字段；建议模板升级 |
| **Mermaid** | 极低——运行时渲染，style 有限 | 仅限 ≤15 节点简单图，不作样式强约束 |

---

## 2. 裁决总表

### 2.1 配色方案（Q-01 ~ Q-06）

| # | 裁决 | 级别 |
|---|------|------|
| **Q-01** | 报告图表统一使用"学术灰度"色板，主色 #000000、深灰 #555555、浅灰 #999999、背景白 #FFFFFF。多系列时使用 7 档灰度梯度：`#000000 / #333333 / #555555 / #777777 / #999999 / #BBBBBB / #DDDDDD`（明度 L 值均匀分布） | MUST |
| **Q-02** | 强调色仅保留一种：`#D62728`（Tol 红色，色觉障碍者仍可感知其与灰度系列的亮度差异）。**禁止**使用其他彩色作为图表强调色 | MUST |
| **Q-03** | 饼图/环形图使用灰度填充 + 不同阴影线样式（`/`、`\`、`x`、`-`、`|`、`+`）区分扇区，而非仅靠灰度值。这是为了灰度打印友好和色觉障碍者友好（Color Universal Design，参照 Paul Tol's qualitative scheme 与 Okabe-Ito 调色板原理） | MUST |
| **Q-04** | 同一概念（如"感知层""网络层""应用层"）在同一份报告的所有图中必须使用相同的颜色。需要在阶段6出第一张图时建立颜色映射注册表（见 §3.3） | MUST |
| **Q-05** | 架构图节点边框统一 1pt #333333，填充根据层级深度递减灰度（顶层浅灰 #F2F2F2，底层深灰 #DDDDDD） | SHOULD |
| **Q-06** | 图表底色统一白色 #FFFFFF（不做透明或灰色底），确保 Word 嵌入后与纸白一致 | MUST |

### 2.2 字体与字号（Q-07 ~ Q-12）

| # | 裁决 | 级别 |
|---|------|------|
| **Q-07** | matplotlib 全局字体：中文 宋体（SimSun）+ 西文 Times New Roman + 等宽 Consolas。通过 rcParams 设置，不允许各图单独设置字体族 | MUST |
| **Q-08** | matplotlib 字号体系：标题 12pt / 坐标轴标签 10pt / 刻度 9pt / 图例 9pt / 注释 8pt。其中坐标轴标签 10pt 和图例 9pt 是 V3.1 §5.2 原文约束 | MUST |
| **Q-09** | drawio 出图时，prompt 中必须声明：所有文本元素字号 ≥12px（对应 9pt），标题 ≥14px（对应 10.5pt），字体族 = Arial/Times New Roman | MUST |
| **Q-10** | fireworks-tech-graph 模板中的默认字号必须 ≥12px。若 JSON 传入的节点 label 过长导致在 14cm 宽度下字号被压缩到 <9pt，应拆分节点或缩短 label | SHOULD |
| **Q-11** | 印刷可读性检查：对于 drawio/ fireworks 生成的图，在导出 PNG 后检查宽度 ≥1102px（14cm × 300dpi / 2.54 ≈ 1654px）。**<1102px → WARNING**（与转换器已有的 W-IMG-02 一致，复用同一阈值） | MUST |
| **Q-12** | 图内不得出现 <8pt 的文字（任何工具）。阶段6/7 质量门槛人工抽查 | SHOULD |

### 2.3 图表类型选择（Q-13 ~ Q-16）

| # | 裁决 | 级别 |
|---|------|------|
| **Q-13** | 扩展 V3.1 §5.3 的推荐表为"数据类型 → 首选图表 → 次选 → 禁止"三级决策表。当 Agent 选择"禁止"类型时，必须在质量门槛检查中给出解释 | MUST |
| **Q-14** | 禁止使用 3D 效果的任何图表（3D 饼图、3D 柱状图、3D 曲面图）——3D 投影扭曲数据比例，是学术图形公认的反模式 | MUST |
| **Q-15** | 饼图仅限 ≤5 个扇区。>5 项的类别数据使用横向条形图（horizontal bar），按值排序 | MUST |
| **Q-16** | 双 Y 轴图必须用不同灰度线型+图例明确标注两条 Y 轴的含义，且两条轴线颜色与对应的数据系列颜色一致 | MUST |

### 2.4 可访问性（Q-17 ~ Q-19）

| # | 裁决 | 级别 |
|---|------|------|
| **Q-17** | 所有图表必须标注数据来源（"数据来源：XXX"），位于图注末尾或图表下方。即使 V3.1 已要求，此处重申为 MUST——防止 Agent 省略 | MUST |
| **Q-18** | 图表必须有有意义的 alt text / 图题。图题应描述图表的核心发现而非仅"X与Y的关系图"（如"2020-2026 年中国 SSA 企业融资额呈指数增长，2026 年突破 50 亿元"而非"融资额变化趋势图"） | SHOULD |
| **Q-19** | 架构图节点颜色必须在灰度打印下仍可区分——即不同层级/类别的节点不仅靠灰度值区分，还应有形状、边框样式、或标签前缀等辅助线索 | MUST |

### 2.5 质量门槛与工具集成（Q-20 ~ Q-23）

| # | 裁决 | 级别 |
|---|------|------|
| **Q-20** | 阶段6 质量门槛新增 3 项：配色一致性检查、颜色映射注册表完整性、PNG 分辨率达标（全部 MUST） | MUST |
| **Q-21** | 阶段7 质量门槛新增 3 项：matplotlib rcParams 加载确认、图表类型合规检查、色盲友好检查（前两项 MUST，第三项 SHOULD） | MUST |
| **Q-22** | 阶段7 写作循环步骤 3（"立即产出该章的数据图表"）中插入一步：出图前先执行 `plt.style.use('design/chart-quality-constraints/matplotlib-report-style.mplstyle')` | MUST |
| **Q-23** | 若项目环境中 dataviz skill 可用，在阶段7 首张数据图表产出后进行颜色校验（触发：`/dataviz` 的色彩校验器）。若不可用，使用内置的 `check_colors()` 函数（见 §3.6）作为等价替代 | SHOULD |

---

## 3. 详细设计

### 3.1 灰度色板精确定义

```
学术灰度色板（Academic Grayscale Palette）

  主色系（7 档明度梯度）：
  ┌──────────┬──────────┬───────┬──────────────────────┐
  │ 名称      │ 色值     │ 用法   │ 色觉障碍亮度对比      │
  ├──────────┼──────────┼───────┼──────────────────────┤
  │ Black     │ #000000  │ 标题/主轴线/主要数据系列  │ L=0    │
  │ Gray-80   │ #333333  │ 第二数据系列/节点边框     │ L≈20   │
  │ Gray-60   │ #555555  │ 第三数据系列/次要网格线   │ L≈33   │
  │ Gray-40   │ #777777  │ 第四数据系列              │ L≈47   │
  │ Gray-20   │ #999999  │ 第五数据系列/辅助标注     │ L≈60   │
  │ Gray-10   │ #BBBBBB  │ 第六数据系列              │ L≈73   │
  │ Gray-05   │ #DDDDDD  │ 第七数据系列/浅底         │ L≈87   │
  │ White     │ #F2F2F2  │ 表格交替行/定义框底色     │ L≈95   │
  │ PureWhite │ #FFFFFF  │ 图底/单元格白底          │ L=100  │
  └──────────┴──────────┴───────┴──────────────────────┘

  强调色（仅一种）：
  Tol-Red: #D62728 — CUD 安全红色，亮度 L≈40，与灰度系列有明显亮度差

  禁止色：蓝/绿/黄/紫/橙等彩色（防止不同图中同一概念配色不一致）
```

### 3.2 matplotlib rcParams 样式模板设计

```
执行方式（阶段7 写作循环步骤 3 之前）：
  plt.style.use('design/chart-quality-constraints/matplotlib-report-style.mplstyle')

核心 rcParams 配置（精确值见 .mplstyle 文件）：

  [字体]
  font.family:           sans-serif
  font.sans-serif:       SimSun, Times New Roman, DejaVu Sans
  font.size:             10.0            # V3.1: 坐标轴标签10pt
  axes.titlesize:        12.0            # 标题稍大
  axes.labelsize:        10.0
  xtick.labelsize:       9.0             # V3.1: 刻度9pt
  ytick.labelsize:       9.0
  legend.fontsize:       9.0             # V3.1: 图例9pt

  [颜色]
  axes.prop_cycle:       cycler('color', ['#000000','#333333','#555555','#777777','#999999','#BBBBBB','#DDDDDD'])
  axes.edgecolor:        '#000000'
  xtick.color:           '#000000'
  ytick.color:           '#000000'
  grid.color:            '#999999'

  [布局]
  figure.dpi:            300
  figure.figsize:        8, 4.5          # 16:9 比例（≈14cm×8cm）
  figure.facecolor:      white
  axes.facecolor:        white
  axes.grid:             True
  axes.spines.top:       False           # 学术惯例：隐藏顶部/右侧脊线
  axes.spines.right:     False
  grid.alpha:            0.3

  [线条]
  lines.linewidth:       1.5
  lines.markersize:      6.0

  [图例]
  legend.frameon:        True
  legend.framealpha:     0.9
  legend.edgecolor:      '#DDDDDD'

  [保存]
  savefig.dpi:           300
  savefig.bbox:          tight
  savefig.pad_inches:    0.1
```

### 3.3 跨图颜色映射注册表

在 `research/figures/color-registry.csv` 中维护：

```csv
concept,color_hex,shape_hint,layer,first_used_fig,notes
感知层,#DDDDDD,矩形,1,3-1,六层架构最顶层
传输层,#BBBBBB,矩形,2,3-1,
数据融合层,#999999,矩形,3,3-1,
算法层,#777777,矩形,4,3-1,
平台层,#555555,矩形,5,3-1,
应用层,#333333,矩形,6,3-1,
国家队阵营,#333333,圆角矩形,无,4-1,left side
上市企业阵营,#777777,圆角矩形,无,4-1,center
民营公司阵营,#BBBBBB,圆角矩形,无,4-1,right side
```

**规则**：
- 阶段6 首张架构图出图后，立即将图中的颜色映射登记到 `color-registry.csv`
- 后续每张架构图/数据图表出图前，先查 `color-registry.csv`——若已有映射则复用
- 若图中出现新概念（注册表无记录），登记新的映射
- 阶段6 质量门槛第2项（新增）：`color-registry.csv` 至少覆盖所有核心架构图的节点

### 3.4 图表类型选择决策表（扩展 V3.1 §5.3）

```
┌─────────────────────┬──────────────┬──────────────┬────────────────┐
│ 数据类型             │ 首选         │ 次选         │ 禁止           │
├─────────────────────┼──────────────┼──────────────┼────────────────┤
│ 时间序列（≤5条线）   │ 折线图       │ 面积图       │ 3D 折线图      │
│ 时间序列（>5条线）   │ 小多组图     │ 折线图+图例  │ 多色折线堆叠    │
│ 类别对比（≤5项）     │ 柱状图（竖） │ 点图         │ 3D 柱状图      │
│ 类别对比（>5项）     │ 条形图（横） │ 柱状图       │ 饼图           │
│ 占比（≤5项）         │ 饼图+hatch  │ 环形图+hatch │ 3D 饼图        │
│ 占比（>5项）         │ 条形图（横） │ 树图         │ 饼图           │
│ 排名                  │ 条形图（横） │ 棒棒糖图     │ 饼图           │
│ 分布                  │ 直方图       │ 箱线图       │ 3D 直方图      │
│ 相关性                │ 散点图       │ 六边形bin图  │ 3D 散点图      │
│ 多维对比              │ 雷达图       │ 平行坐标图   │ 3D 曲面图      │
│ 流程/层级              │ 流程图       │ —            │                │
│ 竞争定位              │ 2×2 矩阵    │ 气泡图       │ 3D 气泡图      │
│ 地理分布              │ 等值线图     │ —            │ 填充椭圆       │
│ 前后对比              │ 哑铃图       │ 分组柱状图   │ 双饼图         │
│ 部分-整体+时间        │ 堆叠面积图   │ 堆叠柱状图   │ 堆叠饼图       │
└─────────────────────┴──────────────┴──────────────┴────────────────┘
```

### 3.5 drawio prompt 约束模板

每次调用 `mcp__drawio__create_diagram` 时，在 Mermaid/XML 描述**之后**注入以下文本：

```
图表样式约束（必须遵守）：
1. 配色：仅使用黑色(#000000)、灰色(#555555)、浅灰(#999999)、极浅灰(#DDDDDD)、白色(#FFFFFF)。
   不同层级/模块通过灰度深度区分，不用彩色。
2. 强调色：仅 #D62728（暗红），用于高亮关键节点，全图最多 3 处。
3. 字体：所有文本 ≥12px（约 9pt）。标题 ≥14px（约 10.5pt）。
4. 边框：节点边框 1pt、#333333。箭头线宽 1.5pt、#000000。
5. 形状：同层级节点使用相同形状；不同层级可变化但每种形状的含义在全图中一致。
6. 背景：纯白 #FFFFFF，不做渐变或透明。
7. 图例：若使用多种灰度区分系列/层级，必须添加图例说明。
```

### 3.6 dataviz skill 集成方案

如果 `dataviz` skill 可用：
- 触发点：阶段7 首张数据图表产出后，执行 `/dataviz` 进行颜色校验
- 输入：已产出的 PNG 文件路径 + `.mplstyle` 路径
- 输出：颜色合规报告（PASS/FAIL + 违规项列表）
- 不阻塞：校验结果记录到阶段7 质量门槛，不中断写作循环

如果 `dataviz` skill **不可用**，使用内置 `check_colors()` Python 函数作为等价替代。该函数：
- 读入 PNG，提取所有非白(#FFFFFF)像素
- 将像素聚类为 K=16 种代表性颜色
- 检查是否存在灰阶色板之外的颜色（红 #D62728 除外）
- 返回违规颜色列表

```python
# 内置颜色校验函数（放在 scripts/chart_checks.py）
import numpy as np
from PIL import Image
from collections import Counter

ALLOWED_COLORS = {
    '#000000', '#333333', '#555555', '#777777',
    '#999999', '#BBBBBB', '#DDDDDD', '#F2F2F2',
    '#FFFFFF', '#D62728',
}

def color_distance(c1, c2):
    """CIEDE2000 简化版——RGB 空间欧氏距离，阈值 30"""
    return np.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))

def check_colors(png_path: str) -> dict:
    """检查 PNG 文件是否仅使用许可色板。"""
    img = Image.open(png_path).convert('RGB')
    pixels = np.array(img).reshape(-1, 3)
    # 采样 1000 个像素进行颜色聚类
    sample = pixels[np.random.choice(len(pixels), min(1000, len(pixels)), replace=False)]
    violations = []
    for px in sample:
        r, g, b = int(px[0]), int(px[1]), int(px[2])
        if r == g == b == 255:  # 纯白豁免
            continue
        hex_color = f'#{r:02X}{g:02X}{b:02X}'
        ok = any(color_distance((r, g, b), _hex_to_rgb(c)) < 30 for c in ALLOWED_COLORS)
        if not ok:
            violations.append(hex_color)
    violation_pct = len(violations) / len(sample) * 100
    return {
        'passed': violation_pct < 2.0,  # <2% 违规容差
        'violation_pct': round(violation_pct, 1),
        'top_violations': [c for c, _ in Counter(violations).most_common(3)],
    }
```

---

## 4. 约束等级体系

| 标签 | 含义 | 违反后果 |
|------|------|---------|
| **MUST** | 强制要求，阻塞性 | 阶段质量门槛不通过，不得进入下一阶段 |
| **SHOULD** | 强烈建议，非阻塞 | 记录偏差到质量门槛备注，不阻止流程 |
| **MAY** | 可选增强 | 不检查，仅作为最佳实践参考 |

**MUST 级共有 13 项**：Q-01, Q-03, Q-04, Q-06, Q-07, Q-08, Q-09, Q-11, Q-13, Q-14, Q-15, Q-16, Q-19, Q-20, Q-21, Q-22

**SHOULD 级共有 5 项**：Q-05, Q-10, Q-12, Q-18, Q-23

---

## 5. 与 SKILL.md / V3.1 联动修订

| 修订目标 | 内容 | 位置 | 详见 |
|---------|------|------|------|
| SKILL.md §6 质量门槛 | 新增 3 项：配色一致性检查 + 颜色映射注册表 + PNG 分辨率 | 第 691 行（现有门槛表之后） | [skill-revision-proposal.md](skill-revision-proposal.md) |
| SKILL.md §7 质量门槛 | 新增 3 项：rcParams 加载确认 + 图表类型合规 + 色盲友好检查 | 第 831 行（现有门槛表之后） | [skill-revision-proposal.md](skill-revision-proposal.md) |
| SKILL.md §7.3 步骤 3 | 插入 `plt.style.use()` 语句 | 第 751 行 | [skill-revision-proposal.md](skill-revision-proposal.md) |
| SKILL.md §6.2 工具 A | 补充 drawio prompt 约束模板引用 | 第 584 行之后 | [skill-revision-proposal.md](skill-revision-proposal.md) |
| V3.1 §5.3 | 替换现有推荐表为完整决策表（§3.4） | 格式规范 §5.3 | 待用户审批后逐条修订 |
| V3.1 §十一 | 灰度色板精确值取代现有通用描述 | 格式规范 §十一 | 待用户审批后逐条修订 |

---

## 6. 已知限制

1. **drawio Mermaid 生成的图无法精确控制字号**：Mermaid 转 drawio 的字号由渲染引擎决定。Q-09 的约束通过 prompt 注入施加"最佳努力"影响，但最终需要人工抽查。若精度要求高，应采用 XML 方式生成
2. **fireworks-tech-graph 模板升级依赖外部项目**：Q-10（字号 ≥12px）需模板维护者配合修改，本方案的约束通过 JSON 传入的 `font_size` 字段作为带内信令
3. **颜色校验依赖像素采样**：`check_colors()` 是统计近似方法，可能在边缘情况（极小面积违规色）遗漏
4. **色觉障碍友好是渐进目标**：当前方案第一次迭代聚焦灰度+单强调色的基本保障，CUD 全量合规（如使用 Tol's bright palette 替换灰度单色）留待 v2
5. **matplotlib 中文字体依赖系统字体**：SimSun（宋体）在 Windows 上预装，macOS/Linux 需回退到 Noto Sans CJK 或文泉驿。`.mplstyle` 的 `font.sans-serif` 提供了 fallback 链

---

## 7. 与 md→docx 转换器的关系

图表质量约束方案与已有转换器的接口：

- **W-IMG-02（低分辨率警告）**：转换器已有 `<1102px → WARNING` 检查，与本方案的 Q-11 印刷可读性阈值一致——不需要重复实现
- **FigureIR 强制宽度 R13**：转换器将图强制嵌入 14cm 宽，若原始图的字体过小则会在印刷品中按比例缩放——这正是 Q-11 检查的动机。前后配合形成双重保障
- **`check_colors()` 函数**：作为转换器后续版本的静态检查项（类似已有的 `check_no_hardcode.py`），但不阻塞转换
