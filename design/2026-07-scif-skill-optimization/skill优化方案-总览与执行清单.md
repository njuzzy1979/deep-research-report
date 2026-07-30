# deep-research-report skill 优化方案 · 总览与执行清单

> 编制日期：2026-07-29
> 触发事件：《面向未来空间智能的世界模型、动态本体、多智能体与空间认知操作系统总体架构研究》（SCIF 框架，10 万字级）编写全过程
> 底层模型：DeepSeek V4（Tier B，非 Claude）
> **本文档性质：设计稿，已于 2026-07-30 全部执行完毕。**
> **执行结果记录：`skill优化方案-执行结果记录.md`（逐项状态/文件改动/commit hash/测试验证/偏差说明）**
> 执行范围：完整 P0-P3，共 30 个子项**全部完成**，0 项跳过。
> 目标仓库 `C:\Users\张\.claude\skills\deep-research-report`，baseline `82e736d` → 共 14 个 commit（`64f9738` … `8175768`）。
> 收尾回归：`python scripts/selfcheck.py --level full` → **PASS**（tests/ 368 passed + scripts/md2docx/tests/ 12 passed + 8 项脚本冒烟全 OK；baseline 为 297 passed + 4 failed）。
> **本次 SCIF 报告产出（`research/`、`output/`）零改动**——仅作为只读测试数据引用，已核实全部文件时间戳未变、未产生任何新文件。
> 下方 §八执行清单中每项均已补实际完成状态标记。

---

## 一、一句话定性

用户可见的"报告章节都是空的"，根因不是模型笨，而是 skill 内部**多个组件各自符合自己的契约、但从未被端到端联调过**；而当管线失败时，skill 又**没有给 orchestrator 任何强制路由**，于是它自己写代码绕过去，把一次技术故障放大成了交付事故。

---

## 二、本次新发现的四个缺陷类别（此前 11 个问题记录均未覆盖）

| 编号 | 缺陷 | 严重度 | 状态 |
|---|---|---|---|
| N1 | 标题体系三重失效：outline 键名契约断裂 → 白名单静默空转 → `## 本章结论` 被判为章标题 | P0 | 详见 `skill优化方案-D1标题体系修复.md` |
| N2 | orchestrator 纪律真空：失败路径无强制路由，机器强制层完全不存在 | P0 | 详见 `skill优化方案-D2护栏体系.md` |
| N3 | 交付产物治理缺失：命名靠人工、output 目录无门禁、docx 从未被任何门禁检查过 | P0 | 详见 `skill优化方案-D3输出规范.md` |
| N4 | **阶段 4 结构声明缺失且无机器校验**：真实 outline 的 `subsections` **16/16 全为空列表**，YAML 声明 0 个 section 而终稿实际有 113 个 `Heading 2`；阶段 4 全文零脚本调用，`stage-4-outline.md:320` 的"大纲含三级标题"门槛是人工勾选、本次被勾选通过而实际违反 | P1 | 详见 `skill优化方案-D1标题体系修复.md` §九（D1-9/D1-8） |

---

## 三、【核心结论】本次审计最重要的一次纠正

**设计层最初的共识是错的，且这个错误如果不纠正，会导致修完仍不解决用户投诉。**

发现层 A3 与设计层 D1 都主张："优先修复权威章标题白名单机制，可**同时**解决 H2 误判与图表章号错位（一石二鸟）。"

审查层 R2 提出反对，主控随即亲自运行 Python 探针，在真实 `research/outline.md` + `research/drafts/final-report.md` 上复现，**实测推翻该论断**：

```
LOOKUP after normalize: 13          ← 白名单确实修好了（从 0 条修到 13 条 CHAPTER）
by kind: {'CHAPTER': 13}
headings: 141
本章结论 count: 13
本章结论 kinds: {'CHAPTER'}          ← 仍然全部是 CHAPTER！
SAMPLE: [('本章结论','CHAPTER','第二章'), ('本章结论','CHAPTER','第四章'), ('本章结论','CHAPTER','第六章')]
W-HDR-04 count: 126
```

