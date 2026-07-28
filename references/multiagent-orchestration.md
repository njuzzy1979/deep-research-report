---
portability: claude-only
---

# 多 Agent 协同编排总纲

> 本文件是 deep-research-report skill 多 Agent 协同的编排总纲，落盘 v4 §2/§6/§7 的编排机制。
> 供 `report_orchestrator`（主对话采用的剧本）执行。复用 UEAS（通用工程 Agent 体系）已验证机制。
> 母文件：`../SKILL.md` §多 Agent 协同执行体系

---

## 1. 编排底座：depth-1 委派

`report_orchestrator` **不是一个被拉起的子 Agent，而是主对话亲自采用的编排剧本**。主对话用 `Agent` 工具逐个分派工作型子 Agent（写作/审计/红队等），委托链恒为 **depth-1**（主对话 → 工作 Agent）。工作型子 Agent **不持有 `Agent` 工具**，确保委托链不嵌套。

- ✅ **正确激活**：用户在主对话说"用 deep-research-report 写一份关于 XX 的报告"，主对话读 SKILL.md、采用编排剧本、开始分派。
- ❌ **禁止**：把本 skill 通过 `Agent` 工具作为嵌套子 Agent 拉起——此时无法再向下分派。
- **降级兜底**：触发条件是**检测不到 `Agent` 工具**（而非"被作为嵌套子 Agent 拉起"这一运行时场景本身——两者常同时成立，但判据是能力探测，不是调用形式），由 `model-profile.json` 的 `host.agent_delegation: false` 显式声明（`scripts/model_profile.py::resolve_collaboration_mode` 硬规则 2），而非运行时嗅探。声明为 `false` 时**自动降级为单 Agent 极速档**，标注"多 Agent 协同不可用，已降级为 V3 单 Agent 模式"。

## 2. 11 角色（口径：`agents/` 下实际存在的 Agent 定义文件数，不含 orchestrator——orchestrator 是主对话采用的编排剧本，由本文件定义，不落地为 `agents/` 下的文件；已废弃的 `diagram_agent` 移入 `agents/deprecated/` 后不计入）× 阶段 × 模型 × 编排模式

| 阶段 | 主责角色 | 编排模式 | 模型 | CHECKPOINT | 门禁 |
|------|---------|---------|------|:---:|:---:|
| 1 初始化 | orchestrator（主对话直接做） | 单体 | Opus | CP1 参数 / CP2 封面 | — |
| 2 搜集抽取 | `source_collector_agent` | 单 Agent 分派 | Haiku | — | G(收集) |
| 3 事实核验 | `fact_verifier_agent` | 单 Agent 分派 | Opus | — | G(核验) |
| 4 详细大纲 | `outline_architect_agent` | 单 Agent 分派 | Opus | **CP3 大纲确认** | G(大纲) |
| 5 专题卡片 | `card_synthesizer_agent` | 单 Agent 分派 | Sonnet | — | G(卡片) |
| 6 核心架构图 | `architecture_chart_agent` | 单 Agent 分派（多图可 parallel） | Sonnet | — | G(出图) |
| **7 分章写作** | `chapter_writer` + `chapter_auditor` | **pipeline + loop-until-pass** | Sonnet + Opus | CP4 逐章汇总 | **G7-write** |
| **8 红队审查** | `redteam ×4` + `redteam_synthesizer` | **parallel fan-out + gather** | 2Opus+2Sonnet + Sonnet | **CP5 风险处理** | **G8-redteam** |
| 9 定稿整合 | `finalizer_agent` | 单 Agent 分派 | Haiku | CP6 交付清单 | G(交付) |

> **为什么只有阶段 7/8 用 Workflow**：其余阶段是"一个专业角色干一件相对独立的事"，单次分派 + 收集即可。只有阶段 7（写审对抗解开 R3）和阶段 8（红队多视角）需要生成-评估对抗或并行 fan-out。这与 UEAS"渐进式复杂度"一致——协同成本花在刀刃（写作质量 + 对抗审查）上。

## 3. 输出隔离契约（强制，防 Windows GBK 乱码/进度条污染）

所有子 Agent 的产出**一律包裹**在标记行之间（复用 UEAS 输出隔离契约，对应本项目 CLAUDE.md 反复强调的 Windows 中文环境编码踩坑）：

```
[AGENT-OUTPUT-START] <agent名称>
<有效产出内容>
[AGENT-OUTPUT-END] <agent名称>
```

