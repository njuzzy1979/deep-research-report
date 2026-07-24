# md→docx 转换器 v2 —— P3 遗留缺陷修复设计（P-006 / P-007 / P-004）

> 产出方式：design-orchestrator 三层流水线（发现层独立核实根因 → 设计层给出可执行改动方案 → 审查层对抗性复核）
> 日期：2026-07-24 ｜ 状态：**待用户审批**（审批通过后交 execution-orchestrator / implementer 落地）
> 上游：`execution-progress.jsonl` 中 2026-07-24 登记的三项 P3 遗留问题（P-006/P-007/P-004，均 `status:"open"`）
> 权威接轨：与 `02-algorithms.md §C.3 / §C.3.1 R-FM / §D.4`、`00-master-design.md §4（R4/R14/R15/R18）`、`§7 分布式要求（G-02/G-10）` 完全对齐；本文档仅设计，不改动任何源代码或既有设计文档。
>
> **本文档只提出方案**。所有对 `02-algorithms.md`、`03-workflow.md`、`execution-progress.jsonl` 的落地修订，均待用户审批后由 execution-orchestrator 执行时统一进行。

---

## 0. 摘要与执行建议

本轮为三项 P3 遗留缺陷设计修复方案。发现层独立复现确认了三者的根因，并**修正/扩大了两处影响范围认定**：

- **P-006（前置件区起点判定过窄）**：确认。附带独立发现两处此前未记载的关联缺陷——(A) W-HDR-03 降级的第二个 H1 **其标题文本本身即被 builder 静默丢弃**（`builder.py:237` 按 token `level==1` 跳过，不看 kind），且其占用了 `chapter_index` 导致后续章号整体 +1；(B) 现行 R-FM 的**区间终止条件过严**，仅靠"显式章编号"终止，导致不带编号的正文首章（如 `## 军事需求与现状分析`）被误吞为 FRONT_MATTER——官方 `front-matter.md` 夹具正是因为**它的正文章全部无编号、被全部误吞**，才"意外"通过（详见 §2.3）。
- **P-007（渲染缺口区静默丢内容）**：确认，且**影响面显著大于原始描述**。缺口不限于"三节降级 + 首章前手动 `---`"，而是"**任何位于第一个 consuming 节 `start_element_index` 之前的元素**"都会被静默丢弃，涵盖四节方案（摘要 H2 前的游离段/`---`）与三节方案，且**不限于 PageBreakIR**——普通段落、乃至 P-006 修复后新产生的 FRONT_MATTER 标题（无摘要时）都会落入缺口丢失（详见 §3.2）。这使 P-007 与 P-006 产生**耦合**：先修 P-006 而不修 P-007，会把"编号错误"变成"内容丢失"，是更隐蔽的退化。
- **P-004（builder 自检 mock 脱节）**：确认，纯自检夹具问题，不涉及生产逻辑。

**执行顺序建议（详见 §6）**：**P-007 → P-006 → P-004**。P-007 是 P-006 的安全前置：P-006 修复会新增 FRONT_MATTER 元素并改变章序，若缺口未先堵住，无摘要报告的前言内容会从"被误编号"退化为"被静默丢弃"。P-004 独立、无依赖，随时可做。

---

## 1. 发现层：根因独立核实结论

三处根因均由发现层直接驱动代码复现确认（复现脚本见各问题小节的"复现证据"）。用户提供的定位准确；发现层在此基础上**补充了三处更深的关联缺陷与更大的影响面**，下文以核实结果为准。

| 问题 | 用户定位 | 核实结论 | 发现层补充 |
|------|---------|---------|-----------|
| P-006 | R-FM 起点仅在"首个 H1 命中前置词"激活；双 H1 下第二个 H1 走 W-HDR-03 降级分支从不判前置 | **确认** | +根因B：降级 H1 标题文本被 `builder.py:237` 静默丢弃且污染章序；+根因C：R-FM 终止条件过严误吞无编号正文章 |
| P-007 | 三节降级 + 首章前 `---` 时 EXPLICIT_HR 落 `body_start-1` 缺口被跳过 | **确认，影响面更大** | 缺口 = "首个 consuming 节 start 之前的**全部元素**"，含四节方案、普通段落、FRONT_MATTER 标题；与 P-006 耦合 |
| P-004 | mock 题注保留 `**` 字面量未设 `bold=True` → `_is_all_bold` False → 误判 APPENDIX | **确认** | 修复参照 `tables.py __main__` 测试4（447 行）现成写法 |

---

## 2. 问题一（P-006）：前置件区起点判定过窄 —— 双 H1 与无编号正文章双重误判

### 2.1 复现证据（发现层实测）

驱动 `classify_and_number()` 隔离复现（脚本 `/tmp/verify_p006.py`、`/tmp/verify_h1_downgrade.py`）：

**场景 B（标题 H1 + 前言 H1）** —— 输入 `# 深度研究报告` / `# 前言/导论` / 4 个无编号前言 H2 / 2 个正文章：

```
L1  MAIN_TITLE   ''      深度研究报告
L5  CHAPTER      第一章   前言/导论        ← 第二个 H1 走 W-HDR-03 降级，未判前置件
L9  CHAPTER      第二章   问题提出与研究背景  ← 前言 H2 被误编号（应为 FRONT_MATTER）
L13 CHAPTER      第三章   研究目标与意义
L17 CHAPTER      第四章   研究方法概述
L25 CHAPTER      第五章   军事需求与现状分析  ← 真实正文首章被挤到第五章
...
```

**关联根因 B（此前未记载）** —— W-HDR-03 降级的第二个 H1，其 `HeadingIR` 虽被 `classify_and_number` 产出为 CHAPTER，但 `builder.py` 步骤6（224-261 行）对 `HeadingToken` 先判 `if t.level == 1: continue`（237-239 行），**按 token 的 md 级别跳过，不看重编后的 kind**。实测：降级 H1 的标题文本 `独立第二标题TTT` 既不在 `elements` 也不在最终 docx，且它已令 `chapter_index += 1`，使其后的 `## 第一章 概述` 渲染成 `第二章 概述`。即**现行 W-HDR-03 降级路径本身是双重损坏的**（标题丢失 + 章序偏移），这是 P-006 修复必须一并处理的既有缺陷。

