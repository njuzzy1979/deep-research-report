---
portability: claude-only
---

# 阶段 7 编排脚本：逐章写作 + 独立审计对抗 pipeline

> 本文件落盘 v4 §5.1 的阶段 7 workflow，供 `report_orchestrator`（主对话剧本）执行。
> 双表达：声明式伪代码（若环境有 Workflow 原语）+ 等价编排器循环散文（今天可执行的底座）。
> 母文件：`../SKILL.md` §多 Agent 协同执行体系

---

## 设计要点

1. **写审分离**：`chapter_writer_agent` 与 `chapter_auditor_agent` 是两个不同 subagent_type，检查者 ≠ 被检查者。
2. **审计盲态预承诺**：审计先看标准承诺评分计划（Phase A），再看稿打分（Phase B）——摧毁"看稿再放宽标准"漂移路径。
3. **量化检查用真脚本**：审计调 `scripts/contract_check.py` 等，不心算。
4. **loop-until-pass 有限回炉**：最多 2 轮，超限升 P0 呈用户。
5. **逐章串行**：第 X 章 PASS 才解锁第 X+1 章，防"写到最后才发现前面崩"。

## 声明式伪代码

```javascript
// stage7_write_audit.workflow —— 逐章写作+独立审计
// 输入：outline.md（章序）、card-index.csv、figures/、writing-standards.md、converter-contract、struct_template
const chapters = parseChapters("research/outline.md");   // 有序章列表
const MAX_REVISION = 2;

for (const ch of chapters) {                    // 逐章串行
  let round = 0, verdict = "REVISE", issues = [];
  while (verdict === "REVISE" && round <= MAX_REVISION) {

    // ① 写作·盲态预承诺（Phase A）+ 明态写作（Phase B）
    const preW = agent("chapter_writer_agent", { model: "sonnet", mode: "precommit",
      inject: { contract: "agents/contracts/writer_contract.json", chapter_meta: metaOf(ch) },
      require_tail: "[PRE-COMMITMENT-ACKNOWLEDGED]" });
    const draft = agent("chapter_writer_agent", { model: "sonnet", mode: "write",
      inject: { phaseA: wrap(preW, "<phaseA_output>"),
                outline_entry: outlineEntry(ch),      // 只给当前章条目（解决A-1）
                cards: cardsOf(ch), figures: figuresOf(ch),
                standards: "writing-standards.md", contract: "appendix-converter-contract.md",
                proposal_mods: struct_template === "proposal" ? PROPOSAL_MODULES : null,
                revision_issues: round > 0 ? issues : null },
      output: "research/drafts/" + ch.file });        // chXX 独立 H2 + 写作者自声明

    // ②a 审计·盲态预承诺（Phase A）—— ⚠ 不注入 draft 正文
    const precommit = agent("chapter_auditor_agent", { model: "opus", mode: "precommit",
      inject: { contract: "agents/contracts/auditor_contract.json",
                outline_entry: outlineEntry(ch), standards: "writing-standards.md",
                contract_c: "appendix-converter-contract.md", writer_selfclaim: draft.selfclaim },
      require_tail: "[PRE-COMMITMENT-ACKNOWLEDGED]", output: "scoring_plan" });
    lint(precommit);  // 失败→retry once，二次失败→P0

    // ②b 审计·明态打分（Phase B）—— 此时才注入正文 + 调真脚本
    const audit = agent("chapter_auditor_agent", { model: "opus", mode: "score",
      inject: { draft: draft.body, precommit_plan: wrap(precommit, "<phaseA_output>"),
        tools: [ run("python scripts/contract_check.py " + draft.file + " --json --expect-figures " + figCount(ch)),
                 run("python scripts/claim_strength_check.py research/drafts/ research/claims/claims-ledger.csv"),
                 run("python scripts/chart_checks.py --figures-dir research/figures/") ] },
      consistency_check: true,   // 打分语言须 substring-match precommit 触发词
      output: { verdict, dimension_scores, issues } });
    lint(audit);

    verdict = audit.verdict; issues = audit.issues; round++;
    persist("research/chapter-reports/" + ch.id + "-r" + round + ".md", audit); // 门禁快照落盘
  }
  if (verdict === "REVISE") { orchestrator.raiseP0(ch, issues); break; }  // 2轮仍不过→P0停
  // PASS → 解锁下一章
}
orchestrator.checkpoint("CP4", aggregate("research/chapter-reports/*"));  // 末尾汇总呈用户
```

### Phase A/B 输出规模应对（跨模型兼容性优化方案 §C4，弱模型 tier B 增量步骤）

`derive_phase_a_mode(profile.limits.max_output_tokens)`（`scripts/model_profile.py`）在 tier A（64K）派生 `"free"`，在 tier B（如 DeepSeek V3.2 8K）派生 `"confirm"`。orchestrator 据此在②a 步 `inject` 中额外注入 `phase_a_mode` 告知审计 Agent 当前应采用的书写形态（详见 `chapter_auditor_agent.md` "Phase A 确认式书写形态"节），并追加以下编排步骤：

