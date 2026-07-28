# 可移植性边界声明（PORTABILITY）

> 本文件回答一个问题：**离开 Claude（Claude Code / Claude 系 Agent 工具），本 skill 还能剩下多少？**
> 供非 Claude 宿主（DeepSeek V3.2 / GLM-4.6 / Qwen3 等，通过 `model-profile.json` 声明能力档）的用户与集成者阅读。
> 机读版见 [`portability-manifest.json`](portability-manifest.json)（CI 用其做覆盖率校验，两者手工保持同步）。

---

## 1. 三档分类定义

| 分类 | 含义 |
|------|------|
| **core** | 与具体 LLM 厂商无关的方法论/流程/契约/脚本。任何支持 Agent Skills 标准（读取 Markdown 指令 + 调用工具）的运行时都可以执行。不依赖 `Agent` 工具委派、不依赖 Claude 专有 MCP。 |
| **claude-enhanced** | 在 Claude 下有增强表现（多 Agent 协同、异构模型防同质化等），但**并非硬依赖**——降级路径明确，非 Claude 宿主可退化执行（通常回退为单 Agent 直接完成同一职责，质量打折但不中断流程）。 |
| **claude-only** | 依赖 Claude 特有能力（`Agent` 工具 depth-1 委派等），非 Claude 宿主上**该能力本身不可用**，只能整体降级为其他档位的等价流程，没有"打折但仍在同一形态下运行"的中间态。 |

> **重要说明——"文件"与"文件里的方法论"是两个不同的判断对象**：`agents/*.md` 每个文件本身是"一段被 `Agent` 工具调度执行的 prompt"，这件事的**调度方式**在非 Claude 单 Agent 宿主上必然不同（不能再用 `Agent` 工具分派）。但 prompt **内容**里描述的方法论、检查清单、维度定义绝大多数是模型无关的。本文件的 `portability` 标注遵循以下裁决原则：
> - 若文件内容的**核心价值**在于"作为独立 Agent 被调度"这件事本身（如红队 4 人格异构并行、写审对抗 pipeline 的物理隔离机制）→ 标 `claude-only` 或 `claude-enhanced`。
> - 若文件内容是**可被任何执行者（单 Agent 或多 Agent）套用的方法论/清单/模板**，"被 `Agent` 工具调度"只是当前实现选择的调用方式而非内容本身要求 → 标 `core`。
> - 非 Claude 宿主下，`claude-only`/`claude-enhanced` 标注的 Agent 文件**内容本身仍可读**——单 Agent 极速档 orchestrator 会直接阅读这些文件中的方法论/清单部分自行执行对应检查，只是不再把它们作为独立 Agent 调度。

## 2. 边界划分表（方案原文）

| 能力 | 分类 |
|------|------|
| 9 阶段方法论、写作标准、红队清单、格式规范 | **core** |
| 全部 `scripts/*.py`（含新增）、`md2docx` 转换器 | **core** |
| 契约 JSON / 机读 schema / 填空骨架 / 红线集 / 信封契约 | **core** |
| `Agent` 工具 depth-1 委派、写审对抗 pipeline、红队 4 人格并行 | **claude-only** |
| drawio MCP 出图 | **core**（DeepSeek V4 级模型经端到端实测可用；仅无 MCP 宿主降级 Mermaid） |
| 三档模式中的"完整/分层"档 | **claude-only** |
| 单 Agent 极速档 | **core** |

## 3. `agents/*.md` 逐文件分类与理由

| 文件 | portability | 理由 |
|------|-------------|------|
| `source_collector_agent.md` | core | 搜集/下载/抽取/索引是机械工具调用型清单，任何执行者均可直接套用 |
| `fact_verifier_agent.md` | core | 核验台账方法论与状态分流规则是模型无关的方法论核心，方法论价值不依赖被独立调度 |
| `outline_architect_agent.md` | core | 大纲叙事框架契约的产出规则是通用方法论；单 Agent 档下 orchestrator 直接套用同一套规则产出 outline.md |
| `card_synthesizer_agent.md` | core | 卡片模板与转写规则是固定结构化方法论，与调度方式无关 |
| `data_chart_agent.md` | core | matplotlib 出图规则/质量约束是工具链方法论，非 Claude 专有能力 |
| `chapter_writer_agent.md` | core | 已有标注（第 6-8 批已定），写作四铁律/标准 0-22 是方法论核心 |
| `chapter_auditor_agent.md` | core | 已有标注，量化维度调脚本、审计矩阵是方法论 + 脚本组合，模型无关 |
| `redteam_synthesizer_agent.md` | core | 合并去重/严重度取最高/统一编号是纯结构化整合规则，单 Agent 档下可由 orchestrator 直接执行 |
| `architecture_chart_agent.md` | core | 核心方法论（图表规划、色板约束、质量门禁）是通用方法论。drawio MCP 经 DeepSeek V4 Pro 2026-07-29 端到端实测可用（Mermaid flowchart/C4Context/手写XML+ELK/libavoid/search_shapes 四层测试全部零错误通过），已从 claude-enhanced 提升为 core。仅无 MCP 能力的宿主需降级 Mermaid |
| `redteam_agent.md` | claude-enhanced | 4 人格异构模型（2×Opus+2×Sonnet）防同质化是 Claude 多模型调用能力的增强效果；tier B/C 下按 D2 改造退化为同模型+人格 prompt 差异化+顺序轮换，仍可运行但效力下降（非硬失效），故标 `claude-enhanced` 而非 `claude-only` |
| `finalizer_agent.md` | （由并行 D5/D6 任务标注，本批不改） | 属于另一并行任务范围，避免冲突未触碰 |

