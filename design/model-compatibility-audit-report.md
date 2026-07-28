# deep-research-report 跨模型兼容性审计报告

> **审计日期**：2026-07-28
> **审计范围**：本 skill 是否隐含依赖 Claude 系列模型的特定能力/行为模式；若换用 DeepSeek V3.2/V4 级别或其他厂商同等能力模型执行 `report_orchestrator` 剧本与 12 个 Agent 角色，是否会导致流程失效、质量下降或规则被忽略
> **审计方法**：发现层三 Agent 并行（外部调研 / 技术评估 / 资产盘点）+ 编排器独立代码实测
> **与既有审计的关系**：本报告是**全新维度**（跨模型兼容性）。`design/skill-quality-audit-report.md` 的 5 维度（完整性/稳定性/可读性/缺失功能/边缘案例）问题已修复，本报告不重复审计那些维度

---

## 执行摘要

本 skill 在 Claude 系列上已达到工业级成熟度：确定性脚本层（`contract_check.py` C1-C9 + QS1-QS4、`figure_gate.py`、`term_consistency_check.py`、`card_overlap_check.py`）建设扎实，写审对抗 + 红队并行的结构性设计正确。**这些机制中"靠脚本"的部分跨模型可移植，"靠模型自律"的部分则高度依赖 Claude 的强指令遵从特性。**

**核心结论**：本 skill 目前**不能**直接迁移到 DeepSeek V3.2 级别模型可靠运行。障碍分三类：

| 类别 | 性质 | 可解性 |
|------|------|--------|
| **A. 隐性 Claude 能力依赖** | 规则密度、盲态预承诺、固定分隔符、结构化输出无校验 | **可解**——转为确定性校验 + prompt 分级 |
| **B. 既有代码缺陷**（与模型无关，但弱模型下后果被放大） | YAML SSOT 字段名不匹配、静默降级、三处失败语义冲突 | **可解**——修 bug + 统一失败语义 |
| **C. 架构级生态锁定** | `Agent` 工具 depth-1 委派、drawio MCP | **不可解**——只能声明边界 + 降级 |

**最关键的单点风险**：`chapter_auditor_agent` 的 Phase A 盲态预承诺要求一次性产出 **24 维度 × 4 字段 = 96 个结构化字段**（立项报告档 29 维度 = **116 字段**），而 DeepSeek V3.2 单次最大输出仅 **8K tokens（约 6000 中文字）**。这是硬性容量冲突，不是调优能解决的问题。

**发现总计**：**30 项**（P0×7 / P1×14 / P2×9）

---

## 0. 目标模型能力画像（设计基准）

来自发现层调研，作为后续所有判断的基准。**设计应以 DeepSeek V3.2 为能力下限**——V4 截至审计日尚未正式发布，其预览规格（1M 上下文 / 384K 输出）不可作为设计依据。

### 0.1 可以依赖的能力

| 能力 | 下限值 | 可信度 |
|------|--------|--------|
| 上下文窗口 | ≥128K tokens（DeepSeek V3.2 在 Bedrock 上的下限；直连 API 为 164K） | A |
| Function calling / JSON mode | 主流模型均支持 | A |
| 单条简单指令遵从 | ≥70% | B |
| 中英文混合输出 | 支持 | A |

### 0.2 必须假设**不可靠**的能力

| 能力 | 实测/推算 | 对本 skill 的直接影响 |
|------|----------|---------------------|
| **多约束同时追踪** | 遵从率 ≈(单条准确率)^n。DeepSeek 单条 IFEval ≈84% → 20 条并列规则理论遵从率 **≈2.5%** | `chapter_writer_agent` 有 30 处强制约束 → 近乎必然违规 |
| **单次输出长度** | **8K tokens ≈ 6000 中文字** | Auditor Phase A 需 104 字段；长章正文需分段 |
| **固定分隔符遵守** | 弱模型易在内容中重复分隔符造成污染 | `[AGENT-OUTPUT-START/END]` 提取失败 |
| **JSON 生成合法性** | DeepSeek JSON mode **非约束解码**，仍会产生格式错误 | 两个 contract JSON 无校验 → 静默劣化 |
| **thinking + function calling 并用** | DeepSeek V3.2 官方明确**互斥** | 审计角色"边推理边调脚本"的假设不成立 |
| **LLM-as-judge 公正性** | 存在位置偏差/自我一致性偏差/长度偏差 | 盲态预承诺与红队评分可信度下降 |

> **可信度标注**：A=官方文档；B=同行评审论文/权威评测；C=技术博客/社区实测；D=传闻。DeepSeek IFEval≈84%、Claude Opus 4.5≈90.9% 为 B 级；"Curse of Instructions"乘法衰减规律为 B 级（ManyIFEval/IFScale）。

