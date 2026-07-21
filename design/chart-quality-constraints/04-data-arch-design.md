# 数据架构设计文档：图表质量约束——颜色注册表与命名规范

> **设计任务**：为 deep-research-report skill 的跨图一致性保障设计两个数据模块：(A) 跨图颜色映射注册表，(B) 架构图节点命名规范。
> **版本**：v1.0
> **日期**：2026-07-21
> **上游输入**：SKILL.md（9 阶段方法论）、`references/研究报告格式规范.md` V3.1、`references/architecture-analysis-guide.md`、fireworks-tech-graph Style-1-flat-icon

---

## 1. 数据需求总览

| 数据项 | 来源 | 现有/新增 | 更新频率 | 依赖 |
|--------|------|----------|---------|------|
| 颜色注册表（color-registry.yaml） | 阶段5 架构卡自动提取 + 阶段4 大纲图表清单人工确认 | **新增** | 阶段5→阶段6 之间创建，阶段6/7 读取，阶段8 验证后锁定 | `research/notes/architecture-cards/` |
| 命名注册表（融入 color-registry.yaml） | 同上 | **新增** | 同上 | 同上 |
| 架构卡组件清单 | 阶段5 产出 | 现有 | 每张架构卡产出时写入 | `research/notes/card-index.csv` |
| 图表文件（drawio/SVG/PNG） | 阶段6 + 阶段7 | 现有 | 出图时写入 `research/figures/` | color-registry.yaml、命名注册表 |
| 红队风险清单 | 阶段8 产出 | 现有 | 阶段8 审查时写入 | color-registry.yaml、图表文件 |
| 图表索引（figures-index.csv） | **新增** | **新增** | 阶段6/7 出图时登记 | 图表文件 |

### 1.1 与现有数据体系的对接

```text
现有体系（SKILL.md 已定义）：
  research/
    notes/
      architecture-cards/     ← 颜色/命名注册表的素材来源（阶段5）
      card-index.csv          ← 卡片登记（现有）
    figures/                  ← 图表存储（阶段6/7），颜色/命名注册表的验证目标
    claims/claims-ledger.csv  ← 不直接使用，但注册表条目可关联 claim_id
    drafts/

新增数据资产（本次设计产出）：
  research/figures/
    color-registry.yaml       ← 颜色+命名联合注册表（核心新增）
    figures-index.csv         ← 图表索引（辅助验证用）
  references/
    color-mapping-rules.yaml  ← 灰色系层级映射规则（项目级可复用配置）
    naming-rules.yaml         ← 命名规范配置（项目级可复用配置）
```

---

## 2. 模块 A：跨图颜色映射注册表

### 2.1 注册表 Schema 设计

#### 2.1.1 存储格式与位置

**格式**：YAML（与项目现有工具链兼容——`references/tool-paths.json`、`references/*.md` 均为 YAML/结构化文本；Python 生态 `PyYAML` 原生解析，无需额外安装依赖）。

**存储位置**：
- **主注册表**（报告级）：`research/figures/color-registry.yaml`
  - 随报告项目走，每份报告独立一份
  - 在阶段 5 架构卡完成后、阶段 6 出图前由 agent 自动生成初稿
- **映射规则配置**（项目级，可复用）：`references/color-mapping-rules.yaml`
  - 放置在 skill 的 `references/` 目录下，跨报告复用
  - 用户可编辑以适配不同架构模式的层级颜色映射

#### 2.1.2 完整 Schema