1. **Phase A 落盘转换**：②a 步 `precommit` 的 Markdown 原文（`confirm`/`adjust:` 形态或 free 形态）落盘为 `research/chapter-reports/chXX-precommit.md`，随后 orchestrator 用 `python scripts/phase_a_to_json.py research/chapter-reports/chXX-precommit.md --chapter chXX --json` 转换为符合 `schemas/auditor-phase-a.schema.json` 的 JSON，落盘 `research/chapter-reports/chXX-precommit.json`，供②b 步在 `<phaseA_output>` 中同时引用 Markdown 原文与 JSON 校验结果。转换失败（未知维度 id / lint 不通过）→ 视同 Phase A lint 失败，走既有重试路径。
2. **分批兜底**（仅确认式仍超限时启用，见 `auditor_contract.json` 的 `batch_grouping` 字段）：②a 步拆分为 3 次调用，分别只注入 `batch_grouping.batch1_high` / `batch2_mid` / `batch3_low` 声明的维度子集，各自落盘 `chXX-precommit-batch{1,2,3}.md`（首行 HTML 注释 `<!-- phase=A batch=N chapter=chXX dims=<count> -->`）。三批文件齐备后，`phase_a_to_json.py` 支持 `--merge` 读取三份文件的 HTML 注释元数据校验批次完整性（声明的 `dims` 数与实际维度小节数一致、`batch_grouping` 声明的全部 id 均已出现），再合并转换为单份 `chXX-precommit.json`。批次不完整（缺文件/维度数不符）→ 报错，不静默拼接。
3. **Phase B 脚本结果落盘**：②b 步中 `tools` 数组各脚本的**全量** stdout（含 `--json` 输出）由 orchestrator 落盘到 `research/chapter-reports/chXX-scripts.json`（合并多个脚本的 JSON 结果为一个文件，键名以脚本名区分），审计 Agent 的 `## 脚本量化结果` 小节只贴摘要（裁决相关字段）+ 引用此路径，不贴全量原始输出。`card_overlap_check.py --json` 卡片数多时输出很长，orchestrator 在落盘前须截断/摘要，只保留裁决相关字段。
4. **Phase A/B 一致性机械核对**（跨模型兼容性优化方案 §B4，红线 A5 的脚本化执行）：②b 步 Phase B 的 5 项必需小节中 `## 逐维度打分`/`## 裁决`/`## issue 清单` 对应内容，由 orchestrator 抽取组装为符合 `schemas/auditor-phase-b.schema.json` 的 JSON，落盘 `research/chapter-reports/chXX-audit-phaseB.json`（与步骤 1 已落盘的 `chXX-precommit.json`——即 Phase A JSON——为同一批产物的两半）。两份 JSON 齐备后，orchestrator 调用：

   ```bash
   python scripts/precommit_consistency_check.py \
       research/chapter-reports/chXX-precommit.json \
       research/chapter-reports/chXX-audit-phaseB.json --json
   ```

   **调用者只能是 orchestrator，不是 `chapter_auditor_agent` 自己**——让被检查者运行检查自己的脚本，在弱模型上等于没检查。退出码 0 = 一致，继续走裁决路由；退出码 1 = 不一致，输出的 `failure_stage` 字段（`"phaseA"` / `"phaseB"`）决定回炉到哪一阶段：`phaseA` 视同 Phase A lint 失败走既有"重试 1 次"路径；`phaseB` 视同 Phase B lint 失败，`emit [GENERATOR-PHASE-ABORTED: role=evaluator, chapter=<id>, reason=phaseB_lint_failed]`，无 retry-once。退出码 2 = 文件读取/schema 加载异常，orchestrator 记降级台账后按 Phase A 失败路径处理。**天花板声明**（脚本 docstring 已完整声明，此处仅提醒）：本脚本只做"文字层面是否复述了触发词"的机械核对，不能证明盲态预承诺纪律被真正遵守——那需要靠②a/②b 两次独立 Agent 调用的物理隔离（本文件"关键"段落）保障，脚本只是提高作弊成本，不是 100% 保证。

## 等价编排器循环散文（今天可执行）

主对话采用 `report_orchestrator` 剧本后，对 outline.md 每一章 ch：

1. 用 `Agent` 拉起 `chapter_writer_agent`（model=sonnet），先 precommit（只给契约+章元数据，要求 `[PRE-COMMITMENT-ACKNOWLEDGED]` 结尾），再 write（注入大纲条目/卡片/图/标准/合约/立项模块）。用输出隔离标记提取草稿 + 自声明。
2. 用 `Agent` 拉起 `chapter_auditor_agent`（model=opus, mode=precommit），**只给标准与大纲条目、不给草稿**，要求输出评分计划并以 `[PRE-COMMITMENT-ACKNOWLEDGED]` 结尾。
3. 用 `Agent` 拉起 `chapter_auditor_agent`（model=opus, mode=score），给草稿 + 上一步评分计划，要求它用 `Bash` 真跑 `contract_check.py` 等脚本取确定性统计，按评分计划逐维度打分，输出 PASS/REVISE + issues。
4. REVISE→回第 1 步（带 issues），round+1；PASS→下一章。round>2 仍 REVISE→orchestrator 记 P0，停，呈用户。
5. 每步审计报告 append 落盘 `research/chapter-reports/`（防长会话丢失）。
6. 全部章 PASS 后，汇总所有审计报告走 CP4 呈用户。

> **关键**：第 2、3 步是**两次独立的 Agent 调用**，第 2 步 prompt 里物理上没有草稿正文——这就是"盲态"的落地方式，不依赖 Agent 自律。

## 门禁映射

- **G7-write**：每章通过独立审计。REVISE 回 writer，2 轮不过记 P0。
- **CP4**：逐章审计报告汇总，orchestrator 呈用户确认后进阶段 8。

## 与 stage-7-writing.md 的关系

`stage-7-writing.md` 定义"检查什么"（12 条标准、13 项自查、写作禁区）——本文件不重复，而是把这些作为 `chapter_auditor_agent` 的评分 rubric。单 Agent 极速档不走本 pipeline，回退 stage-7-writing.md 的 V3 单 Agent 自查清单。
