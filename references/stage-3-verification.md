---
portability: core
---

# 阶段 3：事实核验

> 本文件是 deep-research-report skill 的阶段 3 详细 spec，从 SKILL.md 拆分而来。
> 母文件：`../SKILL.md`（流程索引）

---

这是整个方法论的核心——**未经验证的事实不能进入正文**。

## 3.1 建立事实核验台账

创建 `research/claims/claims-ledger.csv`，每条事实主张记录：

| 字段 | 说明 |
|---|---|
| `claim_id` | 唯一编号 |
| `claim_text` | 原文主张 |
| `source_file` | 来源文件名 |
| `claim_type` | 日期 / 数字 / 人物 / 机构 / 事件 / 技术能力 / 因果判断 / 首次性判断 / 其他 |
| `verification_status` | 真实 / 基本属实 / 误导 / 错误 / 无法证实 / 仅为观点 |
| `evidence_sources` | 核验所用的 A/B 级来源 |
| `confidence` | 高 / 中 / 低 |
| `rewrite_suggestion` | 修正后的表述建议 |
| `risk_note` | 如误用会有什么风险 |
| `adopted` | 采用决策：`true`（采用）或 `false`（剔除）。搜集阶段默认 `true`，核验阶段根据 §3.3 二分决策规则更新 |
| `claim_nature` | 主张性质：`fact`（事实主张）或 `opinion`（观点主张）。仅当核验状态为"仅为观点"时填入 `opinion`；其他情况默认为 `fact` |

## 3.2 核验优先级

优先核验以下类型的主张：
1. **首次性判断**（"首次""第一个""最大"）——必须有 A/B 级独立来源确认
2. **数字与统计**（金额、数量、比例、日期）——必须至少一个 A/B 级来源
3. **因果判断**（"A 导致 B""A 决定了 B"）——必须有 A/B 级来源支持因果链
4. **能力边界**（"完全自主""全自动""秒级"）——几乎总是需要降级为"据称/部分实现"
5. **战果/伤亡/影响**（涉及人的判断）——必须多源交叉验证

## 3.3 核验后二分决策

> **台账数据的读者可见性**：本节所述的所有核验状态（`verification_status`）、证据来源（`evidence_sources`）、置信度（`confidence`）均为**内部质控数据**，记录在 `claims-ledger.csv` 和 `source-index.csv` 中供写作者和审校者使用。核验状态决定了写作者如何使用该事实（下表），但核验状态**本身**不出现在面向读者的正文或参考文献中。读者看到的成品是：被核验通过的事实 + 上标编号 + 干净 GB/T 7714-2015 格式的参考文献列表。按 `writing-standards.md` 标准 0（前台/后台分离），这是"编辑部后台过程"不进入"前台成品"的核心示例。

**核验完成后，对每条主张做最终二分决策：采用或剔除。**

| 决策 | 核验状态 | 操作 |
|------|---------|------|
| **采用** | "真实"或"基本属实" | `adopted=true`。主张可用于正文和卡片合成。在 `claims-ledger.csv` 中将 `adopted` 字段设为 `true`。 |
| **剔除** | "误导""错误""无法证实" | `adopted=false`。对应的 card 不生成或不进入章节卡片池。在 `claims-ledger.csv` 中将 `adopted` 字段设为 `false`，并在 `rewrite_suggestion` 或 `risk_note` 列注明剔除原因。 |
| **采用（观点）** | "仅为观点" | `adopted=true`。但在 `claims-ledger.csv` 中新增 `claim_nature` 字段，标记为 `opinion`（区别于 `claim_nature: fact`）。Writer 在写作时自动知道这是"某方的观点"而非"既定事实"，不需要额外加限定包装（如"据称""尚未证实"）。 |

**`adopted=false` 的主张不入卡片**：`card_synthesizer_agent`（阶段 5）在生成卡片时**只读取 `adopted=true` 的主张**。`adopted=false` 的主张不出现在任何卡片中。如需保留审计追溯，在 `claims-ledger.csv` 中保留记录但确保在卡片合成池中排除。

**核验执行者**：`fact_verifier_agent`（多 Agent 协同体系下）或 orchestrator（单 Agent 档下）。执行者负责：(a) 判定每条主张的 `verification_status`；(b) 基于判定做出采用/剔除二分决策并写入 `adopted` 字段；(c) 对观点类主张写入 `claim_nature: opinion`。

### ▶ 阶段 3 质量门槛

- [ ] claims-ledger.csv 中所有主张的 `adopted` 字段已按照 §3.3 二分决策规则填写完成（`true` 或 `false`）
- [ ] 所有 `adopted=false` 的主张已在台账 `risk_note` 或 `rewrite_suggestion` 列中标注剔除原因
- [ ] 所有核验状态为"仅为观点"的主张已填写 `claim_nature: opinion`
- [ ] 台账中"首次/最大/全自动/秒级"等强表述全部完成核验
- [ ] 每个核心章节至少有 3 个 A/B 级来源（可在后续阶段补充）
- [ ] 所有 `adopted=false` 的主张已从卡片生成池中排除，台账中标注剔除原因

🔴 CHECKPOINT · 🛑 STOP：以上 4 项质量门槛全部通过后进入阶段 4。任一项未通过 → 回到对应子步骤补充（缺来源 → 阶段 2.2 补充资料、缺核验 → 阶段 3.2 优先核验强表述）。
