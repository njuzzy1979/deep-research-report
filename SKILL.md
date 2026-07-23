---
name: deep-research-report
description: >
  编写深度研究报告的全流程9阶段方法论。证据驱动+架构分析，资料可信度分级A/B/C/D、
  事实核验台账、分阶段质量门槛、架构图先于写作、红队审查。
  触发词：研究报告、深度分析、白皮书、政策研究、行业分析、技术评估、
  可行性研究、写报告、evidence-driven report、deep research。
  即使用户只说"帮我写一份关于XX的报告"，也应先做研究设计再动笔。
---

# 深度研究报告编写方法论

本 skill 将研究报告编写拆解为 **9 个顺序阶段**，前置产物未完成不得进入下一阶段。
核心理念：**先打地基，再盖房子**——资料没抽完不写大纲，事实没核验不写正文，
架构图没画不分章写作。

## 流程总览

```
阶段1: 项目初始化 → 阶段2: 资料抽取与索引 → 阶段3: 事实核验
→ 阶段4: 详细大纲 → 阶段5: 专题研究(卡片+证据包)
→ 阶段6: 核心架构图(先于写作) → 阶段7: 分章写作+数据图表(随写作产出)
→ 阶段8: 红队审查 → 阶段9: 定稿整合
```

每个阶段结束时有**质量门槛检查**，不通过不得进入下一阶段。详细 spec 见各阶段独立文件。

> **图表分两批出**：核心架构图在写作前完成——它们是报告的骨架；数据图表随写作按章产出——它们必须与文字内容绑定、用数据驱动。

> **🚫 严禁标密**：本 skill 产出的所有研究报告均基于互联网公开资料，不涉及任何秘密信息。报告的任何位置**禁止标注密级**。

---

## 多 Agent 协同执行体系（v5 整合 V3+V4）

本 skill 在阶段 7（分章写作）和阶段 8（红队审查）采用**多 Agent 协同**，把"写作者自评不可信"这个结构性死结（V3 R3）用系统结构解开——**检查者与被检查者物理分离**。其余阶段（1-6、9）用单 Agent 分派或 orchestrator 直接执行。编排总纲见 [`references/multiagent-orchestration.md`](references/multiagent-orchestration.md)。

### report_orchestrator 编排剧本（主对话采用，非被拉起的子 Agent）

`report_orchestrator` **不是一个 Agent 定义文件，而是主对话采用的编排剧本**——主对话亲自扮演编排器，用 `Agent` 工具逐个分派工作型子 Agent（写作/审计/红队等），委托链恒为 depth-1（主对话 → 工作 Agent）。它的职责：分派、门禁裁决、CHECKPOINT（用户在环确认）、矛盾裁决、降级决策。

11 个角色（落在 `agents/`，沿用 academic-paper 约定）：

| 角色 | 族 | 模型 | 阶段 | 一句话职责 |
|---|---|---|---|---|
| `report_orchestrator`（主对话剧本） | 编排 | Opus | 1-9 | 分派/门禁/CHECKPOINT/裁决/降级 |
| `source_collector_agent` | 研究 | Haiku | 2 | 搜集→下载→抽取→来源索引（强制下载纪律） |
| `fact_verifier_agent` | 研究 | Opus | 3 | 事实核验台账，强表述降级 |
| `outline_architect_agent` | 设计 | Opus | 4 | 产出 outline.md 叙事框架契约 |
| `card_synthesizer_agent` | 设计 | Sonnet | 5 | 台账→结构化卡片 + 证据包 + card-index |
| `diagram_agent` | 制图 | Haiku | 6+7 | 核心架构图（先于写作）+ 数据图表 |
| `chapter_writer_agent` | 写作 | Sonnet | 7 | 逐章写作（生成半），卡片→叙事 |
| `chapter_auditor_agent` | 审计 | Opus | 7 | 逐章独立审计（评估半，R3 的解） |
| `redteam_agent`（×4 人格） | 红队 | 2×Opus+2×Sonnet | 8 | 全报告对抗审查，异构模型防同质化 |
| `redteam_synthesizer_agent` | 红队 | Sonnet | 8 | 合并去重 4 份红队报告→统一风险清单 |
| `finalizer_agent` | 格式 | Haiku | 9 | 合并、合约终检、转换器、12 项交付清单 |

