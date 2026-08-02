---
portability: core
---

# 阶段 4：详细大纲

> 本文件是 deep-research-report skill 的阶段 4 详细 spec，从 SKILL.md 拆分而来。
> 母文件：`../SKILL.md`（流程索引）

---

结合阶段 1.3 确定的研究方法与分析框架，在事实核验和资料索引的基础上，全面分析报告主题、特色、目的所需要研究和表达的内容，形成**三级标题 + 篇幅建议 + 证据源 + 图表规划**的详细大纲。

## 4.1 大纲结构

大纲不只是"目录"，更是**每节的论证蓝图**。不再使用条目化的"核心论点+关键证据+篇幅建议"三件套——它诱导写作者在阶段7逐条翻译元数据而非以论证为主线重新组织素材。新格式改用**叙事框架**，明确每节的论证方向和路径。

```markdown
## 第 X 章：章标题
> **本章要论证什么**：（一段话说明本章的核心判断及其在全文论证中的位置——为什么需要这一章？它回答什么问题？结论对后续章节有什么支撑作用？）
> **篇幅建议**：约 Y 页

### X.1 节标题
> **本节要论证什么**：（一段话说明该节的论点及其在整章论证中的位置）
> **论证路径**：（从什么证据出发，经过什么推理，得出什么结论——用"因为A→所以B→因此C"这样的因果链表达）
> **关键素材**：来源ID列表（从卡片索引引用，如 S002/CASE-01/TECH-03）
> **图表规划**：架构图 X-1：描述 / 数据图方向：对比表 1-2 张
> **篇幅建议**：约 Z 页

#### X.1.1 小节标题
> **本节要论证什么**：（一段话）
> **论证路径**：（因果链）
> **关键素材**：来源ID列表
> **篇幅建议**：约 Z 页
```

**新旧格式对比**：

| 维度 | 旧格式（条目化） | 新格式（叙事框架） |
|------|----------------|-------------------|
| 论点表达 | "核心论点：一句话"——倾向于结论式表述 | "本节要论证什么"——强调论证目的和上下文位置 |
| 证据组织 | "关键证据：S002(Ch7异动识别)"——素材列表 | "关键素材"列表 + "论证路径"因果链——素材配合推理 |
| 写作引导 | 诱导写作者逐条翻译元数据，正文中出现"核心论点：..."痕迹 | 引导写作者将素材内化为连贯叙事，而非条目堆砌 |

> **反例警示**：旧格式的"**关键证据**：S002(Ch7异动识别)、S021(HMM意图识别)"在正文中的正确转写应该是："据遨天科技2026年深度研究报告的分析[S002]，非合作目标的异动识别面临……而基于隐马尔可夫模型的意图识别方法[S021]在仿真中实现了高准确率……"——这是一个因果链叙述，不是两个条目的翻译。

> **页数不写进标题**：章/节/小节标题本身只写标题文字，不要写成"第 X 章：章标题（建议页数：Y 页）"——大纲标题会原样沿用到成稿目录和正文标题，混入页数会导致最终报告的章节标题里出现"建议 XX 页"这种大纲阶段的内部标注。页数预算统一放在标题下方的"篇幅建议"行，写作阶段参考后即可丢弃，不进入正文。
	
	> **编号不写进标题**：大纲 Markdown 正文中的 heading 可以带编号前缀供人阅读（如 `### 1.1 节标题`），但标题的**权威来源是 YAML `section_title` 字段**——它存的是纯文字不含编号。Writer 只从 `section_title` 取标题文本写入分章文件。编号（`section_no`）是单独的元数据字段，用于转换器编号和 `finalizer_agent` 的结构驱动合并。**绝对禁止** Writer 将编号（如"1.1""第一章"）写入分章文件的 H3/H4 标题中——这会导致转换器自动编号与手动编号叠加产生"第一章 第一章"或"1.1 1.1"重复。

> **图表规划分两类**：核心架构图（总览图/架构图/流程图）在此阶段就可以给出具体图号和图名——因为阶段 1.3 已确定分析框架，知道有哪些层次和组件需要可视化；**数据图表（对比表/趋势图/雷达图等）只写方向**（如"预计本章需要 1 张市场规模对比表，数据来源 NSR/Euroconsult"），具体图号在阶段 7 随写作产出时才分配——此时写作还没开始，数据细节未定，过早锁定图名会导致图表与文字脱节。

### 4.1.x 大纲落盘——共享契约文件 `research/outline.md`