### 2.2 根因结构（三层）

1. **根因 A（起点判定，用户已定位）**：`classify_and_number()`（headings.py 476-512 行）中，只有 `if not h1_seen` 的首个 H1 分支调用 `_is_front_back(raw)` 决定 `in_front_matter`；`else`（多余 H1）分支无条件 W-HDR-03 降级 CHAPTER，从不检查前置词。
2. **根因 B（降级 H1 内容丢失 + 章序污染）**：`builder.py:237` 的 `if t.level == 1: continue` 把任何 md H1 token 排除出 `elements`，与"该 H1 已被重编为 CHAPTER 并应正常渲染"矛盾。
3. **根因 C（终止条件过严）**：R-FM 区间终止仅认 `_has_explicit_chapter_number` 或 `_RE_N07`（headings.py:548）。真实报告的正文首章若不带手动编号（如 `## 军事需求与现状分析`），无法触发终止，会被继续吞为 FRONT_MATTER（§2.3 详述）。

### 2.3 关键边界澄清：`front-matter.md` 官方夹具为何"能过"是假象

发现层对官方夹具做了完整 build→render 追踪（脚本 `/tmp/verify_fm2.py`）。夹具首个 H1 即 `# 前言/导论`（激活前置件区），其后所有 H2——**包括本应是正文的 `## 军事需求与现状分析` / `## 研究目标与技术指标`——全部被分类为 FRONT_MATTER**（因它们无显式章编号，未触发 R-FM 终止）：

```
[11] HeadingIR FRONT_MATTER  军事需求与现状分析   ← 夹具注释明写"正文第一章"，实际被吞为前置件
[13] HeadingIR FRONT_MATTER  研究目标与技术指标   ← 夹具注释明写"正文第二章"，同样被吞
```

夹具之所以"渲染无丢失、returncode=0"，恰恰是因为**它一个 CHAPTER 都没有**（`first_chapter_line=None` → `body_start=0` → BODY 节从 0 开始消费全部元素，无缺口）。也就是说：**官方夹具同时踩中根因 C（误吞正文章）却因此绕开了 P-007 缺口**——它验证的其实是一个退化场景，并非"前置件正确 + 正文正确"。这一点 P-002 修复时的 e2e 断言（"4 个前言 H2 未丢失、无第 X 章前缀"）为真，但**未覆盖"正文章应恢复编号"**，属测试盲区。P-006 的修复方案（§2.4 根因 C）会让夹具中的真实正文章恢复 CHAPTER 编号，因此**必须同步更新夹具的期望断言**（§2.6）。

### 2.4 设计方案

核心目标：让"标题 H1 + 前言 H1"结构正确激活前置件区，同时不破坏 W-HDR-03 语义、不误伤正文标题、不再误吞无编号正文章。分三个改动点，逐一给出精确逻辑。

#### 改动 P006-1：H1 前置件起点判定放宽至"结构受限的任一 H1"（headings.py `classify_and_number`）

将起点判定从"仅首个 H1"放宽为"**首个 H1，或紧随首个 H1 之后、在遇到任何 H2 之前出现的第二个 H1**"。用一个新状态位精确约束，避免"任意 H1 命中前置词即激活"带来的误伤。

改动逻辑（headings.py H1 分支，476-512 行）：

- 新增局部状态 `body_started`（bool，初值 False）：一旦处理到**任何 H2/H3/H4/H5/H6**（即进入正文/前置件内容层），置 True。
- 首个 H1 分支（`if not h1_seen`）：维持现状——`_is_front_back(raw)` 命中则 `in_front_matter=True`。**但补充**：若首个 H1 未命中前置词（是报告标题），记录一个标志 `title_h1_pending=True`，表示"允许下一个紧邻 H1 作为前置件起点"。
- 多余 H1 分支（`else`）改写为三分支判定：
  1. **若 `title_h1_pending and not body_started and _is_front_back(raw)`** → 该 H1 是"标题下的前言 H1"：置 `in_front_matter=True`；**不再降级为 CHAPTER，而是归为新的语义或 MAIN_TITLE 之外的前置件标题**（见下"降级 vs 前置"裁决）；**不发 W-HDR-03**（它不是"重复的正文章"，是被识别的前置件起点，发 W-HDR-03 会误导用户）；改发一条 INFO 级 `I-HDR-06`（新增码，见 §2.5）留痕"识别到标题后的前置件 H1，已作为前置件区起点"。
  2. **否则**（非前置词、或正文已开始、或 title_h1_pending 已消费）→ 维持现状：W-HDR-03 降级 CHAPTER（但其内容丢失问题由 P006-2 修复）。
- `title_h1_pending` 在"第二个 H1 被处理"或"body_started 置 True"后立即失效（一次性窗口），确保只有"标题 H1 紧邻前言 H1"这一种结构能激活，第三个及以后的 H1、或中间已插入 H2 后再出现的 H1，都走常规 W-HDR-03。

**"降级 vs 前置"裁决**：识别为前置件起点的这个前言 H1（如 `前言/导论`）本身应如何归类与渲染？三个候选：(a) 归 FRONT_MATTER（不编号，Heading 2 样式）；(b) 归 MAIN_TITLE 之外新增一个"前置件章标题"kind；(c) 保持 CHAPTER 但 in_front_matter 生效于其后 H2。**推荐 (a) 归 FRONT_MATTER**——理由：它语义上就是"前置件区的入口标题"，与其下辖的前言 H2 同属前置件、同为无编号；FRONT_MATTER 已在 `render/headings.py:_KIND_TO_LEVEL` 登记为 Heading 2（38 行），渲染路径现成；且 FRONT_MATTER 不占 `chapter_index`，天然避免章序污染。代价：它作为一个 md H1 却渲染为 Heading 2 级——但这是合理的，因为报告主标题（真正的 H1）已由 cover.py 单独渲染，正文流里不需要第二个 Heading 1 级大标题。**此裁决须在 §C.3.1 R-FM 增补小节明确记录**（§2.5）。