> **模型选型原则**（v4 §3.2）：按任务的**认知负荷类型**分级，不按角色"重要性"。强推理/强判断（审计、红队、核验、大纲）用 Opus；结构化生成（写作、卡片合成、红队综合）用 Sonnet；机械/模板化（搜集、制图、定稿）用 Haiku。非 Opus 角色必须显式传 `model` 参数，不依赖继承 orchestrator 的 Opus。

### 三档协同模式（按报告规模/类型分档，成本花在刀刃）

| 档位 | 触发条件 | 阶段 7 写作 | 阶段 8 红队 | Agent 调用量级 |
|------|---------|-----------|-----------|--------------|
| **完整多 Agent** | 立项报告(proposal) / 篇幅 ≥40 页 / 核心章 ≥3 | 全部章 writer+auditor 对抗 + loop | 4 人格并行 + 综合 | 完整（10+ 角色） |
| **分层多 Agent**（默认，标准研究报告） | 深度研究报告 30-50 页 / 核心章 2-3 | **仅核心分析章**走对抗；摘要/前言/附录 orchestrator 直接写 | 4 人格并行 + 综合 | 标准（6-8 角色） |
| **单 Agent 极速** | 快速简报(brief) / <15 页 / ≤2 章 / 用户说"简报/快速" | orchestrator 单 Agent 写 + **V3 单 Agent 自查兜底** | 压缩为 3 维度，orchestrator 自审 | 最小（回退 V3） |

> **降级是"回退到 V3"而非"没有质量控制"**：单 Agent 极速档直接采用 V3 的 CHECKPOINT/STATS/REPORT 单 Agent 自律机制，orchestrator 本身也从 Opus 降到 Sonnet。**无 `Agent` 工具时的兜底**：若本 skill 被作为嵌套子 Agent 拉起（无法 depth-1 分派），自动降级为单 Agent 极速档，并标注"多 Agent 协同不可用，已降级为 V3 单 Agent 模式"。

### 整合后的机制分层（替代 V3 §4.1.1 原表，升级版）

| 层级 | 名称 | V3 归属（单 Agent 自律） | V5 归属（多 Agent 结构） |
|------|------|------------------------|------------------------|
| L0 阻断型 | 🛑 STOP 用户确认 | 单 Agent 提示 | **orchestrator 执行 6 个 CP**（CP1 参数/CP2 封面/CP3 大纲/CP4 逐章审计汇总/CP5 红队处理/CP6 交付清单） |
| L1 量化型 | 📊 STATS | 写作 Agent 自跑 wc/grep | **审计 Agent 调 `contract_check.py` 真脚本** |
| L2 报告型 | 📋 REPORT | 写作 Agent 自出 | **审计/红队 Agent 产出**（检查者 ≠ 被检查者） |
| L3 警告型 | ⚠ WARN | 记录日志 | orchestrator 记 P1-P3（复用 UEAS 问题分级） |

> 一句话：V3 的"三层机制"作为**规格与用户阻断层**完整保留；其中"自查"部分的**执行主体**从写作 Agent 迁移到独立审计/红队 Agent。V3 的检查项（stage-7 自查清单、converter-contract、writing-standards）不删除，而是变成审计 Agent 的评分细则 rubric。

---

## 九阶段简要说明

### [阶段 1：项目初始化](references/stage-1-init.md)
智能推断参数（题名/受众/方法/规模）、报告类型自动识别（5 种类型）、建立工作目录、确认分析框架与研究方法。默认 7 项参数 ≤2 项标 ⚠️，用户说"继续"即启动。

### [阶段 2：资料搜集、抽取与来源索引](references/stage-2-collection.md)
按优先级搜集（P0 政府/法规/权威媒体 → P1 学术论文/智库 → P2 财报/技术社区），可信度分 A/B/C/D 四级，MinerU 精准解析 PDF/Office/图片为结构化 Markdown。

### [阶段 3：事实核验](references/stage-3-verification.md)
整个方法论的核心——未经验证的事实不能进入正文。建立核验台账，优先核验首次性判断/数字/因果判断/能力边界类主张。核验后按状态分流：真实→可用，错误→不入正文。

### [阶段 4：详细大纲](references/stage-4-outline.md)
叙事框架格式（本节要论证什么 + 论证路径 + 关键素材），分级图表规划（核心架构图有图号+图名、数据图表只写方向）。模板采用"必选骨架 + 可选模块池"机制，按报告类型→模板映射自动加载。