> **nonce（可选后缀）**：`model-profile.json` 的 `policy.envelope_nonce` 为 true 的能力档（tier B/C）下，orchestrator 在分派 prompt 中附带一个十六进制 nonce（如 `a7f3c9d2`），要求该 Agent 原样接到标记后面（`[AGENT-OUTPUT-START:a7f3c9d2]`）。Claude（tier A，`envelope_nonce=false`）默认不启用，继续沿用不带 nonce 的旧格式——两种格式提取正则均能正确处理。nonce 未被照抄不阻断，降级为无 nonce 匹配并写台账。

分派子 Agent 时必须在 prompt 中写明此契约。

## 4. 噪声检测与重试（收集每个子 Agent 输出时执行）

1. **提取有效内容**：用正则 `\[AGENT-OUTPUT-(START|END)(?::[0-9a-f]{6,16})?\]([\s\S]*?)\[AGENT-OUTPUT-(START|END)(?::[0-9a-f]{6,16})?\]` 提取（同时接受带 nonce 与不带 nonce 两种标记形式）。无匹配 → FAILED → 重试。
2. **噪声比率检测**：污染行（GBK 乱码 + 进度条字符 `▕ █ %`）> 30% → CONTAMINATED → 重试（最多 2 次）。
3. **超时保护**：单 Agent > 15 分钟 → 终止重试；仍超时 → P0 停流水线。
4. **关键路径**：`chapter_auditor_agent`（G7）和 `redteam_agent`（G8）若输出污染/超时，必须重试满 2 次才放弃。其他 Agent 最多允许跳过 1 个。

> **Windows 编码专项**：审计 Agent 调 `scripts/*.py` 跑统计时，脚本已统一 `sys.stdout.reconfigure(encoding='utf-8')` + ASCII 替代符号（无 emoji），避免 GBK 控制台崩溃。orchestrator 提取输出时用输出隔离标记过滤污染行。

## 5. 门禁体系（复用 UEAS G0-G8 语义）

| report 门禁 | 语义 | 负责角色 | 失败路由 |
|------------|------|---------|---------|
| G(大纲) | 大纲契约确认 | orchestrator + 用户(CP3) | 回阶段 4 |
| **G7-write** | 每章通过独立审计 | `chapter_auditor` | REVISE 回 writer，2 轮不过记 P0 |
| **G8-redteam** | 高风险清零/中风险≥80% | `redteam_synthesizer` + 用户(CP5) | 回 writer 修订 |
| G(交付) | 12 项交付清单 | `finalizer` + 用户(CP6) | 对症回对应阶段 |

## 6. 问题分级（复用 UEAS P0-P3）

- **P0**：阻断后续任务依赖链（如某章 2 轮审计仍不过、红队高风险无法清零）→ 停，呈用户决策。
- **P1/P2**：局部问题，Agent 顺手修复，orchestrator 记录。
- **P3**：模糊处/无法自动验证项 → 记录，阶段边界呈用户。

## 7. 三档协同模式与模型联动

> **三档协同模式的定义（触发条件、写作/红队策略、Agent 调用量级）以** `../SKILL.md` **"三档协同模式"表为唯一权威来源**。下表仅列出各档位下的角色-模型映射（编排层面的派生信息），不重复定义模式本身。

| 协同档位 | chapter_writer | chapter_auditor | redteam | orchestrator |
|---------|----------------|-----------------|---------|--------------|
| 完整多 Agent | Sonnet | Opus | 2×Opus+2×Sonnet | Opus |
| 分层多 Agent（默认） | Sonnet | Opus（仅核心章） | 2×Opus+2×Sonnet | Opus |
| 单 Agent 极速 | Sonnet（orchestrator 自写） | 不启用（回退 V3 自查） | 不启用（回退 V3 压缩 3 维度） | Sonnet（整体降档） |

> **超大报告红队降级（阶段 8 额外降级路径）**：当报告正文超过 50,000 中文字或章节数超过 8 章时，全报告注入可能超出 Agent 上下文窗口安全边界。此时 4 人格红队可从"全报告并行"降级为"按章节组分批（2-3 组），再跨组交叉"——每组内 4 人格仍并行审查，分组间的一致性矛盾可能漏检（代价声明）。核心结论章不允许被拆分到不同组（红线）。此降级独立于三档协同模式——即使"完整多 Agent"档也适用。详见 `references/workflow-stage8.md` 超大报告降级分支。