---

## 1. P0 级发现（阻断性——不修则跨模型必然失效）

### P0-1：Auditor Phase A 输出规模超出弱模型单次输出上限（硬冲突）

| 项 | 内容 |
|----|------|
| **位置** | `agents/chapter_auditor_agent.md:122-132`；`agents/contracts/auditor_contract.json:19-178`（**实测 24 维度**）+ `:180-211`（proposal_extra **5** 维度） |
| **事实** | Phase A 要求：①`## 契约复述`覆盖**全部**维度组（实测 **8 组**）；②`## 评分计划`为**每个维度**写 `### <维度>` 小节，每节含 four-field（`dimension`/`what_to_look_for`/`what_triggers_block`/`what_triggers_warn`）。实测维度数 **24**（立项报告 **29**）→ **96-116 个结构化字段** |
| **冲突** | DeepSeek V3.2 单次最大输出 **8K tokens ≈ 6000 中文字**。96 字段 + 契约复述段落，按每字段 15-30 字保守估算已达 3000-5000 字，加复述段落**逼近或超出上限** |
| **后果** | 输出被截断 → Phase A lint 失败 → 按 `:134` 重试 1 次 → 二次失败即 `[GENERATOR-PHASE-ABORTED]` → 该章审计不可用 → orchestrator 记 P0。**在弱模型上这不是偶发，是常态** |
| **风险等级** | **P0** |
| **影响范围** | 阶段 7 全部核心章（完整档=所有章）；直接使 R3 死结的解失效 |

### P0-2：`outline_reader.py` subsections 字段名与规范不匹配，结构清单被 100% 静默丢弃

| 项 | 内容 |
|----|------|
| **位置** | `scripts/md2docx/assemble/outline_reader.py:149-150` |
| **规范** | `references/stage-4-outline.md:98-101,117` 定义 subsections 每项为 `{parent_section_no, subsection_no, subsection_title}` |
| **实现** | 代码读 `sub.get("parent", "")` 与 `sub.get("title", "")` —— **字段名完全不匹配** |
| **二次不匹配** | `outline_reader.py:158-161` 查找 parent 序号时只处理 `isinstance(s, str)`，而规范要求 `sections` 每项是 dict（`{section_no, section_title}`）→ 即使字段名改对，parent 匹配仍会失败 |
| **实测验证** | 编排器按规范格式构造 structure 实跑 `_build_structure_lookup()`：**SUBSECTION 条目 = 0**（章、节正常，小节全丢） |
| **telemetry 反向误导（加重情节）** | `build_structure_manifest()`（`:215`）用 `len(ch.get("subsections", []))` 计数，**不应用字段名逻辑**。实测：manifest 报 `subsection_count=1`，lookup 实际 0 条。`builder.py:196-204` 的 INFO 日志会打印 `subsections=1`，**主动告诉操作者结构注入成功了** |
| **下游后果** | `headings.py:479-497` 按标题文本精确匹配 lookup；未命中的 H4 落入 `unmatched_headings` 分支，**静默保留启发式推断的分类与编号**——正是 YAML SSOT 设计要取代的脆弱路径 |
| **⚠️ 危害等级修正（后续验证补充）** | 复核 `headings.py:557-591` 发现存在 **Phase 7b「重算 SUBSECTION 三级编号」**逻辑，它在 overlay 后按文档序无条件重写全部 H4 编号。**这是一条独立兜底路径**——它解释了为何本 bug 至今未导致 H4 编号全面错乱。因此本项的实际后果应理解为「**结构清单与分类丢失，编号有兜底**」，而非「编号必然错乱」。**危害等级从"编号错误"下调为"SSOT 失效 + 依赖隐式兜底"**，但仍属 P0（YAML 权威性被架空，且 telemetry 谎报） |
| **对照证据** | `scripts/merge_drafts.py:207-209` **正确**按 dict 读 `section_no` → 证明这不是规范歧义，而是 `outline_reader.py` 单点失同步 |
| **风险等级** | **P0**（与模型无关的既有缺陷，但弱模型下更难被人工察觉） |
| **影响范围** | 阶段 9 转换器的 H4 编号/分类；`outline.md` 是 6 方共享 SSOT（`stage-4-outline.md:122-128`） |

### P0-3：三处消费同一 SSOT 的脚本，失败语义互相冲突

| 消费者 | 位置 | YAML 缺失/失败时行为 |
|--------|------|---------------------|
| `merge_drafts.py` | `:56-63` | 打印 `[ERROR]` + **`sys.exit(2)` 硬阻断** |
| `md2docx/builder.py` | `:210-219` | 仅记 `Level.WARNING`，**转换继续跑**，回退启发式 |
| `figure_gate.py` | `:65-66` | **裸 `return None`，无任何诊断输出** |

