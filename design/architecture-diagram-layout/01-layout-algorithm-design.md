# D5-01：布局算法与几何判据设计

> **状态：设计稿，待用户审核，尚未执行**
> 来源：设计层 model-designer + 编排器裁决
> 依据：`07-measured-evidence.md` 全部实测数据

---

## 1. 技术选型裁决

### 1.1 结论

**采用参数化公式布局（纯标准库），不引入自动布局引擎。**

### 1.2 核心论点：架构图布局是语义驱动的，不是拓扑驱动的

自动布局引擎（力导向、dagre、ELK）的输入是**拓扑**（谁连谁），输出是"边交叉少、分布均匀"的坐标。但架构图的布局承载的是**人为设计意图**：

- 8-1 的十四层，"物理层在最下、治理层在最上"是语义，不是拓扑能发现的；
- 3-1 的金字塔，"逐层收窄"表达认知升维，力导向会把它摊成一团；
- 11-1 的象限，节点位置**编码了二维评分**，任何自动布局都会摧毁其含义。

**边界（诚实标注）**：该论点对"层次/流程/矩阵"类架构图成立；对**纯拓扑图**（如无明确层次的网络连接图）不成立，自动布局反而更优。D5 的五种模式覆盖前者，后者归入 `layout_mode: manual` 逃生舱。

### 1.3 反面论证

| 候选 | 为什么不用 |
|------|-----------|
| **力导向 / spring_layout** | 输出无量纲坐标、无节点尺寸概念、不做碰撞避免；且对层次语义图产出语义错误结果（14 层会被摊平） |
| **graphviz dot** | 需 graphviz **二进制**，本机未装且要求用户安装会击穿 `PORTABILITY.md` 的"纯 Python 确定性工具"承诺 |
| **networkx** | 虽已安装（3.6.1），但同力导向问题：无尺寸、无碰撞、无量纲。用于矩形节点需补缩放+去重叠后处理，等于自己再写一遍布局 |
| **ELK / dagre** | JS/Java 生态，无可靠 Python binding（`elkpy` **经证伪不存在**） |
| **rectangle packing** | 目标是"塞得紧"，与架构图"表达层次"的目标正交；且 `rectpack` 未安装 |
| **shapely** | 仅用于几何运算，实测 O(N²) 已 5.9ms，引入属过度工程 |
| **draw.io CLI `--layout elkLayered`** | **官方最优路径**，但需 drawio ≥30.2.5，本机未装 → 列为"若环境具备则优先"的**可选增强**，不作唯一路径 |

**严禁写入方案的库**（经调研证伪不存在）：`pycola`、`pyvpsc`、`adaptagrams`、`pyavoid`、`elkpy`、`pydrawio`。

### 1.4 最关键的裁决：公式写进 prompt 还是写进脚本？

**裁决：写进脚本。Agent 不得输出任何坐标。**

把公式写进 Agent prompt 让 LLM 照着算 —— **不能解决问题**。物证是 3-1 的 `x="None"`：Python 的 `None` 被 `str()` 写进 XML，说明当时**已经有代码/模型在算坐标**，且算出 None 时无人校验。LLM 算术不可靠是已证实的根因，给不可靠的算子配更严的检查器，只会得到不收敛的重试循环。

**外部佐证**：draw.io 官方设计立场 + GenAI-DrawIO-Creator 论文实证均支持"LLM 只出拓扑、坐标交给引擎"。
**量化红线**：**节点数 > 20 时，LLM 手算坐标视为禁止项。**

---

## 2. 五种布局模式

### 2.0 全局参数

```python
GRID        = 10     # 网格量化单位
MARGIN      = 40     # 画布四边留白
FONT_TITLE  = 18     # 节点标题（引用 chart-quality-constraints，不重定义）
FONT_BODY   = 16     # 节点正文
FONT_EDGE   = 14     # 边标签
MIN_NODE_W  = 180    # 节点最小宽（实测依据：现有图 200~560）
MIN_NODE_H  = 60     # 节点最小高

def snap(v, g=GRID):
    """坐标量化 —— 使网格对齐率恒为 100%，无需事后修补。"""
    return int(round(v / float(g)) * g)
```

**画布反推（所有模式共用，溢出的根本解）**：

```python
content_w = max(n.x + n.w for n in nodes)
content_h = max(n.y + n.h for n in nodes)
pageWidth  = snap(content_w + MARGIN)
pageHeight = snap(content_h + MARGIN)
```

> 此式使**溢出在生成阶段结构性不可能发生**。这是对 `chart-quality-constraints/03-interface-design.md:473` 固定 `pageWidth="960"` 的取代（见 D5-R8）——固定画布正是溢出的制度性根源。

### 2.1 模式 A：垂直堆叠（层次架构图）

**适用**：8-1 SCOS 十四层、3-1 金字塔。**节点上限**：单列 12，超出自动转双列。

```python
def layout_stack(nodes, w=560, h=80, gap=20, cols=1):
    per = ceil(len(nodes) / cols)
    for i, n in enumerate(nodes):
        c, r = i // per, i % per
        n.w, n.h = w, h
        n.x = snap(MARGIN + c * (w + 120))
        n.y = snap(MARGIN + r * (h + gap))
```

**变体 A'（金字塔，逐层收窄 + 水平居中）**：

```python
def layout_pyramid(nodes, base_w=1100, dec=80, h=110, gap=25):
    pw = snap(base_w + 2 * MARGIN)
    for i, n in enumerate(nodes):
        n.w, n.h = snap(base_w - dec * i), h
        n.x = snap((pw - n.w) / 2.0)          # 居中
        n.y = snap(MARGIN + i * (h + gap))
```