> **口径与 §42 条目的差异说明**：方案 #42 条目列出的 6 个文件（`architecture_chart_agent`/`data_chart_agent`/`fact_verifier_agent`/`redteam_agent`/`redteam_synthesizer_agent`/`source_collector_agent`）是该条目原文强调"还需要加红线节"的文件子集，不是"哪些文件需要 portability 字段"的范围声明。D4 的总要求是**全部** `agents/*.md` 都要有 `portability` 字段（红线节是可选的独立增强项，不在本批任务范围内，仅本次要求的 `portability` 字段已按此口径覆盖全部 11 个文件，含未出现在 #42 条目中的 `card_synthesizer_agent`/`outline_architect_agent`）。

## 4. `references/*.md` 分类

除编排类文件外，`references/*.md` 绝大多数是方法论/清单/模板文档，模型无关，标 `core`：

| 文件 | portability |
|------|-------------|
| `stage-1-init.md` ~ `stage-8-review.md`（不含 stage-9，见下方说明） | core |
| `appendix-converter-contract.md` / `appendix-report-types.md` | core |
| `architecture-analysis-guide.md` | core |
| `glossary.md` | core |
| `md-to-docx-pitfalls.md` / `writing-process-pitfalls.md` | core |
| `red-team-checklist.md` | core |
| `writer-template.md` / `writing-standards.md` | core |
| `研究报告格式规范.md` | core |
| `multiagent-orchestration.md` | **claude-only** —— 编排总纲本身描述的正是 depth-1 委派 + 4 人格并行 fan-out 等 Claude 专有编排机制，内容主体就是"如何用 `Agent` 工具编排"，非 Claude 宿主下这份文件描述的编排方式整体不适用（需回退单 Agent 极速档） |
| `workflow-stage7.md` | **claude-only** —— 写审对抗 pipeline 的编排脚本，依赖 `Agent` 工具分派 writer/auditor 两个独立 Agent |
| `workflow-stage8.md` | **claude-only** —— 红队 4 人格并行 fan-out 编排脚本，依赖 `Agent` 工具并行分派 |

> **`stage-9-finalize.md` 未加 portability 字段**：该文件属于并行任务"第9批-B PhaseE+D5+D6脚本"的改动范围（该任务负责 `agents/finalizer_agent.md` 与 `references/stage-9-finalize.md`），本批为避免冲突未触碰，留给该任务或后续批次统一补齐。

## 5. 诚实结论——非 Claude 宿主上会退化成什么

**非 Claude 宿主上，本 skill 退化为「单 Agent 极速档 + 全套确定性脚本 + drawio MCP（DeepSeek V4 级模型已实测可用）」**：

- 不再有 `chapter_writer_agent` + `chapter_auditor_agent` 的物理隔离写审对抗（R3 死结的解无法复现——单一模型自评自查，"看了稿再放宽标准"的风险重新出现，只是被脚本层的量化检查部分对冲）。
- 不再有红队 4 人格异构模型并行（tier B/C 下按 D2 改造退化为同模型 + 人格 prompt 差异化 + 审查顺序轮换，同质化盲点风险部分回归）。
- 三档协同模式收窄为只剩"单 Agent 极速"一档可用（完整/分层多 Agent 档要求的 `Agent` 工具委派不可用）。

**但这不等于"退回到什么都没有"**：本方案把大量原本依赖审计 Agent 语义判断的检查**下沉到脚本层**（`contract_check.py`/`claim_strength_check.py`/`card_overlap_check.py`/`term_consistency_check.py`/`figure_gate.py` 等），这些脚本是纯 Python 确定性工具，与调用它们的模型无关。因此：

> **非 Claude 宿主的单 Agent 极速档，质量高于本 skill 历史版本（改造前）的单 Agent 极速档**——历史版本的极速档几乎全靠模型自律（V3 CHECKPOINT/STATS/REPORT 自查），现在的极速档在自律之外多了一层脚本化的确定性校验网。这是"打折"而非"清零"。

## 6. 降级触发机制（与代码对齐）

降级判据是**声明式**而非**运行时探测**：`model-profile.json` 的 `host.agent_delegation` 字段为 `false` 时，`scripts/model_profile.py::resolve_collaboration_mode` 强制返回单 Agent 极速档（硬规则 2），与 `references/multiagent-orchestration.md` §1/§7.5 的文字描述一致。不依赖"检测当前是否被作为嵌套子 Agent 拉起"这类运行时探测——探测本身在无 `Agent` 工具概念的宿主上并不可靠。
