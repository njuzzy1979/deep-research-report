# deep-research-report 跨模型兼容性优化实施方案

> **版本**：V1.2（已完成审查层修订 + §九清单全覆盖验证）→ **V1.3（已执行完成）**
> **日期**：2026-07-28（方案定稿）／2026-07-29（执行完成）
> **状态**：✅ **已执行完成** —— 全部 9 个批次落盘，281 项测试通过。执行结果详见文末「**十四、执行结果记录**」
> **基于**：`design/model-compatibility-audit-report.md`（30 项发现：P0×7 / P1×14 / P2×9）
> **方法**：发现层三 Agent 并行 → 设计层三 Agent 并行 → 交叉整合与矛盾裁决（§13）→ 对抗性审查 + 定向修订 → **§九改动清单 43/43 项逐条实跑验证** → **分批执行 + 逐批门禁（G1/G3/G4）+ 收尾聚合复核（G6）与端到端验证（G7）**
> **目标**：让本 skill 在 **DeepSeek V3.2 级别及以上**模型上可靠运行，**同时不削弱 Claude 系列上已验证的质量**
>
> **⚠️ 执行期的重要变更（详见 §十四）**：
>
> | 项 | 变更 |
> |---|---|
> | **A1 第 3 项「编号取真值」** | **裁决为不做**（方案甲）。`headings.py` Phase 7b 保持原样，H4 编号按文档序重算 |
> | **A1 新增必改点** | 方案遗漏了 `outline_reader.py:151-155` 的守卫条件 `parent_title in lookup`——不改则字段名修复仍 100% 失效 |
> | **C2/C6 两处 P0 冲突** | 执行中**新暴露**：`contract_check.py` 会把合并管道自身的正确产出判为 fatal，导致交付门禁永远无法通过。已修复（分别加章容器豁免与分阶段判定） |
> | **stdout 4 处** | 位置随 C3 改动漂移，其中 2 处已被 C3 的红线 A1 前瞻兼容措辞消化 |
> | **nonce 联动面** | 方案记 18 文件/48 处，实测为 **19 文件/49 处**（多出第 3 批新建的 `output_envelope_check.py`） |
> | **`diagram_agent` 残留** | 方案记 4 处，实测为 **7 个文件** |
>
> **✅ V1.1 → V1.2：§九改动清单全覆盖验证**
>
> 对 §九 全部 **43 项**（新增 19 + 修改 24）逐条实跑核实路径、行号、现状描述，并全库 grep 检索遗漏联动点。**发现并已修正 4 处问题**：
>
> | 编号 | 问题 | 修正 |
> |---|---|---|
> | V-1 | 新增表 #1 与 #18 重复（同为 `model-profile.json`） | 删除 #18，全表重编号 |
> | **V-2** | #19 声称 `headings.py:158-161` 是 parent 匹配，**实为中文数字解析函数**；且遗漏 `headings.py:557-591` **Phase 7b 会覆盖 A1 的编号修复** | 订正行号；**A1 第 3 项建议改为"不做"**（Phase 7b 已兜底）；加入第 2 批前置决策 |
> | V-3 | "其余 `agents/*.md` ×9" | 实测 **×6**，已列出确切文件名 |
> | V-4 | 遗漏 `references/appendix-converter-contract.md`（C5 合约，3 处 `AGENT-OUTPUT`） | 补为 #41；给出全库 18 文件 / 48 处完整 nonce 联动面 |
>
> **验证结论**：24 项修改条目中 **23 项行号准确**，错误集中于 1 项——但该项恰是最关键的一项，且连带暴露了会使 A1 失效的 Phase 7b。详见 §九末尾「逐条实跑验证记录」。
>
> **✅ 审查层修订说明（V1.0 → V1.1）**：DesignAuditor 对 V1.0 判定"不可交付"，指出 5 项 Critical。本版已全部修复：
>
> | # | Critical 问题 | 修复位置 |
> |---|--------------|---------|
> | 1 | `model-profile.json` 缺失默认 tier C，推翻"Claude 字节级不变"保证 | §C1 —— 仓库内提供默认配置；缺失→**tier A**，解析失败才→tier C |
> | 2 | B4/C4 格式互斥（JSON vs Markdown）且消费者早于生产者 3 批 | §B4 + §C4 —— 统一 JSON 落盘、Markdown 书写；B4 移至 C4 之后（第 8 批） |
> | 3 | "贴 stdout"实为 4 处，清单只列 1 处 | §C4 —— 4 处全列（`chapter_auditor_agent.md:65/:98/:149` + `SKILL.md:183`），L1 改全库检索 |
> | 4 | L2 快照基线不可操作（现有 fixture 对 A1 零敏感） | §六 —— 实测 8 份 fixture H4 全为 0；第 1 批须先建 `structured-sample` fixture |
> | 5 | `merge_drafts.py:78` 字面量匹配未列入清单，nonce 化后标记会残留进 Word | §C5 —— 列入清单 + 改用共享正则常量 |
>
> **同批修复的 High 级**：删除虚构条目 `clean.py`（实测零命中）；红线改两层结构（红线 5 条 + 脚本硬拦清单）；C10/C11 第一阶段改非阻塞；`phase_a_mode` 改由 `max_output_tokens` 派生；**新增 Phase E 质量增强层**（回应用户"提高输出质量"需求）。
>
> **对审查意见的一处不采纳**：审查层称"四条转写铁律/标准22/标准20/标准0 已有 FATAL 脚本兜底，被错误降为细则"。**实测复核不成立**——`card_overlap`=mid、`QS4`=low、F10 阶段 7 仅 WARN、标准 0 无脚本。它们不满足"红线判据=FATAL且脚本可检出"，降为细则正确。但已采纳其建设性内核（两层结构），详见 §C3。
>
> **仍需用户重点关注的高风险**（编排器自评）：Phase A 会改变既有转换输出，须先建 fixture 与快照；C3 红线完备性无法自动验证；§九改动清单仅被抽查 3 处，其余条目执行前须逐项 grep 复核。

---

## 一、方案概述

### 1.1 核心设计命题

> **跨模型兼容性的本质不是让弱模型变强，而是缩小"必须由模型语义能力兜底"的面积。**

每把一项检查从 prompt 自律搬到确定性脚本，就等价于把该项的模型能力依赖降为零。本方案的全部设计都服务于这一命题。

### 1.2 三类障碍与对应策略

| 类别 | 内容 | 策略 |
|------|------|------|
| **A. 隐性 Claude 能力依赖** | 规则密度 30 条、Phase A 96 字段、固定分隔符、结构化输出无校验 | 转确定性校验 + prompt 分级 + 填空骨架 |
| **B. 既有代码缺陷**（与模型无关，弱模型下后果放大） | YAML 字段名不匹配、静默降级、三处失败语义冲突、F7/F8 无实现 | 修 bug + 统一失败语义 |
| **C. 架构级生态锁定** | `Agent` 工具 depth-1 委派、drawio MCP | **不可解**——声明边界 + 降级，不承诺等价 |

### 1.3 四层改动架构

| 层级 | 内容 | 改动量 | 风险 |
|------|------|--------|------|
| **Phase A**：地基修复（P0 bug） | outline_reader 字段名 / 失败语义统一 / F7/F8 补实现 | ~150 行代码 | **MEDIUM**（触核转换路径，需先建快照） |
| **Phase B**：确定性校验层 | 7 个新脚本 + 5 份机读 schema | ~900 行代码 | LOW（纯新增） |
| **Phase C**：能力分档与 prompt 分级 | model-profile.json + 红线提取 + 填空骨架 | ~300 行文档 + 配置 | **MEDIUM**（改 Agent 行为） |
| **Phase D**：流程加固与文档一致性 | 信封 nonce / 降级台账 / 文档订正 / 回归三层 | ~400 行 | LOW |

### 1.4 关键设计决策（含被否决方案）

| # | 决策 | 理由 | 被否决的替代 |
|---|------|------|-------------|
| 1 | **Tier A（Claude）默认全部新行为 off** | 这是"不削弱已验证质量"的最强保证——Claude 路径字节级不变 | 统一按最低公分母改造（浪费 Claude 能力） |
| 2 | **信封用"固定前缀 + nonce 后缀"** | 前缀不变 → 正则放宽即全兼容 | 完全替换为随机串（破坏 F1 检测 / `merge_drafts.py` 剥离 / finalizer 全链路） |
| 3 | **能力分档用配置声明，不用运行时探针** | 探针能客观判分的恰是脚本已兜底的能力；探针测不出的语义能力恰无客观判分手段——价值被架空 | 运行时能力探针；按模型名字符串推断（模型名不稳定） |
| 4 | **机读 schema 由脚本从叙述性契约派生** | 避免两个真源必然漂移 | 手工维护独立 JSON 侧车 |
| 5 | **YAML 失败改"延迟阻断"而非立即阻断** | 立即阻断会让现有 Claude 流程的小瑕疵变成硬失败，风险过大 | 改为 ERROR 立即中断 |
| 6 | **Phase A 改"确认式"仅在 tier≠A 启用** | 保留 Claude 上已验证的自由生成预承诺 | 全档改确认式 |
| 7 | **红线判据 = FATAL 且脚本可检出** | 保证每条红线都有脚本兜底，不是拍脑袋选的 | 按"重要性"主观挑选 |
| 8 | **Agent 红线用同文件分节，不拆独立文件** | 现有已是"摘要→外部 SSOT"两层结构，再拆成三层跳转，弱模型极可能只读第一层就动笔 | 独立 `hard-rules.md`；塞进 YAML front matter |

---

## 二、Phase A：地基修复（P0，必须最先做）

> **为什么最先**：Phase B 的 `outline_title_extract.py`、阶段 7 结构一致性审计都依赖结构清单可用。不修此 bug，上层设计全部落空。**且该 bug 当前正在静默损坏 Claude 路径**。

### A1. 修复 `outline_reader.py` subsections 字段名不匹配（P0-2）

**文件**：`scripts/md2docx/assemble/outline_reader.py`

**现状**（`:149-150`）：
```python
parent_title = sub.get("parent", "")     # 规范定义为 parent_section_no
sub_title    = sub.get("title", "")      # 规范定义为 subsection_title
```

**实测后果**：按规范（`references/stage-4-outline.md:98-101`）写的 subsections **100% 被静默丢弃**（lookup 中 SUBSECTION 条目 = 0）。

**三处必须同时修**：

> **✅ 执行结果**：本项已于第 2 批落地。**实际修改为 4 处**——方案原列 3 处，执行时发现第 4 处（守卫条件）不改则前两处修了也无效，详见下方第 4 项。第 3 项「编号取真值」经裁决**不做**（方案甲）。

1. **字段名对齐**（`:149-150`）：读 `parent_section_no` / `subsection_no` / `subsection_title`；兼容旧字段名 `parent`/`title` 作降级路径并写台账
2. **parent 查找兼容 dict**（`:158-159`）：现只处理 `isinstance(s, str)`，规范要求 sections 是 `{section_no, section_title}` dict → 双重不匹配，只改字段名仍失败
3. ~~**编号取真值**（`:163-166`）~~ —— **裁决为不做**，见下方 V-2 说明
4. **🔴 守卫条件改造（方案原遗漏，执行时发现）**（`:151-155`）：现有守卫为
   ```python
   if (parent_title and sub_title and parent_title.strip() in lookup):
   ```
   `lookup` 的键是**标题文本**，而规范字段 `parent_section_no` 的值是**编号**（如 `"1.1"`），因此 `"1.1" in lookup` **恒为 False**，subsections 仍会 100% 被丢弃。
   **必须随字段语义一起改**为"用 `parent_section_no` 在 sections 中按 `section_no` 匹配"。
   实现时新增了 `_find_parent_section_idx()` 辅助函数，同时支持新旧两种 parent 语义（编号匹配 / 标题文本匹配）与 sections 的两种形态（dict / str）。

> **🔴 V-2 验证发现：本项（编号取真值）会被 Phase 7b 覆盖，须先决策**
>
> 实跑核实 `scripts/md2docx/assemble/headings.py:557-591` 存在 **Phase 7b「重算 SUBSECTION (H4) 三级编号」**逻辑，它在 overlay **之后**按文档序无条件重写全部 H4 编号：
> ```python
> elif ir.kind == HeadingKind.SUBSECTION:
>     subsection_counter += 1
>     if current_chapter is not None and current_section is not None:
>         ir.number = (current_chapter, current_section, subsection_counter)
> ```
> **因此第 3 项若只改 `outline_reader.py`，结果会被 Phase 7b 直接丢弃。** 两个可选方案：
>
> | 方案 | 做法 | 评价 |
> |------|------|------|
> | **甲（推荐）** | **放弃"取真值"，接受 Phase 7b 的顺序编号** | Phase 7b 的按序编号在绝大多数场景下结果与 `subsection_no` 一致；改动面最小，不触碰已验证的渲染路径 |
> | 乙 | 让 Phase 7b 在 lookup 已提供 subsection 编号时跳过重算 | 语义更"正确"（YAML 为权威），但触碰核心渲染逻辑，回归风险高于收益 |
>
> **建议采甲**：本项从"修 bug"降为"不做"，A1 只保留第 1、2 项（字段名 + dict 兼容）与 manifest 计数修复——这三项才是"结构清单被丢弃"的真正根因；编号问题已有 Phase 7b 兜底，不构成实际缺陷。
>
> **✅ 执行裁决（2026-07-29，编排器）：采纳方案甲。** `headings.py` 的 Phase 7b 保持**完全原样**（已用 `git diff` 验证该逻辑区零改动）。
>
> **补充理由（比方案给的"改动面最小"更强）**：Phase 7b 按**实际文档序**编号，保证渲染出的 H4 编号**连续无跳号**；而取 YAML 真值时，若正文漏写某个 H4（弱模型场景下概率显著上升），会渲染出跳号编号（如 1.1.1 之后直接 1.1.3）。**Phase 7b 在鲁棒性上优于取真值，不只是改动更小。** 这一点恰好与本方案"跨模型兼容"的目标同向。
>
> **附带结论**：Phase 7b 的存在解释了为何 P0-2 至今未导致 H4 编号全面错乱——**它是一条独立兜底路径**。这**降低了 P0-2 的实际危害等级**（分类与结构清单确实丢失，但编号有兜底），审计报告 P0-2 的"下游后果"描述应据此理解为"分类丢失 + 依赖兜底"，而非"编号必然错乱"。

