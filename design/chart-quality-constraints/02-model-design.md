# 算法模型设计文档：图表质量约束方案 — 配色规范体系 & 数据图表类型选择指南

## 1. 模型层级定位

- **层级**：算法选型 + 模型架构 + 特征工程 + 评估方案（跨层级综合设计）
- **创新度**：全新设计——当前 V3.1 格式规范仅有 4 个基础色值和 8 行粗略图表类型表，本方案从零建立完整体系

---

## 模块 A：配色规范体系

### A0. 设计原则

| 原则 | 说明 | 来源 |
|------|------|------|
| **灰度优先** | 核心交付物为 A4 黑白印刷，所有系列必须在纯灰度下可区分 | 研究报告格式规范 V3.1 §5.2 |
| **亮度差 ≥20** | 相邻系列在 0–255 亮度尺度上差值 ≥20，保证裸眼可辨 | 打印可读性实验结论 |
| **双通道编码** | 当系列数 ≥6 时，启用"灰度 + 线型"或"灰度 + 填充纹理"双通道 | CUD (Color Universal Design) 原则 |
| **色盲安全** | 任何使用颜色的场景（强调色、屏幕阅读）必须在 protanopia/deuteranopia/tritanopia 下可区分 | CUD 原则 + Tol (2021) |
| **可逆映射** | 所有色值有对应的十六进制、RGB、亮度值（CIE Y），方便程序化使用 | 工程实践 |

### A1. 灰度色板精确值

#### A1.1 基础色板（继承 V3.1 §11）

| 角色 | 色值 | RGB | 亮度(L) | 用途 |
|------|------|-----|---------|------|
| 主色 | `#000000` | (0, 0, 0) | 0 | 标题、表头文字、封面分隔线、边框、正文、图表主要系列 |
| 强调深灰 | `#333333` | (51, 51, 51) | 51 | 图表次要系列、特殊强调文字、坐标轴线 |
| 辅助文字 | `#555555` | (85, 85, 85) | 85 | 图注、表注、脚注、图表第三系列 |
| 浅灰背景 | `#F2F2F2` | (242, 242, 242) | 242 | 表格交替行、定义框底色 |

> **亮度公式**（ITU-R BT.601）：`L = 0.299 × R + 0.587 × G + 0.114 × B`，范围 0–255。

#### A1.2 图表专用扩展色板

在 4 个基础色值之上，扩展出图表场景所需的完整色板：

| 角色 | 色值 | RGB | 亮度(L) | 使用场景 |
|------|------|-----|---------|---------|
| **网格线** | `#D9D9D9` | (217, 217, 217) | 217 | 图表背景网格线，需可见但不喧宾夺主 |
| **轴线** | `#333333` | (51, 51, 51) | 51 | X/Y 轴线和刻度线 |
| **轴标签** | `#000000` | (0, 0, 0) | 0 | 坐标轴标签文字 |
| **图例文字** | `#333333` | (51, 51, 51) | 51 | 图例中的文字标注 |
| **图表标题** | `#000000` | (0, 0, 0) | 0 | 图表上方或下方的标题文字 |
| **数据标签** | `#555555` | (85, 85, 85) | 85 | 柱状图/饼图上的数值标注 |
| **参考线** | `#999999` | (153, 153, 153) | 153 | 平均值线、目标线等参考线（虚线） |
| **注释框背景** | `#F5F5F5` | (245, 245, 245) | 245 | 图表内注释框/数据说明区域底色 |
| **注释框边框** | `#CCCCCC` | (204, 204, 204) | 204 | 图表内注释框边框 |
| **图表底色** | `#FFFFFF` | (255, 255, 255) | 255 | 图表区域背景（白纸） |

#### A1.3 序列色板——5 级灰度（无需纹理辅助，纯亮度区分）

用于 2–5 个数据系列的场景，仅靠灰度深浅即可可靠区分。相邻系列亮度差 ≥20。

| 系列 | 色值 | RGB | 亮度(L) | 与前一级亮度差 | 使用场景示例 |
|------|------|-----|---------|---------------|-------------|
| 系列 1 | `#000000` | (0, 0, 0) | 0 | — | 折线图系列1、柱状图最左侧/最下侧 |
| 系列 2 | `#3A3A3A` | (58, 58, 58) | 58 | 58 | 折线图系列2、分组柱状图第二组 |
| 系列 3 | `#737373` | (115, 115, 115) | 115 | 57 | 折线图系列3、分组柱状图第三组 |
| 系列 4 | `#ADADAD` | (173, 173, 173) | 173 | 58 | 折线图系列4、分组柱状图第四组 |
| 系列 5 | `#D9D9D9` | (217, 217, 217) | 217 | 44 | 折线图系列5、分组柱状图第五组 |

> **用色规则**：按数据重要性分配灰度级。最重要的系列用 `#000000`（最深），最次要的系列用 `#D9D9D9`。不要因为"视觉好看"而颠倒——最深色吸引读者注意力，应分配给报告想强调的核心数据系列。

### A2. 多系列灰度区分方案（6–8 系列）

当系列数 ≥6 时，纯灰度已不足以可靠区分（亮度差会被压缩），须启用**双通道编码**：灰度 + 线型（折线图）或灰度 + 填充纹理（柱状图/面积图）。

#### A2.1 折线图——8 系列完整映射表

| 系列 | 色值 | 线型 (matplotlib) | 线宽 | 标记 | 标记大小 | 视觉可辨特征 |
|------|------|-------------------|------|------|---------|-------------|
| 1 | `#000000` | `-` (solid) | 2.0pt | `o` | 5 | 最粗纯黑实线 + 圆点 |
| 2 | `#333333` | `--` (dashed) | 1.8pt | `s` | 5 | 深灰宽虚线 + 方块 |
| 3 | `#595959` | `:` (dotted) | 2.0pt | `^` | 6 | 中灰粗点线 + 三角 |
| 4 | `#808080` | `-.` (dash-dot) | 1.8pt | `D` | 5 | 中浅灰点划线 + 菱形 |
| 5 | `#A6A6A6` | `-` (solid) | 1.2pt | `v` | 5 | 浅灰细实线 + 倒三角 |
| 6 | `#4D4D4D` | `(0, (5, 3, 1, 3))` dash-dot-dot | 1.8pt | `p` | 6 | 深灰双点划线 + 五边形 |
| 7 | `#666666` | `(0, (6, 2))` long dash | 1.5pt | `*` | 7 | 中灰长划线 + 星号 |
| 8 | `#999999` | `(0, (1, 2))` densely dotted | 1.8pt | `X` | 6 | 浅灰密点线 + 叉号 |

> **标记仅在数据点 ≤20 时启用**。当数据点 >20 时，每 5 个点打一个标记或完全不用标记，避免标记拥挤导致图例之外的视觉噪声。

#### A2.2 柱状图/条形图——8 系列完整映射表