```yaml
# ============================================================
# 颜色注册表 V1.0 — 报告级
# 位置：research/figures/color-registry.yaml
# 用途：确保同一概念在所有图表（架构图/数据图表/流程图）中使用一致的颜色
# 生命周期：阶段5→6之间创建初稿 → 阶段6/7使用 → 阶段8验证 → 阶段9锁定
# ============================================================

# --- 元数据 ---
meta:
  report_id: ""                    # 报告唯一标识（取自阶段1项目名）
  report_title: ""                 # 报告题名
  created_at: "2026-07-21T00:00:00Z"
  updated_at: "2026-07-21T00:00:00Z"
  version: 1
  status: draft                   # draft | in_use | verified | locked
  verified_by: ""                 # 阶段8验证通过的审查者标识
  schema_version: "1.0"

# --- 全局调色板 ---
# 定义报告中可用的所有颜色。每条颜色有唯一 color_id，
# 概念条目通过 color_id 引用（而非直接引用 hex），
# 这样更换调色板时只需修改此处，所有概念自动跟随。
palette:
  # ---- 灰度核心 ----
  - color_id: gray-900
    hex: "#111827"
    display_name: "最深灰"
    role: text-primary          # text-primary | text-secondary | layer-fill | accent | background
  - color_id: gray-700
    hex: "#374151"
    display_name: "深灰"
    role: text-secondary
  - color_id: gray-500
    hex: "#6b7280"
    display_name: "中灰"
    role: text-secondary
  - color_id: gray-300
    hex: "#d1d5db"
    display_name: "浅灰"
    role: background
  - color_id: gray-100
    hex: "#f3f4f6"
    display_name: "最浅灰"
    role: background

  # ---- 层级填充灰（按架构深度分配）----
  # 六级灰系：L1（最底层/最浅）→ L6（最顶层/最深）
  # 具体映射规则见 references/color-mapping-rules.yaml
  - color_id: layer-gray-L1
    hex: "#f9fafb"
    display_name: "层级灰 L1"
    role: layer-fill
  - color_id: layer-gray-L2
    hex: "#e5e7eb"
    display_name: "层级灰 L2"
    role: layer-fill
  - color_id: layer-gray-L3
    hex: "#d1d5db"
    display_name: "层级灰 L3"
    role: layer-fill
  - color_id: layer-gray-L4
    hex: "#9ca3af"
    display_name: "层级灰 L4"
    role: layer-fill
  - color_id: layer-gray-L5
    hex: "#6b7280"
    display_name: "层级灰 L5"
    role: layer-fill
  - color_id: layer-gray-L6
    hex: "#374151"
    display_name: "层级灰 L6"
    role: layer-fill

  # ---- 语义强调色（少量使用，仅用于关键信号）----
  # 遵循格式规范 V3.1 "黑白灰为主"原则，强调色仅在必要时使用
  - color_id: accent-blue
    hex: "#2563eb"
    display_name: "强调蓝"
    role: accent                # 用于数据流/主流程箭头
  - color_id: accent-blue-light
    hex: "#eff6ff"
    display_name: "强调蓝浅底"
    role: accent-background     # 用于强调蓝对应节点的填充
  - color_id: accent-red
    hex: "#dc2626"
    display_name: "强调红"
    role: accent                # 用于风险/瓶颈/阻断标记
  - color_id: accent-red-light
    hex: "#fef2f2"
    display_name: "强调红浅底"
    role: accent-background
  - color_id: accent-green
    hex: "#16a34a"
    display_name: "强调绿"
    role: accent                # 用于优化/增长/通过标记
  - color_id: accent-green-light
    hex: "#f0fdf4"
    display_name: "强调绿浅底"
    role: accent-background

  # ---- 对比图专用色（阶段7数据图表）----
  # 用于分组柱状图/多折线/饼图等需要多色区分时
  - color_id: chart-series-1
    hex: "#374151"
    display_name: "系列色1（深灰）"
    role: chart-series
  - color_id: chart-series-2
    hex: "#6b7280"
    display_name: "系列色2（中灰）"
    role: chart-series
  - color_id: chart-series-3
    hex: "#9ca3af"
    display_name: "系列色3（浅灰）"
    role: chart-series
  - color_id: chart-series-4
    hex: "#2563eb"
    display_name: "系列色4（蓝）"
    role: chart-series
  - color_id: chart-series-5
    hex: "#dc2626"
    display_name: "系列色5（红）"
    role: chart-series
  - color_id: chart-series-6
    hex: "#16a34a"
    display_name: "系列色6（绿）"
    role: chart-series

  # ---- 线型定义 ----
  line_styles:
    - style_id: solid-main
      stroke_width: 1.5
      dash_array: ""             # 实线
      display_name: "主连线"
    - style_id: solid-thin
      stroke_width: 0.75
      dash_array: ""
      display_name: "辅助连线"
    - style_id: dashed-flow
      stroke_width: 1.0
      dash_array: "6,4"          # 虚线：数据流
      display_name: "数据流线"
    - style_id: dashed-feedback
      stroke_width: 1.0
      dash_array: "4,4"          # 短虚线：反馈/异步
      display_name: "反馈线"
    - style_id: dotted-dependency
      stroke_width: 0.75
      dash_array: "2,4"          # 点线：依赖关系
      display_name: "依赖线"

# --- 概念-颜色映射  ---
# 一条 concept 对应报告中一个有独立视觉身份的概念/组件
# 所有包含该概念的图表必须使用此处定义的颜色和线型
concepts:
  # ====== 示例条目：六层架构中的"感知层" ======
  - concept_id: ARCH-layer-01
    concept_name: "感知层"
    concept_name_en: "Perception Layer"
    description: "数据采集与感知子系统，位于六层架构最底层"
    # 颜色设定：引用 palette 中的 color_id
    fill_color: layer-gray-L1          # #f9fafb（最浅灰——底层）
    stroke_color: gray-300             # #d1d5db
    text_color: gray-900               # #111827
    accent_color: null                 # 无额外强调色
    color_role: layer-fill             # primary | secondary | accent | layer-fill | background
    # 连线样式（该概念对外连线默认使用的样式）
    line_style: dashed-flow            # 数据流线：感知层主要向网络层传输数据
    # 适用图表类型
    applies_to:
      - architecture-diagram           # 架构图
      - data-flow-diagram              # 数据流图
      - system-overview                # 总览图
    # 命名一致性字段（见模块 B）
    canonical_name: "感知层"
    display_name_short: "感知层"
    display_name_full: "感知层 (Perception Layer)"
    # 别名登记——同一概念的其他称呼
    aliases:
      - "感知子系统"
      - "数据采集层"
      - "Sensor Layer"
    # 禁止使用的名称
    forbidden_names:
      - "传感层"
      - "采集子系统"
    # 架构位置
    architecture_position:
      layer_index: 1                   # 从底向上第1层
      layer_name: "感知层"
      parent_concept: null
      sibling_concepts: []             # 同层其他概念（如有）
    # 证据追溯
    evidence_packets: ["C-023", "C-024"]     # 关联 claim_id
    source_cards: ["ARCH-01"]                 # 关联架构卡 ID
    # 下游制图工具对应的颜色表现方式
    tool_mappings:
      drawio:
        fillColor: "#f9fafb"
        strokeColor: "#d1d5db"
        fontColor: "#111827"
      fireworks-tech-graph:
        fill: "#f9fafb"
        stroke: "#d1d5db"
        text_fill: "#111827"
      matplotlib:
        facecolor: "#f9fafb"
        edgecolor: "#d1d5db"
        text_color: "#111827"

  # ====== 示例条目：六层架构中的"网络层" ======
  - concept_id: ARCH-layer-02
    concept_name: "网络层"
    concept_name_en: "Network Layer"
    description: "通信与数据传输子系统，位于六层架构第二层"
    fill_color: layer-gray-L2
    stroke_color: gray-300
    text_color: gray-900
    accent_color: null
    color_role: layer-fill
    line_style: dashed-flow
    applies_to:
      - architecture-diagram
      - data-flow-diagram
    canonical_name: "网络层"
    display_name_short: "网络层"
    display_name_full: "网络层 (Network Layer)"
    aliases:
      - "通信层"
      - "传输层"
    forbidden_names:
      - "网络子系统"
    architecture_position:
      layer_index: 2
      layer_name: "网络层"
      parent_concept: null
    evidence_packets: ["C-025"]
    source_cards: ["ARCH-01"]
    tool_mappings:
      drawio:
        fillColor: "#e5e7eb"
        strokeColor: "#d1d5db"
        fontColor: "#111827"
      fireworks-tech-graph:
        fill: "#e5e7eb"
        stroke: "#d1d5db"
        text_fill: "#111827"
      matplotlib:
        facecolor: "#e5e7eb"
        edgecolor: "#d1d5db"
        text_color: "#111827"

  # ====== 示例条目：非架构层概念——"数据中台" ======
  - concept_id: COMP-data-platform
    concept_name: "数据中台"
    concept_name_en: "Data Middle Platform"
    description: "整合多源数据、提供统一数据服务的中间平台组件"
    fill_color: gray-100
    stroke_color: gray-500
    text_color: gray-900
    accent_color: accent-blue
    color_role: primary               # 核心组件，需突出
    line_style: solid-main
    applies_to:
      - architecture-diagram
      - data-flow-diagram
      - flowchart
      - system-overview
    canonical_name: "数据中台"
    display_name_short: "数据中台"
    display_name_full: "数据中台 (Data Middle Platform)"
    aliases:
      - "数据平台"
      - "数据中心"
    # 关键：所有别名都指向同一个概念，禁止在图中写其他名称
    forbidden_names:
      - "数据平台"                    # 虽然登记为别名（允许旧文档识别），
      - "数据中心"                    # 但**出图时严禁使用**——必须用 canonical_name
    architecture_position:
      layer_index: null               # 跨层组件，不绑定特定层
    evidence_packets: ["C-045", "C-046"]
    source_cards: ["TECH-03"]
    tool_mappings:
      drawio:
        fillColor: "#f3f4f6"
        strokeColor: "#6b7280"
        fontColor: "#111827"
      fireworks-tech-graph:
        fill: "#f3f4f6"
        stroke: "#6b7280"
        text_fill: "#111827"
      matplotlib:
        facecolor: "#f3f4f6"
        edgecolor: "#6b7280"
        text_color: "#111827"

  # ====== 示例条目：流程概念——"数据采集" ======
  - concept_id: FLOW-data-collection
    concept_name: "数据采集"
    concept_name_en: "Data Collection"
    description: "从感知层获取原始数据的流程步骤"
    fill_color: gray-100
    stroke_color: gray-500
    text_color: gray-900
    accent_color: accent-green
    color_role: secondary             # 流程中的步骤节点
    line_style: solid-main
    applies_to:
      - flowchart
      - data-flow-diagram
    canonical_name: "数据采集"
    display_name_short: "数据采集"
    display_name_full: "数据采集 (Data Collection)"
    aliases:
      - "数据获取"
      - "Data Acquisition"
    forbidden_names: []
    evidence_packets: ["C-023"]
    source_cards: ["ARCH-01"]
    tool_mappings:
      drawio:
        fillColor: "#f3f4f6"
        strokeColor: "#6b7280"
        fontColor: "#111827"
      fireworks-tech-graph:
        fill: "#f3f4f6"
        stroke: "#6b7280"
        text_fill: "#111827"

# --- 架构模式 → 层级映射规则引用 ---
# 不在此文件中写死映射逻辑——指向 references/color-mapping-rules.yaml 中的规则 ID
layer_color_rule: "six-layer-bottom-light"   # 六层架构：底浅→顶深
```

#### 2.1.3 Schema 字段说明

