---
portability: claude-only
---

# 阶段 8 编排脚本：红队并行审查 + 综合裁决 parallel

> 本文件落盘 v4 §5.2 的阶段 8 workflow，供 `report_orchestrator`（主对话剧本）执行。
> 母文件：`../SKILL.md` §多 Agent 协同执行体系

---

## 设计要点

1. **8 维度 → 4 并行人格**：证据/逻辑/表述/资产四红队并行跑全报告。
2. **异构模型（仅 Tier A）**：证据/逻辑用 Opus，表述/资产用 Sonnet（v4 §3.2.3，制造真实视角差异防同质化）。**Tier B/C 单模型宿主下**（`model-profile.json` 声明 `capability_tier: B|C`）无法异构，4 人格统一使用 profile 声明的同一模型，改由**人格 prompt 差异化 + 审查顺序轮换**制造视角差异（效力如实低于 Tier A，见 `agents/redteam_agent.md` "Tier B/C 降级"节）。
3. **红队 ≠ 阶段 7 审计**：红队只找跨章/对抗性问题，接收阶段 7 审计报告避免重复逐章打分。
4. **综合去重**：`redteam_synthesizer_agent` 合并 4 份、去重、严重度取最高。
5. **发现 ≠ 修复**：综合清单交回 `chapter_writer_agent` 修订，红队不改稿。
6. **超大报告降级**：当报告正文超过 50,000 中文字或章节数超过 8 章时，
   orchestrator 启动红队前先评估上下文窗口预算。若全报告注入超出安全边界，
   可将 4 人格从"全报告并行"降级为**"按章节组分批，再跨组交叉"**：
   - 将章节按相邻关系分为 2-3 组，每组内 4 人格仍并行审查
   - **代价声明**：分组间的一致性矛盾可能漏检
   - **红线**：核心结论章不允许被拆分到不同组
7. **swap-and-average（仅 Tier C + 高风险报告类型，非默认）**：详见 `agents/redteam_agent.md` 对应节，红队调用轮次翻倍，只在 `capability_tier=C` 且 `struct_template=proposal` 时启用。

> **输出格式权威来源**：本文件伪代码中的 `output_format` 字段仅作示意（列出各字段含义），**实际输出格式以 Markdown 表格为准**——`redteam_agent.md` §"输出——结构化风险清单"（单人格表格：编号/风险等级/涉及章节/问题类型/问题描述/建议处理）与 `redteam_synthesizer_agent.md` §"输出——统一风险清单"（综合表格：额外含"来源人格"列）。两份文件的表格定义是唯一权威格式，本文件不重复定义 schema，避免 JSON 声明与实际 Markdown 表格产出脱节（跨模型兼容性优化方案 D2 格式统一裁决）。

## 声明式伪代码