**附带修**：`build_structure_manifest()`（`:215`）用 `len()` 计数，导致 `builder.py:196-204` 的 INFO 日志谎报 `subsections=1` 而 lookup 实际 0 条 —— **telemetry 反向误导比无 telemetry 更糟**。应改为统计实际成功入表的条目数。

**联动（V-2 订正）**：**`headings.py` 无需修改 parent 匹配逻辑**——该逻辑只存在于 `outline_reader.py:158-159`（本项第 2 步已覆盖），`headings.py` 全文不含 `isinstance(s, str)`。`headings.py` 真正需要关注的是 `:557-591` 的 Phase 7b 重算逻辑，见下方说明。

**验收**：按规范格式构造 structure → `_build_structure_lookup()` 返回的 SUBSECTION 条目数 = YAML 中声明数；manifest 计数 = lookup 实际计数。

### A2. 统一 outline.md SSOT 的失败语义（P0-3）

**现状三处冲突**：

| 消费者 | 位置 | 现行为 |
|--------|------|--------|
| `merge_drafts.py` | `:56-63` | `[ERROR]` + `sys.exit(2)` 硬阻断；且 `:60` 的 `yaml.safe_load` **无 try/except**，格式错误抛未捕获 traceback |
| `md2docx/builder.py` | `:210-219` | 仅 `Level.WARNING`，转换继续，回退启发式 |
| `figure_gate.py` | `:63-66` | 裸 `return None`，**无任何诊断** |

**设计：三级延迟阻断**（不改为立即阻断，避免破坏 Claude 现有流程）

| 级别 | 行为 | 适用 |
|------|------|------|
| L-记录 | 写台账，流程继续 | nonce 未匹配、可选字段缺失 |
| L-显著 | 写台账 + stderr 醒目告警 + `Level.WARNING` 升 `Level.ERROR`（进 Issue 报告但不中断转换） | YAML 解析失败回退启发式、subsections 丢弃、图表清单降级 |
| **L-延迟阻断** | 写台账 + **在 CP6 交付门禁强制阻断**，未经用户逐条确认不得交付 | 全部 L-显著 事件的累积 |

**设计理由**：降级发生时立即阻断风险大（可能中断 40 页报告的第 8 章），但静默接受违背"降级必须可观测"原则。**延迟阻断兼顾两者——允许跑完，但不允许悄悄交付。**

**⚠️ 与上一轮方案的关系**：`design/skill-optimization-plan.md` 的 C2 项曾**有意保留**静默降级语义（原文："返回语义不变…对管道行为零影响"）。本方案**推翻该决定**，理由是跨模型场景下弱模型 YAML 生成失败率显著上升，"静默"从可接受变为不可接受。这是**有意识的决策变更，非修复遗漏**。

**具体改动**：
- `merge_drafts.py:60`：补 try/except，与其余两处统一为 L-显著 + 台账
- `builder.py:210-219`：WARNING → ERROR + 写台账
- `figure_gate.py:63-66`：补诊断输出 + 写台账
- `outline_reader.py:55-67`：保留 stderr 诊断，补台账写入

### A3. 补实现 F7/F8 两条 FATAL 级检查（P1-12，但因文档谎报能力而提级）

**问题**：`references/writer-template.md:117` 声称"审计 Agent 会使用 `contract_check.py` 的 C2/C5/C6/C7/C8/C9 规则逐项检测，命中即阻断"，但 `scripts/contract_check.py:56-65` 的 `BANNED_PATTERNS` 实测仅 7 条，**不含 F7/F8**——而这两条都标注为 FATAL。

**实现成本极低**：`references/stage-7-writing.md:148` **已给出经验证的正则**：
- F7 信源分级前缀：`^\s*\[[ABCD]\]`
- F8 claim_id 泄露：`\[[A-Z]{1,3}\d{3}\]`

**改动（修订——审查层 High-3）**：在 `contract_check.py` 新增 C10（F7）与 C11（F8）两项检查，**分两阶段落地**：

| 阶段 | severity | `pass` 取值 | 是否进 `high_severity_keys` | 目的 |
|------|---------|------------|---------------------------|------|
| **第一阶段（本方案范围）** | `mid` | **恒为 `True`**（只计数不判负） | **否** | 收集真实报告语料的命中分布，零阻断风险 |
| 第二阶段（后续独立决策） | `high` | 按实际命中判定 | 是 | 观察期无误报后再升级 |

> **修订理由**：原方案正文写"纳入 `high_severity_keys`（立即阻断）"、注释却写"先 WARN 观察一轮"，**自相矛盾**。更关键的是——**C10/C11 对 Claude 用户无 tier 门控、直接强制生效**，一旦误报会立即阻断现有 Claude 流程，与"Claude 路径字节级不变"的核心保证冲突。第一阶段非阻塞可彻底消除该风险。
>
> **误报风险已实测排除**（编排器独立验证）：对 8 个真实样本实跑两条正则，**零误报**。反向测试确认 `[SRC-001]`/`[CASE-01]`/`[TECH-03]`/`[THEORY-01]` 均**不**命中 F8（连字符天然阻断 `\d{3}` 紧邻匹配），`[CM021]`/`[CO012]` 正确命中；F7 的 `^\s*\[[ABCD]\]` 只命中行首独立分级前缀，不误伤 `文中提到[A]类` 或 `[1] European Space`。**因此白名单不必要。** 但样本量仅 8 份且均非真实研究报告终稿，故仍按非阻塞起步。

---

## 三、Phase B：确定性校验层（P0/P1，纯新增，低风险）

### B1. `scripts/output_envelope_check.py`（P0-6 + P0-7）

**职责**：信封完整性 + nonce 配对 + 噪声比率检测（三合一，不单独建噪声脚本）

**接口**（与 `contract_check.py` 风格同构）：
```
python scripts/output_envelope_check.py <raw_output.txt> --agent <name> [--nonce <hex>] [--json]
```

**检查项**：
1. 标记成对出现且恰为 1 对
2. 标记内 agent 名称与期望一致（防跨 Agent 输出粘连）
3. nonce 匹配（提供 `--nonce` 时）
4. 噪声比率

**噪声检测的关键实现约束**：**不能**按"非 ASCII 占比"（会把正常中文 100% 误判）。必须精确匹配：
- Unicode 替换字符 `�`（编码错误的确定性标志）
- 进度条专用字符集 `▕ █ ▏▎▍▌▋▊▉`
- 可复用 `contract_check.py:115-134` 的 `count_cjk_chars` 排除中文误判

**exit code**：0=通过 / 1=信封或噪声失败 / 2=读取错误

**JSON 输出**：`{envelope_ok, nonce_matched, noise_ratio, agent_matched, payload_path}`

**调用位置**：orchestrator 每次收集 Agent 输出时（横切全阶段）。**这是前移一道防线**——现状 F1 只能在写完整章后被审计发现（污染已落盘），新设计在提取环节即拦截，成本低一个数量级。

### B2. `scripts/outline_title_extract.py`（P1-8）

**职责**：把 `multiagent-orchestration.md:87-96` §8.5 的纯 prompt 级规则落成脚本

**接口**：
```
python scripts/outline_title_extract.py --outline research/outline.md [--chapter-no N] [--json]
```

**输出**：章→节→小节的纯文字标题树 + YAML/Markdown heading 一致性告警

**实现**：直接复用 `outline_reader.py:80-179` 的 `_build_structure_lookup`（**依赖 A1 修复完成**）

**价值**：把"orchestrator 手动判断该注入什么标题文字"这个纯脑力活动变成一次脚本调用，**对任何模型档位都是纯收益**。

### B3. `scripts/schema_validate.py`（P0-4）

**职责**：通用 JSON Schema 校验器 + repair loop 错误消息格式化

**接口**：
```
python scripts/schema_validate.py <target.json> --schema <name> [--json]
```

**关键设计**：现有 `agents/contracts/*.json` 是**叙述性 schema**（`requirement` 为自然语言），**不能直接** `jsonschema.validate()`。需新建机读 schema（Draft 2020-12）置于 `schemas/`，由脚本从叙述性契约**派生并缓存**，带 `x-generated-from` 字段标明来源，CI 校验同步性。**不手工维护两份真源。**

**需覆盖的 schema**：
- `writer-selfclaim.schema.json`（6 个自声明字段）
- `auditor-phase-a.schema.json`（24 维度 × 4 字段）
- `auditor-phase-b.schema.json`（维度打分 + verdict 枚举 + issue 清单）
- `outline-structure.schema.json`（从 `stage-4-outline.md` §4.1.y 派生）
- `model-profile.schema.json`

**repair loop**：校验失败 → 将 `error.path` + `error.message` 格式化为"请修正以下字段：X" → 注入下一轮 prompt → 重试上限 **2 次**（对齐 `chapter_auditor_agent.md:158` 已有的 `max_rounds=2`，保持全 skill 重试语义一致）

**依赖**：`jsonschema` 4.26.0（**已实测安装**）

### B4. `scripts/precommit_consistency_check.py`（P1-1）

**职责**：Phase A/B 承诺一致性的**机械**校验（替代现在的模型自查自）

**前提改造**：Phase A/B 必须**强制落盘为独立结构化文件**（**JSON 格式，与 C4 统一**）
- `research/chapter-reports/chXX-audit-phaseA.json`
- `research/chapter-reports/chXX-audit-phaseB.json`

> **⚠️ 审查层 Critical-2 修复（格式统一 + 顺序倒置）**：原设计中本节要求 JSON 落盘，而 C4 定义 Phase A 输出为 Markdown 三级标题（`### <维度id>` + `confirm`/`adjust:`），**两者格式互斥**；且原推荐批次把 B4 排在第 4 批、C4 排在第 7 批，**消费者早于生产者 3 批**。
>
> **统一裁决**：Phase A/B 一律以 **JSON** 为落盘格式。Agent 仍可用 Markdown 小节形式书写（对弱模型更友好），由 orchestrator 在提取信封内容后转为 JSON 落盘——**Markdown 是书写形态，JSON 是存储与校验形态**，二者不冲突。`precommit_consistency_check.py` 只消费 JSON。
>
> **顺序修正**：B4 移至 C4 **之后**执行（见 §七修订后的批次表）。

**接口**：
```
python scripts/precommit_consistency_check.py <phaseA.json> <phaseB.json> [--json]
```

**检查**：对每个 dimension，Phase B 的判定说明是否包含 Phase A 对应 `what_triggers_block` 的关键词 token。**建议用分词后集合交集比例而非严格 substring**——严格 substring 对措辞变化过于脆弱。

**⚠️ 天花板声明（必须如实写入文档，不得宣称"已解决盲态问题"）**：
> 机械校验检查的是"文字层面是否复述了关键词"，**不能证明模型真的做到了先承诺后打分**，而非"先看稿再回填一份看似匹配 Phase A 的文本"。这是 substring-match 机制的固有天花板，Claude 上如此，弱模型上更甚。真正堵死需要**架构级隔离**（orchestrator 保证 Phase B 的 prompt 拼接顺序：先注入 Phase A 落盘文件 → 再注入草稿）。**机械校验显著提高作弊成本（从纯自律升级为"文本要对得上落盘证据"），但不是 100% 保证。**

**调用者**：**orchestrator，不由 auditor 自调**。理由——让被检查者运行检查自己的脚本，在弱模型上等于没检查（可以不跑、跑了不报、误报为通过）。这把项目既有的"检查者 ≠ 被检查者"原则从 Agent 层贯彻到脚本调用层。

### B5. `scripts/degradation_report.py`（P2-1）

**职责**：降级台账汇总与交付阻断

**台账格式**（`research/.degradation-log.jsonl`，append-only，沿用 §8"门禁快照落盘"惯例）：
```jsonl
{"event_id":"<sha1>","ts":"...","stage":"9","component":"outline_reader",
 "reason":"yaml_parse_failed","level":"L-显著","fallback_used":"heuristic_text_match",
 "impact":"章节编号可能错误","acknowledged":false}
```

**幂等性**：`event_id = sha1(stage+component+reason+input_path)` 作去重键，重跑同一阶段不产生重复行。

**在 CP6 汇总**，未 `acknowledged` 的 L-显著 事件**阻断交付**，且**强制逐条列出 impact，不支持批量确认**（防止用户一键全确认退化为形式）。

---

## 四、Phase C：能力分档与 Prompt 分级（P0/P1，改 Agent 行为，需谨慎）

### C1. `model-profile.json` 能力档声明（P0-5 的前置）

**位置**：skill 根目录（与 `linkage-constants.json` 同级，沿用现有配置惯例）

**核心字段**：

| 字段 | 取值 | **默认** | 说明 |
|------|------|---------|------|
| `capability_tier` | `A`/`B`/`C` | **`A`**（见下方兜底规则） | A=Claude Opus/Sonnet；B=DeepSeek V3.2/GLM-4.6/Qwen3；C=未知 |
| `host.agent_delegation` | bool | **`true`** | false 即无 depth-1 底座 → 强制单 Agent 极速档 |
| `limits.max_output_tokens` | int | **`64000`**（tier A 实际值） | **驱动 `phase_a_mode` 派生**，见 C4 |
| `policy.hard_rule_budget` | int | **`0`**（=不限） | tier B/C 设 5 |
| `policy.envelope_nonce` | bool | **`false`** | tier B/C 设 true |
| `policy.template_fill_mode` | `off`/`on` | **`off`** | tier B/C 设 on |