**无重叠保证**：`y` 单调递增且步长 `h+gap > h` → 结构性无重叠。

### 2.2 模式 B：水平流程链

**适用**：2-1 演化、4-2 推理流程。**节点上限**：单行 6，超出蛇形折行。

```python
def layout_flow(nodes, w=200, h=90, gap=60, max_w=1400):
    rows, cur, x = [], [], MARGIN
    for n in nodes:
        if x + w > max_w - MARGIN and cur:
            rows.append(cur); cur = []; x = MARGIN
        cur.append((n, x)); x += w + gap
    if cur: rows.append(cur)
    for r, row in enumerate(rows):
        for n, x in row:
            n.w, n.h = w, h
            n.x, n.y = snap(x), snap(MARGIN + r * (h + 80))
```

### 2.3 模式 C：中心-外围星型

**适用**：3-2 七维、4-1 六维、7-2 拓扑。**辐条上限 12**（超出视觉拥挤，见 L-1）。

```python
def layout_star(spokes, cw=300, ch=160, sw=200, sh=90, pad=60):
    R  = int(max(cw, sw) * 1.5 + pad + max(sh, ch))     # 半径含避碰余量
    cx = cy = snap(MARGIN + R + sw / 2.0 + cw / 2.0)
    center.x, center.y = snap(cx - cw/2.0), snap(cy - ch/2.0)
    for i, n in enumerate(spokes):
        th = 2 * pi * i / len(spokes) - pi / 2          # 从正上方起，顺时针均布
        n.w, n.h = sw, sh
        n.x = snap(cx + R * cos(th) - sw / 2.0)
        n.y = snap(cy + R * sin(th) - sh / 2.0)
```

**避碰依据**：相邻辐条圆心距 `2R·sin(π/N)`，N=12 时 ≈ 0.518R。取 `R ≥ 1.5·max(cw,sw)+pad` 保证该距离 > 节点宽。实测 N=6/7/8/12 均 0 重叠。

### 2.4 模式 D：行列网格

**适用**：10-1 路线图（18×6=108 顶点，全库最大）、5-1、6-1、7-1。**上限 150 单元**。

```python
def layout_grid(rows, cols, cw=180, ch=50, gx=25, gy=10):
    for r in range(rows):
        for c in range(cols):
            n = cell[r][c]
            n.w, n.h = cw, ch
            n.x = snap(MARGIN + c * (cw + gx))
            n.y = snap(MARGIN + r * (ch + gy))
```

**无重叠保证**：行列步长恒大于单元尺寸 → 结构性无重叠。实测 108 顶点 0 重叠。

### 2.5 模式 E：象限矩阵

**适用**：11-1 竞争格局。**散点上限 20**。

```python
def layout_quadrant(points, half_w=620, half_h=380, dot=150, dh=70):
    pw, ph = snap(2*half_w + 2*MARGIN), snap(2*half_h + 2*MARGIN)
    cx, cy = pw / 2.0, ph / 2.0
    # 四块背景板 —— 必须显式标记 is_background=True 供校验器豁免
    for (sx, sy) in [(-1,-1), (1,-1), (-1,1), (1,1)]:
        bg = Node(is_background=True, w=snap(half_w), h=snap(half_h), ...)
    # 散点：语义坐标 (nx, ny) ∈ [-1,1] 映射为像素 + 向下推挤避碰
    for p in points:
        x = snap(cx + p.nx * (half_w - dot) - dot/2.0)
        y = snap(cy + p.ny * (half_h - dh)  - dh/2.0)
        for _ in range(60):                       # 终止条件：最多 60 次
            if not collides(x, y, placed): break
            y = snap(y + dh + 10)                 # 单调下推，必然终止
        p.x, p.y = x, y
```

> **注意**：散点的 `(nx, ny)` 是**语义评分**，避碰只允许沿 y 轴微调，不得改变象限归属。

### 2.6 覆盖不了的形态（诚实标注）

五种模式**无法覆盖**：
- **混合拓扑**（如 4-2 的"主链 + 3 分支下挂 + 汇合"）；
- 无明确层次的**纯网络图**；
- 需要**手工微调**的示意图。

**处置**：`layout_mode: manual` 逃生舱 —— 允许 Agent 提供坐标，但该图**强制走 strict 校验、重试预算 = 0**，且在报告中登记（避免逃生舱变成默认路径）。

---

## 3. 几何质量判据

### 3.1 判据总表