补充缺陷：
- `outline_reader.py:55-67` stderr 打印 `[FATAL]` 字样，但调用方 `builder.py` 只记 WARNING → **"FATAL"标签是骗人的，它不阻断**
- `merge_drafts.py:60` 的 `yaml.safe_load` **无 try/except**，格式错误将抛未捕获 traceback
- **全 skill 检索确认**：`SKILL.md`/`references/`/`agents/` 中**无任何位置**要求 orchestrator 检查该 stderr 或 `W-OL-01` issue code → 该信号**无消费者**

**风险等级**：**P0**。**影响**：同一份坏 YAML，走不同路径得到"硬失败/静默降级/无声消失"三种结果，orchestrator 无法形成一致判断；弱模型 YAML 生成合法率更低，触发频率更高。

### P0-4：两个 Agent 合约 JSON 无任何 schema 校验（纯 prompt 自觉）

| 项 | 内容 |
|----|------|
| **位置** | `agents/contracts/writer_contract.json`（D1-D10）、`agents/contracts/auditor_contract.json`（26+5 维度） |
| **检索结论** | 二者仅被 `agents/*.md`、`SKILL.md`、`README.md` 的 **prompt 文本**引用；`scripts/` 下**无任何脚本**对其或对模型据其产出的内容做校验（`md2docx/validate.py` 是 docx IR 校验，与 Agent 合约无关） |
| **性质** | 这两个文件本身是**叙述性 schema**（`requirement` 为自然语言），**不是 JSON Schema Draft 格式**，即使想校验也不能直接 `jsonschema.validate()` |
| **后果** | 模型产出的自声明/评分计划结构合法性**完全无兜底**。Claude 能自觉遵守；DeepSeek JSON mode 非约束解码，结构坍塌（漏字段/嵌套错/```json 围栏未剥离）无人拦截 |
| **风险等级** | **P0** |

### P0-5：`chapter_writer_agent` 约束密度远超弱模型追踪上限

| 项 | 内容 |
|----|------|
| **实测** | grep 强制性表述（必须/禁止/不得/MUST NOT/强制/红线）计数：`chapter_writer_agent.md` **30 处**（全 skill 最高，Sonnet 驱动）；`chapter_auditor_agent.md` 15 处；`source_collector_agent.md` 7 处 |
| **同时生效的规则族** | 四条转写铁律 + 写作标准 0-22 + F1-F8/F10 禁止清单 + 合约 C1-C9 + 验收维度 D1-D10 + 7 项强制读取清单（`writer-template.md:207-218`） |
| **推算** | 按乘法衰减，DeepSeek 单条 84% → 20+ 条并列硬规则遵从率 **≈2.5%**。业界经验硬规则上限 **≤5 条** |
| **后果** | 弱模型下 Writer 违规近乎必然；且违规项由 Auditor 逐条捕获 → 触发 REVISE → 2 轮上限耗尽 → P0 死锁常态化 |
| **风险等级** | **P0** |

### P0-6：输出隔离契约用固定分隔符，弱模型下易污染

| 项 | 内容 |
|----|------|
| **位置** | `references/multiagent-orchestration.md:33-52`；全部 12 个 agent 文件均写死 `[AGENT-OUTPUT-START]/[AGENT-OUTPUT-END]` |
| **调研结论** | 固定分隔符在弱模型上易被内容污染（模型在正文中重复分隔符）；**随机 nonce 边界**可将可靠性提升至 95%+。可靠性排序：Tool Call 返回 > 随机边界 > 固定分隔符 > 文件落盘 |
| **加重因素** | 本 skill 的正文**本身就在讨论这些标记**（`writer-template.md:121` F1 条目、`:190-198` 自声明示例、`chapter_writer_agent.md:61-72`）→ 模型极易把示例中的标记原样吐出，造成提取边界错乱 |
| **现状检测** | 仅由 orchestrator 用正则"心算"（`multiagent-orchestration.md:47`），**无独立脚本** |
| **风险等级** | **P0** |

### P0-7：噪声比率检测（>30%）无脚本实现，纯靠 orchestrator 目测

| 项 | 内容 |
|----|------|
| **位置** | `references/multiagent-orchestration.md:48` |
| **现状** | 规定"污染行（GBK 乱码 + 进度条字符 `▕ █ %`）>30% → CONTAMINATED → 重试"，但**仅为 prompt 层描述，无落地脚本** |
| **问题** | ①"目测比率"对任何模型都不可靠，弱 orchestrator 更甚；②若朴素实现为"非 ASCII 占比"将把**正常中文全部误判为污染** |
| **风险等级** | **P0**（关键路径重试决策依赖此判断） |

---

## 2. P1 级发现（应修——显著影响跨模型可靠性）

### P1-1：盲态预承诺的一致性检查是"模型自查自"，非独立机械校验

- **位置**：`agents/chapter_auditor_agent.md:150,155`；`auditor_contract.json:217-220`
- **现状**：Phase B 打分语言须 substring-match Phase A 触发词，但这是**审计 Agent 对自己输出的内部自检**，无外部脚本验证
- **关键澄清**：这不同于 R3（写审分离已用物理隔离解决）。此处风险是"审计者对自身前后一致性的自律"
- **弱模型失效模式**：更擅长"事后编造一致性文本"而非真正遵守时序
- **天花板声明**：即使落成机械校验，它检查的仍是"文字层面是否复述关键词"，**不能证明模型真的先承诺后打分**。机械校验能显著提高作弊成本，但不能 100% 杜绝话术伪装
- **前提缺失**：Phase A 当前**不强制落盘为独立结构化文件**，缺少机械校验的输入

### P1-2：`finalizer_agent` 模型档位与任务复杂度严重错配

- **位置**：`agents/finalizer_agent.md:4`（`model: haiku`）、`:30-49`（任务链）
- **任务链**：步骤 0 三项正则剥离（标记/自声明区块/红队批注）→ H1 冲突 grep → 结构驱动合并 → `contract_check.py --merged --stage stage9` → `convert_references.py` → 斜杠引用检测 → C9 局部参考文献检测 → 生成 bibliography → 调 md2docx → 核对 12 项交付清单
- **问题**：全 skill **最长、最依赖精确文本操作**的任务链交给**最弱模型**，且位于**交付链末端**（错误直接进最终产物）
- **跨模型含义**：若映射为 DeepSeek 低配变体（如 V4-Flash），失败率进一步上升

### P1-3：`source_collector_agent` 同类档位错配

- **位置**：`agents/source_collector_agent.md:4`（Haiku）、`:34-45`（10 条字段自动填充规则）
- 承担 10 条并列填充规则 + 强制下载纪律，规则密度与档位不匹配

### P1-4：红队"异构模型防同质化"的设计前提在单一模型宿主下失效

- **位置**：`agents/redteam_agent.md:17-26`；`references/workflow-stage8.md:29-34`
- **现状设计**：2×Opus + 2×Sonnet，明确声明"让模型本身构成视角差异的一部分，而非仅依赖 prompt 措辞"
- **失效**：DeepSeek 宿主通常只有单一模型（或 Pro/Flash 两档且能力差距大），异构假设不成立 → 4 人格退化为同一模型的 4 次相似调用，**同质化盲点风险回归**

### P1-5：红队输出格式在两份文件中不一致

- `references/workflow-stage8.md:46` 伪代码声明 `output_schema: { risks: [{id, level, chapter, type, desc, fix}] }`（JSON）
- `agents/redteam_agent.md:77-84` 实际要求 **Markdown 表格**
- 强模型可自行消解，弱模型面对矛盾指令行为不可预测

### P1-6：写作标准数量在四处文件中不一致

| 位置 | 声称 | 实际 |
|------|------|------|
| `references/writing-standards.md` | — | **标准 0-22（23 条）**（实测 grep 章节头，含标准 21 表格写作规范、标准 22 术语一致性） |
| `SKILL.md:232` | "含 12 条标准" | 不符 |
| `README.md:89` | "写作标准体系（17 条）" | 不符 |
| `agents/chapter_auditor_agent.md:22` | "12+5 条" | 不符 |
| `agents/chapter_writer_agent.md:22-25` | 引用至标准 20 | 不完整 |

弱模型据此无法确定应遵守的标准全集。

### P1-7：Agent 角色数量与角色表在三处不一致

- `SKILL.md:42` 称"11 个角色"（表列 11 行）
- `README.md:61` 称"10 个角色"（表列 **13** 行）
- `agents/` 实际 **12 个 .md** + 2 个 contracts JSON
- **`references/multiagent-orchestration.md:26` 角色表仍列已废弃的 `diagram_agent`（Haiku）**，与 `SKILL.md:59`（明确声明已拆分为 `architecture_chart_agent` + `data_chart_agent`，均升 Sonnet）**直接冲突**
- `agents/outline_architect_agent.md:3` 的 description 亦仍引用 `diagram_agent`

### P1-8：§8.5 标题提取规则为纯 prompt 级要求，无脚本支撑

- **位置**：`references/multiagent-orchestration.md:87-96`
- 要求 orchestrator 从 YAML `section_title` 取纯文字、且校验 YAML 与 Markdown heading 一致性——**纯人工/模型判断**
- 该规则是"防编号污染三重防线的第一道"，弱 orchestrator 执行不到位则防线失效
- **可直接复用**`outline_reader.py:80-179` 已有的展平逻辑落成脚本

### P1-9：glossary.md 是第二处依赖模型 YAML 生成能力的 SSOT

- **位置**：`references/glossary.md:13-23`（YAML 结构）；由 `card_synthesizer_agent`（Sonnet）阶段 5 产出
- `scripts/term_consistency_check.py:32-53` 依赖从中提取 ```yaml 代码块并 `yaml.safe_load`
- 弱模型 YAML 生成失败 → 术语一致性检查（F10 / 标准 22）整体失效