| 字段组 | 字段 | 类型 | 必填 | 说明 |
|--------|------|------|------|------|
| `meta` | `report_id` | string | 是 | 报告唯一标识 |
| `meta` | `status` | enum | 是 | draft → in_use → verified → locked |
| `palette` | `color_id` | string | 是 | 颜色唯一 ID，概念通过此 ID 引用 |
| `palette` | `hex` | string | 是 | 6 位 hex 色值（含 `#`） |
| `palette` | `role` | enum | 是 | text-primary / text-secondary / layer-fill / accent / accent-background / chart-series / background |
| `concepts[*]` | `concept_id` | string | 是 | 概念唯一 ID，命名规则：`{类型前缀}-{名称}`，如 `ARCH-layer-01`、`COMP-data-platform` |
| `concepts[*]` | `fill_color` | color_id | 是 | 节点填充色，引用 `palette.color_id` |
| `concepts[*]` | `stroke_color` | color_id | 是 | 节点边框色 |
| `concepts[*]` | `applies_to` | list[enum] | 是 | architecture-diagram / flowchart / data-flow-diagram / system-overview / comparison-chart / trend-chart |
| `concepts[*]` | `forbidden_names` | list[string] | 是 | 图表中禁止出现的名称列表 |
| `concepts[*]` | `tool_mappings` | object | 条件必填 | 按出图工具分别指定颜色值。**若仅提供 palette 引用而 tool_mappings 缺失，验证时将无法精确匹配，仅能做近似色差检测** |

#### 2.1.4 concept_id 命名规范

```
{前缀}-{层级或类别}-{序号}

前缀：
  ARCH    — 架构层概念（如 ARCH-layer-01）
  COMP    — 独立组件（如 COMP-data-platform）
  FLOW    — 流程节点（如 FLOW-data-collection）
  SYS     — 系统/整体概念（如 SYS-closed-loop）
  EXT     — 外部实体（如 EXT-user、EXT-third-party-api）

序号：同前缀同类别内从 01 递增
```

### 2.2 注册表生命周期

```text
阶段4（大纲）              阶段5（卡片）              阶段6（出图前）
    │                          │                          │
    ├─ 图表清单锁定           ├─ 架构卡产出              ├─ [创建] color-registry.yaml
    │  (核心架构图有图号       │  "组件与关系"字段         │   从架构卡自动提取概念列表
    │   和图名)               │   含概念列表              │   并填充到注册表
    │                          │                          │
    │                          │                          ▼
    │                          │                    阶段6（出图时）
    │                          │                    [使用] 读取注册表
    │                          │                    为每个概念取 fillColor/strokeColor
    │                          │                          │
    │                          │                          ▼
    │                          │                    阶段7（数据图表）
    │                          │                    [使用] 读取注册表
    │                          │                    matplotlib 按 concept 取色
    │                          │                          │
    │                          │                          ▼
    │                          │                    阶段8（红队审查）
    │                          │                    [验证] 扫描所有图表文件
    │                          │                    检查颜色一致性 → 风险清单
    │                          │                          │
    │                          │                          ▼
    │                          │                    阶段9（定稿）
    │                          │                    [锁定] status → locked
    │                          │                    归档为 report artifact
```

#### 2.2.1 创建时机与填充方式

| 步骤 | 时机 | 动作 | 执行者 |
|------|------|------|--------|
| 1. 脚手架生成 | 阶段 1.2 创建 `research/figures/` 时 | 生成空 `color-registry.yaml` 骨架（含 `meta` + `palette` 默认值） | 阶段 1 agent |
| 2. 架构卡提取 | 阶段 5 架构卡全部完成后 | 扫描 `research/notes/architecture-cards/`，从每张卡的"组件与关系"字段提取概念列表，自动填充到 `concepts[]` | 阶段 5→6 过渡脚本 |
| 3. 人工确认/补充 | 阶段 6 出图前 | 用户审查自动提取结果：补充遗漏概念、确认层级颜色映射规则、调整个别颜色偏好 | 用户（通过 agent 对话交互） |
| 4. 使用中增量更新 | 阶段 6/7 出图过程中 | 如发现新概念（注册表未覆盖），即时追加到 `concepts[]` 并同步到已出图表（最大努力，不强制回溯） | 阶段 6/7 agent |
| 5. 验证后锁定 | 阶段 8 验证通过后 | `status: locked`，`verified_by` 填写审查者标识 | 阶段 8 agent |

#### 2.2.2 从架构卡到注册表的自动提取逻辑

```
输入：research/notes/architecture-cards/ARCH-01.md ... ARCH-NN.md
处理流程：
  1. 解析每张架构卡的 YAML frontmatter 或 Markdown 结构化字段
     目标字段："所属层次"、"组件与关系"（通常是以列表形式列出的组件名）
  2. 对每个提取到的组件名称：
     a. 查询 color-registry.yaml 中是否已有同名 concept（按 canonical_name 或 aliases 匹配）
     b. 若有 → 跳过（已登记）
     c. 若无 → 创建新 concept 条目
        - concept_id 按命名规范自动生成
        - concept_name = 提取的组件名
        - fill_color/stroke_color 按以下优先级确定：
          (1) 如果该组件有明确的"所属层次"字段 → 按 color-mapping-rules.yaml 的层级规则分配灰度
          (2) 如果无层次信息 → 默认 gray-100 fill + gray-500 stroke
        - canonical_name = 提取的组件名（人工确认后规范化为最终名称）
        - source_cards = [当前架构卡的 card_id]
  3. 输出：更新后的 color-registry.yaml + 提取报告（哪些概念自动创建/哪些需要人工判断）
```

#### 2.2.3 注册表未覆盖概念的处理规则

当阶段 6/7 出图时遇到注册表中不存在的概念：

| 情况 | 处理方式 |
|------|---------|
| 该概念是**新发现的独立概念**（之前架构卡未覆盖） | **自动追加**到注册表，按默认规则分配灰色系颜色，并在 `notes` 字段标注 "auto-added during phase6/7, needs human review" |
| 该概念是已登记概念的**别名字面变异**（如注册表有"数据中台"、图中用"数据平台"） | **抛出警告**：不自动创建新条目，而是报告"检测到未登记名称 '数据平台'，可能为 '数据中台' 的别名。请确认：(A) 合并到现有概念 (B) 创建为独立新概念" |
| 该概念是**临时/一次性的**（如图例中的辅助标注，并非核心概念） | 允许使用 ad-hoc 颜色，不在注册表中登记。`notes` 中标注 "ad-hoc, not registered" |

### 2.3 注册表验证

#### 2.3.1 验证逻辑总览

阶段 8 红队审查时，执行自动化颜色一致性验证。验证脚本读取 `color-registry.yaml` 并扫描所有图表文件。

```text
验证入口：阶段 8 agent 在"一致性审查"维度下调用
输入：
  - research/figures/color-registry.yaml（权威色值来源）
  - research/figures/*.drawio
  - research/figures/*.drawio.svg（如已导出）
  - research/figures/*.drawio.png（如已导出）
  - research/figures/*.svg（fireworks-tech-graph 产物）
  - research/figures/*.png（matplotlib 产物 + fireworks PNG）

核心验证维度：
  V1. 同一 concept_id 在所有文件中的 fillColor 是否一致
  V2. 同一 concept_id 在所有文件中的 strokeColor 是否一致
  V3. 同一 concept_id 在所有文件中的 textColor 是否一致（如有）
  V4. 注册表中声明的 applies_to 与实际图表类型是否匹配（如架构图专用色未被数据图表误用）
  V5. 是否存在注册表未覆盖的概念（检测到未登记名称 → 警告）
```

#### 2.3.2 按文件类型的解析与验证策略