**机理**：`apply_structure_overlay()` 的语义是"**命中即覆盖，未命中只发 WARNING、不改分类**"（`headings.py:489-507`）。`## 本章结论` 不在 outline 声明里 → 未命中 → 保持 `classify_and_number` 推断出的 `CHAPTER`，甚至继续占用章号。

**交叉印证**：补位设计的 D1-bis 在完全独立的分析路径上，自行写出了同一结论——"批次 1 落地后 `本章结论` 仍是 CHAPTER，问题尚未消除，批次 3（层级下沉）才真正消除"。两个独立来源互证，这是本方案中置信度最高的一条判断。

**结论（贯穿全部文档）**：
- 白名单修复（D1-1/D1-2）与 H2 层级下沉（D1-5）是**并列的两个 P0，不是替代关系**。
- **只修白名单就收工，用户投诉的"章节都是空的"不会消失。**
- H2 层级下沉是**治愈用户投诉的关键单点**。

---

## 四、共同根因归簇（15 个问题 × 6 个根因）

| 根因 | 覆盖问题 | 数量 |
|---|---|---|
| **R-A 组件间契约无端到端联调** | N1、N3、P1、P10 | 4 |
| **R-B 规范依赖人工执行而无机器门禁** | N2、N3、N4、P5、P6、P9 | 6 |
| **R-C 门禁存在但从不生效（虚假保证）** | N1、N3、N4、P9、P10 | 5 |
| R-D 失败路径无强制路由 | N2、P11 | 2 |
| R-E 测试 fixture 不代表真实产物 | N1 | 1 |
| R-F 模型能力档位适配不足 | N2、P3 | 2 |

**最高杠杆根因是 R-C「门禁存在但从不生效」**——它比"没有门禁"更危险，因为提供了虚假保证。本次实测出四处：

| 门禁 | 实测失效状态 |
|---|---|
| `figure_gate.py` | 真实项目上 `figures_manifest` 是 list 而脚本要求 dict → 清单 total=0 → 返回 `passed:True` → **exit 0**。声明了 15 张图，一张都没检查过 |
| `writing_quality_check.py` | `CHAPTER_HEADING_PATTERN` 无法匹配 `merge_drafts` 产出的带空格格式"第 1 章" → 对所有合并终稿**恒零命中恒 pass** |
| `apply_structure_overlay` | `headings.py:482` `if not lookup: return results` 静默返回，三个诊断码 W-HDR-04/05、I-HDR-07 全在此行之后，**永不触发** |
| `stage-4-outline.md:320` 质量门槛 | "大纲含三级标题（章→节→小节）"是**人工勾选的复选框**，阶段 4 全文零脚本调用。本次被勾选通过，而实测 `subsections` **16/16 全为空列表**、YAML 声明 0 个 section（N4） |

---

## 五、实施路线图

```
第 1 批（无依赖，可全部并行，约 1 天）
├── D1-0  issues.py 删除两条死码位                    15 分钟
├── D4-10 model_profile.py 死代码修复                 15 分钟  ← 唯一真机器护栏的载体，不修则它是坏的
├── D1-A  writing_quality_check.py 正则补 \s*          30 分钟
└── D3-0  delivery_checklist_check.py 补 output_dir 入参  2 小时

第 2 批（P0 主体，关键路径，约 3 天）
├── D1-1  normalize_outline_structure() 五处调用点贯通   1 天   ┐
├── D1-5  merge_drafts 层级下沉（治愈用户投诉关键单点）  半天   ├ 可并行
├── D2-8  失败时半成品清理（唯一切断事故因果链）        半天   │
└── D3-1  figure_gate 入口修复（当前完全空转）          1 天   ┘

第 3 批（依赖第 2 批，约 2.75 天）
├── D1-2  静默失效修复 + E-OL-03/I-OL-04 新码           半天
├── D1-6  --structure-overlay 三态开关 + W-HDR-04 聚合  半天
├── D1-9  阶段4 结构完整性门禁（阶段4 首次获得机器校验） 0.75 天 ← D1-8 的强制前置
├── D3-2  provenance sidecar + emit_delivery            1 天
└── D2-7  docx 回读校验（交付物当前从未被检查过）        半天

第 4 批（收尾，约 5.4 天）
├── D1-7  端到端测试 + fixture（D1 为唯一 owner）        1 天
├── D1-8  骨架 docx 预确认 + H1/H2 锁定按 kind 分级      1.65 天 ← 依赖 D1-1/D1-6/D1-9
├── D2-1~5 文档层条文（须先补齐可粘贴原文）             半天
└── D2-9  PreToolUse hook 项目级分发（U1/U2 定案）       2.25 天  ← 纵深防御加强层，依赖 D2-7/D2-8 已完成
```