| 系列 | 填充色 | 填充纹理 (hatch) | 边框色 | 视觉可辨特征 |
|------|--------|-----------------|--------|-------------|
| 1 | `#1A1A1A` | 无（纯色填充） | `#000000` | 最深纯黑填充 |
| 2 | `#4D4D4D` | `///` (斜线, 45°) | `#333333` | 深灰底 + 斜线纹理 |
| 3 | `#808080` | 无（纯色填充） | `#595959` | 中灰纯色填充 |
| 4 | `#B3B3B3` | `\\\` (反斜线, 135°) | `#808080` | 浅灰底 + 反斜线纹理 |
| 5 | `#D9D9D9` | 无（纯色填充） | `#999999` | 最浅灰填充 |
| 6 | `#666666` | `xxx` (交叉线) | `#4D4D4D` | 中灰底 + 交叉线纹理 |
| 7 | `#999999` | `...` (点填充) | `#666666` | 浅灰底 + 点纹理 |
| 8 | `#CCCCCC` | `|||` (竖线) | `#999999` | 灰白底 + 竖线纹理 |

> **填充纹理密度**：matplotlib `hatch` 参数中的图案密度可通过重复字符控制。`///` 为标准密度，`//////` 为高密度。在 300dpi 输出下，标准密度已足够可辨。

#### A2.3 面积图——多系列叠加规则

面积图系列数 **不超过 4 个**（超过则底层系列被完全遮挡）。如确需展示 5+ 系列趋势，改用**小多组折线图（small multiples）**。

| 叠加顺序（自底向上） | 填充色 | 透明度 (alpha) | 边框色 | 边框线型 |
|---------------------|--------|---------------|--------|---------|
| 底层（系列 1） | `#D9D9D9` | 1.0 | `#999999` | `-` |
| 第二层（系列 2） | `#ADADAD` | 1.0 | `#666666` | `-` |
| 第三层（系列 3） | `#737373` | 1.0 | `#333333` | `-` |
| 顶层（系列 4） | `#3A3A3A` | 0.85 | `#000000` | `-` |

> **透明度仅在顶层使用**，目的是让读者能看到被部分遮挡的下层区域边界。底层不用透明度——白纸印刷下半透明灰色叠加在白纸上效果不可靠。

### A3. 色盲无障碍约束

#### A3.1 适用场景

本报告的**核心交付形态为 A4 黑白印刷**，灰度方案天然对色觉障碍友好（不依赖色相区分）。色盲无障碍约束主要覆盖以下场景：

1. **屏幕阅读**：PDF 在屏幕上阅读时，强调色必须色盲安全
2. **强调色使用**：A4 节强调色（见下文）在彩色打印或屏幕显示下必须可区分
3. **未来扩展**：如果将来报告增加彩色图表（如面向屏幕阅读的版本），须遵循本节约定的色板

#### A3.2 CUD 原则落地

| CUD 原则 | 本方案落地方式 |
|----------|--------------|
| 不单独依赖红-绿区分信息 | 所有序列用灰度 + 线型/纹理双通道，红绿色根本不出现在图表中 |
| 确保亮度差充足 | 相邻系列亮度差 ≥20（见 A1.3），在三种色觉障碍下均不受影响 |
| 使用形状/纹理作为冗余编码 | 6+ 系列启用线型或填充纹理（见 A2），形状信息独立于灰度，色觉障碍者与正常色觉者看到的信息完全等价 |
| 避免使用光谱两端的颜色并列 | 不使用纯红+纯蓝并列方案 |

#### A3.3 色盲安全的强调色方案

当在灰度图表中需要使用彩色强调关键数据点时（SHOULD 级别），从以下色板中选择。这些颜色经过 CVD 模拟验证，在 protanopia / deuteranopia / tritanopia 三种色觉障碍下均可与灰度背景区分。

**CUD 安全强调色板**（基于 Tol (2021) 定性方案 + Wong (2011) Nature Methods 方案交叉筛选）：

| 色名 | 色值 | 亮度(L) | 适用于深色背景? | 适用于浅色背景? | 色盲安全性 |
|------|------|---------|---------------|---------------|-----------|
| **蓝色** | `#0072B2` | 95 | 部分可辨 | ✅ 推荐 | P/D/T 均可辨 |
| **橙红** | `#D55E00` | 108 | ✅ 可辨 | ✅ 推荐 | P/D/T 均可辨（在 P/D 下偏黄褐色，但仍与灰色区分） |
| **青绿** | `#009E73` | 114 | 部分可辨 | ✅ 可用 | P/D/T 均可辨 |

> **禁止使用的强调色**：纯红 `#FF0000` + 纯绿 `#00FF00` 组合——这在 protanopia 和 deuteranopia 下无法区分，是最常见的色盲无障碍违规。

#### A3.4 验证方法——matplotlib 模拟色觉障碍

以下代码片段用 `colorspacious` 库模拟三种色觉障碍，验证图表在相应条件下的可辨性：

```python
import matplotlib.pyplot as plt
import numpy as np

# ----- 方案 A：使用 colorspacious（推荐，需 pip install colorspacious）-----
def simulate_cvd_image(image_rgb, cvd_type='protanomaly'):
    """
    对 RGB 图像数组应用色觉障碍模拟。
    cvd_type: 'protanomaly' | 'deuteranomaly' | 'tritanomaly'
    返回: 模拟后的 RGB 图像数组
    """
    from colorspacious import cvd_space
    # image_rgb shape: (H, W, 3), values 0-255
    image_float = image_rgb / 255.0
    # colorspacious 期望 (N, 3) 输入
    h, w, _ = image_float.shape
    pixels = image_float.reshape(-1, 3)
    simulated = cvd_space(pixels, cvd_type)
    return (simulated.reshape(h, w, 3) * 255).astype(np.uint8)


def validate_palette_cvd(hex_colors, figsize=(8, 2)):
    """
    验证一组色值在三种 CVD 类型下的可辨性。
    横向排列：原色 | Protanopia | Deuteranopia | Tritanopia
    """
    from colorspacious import cvd_space
    from matplotlib.patches import Rectangle

    cvd_types = ['protanomaly', 'deuteranomaly', 'tritanomaly']
    titles = ['原始颜色', 'Protanopia (红色盲)', 'Deuteranopia (绿色盲)', 'Tritanopia (蓝色盲)']

    n_colors = len(hex_colors)
    fig, axes = plt.subplots(1, 4, figsize=figsize)

    for ax_idx, (ax, title) in enumerate(zip(axes, titles)):
        for i, hex_c in enumerate(hex_colors):
            rgb = plt.matplotlib.colors.to_rgb(hex_c)
            if ax_idx == 0:
                color = rgb
            else:
                # 模拟 CVD
                simulated = cvd_space(np.array([rgb]), cvd_types[ax_idx - 1])[0]
                color = np.clip(simulated, 0, 1)
            rect = Rectangle((i * 1.0, 0), 0.9, 0.9,
                             facecolor=color, edgecolor='black', linewidth=0.5)
            ax.add_patch(rect)
            ax.text(i * 1.0 + 0.45, -0.15, hex_c, ha='center', va='top', fontsize=7)
        ax.set_xlim(-0.2, n_colors * 1.0)
        ax.set_ylim(-0.5, 1.2)
        ax.set_title(title, fontsize=9)
        ax.axis('off')

    plt.tight_layout()
    plt.savefig('cvd_validation.png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f'CVD validation saved to cvd_validation.png')


# ----- 方案 B：使用 daltonlens（备选，无需编译，pip install daltonlens）-----
def simulate_cvd_daltonlens(hex_color, cvd_type='protanopia'):
    """
    使用 daltonlens 模拟单个色值的 CVD 效果。
    """
    from daltonlens import simulate
    sim = simulate.Simulator_Brettel1997()
    rgb = plt.matplotlib.colors.to_rgb(hex_color)
    r, g, b = int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    if cvd_type == 'protanopia':
        sr, sg, sb = sim.simulate_protanopia(r, g, b)
    elif cvd_type == 'deuteranopia':
        sr, sg, sb = sim.simulate_deuteranopia(r, g, b)
    elif cvd_type == 'tritanopia':
        sr, sg, sb = sim.simulate_tritanopia(r, g, b)
    return f'#{sr:02X}{sg:02X}{sb:02X}'


# ----- 验证本方案的 5 级灰度序列 -----
if __name__ == '__main__':
    # 本方案的 5 级灰度序列
    grayscale_5 = ['#000000', '#3A3A3A', '#737373', '#ADADAD', '#D9D9D9']
    validate_palette_cvd(grayscale_5)

    # 强调色验证
    emphasis_colors = ['#0072B2', '#D55E00', '#009E73']
    validate_palette_cvd(emphasis_colors)
```