| # | 判据 | 严重度 | 阈值 | 依据 |
|---|------|--------|------|------|
| G1 | **几何完整性**（`x/y/w/h` 非数值/缺失/`"None"`） | **error（最高优先级）** | 零容忍 | 实测：3-1 唯一真损坏，直接产出 325px 废品 |
| G2 | **节点硬重叠**（ink-box 相交） | **error** | 零容忍 | Sprawlter (TVCG 2020) 反对"轻微可容忍" |
| G3 | **内容溢出**（跨度/page） | **分级** | 见 §3.4 | 实测导出按内容裁剪 |
| G4 | **网格对齐率** | **warning** | ≥90% | 见 §3.5 的诚实评估 |
| G5 | **宽高比** | **warning** | 0.4 ≤ AR ≤ 4.5 | 实测 page AR 1.20~3.02，内容 AR 1.16~4.21 |
| G6 | **画布内嵌题注** | **error** | 零容忍 | 实测 3 处存在，2 处为溢出源 |
| G7 | **伪图残留**（Mermaid 关键字） | **error** | 零容忍 | 回归防护（实测已清零） |
| **G10a** | **拓扑结构自洽**（边集与 `layout_mode` 是否自洽，**零阈值**） | **error** | 见 §3.7 | **C-1 新增**；15 张实跑 0 假阳 0 假阴，**B1 生效** |
| **G10b** | **模式声明一致性**（stack/pyramid 的 rank 跨层校验） | **error** | 见 §3.7 | 需 IR 声明，**B4 后生效**（rank 全库 0 命中） |
| **G11** | **图例位置**（图例须在所有内容边界之外） | **error** | 见 §3.8 | **竞品对标新增** |
| G8 | 字号下限 | — | **引用** chart-quality-constraints | 不重定义 |
| G9 | PNG 宽度/DPI | — | **引用** figure_gate | 不重造 |

### 3.2 G1 几何完整性（为何优先级最高）

```python
BAD_LITERALS = {"None", "nan", "NaN", "null", "NULL", "undefined", ""}

def check_geometry_integrity(cell):
    g = cell.find("mxGeometry")
    if g is None: return "缺 mxGeometry"
    for k in ("x", "y", "width", "height"):
        v = g.get(k)
        if v is None or v.strip() in BAD_LITERALS: return f"{k}={v!r} 非法"
        try: float(v)
        except ValueError: return f"{k}={v!r} 非数值"
```

**为何比重叠更重要**：重叠只是"不好看"，几何损坏是**直接产出废品**。且它是唯一能**逃过所有现有检查**的缺陷（`ET.parse()` 完全通过）。

**配套计数口径**：必须同时输出 `vertex_total`（口径A，实测 376）与 `vertex_geometry_valid`（口径C，实测 370），**差值即告警信号**（3-1 差值 = 6）。

### 3.3 G2 重叠 —— 三态判定（C-3 修订）

**禁止用 IoU**（分母须为 `min(areaA, areaB)` 而非并集，IoU 属概念误用）。

> **本节已按对抗性审查 C-3 全面修订。** 初版的"AABB 不相交即 PASS、ink-box 相交即 FAIL"二态判定被证实存在**真实假阴性**，见 §3.3.3 双向标定。

#### 3.3.0 三态判定（取代初版二态）

| 条件 | 判定 | 语义 |
|------|------|------|
| AABB **不**相交 | **PASS** | 必要条件不成立，确定无重叠 |
| AABB 相交 **且** ink-box(膨胀后) 相交且 `min(ox,oy) ≥ 3px` | **FAIL** | 充分条件成立，确认有害 |
| AABB 相交 **但** ink-box 不相交，或相交厚度 < 3px | **WARNING** | **灰区 —— 不静默放行** |

**关键改动**：AABB 相交是**必要条件**，ink-box 相交是**确认有害的充分条件**；二者之间的区带判 **warning 而非 PASS**。理由：ink-box 是启发式估算，让它单独承担"判无罪"的责任会使零容忍判据静默失效。

#### 3.3.1 ink-box 计算（含安全膨胀）

**审查指出的方向问题已澄清并修正**：`min(cell.w, raw)` 这个钳制本身是**正确的**（墨迹不可能超出盒子），真正的缺陷是 **`raw` 本身被低估时，`min()` 会把低估值原样保留** → 墨迹框偏小 → 漏报。正确处置是**先给 raw 乘安全膨胀系数，再钳制**。

```python
import re, html, unicodedata

INK_INFLATE       = 1.15   # 安全膨胀系数（宁可误报不可漏报）
MIN_INK_THICKNESS = 3      # px；相交厚度门槛

def strip_html(s):
    """C-3 修订：<br>/<div>/<p> 必须转为换行符，不可直接剥除。"""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(div|p|li)\s*>", "\n", s, flags=re.I)   # 块级闭合 → 换行
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)

def char_w(ch, fs):
    """按 Unicode 码位分段。审查指出标准库 east_asian_width 正好可用。"""
    if ch == "\n": return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):  return fs * 1.00     # CJK 全角/宽
    if eaw == "A":         return fs * 0.85     # 歧义宽度（希腊/西里尔）取偏大
    return fs * 0.55                            # 窄字符

def ink_box(cell):
    text = strip_html(cell.value or "").strip()
    if not text:
        return aabb(cell)                       # 无文本装饰形状 → 回退 AABB
    fs    = parse_font_size(cell.style)
    raw_w = max_line_width(text, fs) * INK_INFLATE
    lines = estimate_lines(text, cell.w, fs)
    raw_h = lines * fs * 1.4 * INK_INFLATE
    ink_w = min(cell.w, raw_w)                  # 钳制（正确），但 raw 已膨胀
    ink_h = min(cell.h, raw_h)
    return centered_box(cell, ink_w, ink_h, parse_align(cell.style))
```

**`<br>` 处置的误差不对称性（实测依据）**：

| value | 旧（剥除） | 宽度 | 新（转换行） | 宽度 |
|-------|-----------|-----:|-------------|-----:|
| `<b>A</b><br>B` | `AB` | 17.6 | `A\nB` | 8.8 |
| `<div>行1</div><div>行2</div>` | `行1行2` | 49.6 | `行1\n行2` | 24.8 |

旧写法把多行拼成一行 → 宽度**高估**（偏保守），但 `estimate_lines()` 算成 1 行 → **高度被低估** → **纵向漏报**。两个方向误差不对称，故必须转换换行符。