> 注：因 P006-1 把前言 H1 归为 FRONT_MATTER（level 语义为 H2），它**必然**触发 P006-2 才能进入 elements（否则被 `builder.py:237` 的 `level==1` 跳过而丢失标题文本）。这是 P-006 内部两改动的强依赖，也是 §6 把 P006-2 列为 P006-1 同批必做项的原因。

#### 改动 P006-2：builder 步骤6 的 H1 跳过条件从"看 token level"改为"看重编 kind"（builder.py 232-261 行）

将 `if t.level == 1: continue`（237-239 行）改为**仅跳过真正的 MAIN_TITLE**：先按 `t.source_line` 查到对应 `HeadingIR`（现有逻辑 242-243 行已在其后做，此处需前移查表），当且仅当 `hir.kind == HeadingKind.MAIN_TITLE` 时 `continue`（H1 主标题由 cover.py 渲染，正确排除）；其余情况（H1 被重编为 CHAPTER 或 FRONT_MATTER）照常走"入 elements"逻辑。

改动逻辑：
```
# 原：
#   if t.level == 1:
#       continue
#   key = t.source_line; hir = heading_index.get(key); ...
# 改为：
#   key = t.source_line
#   hir = heading_index.get(key)
#   if hir is not None and hir.kind == HeadingKind.MAIN_TITLE:
#       continue        # 仅主标题不入正文流（cover.py 渲染）
#   if hir is not None:
#       token_to_element_map[token_idx] = len(elements); elements.append(hir)
#   else: 防御 W-HDR-01（维持现状）
```

此改动**同时修复了两件事**：(1) P006-1 归为 FRONT_MATTER 的前言 H1 能正常入 elements 渲染；(2) **既有** W-HDR-03 降级 CHAPTER 的第二个 H1 从此不再静默丢失标题（这是发现层新发现的既有缺陷，顺带闭环）。注意章序污染问题——降级 CHAPTER 仍会 `chapter_index+=1`，这是 W-HDR-03 的既定语义（"降级为章"就应占章序），属正确行为；只有被 P006-1 改判 FRONT_MATTER 的前言 H1 不占章序，符合预期。

#### 改动 P006-3：R-FM 终止条件补充"遇到 ABSTRACT / 已离开前言语义"的收敛（headings.py 542-559 行，根因 C）

根因 C 是独立于双 H1 的既有缺陷：无编号正文首章会被前置件区无限吞并。但**收紧终止条件有误伤风险**——不能简单地"遇到任何无编号 H2 就终止"，否则前言区内本就允许多个无编号 H2。需要一个可解释、有边界的收敛信号。

设计权衡（两个候选）：

- **候选 C1（保守，推荐）**：**不在本轮扩大 R-FM 的自动终止能力**，维持"显式章编号 / 附录前缀"两个终止信号不变，仅通过 P006-1 让"标题+前言"结构能正确激活/关闭前置件区。对根因 C 的"无编号正文章被误吞"，**依赖既有的 W-HDR-05 之外新增一条 WARNING 提示**（`W-FM-01`，见 §2.5）："前置件区内已累计 N 个无编号 H2，若其中包含正文章请为正文首章添加显式编号（`第X章`/`一、`）以标示正文起点"。即：不猜测、只告警，把决定权交回作者（符合 §0.2 warn-and-keep 与"结构信号边界"哲学，不重新引入魔法数量上限）。
- **候选 C2（激进，不推荐本轮采用）**：引入"前置件区最多容纳到首个 ABSTRACT 之后的连续无编号 H2；一旦出现 ABSTRACT 之后的第二组无编号 H2 簇则终止"之类的启发式。这类规则难以证明无误伤，且与 §C.3.1"用结构信号而非启发式"的既定原则冲突。

**推荐候选 C1**。理由：根因 C 的本质是"作者未给正文章编号，转换器无可靠信号区分'又一个前言 H2'与'正文第一章'"——这在信息论上不可判定，唯一诚实的处置是告警而非猜测。C1 零误伤、可解释、与 R-FM"换报告零改码"哲学一致。**代价**：官方 `front-matter.md` 夹具（正文章全无编号）在 C1 下**行为不变**（正文章仍归 FRONT_MATTER），但会多出一条 `W-FM-01` 告警。因此 §2.6 的夹具修订采用"给夹具的正文章补上显式编号"，使夹具真正演示"前置件 + 正文"的正确分层，同时消解 P-007 耦合（见 §3 与 §2.3）。

> **裁决点留给用户**：若用户希望转换器对"无编号正文章"也能自动分层（候选 C2 方向），需单独立项设计并通过对抗性评审——本轮不建议，理由如上。§7 未解决问题登记此裁决点。

### 2.5 设计文档更新点（02-algorithms.md）

以下为待 execution-orchestrator 落地的 `02-algorithms.md` 修订清单（本轮不改，仅登记）：

1. **§C.3.1 R-FM 增补子条 "R-FM 起点扩展（标题+前言双 H1）"**：记录 P006-1 的起点放宽规则（"首个 H1，或标题 H1 紧邻的前置词 H1"）、一次性窗口 `title_h1_pending`、"降级 vs 前置"裁决（前言 H1 归 FRONT_MATTER、不发 W-HDR-03、改发 I-HDR-06）、以及与 W-HDR-03 的边界（第三个 H1 及正文已开始后的 H1 仍走 W-HDR-03）。
2. **§C.3.1 索引一致性要求段补充**：追加 builder 步骤6 的 kind 敏感跳过规则（P006-2）——"H1 token 是否入 elements 由重编 kind 决定（仅 MAIN_TITLE 跳过），不由 md level 决定"，并注明这同时修复了 W-HDR-03 降级 H1 的既有内容丢失。
3. **§C.3.1 终止条件段补充**：记录候选 C1 裁决——终止信号维持"显式章编号 / 附录前缀"两项不变；新增 `W-FM-01` 告警语义（前置件区无编号 H2 累计提示）；显式声明"无编号正文章自动分层"为**已知限制**（指向 §7）。
4. **§0.3 Issue 代码总表新增两码**：
   - `I-HDR-06`（INFO）："识别到标题后的前置件 H1（如'前言/导论'），已作为前置件区起点，未按多余 H1 降级" —— 出处：本文档 §2.4 P006-1。
   - `W-FM-01`（WARNING）："前置件区内累计 N 个无编号 H2；若含正文章请为正文首章补显式编号以标示正文起点" —— 出处：本文档 §2.4 P006-3 候选 C1。
   （核对现有占用：`I-HDR-*` 与 `W-FM-*` 前缀在 §0.3 与 issues.py 中均未占用，无冲突。issues.py 的 `IssueCodeInfo` 注册表须同步加这两码。）