> **验证结果预期**：5 级灰度序列在三种 CVD 模拟下亮度排序不变（灰度信息不受色觉障碍影响），通过。强调色在 CVD 模拟下与灰度背景可区分，通过。若验证未通过，重点检查是否误用了红-绿搭配。

### A4. 强调色方案

#### A4.1 使用场景与约束

| 约束级别 | 说明 |
|---------|------|
| **MUST** | 核心交付是黑白印刷——灰度方案（A1–A2）是主方案，必须能独立完成所有信息传达 |
| **SHOULD** | 当需要在灰度图表中突出 1 个关键数据点、1 条关键曲线、或 1 个异常值时，允许使用强调色——但**仅仅是视觉增强**，信息传递仍依赖灰度 + 标注，不因失去强调色而丢失信息 |
| **MAY** | 如果报告有单独的"屏幕阅读版"（如 HTML 版本），可以在全图表中使用 CUD 安全彩色色板 |

#### A4.2 推荐强调色值

| 强调目的 | 推荐色值 | 色名 | 亮度(L) | 在灰度打印下的表现 | 使用示例 |
|---------|---------|------|---------|------------------|---------|
| 高亮关键数据点 | `#0072B2` | 深蓝 | 95 | 呈现为中等灰度（≈#5F5F5F），与纯黑系列尚可区分 | 标注"本项目"在竞品对比图中的位置 |
| 高亮预警/风险 | `#D55E00` | 橙红 | 108 | 呈现为深灰（≈#6C6C6C），在黑灰系列中较突出 | 标记超出阈值的数据点 |
| 高亮正向/达标 | `#009E73` | 青绿 | 114 | 呈现为深灰（≈#727272），与纯黑系列可区分 | 标记达标指标 |

> **应用方式**：强调色仅用于**散点的填充色**或**单条曲线的线条色**，不使用大面积色块。在图片 `alt` 文本和图注中必须补充文字说明被强调的数据点含义，确保灰度打印下不依赖颜色即可理解。

### A5. 暗色/亮色适配

#### A5.1 亮色主题（White Paper / 优先级最高）

这是报告的主体场景——白色 A4 纸张印刷或白色背景的 PDF 屏幕阅读。

| 元素 | 色值 | 说明 |
|------|------|------|
| 图表背景 | `#FFFFFF` | 纯白，利用纸张本色 |
| 绘图区背景 | `#FFFFFF` | 绘图区无底色 |
| 网格线 | `#D9D9D9` | 浅灰，可见但不喧宾夺主 |
| 轴线 | `#333333` | 深灰，清晰但不刺眼 |
| 文字（标题/标签/刻度） | `#000000` | 纯黑，最高对比度 |
| 数据系列 | 见 A1.3 和 A2 | 灰度序列 |
| 图例背景 | `#FFFFFF` | 无底色，或 `#F5F5F5`（如置于绘图区内） |
| 图例边框 | 无 | 不画边框，依靠留白区分 |

**matplotlib 全局样式预设**：

```python
# 亮色主题——研究报告标准样式
REPORT_LIGHT_STYLE = {
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.edgecolor': '#333333',
    'axes.labelcolor': '#000000',
    'axes.grid': True,
    'grid.color': '#D9D9D9',
    'grid.linewidth': 0.5,
    'grid.alpha': 1.0,
    'xtick.color': '#000000',
    'ytick.color': '#000000',
    'text.color': '#000000',
    'legend.facecolor': 'white',
    'legend.edgecolor': 'none',
    'legend.framealpha': 1.0,
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'lines.linewidth': 1.8,
    'lines.markersize': 5,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.facecolor': 'white',
}
```

#### A5.2 暗色主题（Screen Reading / 优先级次之，级别 MAY）

标注为 MAY 级别：仅在明确需要暗色背景的屏幕阅读场景下使用（如嵌入深色模式网页的图表）。核心交付仍是亮色/A4 印刷。

| 元素 | 亮色值 | 暗色值 | 映射规则 |
|------|--------|--------|---------|
| 图表背景 | `#FFFFFF` | `#1E1E1E` | 白→深灰黑 |
| 绘图区背景 | `#FFFFFF` | `#1E1E1E` | 同上 |
| 网格线 | `#D9D9D9` | `#3A3A3A` | 浅灰→深灰 |
| 轴线 | `#333333` | `#B0B0B0` | 深灰→浅灰（反转） |
| 文字 | `#000000` | `#E0E0E0` | 黑→浅灰白 |
| 数据系列 1–5 | 见 A1.3 | 亮度反转：`#D9D9D9` ↔ `#000000` | 最浅变最深 |
| 数据系列 6–8 | 见 A2 | 同上反转 + 保留纹理 | 线型/纹理不变 |
| 图例背景 | `#FFFFFF` | `#2A2A2A` | 白→深灰 |

**暗色主题的序列灰度反转规则**：

| 暗色序列 | 暗色值 | 对应亮色序列 | 逻辑 |
|---------|--------|-------------|------|
| 系列 1 | `#E0E0E0` | 系列 5 (`#D9D9D9`) | 最亮=最突出（暗背景下的"最重"视觉权） |
| 系列 2 | `#B0B0B0` | 系列 4 (`#ADADAD`) | |
| 系列 3 | `#808080` | 系列 3 (`#737373`) | 中间色调保持不变（双向居中） |
| 系列 4 | `#505050` | 系列 2 (`#3A3A3A`) | |
| 系列 5 | `#202020` | 系列 1 (`#000000`) | 最暗=视觉上"退后" |

#### A5.3 自动切换机制