**总工作量约 12.15 人天**，关键路径为第 2 批的 3 天。

> **口径说明（本轮核算时发现的既有小账差）**：上列各批的"约 X 天"是**标称值**（含余量），与逐项明细求和不完全相等。核对结果：第 4 批明细（1+1.65+0.5+2.25=5.4）与标称一致；**第 3 批在本轮之前即已少算 0.5 天**——原标称 2 天，而明细为 D1-2 0.5 + D1-6 0.5 + D3-2 1 + D2-7 0.5 = 2.5 天。本轮不擅自改动既有标称口径，仍按"原标称 + 新增项"推进（2 + 0.75 = 2.75），故 12.15 这一总数**沿用既有口径**；若改按明细严格求和，总数应为 12.65 人天。实施排期时建议以明细为准。

**最小可交付集（约 2 天）**：第 1 批全部 + D1-5 + D2-8。理由：第 1 批四项都是低风险高确定性修复；D1-5 直接治愈用户投诉；D2-8 是唯一能切断事故因果链的机器措施。**D2-9 不在最小可交付集内**——D2-7/D2-8 已能在产物层面捕获同类事故，D2-9 是行为层面的加强，且自身存在"orchestrator 可编辑 `.claude/settings.json` 绕过 hook"的未闭环递归漏洞（见 D2 文档 §5.4），不构成阻塞项。**D1-8/D1-9 亦不在最小可交付集内**——D1-8 依赖链最长（D1-1+D1-6+D1-9），提前实施只会产出空白骨架（实测：当前跑 `outline_title_extract.py` 得 13/13 空标题且 EXIT=0）。

---

## 六、需用户决策事项

| # | 事项 | 背景 | 建议 |
|---|---|---|---|
| U1/U2 | ~~是否引入 PreToolUse hook / 脚本目录只读保护~~ **已裁决，见 D2-9** | 用户裁决：不采用用户级全局配置，改为随 skill 阶段 1.2 向**项目工作空间**下发 `.claude/settings.json`（复用 `model_profile.py:_write_local_override` 同款下发模式），作用范围收窄到"每次写报告的工作空间"，不影响其他项目/skill。规则二同时替代原"只读保护"设想——机制上是 PreToolUse deny 路径黑名单，不是文件系统权限位 | 详见 `skill优化方案-D2护栏体系.md` §五 D2-9，含 5 条未闭环局限的诚实标注（尤其是"orchestrator 可编辑 `.claude/settings.json` 自身以绕过 hook"的递归漏洞尚未解决） |
| U3 | 是否接受既有项目行为反转 | 白名单生效后，既有项目重新转换会得到**不同的 docx 结构** | 建议加 `--structure-overlay` 三态，存量走 warn |
| U4 | provenance 门禁是否设宽限期 | 既有产物全无标记，直接判 fail 会使既有项目 100% 无法交付 | 建议首版只 WARN |
| U5 | 归档机制是否自动执行 | 按文件名判定会**颠倒**：违规的 `SCIF_V1.0.docx` 被归档，合规的 `final-report.docx` 反而不被识别 | 建议首版只报告不移动 |
| U6 | ~~阶段 4 结构门禁（D1-9 的 S3"每章 ≥2 个节"）是否设为 `strict`~~ **已裁决** | 实测真实 outline 的 `subsections` **16/16 全为空列表**，S3 一旦 `strict` 会使**存量项目 100% 卡在阶段 4 CP3 无法进入阶段 5** | **用户裁决：首版 `--structure-gate=warn`**，与 U3/U4 同口径；待 `outline_architect_agent.md` 补齐 section 级产出要求（D1-8 步 5）后再切 `strict`。**实施时须显式记录切换 `strict` 的触发条件**（"连续 N 个新项目自然产生非空 section"或类似客观判据），避免"待补齐后再切"沦为无人跟进的口头承诺 |
| U7 | ~~是否采纳骨架 docx 预确认（D1-8 本体）~~ **已裁决** | 用户建议的原始诉求。**技术可行性已实测证实（未修改 md2docx 即 EXIT=0 产出含封面/TOC域/H1/H2 的 docx）**，但其确认价值**完全依赖 D1-9 先逼出 section 级数据**——否则骨架只有 16 个章标题、节层空白，反而制造"已确认过结构"的虚假安全感 | **用户裁决：采纳，排在第 4 批**，且以 D1-9 落地为硬前置。**约束**：D1-8 不得在 D1-9 完成并验证（真实 outline 的 section 数据非空）之前提前启动实施，避免重演"产出空白骨架"的风险 |