5. **§C.6 推演表更新**：新增两行——"`# 深度研究报告` + `# 前言/导论` + 无编号前言 H2 → 前言 H1 归 FRONT_MATTER（I-HDR-06），前言 H2 归 FRONT_MATTER，遇显式 `第X章` 终止"；"降级第二个 H1（非前置词）→ CHAPTER 且标题文本正常入 elements（P006-2）"。

### 2.6 测试计划（红绿验证）

新增测试（`tests/test_integration.py` 或 `assemble/headings.py __main__`）：

| 用例 | 输入 | 修复前 | 修复后（期望） |
|------|------|--------|--------------|
| T-P006-1 双H1起点(IR层) | `#标题` + `#前言/导论` + 3无编号H2 + `##第一章X` | 前言H2=第一/二/三章 | 前言H1+3个H2 全 kind==FRONT_MATTER；`第一章X`==CHAPTER 且 display=='第一章' |
| T-P006-2 降级H1不丢内容(e2e) | `#标题` + `#独立标题TTT`(非前置词) + `##摘要` + `##第一章` | docx 无 'TTT'，章序 +1 | docx 含 'TTT'（W-HDR-03 仍发）；`第一章`仍为第一章 |
| T-P006-3 前言H1渲染(e2e) | 同 T-P006-1 | 前言H2 带"第X章"前缀 | docx 中前言H1与前言H2 均为无编号 Heading2 段落 |
| T-P006-4 W-FM-01告警 | 前置件区含 >=1 无编号 H2 且无显式章号正文 | 无告警 | 产出 W-FM-01 |
| T-P006-5 三H1不误激活 | `#标题` + `#前言` + `##摘要` + `#又一个H1` | — | 第三个 H1 走 W-HDR-03（回归保护，验证一次性窗口） |
| **夹具更新** front-matter.md | 给 `军事需求与现状分析`/`研究目标与技术指标` 补 `第一章`/`第二章` 前缀 | 二者=FRONT_MATTER | 二者==CHAPTER 且编号连续；前 4 前言 H2 仍 FRONT_MATTER；同步改 `test_front_matter_not_numbered_ir_level` 断言 |

**红验证要求**（守 P-002 的红绿纪律）：注入根因A（还原"仅首个H1判前置"）→ T-P006-1 红；注入根因B（还原 `if t.level==1: continue`）→ T-P006-2/3 红。

---

## 3. 问题二（P-007）：渲染缺口区静默丢弃元素 —— 影响面远大于原始描述

### 3.1 复现证据（发现层实测）

驱动 `_compute_section_ranges` 与完整 build→render（脚本 `/tmp/verify_p007.py`、`/tmp/verify_4sec_gap.py`、`/tmp/verify_interaction.py`）：

- **三节降级 + 首章前手动 `---`**：`PageBreakIR(EXPLICIT_HR)` 落 token index 0，consuming range 从 1 起，index 0 落缺口 → 丢弃（复现用户原始场景）。
- **四节 + 摘要 H2 前游离段落**：`ParagraphIR('摘要前游离段落ZZZ独特')` 落 index 0，ABSTRACT 节 start=1，index 0 落缺口 → **docx 中确认丢失**。证明缺口**不限 PageBreakIR、不限三节方案**。
- **前置件区激活 + 无摘要 + FRONT_MATTER 标题（P-006 修复后的典型形态）**：`研究背景说明`(FRONT_MATTER 标题) + `前言正文QQQ` 落 index 0/1，BODY 节 start=2，二者落缺口 → **docx 中确认丢失**。这是 P-006↔P-007 耦合的直接证据。

### 3.2 根因结构

`render/document.py:_compute_section_ranges`（92-113 行）只为 `ABSTRACT`/`BODY` 两种 consuming 节生成消费区间；`COVER`/`TOC` 节内容由 `render_cover`/`render_toc` 独立合成、**完全不消费 `ir.elements`**。`render_document`（232-269 行）逐节按 range 渲染，**任何 index < 首个 consuming 节 `start_element_index` 的元素，不落任何 range，被整体跳过**——既不渲染、也不产 Issue（连 `_dispatch_body_element` 的 I-DOC-01 兜底都到不了，因为压根没进入分派循环）。这是纯粹的"范围切片漏底"，与 gate3 计数无关。

**缺口何时非空**（发现层枚举的全部触发路径）：
- 首个 consuming 节的 `start_element_index > 0` 时，`[0, start)` 区间的所有元素即缺口内容。等价条件：**在"摘要 H2（四节）/ 首章 H2（三节）"之前，存在任何进入 `elements` 的块**。
- 已确认的产生源：(1) 首章/摘要前的手动 `---`（→ EXPLICIT_HR）；(2) H1 与摘要之间的游离段落（如夹具 front-matter.md 的 `本文档用于验证...`，四节方案下也会丢——只是官方夹具恰好因 `body_start=0` 而未触发）；(3) P-006 修复后、无摘要报告中首章前的 FRONT_MATTER 标题及其正文段落；(4) 三节方案中首章前的任何段落。

### 3.3 设计方案

用户提出的三个核心问题 (a)(b)(c)，逐一回答并给出方案。

#### (a) 缺口区影响范围结论

**比原始描述广**：不是"三节 + 手动 `---`"的孤例，而是"首个 consuming 节 start 之前的一切元素"的系统性漏底，四节方案同样中招，且与 P-006 强耦合（§3.1 第三条）。因此 P-007 不能当作"分页计数小瑕疵"处理，而是**内容完整性缺陷**，优先级实质高于其 P3 定级——建议随 P-006 一并修复（§6）。

#### (b) 修复落点：`document.py` 渲染层（推荐），而非仅 `breaks.py`

两条思路对比：