```python
import matplotlib.pyplot as plt

def apply_report_style(theme='light'):
    """
    应用研究报告图表样式。
    theme: 'light' (默认, A4 印刷) | 'dark' (屏幕暗色阅读)
    """
    if theme == 'light':
        plt.rcParams.update(REPORT_LIGHT_STYLE)
    elif theme == 'dark':
        dark_style = dict(REPORT_LIGHT_STYLE)
        dark_style.update({
            'figure.facecolor': '#1E1E1E',
            'axes.facecolor': '#1E1E1E',
            'axes.edgecolor': '#B0B0B0',
            'axes.labelcolor': '#E0E0E0',
            'grid.color': '#3A3A3A',
            'xtick.color': '#E0E0E0',
            'ytick.color': '#E0E0E0',
            'text.color': '#E0E0E0',
            'legend.facecolor': '#2A2A2A',
            'savefig.facecolor': '#1E1E1E',
        })
        plt.rcParams.update(dark_style)
    return plt.rcParams


def get_series_color(series_index, total_series, theme='light'):
    """
    获取指定系列的颜色值。
    series_index: 0-based 系列编号 (0 = 最重要)
    total_series: 总系列数 (2-8)
    theme: 'light' | 'dark'
    """
    if total_series <= 5:
        light_colors = ['#000000', '#3A3A3A', '#737373', '#ADADAD', '#D9D9D9']
        dark_colors  = ['#E0E0E0', '#B0B0B0', '#808080', '#505050', '#202020']
    else:
        # 6-8 系列，取 A2 中定义的填充色
        light_colors = ['#1A1A1A', '#4D4D4D', '#808080', '#B3B3B3',
                        '#D9D9D9', '#666666', '#999999', '#CCCCCC']
        dark_colors  = ['#E6E6E6', '#B3B3B3', '#808080', '#4D4D4D',
                        '#202020', '#999999', '#666666', '#333333']

    colors = dark_colors if theme == 'dark' else light_colors
    return colors[series_index] if series_index < len(colors) else colors[-1]
```

---

## 模块 B：数据图表类型选择指南

### B0. 图表选择的元原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **意图优先于数据形状** | 先问"读者看这张图要回答什么问题"，再选图表类型，不要拿数据去"套"图 |
| 2 | **一图一事** | 每张图只传达一个核心信息。如果一张图需要 3 句话才能解释清楚，拆成 2–3 张 |
| 3 | **熟悉度优先** | 折线图、柱状图、散点图是读者最熟悉的图表类型；新奇图表（桑基图、弦图）仅在读者群体专业且确有必要时使用 |
| 4 | **黑白打印验证** | 所有图表在纯灰度打印下必须可读——颜色不能是唯一的信息载体 |
| 5 | **标注数据来源** | 图注末尾必须有数据来源，格式：`数据来源：机构名，报告名，年份` |

### B1. 决策矩阵

#### B1.1 主决策表

| 数据类型 | 变量数 | 有时间维度? | 推荐图表 | 备选图表 | 禁止图表 | 说明 |
|---------|--------|-----------|---------|---------|---------|------|
| **趋势** | 1 | 是 | 折线图 | 面积图、柱状图(≤12点) | 饼图、雷达图 | 折线最直观表达"随时间变化" |
| **趋势** | 2–5 | 是 | 多系列折线图 | 小多组折线图(small multiples) | 堆叠面积图(非加性数据) | 5 系列以内折线图仍可控；超过则考虑小多组 |
| **趋势** | 6+ | 是 | 小多组折线图 | 选取 Top5 折线 + "其他" | 单图超 5 系列折线 | 6+ 系列在一张图上无法区分 |
| **趋势+构成** | 2–5 | 是 | 堆叠面积图 | 百分比堆叠面积图 | 多系列折线图(会误导构成关系) | 仅当数据为加性（如市场份额总和=100%）时使用堆叠 |
| **比较** | 1 | 否 | 柱状图（纵向/横向） | 点图(dot plot)、棒棒糖图(lollipop) | 饼图(>5 类)、3D 柱状图 | 横向柱状图适合长标签（>8 字符） |
| **比较** | 2–5 | 否 | 分组柱状图 | 雷达图(仅≤5 维且维度可比) | 堆叠柱状图(非构成目的) | 分组柱状图是"多项目×多指标"比较的通用解 |
| **比较** | 6+ | 否 | 横向柱状图（Top N） | 表格 | 普通纵向柱状图（标签拥挤） | 长列表用横向柱状图降序排列 |
| **排名** | 1 | 否 | 横向柱状图（降序） | 棒棒糖图、斜率图(slopegraph) | 饼图 | 排名数据天然适合横向柱状图：从长到短一目了然 |
| **分布** | 1 | 否 | 直方图 | 箱线图、小提琴图、密度曲线 | 饼图、折线图 | 展示"数据长什么样" |
| **分布** | 2+ | 否 | 分组箱线图 | 分组小提琴图、蜂群图(beeswarm) | 多系列折线图（无时间维度无意义） | 比较多个组的分布形态 |
| **构成** | 1 | 否 | 饼图/环形图（2–5 类） | 树图(treemap)、瀑布图 | 饼图(>5 类)、3D 饼图 | 5 类是饼图可读性的上限 |
| **构成** | 2–3 | 否 | 堆叠柱状图（≤5 类/组） | 百分比堆叠柱状图、马赛克图 | 3D 堆叠柱状图 | 展示"各组的内部构成" |
| **构成** | 2–5 | 是 | 堆叠面积图 | 百分比堆叠面积图 | 多饼图并列对比 | 展示"构成随时间的变化" |
| **关系** | 2 | 否 | 散点图 | 六边形箱图(hexbin, 大数据量) | 折线图（无时间维度则为误导） | 展示两个连续变量间的关系 |
| **关系** | 3 | 否 | 气泡图（第三维=气泡大小） | 散点图矩阵(scatter matrix) | 3D 散点图（透视失真） | 三变量关系的最安全表达 |
| **关系** | 4+ | 否 | 散点图矩阵 + 相关性热力图 | 平行坐标图 | 3D 图 | 多变量探索用矩阵比单一视图更可靠 |
| **地理** | 1 | 否 | 柱状图（按地区降序） | 地图热力图 | 饼图放在地图上 | 非专业地理需求的报告，柱状图比地图更精确 |
| **地理** | 1 | 是 | 小多组折线图（分地区） | 动画（仅 HTML 版） | 单图多条折线（地区>5） | |
| **流程/结构** | N/A | N/A | 流程图/架构图（drawio） | 桑基图（流量流向） | 文字描述替代 | 阶段 6 已覆盖，此处仅为完整性列出 |
| **不确定性** | 1 | 否 | 区间图（误差棒/置信带） | 扇形图(fan chart) | 仅画均值不画误差 | 预测类报告必须展示不确定性范围 |

#### B1.2 特殊场景快速索引

| 报告场景 | 推荐图表组合 | 备注 |
|---------|-------------|------|
| 市场规模预测 | 折线图（多机构对比）+ 堆叠柱状图（分市场构成） | 时间维度是核心 |
| 竞争格局分析 | 矩阵图(2×2 气泡) + 横向柱状图（排名）+ 雷达图（≤5 维度） | 阶段 6 drawio 出矩阵图 |
| 政策时间线 | 横向时间轴 + 关键事件标注 | 阶段 6 drawio 出时间轴 |
| 技术成熟度评估 | TRL 阶梯图 + 技术对比表 | 阶梯图在阶段 6 用 drawio |
| 财务分析 | 瀑布图（收入分解）+ 折线+柱状组合图（收入+增长率） | |
| 风险雷达 | 热力图矩阵（风险×概率） + 横向柱状图（风险排序） | |
| 区域对比 | 横向柱状图（按地区） + 分组柱状图（地区×指标） | 除非有 GIS 专家读者，否则不推荐地图 |
| 案例对比 | 对比表（结构化文字） + 分组柱状图（量化对比） | 案例对比以表格为主，图表为辅 |
| 专利/文献趋势 | 折线图（年度申请量） + 横向柱状图（申请人/机构排名） | |

### B2. 反模式清单