### P1-10：阶段 9 十二项交付清单中 2 项结构性不可脚本化，弱模型下无兜底

- **位置**：`references/stage-9-finalize.md:124-135`
- 可脚本化 7-8 项（封面/密级、字体、章节编号、图表编号、表格样式、页码、目录）——多为 md2docx 渲染层确定性行为
- 部分可脚本化：参考文献 GB/T 7714 细粒度格式
- **结构性不可脚本化 2 项**：`:25` 红队风险清单处理确认（语义比对"处理建议 vs 实际改动"）、`:26` 全文通读
- 弱模型执行这两项的可信度显著低于 Claude，当前无人在环强制要求

### P1-11：`figure_gate.py` YAML 失败完全静默（无诊断）

- **位置**：`scripts/figure_gate.py:63-66`
- 裸 `except yaml.YAMLError: return None`，连 stderr 都没有 → 降级到 Markdown 正文正则提取，操作者无从知晓
- 虽有降级路径设计（`:72-73` 注释），但**降级发生本身不可观测**

### P1-12：F7/F8 两条 FATAL 级禁止项无脚本兜底，且文档承诺了不存在的能力

| 项 | 内容 |
|----|------|
| **文档承诺** | `references/writer-template.md:117` 明确写："审计 Agent 会使用 `contract_check.py` 的 C2/C5/C6/C7/C8/C9 规则和 `term_consistency_check.py` 脚本**逐项检测，命中即阻断**" |
| **实测反证** | `scripts/contract_check.py:56-65` 的 `BANNED_PATTERNS` 共 **7 条**：建议印刷页数 / 图表占位 / 全文完 / HTML标签 / 封面元数据行 / 密级标注 / 输出隔离标记残留。**不含** F7（`^\s*\[[ABCD]\]` 信源分级前缀）与 F8（`\[CM\d{3}\]` claim_id 泄露）的任何检测 |
| **严重性** | F7/F8 在 `writer-template.md:127-128` 均标注 **FATAL** 级 —— 即"最严重、必阻断"的两条，恰恰**没有任何脚本实现** |
| **后果** | 强模型凭 prompt 自律可避免；弱模型泄露 claim_id 或分级前缀时，**审计 Agent 会因信任文档描述而误以为脚本已检查**，双重失守 |
| **风险等级** | **P1**（若考虑"文档谎报能力"这一因素可升 P0） |