| 思路 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **思路①（推荐）渲染层堵缺口** | 改 `_compute_section_ranges`：让**第一个 consuming 节的起始扩展到 0**（即首个 consuming 节"向前吞并"所有 index < 其原 start 的前导元素），使缺口区元素并入紧邻的第一个内容节渲染 | 根治所有触发路径（含普通段落、FRONT_MATTER、PageBreakIR）；不改 breaks.py 四步流水线；不动 R4/PB-A~D 设计；单点改动 | 需明确前导元素的"归属节"语义（见下） |
| 思路②仅规划层清理 | 改 `breaks.py`：把会落缺口的 PageBreakIR 在规划期删除/合并 | 让规划值"诚实" | **只能处理 PageBreakIR，无法挽救缺口里的段落/标题**——对 §3.1 的段落丢失、FRONT_MATTER 丢失完全无效；治标不治本 |

**推荐思路①**，因为只有它能覆盖"非 PageBreakIR 的缺口内容"。思路②对 PageBreakIR 计数一致性有帮助，但不能单独作为 P-007 的修复（会漏掉内容丢失主症）。

**思路①的精确语义**（`_compute_section_ranges` 改法）：
- 现状：`consuming = [(plan_idx, start) for 每个 ABSTRACT/BODY 节]`，range 从各自 start 到下一个 consuming 节 start（或 total）。
- 改为：**将 `consuming` 列表中第一个元素的起始 `start` 强制置为 0**（`consuming[0] = (consuming[0][0], 0)`）。这样第一个 consuming 节（四节=ABSTRACT、三节=BODY）的 range 变为 `[0, next_start)`，把所有前导缺口元素纳入它渲染。
- **归属语义**：前导元素（手动 `---`、H1 后游离段、FRONT_MATTER 标题/段落）并入**第一个有内容的节**渲染。对四节方案，它们进 ABSTRACT 节（在"摘要"标题之前渲染）；对三节方案，进 BODY 节。这在版式上是合理的——这些内容本就应出现在正文/摘要区起始处，且它们位于封面之后、目录之前的自然阅读位置由节内元素顺序保证。
- **边界**：若无任何 consuming 节（理论不出现，SectionPlan 至少有 BODY），维持现状 early-return 保护。若首个 consuming 节 start 本就是 0（如官方 front-matter.md、multi-chapter.md），改动是恒等变换，**零回归**。

> **PageBreakIR 落缺口的副作用**：思路①让缺口里的 EXPLICIT_HR 也进入渲染 → `doc.add_page_break()` 被调用。需评估这个"首章/摘要前的手动分页"是否产生多余空白页。分析：它位于封面节之后、第一个内容节开头——封面节与第一个内容节之间**已有一个 Word 分节符（sectPr, nextPage）产生换页**，紧接着再 add_page_break 会多一张空白页。因此思路①须与下述 (c) 的 breaks.py 侧清理**配合**：对"位于首个 consuming 节之前的 EXPLICIT_HR"，在 breaks.py 规划阶段就地移除并记 `I-PB-03`（分节符吸收留痕，该码已存在，语义正好匹配），使段落/标题被渲染层挽救、而多余分页被规划层消除。**即最终方案是"思路① 渲染层堵缺口（挽救内容）+ breaks.py 清理缺口内 PageBreakIR（消除多余分页并让规划诚实）"两者并用**——各司其职、互补，不是二选一。

#### (c) breaks.py 侧清理 + gate3 R15 + 新增提示 Issue

- **breaks.py 改动 P007-1**：在 SectionPlan 生成后、返回前，新增一步 **PB-E（缺口清理）**：定位第一个 consuming 节的 `start_element_index`（token 空间），移除 `deduped` 中所有 index < 该 start 的 `PageBreakIR`，每移除一个记一条 `I-PB-03`（"位于首个内容节之前的显式分页被分节符换页吸收，未重复触发分页"）。这使"规划的 PageBreakIR 数"与"渲染实际消费的 PageBreakIR 数"重新对齐（gate3 R15 期望值恢复诚实），同时消除多余空白页。**注意**：PB-E 只清理 PageBreakIR，段落/标题类前导元素仍由思路①渲染层挽救——两者不重叠。
- **gate3.py R15（`_check_page_breaks`）是否需改**：**不需要改计数逻辑本身**。R15 的期望值 `len([PageBreakIR in ir.elements])`（gate3.py:188-192）在 PB-E 清理后会自动与渲染实况一致（缺口内 PageBreakIR 已从 elements 移除），R15 恢复 PASS。这印证了用户判断——"根因在渲染层元素范围，不在 gate3 计数"。**唯一建议的强化**（可选）：在 R15 失败详情里追加一句诊断提示"若差值来自首个内容节之前的元素，检查 PB-E 缺口清理是否生效"，便于未来定位，但非必需。
- **新增提示 Issue P007-2**：为避免"用户手动 `---` 或前导内容被移动/吸收却毫无提示"，除 PB-E 的 `I-PB-03` 外，当**渲染层思路①实际吞并了非空前导区**（存在 index < 首个 consuming 节原 start 的**非 PageBreakIR** 元素）时，产出一条 `W-SEC-02`（新增 WARNING 码）："检测到 N 个位于首个内容节之前的前导元素（标题/段落），已并入首个内容节渲染，请确认其位置符合预期"。这条告警落在 builder 或 document 层（建议 builder 步骤6 后处理，紧邻 `_remap_section_indices`，那里能同时看到 elements 与 section start，且属 assemble 阶段、Issue 时序更早）。

### 3.4 设计文档更新点（02-algorithms.md / 03-workflow.md）