##### A. drawio 文件（`.drawio`）

**数据源**：`mxGraphModel` XML 中的 `mxCell` 元素。

解析目标属性（位于 `<mxCell style="...">` 的 style 字符串中）：

| Style Key | 对应注册表字段 | 对比方式 |
|-----------|--------------|---------|
| `fillColor` | `tool_mappings.drawio.fillColor` | **精确匹配** — hex 值必须完全相同 |
| `strokeColor` | `tool_mappings.drawio.strokeColor` | **精确匹配** |
| `fontColor` | `tool_mappings.drawio.fontColor` | **精确匹配** |
| `shape` | — | 记录，不验证颜色 |

节点名称定位：`<mxCell value="节点名称" ...>` 的 `value` 属性。用此值与注册表中 `canonical_name` 或 `display_name_short` 做精确匹配。

**注意**：同一 drawio 文件中可能有多个 `mxCell` 引用同一个概念（如架构图中感知层出现多次）。验证时按 `value` 聚合——同一 `value` 的所有 `mxCell` 应该有一致的 `fillColor`。

伪代码：
```
for each .drawio file:
    parse XML → collect all (value, fillColor, strokeColor, fontColor) tuples
    for each unique value:
        find matching concept in registry by canonical_name or display_name_short
        if found:
            assert fillColor == concept.tool_mappings.drawio.fillColor
            assert strokeColor == concept.tool_mappings.drawio.strokeColor
            if fontColor present: assert fontColor == concept.tool_mappings.drawio.fontColor
        else:
            report WARNING: unregistered concept name "{value}"
```

##### B. fireworks-tech-graph 文件（`.svg`）

**数据源**：SVG XML 中的 `<rect>` / `<text>` / 自定义元素。

由于 fireworks-tech-graph 生成的 SVG 可能没有直接的 `data-concept-id` 属性（取决于模板实现），验证策略分两级：

| 级别 | 方法 | 精度 |
|------|------|------|
| **L1: 结构化匹配** | 如果 SVG 中节点元素包含 `data-concept-id` 或 `data-concept-name` 属性 → 直接精确匹配 | 高 |
| **L2: 文本+颜色采样** | 如果无结构化标记 → 提取 `<text>` 内容作为节点名 → 取父级/同级 `<rect>` 的 `fill` 属性 → 精确匹配 | 中 |

L2 的局限性：同一 SVG 中可能存在多个同名文本（如图例和图主体），需通过 `y` 坐标排除图例区域。图例的识别规则：`y` 坐标接近 viewBox 底部的紧凑文本区域（y > viewBox_height * 0.85）。

##### C. matplotlib PNG（`.png`）

**数据源**：PNG 像素，无结构化元数据可解析。

**策略**：颜色采样 + 近似匹配（允许少量色差，因为 matplotlib 渲染引擎的 dpi、抗锯齿等因素可能导致 hex 值有微小偏差）。

```
for each .png file produced by matplotlib (identified by naming convention or registry):
    1. 确定该 PNG 对应的章节和图号（通过 figures-index.csv）
    2. 确定该 PNG 中预期出现哪些 concept（通过该章的图表规划）
    3. 对每个预期 concept：
       a. 如果是柱状图/饼图：采样图例区域的色块 → 取平均色 → 与注册表对比
       b. 如果是折线图：识别线条颜色 → 与注册表 chart-series 色对比
    4. 色差阈值：ΔE ≤ 10（CIE76 公式）视为一致
    5. 报告：匹配结果（PASS/近似匹配(ΔE=X)/FAIL）
```

**注意**：PNG 颜色验证是**尽力型**（best-effort），不要求 100% 精确。matplotlib 的 `dpi` 设置和抗锯齿可能导致 1-2 个 hex 通道偏差，这是可接受的。

##### D. drawio 导出的 PNG（`.drawio.png`）

与 `.drawio` 源文件交叉验证——两个文件应指向同一个概念且颜色一致。验证方法：读取 source `.drawio` 的颜色值，与 `.drawio.png` 中对应区域像素采样对比。由于 drawio CLI 导出是逐像素精确渲染，色差应极低（ΔE < 3）。

#### 2.3.3 验证结果与红队审查联动

```text
验证脚本产出：research/figures/color-consistency-report.json

红队 agent（阶段8）消费此报告：
  - 从报告中提取 FAIL 项 → 映射为红队风险清单条目
  - 从报告中提取 WARNING 项 → 映射为中风险或低风险条目
  - 一致性维度下的检查项 "同一术语在全文中是否统一" 自动包含颜色一致性

报告字段：
{
  "summary": {
    "total_concepts": 18,
    "total_files_scanned": 12,
    "pass_count": 15,
    "warning_count": 2,
    "fail_count": 1
  },
  "violations": [
    {
      "violation_id": "COLOR-001",
      "concept_id": "COMP-data-platform",
      "concept_name": "数据中台",
      "file": "3-2-数据处理流程.drawio",
      "expected_fill": "#f3f4f6",
      "actual_fill": "#e5e7eb",
      "delta_E": 8.2,
      "severity": "warning",
      "suggested_action": "drawio 文件中数据中台节点 fillColor 为 #e5e7eb，与注册表 #f3f4f6 不一致。建议修正 drawio 文件或更新注册表。"
    }
  ],
  "unregistered_concepts": [
    {"name": "消息中间件", "file": "4-1-系统架构图.drawio", "suggested_action": "注册为新概念或合并到已有概念"}
  ]
}

红队风险清单中的映射：
  - severity="fail"    → 风险等级="高"，问题类型="颜色不一致"
  - severity="warning" → 风险等级="中"，问题类型="颜色不一致"
  - unregistered       → 风险等级="低"，问题类型="未注册概念"
```

### 2.4 灰色系层级映射规则

#### 2.4.1 默认规则：六层架构（底浅 → 顶深）

遵循格式规范 V3.1 "黑白灰为主"原则，架构层级按底部浅灰 → 顶部深灰分配：