#### 3.3.2 必须显式排除的 cell 类型（H-4 防御性修订）

```python
def participates_in_overlap(cell):
    if cell.get("vertex") != "1":              return False
    if "edgeLabel" in (cell.style or ""):      return False   # 边标签
    if cell.geometry.get("relative") == "1":   return False   # 相对定位子元素
    if cell.parent_is_edge:                    return False   # 挂在边上的 cell
    return True
```

**实测说明**：当前 15 张图中 `relative="1"` 与 `edgeLabel` 均为 **0 命中**，故 H-4 描述的误报机制在**当前样本**上不存在。但边标签是 draw.io 极常见形态，**未来数据上是真实风险** → 判据仍须显式排除，属防御性正确。**同时这也证明双口径差值（376−370=6）在当前样本上确实只由几何非法造成，无系统性误报。**

#### 3.3.3 双向标定（C-3 要求，结果暴露真实缺陷）

对 11-1 的 7 个重叠对做**双向**验证 —— 不仅验"无害项归零"，更要验"有害项不被误归零"：

| A | B | 人工标注 | AABB (ox,oy) | ink×1.0 | ink×1.15 | **三态判定** |
|---|---|---------|--------------|---------|----------|-----------|
| `ql1` | `ql2` | 无害 | (144, 26) | (0,0) | (0,0) | **WARNING**（AABB 相交，灰区） |
| `ql3` | `ql4` | 无害 | (144, 26) | (0,0) | (0,0) | **WARNING**（同上） |
| `yAxis` | `ql3` | 无害 | (5, 26) | (0,0) | (0,0) | **WARNING**（同上） |
| `leg1` | `leg2` | 无害 | (130, 3) | (49.6, **2.4**) | (57.0, **3.0**) | **FAIL**（厚度恰达 3px 门槛，见下） |
| `ql3` | `p10` | **有害** | (117, 17) | (67.5, 13.4) | (80.1, 16.8) | **FAIL** ✅ 正确 |
| `ql4` | `p12` | **有害** | (117, 26) | **(0,0)** ❌ 漏报 | (5.5, 26.0) | **FAIL** ✅ 膨胀后捕获 |
| `p1` | `p3` | **有害** | (33, 45) | **(0,0)** ❌ 漏报 | (8.5, 31.5) | **FAIL** ✅ 膨胀后捕获 |

> **D5-07 订正**：上表此前用 "✅" 标注 `(0,0)` 单元格，暗示"ink 不相交 = PASS = 正确结果"，**与 §3.3.0 三态定义直接矛盾**（三态下 AABB 相交而 ink 不相交应判 **WARNING**，不是 PASS）。现已改为显式给出三态判定列。**全文对同一情形只有一种判定：AABB 相交是必要条件，ink 不相交只降级为 WARNING，绝不判 PASS。**

**结论：初版 ink-box（无膨胀）在 3 个有害对中漏报 2 个 —— 假阴性率 67%。** 审查员的 C-3 指控**成立**。

- 加 `INK_INFLATE=1.15` 后，两个漏报对全部重新捕获；三个无害对的 ink 仍为 (0,0)，但因 AABB 相交而**归入 WARNING（不是 PASS）**。
- `leg1↔leg2` 在膨胀后厚度恰为 3.0px，**达到** `MIN_INK_THICKNESS` 门槛 → 判 **FAIL**。这是一处**已知的假阳性**（人工标注为无害），根因是图例被放在内容区内部 → 应由 **G11 图例位置判据**从源头消除，而非在 G2 里放宽门槛。

> **诚实标注**：`INK_INFLATE=1.15` 是在**同一批 7 对样本上**标定出来的，存在过拟合风险（见 M-8）。它使 3 个有害对全捕获，但**安全窗口仅约 6%**（`ql4↔p12` 膨胀后 ox 仅 5.5px），且与 `MIN_INK_THICKNESS` 方向对冲（见 §3.3 的 D5-08 警示）。缺乏独立验证集。

**禁止用 IoU**（分母须为 `min(areaA, areaB)` 而非并集，IoU 属概念误用）。

**核心创新：ink-box 收缩**。原始难题是面积区间交叠不可分：

| 重叠对 | AABB | ink-box | 性质 |
|--------|-----:|--------:|------|
| `ql1↔ql2` | 3744 | **0** | 无害 |
| `ql4↔p12` | 3042 | 1560 | **有害** |

根因是**居中文本框的 AABB 含大量空白 padding**。按实际文字墨迹收缩后，这两对变为可分。

#### 全库复核结果（勿只看上表 —— 它是部分样本）

对 15 张图**全量**跑 ink-box（辅助函数已按 §3.3.1 纯标准库实现）：

| 指标 | 数值 |
|------|-----:|
| AABB 前景重叠对（已排除背景板） | **25** |
| ink-box 判定重叠对 | **14** |
| 消除的疑似误报 | **11（44%）** |

**ink-box 是显著改进，但不是完全解。** 残留的 14 对中，有 5 对属于**图例条目贴边**，其 ink 相交高度仅 **1~2px**：

```
leg1 <-> leg2   AABB=390  ink=119 (49x2)     ← 7-2 与 11-1 各有数对
legTitle<->leg1 AABB=312  ink= 60 (32x1)
```

这类 1~2px 的相交是**渲染层无害的贴边**，但零容忍判据会把它们判为 error。