**🔴 兜底规则（修订——原设计有严重缺陷）**：

| 情形 | 行为 |
|------|------|
| **仓库内提供默认 `model-profile.json`（tier A 全 off）** | **随方案一并交付**，保证开箱即用 |
| 文件不存在（用户误删/旧版仓库） | **fallback 到 tier A**（= 当前 Claude 行为），写台账提示"未找到配置，已按 tier A 运行" |
| 文件存在但 JSON 解析失败 / schema 校验失败 | **降 tier C** + 写台账 + CP1 显式告警——此时配置意图不明，保守处理有依据 |
| 文件存在且合法 | 按声明的 tier 运行 |

> **⚠️ 本条是审查层判定的 Critical-1 修复**。原设计"文件缺失 → tier C"会导致**现有 Claude 用户不创建该文件就被静默降级**（完整档禁用、红线砍至 5 条、Phase A 退化为确认式），**直接推翻本方案"Claude 路径字节级不变"的核心保证**。修订后的规则区分"未配置"（信任现状=tier A）与"配置坏了"（意图不明=tier C），二者风险性质不同，不应同等处理。

**必须提供 3 份示例**：`model-profile.claude.example.json`（tier A，全 off，保证向后兼容）、`.deepseek.example.json`（tier B）、`.unknown.example.json`（tier C）

### C2. 二维决策矩阵：模型能力档 × 报告规模档

现有三档协同模式由**报告规模/类型**决定，与模型能力**正交**：

| | **完整多 Agent** | **分层多 Agent**（默认） | **单 Agent 极速** |
|---|---|---|---|
| **Tier A**<br>(Claude) | **现状完全不变**。红线不限、Phase A 自由生成 24 维度、nonce 可选、无填空骨架 | **现状不变** | **现状不变** |
| **Tier B**<br>(DeepSeek V3.2 等) | 红线 ≤5；Phase A 确认式；强制 nonce；填空骨架 on；4 个新脚本全开 | 同左，仅核心章走对抗；非核心章 orchestrator 直写 + 全套脚本校验 | 红线 ≤5；填空骨架 on；语义自查压缩 3 项，其余交脚本 |
| **Tier C**<br>(未知兜底) | **不允许**——自动降为"分层"并写台账（理由：完整档 3-5 倍成本放大 + 未知模型 = 高失败风险） | 同 Tier B 分层档 | 同 Tier B 极速档 |

**正交性说明**：能力档影响**每次调用的 prompt 构造方式与输出切分粒度**；规模档影响**调用哪些 Agent、调用几次**。两者不互相覆盖，唯一例外是 `Tier C × 完整档` 强制降级。

**⚠️ 风险标注**：`Tier B × 完整档` **未经实测**。建议首个真实项目先跑分层档。

### C3. Prompt 红线分级（P0-5）

**文件组织：同文件分节**（不拆独立文件）

```markdown
---
name: chapter_writer_agent
model: sonnet
portability: core
hard_rules_count: 5
---

## 🔴 红线（RED LINES）——违反即 FATAL，共 5 条
R1 ... R5   ← 每条 ≤25 字，标注对应校验脚本

## 执行骨架
<FILL_*> 占位符模板（template_fill_mode=on 时生效）

## 细则（GUIDELINES）——尽力遵守，由审计 Agent 语义评估
G1...Gn（原有约束降级至此，非删除）

## 规则锚点摘要 + 强制读取清单（现有内容保留）
```

**红线判据（关键）**：**红线 = 违反即 FATAL 且 `contract_check.py` 可机械检出。** 这保证每条红线都有脚本兜底——即使模型漏了，脚本也会抓住。

#### `chapter_writer_agent` 红线（30 处 → 5 条）

| 红线 | 文本（注入原文，极简无歧义） | 校验 | 原分散位置 |
|------|---------------------------|------|-----------|
| **R1** | 全文不写 H1；第一个 H2 必须逐字是 `## 本章结论` | C1/C2、F5 | writer-template §2.1、agent:91 |
| **R2** | 所有标题只写纯文字，禁止任何数字/中文数字编号前缀 | C2 | writer-template §3.3、agent:42 |
| **R3** | 引用只写 `[SRC-XXX]`，多引用逗号分隔；禁止 `[N]`、`[S001]`、斜杠 | C6/C7 | writer-template §5.1、agent:39,130-134 |
| **R4** | 不写参考文献节、不写密级、不写 `[A]/[B]/[C]/[D]`、不写 claim_id | C5/C9 + **新增 C10/C11** | writer-template F2/F7/F8 |
| **R5** | 正文末尾必须有写作者自声明块，包裹在独立信封标记内 | `output_envelope_check` | writer-template §6 |

**降为细则的 25 处**（全部是语义或非 FATAL 项）：四条转写铁律、标准 0/18/19/20、段落 150-400 字、每 300 字 1 数据点、缩写首次展开、glossary preferred_form、章间/节间过渡、局限说明、上下文预算、跨章禁令、素材缺口标注等。

#### 🔴 补充：脚本硬拦清单（审查层 High-2 修订）

审查层指出"部分被降为细则的约束其实有脚本兜底，读者会误以为无人管"。**经实测复核，审查层点名的 4 项并不满足红线判据**：

| 约束 | 审查层主张 | **实测** | 结论 |
|------|-----------|---------|------|
| 四条转写铁律 → `card_overlap_check.py` | 有 FATAL 兜底 | `card_overlap` severity=**mid** | 不满足"FATAL" |
| 标准 22 术语 → `term_consistency_check.py` | 有 FATAL 兜底 | F10 阶段 7=**WARN**（仅阶段 9 终稿 FATAL） | 阶段 7 不满足 |
| 标准 20 段落 → QS4 | 有 FATAL 兜底 | `QS4_paragraphs` severity=**low** | 不满足 |
| 标准 0 前后台分离 | 有脚本兜底 | **无脚本**（审计报告 P2-2 判定仅可做黑名单代理） | 无兜底 |

**因此降为细则的判断是正确的**，红线仍为 5 条不变。但审查层的建设性内核有效——**采纳其"两层结构"建议**：

```markdown
## 🔴 红线（RED LINES）——占 prompt 预算，需模型主动记忆遵守，5 条
R1 ... R5

## 📋 脚本硬拦清单（不占 prompt 预算，仅告知"这些有机器兜底，不必分心记忆"）
| 约束 | 兜底脚本 | 触发级别 |
|---|---|---|
| 卡片誊抄 | card_overlap_check.py | mid（≥46字×2处→block） |
| 术语一致性 | term_consistency_check.py | 阶段7 WARN / 阶段9 FATAL |
| 段落长度分布 | contract_check.py QS4 | low（统计告警） |
| 图表存在性 | figure_gate.py | FATAL |
| 强表述无证据 | claim_strength_check.py | high |
```

**设计意图**：红线要求模型**主动记忆并遵守**（占认知预算，故 ≤5）；硬拦清单只是**告知模型"这些有机器兜底"**，反而**释放**认知预算——模型不必分心自查已被脚本覆盖的项。二者一增一减，净效果是让 5 条红线的注意力更集中。

#### `chapter_auditor_agent` 红线（15 处 → 5 条）

| 红线 | 文本 | 校验 |
|------|------|------|
| **A1** | 量化维度每个数字必须逐字复制自脚本 stdout，禁止自行计算 | `precommit_consistency_check` 检测报告是否含脚本输出特征串 |
| **A2** | 不改稿。只输出裁决与 issue 清单 | 脚本检测报告中是否含 ≥5 行连续正文片段（改稿代理指标） |
| **A3** | 必须按序输出 5 个指定小节，缺一即失败 | 小节标题正则存在性 |
| **A4** | 恰好输出一行 `verdict=PASS` 或 `verdict=REVISE` | 计数 == 1 |
| **A5** | Phase B 每个 block/warn 判定必须包含 Phase A 对应触发词原文子串 | substring-match lint（脚本化） |

> **关键架构效果**：A1/A3/A4/A5 原本全是 prompt 自律（`chapter_auditor_agent.md:37` 明写"无 Hook 级拦截"），现在四条全部有脚本兜底。**把"审计者是否诚实"从模型能力问题转为可检测事件。**

### C4. Phase A 输出规模应对（P0-1，硬容量冲突）

**实测基线**：`auditor_contract.json` 的 `dimensions` = **24** 条，`proposal_extra` = **5** 条，维度组 **8** 个。Phase A 需 24×4 = **96 字段**（proposal 档 116），vs DeepSeek 单次输出 8K tokens。

**手段 1（主）：契约预置触发词，Phase A 从"生成"降为"确认"**

`auditor_contract.json` 已有 **4 个**维度带 `what_triggers_block_hint`（`structural_consistency`/`card_overlap`/`chapter_transition`/`reader_calibration`）。**将其扩展到全部 24+5 个维度**，并新增 `what_to_look_for_hint`/`what_triggers_warn_hint`。

Phase A **书写形态**改为（Markdown，对弱模型友好）：
```
### <维度id>
confirm
```
或
```
### <维度id>
adjust: <一句话，仅当需偏离预置时>
```

**落盘形态为 JSON**（由 orchestrator 转换，见 B4）：`{"ch01": {"outline_coverage": {"mode": "confirm"}, "strong_claim": {"mode": "adjust", "text": "..."}}}`

单维度输出从约 120 字降至约 10 字，24 维度约 **300 字 ≈ 450 tokens**，远低于 8K。

**⚠️ 代价声明（不粉饰）**：预承诺的防御价值部分来自"审计者自己写下标准"这一认知承诺。改为确认式后这层心理承诺被削弱，**盲态预承诺退化为盲态确认**。对抗"看稿再放宽标准"的力量转由 A5 的 substring lint 承担——而 lint 本身此时反而更强（预置文本固定，子串匹配更可靠）。净效果判断为**正**，但这是**权衡而非纯改进**。

**🔴 启用条件（修订——审查层 High-4）**：由 `limits.max_output_tokens` **派生**，而非绑定 `capability_tier`：

```
phase_a_mode = "confirm"  if max_output_tokens < 16000  else "free"
```

> **修订理由**：原设计"仅在 `capability_tier != A` 时启用确认式"会导致——若 DeepSeek V4 发布为长输出规格（预览称 384K），它仍是 tier B，**却会被不必要地强制降级为确认式**，白白损失预承诺的认知价值。改为按实际输出能力派生后：tier A（64K）→ free；DeepSeek V3.2（8K）→ confirm；未来 V4（若长输出）→ 自动 free。**`phase_a_mode` 因此从配置字段降为派生量，不再单独列入 schema。**

**手段 2：分批兜底**（仅在确认式仍超限时启用，如 proposal 档 29 维度）。按**严重度**而非维度组分 3 批：批1=high（约 9 个）、批2=mid（约 12 个）、批3=low（约 5 个 + proposal 5 项）。

**分批的关键纪律**：
- **high 严重度批次不允许任何简化**——C1/C2/C5/大纲对照/证据密度/强表述 是 R3 解的核心承载，弱模型下不得悄悄放水
- mid/low 批次重试仍失败时，允许降级为"仅填 `what_triggers_block` 一行"，但**必须写降级台账**（不静默）
- 需在 `auditor_contract.json` 新增 `batch_grouping` 字段声明各批含哪些 dimension id，供脚本读取
- 三批分别落盘 `research/chapter-reports/chXX-precommit-batch{1,2,3}.md`，文件首行以 HTML 注释标注元数据（`<!-- phase=A batch=1 chapter=ch01 dims=9 -->`），供 `precommit_consistency_check.py` 做"批次是否完整"的机械校验（不依赖 LLM 判断）

**手段 3：Phase B 同样受 8K 约束**（压力更大——需贴 stdout + 24 维度打分 + issue 清单）。设计：`## 脚本量化结果` 小节改为**只贴 JSON 摘要 + 失败项**，全量 stdout 由 orchestrator 落盘到 `research/chapter-reports/chXX-scripts.json`，报告用路径引用。

> **注意**：`card_overlap_check.py --json` 在卡片数多时输出很长，orchestrator 注入时须做截断/摘要，只保留裁决相关字段。

> **🚨 必须成对修改的点（审查层 Critical-3 修订：实为 4 处，非 1 处）**：此改动与现有"必须贴 stdout"的表述冲突，**经全库检索确认共 4 处**，任一遗漏都将导致 tier B 下全面误阻断：
>
> | # | 位置 | 现文 | 须改为 |
> |---|------|------|--------|
> | 1 | `agents/chapter_auditor_agent.md:65` | "把 stdout 贴进审计报告" | "把脚本 JSON 摘要贴进报告，全量 stdout 落盘并引用路径" |
> | 2 | `agents/chapter_auditor_agent.md:98` | "数字**必须来自脚本 stdout**…orchestrator 会检查审计报告是否含脚本 stdout" | 同上，检查项改为"含 JSON 摘要 + 落盘路径" |
> | 3 | `agents/chapter_auditor_agent.md:149` | "`## 脚本量化结果`——粘贴上述脚本的真实 stdout" | "粘贴脚本 JSON 摘要 + `chXX-scripts.json` 路径" |
> | 4 | `SKILL.md:183` | 反例 13："审计报告须含脚本 stdout" | 同步措辞 |
>
> **L1 静态测试相应加强**：不再断言单一行号，改为**全库检索** `stdout` 关键字，断言不存在"要求粘贴完整 stdout"的残留表述（行号会随编辑漂移，检索更稳健）。