```yaml
# ============================================================
# 颜色映射规则配置 — 项目级（跨报告复用）
# 位置：references/color-mapping-rules.yaml
# ============================================================

# --- 规则元数据 ---
meta:
  schema_version: "1.0"
  description: >
    为不同架构模式定义"层次 → 灰度"的自动映射规则。
    每条规则指定从 layer_index 到 palette color_id 的映射函数。

# --- 规则定义 ---
rules:
  # 规则 1：六层架构（底浅顶深）—— 默认规则
  - rule_id: "six-layer-bottom-light"
    display_name: "六层架构·底浅顶深"
    description: >
      底层（感知/采集）用最浅灰，顶层（应用/展示）用最深灰。
      理由：底层通常是数据源/基础设施，用浅色表示"基础/底材"；
      顶层面向用户/决策，用深色表示"核心/聚焦"。
    direction: "bottom-to-top"       # 从底到顶
    color_ramp: "light-to-dark"      # 浅→深
    layer_count: 6
    # 映射表：layer_index → palette color_id
    mapping:
      1: layer-gray-L1   # #f9fafb — 最底层：最浅
      2: layer-gray-L2   # #e5e7eb
      3: layer-gray-L3   # #d1d5db
      4: layer-gray-L4   # #9ca3af
      5: layer-gray-L5   # #6b7280
      6: layer-gray-L6   # #374151 — 最顶层：最深
    # 适用架构模式（自动匹配时的信号词）
    trigger_keywords:
      - "六层架构"
      - "感知层.*网络层.*平台层.*数据层.*算法层.*应用层"
      - "技术架构六层"
      - "分层架构"

  # 规则 2：六层架构（顶浅底深）—— 备选
  - rule_id: "six-layer-top-light"
    display_name: "六层架构·顶浅底深"
    description: >
      顶层用浅灰（轻量/灵活），底层用深灰（厚重/基础设施）。
      适合强调"上层灵活、下层稳固"的报告叙事。
    direction: "bottom-to-top"
    color_ramp: "dark-to-light"
    layer_count: 6
    mapping:
      1: layer-gray-L6
      2: layer-gray-L5
      3: layer-gray-L4
      4: layer-gray-L3
      5: layer-gray-L2
      6: layer-gray-L1
    trigger_keywords:
      - "灵活上层"
      - "稳固底座"
      - "轻量化架构"

  # 规则 3：四层架构（OSI 式 / TOGAF 式）
  - rule_id: "four-layer-business-top"
    display_name: "四层架构·业务层在顶"
    description: >
      基础设施→平台→数据→业务，自底向上加深。
      对应 TOGAF 四层：技术架构→数据架构→应用架构→业务架构。
    direction: "bottom-to-top"
    color_ramp: "light-to-dark"
    layer_count: 4
    mapping:
      1: layer-gray-L2   # 基础设施层
      2: layer-gray-L3   # 平台层
      3: layer-gray-L5   # 数据/应用层
      4: layer-gray-L6   # 业务层
    trigger_keywords:
      - "四层架构"
      - "TOGAF"
      - "业务架构.*应用架构.*数据架构.*技术架构"

  # 规则 4：三明治架构（中台/平台在中间突出）
  - rule_id: "sandwich-platform-accent"
    display_name: "三明治架构·平台层强调"
    description: >
      前台和后台用浅灰，中间平台层用强调色（蓝底）。
      适合"中台战略""平台化"叙事的报告。
    direction: "bottom-to-top"
    color_ramp: "custom"
    layer_count: 3
    mapping:
      1: layer-gray-L1   # 后台/基础设施：浅灰
      2: accent-blue-light # 中台/平台层：蓝色浅底突出
      3: layer-gray-L6   # 前台/应用：深灰
    trigger_keywords:
      - "中台"
      - "平台化"
      - "三明治架构"
      - "前后台分离"

  # 规则 5：通用 N 层自动映射
  - rule_id: "auto-n-layer-light-bottom"
    display_name: "通用 N 层·底浅顶深（自动）"
    description: >
      当层数不是 3/4/6 时，自动计算灰度阶梯。
      每层的灰度 = 起点灰 + (层序 - 1) × 阶梯增量。
    direction: "bottom-to-top"
    color_ramp: "interpolated"
    layer_count: null                     # null = 任意层数
    # 插值参数
    interpolation:
      start_gray_hex: "#f9fafb"           # L1 灰
      end_gray_hex: "#374151"             # LN 灰
      mode: "linear-rgb"                  # 线性 RGB 插值
      # 可选：指定某几层用特殊颜色
      overrides: {}                       # {layer_index: color_id}
    trigger_keywords:
      - "N层架构"
      - "多层架构"
      - "分层体系"

# --- 线型规则 ---
# 与颜色规则分开定义——同一条颜色规则可以搭配不同的线型规则
line_rules:
  # 数据流 → 虚线 / 控制流 → 实线
  - rule_id: "data-dashed-control-solid"
    display_name: "数据流虚线·控制流实线"
    flow_type_to_style:
      data: dashed-flow
      control: solid-main
      feedback: dashed-feedback
      dependency: dotted-dependency
```

#### 2.4.2 自动匹配逻辑

阶段 5→6 创建注册表时，自动选择映射规则：

```
1. 读取阶段 1.3 的分析框架参数 → 确定架构层数和名称
2. 遍历 color-mapping-rules.yaml 中的 rules[]
3. 匹配优先级：
   a. 精确匹配 layer_count（如规则指定 6 层且报告确实是 6 层）→ 最高分
   b. trigger_keywords 命中报告题名/大纲章标题 → 中分
   c. 无精确匹配 → 使用 auto-n-layer-light-bottom 插值规则
4. 展示推荐规则给用户，用户可以：(A) 接受 (B) 选择其他规则 (C) 自定义映射
```

#### 2.4.3 用户自定义规则

用户可在 `references/color-mapping-rules.yaml` 中新增规则，格式与内置规则相同。新增规则的 `rule_id` 以 `user-` 为前缀以避免与内置规则冲突。

---

## 3. 模块 B：架构图节点命名规范

### 3.1 命名一致性规则

#### 3.1.1 核心原则

**同一概念在所有图中必须同名字、同字形。**

- "同名字"：`canonical_name` 完全相同——不允许"感知层"在一张图中叫"感知层"、在另一张图中叫"感知子系统"。
- "同字形"：中英文、大小写、标点符号完全一致。"Data Middle Platform"和"data middle platform"算不一致。

#### 3.1.2 命名粒度：什么算"同一个概念"？

| 情况 | 判定 | 处理 |
|------|------|------|
| "感知层" vs "感知子系统" | **同一概念**——"感知子系统"是"感知层"的下位表述，但在报告中应统一为 canonical_name "感知层" | 登记 aliases，出图时只用 canonical_name |
| "数据中台" vs "数据平台" vs "数据中心" | **同一概念**——三个名称指向同一个架构组件 | 三选一作为 canonical_name，其余两个登记到 aliases 和 forbidden_names |
| "感知层" vs "数据感知层" | **可能不同**——加了修饰词可能表示不同范围 | 人工判断：如确实指向同一层 → 合并；如"数据感知层"是更窄的概念 → 独立登记 |
| "AI 推理引擎" vs "推理模块" | **人工判断**——"引擎"和"模块"暗示不同的抽象层级 | 默认独立登记，除非架构卡明确说它们是同一组件 |

**粒度判定规则**：
- 如果两个概念在架构卡中**同属一个 card_id** 且**出现在同一"组件"条目下** → 合并
- 如果两个概念**分属不同架构卡**且**架构卡的"所属层次"不同** → 独立
- 如果架构卡信息不足以判定 → 标记为 `aliases_conflict`，在阶段 6 出图前由用户确认

#### 3.1.3 缩写规则

| 规则 | 说明 |
|------|------|
| 何时允许缩写 | 仅在节点框空间不足以容纳完整名称时（估算：中文字符 > 8 个或总字符 > 20 个） |
| 缩写在注册表中如何登记 | `display_name_short` 字段登记缩写形式，`display_name_full` 登记完整形式。出图默认用 `display_name_short`，图注中用 `display_name_full` 补充说明 |
| 首次出现的处理 | 该概念第一次在报告中出现（通常是最早的架构图或正文），必须同时显示完整名称和缩写："数据中台 (DMP)" |
| 缩写一致性 | 同一概念的缩写必须全局一致——不允许图 2-1 中缩写作"DMP"、图 3-2 中缩写作"DM Platform" |

#### 3.1.4 双语规范

| 规则 | 说明 | 示例 |
|------|------|------|
| 主语言 | 中文为主（报告默认中文撰写） | "感知层"为主 |
| 英文标注 | 紧跟中文名，括号内标注英文 | "感知层 (Perception Layer)" |
| 首次出现 | 显示完整双语名称 | "感知层 (Perception Layer)" |
| 后续出现 | 可仅用中文短名 | "感知层" |
| 纯架构图节点 | 如空间紧张，可仅用中文 | "感知层" |
| 纯英文受众报告 | 主语言切换为英文 | "Perception Layer" 为主，中文为辅 |

### 3.2 注册表扩展：命名注册

在 `color-registry.yaml` 的 `concepts[*]` 中已内置命名一致性字段（见 2.1.2 Schema 中的 `canonical_name`、`display_name_short`、`display_name_full`、`aliases`、`forbidden_names`）。这里进一步说明这些字段的使用规范。