**处置裁决**：引入**最小相交厚度**门槛 —— `min(ox, oy) < 3px` 时**降级为 WARNING**（**不是 PASS**）。理由：draw.io 默认 strokeWidth=1，2px 以内的相交在视觉上被边框吸收。这**不是**回退到"面积阈值"（已被证伪的路径），而是对**相交几何形状**的判据 —— 一个 49×2 的细长条与一个 67×13 的块状相交，性质截然不同。

> **D5-07 订正**：此处原写"判 PASS"，与 §3.3.0 三态定义矛盾。**统一为 WARNING** —— 厚度不足只降级，不放行。

> **D5-08 参数对冲警示**：`INK_INFLATE=1.15`（放大墨迹、增加相交）与 `MIN_INK_THICKNESS=3px`（要求厚度达标、减少判定）**方向相反**，其乘积效应未做联合敏感性分析。实测 `leg1↔leg2` 膨胀后厚度**恰为 3.0px**，正好卡在门槛上；`ql4↔p12` 膨胀后 ox 仅 **5.5px**，若 `INK_INFLATE` 取 1.10 则大概率重新漏报 → **安全窗口约 6%**。系统处于参数敏感的临界状态，**两个参数不应各自独立调整**。

采用该门槛后：**25 对 → 9 对**，5 对图例贴边全部消除，`ql3↔p10`(67×13)、`d4↔ringOuter`(176×22)、`dim2↔rightLabel`(109×89) 等真实重叠全部保留。

> **诚实标注**：3px 这个门槛同样是**推断值**（依据 strokeWidth=1 的视觉吸收），未经渲染验证。它把判据从"零容忍"弱化为"厚度零容忍"——**这是一个真实的妥协**，见 M-6。

```python
def ink_box(cell):
    """按文字实际占位收缩 AABB。"""
    text = strip_html(cell.get("value") or "")
    if not text: return None                        # 纯装饰形状 —— 见下方裁决
    fs    = parse_font_size(cell.get("style"))      # 默认 16
    lines = estimate_lines(text, cell.w, fs)
    ink_w = min(cell.w, max_line_width(text, fs))
    ink_h = min(cell.h, lines * fs * 1.4)
    align = parse_align(cell.get("style"))          # center/left/right
    return centered_box(cell, ink_w, ink_h, align)

def overlap_area(a, b):
    ox = min(a.x+a.w, b.x+b.w) - max(a.x, b.x)
    oy = min(a.y+a.h, b.y+b.h) - max(a.y, b.y)
    return ox * oy if ox > 0 and oy > 0 else 0      # 边缘相切判不重叠

MIN_INK_THICKNESS = 3   # px；min(ox,oy) < 3 降级为 WARNING（非 PASS，见 §3.3.0）
```

#### 3.3.1 六个辅助函数的纯标准库实现（已验证可行）

审查关注点：这六个函数在"零第三方依赖"约束下是否真能实现。**已实测通过**，关键是 `unicodedata.east_asian_width` 提供了中英文字宽区分：

```python
import re, html, unicodedata

def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)                      # 处理 &amp; &lt; &gt;

def parse_font_size(style, default=16):
    m = re.search(r"fontSize=(\d+)", style or "")
    return int(m.group(1)) if m else default

def parse_align(style):
    m = re.search(r"(?<![a-zA-Z])align=(\w+)", style or "")
    return m.group(1) if m else "center"          # 负向断言避开 verticalAlign

def char_w(ch, fs):
    """CJK 全角计 1.0×fs，西文计 0.55×fs。"""
    if ch == "\n": return 0
    return fs * (1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.55)

def max_line_width(text, fs):
    return max((sum(char_w(c, fs) for c in ln) for ln in text.split("\n")), default=0)

def estimate_lines(text, box_w, fs):
    n = 0
    for ln in text.split("\n"):
        w = sum(char_w(c, fs) for c in ln)
        n += max(1, int(-(-w // box_w)) if box_w > 0 else 1)
    return max(1, n)
```

实测冒烟结果（含富文本与转义）：

| value | 解析出的 text | fs | align | maxw | lines |
|-------|--------------|---:|-------|-----:|------:|
| `<b>Layer 3 · Knowledge</b><br>知识层` | `Layer 3 · Knowledge\n知识层` | 16 | center | 167.2 | 2 |
| `数据驱动型<br>工程实践强` | `数据驱动型\n工程实践强` | 16 | center | 80.0 | 2 |
| `&amp;&lt;&gt; 转义` | `&<> 转义` | 12 | left | 50.4 | 1 |

**最可能成为实施拦路虎的是 `estimate_lines()`** —— draw.io 的 `whiteSpace=wrap` 实际按**单词边界**折行（西文）而非按字符硬切，中文则可任意断行。当前实现按字符累加宽度做 ceil 除法，对西文长单词会**低估行数**。

#### 3.3.2 无文本装饰形状的处置（必须写死，否则是漏洞）

实测全库有 **5 个无文本的装饰性 vertex**，`ink_box()` 对其返回 `None`。

**裁决：无文本节点回退使用 AABB 参与重叠检查**，不豁免。理由：装饰形状（分隔线、箭头底板、色块）虽无文字，但**占据视觉空间**，压在文字上同样是缺陷。若豁免，则"把所有节点的 value 清空"就成了一条零成本绕过路径。

**边界情况**：A 右边界 x=100、B 左边界 x=100 → `ox = 0` → **判不重叠**（已验证）。