### P1-13：`diagram_agent` 废弃残留共 4 处（非 1 处）

除 P1-7 已记的 `multiagent-orchestration.md:26` 外，实测另有：
- `agents/card_synthesizer_agent.md:49`：交接说明仍写"→ `diagram_agent`（架构卡）"
- `references/stage-4-outline.md:51`：仍将 `diagram_agent` 列为"四方唯一共享契约"消费者之一
- `agents/outline_architect_agent.md:3`：description 仍引用 `diagram_agent`
- **且 `agents/diagram_agent.md` 实体文件仍存在** → 弱模型完全可能按编排总纲把它拉起来

### P1-14：orchestrator 自身的判断负荷 57% 依赖语义推理

- **盘点结论**：orchestrator 需执行的判断/动作共 21 项 —— **确定性 9 项（43%）**（正则提取/exit code 读取/JSONL 落盘/阈值计数）、**半确定性 6 项**（§8.5 一致性校验的文本比对边界、污染行识别边界、P0 升级判断、门禁失败路由、档位查表）、**纯经验判断 6 项**（三档模式选择、P0 决策树路径呈现、降级时机、矛盾裁决二次判断、上下文溢出评估、WARNING 是否升级）
- **含义**：跨模型风险不止在被分派的子 Agent —— **orchestrator 本身的模型能力同样是隐性依赖**。单 Agent 极速档下 orchestrator 还会从 Opus 降到 Sonnet，风险叠加