#### 3.2.1 命名字段详解

```yaml
# 每个 concept 的命名相关字段
canonical_name: "数据中台"
  # 规范名——所有图表和正文中必须使用的统一名称
  # 规则：
  #   - 中文为主
  #   - 不含英文（英文单独在 display_name_full 中）
  #   - 不含括号标注
  #   - 不含层级修饰（"第X层"等位置信息是 architecture_position 的事）

display_name_short: "数据中台"
  # 图内短名——空间紧张时的显示名称
  # 默认与 canonical_name 相同
  # 仅在确实需要缩写时才不同（如 "ADAS" vs "高级驾驶辅助系统"）

display_name_full: "数据中台 (Data Middle Platform)"
  # 图内全名——首次出现或有足够空间时的显示名称
  # 格式：{canonical_name} ({concept_name_en})

aliases:
  - "数据平台"
  - "数据中心"
  - "Data Middle Platform"
  # 同一概念的其他称呼
  # 用途：
  #   - 阶段 5→6 自动提取时，用 aliases 匹配已有概念
  #   - 阶段 8 扫描时，aliases 不算违规——仅 forbidden_names 算违规
  # 注意：aliases 不等于"可以用"——出图时仍应使用 canonical_name

forbidden_names:
  - "数据平台"     # ← 这个看似矛盾：既在 aliases 里又在 forbidden_names 里
  - "数据中心"     #    实际上 aliases 是"识别用"，forbidden_names 是"出图禁用"
  # 禁止在图表中出现的名称列表
  # 如果某个别名被识别为"和 canonical_name 差异太大，用了会误导"，
  # 则同时列在 aliases（让自动匹配能识别到）和 forbidden_names（出图时禁用）
```

#### 3.2.2 阶段 8 命名一致性自动扫描

与颜色验证（2.3）同步执行，共用同一套文件扫描逻辑。命名扫描关注的是**节点名称字符串**，而非颜色。

```
扫描维度：
  N1. forbidden_names 检查
      扫描所有图表文件中出现的节点/文本标签，
      与注册表中所有 forbidden_names 做字符串匹配。
      命中 → FAIL：高优先级，必须修正。

  N2. canonical_name 覆盖率检查
      扫描所有图表文件中出现的概念名称，
      与注册表中 canonical_name 和 display_name_short 做匹配。
      名称与 canonical_name/display_name_short 不一致且不在 aliases 中：
        → 可能为未注册新概念或拼写错误 → WARNING。

  N3. 名称拼写一致性检查
      同一 canonical_name 在不同图表中的字符串是否完全一致。
      例：图 2-1 中为"感知层"，图 3-2 中为"感知 层"（多了一个空格）
        → FAIL：空格/标点不一致。

  N4. 双语完整性检查
      检查首次出现的图表（按图号顺序）是否使用了 display_name_full（含英文标注）。
      如果首次出现只用了 short name → WARNING：建议补充英文标注。

输出格式（与颜色报告合并为 color-consistency-report.json）：
{
  "naming_violations": [
    {
      "violation_id": "NAME-001",
      "concept_id": "COMP-data-platform",
      "type": "forbidden_name_detected",
      "forbidden_name": "数据平台",
      "file": "4-2-数据流图.drawio",
      "severity": "fail",
      "suggested_action": "将节点名称'数据平台'替换为 canonical_name '数据中台'"
    },
    {
      "violation_id": "NAME-002",
      "concept_id": "ARCH-layer-01",
      "type": "spelling_inconsistency",
      "expected": "感知层",
      "actual": "感知 层",
      "file": "3-2-架构拆解.drawio",
      "severity": "fail",
      "suggested_action": "移除'感知'和'层'之间的多余空格"
    }
  ]
}
```

### 3.3 与阶段 5 架构卡的联动

#### 3.3.1 架构卡作为注册表素材来源

阶段 5 的架构卡模板（SKILL.md §5.3）中，"组件与关系"字段是填充注册表的核心素材：

```markdown
## 架构名称：六层技术架构
1. **所属层次**：N/A（整体架构）
2. **组件与关系**：
   - 感知层：传感器网络、数据采集网关 → 向网络层提供原始观测数据
   - 网络层：低轨卫星通信、5G专网、光纤骨干 → 向平台层提供数据传输
   - 平台层：容器化PaaS、API网关、消息中间件 → 向数据层提供计算资源
   - 数据层：数据湖、知识图谱、实时流处理 → 向算法层提供结构化数据
   - 算法层：大语言模型、计算机视觉、强化学习 → 向应用层提供AI能力
   - 应用层：指挥控制、态势感知、辅助决策 → 面向最终用户
3. **数据流**：证据包 [C-023, C-024]
4. **验证方式**：官方白皮书 + 公开技术文档
5. **对应的图表**：图 2-1（阶段 6 出图时回填）
```

**提取规则**：
- 从"组件与关系"列表中提取以 `- ` 开头的行
- 解析每个组件名称（如"感知层"）：取第一个冒号或中文破折号或中文顿号之前的部分，或取"→"之前的第一个名词短语
- 每个组件创建一个 concept 条目
- "所属层次"字段中的层级信息用于匹配 `layer_index`

#### 3.3.2 提取流程的边界情况

| 情况 | 处理 |
|------|------|
| 架构卡中没有"组件与关系"字段 | 跳过该卡——不是所有架构卡都用于出图（有些是概念分析） |
| 组件名包含修饰语（如"容器化 PaaS 平台"） | 提取为 `canonical_name = "PaaS 平台"`，修饰语放入 `description`；但同时登记 `aliases = ["容器化 PaaS 平台"]` 以便后续自动匹配 |
| 一张架构卡覆盖多个层次 | 每个组件独立分配 `layer_index`（通过"所属层次"判断） |
| 多张架构卡描述同一组件（如 ARCH-02 和 ARCH-03 都提到"数据中台"） | 去重合并——以先出现的架构卡为准，后来的补充 aliases 和 evidence_packets |
| 架构卡的组件名称与 report 主题高度相关但有领域特殊术语 | 保留原始名称，在 `notes` 中标注"源自架构卡 ARCH-NN，未经领域规范化" |

#### 3.3.3 完整联动流程图

```text
阶段4 大纲
  │
  ├── 核心架构图清单（图号+图名+核心要素）
  │   例：图 2-1：六层技术架构全景（感知层/网络层/平台层/数据层/算法层/应用层）
  │
  ▼
阶段5 卡片
  │
  ├── 架构卡 ARCH-01（"六层技术架构"）
  │   "组件与关系"包含概念列表
  │
  ├── 架构卡 ARCH-02（"数据流架构"）
  │   "组件与关系"包含概念列表（与 ARCH-01 可能有重叠）
  │
  ├── [自动提取] 扫描所有架构卡 → 去重合并 → 生成 color-registry.yaml 初稿
  │   从架构卡提取的字段：canonical_name, architecture_position, evidence_packets, source_cards
  │   自动分配的字段（按映射规则）：fill_color, stroke_color, color_role
  │   待人工确认的字段：forbidden_names, display_name_short, display_name_full
  │
  ▼
阶段5→6 过渡
  │
  ├── [人工确认] 用户审查 color-registry.yaml：
  │   - 确认 canonical_name 选择（从多个别名中选其一）
  │   - 确认层级颜色映射规则（六层底浅顶深 / 自定义）
  │   - 补充遗漏概念
  │   - 确认 forbidden_names 列表
  │
  ▼
阶段6 出图
  │
  ├── drawio 生成架构图：读取 color-registry.yaml 获取颜色
  ├── fireworks-tech-graph 生成技术架构图：读取 color-registry.yaml 获取颜色
  ├── 每出完一张图 → 登记到 figures-index.csv
  │
  ▼
阶段7 出数据图
  │
  ├── matplotlib 生成数据图：读取 color-registry.yaml 获取 chart-series 颜色
  ├── 图中如有架构概念 → 引用对应 concept 的颜色
  │
  ▼
阶段8 红队审查
  │
  ├── [自动扫描] 命名一致性 + 颜色一致性
  ├── 产出 color-consistency-report.json
  ├── 红队 agent 将此报告纳入一致性审查维度
  ├── 违规项 → 风险清单（RXXX），逐项处理
  │
  ▼
阶段9 定稿
  │
  ├── color-registry.yaml status → locked
  ├── 图表索引 figures-index.csv → 最终版
  └── 归档为报告交付物的一部分
```