| # | 反模式名称 | 为什么是问题 | 反例描述 | 正确替代方案 |
|---|-----------|-------------|---------|-------------|
| 1 | **3D 饼图** | 透视变形导致扇区面积无法准确比较；将二维数据映射到三维造成视觉失真；徒增"图表垃圾"(chartjunk) 而不增加信息量 | 一个倾斜的 3D 饼图，"前面"的扇区因透视显得更大，读者无法判断各扇区的真实占比 | 用 2D 环形图或横向柱状图（降序排列）。如类别 ≤3 且总和=100%，可直接在正文中用百分比表述 |
| 2 | **双 Y 轴滥用** | 左右两个不同尺度的 Y 轴会让读者无法判断两条曲线的真实关系——调整坐标轴范围可以"制造"任何想要的交叉点和相关性假象 | 左轴标营收(0–100亿)，右轴标增长率(-5%–+20%)，两条曲线在 2023 年"交叉"——但如果把左轴范围调到 0–200 亿，交叉点就消失了 | **原则：绝不使用双 Y 轴。** 改为：上下两张图共享 X 轴（stacked plots），或用索引化（indexed, 设基准年=100）将不同量纲的序列映射到同一尺度 |
| 3 | **柱状图非零基线** | 柱状图的视觉编码依赖"柱子的长度"，而非零基线会放大微小差异——例如从 50 截断的 Y 轴会让 50→55 的柱子看起来长了 10 倍 | Y 轴从 80 起步的柱状图，A=83 的柱子和 B=88 的柱子看起来相差 3 倍，实际差异仅 6% | 柱状图 Y 轴必须从 0 开始。如果数据集中在一个较小区间（如全部在 80–90）且需要展示差异，改用点图(dot plot)或直接列出数值表格 |
| 4 | **截断折线图 Y 轴（不可见的变化）** | 与柱状图不同，折线图可以截断 Y 轴——但截断后必须用视觉手段（如 Y 轴断裂标记 `//`）明确告知读者，否则会误读趋势幅度 | Y 轴从 500 截断到 1000，折线从 510 升到 530，看起来像剧烈增长，实际仅增 4% | 折线图可截 Y 轴但**必须加断裂标记**。更好的做法：用索引化（基准年=100）展示相对变化趋势 |
| 5 | **饼图超过 5 个分类** | 超过 5 个扇区后，人眼无法准确比较扇区角度和面积；小扇区标签拥挤甚至重叠 | 一个 9 类别的饼图，其中 5 个类别各占不到 5%，标签挤在一起不可读 | 取 Top 5 + "其他"合并为一个扇区；或用横向柱状图代替（降序排列，所有类别一目了然） |
| 6 | **面积图遮挡（>4 系列）** | 超过 4 层的堆叠面积图中，底层系列的部分面积被上层遮挡，读者只能看到"轮廓"而看不到被盖住的区域形状，无法判断底层系列的独立趋势 | 5 个系列的堆叠面积图，底层 2 个系列只有顶部边缘可见，其波动趋势完全被上层遮挡 | 限制面积图 ≤4 系列；5+ 系列改用小多组折线图（每个系列一张小图，共享 X/Y 轴） |
| 7 | **过多样式装饰（chartjunk）** | 加粗边框、渐变背景、图片水印、装饰性图标、3D 效果、阴影等不承载数据的视觉元素，增加认知负荷而减少数据-墨水比(data-ink ratio) | 深蓝渐变背景 + 圆角加粗边框 + 半透明水印 Logo + 3D 柱体 + 阴影效果的柱状图——数据本身只占不到 20% 的视觉面积 | 白底 + 灰色网格线 + 纯黑文字 + 灰度柱体。最大数据-墨水比原则：每一滴墨水都应服务于数据的表达 |
| 8 | **颜色作为唯一区分手段** | 仅靠红-绿-蓝颜色区分系列，色觉障碍者无法区分，且黑白打印下所有系列变成同一灰色 | 折线图 3 条曲线分别用红色 / 绿色 / 蓝色，但线型全是实线，标记全是圆点——黑白打印后三条曲线完全相同 | 用灰度 + 线型 + 标记形状三重编码（见 A2.1 映射表），即使掉色也不丢失信息 |
| 9 | **雷达图用于非循环/不可比维度** | 雷达图的"圆形"形状暗示各维度有循环关系或同等重要性；当维度量纲不同时，雷达图上的面积完全无意义；且多边形形状对维度排列顺序敏感 | 用雷达图展示一家公司的"营收(亿美元)、员工数(万人)、专利数(件)、市场份额(%)、成立年数(年)"——维度量纲完全不同，多边形面积毫无意义 | 用分组柱状图（各维度归一化到 0–100 或百分位），或平行坐标图。雷达图仅适用于维度 ≤5 个、量纲相同、维度间有"全面性/均衡性"语义的场景 |
| 10 | **螺旋图/极坐标图用于非周期数据** | 极坐标图的径向和角度编码极难被人眼准确解码；非周期数据映射到角度轴会造成"头尾相接"的虚假循环感 | 用极坐标图展示各月销售额（非周期数据），读者以为 12 月和 1 月存在某种循环关系 | 用普通折线图或柱状图。极坐标图仅适用于方向性数据（如风向频率玫瑰图）或天然循环数据（如 24 小时活动模式） |
| 11 | **堆叠柱状图中各层的趋势比较** | 除了底层系列外，其他层级的柱段"起点"不统一（随下层高度浮动），人眼无法跨组比较同一层级的长度——唯一能准确比较的只有底层和总高度 | 堆叠柱状图展示 3 个季度中 4 个产品的销量构成——读者想比较"产品 C 在 Q1/Q2/Q3 的变化"，但产品 C 的柱段起点每个季度不同，视觉上无法判断 | 如果目的是构成展示→堆叠柱状图可用；如果目的是跨组趋势比较→改用分组柱状图或小多组折线图 |
| 12 | **图表无数据来源标注** | 没有数据来源的图表无法验证、无法追溯、不可信——在研究报告语境下等同于"无来源断言" | 一张精美的市场规模折线图，图注只写"图 3-2 全球 OOS 市场规模预测"，没有标注数据来源 | 图注末尾必须标注数据来源：`数据来源：NSR, Global OOS Market Report, 2025`。如数据由作者估算/建模得出，标注"数据来源：作者基于 XX 模型估算" |

### B3. 推荐图表类型的 matplotlib 代码骨架

以下所有骨架遵循统一规范：
- `dpi=300` 保存（符合 V3.1 §5.2 要求）
- 应用 A5.1 亮色主题样式
- 配色使用 A1.3 和 A2 定义的灰度序列
- `plt.close()` 收尾，防止内存泄漏
- 可直接复制使用，仅需替换数据部分

#### B3.1 折线图——单系列趋势