### [阶段 5：专题研究——卡片与证据包](references/stage-5-cards.md)
台账的零散主张 → 结构化卡片（案例卡/技术卡/架构卡/理论卡），每条关键判断绑定证据包（claim_id + 来源），登记到 card-index.csv 确保可追溯。

### [阶段 6：核心架构图——先于写作](references/stage-6-diagrams.md)
总览图/架构图/流程图在分章写作前完成。出图工具：drawio（复杂架构）、fireworks-tech-graph（技术架构）、Mermaid（简单流程）。PNG 统一 300dpi+，配色限灰度色板 + 暗红 #D62728。

### [阶段 7：分章写作与数据图表](references/stage-7-writing.md)
卡片→正文叙事化转写（三条铁律：禁逐条翻译字段、禁字段标签、强制主张→证据→推理三角），12 条内容质量标准，10 项逐章即时自查清单。标题只写纯文字，编号交给转换器。数据图表随写作出。
> **多 Agent 档（默认/完整）**：改为 `chapter_writer_agent` + `chapter_auditor_agent` **写审对抗 pipeline**——逐章 loop-until-pass，审计采用盲态预承诺（先锁标准再看稿），量化维度由审计 Agent 调 `contract_check.py` 真跑。写审物理分离解开 R3 死结。逐章审计报告汇总走 CP4。详见 [`references/workflow-stage7.md`](references/workflow-stage7.md)。单 Agent 极速档回退本文件的 V3 自查清单。

### [阶段 8：红队审查](references/stage-8-review.md)
8 个检查维度（证据薄弱/逻辑跳跃/夸大表述/概念堆砌/偏题/矛盾/卡片浪费/图表一致性），高风险项 100% 处理，中风险项 ≥80% 处理。逐项落地修改并记录结果。
> **多 Agent 档**：8 维度聚为 **4 个红队人格并行**（`redteam_agent` ×4，异构 2×Opus+2×Sonnet）审查全报告，再由 `redteam_synthesizer_agent` 合并去重为统一风险清单，走 CP5。红队只找跨章/对抗性问题，接收阶段 7 审计报告避免重复逐章打分。详见 [`references/workflow-stage8.md`](references/workflow-stage8.md)。

### [阶段 9：定稿整合](references/stage-9-finalize.md)
术语/引用/编号/交叉引用统一，全章合并为 final-report.md，md→docx 转换器自动生成符合 V3.1 格式规范的 Word 文档，12 项交付清单逐项确认。

---

## 质量门槛总表

| 阶段 | 进入条件 |
|---|---|
| 阶段 4 详细大纲 | 素材全部抽取 + 来源索引完成 + 事实完成第一轮拆解 |
| 阶段 7 分章写作+数据图表 | 大纲确认 + 专题卡片达标并登记 card-index + 核心架构图草图完成 + 核心章节有足够 A/B 级来源 |
| 阶段 9 定稿 | 红队风险清单完成 + 高风险项清零 + 每章有结论和贡献 |

### 质量门槛失败处理——如果门槛未通过

| 失败症状 | 触发条件 | 处理动作 | 退回阶段 |
|---------|---------|---------|---------|
| 素材抽取不全 | 阶段 2 质量门槛第 1 项未通过 | 检查缺失的素材格式是否支持；对不支持格式标注后跳过 | 回到阶段 2.3 |
| 来源元数据缺失 | 阶段 2 质量门槛第 2 项未通过 | 逐份补充 source_id/credibility_level | 回到阶段 2.2 |
| D 级事实未标记 | 阶段 2 质量门槛第 4 项未通过 | grep 扫描 D 级来源文本，断言性语句加 `[待核验]` | 回到阶段 2.1 |
| 强表述核验不足 | 阶段 3 质量门槛第 2 项未通过 | 逐条核验或降级表述为"据称/部分实现" | 回到阶段 3.2 |
| 核心章缺 A/B 来源 | 阶段 3 质量门槛第 3 项未通过 | 追加专项搜索，如仍不足则标注"证据基础有限" | 回到阶段 2 |
| 大纲未获用户确认 | 阶段 4 质量门槛第 6 项未通过 | 展示大纲，逐项确认结构 | 回到阶段 4.1 |
| 卡片不足 | 阶段 5 质量门槛第 1 项未通过 | 补充专题卡片并登记 | 回到阶段 5.2 |
| 核心架构图缺口 | 阶段 6 质量门槛第 2 项未通过 | 快速出图草稿（先有再优化） | 回到阶段 6.1 |
| 数据图表与文字不契合 | 阶段 7 质量门槛第 4 项未通过 | 确认数据来源准确性，必要时换图表类型 | 回到阶段 7.3 |
| 证据密度不达标 | 阶段 7 证据密度检查未通过 | 补充来源或标注"基于作者分析" | 回到阶段 7.3 |
| 红队高风险残留 | 阶段 8 质量门槛第 2 项未通过 | 逐条处理（删/改写/补证据/降级） | 回到阶段 8.3 |
| 交叉引用不一致 | 阶段 9 整合阶段发现 | 逐章核对修正 | 回到阶段 9.1 |