---

## 4. 新增数据资产：figures-index.csv

### 4.1 DDL 设计

```sql
-- 概念上这是一个 CSV 文件（与现有 card-index.csv 风格一致），
-- 而非 SQL 表。以下为各列定义。

-- 文件位置：research/figures/figures-index.csv
-- 字符编码：UTF-8（无 BOM）
-- 分隔符：逗号

-- 列定义：
-- figure_id       TEXT PRIMARY KEY     -- 图号，如 "2-1"（章号-图序）
-- figure_title    TEXT NOT NULL        -- 图名，如 "六层技术架构全景"
-- figure_type     TEXT NOT NULL        -- architecture-diagram | flowchart | data-flow-diagram | system-overview | comparison-chart | trend-chart | pie-chart | radar-chart | heatmap | timeline | other
-- tool            TEXT NOT NULL        -- drawio | fireworks-tech-graph | mermaid | matplotlib | other
-- source_files    TEXT NOT NULL        -- 源文件路径，相对 research/figures/；多个用分号分隔
-- chapter_ref     TEXT NOT NULL        -- 对应章节号，如 "第2章"
-- concepts_used   TEXT                 -- 该图使用的 concept_id 列表，分号分隔；用于反向查找"哪些图使用了概念 X"
-- status          TEXT NOT NULL        -- draft | final
-- color_registry_checked TEXT          -- 是否已通过颜色一致性验证：unchecked | passed | warnings | failed
-- created_at      TEXT NOT NULL        -- ISO 8601 日期
-- notes           TEXT                 -- 备注
```

### 4.2 模板示例

```csv
figure_id,figure_title,figure_type,tool,source_files,chapter_ref,concepts_used,status,color_registry_checked,created_at,notes
2-1,六层技术架构全景,architecture-diagram,drawio,"2-1-六层技术架构全景.drawio;2-1-六层技术架构全景.drawio.svg;2-1-六层技术架构全景.drawio.png",第2章,"ARCH-layer-01;ARCH-layer-02;ARCH-layer-03;ARCH-layer-04;ARCH-layer-05;ARCH-layer-06",final,unchecked,2026-07-21,
3-1,数据流架构图,data-flow-diagram,fireworks-tech-graph,"3-1-数据流架构图.svg;3-1-数据流架构图.png",第3章,"ARCH-layer-01;ARCH-layer-02;COMP-data-platform;FLOW-data-collection",final,unchecked,2026-07-21,
```

### 4.3 索引用途

| 用途 | 查询 |
|------|------|
| "概念 X 在哪些图中出现了？" | `grep {concept_id} figures-index.csv` 查 `concepts_used` 列 |
| "哪些图还没做颜色验证？" | `grep "unchecked" figures-index.csv` 查 `color_registry_checked` 列 |
| "阶段 6 的图产出够不够？" | 对照阶段 4.3 的图表清单与 `figures-index.csv` 的 `figure_id` 列表 |
| "阶段 8 验证后更新状态" | 阶段 8 agent 逐条更新 `color_registry_checked` 字段 |

---

## 5. 存储评估

| 项目 | 日增量 | 年总量（按 20 份报告估算） | 说明 |
|------|--------|--------------------------|------|
| `color-registry.yaml` | 约 3-8 KB/报告 | 约 160 KB | 每份报告约 15-30 个 concept 条目 |
| `figures-index.csv` | 约 0.5-2 KB/报告 | 约 40 KB | 每份报告约 10-30 张图 |
| `color-mapping-rules.yaml` | 0（项目级静态文件） | 约 10 KB | 仅 5-10 条规则，极少修改 |
| `naming-rules.yaml` | 0（项目级静态文件） | 约 5 KB | 命名规范配置，极少修改 |
| `color-consistency-report.json` | 约 5-15 KB/报告 | 约 300 KB | 阶段 8 验证报告，可随项目归档 |

**存储膨胀量**：可忽略。全部新增数据资产为文本格式，单份报告增量 < 30 KB，年总量 < 1 MB。

**归档策略**：随报告项目目录一并归档（`research/` 目录），不需要独立的归档策略。`color-registry.yaml` 在阶段 9 锁定后可作为模板复用于同类主题的未来报告。

---

## 6. 数据质量规则

| 规则 ID | 规则描述 | 检查方法 | 告警阈值 | 处理方式 |
|---------|---------|---------|---------|---------|
| DQ-COLOR-01 | 每个 `concept.fill_color` 必须在 `palette` 中定义 | 启动时加载注册表即校验 | 1 条违规即报错 | 阻止注册表保存，提示修正 |
| DQ-COLOR-02 | 每个 `concept.tool_mappings` 必须覆盖该 concept 的 `applies_to` 所对应的所有工具 | 阶段 6 出图前检查 | 任一工具缺失即 WARNING | 提示补充映射，不阻塞出图 |
| DQ-COLOR-03 | `canonical_name` 不得与 `forbidden_names` 相同 | 注册表保存时检查 | 1 条违规即报错 | 阻止保存 |
| DQ-COLOR-04 | 同一 `canonical_name` 不得注册两次（去重） | 自动提取时检查 | 1 条重复即 WARNING | 自动合并 aliases 和 evidence_packets，提示用户确认 |
| DQ-COLOR-05 | 阶段 8 验证：颜色一致性 ≥ 95% | 扫描所有图表文件 | FAIL 项占比 > 5% → 高风险 | 逐项修正或更新注册表 |
| DQ-COLOR-06 | 阶段 8 验证：forbidden_names 零出现 | 扫描所有图表文件 | 任一命中 → 高风险 | 必须修正为 canonical_name |
| DQ-COLOR-07 | 注册表状态转换合法性 | 状态机检查 | draft→in_use→verified→locked 不可跳步 | 记录违规并阻止非法状态转换 |
| DQ-NAME-01 | `canonical_name` 与 `display_name_full` 的一致性 | 注册表保存时检查 | `display_name_full` 必须包含 `canonical_name` 字面 | 提示修正 |
| DQ-NAME-02 | `aliases` 与 `forbidden_names` 无意外重叠 | 注册表保存时检查 | 两列表的交集 → INFO（可能是故意的，见 3.2.1 说明） | 不阻止，仅记录 |

### 6.1 时效性检查

| 检查项 | 方法 | 预期 |
|--------|------|------|
| 注册表更新时间 | `meta.updated_at` 与最后出图时间对比 | 注册表更新时间应在所有图表文件的最后修改时间之后（注册表是权威来源，应在出图前更新） |
| 架构卡 vs 注册表同步 | 对比架构卡中组件列表与注册表 concepts[*] 的 `source_cards` 字段 | 注册表应覆盖所有架构卡中出现的组件名称 |

### 6.2 一致性检查