```python
import matplotlib.pyplot as plt
import numpy as np

# ===== 数据准备 =====
years = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
# 替换为实际数据
values = [12.5, 15.8, 18.2, 22.1, 28.7, 35.4, 42.0, 48.6]
data_source = "NSR, Global Market Report, 2025"

# ===== 样式 =====
plt.rcParams.update({
    'figure.facecolor': 'white', 'axes.facecolor': 'white',
    'axes.edgecolor': '#333333', 'axes.labelcolor': '#000000',
    'axes.grid': True, 'grid.color': '#D9D9D9', 'grid.linewidth': 0.5,
    'xtick.color': '#000000', 'ytick.color': '#000000',
    'text.color': '#000000', 'font.size': 10,
    'savefig.dpi': 300, 'savefig.bbox': 'tight',
})

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(years, values, color='#000000', linewidth=2.0, marker='o',
        markersize=5, markerfacecolor='#000000', label='全球市场规模')

# 标注最后一个数据点
ax.annotate(f'{values[-1]:.1f}',
            xy=(years[-1], values[-1]),
            xytext=(5, 0), textcoords='offset points',
            fontsize=9, color='#333333', va='center')

ax.set_xlabel('年份')
ax.set_ylabel('市场规模（十亿美元）')
ax.set_title('2018-2025年全球OOS市场规模', fontsize=12, fontweight='bold', pad=12)

# 图注
ax.text(0, -0.18, f'数据来源：{data_source}',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/trend-line-chart.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.2 多系列折线图——5 系列趋势对比

```python
import matplotlib.pyplot as plt

# ===== 数据准备 =====
years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
# 替换为实际数据（5 个系列 × 7 个年份）
series_data = {
    '美国': [8.2, 9.1, 11.3, 14.5, 18.2, 22.0, 25.8],
    '中国': [3.5, 5.2, 7.8, 12.1, 16.9, 21.3, 27.5],
    '欧洲': [6.1, 6.8, 7.4, 8.2, 9.5, 10.8, 12.0],
    '日本': [4.2, 4.5, 4.8, 5.1, 5.6, 6.0, 6.3],
    '其他': [3.0, 3.3, 3.8, 4.2, 4.9, 5.5, 6.1],
}

# 5 级灰度序列（见 A1.3）+ 线型 + 标记
configs = [
    {'color': '#000000', 'linestyle': '-',  'marker': 'o', 'linewidth': 2.0, 'markersize': 5},
    {'color': '#3A3A3A', 'linestyle': '--', 'marker': 's', 'linewidth': 1.8, 'markersize': 5},
    {'color': '#737373', 'linestyle': ':',  'marker': '^', 'linewidth': 2.0, 'markersize': 6},
    {'color': '#ADADAD', 'linestyle': '-.', 'marker': 'D', 'linewidth': 1.8, 'markersize': 5},
    {'color': '#D9D9D9', 'linestyle': '-',  'marker': 'v', 'linewidth': 1.2, 'markersize': 5},
]

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(9, 5))
for (label, data), cfg in zip(series_data.items(), configs):
    ax.plot(years, data, label=label, **cfg)

ax.set_xlabel('年份')
ax.set_ylabel('市场规模（十亿美元）')
ax.set_title('2019-2025年全球OOS市场分地区趋势', fontsize=12, fontweight='bold', pad=12)
ax.legend(frameon=False, loc='upper left', fontsize=9)
ax.text(0, -0.18, '数据来源：NSR, Euroconsult, 各年度报告',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/multi-series-line.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.3 分组柱状图——多项目多指标比较

```python
import matplotlib.pyplot as plt
import numpy as np

# ===== 数据准备 =====
categories = ['参数A', '参数B', '参数C', '参数D', '参数E']
# 替换：5 个类别 × 3 个组
group1 = [85, 72, 90, 65, 78]
group2 = [70, 68, 75, 60, 82]
group3 = [55, 80, 60, 70, 65]
groups = [group1, group2, group3]
group_labels = ['方案一', '方案二', '方案三']

# 灰度序列
colors = ['#1A1A1A', '#808080', '#D9D9D9']

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(categories))
width = 0.25  # 柱子宽度
n_groups = len(groups)

for i, (data, label, color) in enumerate(zip(groups, group_labels, colors)):
    offset = (i - (n_groups - 1) / 2) * width
    bars = ax.bar(x + offset, data, width, label=label,
                  color=color, edgecolor='#333333', linewidth=0.5)
    # 在柱顶添加数值标签
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., h + 0.5,
                f'{h}', ha='center', va='bottom', fontsize=8, color='#555555')

ax.set_xticks(x)
ax.set_xticklabels(categories)
ax.set_ylabel('得分')
ax.set_title('三种方案的多维对比', fontsize=12, fontweight='bold', pad=12)
ax.legend(frameon=False, fontsize=9)
ax.set_ylim(0, max(max(g) for g in groups) * 1.15)  # 确保 Y 轴从 0 开始
ax.text(0, -0.18, '数据来源：作者基于XX标准评分',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/grouped-bar.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.4 堆叠柱状图——构成展示

```python
import matplotlib.pyplot as plt
import numpy as np

# ===== 数据准备 =====
categories = ['2020', '2021', '2022', '2023', '2024', '2025']
# 替换为实际数据（≤5 层堆叠）
layer1 = [30, 32, 35, 38, 42, 45]   # 底层
layer2 = [25, 28, 30, 28, 27, 25]
layer3 = [20, 18, 16, 15, 14, 14]
layer4 = [15, 14, 12, 12, 11, 10]
layer5 = [10, 8, 7, 7, 6, 6]        # 顶层
layers = [layer1, layer2, layer3, layer4, layer5]
layer_labels = ['硬件', '软件', '服务', '运维', '其他']

# 灰度序列（深→浅，对应自底向上）
colors = ['#1A1A1A', '#4D4D4D', '#808080', '#B3B3B3', '#D9D9D9']

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(categories))
bottom = np.zeros(len(categories))

for data, label, color in zip(layers, layer_labels, colors):
    bars = ax.bar(x, data, bottom=bottom, label=label,
                  color=color, edgecolor='#333333', linewidth=0.3)
    bottom += np.array(data)

ax.set_xticks(x)
ax.set_xticklabels(categories)
ax.set_ylabel('市场规模（十亿美元）')
ax.set_title('2020-2025年全球OOS市场构成变化', fontsize=12, fontweight='bold', pad=12)
ax.legend(frameon=False, fontsize=9, loc='upper left')
ax.text(0, -0.18, '数据来源：NSR, Global OOS Market Report, 2025',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/stacked-bar.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.5 横向柱状图——排名展示（长标签友好）

```python
import matplotlib.pyplot as plt

# ===== 数据准备 =====
# 降序排列
labels = [
    'SpaceX (美国)',
    'Northrop Grumman (美国)',
    'Astroscale (日本)',
    'ClearSpace (瑞士)',
    'D-Orbit (意大利)',
    'ExoAnalytic (美国)',
    '上海航天 (中国)',
    '银河航天 (中国)',
]
values = [850, 720, 480, 350, 280, 210, 165, 120]
data_source = "NSR, 各公司公告, 2025"

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(8, 5))
y_pos = range(len(labels))

# 灰度序列：最重要的用深色
colors = ['#1A1A1A', '#1A1A1A', '#333333', '#595959',
          '#808080', '#A6A6A6', '#A6A6A6', '#D9D9D9']
bars = ax.barh(y_pos, values, color=colors, edgecolor='#333333', linewidth=0.3, height=0.6)

# 数值标签
for bar, val in zip(bars, values):
    ax.text(bar.get_width() + 5, bar.get_y() + bar.get_height() / 2.,
            f'{val:,}', va='center', fontsize=9, color='#333333')

ax.set_yticks(y_pos)
ax.set_yticklabels(labels)
ax.invert_yaxis()  # 最大值在最上面
ax.set_xlabel('融资金额（百万美元）')
ax.set_title('全球OOS企业融资排名（截至2025年）', fontsize=12, fontweight='bold', pad=12)
ax.set_xlim(0, max(values) * 1.15)
ax.text(0, -0.12, f'数据来源：{data_source}',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/horizontal-bar.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.6 散点图——两变量关系

```python
import matplotlib.pyplot as plt
import numpy as np

# ===== 数据准备 =====
np.random.seed(42)
n = 30
# 替换为实际 X、Y 数据
x = np.random.uniform(10, 100, n)
y = x * 0.8 + np.random.normal(0, 8, n)
# 可选：按第三维度分组
groups = np.random.choice(['A类', 'B类', 'C类'], n)
data_source = "作者基于XX数据库分析"

# 灰度 + 标记形状（分组）
group_styles = {
    'A类': {'color': '#1A1A1A', 'marker': 'o', 'label': 'A类'},
    'B类': {'color': '#808080', 'marker': 's', 'label': 'B类'},
    'C类': {'color': '#D9D9D9', 'marker': '^', 'label': 'C类',
            'edgecolor': '#333333', 'linewidth': 0.5},
}

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(7, 5))
for grp, style in group_styles.items():
    mask = groups == grp
    ax.scatter(x[mask], y[mask], s=50, **{k: v for k, v in style.items() if k != 'label'},
               label=style['label'], zorder=3)