---

## 3. P2 级发现（可选优化）

| # | 发现 | 位置 | 说明 |
|---|------|------|------|
| P2-1 | 降级路径无统一计数与告警 | 全局 | YAML 降级、图表降级、协同档降级各自为政，无统一 telemetry。弱模型下降级频率上升，"静默接受降级"会掩盖系统性劣化 |
| P2-2 | 写作标准 0 的后台泄露检测未脚本化 | `writing-standards.md:11-16` | 该清单是**可枚举的固定习语**（"A级/B级来源"、"证据强度较高"、"经交叉确认"、`[CM021]`、`[A]`-`[D]` 前缀），黑名单代理指标可行；但拦不住新造句式 |
| P2-3 | 标准 20 信息密度未脚本化 | `writing-standards.md:415-420` | 段落长度分布已由 QS4 覆盖（`contract_check.py:137-173`）；"每 300 字 ≥1 数据点"定义精确（数字/百分比/`[N]`），可低成本扩展 |
| P2-4 | 标准 19 读者校准代理指标误报率高 | `writing-standards.md:381` | 全大写缩写正则易误报已登记惯用缩写（NASA 等），需 glossary 白名单配合 |
| P2-5 | 标准 18 过渡"存在性"可校验但"质量"不可 | `writing-standards.md:347` | 正则可 100% 确定格式对错（弱模型主要失分点），但拦不住"写了但空洞" |
| P2-6 | 无 `Agent` 工具时的降级触发条件过窄 | `multiagent-orchestration.md:15`；`SKILL.md:71` | 现写"被作为嵌套子 Agent 拉起时"，未覆盖"宿主环境根本无 Agent 工具概念"的更普遍场景 |
| P2-7 | drawio MCP 为强耦合项 | `SKILL.md:245-248` | MCP 是 Claude 生态协议扩展点；其余外部工具（web-search-skill/paper-search/MinerU/fireworks/mermaid-cli）与全部 Python 脚本**均可移植** |
| P2-8 | Agent `.md` 无法被 pytest 覆盖 | `agents/` | prompt 文本非可执行代码，回归只能靠"新增脚本单测 + 端到端冒烟 + 改造前后产出物 diff" |
| P2-9 | `dashboard.md` Dim8 实测分数不可信 | `dashboard.md` | 既有已知遗留（全程 dry_run），跨模型改造后更应重跑 |

---

## 4. 确定性脚本覆盖 vs 纯 prompt 自律的边界盘点

这是本次审计的核心交付之一——**明确哪些质量维度对模型能力不敏感，哪些高度敏感**。

### 4.1 已有脚本兜底（跨模型可移植，能力不敏感）

| 质量维度 | 兜底脚本 | 备注 |
|---------|---------|------|
| 合约 C1-C9（H1/手动编号/图片语法/表格题注/禁止内容/引用格式/SRC残留/字数残留/局部参考文献） | `contract_check.py` | 有 `--json` + exit code 0/1/2 + `--stage{stage7,stage9}` 分级 |
| 量化 QS1-QS4（字数/图数/表数/段落分布） | `contract_check.py:137-173` | **标准 20 段落长度已完全脚本化** |
| 图表文件存在性 | `figure_gate.py` | FATAL 阻断，零人工干预 |
| 术语一致性（F10/标准 22） | `term_consistency_check.py` | 依赖 glossary.md YAML（见 P1-9） |
| 卡片-正文重合度 | `card_overlap_check.py` | 46字/2处阈值，脚本裁决 + 审计判读 |
| 强表述核验 | `claim_strength_check.py` | 对照 claims-ledger.csv |
| 图表 DPI/配色/注册表 | `chart_checks.py` | — |
| 跨文件常量联动 | `check_linkage_constants.py` | — |

### 4.2 纯 prompt 自律（跨模型高敏感，无兜底）

| 质量维度 | 现状 | 可脚本化性 |
|---------|------|-----------|
| 输出隔离标记存在性/配对 | orchestrator 正则心算 | **完全可**（布尔可判定，S） |
| 噪声比率 >30% | orchestrator 目测 | **完全可**（需精确字符集，S） |
| Phase A/B 承诺一致性 | 模型自查自 | **部分可**（需先落盘；有天花板，M） |
| §8.5 标题提取与一致性校验 | orchestrator prompt 级 | **完全可**（复用现有函数，S） |
| Writer/Auditor 结构化产出合法性 | 无校验 | **完全可**（jsonschema，M） |
| outline.md YAML 结构合法性 | 三种冲突行为 | **完全可**（M） |
| 写作标准 0（前台/后台分离） | 模型语义判断 | **仅黑名单代理**（拦已知，拦不住新句式） |
| 写作标准 19（读者校准） | 模型语义判断 | **仅代理指标**（误报率高，需白名单） |
| 写作标准 18（过渡质量） | 模型语义判断 | **仅存在性可校验** |
| 章节论证质量、红队风险判断、审计评分 | 模型语义判断 | **本质不可脚本化** |
| 阶段 9：红队处理确认、全文通读 | 模型/人工 | **结构性不可脚本化** |