| 检查项 | 方法 | 预期 |
|--------|------|------|
| 同一概念在多张图中的颜色 | 阶段 8 扫描所有图表文件 | fillColor/strokeColor 一致 |
| 同一概念的命名 | 阶段 8 扫描所有图表文件 | 字符串完全一致（精确到空格和标点） |
| 注册表概念 vs 实际图表概念 | `figures-index.csv` 中的 `concepts_used` vs 阶段 8 扫描发现的节点名称 | 无遗漏、无多余 |

---

## 7. 迁移方案

### 7.1 对现有报告的影响

**已有的报告（在设计定稿前产出的）：不受影响。** 颜色注册表和命名规范是新增的质量保障机制——旧报告没有 color-registry.yaml，阶段 8 验证时将跳过颜色一致性检查（但不跳过命名一致性的人工审查，该项已存在于现有红队清单"六、一致性审查"中）。

### 7.2 新报告的接入流程

1. **阶段 1.2**：`research/figures/` 目录创建时，自动生成空 `color-registry.yaml` 骨架（`meta` + `palette` 默认值已填充，`concepts` 为空列表）。
2. **阶段 5 完成时**：新增过渡步骤——从架构卡自动提取概念并填充 `concepts[]`。
3. **阶段 6 出图前**：用户确认注册表（或接受自动填充结果）。
4. **阶段 6/7 出图时**：agent 读取注册表获取颜色和规范名称。
5. **阶段 8 红队审查**：自动执行颜色+命名扫描，产出一致性报告。
6. **阶段 9 定稿**：注册表锁定。

### 7.3 与现有工具链的兼容性

| 工具 | 兼容性 | 适配工作 |
|------|--------|---------|
| drawio（MCP `create_diagram`） | 完全兼容 | 出图 agent 在构造 Mermaid/XML 前读取注册表，按 `tool_mappings.drawio.*` 设置颜色 |
| fireworks-tech-graph | 完全兼容 | 出图 agent 在构造 JSON 数据时，将节点颜色按 `tool_mappings.fireworks-tech-graph.*` 填入 |
| matplotlib | 完全兼容 | 阶段 7 agent 使用注册表的 `chart-series-*` 色值和 concept 颜色 |
| 现有阶段 8 红队审查 | 增强 | 在现有一致性审查维度下增加"颜色一致性"和"命名一致性"两个子项 |
| 现有 card-index.csv | 无冲突 | `figures-index.csv` 是独立的图表索引，与卡片索引互补 |
| 现有 `references/` 配置文件 | 扩展 | 新增 `color-mapping-rules.yaml` 和 `naming-rules.yaml`，不修改现有文件 |

### 7.4 回滚方案

如果 color-registry 在实践中被证明增加了过多摩擦（如 agent 频繁因颜色不匹配而阻塞），回退路径：

1. **短期降级**：阶段 8 的颜色验证从"阻塞高风险"降级为"仅报告 INFO"，不阻塞进入阶段 9。
2. **中期禁用**：在阶段 1.2 脚手架生成时跳过 color-registry.yaml 创建，各工具仍按现有方式独立选色。
3. **架构卡不受影响**：命名规范中的 `canonical_name` 和 `forbidden_names` 即使颜色注册表被禁用，仍在阶段 8 一致性审查中保留（人工检查），因为它是现有红队清单的增强而非替代。

---

## 8. 实施建议

### 8.1 实施优先级

| 优先级 | 组件 | 理由 |
|--------|------|------|
| **P0（必须）** | `color-registry.yaml` 核心 schema + 阶段5→6 自动提取 + 阶段8 命名一致性扫描 | 直接解决当前核心问题（同概念不同图不同色/不同名） |
| **P1（应该）** | 阶段8 颜色一致性自动扫描（drawio + SVG） | 自动化验证是防止退化的关键 |
| **P2（可以）** | PNG 颜色采样验证 + `figures-index.csv` + 灰色系映射规则的可视化配置 UI | 锦上添花，不阻塞 MVP |
| **P3（未来）** | 跨报告颜色注册表复用（同主题报告从模板复制注册表） | 效率提升，当前 20 份报告/年的规模暂不需要 |

### 8.2 关键设计决策记录

| 决策 | 选择 | 替代方案 | 理由 |
|------|------|---------|------|
| 注册表格式 | YAML | JSON | YAML 更易人工阅读和编辑；项目已有 YAML 使用先例（tool-paths.json 虽是 JSON 但 YAML schema 描述在多个 references 中） |
| 颜色引用方式 | palette 间接引用（`fill_color: layer-gray-L1`） | 直接写 hex | 调色板统一替换时只改一处；避免 hex 散落在各 concept 中导致批量调整困难 |
| concept_id 命名 | 语义前缀（ARCH/COMP/FLOW/SYS/EXT） | 纯数字 ID | 人类可读，方便 agent 在出图时直接识别概念类型 |
| 灰色系映射方向 | 默认底浅顶深 | 底深顶浅 | 格式规范 V3.1 "黑白灰为主"——浅灰底保底色轻，深灰顶突出核心 |
| aliases vs forbidden_names 分离 | 分离：aliases 用于识别，forbidden_names 用于禁用 | 合一：一个列表同时做识别和禁用 | 存在"能识别到但不应该用"的场景（如"数据平台"能匹配"数据中台"但出图时不应写"数据平台"） |

---

## 附录：完整示例数据

### 附录 A：color-registry.yaml 完整示例（六层架构报告）

参见 2.1.2 节 Schema 中的完整 YAML 示例（含 `palette`、`concepts`、`line_styles` 三个完整条目）。

### 附录 B：figures-index.csv 示例

参见 4.2 节模板示例。

### 附录 C：color-consistency-report.json 完整示例

```json
{
  "meta": {
    "report_id": "RPT-2026-001",
    "verified_at": "2026-07-21T15:00:00Z",
    "registry_version": 3,
    "total_concepts": 18,
    "total_files_scanned": 12
  },
  "summary": {
    "color_pass": 15,
    "color_warning": 2,
    "color_fail": 1,
    "naming_pass": 16,
    "naming_warning": 1,
    "naming_fail": 1,
    "unregistered_concepts_count": 1
  },
  "violations": [
    {
      "violation_id": "COLOR-001",
      "type": "color_mismatch",
      "concept_id": "COMP-data-platform",
      "concept_name": "数据中台",
      "file": "3-2-数据处理流程.drawio",
      "field": "fillColor",
      "expected": "#f3f4f6",
      "actual": "#e5e7eb",
      "delta_E": 8.2,
      "severity": "warning",
      "suggested_action": "修正 drawio 文件中数据中台节点的 fillColor 或在注册表中将 fill_color 改为 layer-gray-L2"
    },
    {
      "violation_id": "NAME-001",
      "type": "forbidden_name_detected",
      "concept_id": "COMP-data-platform",
      "forbidden_name": "数据平台",
      "file": "4-2-数据流图.drawio",
      "node_value": "数据平台",
      "severity": "fail",
      "suggested_action": "将节点 '数据平台' 改为 canonical_name '数据中台'"
    },
    {
      "violation_id": "NAME-002",
      "type": "spelling_inconsistency",
      "concept_id": "ARCH-layer-01",
      "expected": "感知层",
      "actual": "感知 层",
      "file": "3-2-架构拆解.drawio",
      "severity": "fail",
      "suggested_action": "移除多余空格"
    }
  ],
  "unregistered_concepts": [
    {
      "name": "消息中间件",
      "file": "4-1-系统架构图.drawio",
      "suggested_action": "在 color-registry.yaml 中注册为新概念或合并到已有概念"
    }
  ]
}
```