> **原则**：走到哪、卡在哪、退到哪。不退到更早阶段——除非根源在前序阶段。

---

## 常见问题

**Q：用户只给了一个主题，没有提供素材怎么办？**
A：按阶段 2.0「资料搜集」执行——先用 web-search-skill `search` 搜 A/B 级来源，再用 `paper-search` CLI 搜学术论文。

**Q：用户提供了素材，是不是就不用扩展搜集了？**
A：不是默认跳过。阶段 1.1a 会强制停下来问用户："仅基于素材"还是"素材+扩展搜集（推荐）"。

**Q：用户要求的时间很紧，能否跳过某些阶段？**
A：可以压缩但不能跳过。最精简路径：阶段 3（事实核验）和阶段 8（红队审查）不可跳过。极速模式自动填入默认参数、合并阶段 2-3、大纲降到二级标题、只出 1 张总览图、写作只强制执行标准 A+D、红队压缩为 3 项。

**Q：报告不需要架构图怎么办？**
A：纯叙事/历史类可确认跳过。但大多数分析型报告至少需要 1 张核心闭环图。

**Q：用户中途改变了想法（主题/规模/受众）？**
A：回到阶段 1 重新确认参数，检查已有产物可复用性，不在新旧要求之间折中妥协。

---

## 反例清单——执行本 skill 时不要做的事

| # | 反模式 | 正确做法 |
|---|--------|---------|
| 1 | **参数确认阻塞流程**——逐项问 7 个问题 | 自动推断，一次性展示，≤2 项标 ⚠️，用户说"继续"即启动 |
| 2 | **跳过参数直接搜资料** | 至少确认题名和受众后再进阶段 2 |
| 3 | **D 级来源当结论用** | D 级仅作线索，必须找到 A/B 级来源确认后才入正文 |
| 4 | **质量门槛未通过就进入下一阶段** | 见上方「质量门槛失败处理」表 |
| 5 | **先写正文再补图表** | 核心架构图在阶段 6 先于写作；数据图表在阶段 7 随写作按章产出 |
| 6 | **把强表述当成事实** | 核验台账盯首次性判断/能力边界类主张，找不到 A/B 级证据就降级 |
| 7 | **红队审查走形式** | 至少做一轮独立红队（换视角/假设对立立场），高风险项必须全部处理 |
| 8 | **只写正向不写边界** | 每章末尾强制留至少 1 句分析局限说明 |
| 9 | **建议写成空话** | 每条建议必须回答：谁 / 做什么 / 资源 / 效果指标 |
| 10 | **跳过 Word 导出** | 阶段 9 必须执行 md→docx 转换器，生成符合 V3.1 规范的 .docx |
| 11 | **凭记忆写作**——不读取大纲就开始写正文 | 阶段 7 每节写作前必须读取 `research/outline.md` 对应条目；多 Agent 档下 `chapter_writer_agent` 输入契约只含当前章条目，物理上拿不到跨章内容 |
| 12 | **内部自查**——写作 Agent 只在心里打勾不输出报告 | 多 Agent 档下自查由**独立** `chapter_auditor_agent` 产出结构化审计报告；单 Agent 档下 10 项自查必须输出报告逐项标注通过/未通过/处理 |
| 13 | **跳过量化验证 / 编造字数**——写完不统计或自报字数 | 量化维度（字数/图/表）由审计 Agent 调 `contract_check.py` 真跑，写作 Agent 无权自报通过；审计报告须含脚本 stdout |
| 14 | **跨 Agent 越界写**——审计者/红队顺手改稿或写下一章 | 发现者 ≠ 修复者：审计只出裁决 + issue 清单，修改交回 `chapter_writer_agent`；每个角色严守 Phase Boundary |
| 15 | **审计放宽标准**——看了稿再把评分标准调松到刚好让稿子通过 | 审计采用盲态预承诺：Phase A 未看稿先书面锁定触发词，Phase B 打分语言须 substring-match Phase A 承诺（一致性 lint） |
| 16 | **降级档误用多 Agent**——5 页简报也拉起 writer+auditor 对抗 | brief/简报自动进单 Agent 极速档回退 V3 自查；多 Agent 是标准/完整档的增强，不是唯一选项 |