1. **§D.4 分页语义规则新增 PB-E**：在 PB-A~D 四步之后增第五步"PB-E 缺口清理"，描述"移除位于首个 consuming 节之前的 PageBreakIR + I-PB-03"，并注明与 R4 分节符接管的关系（分节符已换页，前导显式分页冗余）。同时在 §D.4 显式声明"前导非分页元素由渲染层 `_compute_section_ranges` 归入首个内容节，见 01/document 渲染约定"。
2. **§0.3 新增 `W-SEC-02`（WARNING）**：语义如 §3.3(c)。核对占用：`W-SEC-*` 前缀未占用（现有 `E-SEC-01`），无冲突。issues.py 同步注册。
3. **§B.2 说明微调（可选）**：P-007 与 §B.2 无直接关系，但若前导区含"孤立题注"类元素，其渲染归属由思路①统一处理，无需 §B.2 改动。
4. **03-workflow.md 边界样本清单**：新增两条边界样本——"四节方案 + 摘要 H2 前游离段"、"三节方案 + 首章前手动 `---`/前导段"，期望"前导内容不丢失、无多余空白页、gate3 R15 PASS、产出 I-PB-03/W-SEC-02"。（现清单已有第16项 `--no-appendix-page-break`，本轮续编号第17/18项。）

### 3.5 测试计划（红绿验证）

| 用例 | 输入 | 修复前 | 修复后（期望） |
|------|------|--------|--------------|
| T-P007-1 三节首章前`---`(e2e) | 三节方案 + 首章前 `---` | gate3 R15 Fatal（IR6/docx5）或分页丢失 | 无多余空白页；gate3 R15 PASS；I-PB-03 记录 |
| T-P007-2 四节摘要前游离段(e2e) | 四节 + `#标题` 与 `##摘要` 间一段独特文本 | docx 无该段（静默丢失） | docx 含该段；W-SEC-02 告警 |
| T-P007-3 前置件+无摘要(e2e，P-006耦合) | 前言H1激活 + 无摘要 + FRONT_MATTER标题+段落 + `##第一章` | FRONT_MATTER 标题与段落丢失 | 全部内容出现在 docx；W-SEC-02 告警 |
| T-P007-4 恒等无回归 | 官方 multi-chapter.md（首个consuming start=0） | 正常 | 逐段与修复前 docx 一致（回归保护） |
| T-P007-5 R15 计数诚实 | T-P007-1 同输入 | R15 期望≠实况 | R15 期望==实况（PB-E 生效后） |

---

## 4. 问题三（P-004）：builder 自检 mock 未遵循 inline parser 产物形状

### 4.1 复现证据（发现层实测）

运行 `python -m md2docx.assemble.builder`：`[FAIL] table_registry 含正文表 -- 实际 0`，18 通过 / 1 失败。根因确认：mock 题注段（builder.py:518-523）为 `InlineRun(text="**表1-1 产业链上中下游环节对比表**")`——`**` 是字面量、`bold` 未设 True。`resolve_tables` 的 `_is_all_bold(prev_token)`（tables.py:217）返回 False（run 的 `bold` 非 True），题注检测失败 → 表被判 `TableKind.APPENDIX` → `table_registry`（仅注册 BODY 表）为空 → 断言 FAIL。纯自检夹具与真实 parse 产物形状脱节，不涉生产逻辑（`git stash` 确认 HEAD 即存在，真实路径由 with-table 集成测试 + 咖啡金标准 IR 测试覆盖正常）。

### 4.2 设计方案（改动 P004-1）

比照 `tables.py __main__` 测试4（447 行）的现成正确写法，修正 builder.py:518-523 的 mock 题注段：

```
# 现状（错误）：
#   ParagraphToken(runs=[InlineRun(text="**表1-1 产业链上中下游环节对比表**")], source_line=35)
# 改为（遵循 inline parser 产物形状：无 ** 字面量，bold=True）：
#   ParagraphToken(runs=[InlineRun(text="表1-1 产业链上中下游环节对比表", bold=True)], source_line=35)
```

即：去掉两端 `**` 字面量、对该 `InlineRun` 设 `bold=True`。这样 `_is_all_bold` 返回 True、`_RE_TBL_CAPTION_TEXT`（无 `**` 的纯文本正则）匹配成功 → 表判 BODY → `table_registry` 含 `1-1` → 断言 PASS。

**防未来再脱节**：将 builder.py:515-517 现有的那段**误导性注释**（"实际 parse 阶段产出的 ParagraphToken 中 ** 为字面量文本（未转为 bold 布尔属性），此处模拟该行为"——这句话本身就是错误认知的来源）**改写为正确约定说明**：

```
# mock 数据必须遵循 inline parser（阶段2）产物形状约定：Markdown 的 **...**
# 语法已被消耗为 InlineRun.bold=True，纯文本不再含 ** 字面量。题注检测
# （tables.resolve_tables）依赖 _is_all_bold + 不含 ** 的 RE_TBL_CAPTION_TEXT，
# 故加粗题注须写为 InlineRun(text="表X-Y 标题", bold=True)（参见 tables.py
# __main__ 测试4 / 顶部注释 19-27 行 / 02-algorithms.md §B.2）。
```

并在断言处（builder.py:713-714 `table_registry 含正文表`）加一行注释指明"若此断言 FAIL，首查 mock 题注段是否遵循上述产物形状约定"，形成自解释护栏。

### 4.3 设计文档更新点

P-004 是自检夹具修正，**不涉及 02-algorithms.md 算法规格变更**，无需改设计文档。仅需在 `execution-progress.jsonl` 落地时把 P-004 标 `status:"closed"`，resolution 引用本节。

### 4.4 测试计划

无需新增测试用例——修复对象即 builder.py `__main__` 自检本身。验证方式：修复后 `python -m md2docx.assemble.builder` 应 19 通过 / 0 失败（`table_registry 含正文表` 转 PASS）。红绿：还原 `**...**`+无 bold 写法 → 该断言复现 FAIL。

---

## 5. 审查层：对抗性复核

对三方案逐一红队审查：是否引入新回归、是否与既有规则冲突、是否触碰硬约束。

### 5.1 P-006 方案审查