**豁免（白名单式，非开关）**：
- `is_background=True` 显式标记的背景板；
- style 含 `swimlane`/`group`/`container=1` 的容器；
- **完全包含**关系（背景板含子节点）豁免，**部分相交**不豁免。

> 豁免必须**具名到 cell id 或 style 特征**，且**出现在 JSON 报告中可被审计**。绝不能是整体关闭门禁的开关。

### 3.4 G3 溢出分级

| 条件 | 判定 |
|------|------|
| 跨度 ≤ 1.0× page | **PASS** |
| 1.0× < 跨度 ≤ **1.8×** | **WARN** |
| 跨度 > **1.8×** | **FAIL** |

**为何 W/H 两侧统一取 1.8×**（而非调研建议的 W=2.5×、H=1.0×）：

实测 15 张真实图 —— W 比 0.85~1.15、H 比 0.53~**0.97**。**6-1 的 H 比已达 0.97，7-1/9-1 达 0.95**。若按 H=1.0× 硬失败，正常图仅差 0.03 就会被误判。取 1.8× 使最差实测值（1.15）仍有 **56% 裕度**，同时仍能拦住"内容跨度接近 2 倍画布"的真实裁切风险。

> **裕度依据标注为「实测 + 推断」**：1.8 这个具体数值来自"最大实测值 1.15 × 1.5 倍安全系数 ≈ 1.7，向上取整到 1.8"，**未经真实裁切场景验证**（见 L-8）。

### 3.5 G4 网格对齐率 —— 诚实评估

**它主要是伪指标。** 网格对齐影响的是**人工在 draw.io 中继续编辑时的吸附手感**，而非导出 PNG 的观感——实测 8-2 对齐率仅 23.0%，但其 PNG 视觉无异常。

**故定为 warning 而非 error。** 且由于生成器全程 `snap()` 量化，**对齐率恒为 100%**，该检查实际只对 manual 逃生舱产物有意义。

### 3.6 G6 内嵌题注

```python
CAPTION_PAT = re.compile(r"^\s*(图\s*\d+\s*[-–—]\s*\d+|图注)")
CAPTION_IDS = {"title", "note", "caption", "bottomNote"}
```

实测命中 12-1 `bottomNote`、4-1 `note1`、4-2 `note2`。**必须保留为实检查项** —— 不可沿用 `stage-6-diagrams.md:231` 的"0 命中"结论砍掉（该断言已被证伪，见总览 §3.2）。

---

## 3.7 G10 拓扑-模式一致性（C-1 新增，Critical 修复）

### 问题

审查指出的失效模式：**IR 的 `layout_mode` 是枚举，Agent 选错模式会产出"几何完美但语义错误"的图** —— 门禁全绿，图是错的。例如给"主链+分支汇合"的混合拓扑选了 `flow`，生成器会把分支节点硬排成一条直线，几何指标全部合规。

**这是比重叠更危险的缺陷** —— 重叠肉眼可见，语义错误需要读懂图才能发现。

### 判据（纯拓扑判断，O(N+E)，可机器校验）

> **第三轮修订（D5-01~06）**：前两版均有实质缺陷 —— 初版误伤 11/15；第二版的 `FLOW_MAX_FANOUT=3` 经实测**在唯一样本上放行 4-2**（`3 > 3 == False`），且**不存在任何可行取值**（=2 会误伤 8-2）。现改为**零阈值结构判据**，已在 15 张真实图上实跑，0 假阳 0 假阴。

#### G10a（结构自洽，**B1 即可生效**，不依赖 IR）

```python
def g10a(mode, V, E):
    """零阈值结构判据。仅用边集，不需要 rank/layout_mode 声明。"""
    outd, ind, deg = degree_maps(E)

    if mode == "flow":
        # 简单流程链不会"先分叉再汇合"。分叉+汇合 = 混合拓扑
        if any(outd[n] > 1 for n in V) and any(ind[n] > 1 for n in V):
            return "FLOW_RECONVERGENT"

    elif mode == "star":
        if not E: return "STAR_NO_EDGES"
        mx   = max(deg.values())
        hubs = [n for n in V if deg[n] == mx]
        sec  = max((deg[n] for n in V if deg[n] < mx), default=0)
        if len(hubs) != 1:            return "STAR_NO_UNIQUE_HUB"
        if mx < max(3, sec * 2):      return "STAR_HUB_NOT_DOMINANT"

    elif mode in ("grid", "quadrant"):
        # 表格/矩阵的本质是"无连通语义骨架"。装饰引线不会连成大连通块
        if E and largest_component(V, E) > len(V) / 3.0:
            return "GRID_HAS_CONNECTED_STRUCTURE"

    return None
```

**关键改进：全部零数值阈值。** `FLOW_MAX_FANOUT` 与 `GRID_MAX_EDGE_RATIO` **已删除** —— 前者无可行取值，后者取自数据空白区。取而代之的是三个**结构性质**判定（是否重汇合 / 是否存在支配中心 / 是否存在连通骨架），无参数可调，因而无过拟合空间。

> `star` 分支保留两个结构常数（`!= 1` 唯一性、`sec*2` 支配性），但它们是**结构定义**而非拟合阈值：中心唯一是星型的定义，度数至少 2 倍于次高是"支配"的最小合理表述。

#### G10b（模式声明一致性，**需 IR，B4 后生效**）

`stack`/`pyramid` 的 rank 跨层校验。**实测 `rank` 字段全库 0/15 命中** → 该分支在现有产物上**无法执行**，故独立编号、延后生效。

