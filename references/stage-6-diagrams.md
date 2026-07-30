---
portability: core
---

# 阶段 6：核心架构图——先于写作

> 本文件是 deep-research-report skill 的阶段 6 详细 spec，从 SKILL.md 拆分而来。
> 母文件：`../SKILL.md`（流程索引）

---

## 图表术语统一声明

在本 skill 中，三类视觉元素使用如下严格区分：

| 术语 | 定义 | 负责 Agent | 工具 | 质量门槛 |
|------|------|-----------|------|---------|
| **架构图** | 阶段 6 产出的核心架构图（总览图/架构图/流程图）——报告的骨架，先于写作完成 | `architecture_chart_agent` (Sonnet) | drawio MCP / fireworks-tech-graph / Mermaid | 阶段6 CHECKPOINT + figure_gate.py 门禁 |
| **数据图表** | 阶段 7 产出的 matplotlib 图表（对比图/趋势图/份额图/雷达图等）——随写作按章产出 | `data_chart_agent` (Sonnet) | matplotlib + report 样式模板 | 阶段7质量门槛 + chart_checks.py |
| **表格** | Markdown 原生表格——正文组成部分，Writer 直接编制 | `chapter_writer_agent` (Sonnet) | Markdown 表格语法 | 阶段7合约检查 C4 + gate3 表格框线 |

> 三者使用不同的 Agent、工具和质量门槛，不可混淆。**"架构图"不是"数据图表"的上位词**——前者是阶段6产物，后者是阶段7产物。"图"（figure）泛指架构图+数据图表的 PNG 嵌入，"表"（table）指 Markdown 表格正文。

---

**核心架构图必须在分章写作之前完成**。它们是报告的骨架——定义分析框架、拆解层次、展示逻辑链路，文字要围绕它们展开。

## 6.1 出图清单

从阶段 4.3 的"核心架构图"清单取出图号和图名，再从阶段 5 的**架构卡**（`research/notes/architecture-cards/`）取出"组件与关系""数据流"作为具体绘制素材——阶段 4.3 只锁定"要画什么图"，架构卡才是"图里具体画什么"的依据。按此优先级：

1. **总览图**（1–3 张）—— 全文核心判断、主题闭环图，读者看完就理解报告主线
2. **架构图**（3–6 张）—— 主题的 X 层架构拆解，报告的分析框架
3. **流程图**（3–5 张）—— 关键流程的端到端展示

## 6.2 出图工具——选择与使用

根据图的类型选择合适的工具：

| 图类型 | 首选工具 | 输出格式 | 保存路径 |
|--------|---------|---------|---------|
| **架构图、流程图**（分层/组件/连接关系复杂） | drawio | `.drawio` + `.svg` | `research/figures/` |
| **技术架构图**（系统拓扑/技术栈分层/部署架构） | fireworks-tech-graph | `.svg` + `.png` | `research/figures/` |
| **简单流程图/时序图**（线性逻辑） | Mermaid（内联到 Markdown） | 无需独立文件 | — |

---

### 工具 A：drawio — 架构图、流程图

**生成 `.drawio` 文件**：使用 MCP 工具 `mcp__drawio__create_diagram`，通过 Mermaid 语法或 mxGraphModel XML 生成，返回的 XML 直接写入文件即可。

```text
调用: mcp__drawio__create_diagram
  参数: mermaid (流程图/架构图/泳道图推荐) 或 xml (需精确控制布局时)
  写入: 将返回的 xml 字段内容写入 research/figures/<图号-描述>.drawio
```

**图表样式约束**：调用 `mcp__drawio__create_diagram` 时，在 Mermaid/XML 描述之后注入样式约束文本（完整模板见 `design/chart-quality-constraints/chart-quality-checklist.md` 第四节）：
- 配色：灰度色板 + 暗红 #D62728 唯一强调色
- 字体：≥12px（≈9pt），标题 ≥14px
- 边框：1pt #333333，箭头 1.5pt
- 背景：纯白 #FFFFFF
- 图例：>2 种灰度/形状时必须附

**导出 SVG**：通过 draw.io 桌面版 CLI 导出。路径配置见 `references/tool-paths.json` 中 `drawio_desktop.absolute_path` 字段。