### C5. 输出信封 nonce 迁移（P0-6）

**新格式**：
```
[AGENT-OUTPUT-START:a7f3c9d2] chapter_writer_agent
<有效产出>
[AGENT-OUTPUT-END:a7f3c9d2] chapter_writer_agent
```

**兼容性核心**：nonce 是**后缀**，前缀 `[AGENT-OUTPUT-START` 不变。因此：
- 检测正则统一放宽为 `\[AGENT-OUTPUT-(START|END)(:[0-9a-f]{6,16})?\]`
- Claude（tier A）可继续输出无 nonce 旧格式，提取正则同时接受两种

**🔴 审查层 Critical-5 修复：字面量前缀匹配点必须一并改**

实测确认 `scripts/merge_drafts.py:78` 用的是**字面量** `s.startswith("[AGENT-OUTPUT-START]")`：

```python
if s.startswith("[AGENT-OUTPUT-START]") or s.startswith("[AGENT-OUTPUT-END]"):
```

nonce 化后 `[AGENT-OUTPUT-START:a7f3c9d2]` **不会被匹配**——该行是 finalizer 合并管道的 B1 剥离步骤，**漏匹配将导致隔离标记残留进入最终 Word 交付物**。且原方案 §九 改动清单**遗漏了此文件的这一处**。

**修复要求**：所有标记匹配点改用**共享正则常量**（而非各自写字面量），建议在 `contract_check.py` 定义 `RE_ENVELOPE_MARKER` 并由 `merge_drafts.py` import 复用（已实测四个脚本均有 `__main__` guard，可安全 import）。

**全库标记匹配点清单**（须逐一改，实测确认）：

| 位置 | 现形式 | 说明 |
|------|--------|------|
| `scripts/contract_check.py:64` | 正则 `\[AGENT-OUTPUT-(?:START\|END)\]` | C5 检测，放宽 + 导出为共享常量 |
| `scripts/merge_drafts.py:78` | **字面量 startswith** | **Critical-5，改用共享常量** |
| `references/writer-template.md:121` | F1 检测说明 | 文档同步 |
| `agents/finalizer_agent.md:33` | 步骤 0a 剥离说明 | 文档同步 |

> **已删除的虚构条目**：原 §九 #36 列出 `scripts/md2docx/textstage/clean.py`（"信封剥离正则放宽"）。**实测该文件 `AGENT-OUTPUT` 零命中，整个 `md2docx` 包内无任何文件包含此字符串**——该条目基于错误前提，已删除。R-12 兜底删除的是"写作者自声明"区块，不是信封标记。

**降级处理**：nonce 未命中 → 降级为无 nonce 匹配，**并写台账**（"弱模型没照抄 nonce"这一事实被计数，而非静默通过）

**误匹配防护**：nonce 格式限定 `[0-9a-f]{6,16}` + 必须行首 + 必须带 agent 名后缀，三重约束

---

## 五、Phase D：流程加固与文档一致性（P1/P2）

### D1. 门禁体系增列确定性检查

沿用现有门禁实名（`multiagent-orchestration.md` §5），非虚构 G0-G8：

| 门禁/阶段 | 新增调用 | 调用者 | 失败路由 |
|-----------|---------|--------|---------|
| **全阶段横切** | `output_envelope_check.py` | orchestrator | 信封失败→重试（关键路径 2 次）；nonce 失配→接受但记台账；噪声>30%→重试 |
| **G(大纲)** 阶段 4 | `schema_validate.py --schema outline` | orchestrator | schema 失败 → 回 `outline_architect_agent` 修正（**不静默降级**） |
| **阶段 7 注入前** | `outline_title_extract.py` | orchestrator | 提取为空 → P0（现状是静默丢弃） |
| **G7-write** 每章每轮 | `precommit_consistency_check.py` + `schema_validate.py --schema auditor_phase_b` | **orchestrator（非 auditor 自调）** | lint 失败 → Phase A 重试 1 次 / Phase B abort（沿用现规则） |
| **G8-redteam** | `output_envelope_check.py` ×4 | orchestrator | 同横切 |
| **G(交付)** | `degradation_report.py`（**12 项 → 13 项清单**） | `finalizer_agent` | 未确认降级 → **阻断 CP6** |

### D2. 红队跨模型适配（P1-4、P1-5）

**问题**：`redteam_agent.md:17-26` 的"异构模型防同质化"设计（2×Opus + 2×Sonnet）在单一模型宿主下**前提不成立**。

**方案**：
- tier B/C 下，异构由**模型差异**改为**人格 prompt 差异化增强 + 审查顺序轮换**（swap 顺序对抗位置偏差）
- 在文档中**如实声明**：单模型宿主下"异构防同质化"效力下降，同质化盲点风险部分回归——这是 tier B/C 的固有质量上限，**不粉饰**
- **swap-and-average 不作为默认启用**：它使红队调用轮次翻倍（成本已是 3-5 倍放大的阶段），建议仅在 `capability_tier=C` 且报告为高风险类型时启用

**格式统一**（P1-5）：`workflow-stage8.md:46,82` 的 `output_schema` JSON 声明与 `redteam_agent.md:77-84`、`redteam_synthesizer_agent.md:55-59` 的 Markdown 表格冲突。**裁决：以 Markdown 表格为准**（两处实际实现一致，且 Markdown 表格对弱模型更鲁棒），修改 `workflow-stage8.md` 的伪代码。

### D3. 文档一致性订正（P1-6、P1-7、P1-13）

| 项 | 现状 | 订正 |
|----|------|------|
| 写作标准数量 | `writing-standards.md` 实际 **0-22（23 条）**；`SKILL.md:232` 说 12；`README.md:89` 说 17；`chapter_auditor_agent.md:22` 说 12+5 | 全部统一为实际值，并在 CI 加自动校验 |
| 角色数量 | `SKILL.md:42` 说 11；`README.md:61` 说 10（表列 13 行） | 统一口径定义（是否含 orchestrator/已废弃角色）后订正 |
| `diagram_agent` 残留 **4 处** | `multiagent-orchestration.md:26`、`card_synthesizer_agent.md:49`、`stage-4-outline.md:51`、`outline_architect_agent.md:3` | 全部替换为 `architecture_chart_agent`/`data_chart_agent`；`agents/diagram_agent.md` 移入 `agents/deprecated/` 或删除 |

### D4. 非 Claude 宿主边界声明（P2-6、P2-7）

**声明方式**：每个 `agents/*.md`、`references/*.md` 的 front matter 增加 `portability: core | claude-enhanced | claude-only`；根级新增 `PORTABILITY.md`（人读）+ `portability-manifest.json`（机读）

**边界划分**：

| 能力 | 分类 |
|------|------|
| 9 阶段方法论、写作标准、红队清单、格式规范 | **core** |
| 全部 `scripts/*.py`（含新增）、`md2docx` 转换器 | **core** |
| 契约 JSON / 机读 schema / 填空骨架 / 红线集 / 信封契约 | **core** |
| `Agent` 工具 depth-1 委派、写审对抗 pipeline、红队 4 人格并行 | **claude-only** |
| drawio MCP 出图 | **claude-only**（降级 Mermaid） |
| 三档模式中的"完整/分层"档 | **claude-only** |
| 单 Agent 极速档 | **core** |

**降级触发条件改造**：`multiagent-orchestration.md:15` 现写"被作为嵌套子 Agent 拉起时"，扩展为"检测不到 Agent 工具时"。**但由 `model-profile.json` 的 `host.agent_delegation: false` 显式声明，而非运行时探测**——运行时探测在无 Agent 工具的宿主上本身就不可靠。

**诚实结论**：非 Claude 宿主上本 skill 退化为「单 Agent 极速档 + 全套确定性脚本」。**但因本方案把大量检查搬进脚本层，此形态质量高于现状的极速档**（现状极速档几乎全靠自律）。

### D5. `finalizer_agent` 档位错配处理（P1-2）

**问题**：Haiku 承担全 skill 最长任务链（3 项正则剥离 + H1 grep + 结构驱动合并 + 4 脚本 + 12 项清单），且处于交付链末端。

**方案（不升档，而是脚本化）**：`scripts/merge_drafts.py` 已实现六阶段确定性合并管道（含 B1 剥离标记）。新增 `scripts/finalize_pipeline.py` 把**顺序强依赖且纯机械**的步骤（剥离标记 → H1 检测替换 → 结构驱动合并 → convert_references → contract_check --merged --stage stage9 → delivery_checklist）串成单一 Python 流程，`finalizer_agent`（Haiku）职责收窄为"跑一个脚本 + 读 JSON + 按 `failure_step` 查固定路由表"。

**关键设计**：`finalize_pipeline.py` 的 JSON 输出必须含 `failure_step` 枚举字段（`strip_markers`/`h1_check`/`merge`/`convert_refs`/`contract_check`/`delivery_checklist`），使 Haiku **不需要诊断哪里出错**（低配模型诊断能力弱），只需查表——这是 Haiku 完全胜任的机械任务。

**理由**：真正的问题不是任务难度超出 Haiku 能力，而是**任务顺序/依赖关系复杂**——Haiku 需"记住并遵守 9 步顺序"这件事本身超出低配模型可靠遵从率。顺序正确性交给脚本代码保证（脚本不会打乱自己的执行顺序）。升档到 Sonnet 治标不治本（仍是模型做精确文本操作）；拆分为多个子调用只是把顺序负担从 Agent 转移到 orchestrator，本质未解。

> **可行性已实测确认**（编排器验证）：`contract_check.py` / `convert_references.py` / `term_consistency_check.py` / `merge_drafts.py` **四个脚本全部具备 `__main__` guard**，函数级可直接 import 复用。**因此聚合脚本无需前置的函数级重构**——这排除了工作流设计中标注的一项风险。

**同理**：`source_collector_agent`（P1-3）的 10 条字段填充规则，建议提供 `source_index_helper.py` 辅助自动填充，降低 Haiku 负担。（P2 优先级）

### D6. 阶段 9 交付清单脚本化（P1）

12 项中 **10 项可脚本化**（比初估的 7-8 项更多），2 项结构性不可脚本化：

| 可脚本化（10 项） | 复用脚本 |
|---|---|
| 术语一致性 | `term_consistency_check.py` |
| 引用格式 + 无分级前缀 | `contract_check.py` C6 + **新增 C10** |
| 参考文献去重与一一对应 | `convert_references.py` |
| 图表编号统一 | `figure_gate.py` + C3/C4 |
| 输出隔离标记剥离 | C5 |
| 写作者自声明剥离 | 验证剥离后不含 `### 写作者自声明` |
| 红队批注剥离 | 验证 R-14 兜底生效 |
| 字数统计残留 | C8 |
| 局部参考文献 | C9 |
| 交叉引用一致（部分） | REF 域生成校验（语义指对与否仍需抽查） |

| **不可脚本化（2 项）** | 保障方式 |
|---|---|
| 红队风险清单处理确认 | 新增中间产物 `research/redteam-resolution-diff.md`——orchestrator 自动生成"风险项 → 修复前后 diff 摘要"对照表（用文本 diff 生成，不需 LLM 判断语义）。人工核对"变了什么"而非从头核对全文，降低核对成本 |
| 全文通读 | **强制人在环**——即使弱模型/单 Agent 极速档，orchestrator **不得**自行宣称"已完成通读"，必须在 CP6 显式列为待用户确认项，不可默认勾选。这是所有脚本/审计/红队机制都无法覆盖的最后一道防线 |

**新增 `scripts/delivery_checklist_check.py`**：作为**聚合调用器**，不重新实现检查逻辑，依次调用上述已有脚本，汇总 JSON + exit code。

---

## 五之二、Phase E：质量增强层（P1，审查层 High-5 新增）

> **新增理由**：审查层指出——原方案 **90% 是防御性改造**（防失效、防降级、防污染），对**只用 Claude 的用户几乎零可感知收益**。而用户原始需求是"加强 skill 的规范性，**用标准化流程提高报告输出质量**"。防御性改造只回应了前半句。本层直接回应后半句，且**对全部 tier 生效、不受 tier 门控**。

### E1. 标准 20 信息密度检查（扩展 QS4）

**现状**：`contract_check.py:137-173` 的 `compute_paragraph_stats` 已完全实现段落长度分布（P50/P75/P90 + >600 字计数）。**标准 20 的后半句"每 300 字至少 1 个数据点"尚未实现。**

**可行性**：`writing-standards.md:417-420` 已给出精确定义——"数据点 = 数字（含百分比/金额/数量）、带明确出处的声称、引用编号 `[N]`"。**低成本扩展**（复用现有函数，加一个正则计数）。

**输出**：`QS5_density`——每段字数/数据点数比值，标记"连续 500 字纯论述无数据点"的段落位置。

### E2. 标准 18 过渡存在性检查

**可脚本化部分**（存在性，非质量）：
- 章间过渡：非最后一章的文件末尾是否存在 `> **本章小结与过渡**：` 引用块且 ≥2 句
- 节间过渡：相邻 H3 之间是否有非空过渡文本

**价值**：弱模型主要失分点是**漏写**而非写得差；存在性检查能 100% 拦住漏写。**质量仍交审计 Agent。**

### E3. 标准 0 后台泄露黑名单检查

**依据**：`writing-standards.md:11-16` 的后台内容清单是**可枚举的固定习语**：`A 级/B 级/C 级来源`、`证据强度较高/较弱`、`可信度中等偏高`、`经交叉确认`、`尚未见独立信源证实`、`本次核验范围内`、`本报告采用…不采用`、claim_id 模式。