> 本节对应 v3 优化方案修改 4.1/4.2。在多 Agent 协同体系（见 `multiagent-orchestration.md`）下，本文件由 `outline_architect_agent` 产出，落盘格式沿用本节定义——它是 `chapter_writer_agent`（写作蓝图）、`chapter_auditor_agent`（审计基准）、`card_synthesizer_agent`（按章组织卡片）、`architecture_chart_agent`（出图清单）四方的**唯一共享契约**。单 Agent 极速档下由 orchestrator 自己落盘同一格式。

大纲产出后**必须保存为独立文件 `research/outline.md`**，为阶段 7"写每节前先读对应大纲条目"做准备。格式为：

```markdown
# 大纲：<报告题名>
> 阶段 4 产出 | 阶段 7 写作时必须逐节对照 | struct_template=<research|proposal|policy|tech-eval|brief>

## 第 X 章：章标题
> **篇幅预算**：约 Y 页（约 Y×800 字，按中文正文每页约 800 字估算）
> **本章要论证什么**：（核心判断及其在全文论证中的位置）
> 🏗️ **核心架构图**：图 X-1 ...（阶段 6 完成后回填图号）

### X.1 节标题  <!-- 编号"X.1"是供人阅读的展示前缀，不是标题文本的一部分；Writer 从 YAML section_title 取纯文字"节标题"写入分章文件 -->
> **篇幅预算**：约 Z 页（约 Z×800 字）
> **本节要论证什么**：（论点及其在整章论证中的位置）
> **论证路径**：（因为 A → 所以 B → 因此 C 的因果链）
> **关键素材**：S001, CASE-02, ARCH-03（来源/卡片 ID 列表）
> **图表规划**：架构图 X-1：描述 / 数据图方向：对比表 1-2 张
```

**字数换算规则**：每处"篇幅预算：约 Z 页"必须同时给出字数换算"约 Z×800 字"（中文正文按每页约 800 字估算）。这是阶段 7 量化门禁 QS1（字数 vs 预算）的比对基准——审计 Agent 会用 `contract_check.py` 数出实际字数，与此换算值对比，偏差 > 30% 触发说明或 REVISE。

### 4.1.y 机器可读结构清单——YAML front matter

outline.md 在 Markdown 正文（人类可读大纲）之前须包含 **YAML front matter**，声明机器可读的结构清单。此清单供阶段 9 转换器的 `--outline` 参数和 `finalizer_agent` 的结构驱动合并流程消费，用于**覆盖**转换器基于 Markdown heading 文本模式匹配的启发式结构推断。

```yaml
---
struct_template: research
title: "报告题名"
structure:
  frontmatter:
    - chapter_title: "前言/导论"
      sections:
        - section_no: ""
          section_title: "问题提出与研究背景"
        - section_no: ""
          section_title: "概念界定与研究边界"
  bodymatter:
    - chapter_no: 1
      chapter_title: "第一章完整标题"
      sections:
        - section_no: "1.1"
          section_title: "节标题"
        - section_no: "1.2"
          section_title: "节标题"
      subsections:
        - parent_section_no: "1.1"
          subsection_no: "1.1.1"
          subsection_title: "小节标题"
    - chapter_no: 2
      chapter_title: "第二章完整标题"
      sections:
        - section_no: "2.1"
          section_title: "节标题"
  appendix:
    - appendix_letter: "A"
      appendix_title: "附录A标题"
---
```

**字段语义**：
- `struct_template`：报告类型标识，对应五种报告类型（research/proposal/policy/tech-eval/brief）
- `title`：报告题名
- `frontmatter`：前置件区。H1（MAIN_TITLE）后的 H2/H3 归入此区，**不编号**。前置件区的 `section_no` 填空字符串
- `bodymatter`：正文区。每个元素是一个完整章，`chapter_no` 为章序号。`sections` 按文档序排列，每项为 `{section_no, section_title}` 结构化对象——**编号是元数据（`section_no`），不是标题文本的一部分**。`subsections` 通过 `parent_section_no` 字段关联所属节，每项为 `{parent_section_no, subsection_no, subsection_title}` 结构化对象
- `appendix`：附录区。`appendix_letter` 为字母标识（A/B/C…），顺序即为文档序