> **执行前**：先读取 `references/tool-paths.json`，取 `drawio_desktop.absolute_path`。若已填写 → 直接使用；若为空 → 用 `where draw.io`（Win）或 `which draw.io`（Linux/macOS）查找。

| 项 | 状态 |
|----|------|
| draw.io MCP（生成 `.drawio`） | ✅ 可用 |
| draw.io 桌面版（导出 SVG） | ✅ 已安装 | 路径见 `tool-paths.json` 中 `drawio_desktop.absolute_path`；也可通过 `where draw.io`（Win）或 `which draw.io`（Linux/macOS）查找 |

```powershell
# 路径取自 tool-paths.json 中 drawio_desktop.absolute_path，如为空则用 where/which 查找
& "<draw.io 安装路径>/draw.io.exe" -x -f svg -e -b 10 -o research/figures/<图名>.drawio.svg research/figures/<图名>.drawio
```

`-e` 将原始 `.drawio` XML 嵌入 SVG，导出的 SVG 可通过 draw.io 重新编辑；`-b 10` 加 10px 边距。

**导出 PNG（docx 嵌入格式，300dpi+ 必须）**：SVG 仅用于人工编辑，docx 嵌入统一用 PNG（研究报告格式规范 V3.1 §5.2）。draw.io 桌面版可直接导出 300dpi PNG：

```powershell
& "<draw.io 安装路径>/draw.io.exe" -x -f png --scale 3.125 -b 10 -o research/figures/<图名>.drawio.png research/figures/<图名>.drawio
python -c "
from PIL import Image
p = 'research/figures/<图名>.drawio.png'
img = Image.open(p)
img.save(p, dpi=(300, 300))
print('PNG 300dpi OK, size:', img.size)
"
```

`--scale 3.125` 对应 300dpi/96dpi 的缩放系数，与 SVG 导出保持一致的边距（`-b 10`）。

**文件命名**：`<图号>-<描述>.drawio`（源文件）+ `<图号>-<描述>.drawio.svg`（人工编辑用）+ `<图号>-<描述>.drawio.png`（docx 嵌入用），如 `2-1-技术架构全景.drawio`。

> **⚠️ 如果 draw.io 桌面版不可用**（未安装 / `tool-paths.json` 路径为空且 `where draw.io` 找不到）：
> 1. **降级导出**：使用 draw.io 在线版（https://app.diagrams.net/）手动打开 `.drawio` 文件 → File → Export as → PNG（设置 300dpi，`scale=300/96≈3.125`）
> 2. **在线版也不可用** → 使用 MCP `mcp__drawio__create_diagram` 的 `mermaid` 参数仅输出 Mermaid 渲染（无 .drawio 源文件编辑能力），标注该图"无源文件，后续修改需重做"
> 3. **仍失败** → 该架构图降级为文字描述段落（在阶段7写作中用文字替代图形表达架构关系），在质量门槛备注中记录

---

### 工具 B：fireworks-tech-graph — 技术架构图

**生成 SVG + PNG**：使用 `generate-from-template.py` 生成 SVG，再用 `cairosvg` 导出 PNG。**PNG 必须达到 300dpi+ 并写入 pHYs 物理尺寸元数据**（研究报告格式规范 V3.1 §5.2 强制要求；PNG 是 docx 嵌入的唯一格式，SVG 仅保留用于人工后续编辑，不用于嵌入——python-docx 技术上不支持 SVG 嵌入，经实测验证）。

**路径配置**：`references/tool-paths.json` 中 `fireworks_tech_graph.absolute_path` 字段。如为空则使用相对路径 `fireworks-tech-graph/scripts/generate-from-template.py`。

> **执行前**：先读取 `references/tool-paths.json`，取 `fireworks_tech_graph.absolute_path`。若已填写 → `python -X utf8 "<absolute_path>" ...`；若为空 → `python -X utf8 "fireworks-tech-graph/scripts/generate-from-template.py" ...`。

**实测可用** ✅：SVG 生成和 PNG 导出（含 DPI 元数据写入）均验证通过。