---

## 七、诚实性声明

1. **审查覆盖不均**：R1（技术正确性）、R2（连锁影响）、R3（可执行颗粒度）、R4（护栏有效性）四视角全部返回并已纳入。但 D2/D3 的部分条文（D2-1~D2-4）**当前只有设计说明、无可直接粘贴的完整 Markdown 原文**，转入实施前必须补齐。
2. **主控自身犯过两次错，均已纠正并记录**：
   - 误判"`h1_check` 是路由表盲区"——因提取枚举的正则字符类 `[a-z_]+` 不含数字，漏掉含数字的标识符。R1/R3/R4 三方独立指出。实际 failure_step 为 **6 个枚举、19 个调用点，路由表无需按数量修正**。
   - 误判"白名单读错键名"——schema 实测证明 `outline_reader.py` 是唯一合规消费端，违规方是适配层。
3. **纯文档护栏的效力评估为"接近零"**，本方案不将其计入有效交付项。详见 D2 文档。
4. **本轮（D1-8/D1-9 设计）在既有设计稿中新查出两处缺陷，均已就地标注，实施时必须一并修**：
   - **D1-1 归一化对非空 `subsections` 会产出 `section_title=None`**——schema 实测 `sections` 的 items 键为 `{section_no, section_title}`，`subsections` 的 items 键为 `{parent_section_no, subsection_no, subsection_title}`，内层键名不同，而 D1-1 是整体赋值。当前被"16/16 全空"掩盖，D1-9 逼出真实数据后即刻暴露。详见 D1 文档 §十第 4 条。
   - **D2-7 的 `verify_docx_structure()` 把 `Heading 2` 文本当作正文收集**，导致"只有标题、完全无正文"的 docx 能通过该门禁（已用骨架 docx 实测 `pass=True`）。它能捕获本次事故形态，但捕获不到"全文只有骨架"形态。约 1 行可修。详见 D1 文档 §9.4.4 与 D2 文档 §3 D2-7 处的标注。
5. **D1-3/D1-4 为空号**，历次修订从未占用（全库 grep 零命中），已在 D1 文档 §九开头明文声明永久保留不再启用，避免后续实施者误判为遗失章节。

---

## 八、执行清单摘要

> **执行状态说明（2026-07-30 补）**：下表"状态"列为实际执行结果。全部 30 项均已完成，详见 `skill优化方案-执行结果记录.md`。

### P0 — 阻塞交付，必做