---

## 参考文件

本 skill 包含以下参考文件，在需要时读取：

**各阶段详细 spec**（拆分自本文件）：
- `references/stage-1-init.md` — 阶段 1 详细 spec：项目初始化
- `references/stage-2-collection.md` — 阶段 2 详细 spec：资料搜集与抽取
- `references/stage-3-verification.md` — 阶段 3 详细 spec：事实核验
- `references/stage-4-outline.md` — 阶段 4 详细 spec：详细大纲
- `references/stage-5-cards.md` — 阶段 5 详细 spec：专题研究（卡片+证据包）
- `references/stage-6-diagrams.md` — 阶段 6 详细 spec：核心架构图
- `references/stage-7-writing.md` — 阶段 7 详细 spec：分章写作+数据图表
- `references/stage-8-review.md` — 阶段 8 详细 spec：红队审查
- `references/stage-9-finalize.md` — 阶段 9 详细 spec：定稿整合+Word导出

**附录**：
- `references/appendix-report-types.md` — 报告类型适配（类型识别表+模板映射+领域适配指南）
- `references/appendix-converter-contract.md` — 转换器合约（标题/图片/表格/禁止内容四条约法+自查清单+C1-C5编号化检查规格）

**多 Agent 协同**（v5 新增，阶段 7/8 写审对抗与红队并行）：
- `references/multiagent-orchestration.md` — **编排总纲**：depth-1 委派 + 输出隔离契约 + 噪声重试 + 门禁 + 三档模型联动
- `references/workflow-stage7.md` — 阶段 7 写审对抗 pipeline 编排脚本（双表达）
- `references/workflow-stage8.md` — 阶段 8 红队并行审查编排脚本（双表达）
- `agents/chapter_writer_agent.md` — 写作·生成半（Sonnet）
- `agents/chapter_auditor_agent.md` — 审计·评估半（Opus，R3 的解，含盲态预承诺 Phase A/B）
- `agents/redteam_agent.md` — 红队 4 人格（异构 2×Opus+2×Sonnet）
- `agents/redteam_synthesizer_agent.md` — 红队综合去重（Sonnet）
- `agents/outline_architect_agent.md` — 大纲契约生产者（Opus）
- `agents/source_collector_agent.md` / `fact_verifier_agent.md` / `card_synthesizer_agent.md` / `diagram_agent.md` / `finalizer_agent.md` — 阶段 2/3/5/6/9 角色
- `agents/contracts/writer_contract.json` + `auditor_contract.json` — 生成/评估契约维度 schema
- `scripts/contract_check.py` — 合约 C1-C5 + 量化 QS1-QS3 检查（审计 Agent 调用的确定性工具）

**模板与规范**：
- `references/claims-ledger-template.csv` — 事实核验台账模板
- `references/source-index-template.csv` — 来源索引模板
- `references/red-team-checklist.md` — 红队审查详细清单
- `references/writing-standards.md` — 写作标准详细说明与示例（含 12 条标准）
- `references/architecture-analysis-guide.md` — 架构分析方法论详细指南
- `references/研究报告格式规范.md` — **【权威】研究报告 Word 格式规范 V3.1**
- `references/word-format-spec.md` — Word 文档格式规范（旧版 v1.0，已归档）
- `references/md-to-docx-pitfalls.md` — Markdown→Word 转换踩坑记录与修复方案
- `design/md-to-docx-design-v2/` — **【权威】md→docx 转换器 v2 完整设计方案**

**外部依赖——资料搜集与抽取工具**：
- **web-search-skill**（`web-search-skill/scripts/search.js`）— 通用网页搜索，5 个子命令
- **paper-search**（CLI: `paper-search`）— 学术论文搜索与下载，3 个子命令
- **MinerU**（`mineru/scripts/mineru_parse.py`）— 文档精准解析（VLM API）

**外部依赖——出图工具**：
- **drawio**（MCP + 桌面版）— 架构图、流程图
- **fireworks-tech-graph** — 技术架构图，16 种模板
- **Mermaid** — 简单流程图备选，内联 Markdown

> 所有工具路径统一配置在 `references/tool-paths.json` 中。