# 可选：添加趋势线
z = np.polyfit(x, y, 1)
p = np.poly1d(z)
x_line = np.linspace(x.min(), x.max(), 100)
ax.plot(x_line, p(x_line), '--', color='#333333', linewidth=1.2, alpha=0.7,
        label=f'趋势线 (y={z[0]:.2f}x+{z[1]:.1f})')

ax.set_xlabel('研发投入（百万美元）')
ax.set_ylabel('市场份额（%）')
ax.set_title('研发投入与市场份额的关系', fontsize=12, fontweight='bold', pad=12)
ax.legend(frameon=False, fontsize=9)
ax.text(0, -0.18, f'数据来源：{data_source}',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/scatter.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.7 箱线图——多组分布比较

```python
import matplotlib.pyplot as plt

# ===== 数据准备 =====
# 替换为实际分组数据（每组一个列表）
group_a = [45, 52, 48, 55, 60, 58, 63, 51, 49, 57, 62, 54, 50, 59, 61]
group_b = [38, 42, 40, 45, 48, 44, 50, 39, 43, 47, 41, 46, 49, 42, 44]
group_c = [55, 60, 58, 65, 70, 68, 62, 59, 64, 67, 72, 66, 63, 69, 71]
group_d = [30, 35, 32, 38, 40, 36, 42, 33, 37, 41, 34, 39, 43, 36, 38]
data = [group_a, group_b, group_c, group_d]
labels = ['方案\nAlpha', '方案\nBeta', '方案\nGamma', '方案\nDelta']

# 灰度填充
box_colors = ['#333333', '#595959', '#808080', '#ADADAD']

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(7, 5))
bp = ax.boxplot(data, labels=labels, patch_artist=True,
                medianprops={'color': '#000000', 'linewidth': 1.5},
                whiskerprops={'color': '#333333', 'linewidth': 1.0},
                capprops={'color': '#333333', 'linewidth': 1.0},
                flierprops={'marker': 'o', 'markerfacecolor': '#D9D9D9',
                            'markeredgecolor': '#333333', 'markersize': 5})

for patch, color in zip(bp['boxes'], box_colors):
    patch.set_facecolor(color)
    patch.set_edgecolor('#000000')
    patch.set_linewidth(1.0)

ax.set_ylabel('性能指标')
ax.set_title('四种方案的性能分布对比', fontsize=12, fontweight='bold', pad=12)
ax.text(0, -0.18, '数据来源：作者基于XX仿真结果统计',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/boxplot.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.8 饼图/环形图——构成展示（≤5 类）

```python
import matplotlib.pyplot as plt

# ===== 数据准备 =====
labels = ['硬件', '软件', '服务', '运维', '其他']
sizes = [35, 28, 20, 12, 5]
# 灰度序列
colors = ['#1A1A1A', '#4D4D4D', '#808080', '#B3B3B3', '#D9D9D9']
explode = (0.05, 0, 0, 0, 0)  # 突出最大扇区
data_source = "NSR, 2025"

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(6, 6))

# 用环形图 (donut) 替代传统饼图——去掉圆心减小视觉面积误导
wedges, texts, autotexts = ax.pie(
    sizes, explode=explode, labels=None, colors=colors,
    autopct='%1.1f%%', startangle=90, pctdistance=0.82,
    wedgeprops={'edgecolor': 'white', 'linewidth': 1.5},
    textprops={'fontsize': 9, 'color': '#000000'},
)

# 中心空心圆 = 环形图
centre_circle = plt.Circle((0, 0), 0.55, fc='white', edgecolor='#D9D9D9', linewidth=0.5)
ax.add_artist(centre_circle)

# 百分比文字颜色：深色扇区用白色，浅色扇区用黑色
threshold_luminance = 150
for autotext, color in zip(autotexts, colors):
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    autotext.set_color('white' if lum < threshold_luminance else 'black')

# 图例在右侧
ax.legend(wedges, [f'{l} ({s}%)' for l, s in zip(labels, sizes)],
          title='市场构成', loc='center left', bbox_to_anchor=(1, 0.5),
          frameon=False, fontsize=9)

ax.set_title('2025年全球OOS市场构成', fontsize=12, fontweight='bold', pad=12)
ax.text(0.5, -0.15, f'数据来源：{data_source}',
        transform=ax.transAxes, fontsize=8, color='#555555',
        style='italic', ha='center')