### 4.3 资产规模基线（实测）

| 资产 | 规模 |
|------|------|
| `agents/` 12 个 .md（含 1 个已废弃） | 957 行 / 73,885 字符 / 约 44,300 tokens【估算】 |
| `references/` 22 个 .md | 4,062 行 / 281,530 字符 |
| 规模最大单文件 | `writing-standards.md` 544 行 / 37,955 字符 |
| 规则密度 TOP2 | `chapter_writer_agent.md`（194 行）、`chapter_auditor_agent.md`（159 行）——亦是**仅有的两个双 Phase 角色** |
| `scripts/` 主脚本 | 9 个 + 1 个 shim |

> **关键观察**：规则密度最高的两个角色，恰好也是唯一采用"盲态预承诺 + 明态执行"双 Phase 结构的角色。**对模型自我约束能力的依赖在此处双重叠加**——既要同时追踪最多约束，又要跨两次调用维持承诺一致性。这是跨模型迁移风险的最集中点。

### 4.4 结论

**脚本化的天花板明确**：能拦已知模式，拦不住新坑。**因此弱模型档不能靠脚本"替代"审计 Agent，只能靠脚本"减轻"审计 Agent 的负担、并把可机械判定的部分彻底移出模型判断范围。** 语义质量判断这一层，无论哪个模型档位都必须保留独立审计角色（或人在环）。

---

## 5. 跨模型一致性风险总表

| 风险点 | 强模型（Claude）表现 | 弱模型（DeepSeek V3.2 级）预期表现 |
|--------|---------------------|-----------------------------------|
| 30 条并列约束 | 大部分遵守 | 遵从率推算 ≈2.5%，近乎必然违规 |
| Phase A 104 字段 | 可完整产出 | **输出截断 → Phase 中止** |
| 固定分隔符 | 稳定遵守 | 内容污染 → 提取失败 |
| JSON/YAML 生成 | 高合法率 | 结构坍塌无兜底 |
| 文档间矛盾（角色数/标准数/红队格式/废弃角色） | 自行消解 | 行为不可预测 |
| 盲态预承诺 | 机制有效 | 退化为走过场 |
| 异构红队 | 真实视角差异 | 同质化回归 |
| thinking + 工具调用 | 可并用 | **官方互斥**，需拆两步 |
| orchestrator 经验判断（噪声/降级/裁决） | 可靠 | 显著劣化 |

---

## 6. 非 Claude 宿主的架构边界

| 依赖项 | 耦合性质 | 结论 |
|--------|---------|------|
| `Agent` 工具 depth-1 委派 | **强耦合（生态锁定）** | DeepSeek/GLM 无原生等价物；Cline 无多 Agent 子调用、OpenHands delegate 语义不同、LangGraph 需外部框架重建。**不可解，只能降级** |
| drawio MCP | **强耦合** | MCP 为 Claude 生态协议；可降级 Mermaid（`SKILL.md:247` 已列为备选） |
| web-search-skill / paper-search / MinerU / fireworks-tech-graph / mermaid-cli | 可替换 | 均为独立 CLI/脚本，宿主无关 |
| 全部 `scripts/*.py` | **完全可移植** | 纯 Python + 命令行，只要宿主能执行 shell |

**含义**：多 Agent 协同（阶段 7 写审对抗、阶段 8 四人格红队）应明确定位为 **Claude Code 特化增强**；在其他宿主上默认预期走单 Agent 极速档（V3 自查）。不应承诺"多 Agent 协同在非 Claude 宿主等价可用"。

---

## 7. 审计盲区与不确定项