**`stage-7-writing.md:148` 已给出经验证的检索式**——当前仅作为**人工自查项**，本项将其脚本化。

**天花板（如实声明）**：黑名单**拦已知习语，拦不住新造句式**。这是代理指标的固有局限，不是"标准 0 已被解决"。

### E4. 标准 19 缩写展开检查（带白名单）

**代理指标**：全大写缩写（`[A-Z]{2,6}`）首次出现时，前后 30 字内是否有中文全称或括号释义。

**必须配白名单**：`glossary.md` 的 `aliases` + 通用缩写表（NASA/ESA/GDP/AI/API 等），否则误报率高到不可用。

**优先级说明**：E4 误报风险最高，建议**最后实现**，且第一阶段非阻塞。

### E5. Phase E 的定位声明

| 项 | 说明 |
|----|------|
| **受益对象** | **全部 tier，含 Claude 用户** —— 这是本方案对 Claude 用户唯一的**正向增量**（其余改造对 tier A 均为 no-op） |
| **不受 tier 门控** | 质量检查与模型能力无关 |
| **全部第一阶段非阻塞** | severity=low/mid，只报告不阻断，观察期后再决定是否升级 |
| **不替代审计 Agent** | E1-E4 是**代理指标**，语义质量判断仍由 `chapter_auditor_agent` 承担 |

**新增文件**：`scripts/writing_quality_check.py`（聚合 E1-E4，`--json` + exit code 0/1/2）

---

## 六、回归保障（P1）

**核心矛盾**：`agents/*.md` 是 prompt 文本，**无法被 pytest 测试**。设计三层把"不可测的 prompt"转为"可测的结构与产物"：

| 层 | 机制 | 可测内容 | 文件 |
|----|------|---------|------|
| **L1 静态契约测试** | pytest 解析 `agents/*.md` front matter 与章节结构 | 红线节存在且条数 ≤ `hard_rules_count`；`model`/`portability` 字段合法；锚点摘要引用的文件路径**真实存在**；红线编号无缺号；**`chapter_auditor_agent.md:98` 验收标准文本已更新**（防 C4 遗漏） | `tests/test_agent_contracts.py` |
| **L2 黄金样本快照回归** | 固定输入草稿 → 跑全部校验脚本 → 断言 JSON 输出逐字节不变 | **这是"不削弱 Claude 已验证质量"的可执行定义** | `tests/test_golden_snapshot.py` + `tests/golden/` |