```javascript
// stage8_redteam.workflow —— 红队并行审查 + 综合
const report = "research/drafts/final-report.md";        // 阶段7合并后的正文
const auditReports = glob("research/chapter-reports/*");  // 阶段7审计报告(给红队避免重复)

// PERSONAS：Tier A 下模型异构（opus/sonnet 见下）；Tier B/C 下 orchestrator 将
// 全部 persona 的 model 字段统一替换为 profile.capability_tier 对应的单一模型，
// 并追加 prompt 差异化指令 + 按报告轮换 personaOrder（不在此常量中体现，由
// orchestrator 在分派时按 model-profile.json 动态改写，详见 redteam_agent.md）。
const PERSONAS = {
  证据红队: { dims: ["证据薄弱","矛盾一致性"], model: "opus" },
  逻辑红队: { dims: ["逻辑跳跃","偏题"],       model: "opus" },
  表述红队: { dims: ["夸大表述","概念堆砌"],   model: "sonnet" },
  资产红队: { dims: ["卡片浪费","图表一致性"], model: "sonnet" },
};

// ── 并行 fan-out：4 人格独立审查全报告 ──
// 输出格式：Markdown 表格（见 redteam_agent.md 权威定义），此处 output_format
// 仅为伪代码示意各字段含义，不是实际传输格式。
const redteamReports = parallel(
  Object.entries(PERSONAS).map(([persona, cfg]) =>
    agent("redteam_agent", { persona, model: cfg.model, dimensions: cfg.dims,
      inject: { report, prior_audit: auditReports,        // 阶段7已判的，红队只复核不重判
                ledger: "claims-ledger.csv", cards: "card-index.csv",
                color_registry: "research/figures/color-registry.csv",
                // 退化：color-registry.csv 不存在时跳过跨图颜色一致性检查
                checklist: "red-team-checklist.md",
                scope: "全报告·跨章·对抗性；逐章合约类问题已由阶段7审计覆盖，勿重复" },
      // 字段含义：编号/风险等级(高中低)/涉及章节/问题类型/问题描述/建议处理，
      // 实际以 redteam_agent.md 表格列为准
      output_format: "markdown_table" })
  )
);  // 关键路径：某人格污染/超时 → 重试满2次

// ── gather：综合去重裁决 ──
const unified = agent("redteam_synthesizer_agent", { model: "sonnet",
  inject: { reports: redteamReports },
  tasks: ["合并同指问题(去重)", "严重度冲突取最高", "统一R编号排序", "分组：高100% / 中≥80%"],
  output: "research/redteam-risklist.md" });

orchestrator.checkpoint("CP5", unified);  // 呈用户确认处理方案

// ── 修订：发现≠修复，交回 writer 逐条处理 ──
for (const risk of unified.high.concat(unified.mid)) {
  agent("chapter_writer_agent", { model: "sonnet", mode: "redteam_fix",
    inject: { risk, chapter: risk.chapter, report }, action: risk.suggested_fix }); // 删/改写/补证据/降级
  markResolved(risk);
}
gate("G8-redteam", unified.high.every(r => r.resolved));  // 高风险未清零→不进阶段9

// ── 超大报告降级分支（超过 50,000 字或 8 章触发）──
if (report.chinese_chars > 50000 || report.chapter_count > 8) {
  const groups = splitChaptersIntoGroups(report.chapters, { maxGroups: 3 });
  // 红线校验：核心结论章不可跨组拆分
  assert(groups.every(g => !hasSplitCoreChapter(g)), "核心结论章跨组拆分——拒绝降级");
  warn("超大报告降级启动：4 人格按章节组分批审查，分组间一致性矛盾可能漏检");
  const groupedReports = [];
  for (const group of groups) {
    const partial = parallel(
      Object.entries(PERSONAS).map(([persona, cfg]) =>
        agent("redteam_agent", { persona, model: cfg.model, dimensions: cfg.dims,
          inject: { report: group, prior_audit: auditReportsByGroup(group),
                    ledger: "claims-ledger.csv", cards: "card-index.csv",
                    color_registry: "research/figures/color-registry.csv",
                    checklist: "red-team-checklist.md",
                    scope: `章节组 ${group.label}·跨章·对抗性（超大报告降级模式）` },
          output_format: "markdown_table" })
      )
    );
    groupedReports.push(...partial);
  }
  // 合并后仍走综合去重裁决
  const unified = agent("redteam_synthesizer_agent", { model: "sonnet",
    inject: { reports: groupedReports },
    tasks: ["合并同指问题(去重)", "严重度冲突取最高", "统一R编号排序",
            "标注降级模式:分组间一致性矛盾可能漏检"],
    output: "research/redteam-risklist.md" });
}
```

## 等价编排器循环散文（今天可执行）

主对话采用剧本后：

1. 用 **4 次 `Agent` 调用**（可同一消息内并发发起）拉起 `redteam_agent`，各带不同 persona 与维度子集、**不同 model**（证据/逻辑=opus，表述/资产=sonnet），都注入 final-report.md + 阶段 7 审计报告 + 台账 + 卡片索引 + 红队清单，要求输出结构化风险项。用输出隔离标记提取 4 份。
2. 用 `Agent` 拉起 `redteam_synthesizer_agent`（model=sonnet），注入 4 份报告，要求合并去重 + 严重度裁决（取最高）+ 统一编号，产出统一风险清单。
3. orchestrator 走 CP5 呈用户确认处理方案。
4. 对高/中风险逐条，用 `Agent` 拉起 `chapter_writer_agent`（mode=redteam_fix）在对应章执行删/改写/补证据/降级，回填处理结果。
5. 高风险全部 resolved 才算 G8 通过；否则不得进阶段 9。

## 门禁映射

- **G8-redteam**：高风险清零 / 中风险 ≥80%。`redteam_synthesizer` + 用户(CP5)负责，失败回 writer 修订。

## 与 stage-8-review.md 的关系

`stage-8-review.md` 定义 8 检查维度与风险处理标准——本文件把这 8 维度聚为 4 并行人格执行。单 Agent 极速档不走并行，红队压缩为 3 维度由 orchestrator 自审（回退 stage-8-review.md 的 V3 单 Agent 流程）。