| 攻击向量 | 分析 | 结论 |
|---------|------|------|
| 起点放宽是否误伤"正文中含'前言'字样的章"？ | P006-1 的一次性窗口 `title_h1_pending` 要求：必须是**紧邻首个 H1 的第二个 H1**、**正文未开始**（无 H2 出现过）、**且 `_is_front_back` 整词/复合全命中**（§2.4 复用现有 `_is_front_back`，其误伤边界已在 §C.3.1 五例论证）。正文里的普通章是 H2 不是 H2 之前的 H1，进不了该窗口。 | 无误伤 |
| 与 W-HDR-03 冲突？ | 仅"标题后紧邻前置词 H1"这一窄结构改走前置分支（发 I-HDR-06 不发 W-HDR-03）；其余多余 H1 完全维持 W-HDR-03。语义边界清晰、可解释。 | 协调，不冲突 |
| P006-2 改 builder H1 跳过条件，是否让 MAIN_TITLE 漏进正文流？ | 改后**仅** `kind==MAIN_TITLE` 跳过，判定比原 `level==1` 更精确（原逻辑连被降级的 CHAPTER H1 都误跳）。MAIN_TITLE 仍被正确排除。 | 更安全 |
| P006-2 是否影响 G-08（IR 内容字段无默认值）等分布式要求？ | 不涉及 IR 字段定义，仅改 builder 遍历分支。查表键仍是 source_line（P-002 已确立的单键）。 | 无影响 |
| 候选 C1 保留"无编号正文章被吞"，是否算未修完？ | 是**有意的**保守裁决（§2.4）——信息不可判定场景只告警不猜测。已登记为已知限制 + 用户裁决点（§7）。 | 可接受，需用户确认 |
| 夹具断言更新是否掩盖真实回归？ | front-matter.md 补编号后，`test_front_matter_not_numbered_ir_level` 的前 4 前言 H2 断言不变（仍 FRONT_MATTER），仅新增"正文章恢复 CHAPTER"断言——是**增强**而非放宽。P-002 的红绿注入仍有效。 | 增强覆盖 |

### 5.2 P-007 方案审查

| 攻击向量 | 分析 | 结论 |
|---------|------|------|
| **G-02 硬约束**（add_page_break 仅 document.py）是否被触碰？ | 思路① 不新增 add_page_break 调用点——它只是扩大首个 consuming 节的 range，缺口内元素经既有 `_dispatch_body_element` 分派，PageBreakIR 仍在**同一** document.py:158 唯一消费点触发。PB-E 在 breaks.py 只**删** PageBreakIR，不调 add_page_break。 | G-02 不破坏 |
| **G-10**（分页账目单一事实源=breaks.py；门3只做实况=规划比对）是否被破坏？ | PB-E 让 breaks.py 的规划结果（移除缺口 PageBreakIR 后）与渲染实况重新一致，正是**强化** G-10，不是绕过。gate3 R15 逻辑零改动。 | G-10 强化 |
| 思路①把前导 `---` 分页交渲染 + PB-E 又删它，会不会打架（重复处理）？ | 不会：PB-E 在 breaks.py 规划期就把缺口内 PageBreakIR 从 elements 移除，故渲染层 range 扩大后，那个位置已无 PageBreakIR 可渲染；渲染层只接管**非 PageBreakIR** 前导元素。职责严格互补、无重叠。 | 一致 |
| 前导元素并入 ABSTRACT 节，是否让它们错误地拿到罗马页码/摘要页眉？ | 是的，它们会落在 ABSTRACT 节的页码/页眉体系内（罗马数字、TITLE_SHORT 页眉）。对"H1 后游离段"这类前导内容，位于摘要区起始处渲染、用罗马页码，是可接受的版式（它们本就是前置内容）。**但需在 §3.4 文档与 W-SEC-02 告警中明示这一归属**，让用户知晓。 | 可接受，需告警明示 |
| PB-A~D 四步流水线（§D.4）被改动？ | 仅**追加** PB-E 第五步，不改 PB-A~D 任一步。R4 分节符接管（PB-B 前置条件）不动。 | 增量，不破坏 |
| 官方夹具回归？ | multi-chapter.md/with-table.md/minimal.md 的首个 consuming 节 start 本就是 0（无摘要且无前导，或摘要即首元素），思路①对它们是恒等变换。T-P007-4 专门守此回归。 | 零回归（须测试守住） |

### 5.3 P-004 方案审查

| 攻击向量 | 分析 | 结论 |
|---------|------|------|
| 改 mock 是否掩盖生产真 bug？ | 否。生产 `resolve_tables` 逻辑正确（要求 bold=True 是对的，因真实 inline parser 确实产出 bold=True）；错的是 mock 违背该约定。真实路径由 with-table 集成 + 咖啡金标准覆盖。改 mock 使自检与真实一致，是修正测试假阴性。 | 纯自检修正 |
| 是否触碰反硬编码（check_no_hardcode）？ | mock 题注文本仍是业务字面量，但位于 `__main__` 自检块——check_no_hardcode 的上下文分类器已豁免 `__main__`（见 execution-progress C-15-scanner 记录）。不新增违规面。 | 无影响 |

### 5.4 三方案交叉依赖与优先级

- **P-007 必须先于（或同批于）P-006**：P-006 修复会新增 FRONT_MATTER 元素并可能使无摘要报告的首个 consuming 节 start > 0，若 P-007 缺口未先堵，P-006 会把"前言被误编号"退化为"前言内容静默丢失"（§3.1 第三条实测证明）。这是**硬依赖**（CONTRADICTION 级：不先修 P-007，P-006 引入更严重的内容丢失回归）。
- **P-004 无依赖**：独立自检夹具，任意顺序。
- 三者均落在已核实的既有代码上，无一需要回炉重设计。

---

## 6. 建议执行顺序与涉及文件清单

### 6.1 执行顺序（拓扑）

```
P-004（独立，可并行/任意时点）
P-007  ──先于──▶  P-006
  │                 │
  └── 二者同批提交测试，确保 P-006 引入的 FRONT_MATTER 内容不落回缺口
```

推荐批次：**批次一 = P-007（含 PB-E + 渲染层堵缺口 + W-SEC-02）；批次二 = P-006（P006-1/2/3 + 夹具更新，依赖批次一已堵缺口）；P-004 随任一批次搭车**。每批次内先红后绿、跑全量 pytest + 三个 `__main__` 自检 + check_no_hardcode + gate3。

### 6.2 涉及文件清单（结构化，供 execution-orchestrator 消费）