> **参考文献节的特殊地位**：合并终稿中的 `## 参考文献` 一节由阶段9 `convert_references.py`/`finalize_pipeline.py` 自动生成并注入（插入于最后一个正文章节之后、附录之前），**不需要、也不应该**在本 YAML 结构清单中声明——它与 `merge_drafts.assemble_merged()` 生成的章容器 `## 第X章：` 同属"管道自身产出的结构性标记"，会被 `md2docx` 的 `FRONT_BACK_WORDS` 白名单自动识别为前置/后置件（渲染为 Word Heading 2 样式，不参与"第X章"编号），无需 `outline.md` 结构清单覆盖介入。
- `figures_manifest`（**可选，阶段4产出**）：机器可读的图表规划清单。若报告超过 3 个核心架构图则**强烈建议**产出此字段，作为阶段6/7/9各方的图表清单权威来源。与 `structure` 同级，包含三个子清单（见下方完整 YAML 示例和字段 schema）
- **"精确一致"约束**：YAML 中的 `section_title` / `subsection_title` 文本须与 Writer 分章文件中实际出现的 H3/H4 heading 文本**精确一致**（含标点、空格）。注意：是 `section_title` 与 heading 文本一致——`section_no` 是编号元数据，用于转换器编号和 `finalizer_agent` 结构驱动合并，Writer 不将其写入标题

**下游消费者**：
- `--outline` 参数传入的转换器：`assemble/headings.py::apply_structure_overlay()` 用于覆盖推断的 heading 分类与编号
- `finalizer_agent`（阶段 9）：读取结构清单生成合并清单，按章插入 H2 章容器
- `chapter_auditor_agent`（阶段 7）：结构一致性审计维度的比对基准
- `architecture_chart_agent`（阶段 6）：从 `figures_manifest.architecture_figures` 获取出图清单（机器可读，无需从正文 grep）
- `data_chart_agent`（阶段 7）：从 `figures_manifest.data_figures` 获取数据图表方向（为阶段7出图提供结构化上下文）
- `figure_gate.py`（阶段6 CHECKPOINT + 阶段9转换前）：从 `figures_manifest` 提取文件清单，逐文件验证存在性与有效性

### 4.1.z figures_manifest 字段定义（可选产出，图表清单权威来源）

`figures_manifest` 是 `outline.md` YAML front matter 中与 `structure` 同级的可选字段。**若存在，则阶段6 (`architecture_chart_agent`)、阶段7 (`data_chart_agent`)、阶段9 (`figure_gate.py` 门禁) 均以此字段为图表清单的权威来源**，不再从 Markdown 正文的非结构化文本中 grep 提取图信息。

当前 `outline.md` YAML front matter 中的完整 `figures_manifest` 示例（插入在 `structure` 块之后，`appendix` 与 `figures_manifest` 同级）：

```yaml
---
struct_template: research
title: "报告题名"
structure:
  # ...（见 §4.1.y 完整示例）
figures_manifest:
  architecture_figures:
    - figure_id: "fig-arch-overview"
      figure_no: "1-1"
      title: "空间态势感知核心闭环"
      type: "overview"
      tool: "drawio"
      priority: "required"
      belongs_to_chapter: 1
      status: "planned"
      output_files:
        - "research/figures/1-1-空间态势感知核心闭环.drawio"
        - "research/figures/1-1-空间态势感知核心闭环.drawio.png"
      checkpoints:
        - "stage6_figure_gate"
    - figure_id: "fig-arch-layer"
      figure_no: "2-1"
      title: "六层技术架构全景"
      type: "architecture"
      tool: "drawio"
      priority: "required"
      belongs_to_chapter: 2
      status: "planned"
      output_files:
        - "research/figures/2-1-六层技术架构全景.drawio"
        - "research/figures/2-1-六层技术架构全景.drawio.png"
      checkpoints:
        - "stage6_figure_gate"
    - figure_id: "fig-arch-pipeline"
      figure_no: "3-1"
      title: "数据处理管道流程图"
      type: "flowchart"
      tool: "mermaid"
      priority: "required"
      belongs_to_chapter: 3
      status: "planned"
      output_files:
        - "research/figures/3-1-数据处理管道流程图.drawio.png"
      checkpoints:
        - "stage6_figure_gate"
  data_figures:
    - figure_id: "fig-data-market-compare"
      figure_no: "2-2"
      title: "主要系统市场份额对比（2025）"
      type: "bar"
      tool: "matplotlib"
      priority: "optional"
      belongs_to_chapter: 2
      status: "planned"
      data_source: "NSR Global Satellite Markets 17th Ed"
      output_files:
        - "research/figures/2-2-市场份额对比.png"
      checkpoints:
        - "stage9_figure_gate"
    - figure_id: "fig-data-trend"
      figure_no: "3-2"
      title: "轨道目标数量增长趋势（2016-2026）"
      type: "line"
      tool: "matplotlib"
      priority: "required"
      belongs_to_chapter: 3
      status: "planned"
      data_source: "ESA Space Environment Report 2025"
      output_files:
        - "research/figures/3-2-轨道目标增长趋势.png"
      checkpoints:
        - "stage9_figure_gate"
  tables:
    - table_id: "tbl-compare-systems"
      table_no: "2-1"
      title: "主流空间态势感知系统能力对比"
      belongs_to_chapter: 2
      status: "planned"
      rows_estimate: 8
    - table_id: "tbl-eval-metrics"
      table_no: "3-1"
      title: "技术评估指标体系"
      belongs_to_chapter: 3
      status: "planned"
      rows_estimate: 10
```