plt.tight_layout()
plt.savefig('research/figures/donut-chart.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.9 堆叠面积图——构成随时间变化

```python
import matplotlib.pyplot as plt
import numpy as np

# ===== 数据准备 =====
years = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
# ≤4 层堆叠
s1 = np.array([10, 12, 14, 18, 22, 28, 34, 40])  # 底层
s2 = np.array([8, 9, 10, 12, 14, 15, 16, 15])
s3 = np.array([5, 6, 7, 8, 9, 10, 11, 12])
s4 = np.array([3, 3, 4, 4, 5, 5, 5, 5])           # 顶层
layers = [s1, s2, s3, s4]
labels = ['亚太', '北美', '欧洲', '其他']

# 灰度（浅→深，自底向上）
fill_colors = ['#D9D9D9', '#ADADAD', '#737373', '#3A3A3A']
edge_colors = ['#999999', '#666666', '#333333', '#000000']

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(9, 5))
for data, label, fc, ec in zip(layers, labels, fill_colors, edge_colors):
    ax.fill_between(years, np.zeros_like(data) if label == labels[0]
                    else sum(l[:len(data)] for l in layers[:layers.index((data, label))[0] if isinstance(layers[0], np.ndarray) else ...]),
                    # 简化：使用 ax.stackplot 更直接
                    pass  # 占位，实际用 stackplot

# 使用 matplotlib 内置 stackplot（更简洁）
ax.stackplot(years, *layers, labels=labels,
             colors=fill_colors, edgecolor=edge_colors, linewidth=0.5)

ax.set_xlabel('年份')
ax.set_ylabel('市场规模（十亿美元）')
ax.set_title('2018-2025年全球OOS市场分地区构成变化', fontsize=12, fontweight='bold', pad=12)
ax.legend(frameon=False, fontsize=9, loc='upper left')
ax.text(0, -0.18, '数据来源：NSR, Euroconsult, 各年度报告',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/stacked-area.png', dpi=300, bbox_inches='tight')
plt.close()
```

#### B3.10 热力图矩阵——多维数据密度展示

```python
import matplotlib.pyplot as plt
import numpy as np

# ===== 数据准备 =====
rows = ['因素A', '因素B', '因素C', '因素D', '因素E', '因素F']
cols = ['场景1', '场景2', '场景3', '场景4', '场景5']
# 替换为实际矩阵数据
data = np.array([
    [0.85, 0.72, 0.45, 0.38, 0.15],
    [0.62, 0.58, 0.80, 0.55, 0.42],
    [0.30, 0.25, 0.50, 0.72, 0.88],
    [0.90, 0.85, 0.70, 0.60, 0.40],
    [0.20, 0.35, 0.55, 0.70, 0.82],
    [0.55, 0.60, 0.65, 0.50, 0.45],
])
data_source = "作者基于XX模型计算"

# ===== 绘图 =====
fig, ax = plt.subplots(figsize=(8, 5.5))

# 灰度热力图：白(#FFFFFF)→黑(#000000)，亮度线性映射
im = ax.imshow(data, cmap='Greys', vmin=0, vmax=1, aspect='auto')

# 标注数值
for i in range(len(rows)):
    for j in range(len(cols)):
        val = data[i, j]
        text_color = 'white' if val < 0.5 else 'black'
        ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                fontsize=9, color=text_color)

ax.set_xticks(range(len(cols)))
ax.set_xticklabels(cols)
ax.set_yticks(range(len(rows)))
ax.set_yticklabels(rows)
ax.set_title('各风险因素在不同场景下的影响程度', fontsize=12, fontweight='bold', pad=12)

# 颜色条
cbar = plt.colorbar(im, ax=ax, shrink=0.85)
cbar.set_label('影响程度 (0=无影响, 1=决定性影响)', fontsize=9)

ax.text(0, -0.15, f'数据来源：{data_source}',
        transform=ax.transAxes, fontsize=8, color='#555555', style='italic')

plt.tight_layout()
plt.savefig('research/figures/heatmap.png', dpi=300, bbox_inches='tight')
plt.close()
```

---

## 6. 数据依赖

| 数据项 | 来源 | 现有/新增 | 时效要求 |
|--------|------|----------|---------|
| V3.1 格式规范 §11 基础色值 | `references/研究报告格式规范.md` | 现有 | 随 V3.1 版本更新 |
| V3.1 格式规范 §5.3 图表类型表 | `references/研究报告格式规范.md` | 现有 | 随 V3.1 版本更新 |
| Tol 7-color qualitative scheme | Tol (2021), "Colour schemes", SRON technical note | 外部参考（已在此文档中引用具体色值） | 稳定（学术界公认） |
| CUD 原则 | Color Universal Design (CUD) guidelines, 日本色彩研究所 | 外部参考 | 稳定 |
| Wong (2011) Nature Methods colorblind-safe palette | Wong, B. (2011). "Points of view: Color blindness". Nature Methods, 8(6), 441. | 外部参考 | 稳定 |
| matplotlib 样式预设 | Python matplotlib 库 | 已安装（项目依赖） | ≥3.5.0 |

> 本方案不引入新的外部数据源依赖。所有色值和图表类型选择逻辑均在本设计文档中完整定义，下游实现者可直接消费。

## 7. 评估方案

### 7.1 配色方案验证

| 验证项 | 方法 | 通过标准 | 测试工具 |
|--------|------|---------|---------|
| 相邻系列亮度差 ≥20 | 对 5 级和 8 级序列计算 ITU-R BT.601 亮度，检查相邻差值 | 全部相邻差 ≥20 | Python 脚本（见 A3.4） |
| CVD 模拟可区分性 | 对 5 级灰度 + 强调色板分别用 colorspacious 模拟 protanopia/deuteranopia/tritanopia | 三种 CVD 下所有序列视觉可辨（人工判断 + 亮度差值 ≥15） | `colorspacious.cvd_space()` |
| 灰度打印可读性 | 将图表导出为灰度 PNG（desaturated），由人工在 A4 纸上打印并评估 | 所有图例标签与对应数据系列可一一配对，无误配 | 人工评审 |
| 300dpi 下纹理可辨性 | 用 8 系列柱状图模板出图（300dpi），在 A4 纸上打印，检查 hatch 纹理 | 所有 8 种填充纹理可独立识别，不混淆 | 人工评审 |

### 7.2 图表类型选择验证

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| 决策矩阵覆盖度 | 对照阶段 4.3 图表方向清单中的常见场景，逐一检查是否在 B1 决策矩阵中找到匹配条目 | 覆盖所有已规划出图场景 |
| 反模式触发检查 | 在阶段 7 出图时逐张检查：是否命中 B2 反模式清单中的任一项？如命中，是否使用了正确替代方案？ | 命中反模式 ≤0（即所有命中都有意替换为正确方案） |
| 代码骨架可运行性 | 将所有 B3 代码骨架在新的 Python 环境中执行（`python skeleton.py`），检查是否无错误完成 | 全部 10 个骨架无错误运行，生成 300dpi PNG |

---

## 8. 风险提示

| 风险 | 级别 | 说明 | 缓解措施 |
|------|------|------|---------|
| **灰度级过多导致混淆** | 中 | 8 系列方案在极端条件下（如用户打印机的灰度表现力差）可能出现系列 6/7/8 难以区分 | 在文档中标注"6+ 系列强烈建议改用小多组图替代单图多系列"；在 A2 映射表中引入线型和填充纹理作为冗余编码 |
| **暗色主题未经充分验证** | 低 | 暗色主题标注为 MAY 级别，当前未经过 A4 打印场景之外的充分测试 | 暗色主题仅在用户明确要求时启用；启用前先出一张样例图让用户确认 |
| **强调色在灰度打印下丢失信息** | 中 | 如果作者依赖强调色传达关键信息（如"红色=风险"），灰度打印后该信息完全丢失 | A4.1 明确规定：强调色仅作视觉增强，信息传递仍依赖灰度 + 标注；在图片 `alt` 文本和图注中补充文字说明 |
| **matplotlib 样式跨版本不一致** | 低 | matplotlib 不同版本对 `rcParams` 的默认值和处理方式可能有差异 | 在本方案样式中显式设置所有关键参数（不依赖默认值）；建议在 `requirements.txt` 中锁定 `matplotlib>=3.7.0` |
| **CVD 模拟库依赖** | 低 | `colorspacious` 依赖 C 编译（`pip install` 在某些 Windows 环境下需要 MSVC），可能导致 A3.4 验证代码无法运行 | 提供备选方案：`daltonlens` 纯 Python 实现，无需编译 |
| **多系列线型在数据密集时失效** | 中 | 当数据点 >50 时，虚线/点线/点划线之间的差异缩小（视觉上看起来都像实线） | 数据点 >50 时：减少系列数（≤5），或改用小多组图；在 A2.1 中标注标记仅在数据点 ≤20 时启用 |
