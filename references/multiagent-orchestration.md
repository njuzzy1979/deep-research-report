# 多 Agent 协同编排总纲

> 本文件是 deep-research-report skill 多 Agent 协同的编排总纲，落盘 v4 §2/§6/§7 的编排机制。
> 供 `report_orchestrator`（主对话采用的剧本）执行。复用 UEAS（通用工程 Agent 体系）已验证机制。
> 母文件：`../SKILL.md` §多 Agent 协同执行体系

---

## 1. 编排底座：depth-1 委派

`report_orchestrator` **不是一个被拉起的子 Agent，而是主对话亲自采用的编排剧本**。主对话用 `Agent` 工具逐个分派工作型子 Agent（写作/审计/红队等），委托链恒为 **depth-1**（主对话 → 工作 Agent）。工作型子 Agent **不持有 `Agent` 工具**，确保委托链不嵌套。

- ✅ **正确激活**：用户在主对话说"用 deep-research-report 写一份关于 XX 的报告"，主对话读 SKILL.md、采用编排剧本、开始分派。
- ❌ **禁止**：把本 skill 通过 `Agent` 工具作为嵌套子 Agent 拉起——此时无法再向下分派。
- **降级兜底**：若本 skill 被作为嵌套子 Agent 拉起（`Agent` 工具不可用），**自动降级为单 Agent 极速档**，标注"多 Agent 协同不可用，已降级为 V3 单 Agent 模式"。

## 2. 11 角色 × 阶段 × 模型 × 编排模式

| 阶段 | 主责角色 | 编排模式 | 模型 | CHECKPOINT | 门禁 |
|------|---------|---------|------|:---:|:---:|
| 1 初始化 | orchestrator（主对话直接做） | 单体 | Opus | CP1 参数 / CP2 封面 | — |
| 2 搜集抽取 | `source_collector_agent` | 单 Agent 分派 | Haiku | — | G(收集) |
| 3 事实核验 | `fact_verifier_agent` | 单 Agent 分派 | Opus | — | G(核验) |
| 4 详细大纲 | `outline_architect_agent` | 单 Agent 分派 | Opus | **CP3 大纲确认** | G(大纲) |
| 5 专题卡片 | `card_synthesizer_agent` | 单 Agent 分派 | Sonnet | — | G(卡片) |
| 6 核心架构图 | `diagram_agent` | 单 Agent 分派（多图可 parallel） | Haiku | — | G(出图) |
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

分派子 Agent 时必须在 prompt 中写明此契约。

## 4. 噪声检测与重试（收集每个子 Agent 输出时执行）

1. **提取有效内容**：用正则 `\[AGENT-OUTPUT-START\]([\s\S]*?)\[AGENT-OUTPUT-END\]` 提取。无匹配 → FAILED → 重试。
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

## 7. 三档协同模式与模型联动（见 SKILL.md 三档表）

| 协同档位 | chapter_writer | chapter_auditor | redteam | orchestrator |
|---------|----------------|-----------------|---------|--------------|
| 完整多 Agent | Sonnet | Opus | 2×Opus+2×Sonnet | Opus |
| 分层多 Agent（默认） | Sonnet | Opus（仅核心章） | 2×Opus+2×Sonnet | Opus |
| 单 Agent 极速 | Sonnet（orchestrator 自写） | 不启用（回退 V3 自查） | 不启用（回退 V3 压缩 3 维度） | Sonnet（整体降档） |

> **降级不是"没有质量控制"**：单 Agent 极速档采用 V3 的 CHECKPOINT/STATS/REPORT 单 Agent 自律机制，V3 的价值在极速档完全保留。**关键**：单 Agent 档 orchestrator 自身也从 Opus 降到 Sonnet——此时它承担"直接写一份简报"而非"跨 9 阶段全局裁决"，认知负荷类型变了。回退兜底：模型不可用时按 Haiku→Sonnet→Opus 单向就高兜底。

## 8. 门禁快照落盘（防长会话丢失，UEAS 习惯）

每个门禁步骤把快照 append 落盘（JSONL，append-only）到进度文档，不依赖会话记忆。阶段 7 逐章审计报告落 `research/chapter-reports/`，阶段 8 统一风险清单落 `research/redteam-risklist.md`。

## 9. 已知限制（继承 v4 §9）

- **depth-1 天花板**：`Agent` 工具只支持主对话→工作 Agent 单层委派。
- **成本放大 3-5 倍**：完整档阶段 7 每章 = 写作 + 审计预承诺 + 审计打分 + 最多 2 轮回炉。这是三档降级的根本原因。
- **无 Hook 级强制**：所有 Agent 边界与预承诺纪律都是 prompt-level，无确定性 PreToolUse hook 拦截。但"不同 Agent + 盲态预承诺 + 真脚本量化"相比 V3"同一 Agent 自查"已是数量级改善——把"靠自律"变成"靠结构 + 大幅提高作弊成本"。