| 改动ID | 目标文件 | 函数/位置 | 内容 | 依赖 | 关键路径 | 验收标准 |
|--------|---------|----------|------|------|:---:|---------|
| P007-1 | `assemble/breaks.py` | `plan_breaks_and_sections` 尾部（SectionPlan 生成后） | 新增 PB-E：移除首个 consuming 节 start 之前的 PageBreakIR，每个记 I-PB-03 | 无 | ✓ | T-P007-1/5 绿；gate3 R15 期望==实况 |
| P007-2 | `render/document.py` | `_compute_section_ranges`（92-113） | 首个 consuming 节起始强制置 0，吞并前导缺口元素 | P007-1 | ✓ | T-P007-2/3 绿；T-P007-4 零回归 |
| P007-3 | `assemble/builder.py` | 步骤6 后处理（`_remap_section_indices` 邻近） | 检测非空非分页前导区 → 产 W-SEC-02 | P007-2 | | 前导段落存在时产 W-SEC-02 |
| P007-4 | `issues.py` | `IssueCodeInfo` 注册表 | 新增 W-SEC-02 | — | | 码注册且有出处 |
| P006-1 | `assemble/headings.py` | `classify_and_number` H1 分支（476-512） | title_h1_pending 一次性窗口 + 前言H1归FRONT_MATTER + I-HDR-06 不发W-HDR-03 | P007-* | ✓ | T-P006-1/5 绿 |
| P006-2 | `assemble/builder.py` | 步骤6 H1 分支（237-243） | 跳过条件改为 `kind==MAIN_TITLE`（不再按 level==1） | P006-1 | ✓ | T-P006-2/3 绿；降级H1不丢内容 |
| P006-3 | `assemble/headings.py` | `classify_and_number` 前置件累计 + 收尾 | W-FM-01 告警（无编号H2累计提示）；终止条件维持不变（候选C1） | P006-1 | | T-P006-4 绿 |
| P006-4 | `issues.py` | `IssueCodeInfo` 注册表 | 新增 I-HDR-06、W-FM-01 | — | | 两码注册且有出处 |
| P006-5 | `tests/test_fixtures/front-matter.md` + `tests/test_integration.py` | 夹具 + 断言 | 正文章补显式编号；断言正文章恢复CHAPTER、前言H2仍FRONT_MATTER | P006-1..3 | ✓ | 夹具 e2e 前置/正文分层正确 |
| P004-1 | `assemble/builder.py` | mock 题注段（518-523）+ 注释（515-517）+ 断言注释（713-714） | 题注改 `bold=True` 无 `**`；注释改为正确产物形状约定说明 | 无 | | `python -m ...builder` 19/0 |
| DOC-1 | `02-algorithms.md` | §C.3.1 / §0.3 / §C.6 / §D.4 / §B.2 | 落地 §2.5 + §3.4 全部文档更新点（**用户审批后由执行编排器改**） | 全部 | | 编号无冲突、术语接轨 R-FM |
| DOC-2 | `03-workflow.md` | 边界样本清单 | 新增第17/18项边界样本 | P007-* | | 清单含缺口场景 |
| DOC-3 | `execution-progress.jsonl` | append | P-004/P-006/P-007 FIX + status 更新 + 门禁快照（**执行时 append**） | 全部 | | 三问题 closed 留痕 |

### 6.3 新增 Issue 码汇总（核对无冲突）

| 码 | 级别 | 语义 | 归属问题 | 出处 |
|----|------|------|---------|------|
| I-HDR-06 | INFO | 识别标题后的前置件 H1 作为前置件区起点（未按多余H1降级） | P-006 | 本文档 §2.4 |
| W-FM-01 | WARNING | 前置件区累计 N 个无编号 H2，含正文章请补显式编号 | P-006 | 本文档 §2.4 C1 |
| W-SEC-02 | WARNING | 首个内容节之前的前导元素已并入首节渲染，请确认位置 | P-007 | 本文档 §3.3(c) |

（`I-PB-03` 复用现有码，语义匹配，不新增。核对：`I-HDR-*`/`W-FM-*`/`W-SEC-*` 前缀在 §0.3 与 issues.py 均无占用；`E-SEC-01` 已存在但序号不冲突。）

---

## 7. 未解决问题（需用户决策）

| # | 问题 | 建议 | 待用户裁定 |
|---|------|------|-----------|
| U-1 | **根因 C 是否本轮扩展 R-FM 自动分层能力**（候选 C2：对"无编号正文章"启发式分层） | 本轮采**候选 C1**（只告警不猜测），因无编号正文章与前言 H2 信息论不可判定，启发式难证无误伤 | 是否认可 C1，将 C2 列为独立后续立项？ |
| U-2 | **前导元素并入首个内容节的页码归属**（四节方案下前导内容落 ABSTRACT 节 → 罗马页码 + 摘要页眉） | 接受该归属（前导内容本属前置区），以 W-SEC-02 告警明示 | 是否认可此版式归属？ |
| U-3 | **P-007 实际定级** | 发现层认定其为**内容完整性缺陷**（静默丢内容），实质重于 P3；建议与 P-006 同批优先修复 | 是否同意提升处置优先级（不必改 P3 标签，但排入本轮必修）？ |

---

## 8. 附：发现层复现脚本索引（临时，非交付物）

| 脚本 | 验证内容 | 关键结论 |
|------|---------|---------|
| `/tmp/verify_p006.py` | 双H1场景分类 | 前言H2被编为第一~四章 |
| `/tmp/verify_h1_downgrade.py` | W-HDR-03降级H1 | 标题文本丢失 + 章序+1（根因B） |
| `/tmp/verify_p007.py` | 三场景token流缺口 | 缺口含PageBreakIR/段落/FRONT_MATTER |
| `/tmp/verify_4sec_gap.py` | 四节摘要前游离段 | docx确认丢失 |
| `/tmp/verify_interaction.py` | 前置件+无摘要 | FRONT_MATTER标题+段落确认丢失（P-006↔P-007耦合） |
| `/tmp/verify_fm2.py` | 官方夹具追踪 | 正文章全被误吞FRONT_MATTER，因无CHAPTER而绕开缺口 |

> 上述脚本为发现层核实工具，随环境清理即可，不纳入 `tests/`。正式测试用例见 §2.6 / §3.5 的 T-P006-* / T-P007-* 设计。