```powershell
# Step 1: 生成 SVG（architecture 模板）
# Windows 上须加 -X utf8 避免 GBK 编码错误
python -X utf8 "fireworks-tech-graph/scripts/generate-from-template.py" `
  architecture `
  research/figures/<图号-描述>.svg `
  '{"title":"<图标题>","nodes":[...],"arrows":[...]}'

# Step 2: 验证 SVG 语法
python -c "import xml.etree.ElementTree as ET; ET.parse('research/figures/<图名>.svg'); print('SVG OK')"

# Step 3: 导出 PNG（300dpi，缩放系数按 300/96≈3.125 计算，并写入 pHYs 元数据）
python -c "
import cairosvg
from PIL import Image
svg_path = 'research/figures/<图名>.svg'
png_path = 'research/figures/<图名>.png'
cairosvg.svg2png(url=svg_path, write_to=png_path, scale=300/96)
img = Image.open(png_path)
img.save(png_path, dpi=(300, 300))
print('PNG 300dpi OK, size:', img.size)
"
```

**JSON 数据格式**（传入 `generate-from-template.py` 的第三个参数，注意 PowerShell 中 JSON 用单引号包裹、内部用双引号）：
```json
{
  "title": "六层技术架构全景",
  "nodes": [
    {"id": "perception", "label": "感知层", "x": 40, "y": 40, "width": 880, "height": 80},
    {"id": "network", "label": "网络层", "x": 40, "y": 160, "width": 880, "height": 80}
  ],
  "arrows": [
    {"source": "perception", "target": "network", "label": "观测数据"}
  ]
}
```

**可用模板类型**：`architecture`（架构图）、`data-flow`（数据流）、`flowchart`（流程图）、`sequence`（时序图）、`agent`（Agent 架构）、`memory`（记忆架构）、`network-topology`（网络拓扑）、`class`（UML 类图）、`state-machine`（状态机）、`er-diagram`（ER 图）等。

**样式参考**：默认 Style 1（Flat Icon，白底），加载 `fireworks-tech-graph/references/style-1-flat-icon.md` 获取精确色值。

**文件命名**：`<图号>-<描述>.svg` + `<图号>-<描述>.png`，如 `4-1-技术架构全景.svg` + `4-1-技术架构全景.png`。

---

### 工具 C：Mermaid — 简单流程图（备选，需渲染为 PNG）

适用场景：简单线性流程（≤15 个节点）。**不再允许仅停留在 Markdown 代码块中——必须产出可嵌入的 PNG 文件**，否则这些 Mermaid 图将在阶段 9 的 docx 转换中全部丢失（python-docx 无法渲染 Mermaid 代码块）。

**Mermaid → PNG 渲染路径**（按可用性降级）：

**路径 1：mmdc（mermaid-cli）——首选**
```powershell
# 如 mmdc (mermaid-cli) 已安装且可用
mmdc -i research/figures/<图号-描述>.mmd -o research/figures/<图号-描述>.mmd.png --scale 3 --backgroundColor white

# 写入 DPI 元数据
python -c "
from PIL import Image
p = 'research/figures/<图号-描述>.mmd.png'
img = Image.open(p)
img.save(p, dpi=(300, 300))
print('PNG 300dpi OK, size:', img.size)
"
```
`--scale 3` 确保输出分辨率足够 300dpi 打印。mmdc 路径配置见 `references/tool-paths.json` 中 `mermaid_cli` 条目。

**路径 2：drawio MCP 降级——mmdc 不可用时的备选**
```text
调用: mcp__drawio__create_diagram
  参数: mermaid（传入原 .mmd 文件内容）
  写入: 将返回的 xml 字段内容写入 research/figures/<图号-描述>.drawio