| 编号 | 一行概述 | 涉及文件 | 工作量 | 所在文档 | 状态 |
|---|---|---|---|---|---|
| D1-1 | outline 键名归一化，贯通四个消费端，消灭 `int("?")` 崩溃 | `outline_reader.py`、`finalize_pipeline.py`、`merge_drafts.py`、`outline_title_extract.py` | 1 天 | D1 | ✅ 完成 `abfb755`（lookup 0→16，A1 达成 4 failed→17 passed） |
| D1-5 | merge_drafts 层级下沉，分章草稿内 H2→H3（**治愈用户投诉关键单点**） | `merge_drafts.py`、`stage-7-writing.md` | 半天 | D1 | ✅ 完成 `abfb755` + `8175768`（相邻 H2 对数=0） |
| D1-2 | 修复 `headings.py:482` 静默失效，新增 E-OL-03/I-OL-04 | `headings.py`、`issues.py` | 半天 | D1 | ✅ 完成 `f75039d` |
| D3-1 | figure_gate 入口修复（支持 list 形态 manifest，空清单判 FAIL） | `figure_gate.py` | 1 天 | D3 | ✅ 完成 `ac36bbf`（total 0→15，invalid 定位到 3-1） |
| D2-8 | 管线失败时不留半成品（**唯一切断事故因果链**） | `finalize_pipeline.py` | 半天 | D2 | ✅ 完成 `032f6ee` |
| D2-7 | docx 回读校验（最终交付物当前从未被任何门禁检查过） | `finalize_pipeline.py`、新增校验 | 半天 | D2 | ✅ 完成 `54ed312`（含修掉"骨架也能通过"的原设计漏检） |
| D4-10 | `model_profile.py` 死代码修复（唯一真机器护栏的载体） | `model_profile.py` | 15 分钟 | D4 | ✅ 完成 `64f9738` |
| D3-0 | `delivery_checklist_check.py` 补 `output_dir` 入参贯通 | `delivery_checklist_check.py`、`finalize_pipeline.py` | 2 小时 | D3 | ✅ 完成 `64f9738` |

### P1 — 严重

| 编号 | 一行概述 | 涉及文件 | 工作量 | 所在文档 | 状态 |
|---|---|---|---|---|---|
| D1-A | `writing_quality_check.py` 正则补 `\s*`（当前恒 pass 的虚假门禁） | `writing_quality_check.py` | 30 分钟 | D1 | ✅ 完成 `64f9738`（5/5 正例命中） |
| D1-6 | `--structure-overlay` 三态开关 + W-HDR-04 按 kind 聚合（防 126 条刷屏） | `headings.py`、`cli.py` | 半天 | D1 | ✅ 完成 `f75039d`（含 D1-8 步 4 按 kind 分级） |
| D1-7 | 端到端测试 + 真实形态 fixture（D1 为唯一 owner） | `tests/test_e2e_draft_to_docx.py`、`tests/fixtures/e2e-merge/` | 1 天 | D1 | ✅ 完成 `00adbe9`（12 用例 + 2 条 fixture 真实性自检） |
| D1-9 | 阶段 4 结构完整性门禁（S1-S6，阶段 4 首次获得机器校验；逼出 section 级数据） | 新增 `outline_structure_gate.py`、`stage-4-outline.md`、`outline_architect_agent.md` | 0.75 天 | D1 | ✅ 完成 `e92079e`（15 用例；真实 outline 上 S3 捕获 13 章全 0 节） |
| D3-2 | provenance sidecar + `emit_delivery` 命名下沉 | `finalize_pipeline.py`、新增 `.provenance.jsonl` | 1 天 | D3 | ✅ 完成 `e9c4764` |
| D4-8 | 长耗时操作超时/重试统一治理（合并 P3+P4） | `multiagent-orchestration.md`、`stage-2-collection.md` | 半天 | D4 | ✅ 完成 `1bc50b9`（新增 §4.1） |
| D4-9 | 阶段 2 门禁自适应 + 可信度升级路径（合并 P5+P6） | `stage-2-collection.md`、`source_collector_agent.md` | 半天 | D4 | ✅ 完成 `1bc50b9`（分桶门槛 + §2.1.1 升级路径） |
| D3-3 | 图表质量门禁加固（合并 P1+P7+P8+P9+P10） | `figure_gate.py`、`architecture_chart_agent.md`、`stage-6-diagrams.md` | 1 天 | D3 | ✅ 完成 `ac36bbf` + `1bc50b9`（新增 §6.9 可执行调用点） |
| D2-9 | PreToolUse hook 项目级分发（U1/U2 定案，纵深防御加强层） | `skill_root/.claude/hooks/`、`stage-1-init.md`、`stage-9-finalize.md` | 半天+半天+2小时+半天 | D2 | ✅ 完成 `673e1fc`（21 用例，含误伤率测试；递归漏洞按定案未强修） |