> **D5-05 澄清**：此前把 G10 整体标为"需等 B4"是**把实施顺序选择包装成了技术必然性**。实际上 G10a 用的全部数据（边集、出入度、连通分量）都能从现有 `.drawio` 直接解析 —— 只有 rank 需要声明。

### 3.7.2 实跑标定（15 张真实图，可复现）

```
图      声明        N    E   G10a                                  真值
2-1    flow       11    5   一致 OK                               应通过
4-2    flow       12    9   FLOW_RECONVERGENT                     应标记
8-2    flow       25   25   FLOW_RECONVERGENT                     应标记
10-1   grid      108    0   一致 OK                               应通过
5-1    grid       42    6   一致 OK                               应通过
6-1    grid       44    4   一致 OK                               应通过
7-1    grid       16   11   GRID_HAS_CONNECTED_STRUCTURE(12/16)   应标记
11-1   quadrant   28    0   一致 OK                               应通过
3-2    star       14   14   一致 OK                               应通过
4-1    star       10   12   一致 OK                               应通过
7-2    star       16   15   一致 OK                               应通过
3-1/8-1/9-1/12-1  stack/pyramid  ->  n/a，交 G10b（rank 全库 0 命中）

覆盖 11 张；期望标记 [4-2, 7-1, 8-2] / 实际标记 [4-2, 7-1, 8-2]
假阳性 无   假阴性 无
forced manual 比例 = 3/15 = 20.0%（< 30% warning 线）
```

#### 三处真阳性的独立佐证

| 图 | G10a 判定 | 独立证据（不依赖判据本身） |
|----|----------|------------------------|
| **4-2** | `FLOW_RECONVERGENT` | s3 出度 3 → fp/ip/cp 三路预测，汇合于 s4「Decision」入度 3。即设计文档反复提及的"主链+3分支汇合"混合拓扑 |
| **8-2** | `FLOW_RECONVERGENT` | ①图名「SCOS**三流合一**」；②图内 `id=merge` 节点 value 为"三流汇聚…"，入度 3（df7/kf7/rf7）——**图自己声明的汇聚点**；③原 SCIF 补救方案将其描述为"B 三列"，而模式 B 定义为单链，无法表达三列并汇 |
| **7-1** | `GRID_HAS_CONNECTED_STRUCTURE(12/16)` | 声明 grid 却有 11 条语义边、最大连通块覆盖 12/16 节点 —— 实为分层拓扑图而非表格 |

> **8-2 的意义特别值得注意**：它的几何质量**极佳**（0 重叠、0 溢出、0 图注）。若只看几何判据，它是满分图。**G10a 抓到的正是 C-1 描述的失效模式 —— 几何全绿但模式声明与拓扑不符。** 这是 C-1 在真实数据上第一次被证明确实存在，而非假想风险。

> **真值修正的诚实说明**：8-2 在第三轮初次验证时被我标为"应通过"，导致判据显示 1 个假阳性。经查证图名与 `merge` 节点后确认**是真值标注错误，非判据错误**。修正真值所依据的三条证据**均独立于判据本身**（图名、图内自声明节点、历史方案描述），不构成为判据开脱。

### 失败处置（关键：不允许简单改模式重试）

一致性校验失败 → **不得**让 Agent 换个模式再试。因为拓扑是客观的，"换模式直到通过"等于用穷举绕过语义检查。

正确处置：**登记为"该图拓扑无对应模式"，强制走 `manual`，并计入 manual 使用率统计**。这使模式覆盖不足的真实比例可被观测（回应 M-3）。

**实测校验**：4-2（主链 s1→s2→s3 + 3 分支下挂 + 汇合 Decision）在 `flow` 模式下触发 **`FLOW_RECONVERGENT`**（s3 出度 3 分叉、s4「Decision」入度 3 汇合，同时满足重汇合条件）→ 正确地被拒绝并转入 manual。这与前文"4-2 属混合拓扑、模式覆盖不了"的独立判断**一致**。

---

## 3.8 G11 图例位置（竞品对标新增）

### 来源

`space-architecture-diagram` / `architecture-diagram` 两个同类 skill 给出了**可直接机器校验的量化判据**（此前 D5 仅有"12-1 的 bottomNote 内嵌导致溢出"这类个案观察）：

> 图例必须放在所有边界框之外；计算所有内容边界的最低 Y 坐标，图例至少放在该值下方 **20px**。

### 判据

```python
LEGEND_MIN_GAP = 20   # px

def check_legend_placement(nodes):
    legend = [n for n in nodes if is_legend(n)]      # id/value 含 legend|图例|leg\d
    if not legend: return None
    content = [n for n in nodes if n not in legend and not n.is_background]
    content_bottom = max(n.y + n.h for n in content)
    for lg in legend:
        if lg.y < content_bottom + LEGEND_MIN_GAP:
            return f"LEGEND_INSIDE_CONTENT: 图例 {lg.id} 顶边 y={lg.y} < 内容底边 {content_bottom} + {LEGEND_MIN_GAP}"
```

**这条判据同时解释了此前观测到的一批"图例贴边重叠"**：11-1 的 `leg1~leg5`、7-2 的 `legTitle/leg1~leg3` 之所以产生 1~3px 的 ink 相交（§3.3.3），根因正是图例被放在了内容区域**内部**而非下方 20px 处。**G11 从源头消除这类重叠，比在 G2 里给它们开厚度豁免更正确。**

---

## 3.9 关系类型专属间距（竞品对标新增）