**字段 schema**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `figure_id` | string | 是 | 唯一标识符，格式 `fig-<type>-<slug>` |
| `figure_no` | string | 是 | 图号，格式 `X-Y`（章号-章内序号）。架构图由阶段4分配，数据图表由阶段7分配（阶段4可填 `?`） |
| `title` | string | 是 | 图标题（将作为题注出现） |
| `type` | string | 是 | 架构图：`overview` / `architecture` / `flowchart`；数据图表：`bar` / `line` / `pie` / `radar` / `scatter` / `table` |
| `tool` | string | 是 | 产出工具：`drawio` / `fireworks-tech-graph` / `mermaid` / `matplotlib` |
| `priority` | string | 是 | `required`（不可或缺）/ `optional`（可降级为文字描述） |
| `belongs_to_chapter` | int | 是 | 所属章序号（与 `structure.bodymatter.chapter_no` 对应） |
| `status` | string | 是 | `planned` → `in_progress` → `done` → `dropped`（生命周期状态） |
| `output_files` | list | 是 | 预期产出文件路径列表（至少含1个 PNG） |
| `checkpoints` | list | 否 | 该图表需要经过的门禁检查点 |
| `data_source` | string | 否 | 数据来源（数据图表专用，架构图可省略） |
| `rows_estimate` | int | 否 | 预估行数（表格专用） |

> **figures_manifest 的阶段变迁**：阶段4产出时为 `planned` 状态，数据图表 `figure_no` 可填 `"?"`。阶段6完成后 `architecture_figures` 逐一变为 `done`。阶段7完成后 `data_figures` 逐一变为 `done`。阶段9 `figure_gate.py` 据此逐项验证文件存在性。

> **如果阶段4未产出 figures_manifest**：下游 Agent 从 Markdown 正文的 🏗️ **核心架构图** 和 **图表规划** 标记中提取图信息。此时 `figure_gate.py` 的匹配精度会从"精确匹配"降级为"模糊匹配"，但不会阻断流程。

> **阶段 7 每节写作前，必须读取 `research/outline.md` 中对应该节的条目。此为硬性要求**——不读大纲就开始写作，等于承认"本 skill 的流程设计是摆设"。在多 Agent 档下，这条硬约束由输入注入机制物理保证（`chapter_writer_agent` 的输入契约里只有当前章条目，拿不到凭记忆写作的机会）。

## 4.2 报告结构模板——必选骨架 + 可选模块池

固定模板对所有报告一概适用并不合理：情景前瞻类报告不需要"案例分析"；政策法规类报告需要"条文解读"而非泛化的"背景/现状"；未采用比较研究法的报告不应被迫塞入对比性章节。因此结构不再是单一固定表格，而是**必选骨架决定下限，可选模块按阶段 1.3 确认的研究方法/分析框架/报告目的触发插入**。

### 必选骨架（任何报告都包含）

| 章节 | 建议占比 | 说明 |
|---|---|---|
| 摘要 | 3–5% | 核心结论 + 关键图表 + 主要启示 |
| 前言/导论 | 5–8% | 问题提出、概念界定、研究边界、方法论（写明 1.3 确定的研究方法） |
| 核心分析 | 35–50% | 报告的技术/业务核心，章数 = 阶段 1.3 分析框架的维度数（通常 2–3 章），每章有架构图 |
| 启示/建议 | 8–12% | 可操作建议，落到组织/流程/技术/人才 |
| 附录 | 5%+ | 资料来源、术语表、图表索引、核验台账摘要 |

### 可选模块池（按 1.3 的研究方法/分析框架/报告目的触发，插入到骨架之间）