### P2 — 中等

| 编号 | 一行概述 | 涉及文件 | 工作量 | 所在文档 | 状态 |
|---|---|---|---|---|---|
| D1-0 | 删除 `issues.py` 两条死码位 | `issues.py` | 15 分钟 | D1 | ✅ 完成 `64f9738` |
| D1-8 | 阶段 4 骨架 docx 预确认 + H1/H2 锁定按 kind 分级裁决（`I-HDR-08`/`E-HDR-09`） | 新增 `outline_skeleton.py`、`headings.py`、`stage-4-outline.md` | 1.65 天 | D1 | ✅ 完成 `16a2a04`（13 用例；U7 硬前置已满足；section 全空时正确拒绝产出） |
| D2-5 | 补齐 failure_step 路由表（19 调用点二级键，修 `:210` 误导文案） | `finalizer_agent.md`、`finalize_pipeline.py` | 半天 | D2 | ✅ 完成 `6596016`（"回炉"文本 0→7 处） |
| D4-12 | 门禁名补齐 4 个 + "12 项/13 项"跨 4 处同步订正 | `multiagent-orchestration.md`、`finalizer_agent.md` | 1 小时 | D4 | ✅ 完成 `6596016`（"12 项交付清单"表述归零） |
| D3-4 | output 目录归档机制（首版只报告不移动） | `finalize_pipeline.py` | 半天 | D3 | ✅ 完成 `e9c4764`（含"按文件名判定会颠倒"反例断言） |

### P3 — 轻微 / 待决策

| 编号 | 一行概述 | 涉及文件 | 工作量 | 所在文档 | 状态 |
|---|---|---|---|---|---|
| D2-1~4 | 文档层护栏条文（**效力接近零，须补齐可粘贴原文**） | `SKILL.md`、`multiagent-orchestration.md` | 半天 | D2 | ✅ 完成 `6596016`（**可粘贴原文由本次撰写补齐**；反例第 21/22 条各只出现 1 次） |
| D4-3 | Tier 感知流程严格度（并入 §7.5 第三列，避免"二维"措辞冲突） | `multiagent-orchestration.md` | 半天 | D4 | ✅ 完成 `1bc50b9`（并入为 §7.5.1，未新开"第三维"） |
| D3-5 | 删除 `figure_gate.py:285-288` 无条件放行（真实项目 0 影响，纯清理） | `figure_gate.py` | 15 分钟 | D3 | ✅ 完成 `ac36bbf`（按方案要求不计入验收） |

---

## 九、配套文档

| 文档 | 内容 |
|---|---|
| `skill优化方案-D1标题体系修复.md` | 标题体系三重失效的完整故障链、键名契约定案、层级下沉方案、实测数据 |
| `skill优化方案-D2护栏体系.md` | orchestrator 纪律真空、护栏有效性残酷评估、三层护栏设计 |
| `skill优化方案-D3输出规范.md` | 交付产物治理、figure_gate 入口修复、端到端测试基建 |
| `skill优化方案-D4模型适配.md` | **为什么 DeepSeek V4 不遵守 skill 规定**（用户核心问题）、Tier 感知设计、存量问题合并 |
| `2026-07-29-SCIF报告编写问题记录.md` | 此前已记录的 11 个问题（基线，本次在其上补充） |