1. **DeepSeek V4 正式规格未定**：预览数据（1M/384K）未经官方正式文档确认，本报告一律以 V3.2 为基准。若 V4 正式发布且规格属实，P0-1（输出上限冲突）严重度可下调
2. **GLM-4.6 / Qwen3 / Kimi K2 的 IFEval 数据缺失**：BFCL 数据（78%/72%/71%）为 C 级，未单独核验
3. **GPT-5 / Gemini 3 / MiniMax 公开数据极少**：标注 D 级，不作设计依据
4. **"Curse of Instructions" 论文未逐一核验 DOI**：乘法衰减规律为 B 级结论，2.5% 为**理论推算值非实测值**——实际衰减可能因规则相关性而缓于纯乘法
5. **未做真实 DeepSeek 端到端跑测**：本审计基于规格文档 + 代码静态分析 + 局部实测（Python 层），**未在 DeepSeek 上实跑完整 9 阶段**。所有"弱模型预期表现"为推断，需改造后实测验证
6. **规则条数存在两种口径**：编排器精确口径（仅计"必须/禁止/不得/MUST NOT/强制/红线"）得 `chapter_writer_agent` **30 处**；资产盘点粗口径（额外计入 F/D/C 编号与"标准N"引用）得 **57 处**。两者均指向同一结论（远超 ≤5 条建议上限），但**具体数值取决于统计口径，不应作为精确指标引用**
7. **"可脚本化比例"为判断性结论而非客观测量**：资产盘点给出"写作标准 23 条中 15 条不可脚本化（约 65%）"、"审计契约 24 维度中约 14 个无脚本兜底（约 70%）"。这类分类依赖对"可脚本化"的定义边界（如"半可脚本化"归入哪侧），属专业判断，引用时应保留区间感而非当作精确统计

---

## 8. 发现清单汇总

| 编号 | 级别 | 标题 | 主要位置 |
|------|------|------|---------|
| P0-1 | P0 | Auditor Phase A 104 字段超出 8K 输出上限 | `chapter_auditor_agent.md:122-132` |
| P0-2 | P0 | outline_reader subsections 字段名不匹配（实测 100% 丢失 + telemetry 反向误导） | `outline_reader.py:149-150,215` |
| P0-3 | P0 | 三处 SSOT 消费者失败语义冲突 + FATAL 标签不阻断 + 无 stderr 消费者 | `merge_drafts.py:56-63`/`builder.py:210-219`/`figure_gate.py:65-66` |
| P0-4 | P0 | 两个 Agent 合约 JSON 无 schema 校验 | `agents/contracts/*.json` |
| P0-5 | P0 | Writer 30 处并列约束超弱模型追踪上限 | `chapter_writer_agent.md` |
| P0-6 | P0 | 固定分隔符输出契约易污染 | `multiagent-orchestration.md:33-52` |
| P0-7 | P0 | 噪声比率检测无脚本 | `multiagent-orchestration.md:48` |
| P1-1 | P1 | 盲态预承诺为模型自查自，Phase A 未落盘 | `chapter_auditor_agent.md:150,155` |
| P1-2 | P1 | finalizer_agent 档位错配（Haiku 承担最长链） | `finalizer_agent.md:4,30-49` |
| P1-3 | P1 | source_collector_agent 档位错配 | `source_collector_agent.md:4,34-45` |
| P1-4 | P1 | 红队异构模型前提在单模型宿主失效 | `redteam_agent.md:17-26` |
| P1-5 | P1 | 红队输出格式 JSON/Markdown 不一致 | `workflow-stage8.md:46` vs `redteam_agent.md:77-84` |
| P1-6 | P1 | 写作标准数量四处不一致（实际 0-22） | `writing-standards.md` / `SKILL.md:232` / `README.md:89` |
| P1-7 | P1 | 角色数量三处不一致 + 废弃角色残留 | `multiagent-orchestration.md:26` vs `SKILL.md:59` |
| P1-8 | P1 | §8.5 标题提取无脚本支撑 | `multiagent-orchestration.md:87-96` |
| P1-9 | P1 | glossary.md 为第二处 YAML SSOT 风险 | `glossary.md:13-23` |
| P1-10 | P1 | 阶段 9 两项结构性不可脚本化无兜底 | `stage-9-finalize.md:25-26` |
| P1-11 | P1 | figure_gate YAML 失败完全静默 | `figure_gate.py:63-66` |
| P1-12 | P1 | F7/F8 两条 FATAL 项无脚本兜底，文档承诺不存在的能力 | `contract_check.py:56-65` vs `writer-template.md:117,127-128` |
| P1-13 | P1 | `diagram_agent` 废弃残留共 4 处 + 实体文件仍在 | `card_synthesizer_agent.md:49`/`stage-4-outline.md:51`/`outline_architect_agent.md:3`/`multiagent-orchestration.md:26` |
| P1-14 | P1 | orchestrator 自身 57% 判断依赖语义推理 | 全局盘点（21 项判断） |
| P2-1~9 | P2 | 见 §3 表 | — |

**发现总计更新**：**30 项**（P0×7 / P1×14 / P2×9）

---

> **本报告只做问题诊断，不含实施方案。** 对应的优化方案见 `design/model-compatibility-optimization-plan.md`。