| 模块 | 触发条件（来自 1.3 确认结果） | 建议占比 | 插入位置 |
|---|---|---|---|
| 背景/现状 | 默认包含——纯情景前瞻/条文解读类报告可压缩并入导论 | 10–15% | 导论之后 |
| 案例分析 | 研究方法含"案例研究法" | 15–20% | 核心分析之前 |
| 政策/条文解读 | 研究方法含"内容分析法"，或主题属于政策法规类 | 10–15% | 背景之后、核心分析之前 |
| 情景推演 | 研究方法含"情景分析法" | 10–15% | 核心分析之后 |
| 风险/挑战 | 分析框架含"风险维度"，或报告目的偏决策支持 | 5–10% | 核心分析之后 |
| 横向对比 | 研究方法含"比较研究法"且对比是报告主要目的 | 融入核心分析，或独立成章 10–15% | 核心分析内，或作为独立章 |

> 占比合计不强制等于 100%——各模块占比为参考区间，按主题实际权重裁量分配，未触发的模块不占篇幅。多个可选模块同时触发时（如案例研究法 + 比较研究法同时命中），优先合并为同一批章节（如"案例横向对比"），不机械叠加两套模块。

> **与旧模板的区别**：旧模板把"案例分析""风险挑战"当成放之四海而皆准的必选项；新设计只有 5 项真正通用，其余模块的取舍直接绑定 1.3 已确认的研究方法和分析框架——选了案例研究法，大纲自然有案例分析章；没选情景分析法，就不硬凑"情景展望"一章。

### 报告类型→模板映射表

阶段 1.1 识别报告类型后，按以下映射自动加载对应的模板结构。`struct_template` 是阶段 4 大纲产出的内部标识，决定了可选模块池中哪些模块默认触发、哪些模块被禁用。

| 报告类型 | struct_template | 默认触发的可选模块 | 禁用的可选模块 | 特殊写作要求 |
|---------|----------------|-------------------|---------------|-------------|
| **立项报告** | `proposal` | 背景/现状 + 风险/挑战 | — | 技术指标必须量化（数值+单位+达标判定标准）；TRL评估必须引用标准定义；创新点必须独立成节并区分"理论创新/技术创新/应用创新" |
| **深度研究报告**（默认） | `research` | 背景/现状 | — | 需要架构图（至少1张）、证据驱动写作、机制导向分析 |
| **政策分析** | `policy` | 政策/条文解读 + 背景/现状（压缩入导论） | 案例分析、情景推演 | 条文解读必须注明条款编号和出处；利益相关方分析必须包含"受益方/受损方/中立方"三分法 |
| **技术评估** | `tech-eval` | 背景/现状 + 风险/挑战 | — | 评测方法论必须声明比较基准和度量指标；基准测试结果必须注明测试环境和条件 |
| **快速简报** | `brief` | 无（全部压缩） | 全部可选模块 | 自动触发极速模式（阶段 2-3 合并、大纲降到二级标题、只出 1 张总览图） |

### 立项报告专用可选模块（5个新增）

当 `struct_template = proposal` 时，以下模块自动追加到可选模块池：

| 模块 | 建议占比 | 插入位置 | 核心内容要求 |
|------|---------|---------|-------------|
| 技术指标与考核方式 | 5–8% | 研究内容之后 | 每项指标含：指标名称、目标值、考核方法、达标判定标准；技术就绪度不同的指标分期考核 |
| 创新点归纳 | 3–5% | 技术途径之后 | 分"理论创新/技术创新/应用创新"三类；每项创新点含：创新内容、与现有技术/方法的具体区别、预期效益 |
| TRL成熟度评估 | 3–5% | 技术途径之后 | 按国军标或NASA TRL定义逐项评估当前成熟度和目标成熟度；附TRL提升路径和关键验证节点 |
| 进度计划与里程碑 | 3–5% | 核心分析之后 | 含甘特图或里程碑表；每阶段有明确的交付物和完成标志；标注关键路径和里程碑之间的依赖关系 |
| 研究基础与条件 | 3–5% | 进度计划之后 | 已有研究成果、实验条件、团队能力、合作单位；说明与本研究的关系和支撑作用 |

> **模块触发优先级**：`struct_template` 默认触发 > 1.3 研究方法触发 > 用户在大纲确认时手动调整。例如：若用户指定 `proposal` 模板但明确表示"不需要TRL评估"（如社科类立项），则 TRL评估模块被手动移除，不因模板绑定而强制保留。

## 4.3 图表规划——分两批，不同精度

阶段 4 列图表清单，但精度不同：