> **降级不是"没有质量控制"**：单 Agent 极速档采用 V3 的 CHECKPOINT/STATS/REPORT 单 Agent 自律机制，V3 的价值在极速档完全保留。**关键**：单 Agent 档 orchestrator 自身也从 Opus 降到 Sonnet——此时它承担"直接写一份简报"而非"跨 9 阶段全局裁决"，认知负荷类型变了。回退兜底：模型不可用时按 Haiku→Sonnet→Opus 单向就高兜底。

## 7.5 二维决策矩阵：模型能力档 × 报告规模档（跨模型兼容性优化方案 §C2）

上面 §7 的"三档协同模式"由**报告规模/类型**决定；`model-profile.json` 声明的**模型能力档**（tier A/B/C，见 `scripts/model_profile.py`）是**正交的第二维**——两者不互相覆盖，只有一个例外（见下表 Tier C × 完整多 Agent）。

| | **完整多 Agent** | **分层多 Agent**（默认） | **单 Agent 极速** |
|---|---|---|---|
| **Tier A**<br>(Claude Opus/Sonnet) | **现状完全不变**。红线不限、Phase A 自由生成 24 维度、nonce 可选、无填空骨架 | **现状不变** | **现状不变** |
| **Tier B**<br>(DeepSeek V3.2 / GLM-4.6 / Qwen3 等) | 红线 ≤5；Phase A 确认式；强制 nonce；填空骨架 on；4 个新脚本全开 | 同左，仅核心章走对抗；非核心章 orchestrator 直写 + 全套脚本校验 | 红线 ≤5；填空骨架 on；语义自查压缩 3 项，其余交脚本 |
| **Tier C**<br>(未知模型兜底) | **不允许**——自动降为"分层多 Agent"并写台账（理由：完整档成本放大 3-5 倍 + 未知模型 = 高失败风险叠加） | 同 Tier B 分层多 Agent 档 | 同 Tier B 单 Agent 极速档 |

**正交性说明**：能力档影响**每次调用的 prompt 构造方式与输出切分粒度**（红线条数、Phase A 书写形态、是否强制 nonce、是否用填空骨架）；规模档影响**调用哪些 Agent、调用几次**（完整/分层/极速三档见 §7 上表）。两者独立生效，唯一硬性覆盖规则是 `Tier C × 完整多 Agent` 强制降级。

**硬规则的代码实现**：`scripts/model_profile.py` 的 `resolve_collaboration_mode(profile, requested_mode)` 返回 `(实际生效模式, 降级原因|None)`，落地两条硬规则：
1. `capability_tier == "C"` 且请求档位为"完整多 Agent" → 强制降为"分层多 Agent" + 写台账。
2. `host.agent_delegation == false`（无 depth-1 委派底座）→ 强制降为"单 Agent 极速"，与本文件 §1"降级兜底"一致。

模式命名（"完整多 Agent"/"分层多 Agent"/"单 Agent 极速"）与 `SKILL.md` §三档协同模式表、本文件 §7 上表严格一致，代码中的字符串常量与文档措辞同步维护。

> **⚠️ 风险标注**：`Tier B × 完整多 Agent` **未经实测**。建议首个真实项目先跑分层多 Agent 档，验证通过后再尝试完整档。

## 8. 门禁快照落盘（防长会话丢失，UEAS 习惯）

每个门禁步骤把快照 append 落盘（JSONL，append-only）到进度文档，不依赖会话记忆。阶段 7 逐章审计报告落 `research/chapter-reports/`，阶段 8 统一风险清单落 `research/redteam-risklist.md`。

## 8.5 Writer 注入时的标题提取规则（确定性要求）

在阶段 7 为 `chapter_writer_agent` 注入"当前章大纲条目"时，orchestrator **必须**从 `outline.md` 的 YAML front matter 中提取标题文本，而非从 Markdown 正文 heading 行解析。具体规则：