```
然后按工具 A（drawio）的导出步骤将 .drawio 导出为 PNG。

**路径 3：在线 mermaid.live 手动导出——以上两条均不可用**
标注该图为"手动渲染"，记录到质量门槛备注中。

> **注意**：复杂架构图（>15 节点、含复杂布局）仍用 drawio（工具 A），不因 Mermaid 渲染路径存在而降级使用。Mermaid 仅用于简单流程图。

### ▶ 阶段 6 质量门槛

- [ ] 总览图至少 1 张完成（`.drawio` 源文件 + `.svg`（人工编辑用）+ `.png`（docx 嵌入用，300dpi+ 含 pHYs 元数据）已保存到 `research/figures/`）
- [ ] **所有 Mermaid 产出的流程图已渲染为 PNG**：检查所有 Mermaid `.mmd` 源文件均有对应的 `.png` 渲染产物，不存在仅停留在 Markdown 代码块中的 Mermaid 图。如果 mmdc 不可用且 drawio 降级路径也不可用，标注为"手动渲染"并记录到质量门槛备注
- [ ] 每个核心分析章节至少 1 张架构图草图
- [ ] 架构图之间逻辑一致（同一对象在不同图中名称统一）
- [ ] 所有架构图有逻辑或来源标注（在图注中说明）
- [ ] 所有 PNG 均已验证达到 300dpi（`PIL.Image.open(p).info.get('dpi')` 应为 `(300, 300)` 或更高）
- [ ] **颜色映射注册表已创建**：`research/figures/color-registry.csv` 已建立，至少覆盖本报告所有核心分析章对应的架构图首张图。每个节点/实体的颜色登记后，后续出图直接复用，确保同一概念的跨图一致性
- [ ] **配色符合灰度色板**：所有架构图仅在灰度色板（#000000 / #333333 / #555555 / #777777 / #999999 / #BBBBBB / #DDDDDD / #F2F2F2 / #FFFFFF）中选择颜色。如使用强调色，仅限暗红 #D62728 且全图 ≤3 处。抽查 2 张图确认无违规彩色
- [ ] **PNG 分辨率达标**：所有 PNG 宽度 ≥1102px（对应 14cm 宽、~9pt 文字在 200dpi 下的最低打印可读阈值，与阶段 9 转换器已有的 W-IMG-02 检查一致）
- [ ] **已运行 `figure_gate.py` 且 exit code 为 0**（见下方 §6.9，机器校验，非人眼勾选）

### 6.9 figure_gate.py 机器门禁（D3-1/D4-6，**必须实际执行**）

**为什么单独立节**：此前 `figure_gate` 在本文件中**只出现在 §一的表格单元格里**（一个"门禁名"字符串），全文 6 处 `python` 调用无一是 figure_gate——**有门禁名、无可执行调用点**。这正是"最强措辞 + 零可执行调用点 = 零效果"的实例：反例清单第 20 条已写"exit code 非零即阻断，零人工干预"，但被约束的脚本从来没被调用过。

CHECKPOINT 之前**必须实际执行**：

```bash
python scripts/figure_gate.py --outline research/outline.md \
    --figures-dir research/figures --stage stage6
```

**exit code 非零即阻断，零人工干预。** 不得以"图都在目录里、我看过了"替代本命令。

门禁的判定口径（D3-1 修复后）：

| 项 | 行为 |
|---|---|
| manifest 解析 | 同时支持 **list 形态**（`- fig_id: ...`）与 dict 形态；list 条目键名自动映射 `fig_id`→`figure_id`、`fig_title`→`title`、`fig_type` 含"架构"→`architecture` |
| **清单为空** | 若 outline 声明了 `core_architecture_figures > 0` 而解析出的清单为空 → **判 FAIL**（此前无条件 `passed: True` + exit 0，导致"声明 15 张图、一张都没检查过"） |
| 宽度 / 尺寸 | `< 1102px` 或尺寸异常 → 计入 `errors`，阻断 |
| DPI | 缺少 DPI 元数据 → 计入 `warnings`，**不阻断**（实测真实项目 15/15 架构图均无 dpi 元数据，若计入硬失败会使门禁全红、验收永不通过，反向逼迫放宽门禁）；DPI 存在但 `< 300` → 计入 `errors`，阻断 |

> **诚实标注**：`fontSize < 12` 与"内嵌题注"两项检查在真实项目上实测 **0 命中**（实际最小字号 12/14/16，题注统一写在 Markdown 而非图内），属"为不存在的问题写代码"，故**不作为阻断依据**。以 0 命中的检查充当门禁核心是虚假保证。

🔴 CHECKPOINT · 🛑 STOP：总览图和核心章架构图就位、且 `figure_gate.py` exit code 为 0 后进入阶段 7。总览图未完成、核心章缺架构图、或门禁未通过 → 回到阶段 6.1 补充。