| 图表类型 | 规划精度 | 说明 |
|---------|---------|------|
| **核心架构图**（总览/架构/流程） | 图号 + 图名 + 核心要素 | 基于阶段 1.3 分析框架，此时已明确。例：`图 2-1：六层技术架构全景（感知层/网络层/平台层/数据层/算法层/应用层）` |
| **数据图表**（对比/趋势/份额/雷达） | 方向 + 数据来源 | 写作未开始，数据细节未定。例：`方向：1 张市场区域对比表 + 1 张增长率折线图，数据来源 NSR 2025` |

**数据图表的图号在阶段 7 出图时分配**，不在阶段 4 锁定。阶段 4 只确保"不临时加图"——每章需要什么类型的数据可视化、数据从哪来，心里有数即可。

### ▶ 阶段 4 结构完整性门禁（D1-9，机器校验）

**为什么需要这一步**：本阶段的质量门槛此前**全部是人工勾选的复选框**，阶段 4 全文零脚本调用。实测后果——某次运行中"大纲含三级标题"被勾选通过，而实际 `subsections` **16/16 全为空列表**、YAML 声明 0 个 section，终稿却产出了 113 个 `Heading 2`。节标题全靠 Writer 在阶段 7 即兴补齐，结构与大纲不可核对。

进入 CP3 之前**必须运行**：

```bash
python scripts/outline_structure_gate.py --outline research/outline.md
```

六项检查（S1-S4 为 FATAL 级、S5-S6 为 WARNING 级）：

| 编号 | 判据 | 级别 |
|---|---|---|
| S1 | YAML `structure` 存在且归一化后 `bodymatter` 非空 | FATAL |
| S2 | 每个 `bodymatter[*]` 有非空 `chapter_title` | FATAL |
| S3 | 每个 `bodymatter[*].sections` **条目数 ≥ 2** | FATAL |
| S4 | 每个 `sections[*]` 有非空 `section_no` 与 `section_title` | FATAL |
| S5 | YAML 声明的章标题集合 == Markdown 正文 `##` 标题集合（去编号后） | WARNING |
| S6 | `section_title` 不含编号前缀 | WARNING |

**S3 阈值为 ≥2 而非 ≥1 的理由**：只有 1 个节的章，其节标题必然与章标题语义重复，是"为过门禁而填一行"的典型形态。

**三态开关与首版默认值**：`--structure-gate=off|warn|strict`，**首版默认 `warn`**（只报告不阻断）。理由：存量项目的 outline 当前 100% 无法通过 S3，直接 `strict` 会使既有项目全部卡死在 CP3。

> **切换到 `strict` 的客观触发判据**（不是"待定后再切"这种无法验证的口头承诺）：
> **连续 3 个新项目的 `outline.md` 在未经人工补写的情况下自然通过 S1-S4**（即 `outline_architect_agent` 按已补齐的 section 级产出要求自然产出非空 `sections`），即可将默认值切换为 `strict`。
> 判定方法：每个新项目在阶段 4 首次运行本脚本时记录 JSON 输出中的 `s1_s4_passed`；连续 3 次为 `true` 即满足条件。
> 判据同时写入 `scripts/outline_structure_gate.py` 的 `STRICT_SWITCH_CONSECUTIVE_PROJECTS` 常量注释，两处口径一致。

**呈报给用户时须附机器判据数字**（如"13 章 / 87 节已声明"），使 CP3 的确认对象是**数字**而非印象——否则用户确认疲劳后草率点过，门禁反而提供虚假安全感。

### ▶ 阶段 4 质量门槛

- [ ] 章节结构（必选骨架 + 可选模块）已依据 1.3 的研究方法、分析框架、报告目的选定，非固定套用模板
- [ ] 大纲含三级标题（章→节→小节）+ 篇幅建议 + 证据源标注
- [ ] 核心架构图清单完整（每张有图号/图名/核心要素）
- [ ] 数据图表方向清单完整（每章标注需要什么类型的图 + 数据来源）
- [ ] 每章有明确的"本章结论"占位
- [ ] 已运行 `outline_structure_gate.py`，S1-S4 全部通过（D1-9）
- [ ] 已生成 `research/outline-skeleton-preview.docx`，用户在 Word 中确认了章节框架（D1-8）
- [ ] 用户确认了大纲结构

🔴 CHECKPOINT · 🛑 STOP：用户确认大纲结构（含章标题/**节标题**/篇幅建议/证据源/图表规划）**及骨架 docx 的标题框架**后进入阶段 5。未确认 → 回到阶段 4.1 调整大纲结构或补充证据源。