1. **标题文本来源**：从 `structure.bodymatter[*].sections[*].section_title` 字段取纯文字标题。`section_no` 是编号元数据，**不注入**到 Writer prompt 的标题文本中
2. **注入格式**：向 Writer 注入时，标题文本以纯文字形式呈现（如"军事需求分析"），不附带任何编号前缀（不写"1.1 军事需求分析"）
3. **Markdown heading 中的编号**：`outline.md` 的 Markdown 正文 heading 可以带编号供人阅读（如 `### 1.1 军事需求分析`），但 orchestrator **不得**从 heading 行解析标题——必须以 YAML `section_title` 为准。这是防止"编号写入标题"的三重防线中的第一道
4. **YAML-Markdown 一致性校验**：如果 YAML `section_title` 的值与 Markdown heading 去掉编号前缀后的文本不一致，orchestrator 应标记该不一致并提示大纲架构师修正（说明 YAML 或 Markdown 有一方未同步更新）

> **设计理由**：SCIF 项目中 Part 2/6 的 H3 被 Writer 降级为 H4，根因是大纲 YAML 的 section 标题带编号前缀"1.1"，Writer 将编号当标题文字消费后触发了错误的层级判断。这条确定性规则从 orchestrator 注入层面切断编号污染路径——Writer 看到的标题永远是纯文字，无从污染。

## 9. 已知限制（继承 v4 §9）

- **depth-1 天花板**：`Agent` 工具只支持主对话→工作 Agent 单层委派。
- **成本放大 3-5 倍**：完整档阶段 7 每章 = 写作 + 审计预承诺 + 审计打分 + 最多 2 轮回炉。这是三档降级的根本原因。
- **无 Hook 级强制**：所有 Agent 边界与预承诺纪律都是 prompt-level，无确定性 PreToolUse hook 拦截。但"不同 Agent + 盲态预承诺 + 真脚本量化"相比 V3"同一 Agent 自查"已是数量级改善——把"靠自律"变成"靠结构 + 大幅提高作弊成本"。
- **Agent 上下文窗口溢出风险**：在长章场景（单章 >15,000 中文字，约 20 页）下，Writer（Sonnet, 200K）和 Auditor（Opus, 200K）的输入量可能接近安全边界。缓解措施见 `agents/chapter_writer_agent.md` "上下文预算提醒"节。对于 >25K 字的章，建议在阶段 4 大纲拆分时规划为子章。

## 10. P0 死锁处理决策树（写审对抗 2 轮上限后）

当 writer+auditor loop 在 `max_rounds=2` 后仍未通过审计时，系统记 P0 并呈用户决策。以下 3 条路径供用户选择，orchestrator 必须逐条展示：

### 路径 A：手动改稿 → 重新审计

**触发条件**：用户愿意且有能力手动修订该章草稿。

**操作**：
1. 用户基于 auditor 的 issue 清单手动编辑 `research/drafts/chXX-*.md`
2. Orchestrator 对该章重新发起审计（1 轮，不复用旧审计报告）
3. 若通过 → 正常继续；若仍 REVISE → 回到本决策树

**适用**：内容质量临界通过、仅少数 issue 难以通过 prompt 修复。

### 路径 B：降级为 WARN → 标注后继续

**触发条件**：触发 block 的维度为 mid/low 严重度（非 C1/C2/C5 红线），且内容实质性正确。

**操作**：
1. Orchestrator 记录降级决定：哪个维度、哪个 issue、降级原因
2. 在最终报告的"红队风险清单"中添加 WARN 项：`[P0-降级] 第X章 <维度名> 审计未通过，降级为 WARN，原因：<用户填写>`
3. 该章标记为 PASS-WARN，继续流程

**适用**：段落过渡缺失、篇幅超标等结构性但非事实性缺陷。

### 路径 C：跳过本章 → 标记风险后继续

**触发条件**：本章内容对报告主线非关键（如"背景介绍"章），且当前时间/成本不允许继续投入。

**操作**：
1. 在 final-report.md 的该章位置插入风险提示：`> ⚠️ 本章因写审对抗 2 轮未通过，按用户决策跳过。内容未经完整审计，可能存在事实偏差或论证缺陷。`
2. 在目录中该章标题后标注"（未完成审计）"
3. 红队风险清单中记录 HIGH 风险项
4. 后续章正常继续

**适用**：极强的成本/时间约束，且本章可接受风险。

### 禁止的操作

- ❌ **不得默认放行**：无论如何不能将 REVISE 静默改为 PASS
- ❌ **不得自动选择路径**：P0 必须呈用户，由用户从 3 条路径中选择
- ❌ **C1/C2/C5 红线不走 B 路径**：合约层高严重度失败（密级、标题编号、H1）必须走路径 A 或 C，不得降级为 WARN