`excalidraw-skill` 按**关系类型**细分间距，而非用统一常数。这比 §2 各模式的固定 `gap` 更精细，采纳为**推荐值表**：

| 关系类型 | 间距取值 | 适用模式 |
|---------|---------|---------|
| 层级（父→子） | 垂直 ≥40px | A / A' |
| 流水线（顺序） | 水平 ≥60px | B |
| 一对多（分叉） | 分支间 ≥30px，主干到分支 ≥50px | manual |
| 多对一（汇合） | 同上 | manual |
| 对比（并列） | 列间 ≥80px | E |
| 循环 | 环上相邻 ≥40px | C |

**同时采纳的 CJK 宽度公式**（比 D5 原"中文按英文 2 倍"更精确，来自 `excalidraw-skill`）：

```
CJK  : node_width ≥ max(160, charCount × 18)
Latin: node_width ≥ max(160, charCount × 9)
```

**注**：D5 的 `char_w()` 采用 `unicodedata.east_asian_width` 逐码位判定（§3.3.1），精度高于按整串估算的上述公式；后者保留为**节点最小宽度的下限校验**，两者互补而非冲突。

**反馈必须是确定性具体数值**，不能是"让 LLM 再看一眼自己的图"（ICLR 2024 已证无外部反馈的自我纠错会持续退化）。

**格式范例**：

```
[G2-硬重叠] 节点 ql4(x=560,y=105,w=624,h=26) 与 p12(x=980,y=110,w=150,h=70)
            ink-box 相交 60×26px（面积 1560）
            建议：模式 E 散点避碰半径不足，增大 dh 或减少该象限散点数
```

每个 issue 必须含**两个 cell 的完整 (x,y,w,h) + 重叠矩形宽高**，不能只给面积。

---

## 5. 本层未闭环局限

| # | 局限 |
|---|------|
| M-1 | **ink-box 是启发式估算**。`estimate_lines()` 按字符宽度累加做 ceil 除法，而 draw.io 的 `whiteSpace=wrap` 对西文按**单词边界**折行 → 长单词会**低估行数**。中英混排、HTML 富文本已实测可解析，但**未在真实渲染引擎上标定**。低估墨迹 → **漏报真重叠（假阴性）**，对声称"零容忍"的判据而言，假阴性比假阳性更致命。 |
| M-6 | **"零容忍"实际是"厚度零容忍"**。全库复核发现 5 对 1~2px 的图例贴边会被误判，故引入 `MIN_INK_THICKNESS=3px` 门槛。**这是一个真实的妥协** —— 判据从"任何相交即失败"弱化为"相交厚度 ≥3px 才失败"。3px 依据 strokeWidth=1 的视觉吸收推断，**未经渲染验证**。 |
| M-7 | **ink-box 效果的真实量级低于初版结论**。初版基于 11-1 部分样本称"无害项归零"；全库复核实际为 **25→14 对（消除 44%）**，加 3px 门槛后 **25→9 对**。仍有 9 对需人工确认是真重叠还是判据不足。 |
| M-2 | **1.8× 溢出阈值未经真实裁切验证**。它由实测最大值加安全系数推断而来，**没有一张真实被裁切的图作为正样本**。 |
| M-3 | **五种模式覆盖率未量化**。15 张实测图中 4-2 属混合拓扑，模式覆盖不了 → 至少 1/15 需走 manual。真实项目的 manual 比例未知。 |
| M-4 | **机器合规 ≠ 美学良好**。星型模式 12 辐条时机器全绿但视觉拥挤；网格模式在稀疏数据下会产出大片空白。门禁只能保证"不出废品"。 |
| M-5 | **避碰的单调下推可能破坏语义**。模式 E 的散点沿 y 轴下推避碰，若推挤过多会使散点偏离其语义评分位置——**精度与无重叠之间存在无法两全的取舍**，当前设计优先无重叠。 |
| M-8 | **`INK_INFLATE=1.15` 存在过拟合风险**。它在 §3.3.3 那**同一批 7 对样本**上标定出来，恰好使 3 个有害对全捕获、3 个无害对全归零——这个"恰好"**缺乏独立验证集**。真实的假阴性率未知。 |
| M-9 | **G10b 依赖 `rank` 字段的正确性**。若 Agent 把 rank 填错（如两个节点填同一 rank），校验会误判。rank 是语义、无法机器校验其正确性——**这是 G10b 的判据边界**。**且 rank 全库 0 命中 → G10b 在 B4 之前无法验证。**（G10a 不受此限，已实跑通过） |
| ~~M-11~~ | ~~G10 三阈值过拟合~~ → **已消除**：第三轮改为零阈值结构判据，`FLOW_MAX_FANOUT`/`GRID_MAX_EDGE_RATIO` 已删除。残留的 `star` 两个结构常数是定义而非拟合值。 |
| **M-12** | **G10a 的三处真阳性中，8-2 的真值曾被我标错**（初次验证标为"应通过"，产生 1 个假阳性）。虽已用三条独立证据（图名/图内自声明节点/历史方案描述）修正，但**这暴露了真值标注本身缺乏独立来源** —— 15 张图的"应通过/应标记"由我判定，无第三方标注。**判据的 0 假阳 0 假阴是相对于我自己的标注而言的。** |
| M-10 | **全部阈值来自 15 张同源、且已被人工修复过一轮的图**（H-5）。这批图不是原始故障态，导致阈值可能**定得过松**——真实的"坏图"分布未被观测。B1 上线后必须用未修复过的新项目数据重新标定。 |