> **🔴 审查层 Critical-4 修复：现有 fixture 对 A1 完全不敏感**
>
> **实测确认**（编排器复核）：现有 8 份 fixture（`tests/fixtures/alt-sample/` ×2 + `scripts/md2docx/tests/test_fixtures/` ×6）**全部 H4 数量 = 0、全部无 YAML `structure` 节点、"subsection" 零提及**：
>
> | fixture | H3 | H4 | YAML structure |
> |---|:-:|:-:|:-:|
> | alt-report.md / alt-report-cleaned.md | 3 | **0** | 否 |
> | multi-chapter.md | 8 | **0** | 否 |
> | with-image / with-table / minimal / front-matter / alt-topic-coffee | 0-1 | **0** | 否 |
>
> **后果**：若直接用现有 fixture 建快照，A1（subsections 字段名修复）改前改后将产生**零差异**——快照会给出"安全"的**假阳性**结论，而真正被修复的代码路径根本没被覆盖。
>
> **修复（必须在第 1 批执行）**：先新建一份 `tests/fixtures/structured-sample/` fixture，须包含：
> - 完整 YAML front matter，含 `structure.bodymatter` 且**至少 2 个章、每章 ≥2 节、至少 1 节含 ≥2 个 subsections**（覆盖"同一 parent 多个 subsection"这一 A1 编号 bug 的触发条件）
> - 对应的 Markdown 正文含匹配的 H2/H3/**H4**
> - 一份 `expected-structure.json`（A1 修复**后**的正确展平结果）
>
> 该 fixture 是 A1 的**唯一有效回归证据**；对现有 8 份 fixture 另建快照，用于证明 A1 未破坏既有行为（二者作用不同，都需要）。
| **L3 文档一致性测试** | 跨文件集合比对 | 角色表三处一致；`agents/` 实际文件与角色表一致；契约维度 id 与 agent md 提及一致；标准数量一致 | `tests/test_doc_consistency.py` |

**可复用基础设施**（已实测）：`scripts/md2docx/tests/`（**12 passed**）+ `conftest.py` 的 `run_converter`/`copy_fixture_to_workdir` 模式 + `tests/fixtures/alt-sample/`（含 `alt-report.md`/`expected.json`/3 张真实 PNG）

**L3 首次运行必然失败的 3 处已知不一致**（见 D3），属预期。

**⚠️ 回归保障的边界（不粉饰）**：L1-L3 能证明"结构未破坏、脚本判定未漂移、文档自洽"，**不能证明"Claude 上的写作质量未下降"**——后者需人工 A/B 评测。**最强的回归保证是决策 1：tier A 下默认全部新行为 off，使 Claude 路径在字节层面保持现状。**

---

## 七、依赖关系与执行顺序

```
Phase A 地基修复（P0，必须最先）
  A1 outline_reader 字段名 ──┐
  A2 失败语义统一 ───────────┤  ← A1 是 B2 的硬依赖
  A3 F7/F8 补实现 ───────────┘
            │
Phase B 确定性层（P0/P1，纯新增）
  B1 output_envelope_check ── 独立
  B2 outline_title_extract ── 依赖 A1
  B3 schema_validate ──────── 独立
  B5 degradation_report ───── 依赖 A2（台账写入点）
            │
Phase C 能力档与 prompt 分级（改 Agent 行为）
  C1 model-profile ────────── 依赖 B3
  C2 二维矩阵 ─────────────── 依赖 C1
  C3 红线分级 ─────────────── 依赖 A3（R4 需 C10/C11）
  C5 信封 nonce ───────────── 依赖 B1
  C4 Phase A 确认式 ───────── 依赖 C1（定义 JSON 落盘格式）
            │
  B4 precommit_consistency ── **依赖 C4**（消费其定义的 JSON）+ B3
            │
Phase D 流程与文档 + Phase E 质量增强（低风险，可并行）
  D1 门禁增列 ── 依赖 B1-B5
  D2 红队适配 ── 独立
  D3 文档订正 ── 独立
  D4 边界声明 ── 独立
  D5 finalizer 脚本化 ── 独立
            │
回归三层 ── 依赖全部
```

**推荐批次**：

| 批次 | 内容 | 前置动作 |
|------|------|---------|
| **第 1 批** | ①**新建 `tests/fixtures/structured-sample/`**（含 subsections/H4 的 fixture）②对现有 8 份 fixture 建 L2 快照基线 | ⚠️ **必须在 A1 之前**——现有 fixture 对 A1 零敏感（实测 H4 全为 0），不新建则快照是假阳性 |
| **第 2 批** | A1 + A2 + A3（地基修复） | ⚠️ **先决策 A1 与 `headings.py:557-591` Phase 7b 的协同方案**（V-2：Phase 7b 会覆盖 A1 的编号取真值，不决策则该项白做）；用新 fixture 验证 A1 生效；用旧快照验证未破坏既有行为 |
| **第 3 批** | B1 + B3（无依赖的新脚本） | — |
| **第 4 批** | B2 + B5 | 依赖 A1 / A2 |
| **第 5 批** | C1 + C2（能力档，默认 tier A 全 off） | 验证 Claude 路径字节不变 |
| **第 6 批** | C3 + C5（红线 + nonce） | 高风险，需人工 A/B；**C5 须含 `merge_drafts.py:78`** |
| **第 7 批** | **C4（Phase A 确认式，定义 JSON 落盘格式）** | ⚠️ 注意 4 处 stdout 表述成对修改 |
| **第 8 批** | **B4（precommit_consistency_check，消费 C4 定义的 JSON）** | ⚠️ **必须晚于 C4**——原方案把 B4 排第 4 批、C4 排第 7 批，消费者早于生产者 3 批 |
| **第 9 批** | D1-D6 + Phase E + 回归三层 | — |

---

## 八、回归风险评估

| 改动 | 风险 | 理由与缓解 |
|------|------|-----------|
| A1（outline_reader 字段名） | **MEDIUM-HIGH** | 会改变既有报告的 H4 编号输出。缓解：先建快照，逐差异人工确认为"修正"而非"回归" |
| A2（失败语义） | **MEDIUM** | WARNING→ERROR 可能使既有流程报错更多。缓解：延迟阻断而非立即阻断；仅在 CP6 强制 |
| A3（F7/F8） | **MEDIUM** | 新增 FATAL 检查可能误伤既有合法内容。缓解：先以 WARN 观察一轮；加 SRC-/CASE- 白名单 |
| B1-B5（新脚本） | **LOW** | 纯新增，不改现有调用路径 |
| C1-C2（能力档） | **LOW** | tier A 全 off，Claude 路径字节不变 |
| C3（红线分级） | **MEDIUM-HIGH** | 红线提取可能遗漏关键约束。缓解：判据严格限定"FATAL + 脚本可检出"；降级项仍由 auditor 语义评估（非删除）；需人工 A/B |
| C4（Phase A 确认式） | **MEDIUM** | 削弱认知承诺（已声明为权衡）；**`:98` 遗漏将致全面误阻断** | 
| C5（nonce） | **MEDIUM** | 正则放宽可能误匹配。缓解：三重格式约束 |
| D1-D5 | **LOW** | 门禁增列为纯加法；文档订正无行为影响 |

---

## 九、文件改动总览

### 新增文件

| # | 路径 | 说明 | 优先级 |
|---|------|------|--------|
| 1 | `model-profile.json` + 3 份 `.example` | 能力档声明；**主文件即 tier A 全 off 默认值，随方案交付、非用户自建**（Critical-1） | **P0** |
| 2 | `schemas/model-profile.schema.json` | Draft 2020-12 | P0 |
| 3 | `schemas/outline-structure.schema.json` | 从 §4.1.y 派生 | P0 |
| 4 | `schemas/writer-selfclaim.schema.json` | 6 字段 | P1 |
| 5 | `schemas/auditor-phase-a.schema.json` / `auditor-phase-b.schema.json` | Phase 输出 | P1 |
| 6 | `scripts/output_envelope_check.py` | 信封+nonce+噪声 | **P0** |
| 7 | `scripts/schema_validate.py` | 通用校验 + repair loop | **P0** |
| 8 | `scripts/outline_title_extract.py` | 标题提取（薄封装） | **P0** |
| 9 | `scripts/precommit_consistency_check.py` | Phase lint | P1 |
| 10 | `scripts/degradation_report.py` | 降级汇总与阻断 | P1 |
| 11 | `tests/test_agent_contracts.py` | L1 静态契约 | P1 |
| 12 | `tests/test_golden_snapshot.py` + `tests/golden/` | L2 快照 | **P0**（须最先建） |
| 13 | `tests/test_doc_consistency.py` | L3 文档一致性 | P1 |
| 14 | `PORTABILITY.md` + `portability-manifest.json` | 移植边界 | P2 |
| 15 | `scripts/delivery_checklist_check.py` | 交付清单 10 项聚合调用器 | P1 |
| 16 | `scripts/finalize_pipeline.py` | finalizer 顺序敏感步骤聚合（含 `failure_step` 字段） | P1 |
| 17 | `scripts/redteam_output_schema_check.py` | 红队 Markdown 表格结构校验 | P1 |
| 18 | **`tests/fixtures/structured-sample/`** | 含 subsections/H4 的 fixture + `expected-structure.json`（Critical-4） | **P0** |
| 19 | `scripts/writing_quality_check.py` | Phase E：E1-E4 质量代理指标聚合 | P1 |

> **验证修正 V-1**：原 #18 `model-profile.json` 与 #1 **完全重复**（同一路径列两次），已删除并重新编号。#1 的说明已合并 Critical-1 的"随方案交付 tier A 默认值"要求。

### 修改文件

| # | 路径 | 改动 | 优先级 |
|---|------|------|--------|
| 20 | `scripts/md2docx/assemble/outline_reader.py` | **修 bug**：`:149-150` 字段名 + `:158-159` dict 兼容 + `:163-166` 编号取真值 + `:216` manifest 计数 + `:55-67` 台账 | **P0** |
| 21 | `scripts/md2docx/assemble/headings.py` | **`:557-591` Phase 7b 重算 H4 编号逻辑**（见下方 V-2，非原写的 `:158-161`） | **P0** |
| 22 | `scripts/md2docx/assemble/builder.py` | `:210-219` WARNING→ERROR + 台账 | **P0** |
| 23 | `scripts/merge_drafts.py` | `:60` 补 try/except + 统一失败语义；**`:78` 字面量 startswith → 共享正则常量（Critical-5）** | **P0** |
| 24 | `scripts/figure_gate.py` | `:63-66` 补诊断 + 台账 | P1 |
| 25 | `scripts/contract_check.py` | 新增 C10(F7)/C11(F8)；`:64` F1 正则放宽 + 导出为共享常量；台账接入 | **P0** |
| 26 | `agents/chapter_writer_agent.md` | 红线 R1-R5 节 + 脚本硬拦清单 + 填空骨架 + `portability` | **P0** |
| 27 | `agents/chapter_auditor_agent.md` | 红线 A1-A5 节；**`:65`/`:98`/`:149` 三处 stdout 表述改为"JSON 摘要 + 落盘路径"（Critical-3）** | **P0** |
| 28 | `agents/contracts/auditor_contract.json` | 24 维度 + 5 proposal_extra 补齐三个 `*_hint`（**现仅 4 个维度有 hint**）；新增 `batch_grouping` 字段（现无） | **P0** |
| 29 | `agents/contracts/writer_contract.json` | D1-D10（实测 10 条）补 `hard_rule: true/false`（现无该字段） | P1 |
| 30 | `references/multiagent-orchestration.md` | §3 nonce、§4 噪声脚本化、§5 门禁增列、**§2 表 `diagram_agent`→新角色 + "11 角色"标题订正**、§1(`:15`) 降级触发条件 | **P0** |
| 31 | `references/writer-template.md` | F1 正则放宽（`:121`）；**`:117` 修正"contract_check 会检测 C2/C5/C6/C7/C8/C9"的表述**（实测不含 F7/F8） | **P0** |
| 32 | `agents/finalizer_agent.md` | 改为调用 `finalize_pipeline.py` + 查 `failure_step` 路由表；`:33` 剥离说明同步 nonce；12→13 项清单 | P1 |
| 33 | `references/stage-9-finalize.md` | 同上 + 降级确认项 + `:26` 全文通读强制人在环 | P1 |
| 34 | `references/workflow-stage7.md` | 编排脚本增 orchestrator 侧脚本调用 + Phase A/B JSON 落盘 | P1 |
| 35 | `references/workflow-stage8.md` | `:46`、`:82` 两处 `output_schema` 对齐 Markdown 表格 | P1 |
| 36 | `agents/card_synthesizer_agent.md` | `:49` `diagram_agent` → 新角色 | P1 |
| 37 | `references/stage-4-outline.md` | `:51` `diagram_agent` → 新角色 | P1 |
| 38 | `agents/outline_architect_agent.md` | `:3` description 去 `diagram_agent` | P1 |
| 39 | `SKILL.md` | `:42` 角色数、`:232` 标准数订正、能力档章节、参考文件清单；**`:183` 反例 13 的 stdout 措辞（Critical-3 第 4 处）** | **P0** |
| 40 | `README.md` | `:61` "10 个角色"、`:89` "17 条"标准数订正 | P2 |
| 41 | `references/appendix-converter-contract.md` | **C5 合约定义中 3 处 `AGENT-OUTPUT` 标记描述须同步 nonce 放宽**（V-4 新增，原清单遗漏） | **P0** |
| 42 | 其余 `agents/*.md` **×6**（非 ×9） | 加 `portability` + 红线节：`architecture_chart_agent`/`data_chart_agent`/`fact_verifier_agent`/`redteam_agent`/`redteam_synthesizer_agent`/`source_collector_agent`。**注意每个文件各含 2 处 `AGENT-OUTPUT` 信封声明，nonce 化时须一并放宽** | P2 |
| 43 | `agents/diagram_agent.md` | 移入 `agents/deprecated/` 或删除 | P2 |

> **🔴 验证修正 V-2（本轮最重要发现）**：原 #19 条目写 `headings.py:158-161` 为"parent 匹配处理 dict"，**经实跑核实完全错误**——该行实际是中文数字解析函数（`tens*10+ones`）。parent 匹配逻辑**只存在于 `outline_reader.py:158-159`**（已由 #20 覆盖），`headings.py` 全文不含 `isinstance(s, str)`。
>
> 但核查同时发现一处**清单原本完全遗漏的关键联动点**：`headings.py:557-591` 的 **Phase 7b 会在 overlay 之后按文档序无条件重算全部 H4 编号**（`ir.number = (current_chapter, current_section, subsection_counter)`）。这意味着 **A1 修复中"编号取真值 `subsection_no`"一项会被 Phase 7b 直接覆盖，修了也不生效**。
>
> **执行影响**：A1 必须与 Phase 7b 协同设计——要么让 Phase 7b 在 lookup 已提供 subsection 编号时跳过重算，要么放弃"取真值"改为接受 Phase 7b 的顺序编号（后者更简单，且 Phase 7b 的顺序编号在多数场景下结果正确）。**此项必须在 A1 实施前决策**。
>
> **附带说明**：Phase 7b 的存在也解释了为何 P0-2 的 subsections 丢失至今未造成 H4 编号全面错乱——它是一条独立兜底路径。这**降低了 P0-2 的实际危害程度**（分类仍丢失，编号有兜底），但不改变"结构清单被静默丢弃"这一事实。

> **验证修正 V-3**：原 #40 写"其余 `agents/*.md` ×9"，**实测为 ×6**（`agents/` 共 12 个 .md，已单列 6 个）。已改为 6 并列出确切文件名。

> **🔴 验证修正 V-4（新增遗漏条目）**：全库检索 `AGENT-OUTPUT` 发现 **18 个文件共 48 处**引用，其中 `references/appendix-converter-contract.md`（**3 处**，C5 合约定义）**原清单完全遗漏**。C5 是 nonce 化的直接相关方（`contract_check.py` 的 C5 检测正则由此合约定义），漏改将导致合约文档与脚本实现不一致。已补为 #41。
>
> **完整的 nonce 联动面（实测 18 文件 / 48 处）**：`agents/*.md` 12 个文件（`chapter_writer_agent` 6 处、`finalizer_agent` 4 处、其余各 2 处）、`references/` 4 个文件（`writer-template` 10 处、`multiagent-orchestration` 4 处、`appendix-converter-contract` 3 处、`stage-9-finalize` 2 处）、`scripts/` 2 个文件（`contract_check` 3 处、`merge_drafts` 2 处）。**执行 C5 时须以此清单为准逐处核对**，不可只改清单中显式列出的位置。

> **已删除的虚构条目**：原 #36 `scripts/md2docx/textstage/clean.py`（"信封剥离正则放宽"）—— **实测该文件及整个 `md2docx` 包 `AGENT-OUTPUT` 零命中**，条目基于错误前提，已移除。

**不变**：全部 `references/stage-*.md` 方法论内容（除 §4.1.y 引用订正）、`writing-standards.md` 标准正文、`研究报告格式规范.md`、`md2docx` 渲染层（除 `headings.py` Phase 7b）、`linkage-constants.json`

**总计**：新增 **19 项**、修改 **24 项**（编号 1-19 为新增，20-43 为修改）

---

### ✅ §九改动清单逐条实跑验证记录

> **验证范围**：**43/43 项已逐条实跑验证**（新增 19 项 + 修改 24 项），非抽查。
> **验证日期**：2026-07-28
> **验证方法**：对每一项执行 ①路径存在性检查（`pathlib.Path.exists()`）②引用行号内容读取比对 ③"现状"描述与实际代码/文档文本核对 ④全库 grep 检索遗漏联动点

**验证结果汇总**：

| 维度 | 结果 |
|------|------|
| 新增文件路径（19 项） | ✅ 全部确认**当前不存在**（符合"新增"定性） |
| 修改文件路径（24 项） | ✅ 全部确认**当前存在** |
| 引用行号准确性 | ⚠️ **1 处严重错误**（V-2）、其余 **23 处行号全部准确** |
| 条目重复 | ⚠️ **1 处重复**（V-1） |
| 计数准确性 | ⚠️ **1 处错误**（V-3） |
| 遗漏联动点 | ⚠️ **2 处**（V-2 的 Phase 7b、V-4 的 C5 合约文档） |

**本轮发现并已修正的 4 类问题**：

| 编号 | 问题 | 性质 | 修正 |
|------|------|------|------|
| **V-1** | 新增表 #1 与 #18 均为 `model-profile.json`，完全重复 | 重复条目 | 删除 #18，说明合并入 #1，全表重编号 |
| **V-2** | #19 声称 `headings.py:158-161` 是"parent 匹配"，**实为中文数字解析函数**；且**遗漏** `headings.py:557-591` Phase 7b 重算 H4 编号这一关键联动点 | **行号错误 + 关键遗漏** | 改为 `:557-591`；补充"A1 的编号取真值会被 Phase 7b 覆盖，须在实施前决策协同方案"的执行警告 |
| **V-3** | "其余 `agents/*.md` ×9" | 计数错误（实为 ×6） | 改为 ×6 并列出确切文件名 |
| **V-4** | `references/appendix-converter-contract.md`（C5 合约定义，3 处 `AGENT-OUTPUT`）未列入 | 遗漏条目 | 补为 #41；并给出全库 18 文件 / 48 处的完整 nonce 联动面清单 |

**逐项验证明细**（行号已实际打开核对）：

| 条目 | 验证的具体断言 | 结果 |
|------|--------------|------|
| #20 | `outline_reader.py:149` = `sub.get("parent","")`；`:150` = `sub.get("title","")` | ✅ 逐字一致 |
| #20 | `:158-159` = `for si,s in enumerate(sections)` + `isinstance(s, str)` | ✅ 一致 |
| #20 | `:163-166` 编号硬编码为 `(ch_no, parent_idx, 1)` | ✅ 一致 |
| #20 | manifest 计数用 `len()` | ✅ 实际在 `:216`（原写 `:215`，已订正） |
| #20 | `:55-67` YAML except 分支 + stderr `[FATAL]` | ✅ 一致 |
| #21 | 原写 `:158-161` parent 匹配 | ❌ **错误 → V-2 修正** |
| #22 | `builder.py:210-219` = `Level.WARNING` + `W-OL-01` | ✅ 一致 |
| #23 | `merge_drafts.py:60` = `yaml.safe_load` 无 try/except | ✅ 一致 |
| #23 | `:78` = 字面量 `s.startswith("[AGENT-OUTPUT-START]")` | ✅ 一致 |
| #24 | `figure_gate.py:63-66` 裸 `except yaml.YAMLError: return None` | ✅ 一致 |
| #25 | `contract_check.py:64` F1 正则精确匹配 | ✅ 一致；`BANNED_PATTERNS` 实测 7 条不含 F7/F8 |
| #27 | `chapter_auditor_agent.md` `:65`/`:98`/`:149` 三处 stdout | ✅ 三处全部命中 |
| #28 | `auditor_contract.json` 24 维度 + 5 proposal_extra；仅 4 维度有 hint；无 `batch_grouping` | ✅ 全部实测确认 |
| #29 | `writer_contract.json` 10 维度；无 `hard_rule` 字段 | ✅ 确认 |
| #30 | `multiagent-orchestration.md` §1-§10 全部存在；降级兜底在 `:15`；§2 标题为"11 角色" | ✅ 确认 |
| #31 | `writer-template.md:117` C2/C5/C6/C7/C8/C9 表述；`:121` F1 正则 | ✅ 两处均一致 |
| #32 | `finalizer_agent.md:33` 剥离 `[AGENT-OUTPUT-START]`/`[AGENT-OUTPUT-END]` | ✅ 一致 |
| #33 | `stage-9-finalize.md:25` 红队处理确认、`:26` 全文通读 | ✅ 两处一致 |
| #34 | `workflow-stage7.md` 已含 `contract_check.py`/`precommit`/`persist(`/`chapter-reports` | ✅ 确认（改动为增量而非新建） |
| #35 | `workflow-stage8.md:46`、`:82` 两处 `output_schema` | ✅ 两处一致 |
| #36 | `card_synthesizer_agent.md:49` `diagram_agent` | ✅ 一致 |
| #37 | `stage-4-outline.md:51` `diagram_agent`（行尾） | ✅ 一致 |
| #38 | `outline_architect_agent.md:3` description 含 `diagram_agent` | ✅ 一致 |
| #39 | `SKILL.md:42` "11 个角色"、`:232` "含 12 条标准"、`:183` 反例 13 stdout | ✅ 三处一致 |
| #40 | `README.md:61` "### 10 个角色"、`:89` "写作标准体系（17 条）" | ✅ 两处一致 |
| #41 | `appendix-converter-contract.md` 3 处 `AGENT-OUTPUT` | ✅ 新增条目，已确认 |
| #42 | 其余 agents .md 数量 | ❌ **×9 错误 → V-3 修正为 ×6** |
| #43 | `agents/diagram_agent.md` 存在 | ✅ 确认 |
| 新增 #1-#19 | 19 个路径全部不存在 | ✅ 全部确认 |

**批次顺序复核（是否存在类似 B4/C4 的生产者/消费者倒置）**：

| 检查项 | 结果 |
|--------|------|
| B4（消费 Phase A JSON）晚于 C4（定义格式） | ✅ 已修（第 8 批 > 第 7 批） |
| B2（复用 `_build_structure_lookup`）晚于 A1（修该函数） | ✅ 第 4 批 > 第 2 批 |
| C3 红线 R4（依赖 C10/C11）晚于 A3（实现 C10/C11） | ✅ 第 6 批 > 第 2 批 |
| B5（写台账）晚于 A2（建台账写入点） | ✅ 第 4 批 > 第 2 批 |
| C1（model-profile）晚于 B3（schema_validate 校验它） | ✅ 第 5 批 > 第 3 批 |
| **A1 与 Phase 7b（V-2 新发现）** | ⚠️ **需在 A1 实施前先决策协同方案**，已加入第 2 批前置条件 |
| L2 快照 + `structured-sample` fixture 早于 A1 | ✅ 第 1 批 > 第 2 批 |

**客观无法验证的项（明确标注原因）**：

| 项 | 无法验证的原因 |
|----|--------------|
| 新增 19 项的**内部实现正确性** | 文件尚不存在，只能验证"路径当前为空"这一定性；实现质量须在编码后由 `code-validator` 验证 |
| #26/#42 的"红线节"具体内容 | 红线文本尚未撰写，仅验证了宿主文件存在与当前规则密度（30 处/15 处） |
| DeepSeek V3.2/V4 **真机行为** | V4 未正式发布；V3.2 未做端到端跑测。所有"弱模型预期表现"仍为基于规格与评测的推断（已列入 §12 未解决问题 4） |
| `model-profile.json` 三份 `.example` 的**字段取值合理性** | 依赖真机验证，当前取值为基于官方规格的设计值 |

> **✅ 清单可信度声明（已完成全覆盖验证）**：本清单 **43/43 项已逐条实跑验证**（详见上方验证记录），发现并修正 **4 处问题**（1 处重复条目 / 1 处行号严重错误 / 1 处计数错误 / 2 处遗漏联动点，其中 V-2 同时属行号错误与遗漏）。
>
> **前一轮的短板已消除**：审查层此前抽查 3 处发现 2 处出错，据此推断整表错误率可能较高。本轮全覆盖验证的实际结果是——**24 项修改条目中 23 项行号准确**，错误集中在 1 项（V-2 的 `headings.py`）。但该项恰好是最关键的一项，且连带暴露了 Phase 7b 这个会**使 A1 修复失效**的遗漏联动点。
>
> **仍需注意**：新增 19 项的实现正确性无法在编码前验证（文件尚不存在），须在编码后由独立验证环节把关。

---

## 十、验收标准

### Phase A
- [ ] **`tests/fixtures/structured-sample/` 已建，含 ≥2 章 / 每章 ≥2 节 / ≥1 节含 ≥2 subsections / 对应 H4**
- [ ] 按规范格式构造的 subsections，`_build_structure_lookup()` 返回 SUBSECTION 条目数 = YAML 声明数
- [ ] **A1 与 Phase 7b 的协同方案已决策**（推荐方案甲：放弃"编号取真值"，接受 Phase 7b 顺序编号）；若采方案乙，须额外验证 Phase 7b 跳过重算后编号仍正确
- [ ] `build_structure_manifest` 计数 = lookup 实际入表数（消除谎报）
- [ ] 三个 SSOT 消费者（merge_drafts/builder/figure_gate）对同一坏 YAML 的失败级别一致
- [ ] `merge_drafts.py` 对格式错误的 YAML 不再抛未捕获 traceback
- [ ] `contract_check.py --json` 输出含 `C10`/`C11` 字段，且**第一阶段 `pass` 恒为 True**（非阻塞）

### Phase B
- [ ] 8 个新脚本均支持 `--json` 且 exit code 语义为 0/1/2（与 `contract_check.py` 一致）
- [ ] `output_envelope_check.py` 对纯中文正文的噪声比率判定 = 0（无误报）
- [ ] `schema_validate.py` 能捕获缺字段/类型错/枚举越界三类错误并输出可回传 prompt 的错误消息
- [ ] `outline_title_extract.py` 输出的标题不含任何编号前缀
- [ ] **`precommit_consistency_check.py` 消费的 JSON 格式与 C4 定义一致**（B4 在 C4 之后实现）

### Phase C
- [ ] **仓库内已提供 tier A 全 off 的默认 `model-profile.json`**
- [ ] **文件缺失时 fallback 到 tier A（非 tier C）；仅解析失败才降 tier C**
- [ ] **tier A 下，全部校验脚本对黄金样本的输出与改造前逐字节一致**（最关键项）
- [ ] `chapter_writer_agent.md` 红线节恰 5 条 + 独立的"脚本硬拦清单"表格
- [ ] **全库检索 `stdout`，无"要求粘贴完整 stdout"残留**（4 处均已改）
- [ ] Phase A 确认式输出在 `max_output_tokens<16000` 时 < 1000 tokens
- [ ] `phase_a_mode` 由 `max_output_tokens` 派生，不出现在 schema 配置字段中
- [ ] nonce 与无 nonce 两种格式均能被提取正则正确处理
- [ ] **`merge_drafts.py:78` 已改用共享正则常量，nonce 化标记能被正确剥离**

### Phase E
- [ ] `writing_quality_check.py` 输出 E1-E4 四类指标，全部 severity=low/mid 非阻塞
- [ ] E4 缩写检查已接入 glossary aliases + 通用缩写白名单，误报率可接受

### Phase D
- [ ] `diagram_agent` 在全部 4 处文档中已替换
- [ ] 角色数量与标准数量在 SKILL.md/README.md/multiagent-orchestration.md 三处一致
- [ ] `degradation_report.py` 在存在未确认 L-显著 事件时阻断 CP6
- [ ] L1/L2/L3 三层测试全部通过

---

## 十一、不做的事项（明确排除）

| 排除项 | 理由 |
|--------|------|
| **运行时模型能力探针** | 探针能客观判分的能力恰是脚本已兜底的；测不出的语义能力恰无客观判分手段——价值被架空 |
| **标准 0/19 的语义质量"完全"脚本化** | 只能做黑名单/白名单代理指标，天花板明确（拦已知坑，拦不住新坑）。**修订：代理指标部分已纳入 Phase E（E3/E4），此处排除的是"用脚本替代审计 Agent 的语义判断"这一更强主张** |
| **阶段 9"红队处理确认"与"全文通读"脚本化** | 结构性不可脚本化（语义比对"处理建议 vs 实际改动"、整体阅读判断）。保留人在环 |
| **`Agent` depth-1 委派在非 Claude 宿主的等价复现** | 生态锁定，非工程量问题。声明边界 + 降级，不承诺等价 |
| **Phase A/B 一致性的"防伪装"保证** | 机械检查只能提高作弊成本，不能证明真实时序遵守。如实声明天花板 |
| **swap-and-average 默认启用** | 使红队调用轮次翻倍，而阶段 8 成本已是 3-5 倍放大。仅 tier C + 高风险报告时启用 |
| **改用独立 JSON 侧车替代 YAML front matter** | 维护两个真源必然漂移，一致性风险反而上升 |
| **完全替换固定分隔符为随机串** | 破坏 F1 检测 / `merge_drafts.py:78` 剥离 / finalizer 全链路，改动面失控。用后缀式 nonce 达成同等可靠性 |
| **英文报告输出支持** | 沿用上一轮方案的排除理由，工作量远超本次范围 |

---

## 十二、已知限制与未解决问题（提交用户决策）

1. **[P3] `Tier B × 完整档` 未经实测** —— 二维矩阵中该格为设计推演。建议首个真实项目先跑分层档验证
2. **[P3] 分批 Phase A 破坏跨批标准一致性** —— 批 1 承诺的严格度是否在批 4 保持，**无脚本解**。缓解：批间注入前批摘要，但这是设计天花板
3. **[P3] 红线提取的完备性无法自动验证** —— "5 条红线是否真的覆盖了最关键的 5 项"依赖人工判断。L2 快照能证明脚本判定未漂移，不能证明写作质量未降
4. **[P3] 本方案未在真实 DeepSeek 上端到端验证** —— 全部"弱模型预期表现"为基于规格与评测数据的推断。**建议在执行 Phase C 前先做一次小规模真机验证**（如用 DeepSeek 跑一份 brief 档报告）
5. **[P3] "Curse of Instructions" 的 2.5% 为理论推算值** —— 实际衰减可能因规则相关性而缓于纯乘法模型。红线 ≤5 的阈值取自业界经验，非本项目实测

---

## 十三、设计层矛盾裁决记录

设计层三个 Agent（架构 / 工作流 / 接口）独立工作、互不共享中间产物——这有意制造"独立视角"。以下是交叉整合中发现的矛盾与裁决：

| 类型 | 涉及方 | 描述 | 裁决 | 理由 |
|------|--------|------|------|------|
| **CONTRADICTION** | 编排器初读 vs 架构师 | 审计维度数：26 vs 24 | **采信 24**（proposal_extra 5，合计 29） | 编排器实跑 `json.load` 复核确认；架构师另称"已带 hint 的 5 个"亦有偏差，实测为 **4 个** |
| **CONTRADICTION** | 架构师 vs 工作流 | Phase A 应对手段：架构师主张"确认式"（预置 hint，输出 confirm/adjust）；工作流主张"分 3 批 + 批内降权" | **两者叠加，非二选一** | 确认式解决"单批输出量"，分批解决"跨批一致性风险"。但**确认式优先**——它把 96 字段降至约 450 tokens，此时分批的必要性大幅下降，仅在 proposal 档（29 维度）或实测仍超限时启用 |
| **VARIANCE** | 架构师 vs 工作流 | 红队适配：架构师主张"人格 prompt 差异化 + 顺序轮换"；工作流主张"跨厂商异构（DeepSeek+GLM）优先" | **采纳工作流的跨厂商异构为首选，架构师方案为退化路径** | 跨厂商异构最贴近原设计意图（"让模型本身构成视角差异"），且成本增量最小；但它**依赖环境同时提供两个模型端点**，不可假定，故必须保留单模型退化路径 |
| **VARIANCE** | 架构师 vs 工作流 | max_rounds 是否调整 | **保持 2 不变**，但采纳工作流的"issue > 8 条时第 2 轮改全量重写"建议 | 放大轮次只会让通不过的稿子多耗调用，且架空 P0 决策树 |
| **GAP** | 工作流 | 未覆盖"Phase B 也可能超 8K"（其自评为待验证项） | **补入方案**（见 C4 手段 3） | 架构师已给出解法（stdout 落盘 + 路径引用），可直接采纳 |
| **OVERLAP** | 架构师 vs 工作流 | 二者都设计了降级台账（`.degradation-log.jsonl` vs `degradation-log.jsonl`）与交付清单聚合器 | **合并去重**，统一路径为 `research/.degradation-log.jsonl` | 功能同构，取架构师的 `event_id` 幂等去重设计 + 工作流的"超阈值额外提示"设计 |
| **证伪** | 工作流风险项 5 | 称现有脚本可能"只能 CLI 运行、需先重构才能被聚合脚本 import" | **不成立** | 编排器实测：`contract_check.py`/`convert_references.py`/`term_consistency_check.py`/`merge_drafts.py` **全部有 `__main__` guard**，函数级可直接复用 |
| **证伪** | 方案初稿（编排器） | 称 F8 正则需加 SRC-/CASE- 白名单防误报 | **不必要** | 实测 8 个真实样本零误报，连字符天然阻断匹配 |
| **降级** | 工作流 | 主张新增 `source_index_schema_check.py`/`claims_ledger_schema_check.py`/`card_index_schema_check.py` 三个 CSV 校验脚本 | **降为 P2，且建议合并进 `schema_validate.py`** | 三者本质同构（CSV 必填列 + 枚举校验），单独建三个脚本属过度设计；且它们针对的问题未出现在审计的 30 项发现中 |

### 审查层（DesignAuditor）意见的裁决

| 类型 | 审查意见 | 裁决 | 依据 |
|------|---------|------|------|
| **CONTRADICTION** | Critical-1：缺失配置默认 tier C 推翻核心保证 | **全盘采纳** | 逻辑自洽性问题，无需实测即成立 |
| **CONTRADICTION** | Critical-2：B4/C4 格式互斥 + 批次倒置 | **全盘采纳** | 文档内部对读即可确认 |
| **CONTRADICTION** | Critical-3：stdout 实为 4 处 | **全盘采纳** | 实跑 grep 确认 4 处（`:65`/`:98`/`:149` + `SKILL.md:183`） |
| **CONTRADICTION** | Critical-4：fixture 对 A1 零敏感 | **全盘采纳** | 实测 8 份 fixture H4 全为 0、structure 全为 False |
| **CONTRADICTION** | Critical-5：`merge_drafts.py:78` 字面量匹配 | **全盘采纳** | 实测确认为 `s.startswith("[AGENT-OUTPUT-START]")` |
| **CONTRADICTION** | High：`clean.py` 是虚构条目 | **全盘采纳** | 实测该文件及整个 md2docx 包 `AGENT-OUTPUT` 零命中 |
| **PARTIAL** | High：4 项"已有 FATAL 兜底"的约束被错误降为细则 | **不采纳前提，采纳内核** | **实测反证**：`card_overlap`=mid、`QS4`=low、F10 阶段7=WARN、标准0 无脚本 → 均不满足"FATAL"判据，降级正确。但采纳"应显式列出脚本兜底项"的建设性内核 → 新增两层结构 |
| **VARIANCE** | High：`phase_a_mode` 应由 token 上限派生 | **采纳** | 前瞻性正确——避免 V4 若长输出仍被误降级 |
| **GAP** | High：方案 90% 防御性，未回应"提高质量" | **采纳** | 直接对照用户原话确认属实 → 新增 Phase E |

| 建议 | 来源 | 不采纳理由 |
|------|------|-----------|
| swap-and-average 在"完整档 × 弱模型"默认启用 | 工作流 | 工作流自己标注"操作定义不确定"（是评审者顺序 swap 还是角色互换，属外推）。且使阶段 8 成本再放大 1.4-1.6 倍。**降为 tier C + 高风险报告时可选** |
| 把 `outline_reader.py` bug 修复排除在方案范围外、另立任务 | 工作流 | 该 bug 是本方案多个组件的共同地基，且**正在静默损坏 Claude 路径**。排除它会导致"schema 校验通过但下游仍丢数据"的假阳性——**必须纳入方案作为 Phase A 第一项** |

---

---

## 十四、执行结果记录

> **执行日期**：2026-07-28 ~ 2026-07-29
> **执行方式**：编排器（主对话）分派 implementer / code-validator / integration-verifier 子 Agent，逐批实施 + 逐批门禁
> **最终状态**：**9 个批次全部完成**，`pytest tests/ scripts/md2docx/tests/` → **281 passed**
> **门禁执行**：G1（交叉验证）×3 轮、G4（测试）逐批、G6（分布式要求聚合复核）、G7（端到端集成验证）。**G2（领域安全审查）跳过——本项目未注册 `domain-guard` 角色**

### 14.1 逐批执行结果

| 批次 | 内容 | 测试 | 结果 |
|---|---|---|---|
| **第 1 批** | 新建 `tests/fixtures/structured-sample/`（2 章 4 节 **5 个 H4**）+ 8 份 fixture 的 L2 快照基线 | 22 passed + **2 xfailed** | ✅ xfail(strict=True) 证明 fixture 确实对 A1 敏感（改前 SUBSECTION 入表数 = 0） |
| **第 2 批** | A1 字段名/dict兼容/守卫/manifest + A2 失败语义与台账 + A3 C10/C11 | 67 passed | ✅ G1 发现 6 项 → 全部回炉修复（见 14.2） |
| **第 3 批** | B1 `output_envelope_check.py` + B3 `schema_validate.py` + 5 份 schema | 67 → 89 passed | ✅ G1 PASS |
| **第 4 批** | B2 `outline_title_extract.py` + B5 `degradation_report.py` | 89 passed | ⚠️ G1 发现 B2 的 P1 假阳性 → 已修复 |
| **第 5 批** | C1 `model-profile.json` + 3 份 example + 加载器 + C2 二维矩阵 | 114 passed | ✅ 三条兜底路径实测通过 |
| **第 6 批** | C3 红线分级（writer/auditor 各 5 条）+ C5 nonce（**19 文件/49 处**） | 151 passed | ✅ Critical-5 端到端实证：标记零残留 |
| **第 7 批** | C4 Phase A 确认式 + 29 维度 hint 补齐 + `batch_grouping` + 4 处 stdout | 180 passed | ✅ 确认式输出 **205 tokens**（限 1000） |
| **第 8 批** | B4 `precommit_consistency_check.py` | 202 passed | ✅ 与 C4 生产者格式端到端串联通过 |
| **第 9 批** | D1-D6 + Phase E（E1-E4）+ 回归三层（L1/L2/L3） | 280 → 281 passed | ✅ 含 C2/C6 两处 P0 冲突修复 |

### 14.2 执行中发现并修复的问题

#### 🔴 P0-1：C2 章容器冲突（执行中**新暴露**，方案未预见）

- **现象**：`merge_drafts.py:250` 按规范生成的章容器 `## 第 1 章：xxx` 必然命中 `contract_check.MANUAL_NUMBER_PATTERN`，且 `merged + stage9` 下 severity 升为 **fatal**（标注"不可降级放行"）。
- **后果**：**任何含编号章节的真实报告都无法通过 CP6 交付门禁** —— 检查器把自家合并管道的标准输出判为致命错误。此前被 `merge_drafts.py` 阶段 E/F 校验"只 WARN 不阻断"掩盖，D5 管道建成后第一次真正生效。
- **修复**：新增 `PIPELINE_CHAPTER_CONTAINER_PATTERN`，**仅在 merged 模式下**豁免管道自动生成的章容器。
- **裁决依据**：C2 的立法意图是禁止**作者手写**编号前缀（编号应交由 Word 自动编号域生成），而章容器是**管道自身按规范产出的结构性标记**，下游 `headings.py` 会将其识别为 CHAPTER 并接管编号。
- **豁免精确性已实证**：`## 第 1 章：绪论` 放行，而作者手写的 `### 1.1 xxx` **仍判 fatal**。

#### 🔴 P0-2：C6 引用格式冲突（G7 端到端验证发现，与 P0-1 同构）

- **现象**：`convert_references.py` 按 GB/T 7714 顺序编码制正确把 `[SRC-001]` 转为 `[1]`，紧接着 `contract_check` 的 C6 又把纯数字引用判为违规——**定稿管道否定自己上一步的正确产出**。
- **后果**：任何含至少一条参考文献的报告都无法走完管道，`delivery_checklist`（含降级台账确认、红队确认、全文通读确认）**永远不可达**。
- **修复**：`_check_c6_references()` 改为**分阶段判定**，与 C7 已有的 stage7/stage9 对称设计一致：
  - stage7 分章草稿 → 纯数字引用**仍违规**（作者不应提前写死编号）
  - stage9 + merged 合并终稿 → 纯数字引用是**预期产出**，不判负
  - `slash_src` / `s_variant` 两类真正的格式错误 → **任何阶段都仍判负**
- **快照核对**：8 份 golden 快照差异经逐键比对，**全部为新增 `pure_num_expected` 一个键，零既有键值变化**（纯加法），核对通过后才刷新。

#### 第 2 批 G1 交叉验证发现的 6 项

| 编号 | 问题 | 修复 |
|---|---|---|
| **D1** | `--strict` 下 W-OL-01 被升为 FATAL，**DOCX 完全不产出**（基线 39172 字节 → 0），违反方案 §A2「不中断转换」 | `issues.py` 新增 `STRICT_ESCALATION_EXEMPT_CODES` 豁免集 |
| **D2** | 台账路径随 cwd 漂移（`scripts/research/` vs 项目根），会让 **CP6 读到空台账、延迟阻断静默失效** | `_resolve_log_path()` 锚定项目根 `_PROJECT_ROOT` |
| **D3** | `event_id` 粒度过粗，两个不同孤儿 subsection 被折叠为 1 条，与 §B5「强制逐条列出 impact」冲突 | 新增 `instance_key` 参与哈希；台账 `input_path` 改为透传真实路径 |
| **D5** | 一次转换中 `_build_structure_lookup()` 被调 **3 次**，同一诊断打印 3 遍 | `build_structure_manifest()` / `apply_structure_overlay()` 增加 `lookup` 复用参数（实测降至 **1 次**） |
| **D6** | golden 快照 docstring 自称"改动前快照"，实为改动后，对"纯加法"零证明力 | 改为准确描述"当前基线"+ 刷新纪律 |
| **O1** | W-OL-01 两处发射点级别不一致 | 按语义拆分为 W-OL-01（解析失败）/ W-OL-02（文件不可读） |

#### 第 4 批 G1 发现的 B2 P1 缺陷

- **现象**：`--chapter-no N` 过滤时，YAML 侧只剩 1 章而 Markdown 侧仍扫全文，导致其余章标题全被误判 `markdown_only`。实测：全量模式 0 告警，`--chapter-no 1` **9 条**、`--chapter-no 2` **10 条**全部为假阳性。
- **后果放大**：`--chapter-no` 正是阶段 7 单章注入的主用法；每条假阳性写 L-显著台账且因 `instance_key` 不同**不会被幂等去重**，一份 10 章报告会累积数十条噪声，**恰好淹没 B5 刚建立的交付门禁** —— 使 §B5「强制逐条确认防形式主义」的设计变成它自己警惕的形式主义。
- **修复**：单章模式下抑制 `markdown_only` 方向（保留 `yaml_only`）；一致性告警**不再触发 exit 1**（方案 §D1 只定义"提取为空 → P0"）；告警级别由 L-显著**降为 L-记录**（其 `fallback_used="report_only_no_auto_fix"`，未发生任何降级回退，按 §A2 定义属 L-记录）。

### 14.3 方案与实际不符之处（已在正文对应位置订正）

| # | 方案原文 | 实际 | 处理 |
|---|---|---|---|
| 1 | A1「三处必须同时修」 | 实为 **4 处**——守卫条件 `parent_title in lookup` 不改则前两处无效 | 已补入 §A1 第 4 项 |
| 2 | nonce 联动面 18 文件/48 处 | **19 文件/49 处**（多出第 3 批新建的 `output_envelope_check.py` 6 处） | 执行时以实测为准 |
| 3 | stdout「4 处」位置 | 位置随第 6 批 C3 改动漂移；其中 2 处已被红线 A1 前瞻兼容措辞消化，实改 `chapter_auditor_agent.md` 3 处 + `SKILL.md` 1 处 | 已按实测执行 |
| 4 | `diagram_agent` 残留 4 处 | 实测 **7 个文件** | 已全部替换 |
| 5 | C3 脚本硬拦清单的 severity | 方案给的单一标签（low/high）在多数脚本中实为**混合/条件性**（依赖规则子项与调用阶段） | 已按实测 severity 如实改写 |
| 6 | `event_id = sha1(stage+component+reason+input_path)` | 该公式与 §B5「逐条列出 impact」存在张力（同类不同实例被折叠） | 已增加 `instance_key` |

### 14.4 验收标准达成情况

**Phase A**（7 项）：✅ 全部达成
- fixture 已建（2 章/4 节/**5 个 subsection**，覆盖"同一 parent 多 subsection"）；SUBSECTION 入表数 = YAML 声明数 = 5；manifest 计数 = lookup 实际数（新增 `subsection_declared_count` 区分声明值）；三消费者失败级别统一；`merge_drafts.py` 不再抛裸 traceback；C10/C11 `pass` 恒为 True；**Phase 7b 协同已决策（方案甲）**

**Phase B**（5 项）：✅ 全部达成
- 新脚本 `--json` + exit 0/1/2 语义统一；**纯中文正文噪声比率 = 0**（无误报）；schema 三类错误全捕获且输出 `repair_prompt`；提取标题无编号前缀；B4 与 C4 JSON 格式端到端串联实证兼容

**Phase C**（9 项）：✅ 全部达成
- 仓库内已提供 tier A 全 off 默认配置；**缺失→tier A / 解析失败→tier C** 三路径实测；**tier A 下 golden 快照逐字节不变**；红线恰 5 条 + 独立硬拦清单；**全库 stdout 残留 = 0**；确认式输出 **205 tokens**（限 1000）；`phase_a_mode` 为派生量不进 schema；nonce/无 nonce 双格式均正确处理；`merge_drafts` 改用共享正则常量且降级路径非 no-op

**Phase D**（4 项）：✅ 全部达成
- `diagram_agent` 零残留（7 文件全替换 + 移入 `agents/deprecated/`）；**角色数 11 / 标准数 23 三处一致**（并由 L3 测试锁定）；`degradation_report.py` 未确认 L-显著阻断 CP6；L1/L2/L3 三层测试全部通过

**Phase E**（2 项）：✅ 达成，E4 有已知误报（见 14.5）

### 14.5 无法本地验证 / 遗留项（如实标注，未假装通过）

| # | 项 | 状态 |
|---|---|---|
| 1 | **DeepSeek V3.2 真机行为**（tier B 端到端） | ❌ **无法本地验证**（无 DeepSeek 端点）。`phase_a_mode` 派生逻辑已本地验证一致，但"DeepSeek 在 confirm 模式下是否真按 `### <维度id>` + `confirm`/`adjust:` 格式产出"需真机测试。**手动核对步骤**：用真实 API 跑一次 Phase A → 保存原始 Markdown → 执行 `python scripts/phase_a_to_json.py --chapter <id> --json <file>` → 确认能解析出 24 维度且不抛 `ValueError` |
| 2 | `Tier B × 完整档` | ❌ 未实测（方案 §十二 P3 原有遗留）。建议首个真实项目先跑分层档 |
| 3 | **E4 缩写检查误报** | ⚠️ 已发现具体实例：复合缩写 `CI/CD` 中的后半 `CD` 被误判为待展开缩写（前半 `CI` 因后跟 `/` 被国标前缀逻辑豁免）。**非阻塞**（exit 恒 0），方案已预警"E4 误报风险最高"，此为该预警的实例化证据 |
| 4 | **红线完备性** | ⚠️ 无法自动验证（方案 §十二 P3 原有遗留）。已用降级映射表逐条证明 **45 处原约束（writer 30 + auditor 15）全部有归宿、无丢失**，但"这 5 条是否真是最关键的 5 条"仍依赖人工判断 |
| 5 | **降级台账无 run 级隔离** | ⚠️ 台账为全生命周期累积文件，无轮转/按次归档。同一项目连续处理多份报告时历史 L-显著事件会持续阻断新交付。**建议后续补充"按报告/按 session 隔离"的设计说明** |
| 6 | Phase A/B **防伪装**保证 | ⚠️ 方案已声明的固有天花板：机械校验只能提高作弊成本，不能证明真实时序遵守。B4 脚本 docstring 已如实写明 |
| 7 | B4 的 **A1/A4 检查** | ⚠️ 纯 JSON 输入下无数据来源（A1 需原始报告文本、A4 需行计数）。设计为**可选**：传 `--phase-b-report` 才执行，未传时显式标记 `"status": "skipped"`（**非静默跳过**） |

### 14.6 交付物清单

**新建脚本（11）**：`degradation_log.py`、`degradation_report.py`、`output_envelope_check.py`、`schema_validate.py`、`outline_title_extract.py`、`model_profile.py`、`phase_a_to_json.py`、`precommit_consistency_check.py`、`writing_quality_check.py`、`delivery_checklist_check.py`、`finalize_pipeline.py`

**新建配置（9）**：`model-profile.json` + 3 份 `.example` + `schemas/` 下 5 份 Draft 2020-12 schema

**新建文档（2）**：`PORTABILITY.md`、`portability-manifest.json`

**新建测试（13 份）**：`test_golden_snapshot.py`、`test_structured_fixture.py`、`test_agent_contracts.py`、`test_doc_consistency.py`、`test_output_envelope_check.py`、`test_schema_validate.py`、`test_outline_title_extract.py`、`test_degradation_report.py`、`test_model_profile.py`、`test_envelope_nonce.py`、`test_phase_a_to_json.py`、`test_precommit_consistency_check.py`、`test_writing_quality_check.py`、`test_delivery_checklist_check.py`、`test_finalize_pipeline.py` + `tests/fixtures/structured-sample/` + `tests/golden/`（8 份快照）

**修改既有**：`outline_reader.py`、`builder.py`、`headings.py`（仅参数透传，**Phase 7b 逻辑零改动**）、`issues.py`、`merge_drafts.py`、`figure_gate.py`、`contract_check.py`、`check_no_hardcode.py`、全部 `agents/*.md`、多个 `references/*.md`、`SKILL.md`、`README.md`

**归档**：`agents/diagram_agent.md` → `agents/deprecated/diagram_agent.md`

---

> **本方案已执行完成。** 对应的问题诊断见 `design/model-compatibility-audit-report.md`；执行结果见上方 §十四。
