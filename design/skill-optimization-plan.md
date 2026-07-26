# deep-research-report 技能质量优化实施方案

> **版本**：V1.1  
> **日期**：2026-07-26  
> **状态**：✅ 已全部执行（commit `70f2d91` + `待提交`）  
> **基于**：`design/skill-quality-audit-report.md` 综合审计报告（5 维度审计，34 项发现，P0×4 + P1×7 + P2-P3×13）  
> **方法**：分层设计 + 依赖分析 + 交叉影响评估 + 回归风险评估

---

## 一、方案概述

### 1.1 优化目标

审计发现系统在"保证报告不犯错"方面极其强大，但在"保证报告写得好"方面存在系统性缺口。本方案聚焦于**消除这些缺口而不引入新问题**。

### 1.2 四层改动架构

| 层级 | 内容 | 改动量 | 风险 |
|------|------|--------|------|
| **Phase A**：写作质量标准 | 新增标准 18-21 + 写作指导 + 自查清单 | ~200 行文档 | LOW（纯增量） |
| **Phase B**：审计增强 | QS4 段落统计 + 新审计维度 + Writer prompt 富化 | ~100 行代码 + ~50 行文档 | LOW（纯增量） |
| **Phase C**：转换器增强 | REF 域交叉引用 + YAML 错误处理 | ~150 行代码 | MEDIUM（触核渲染路径） |
| **Phase D**：编排增强 | P0 死锁决策树 + 上下文窗口文档 | ~80 行文档 | NONE（纯文档） |

### 1.3 关键设计决策

1. **REF 域实现使用现有基础设施**：`oxml_helpers.make_field()` + `xref_registry` + `bookmark_name` 已全部就绪，只需在 `render/paragraphs.py` 中消费这些数据替换静态文本。
2. **新标准全部增量添加**：不修改现有标准 0-17 的编号和内容，向后完全兼容。
3. **card_overlap_check.py 无需代码改动**：审计中的"卡片-正文 vs 卡片-卡片"歧义经核实不成立——脚本已正确实现卡片-正文重合度检测，仅需文档澄清。
4. **不强制全量实施**：每个 Phase 独立可测、独立可部署，不互相阻塞。

---

## 二、Phase A：写作质量标准层（文档层，纯增量）

### A1. 新增标准 18：章节与节间过渡

**直接修改**：
- `references/writing-standards.md`（新增标准）
- `references/stage-7-writing.md`（§7.2.3 自查清单 + §7.4 质量标准）

**间接更新**：
- `agents/contracts/writer_contract.json`（新增 D8 维度）
- `agents/contracts/auditor_contract.json`（新增过渡检查项）
- `agents/chapter_writer_agent.md`（新增 prompt 要求）
- `agents/chapter_auditor_agent.md`（新增审计维度）
- `references/stage-9-finalize.md`（新增 finalizer 步骤）

**标准 18 内容**：

```markdown
## 标准 18：章节与节间过渡（叙事连贯性）

**原则**：报告不是独立分章的汇编，而是连贯的论证链条。章与章之间、同章内节与节之间，必须有内容层面的过渡叙事。

### 章间过渡

每章结尾必须有"本章要点 + 引出下一章"的过渡段（≥2 句），位于"对主论点的贡献"段落之后。
- 第一句：凝练本章的核心发现（复用结论段但重新措辞）
- 第二句：将本章结论与下一章连接（内容承接，非坐标指路）
- 在 Markdown 中以 `> **本章小结与过渡**：...` 引用块形式书写
- 最后一章例外：仅需本章小结，无需引出下一章

### 节间过渡

同章内每个 H3 节之间必须有 ≥1 句过渡叙事。
- 过渡句位于上一节末尾或下一节首段开头
- 内容承接：用上一节的认识自然引出下一节的问题
- 禁止纯坐标指路（"下一节将讨论..."不构成过渡）

### ✅ 章间过渡示例

> **本章小结与过渡**：综上，东南亚新能源汽车市场的增长已从政策驱动阶段进入供需双轮驱动阶段，但充电基础设施的覆盖缺口（当前仅覆盖主要干线）是下一阶段增长的核心瓶颈。这一瓶颈如何被各国充电网络规划应对、以及中国充电桩企业在这一进程中的角色，正是下一章要审视的问题。

### ✅ 节间过渡示例

> 上述审批流程的比较揭示了碎片化的制度性成因，但仅分析流程不足以回答"碎片化对企业意味着什么"——这需要从合规成本的角度加以量化。
```

**自查清单新增项**（`stage-7-writing.md` §7.2.3）：
```markdown
- [ ] **章间过渡检查**：检查本章结尾是否包含"本章小结与过渡"引用块（≥2 句）。仅适用于非最后一章
- [ ] **节间过渡检查**：检查同章内每个 H3 节之间是否有 ≥1 句内容承接过渡
```

**writer_contract.json 新增维度**：
```json
{"id": "D8", "name": "transition_narrative", "cn": "章节过渡叙事",
 "requirement": "每章结尾有≥2句过渡引用块（非坐标指路）。同章内H3节间有≥1句过渡。"}
```

**auditor_contract.json 新增维度**：
```json
{"group": "结构", "id": "chapter_transition",
 "method": "检查章尾是否有≥2句过渡引用块；检查H3节间过渡",
 "severity": "mid",
 "what_triggers_block_hint": "非最后章缺少章间过渡段，或同章内相邻H3节间无过渡句"}
```

**finalizer_agent 新增步骤**（`stage-9-finalize.md` §9.1）：
```markdown
- [ ] **章间过渡段完整性确认**：检查各章间是否存在过渡引用块。
       如 writer 遗漏，finalizer 在合并时基于前后章标题和大纲条目补写过渡内容
```

**影响分析**：
- ✅ 现有标准 0-17 编号不变
- ✅ Writer 不遵循此标准时 auditor 会检测到（新增检查项）但不阻断核心流程（severity=mid）
- ✅ 增量采纳：先写标准→后续报告逐步遵循

---

### A2. 新增标准 19：读者层次校准（知识诅咒防御）

**直接修改**：`references/writing-standards.md`（新增标准）  
**间接更新**：`agents/chapter_writer_agent.md`（受众参数注入）+ `references/stage-1-init.md`（受众参数收集）

**标准 19 内容**：

```markdown
## 标准 19：读者层次校准（"知识的诅咒"防御）

**原则**：写作时默认读者不了解你已掌握的全部背景。写作者需假想一个"非专家的专业读者"。

### 规则

1. **缩写首次出现必须展开**：给出全称和中文释义（如"TLE（Two-Line Element，双行轨道根数）"），即使缩写通用也须展开
2. **关键概念首次出现给 1 句解释**：嵌入叙事语句而非括号注
3. **默认读者画像**：对该领域有基本素养但不掌握项目特定细节的专业人士

### ❌ 未做校准
> 系统基于 TLE 数据进行 SGP4 传播，在 GCRF 坐标系下计算残差。

### ✅ 已校准
> 系统的轨道计算链路从公开的 TLE（Two-Line Element，双行轨道根数——美国太空军定期发布的空间目标轨道参数）入手，通过 SGP4（Simplified General Perturbations 4，简化通用摄动模型）将 TLE 数据传播为任意时刻的位置速度，并在 GCRF（地心天球参考架）坐标系下比较预测值与实测值之间的残差。
```

**writer prompt 富化**（`chapter_writer_agent.md` 输入表新增）：
```markdown
| **受众画像** | 阶段1 `audience` 参数 | 读者层次校准参照：缩写展开程度、概念解释详细度 |
```

**影响分析**：
- ✅ Writer 如果不注入受众参数 → 使用默认值（"非专家的专业读者"），不阻断
- ✅ 不需要 LLM 主动判断"什么是缩写"——规则明确（"首次出现的英文大写字母组合"）

---

### A3. 新增标准 20：段落长度与信息密度

**直接修改**：`references/writing-standards.md`（新增标准）  
**间接更新**：`scripts/contract_check.py`（Phase B 新增 QS4）

**标准 20 内容**：

```markdown
## 标准 20：段落长度与信息密度

**原则**：段落是读者消耗信息的自然单元。过长降低可读性，过短缺乏论证深度。

### 段落长度
- 理想区间：150-400 字（中文）
- 警告区间：400-600 字 → 考虑拆分
- 超标区间：>600 字 → 必须拆分

### 信息密度
- 最低密度：每 300 字至少 1 个具体数据/事实/来源引用 [N]
- 连续 500 字纯论述无数据点 → 需补充事实支撑或拆分
- "数据点"定义：数字、带有出处的声称、引用文献编号
```

**影响分析**：
- ✅ 这是建议性标准而非阻断性合约——auditor 设为 WARN 而非 block
- ⚠️ contract_check.py 新增 QS4 段落统计功能，需确保不影响现有 QS1-QS3 输出格式

---

### A4. 扩展标准 12：执行摘要专条要求

**直接修改**：`references/writing-standards.md`（扩展标准 12）

**扩展内容**（追加到标准 12 末尾）：

```markdown
### 执行摘要的额外要求

1. **长度限制**：不超过报告总页数的 5%
2. **全章覆盖**：每个核心发现对应正文至少一章，无"悬空发现"
3. **每结论 1-2 句**：不展开论证，只给判断 + 最关键数字
4. **建议摘要**：若含建议章，摘要中给最简版（2-3 条，每条 1 句）
5. **无新信息**：摘要中任何数字/事实必须已在正文出现
```

---

### A5. SKILL.md 元描述同步

将 "含 12 条标准" 更新为 "含 18+ 条标准（标准 0-17 + 章间过渡/读者校准/段落密度/执行摘要）"。

**依赖**：必须在 A1-A4 全部完成后执行。

---

## 三、Phase B：审计增强层（验证层）

### B1. contract_check.py 新增 QS4 段落统计

**新增函数** `compute_paragraph_stats(text)`：

```python
def compute_paragraph_stats(text: str) -> dict:
    """QS4: 段落长度分布统计。
    
    排除标题行(#)、引用块(>)、表格行(|)、图片行(![)。
    返回: count, mean, p25, p50, p75, p90, over_600, under_150, ideal_range, longest
    """
```

**输出示例**（`--json`）：
```json
"QS4_paragraphs": {
    "count": 87, "mean": 245.3, "p25": 142, "p50": 228, "p75": 348,
    "p90": 512, "over_600": 3, "under_150": 12, "ideal_range": 58, "longest": 847
}
```

**auditor_contract.json 新增**：
```json
{"group": "量化", "id": "QS4_paragraphs",
 "method": "contract_check.py：段落长度分布 + 超长段落(>600字)计数",
 "severity": "low"}
```

**影响分析**：
- ✅ QS4 字段仅追加到 JSON 输出中，现有 QS1-QS3 字段不变
- ✅ auditor 如果不消费 QS4 → 旧行为不变
- ✅ 文本报告格式同步更新（新增 QS4 节）

---

### B2. 审计合约新维度

在 `auditor_contract.json` 的 `dimensions` 数组中新增：

```json
{"group": "结构", "id": "chapter_transition",
 "method": "检查章尾过渡引用块(≥2句) + H3节间过渡(≥1句)",
 "severity": "mid",
 "what_triggers_block_hint": "非最后章缺少章间过渡段，或同章内相邻H3节间无过渡句"},
{"group": "表述", "id": "reader_calibration",
 "method": "抽查5个专有名词/缩写，确认首次出现时给出全称+1句解释",
 "severity": "low",
 "what_triggers_block_hint": "存在未展开的缩写（首次出现无全称+中文释义）"}
```

**影响分析**：
- ✅ 新维度增量添加——auditor 不识别时不报错
- ✅ severity=mid/low——不阻断核心流程，仅告警

---

### B3. Writer Prompt 富化

在 `chapter_writer_agent.md` 中输入表新增受众参数行，并在"职责边界"节后新增上下文预算提醒：

```markdown
## 上下文预算提醒（长章场景）

如果当前章的卡片数量 > 10 张或大纲预估字数 > 12,000 字：
1. **优先使用卡片的摘要字段**（`一句话论点`/`机制小结`/`采用定义`）
2. **分段写入**：按大纲的"节"为单元逐步写入
3. 若素材过多导致上下文紧张，在自声明中标记 `[上下文字段裁剪]`
```

---

## 四、Phase C：转换器增强层（技术层）

### C1. REF 域交叉引用实现（核心 P0 项）

**问题**：`render/paragraphs.py` 未接入 REF 域，正文中"如图 3-2 所示"是静态文本。

**现有基础设施**（已就绪，无需新建）：
- `oxml_helpers.make_field()` —— SEQ/TOC/PAGE/PAGEREF 域均通过此函数生成
- `validate.py` 中 `xref_registry` —— 已收集所有交叉引用提及（含 ref_id, ref_type, mention_line）
- `FigureIR.bookmark_name` 和 `TableIR.bookmark_name` —— 图表已有书签名（如 `fig_3_2`, `Tab3_2`）

**实现步骤**：

#### 步骤 1：扩展 XRefMention（`ir.py`）

```python
@dataclass
class XRefMention:
    ref_id: str         # "图1-1" / "表4-1"
    ref_type: str       # "figure" | "table"
    mention_line: int
    style: str          # "paren" / "asshown" / "positional"
    bookmark_name: str | None = None  # NEW: 对应图表书签名
```

#### 步骤 2：填充 bookmark_name（`validate.py`）

在 `_check_xref_consistency()` 中，注册 XRefMention 时查找匹配的 figure/table 实体存储其书签名：

```python
bookmark = None
if ref_type == "figure" and figure_id in document_ir.figure_registry:
    bookmark = document_ir.figure_registry[figure_id].bookmark_name
elif ref_type == "table" and figure_id in document_ir.table_registry:
    bookmark = document_ir.table_registry[figure_id].bookmark_name
```

#### 步骤 3：段落渲染中替换 REF 域（`render/paragraphs.py`）

新增 `render_paragraph_with_refs()` 函数——扫描段落文本中的 `图X-Y`/`表X-Y` 模式，在匹配位置将静态文本替换为 REF 域：

```python
_RE_XREF_PATTERN = re.compile(r'(图|表)(\d{1,2})-(\d{1,2})')

def render_paragraph_with_refs(doc, token, styles, ref_map=None):
    """渲染正文段落，支持 REF 域自动替换。ref_map=None 时回退原行为。"""
```

核心逻辑：遍历每个 InlineRun 的文本 → 对每个正则匹配 → 如果 ref_map 中有对应书签 → 插入 REF 域（`make_field(p, f"REF {bookmark} \\h", placeholder_text=ref_text)`） → 否则回退为静态文本。

#### 步骤 4：从 document.py 传递 ref_map

在 `render_document()` 中构建 `ref_map = {xref.ref_id: xref.bookmark_name for xref in ir.xref_registry if xref.bookmark_name}`，通过 dispatcher 传到段落渲染。

#### 步骤 5：确认表也有书签

核实 `render/tables.py` 中表格题注也创建了书签（当前已有 `make_bookmark_start/end` 调用，格式为 `TabX_Y`）。

**影响分析**：
- ⚠️ **MEDIUM 风险**：触核段落渲染路径。缓解措施：
  - `ref_map=None` 参数保证 100% 向后兼容——不提供时行为完全不变
  - 正则 `_RE_XREF_PATTERN` 与 `validate.py` 中的一致，避免匹配差异
  - 跨 run 边界匹配（如**加粗的"图"** + 普通"3-2"）暂不处理——记录为已知限制
- ✅ 自检：`paragraphs.py` 新增测试断言 REF 域正确生成
- ✅ 集成：全管道测试验证 .docx 输出中 REF 域可被 Word 正确更新

---

### C2. YAML 错误处理加固

**问题**：`outline_reader.py` 中 `try: parsed = yaml.safe_load(yaml_text) except yaml.YAMLError: return None, body` 静默吞掉错误。

**修复**：在异常分支中输出诊断信息（stderr），并尽可能定位问题行：

```python
except yaml.YAMLError as e:
    import sys
    print(f"[FATAL] outline.md YAML 解析失败: {e}", file=sys.stderr)
    if hasattr(e, 'problem_mark') and e.problem_mark is not None:
        line_no = e.problem_mark.line + 2  # +2 for --- offset
        print(f"  问题大约在第 {line_no} 行: {e.problem}", file=sys.stderr)
    return None, body
```

**影响分析**：
- ✅ 返回语义不变（仍是 `(None, body)`），调用方的回退路径不变
- ✅ 仅增加 stderr 诊断输出——对管道行为零影响

---

### C3. card_overlap_check.py 文档澄清

**审计发现**：命名可能被误解为"卡片间重叠检测"。

**核实结果**：脚本实际检测的是**卡片-正文重合度**（脚本 docstring："对本章正文与本章引用的每张卡片做滑动窗口 n-gram 重合检测"）。

**修复**：在 docstring 首行明确声明检测目标：
```python
"""卡片-正文重合度检测脚本。

注意：本脚本检测的是**卡片内容与正文之间的重合**（card-to-body overlap），
非卡片间重叠。用途是量化"卡片是否被消化转写而非誊抄"。
"""
```

**影响分析**：NONE——纯文档改动。

---

## 五、Phase D：编排增强层（流程层，纯文档）

### D1. P0 死锁处理决策树

在 `references/multiagent-orchestration.md` 新增 §10，明确写审对抗 2 轮上限后的 3 条路径：

| 路径 | 触发条件 | 操作 | 适用场景 |
|------|---------|------|---------|
| **A：手动改稿→重审** | 用户愿手动修改 | 编辑草稿→重新审计 1 轮 | 临界通过、少数 issue 难修 |
| **B：降级为 WARN** | block 维度非 C1/C2/C5 红线 | 记录降级决定 + 红队风险清单加 WARN 项 | 段落过渡缺失、篇幅超标 |
| **C：跳过该章** | 本章对主线非关键 | 在正文插入风险提示 + 目录标注"未完成审计" | 强成本/时间约束 |

**红线**：C1/C2/C5 合约层高严重度失败不走路径 B（必须手动修或跳过，不可降级为 WARN）。

---

### D2. Agent 上下文窗口风险文档化

在 `multiagent-orchestration.md` §9（已知限制）新增条目：

- Writer Agent（Sonnet, 200K context）：长章 15K+ 字 + 10+ 张卡片 ≈ 80-100K tokens
- Auditor Agent（Opus, 200K context）：全章正文 15K+ 字占 40-60K tokens
- 缓解：Writer prompt 含上下文预算提醒 + 优用卡片摘要字段 + >25K 字建议拆分为子章

---

## 六、依赖关系与执行顺序

```
Phase A (文档) ────────────────────┐
  A1 (标准18: 过渡) ───────────────┤
  A3 (标准20: 段落密度) ───────────┤
  A2 (标准19: 读者校准) ───────────┤
  A4 (标准12扩展: 执行摘要) ───────┤
  A5 (SKILL.md同步) ───────┘────── 依赖 A1-A4 完成
                                    │
Phase B (审计) ─────────────────────┤
  B1 (QS4 contract_check.py) ─────── 依赖 A3
  B2 (审计合约新维度) ────────────── 依赖 A1, A2, B1
  B3 (Writer prompt富化) ────────── 依赖 A2, D2
                                    │
Phase C (转换器) ───────────────────┤
  C1 (REF域) ────────────────────── 独立（无依赖其他Phase）
  C2 (YAML错误处理) ─────────────── 独立
  C3 (card_overlap澄清) ─────────── 独立
                                    │
Phase D (编排) ─────────────────────┤
  D1 (P0决策树) ─────────────────── 独立
  D2 (上下文窗口文档) ───────────── 独立
```

**推荐执行顺序**：
- **第 1 批（独立并行）**：A1 + A3 + C2 + C3 + D1 + D2 —— 6 项无互相依赖
- **第 2 批**：C1（REF 域）—— 技术复杂度最高，专注实施
- **第 3 批**：A2 + A4 + A5 —— 剩余 Phase A
- **第 4 批**：B1 + B2 + B3 —— Phase B 依赖 Phase A 完成

---

## 七、回归风险评估

| 改动 | 风险 | 理由 |
|------|------|------|
| A1-A5（新增标准） | **LOW** | 纯增量。Agent 不消费未知标准 → 旧行为不变 |
| B1（QS4） | **LOW** | 追加 JSON 字段，现有字段不变 |
| B2（审计合约） | **LOW** | 新维度增量添加 |
| B3（Writer prompt） | **LOW** | 追加指令，不删除现有要求 |
| C1（REF 域） | **MEDIUM** | 触核段落渲染路径。缓解：ref_map=None 回退 + 正则一致 + 自检覆盖 |
| C2（YAML） | **LOW** | 仅改诊断输出，返回语义不变 |
| C3（card_overlap） | **NONE** | 纯文档 |
| D1-D2 | **NONE** | 纯文档 |

---

## 八、文件改动总览

| # | 文件 | 改动类型 | 行数 | Phase |
|---|------|---------|------|-------|
| 1 | `references/writing-standards.md` | 新增标准 18-20 + 扩展标准 12 | +120 | A |
| 2 | `references/stage-7-writing.md` | 新增自查项 + 质量标准引用 | +20 | A |
| 3 | `agents/contracts/writer_contract.json` | 新增 D8 维度 | +5 | A |
| 4 | `agents/contracts/auditor_contract.json` | 新增过渡/读者校准/QS4 维度 | +15 | A+B |
| 5 | `agents/chapter_writer_agent.md` | 受众参数 + 上下文预算提醒 | +20 | A+B |
| 6 | `agents/chapter_auditor_agent.md` | 新增审计维度 + QS4 引用 | +10 | B |
| 7 | `references/stage-9-finalize.md` | 章间过渡完整性确认 | +5 | A |
| 8 | `SKILL.md` | 标准数量同步 | +2 | A |
| 9 | `scripts/contract_check.py` | 新增 QS4 段落统计 | +80 | B |
| 10 | `scripts/md2docx/render/paragraphs.py` | REF 域渲染 | +120 | C |
| 11 | `scripts/md2docx/render/document.py` | 传递 ref_map | +10 | C |
| 12 | `scripts/md2docx/ir.py` | XRefMention 扩展 bookmark_name | +3 | C |
| 13 | `scripts/md2docx/validate.py` | 填充 bookmark_name | +8 | C |
| 14 | `scripts/md2docx/assemble/outline_reader.py` | YAML 错误诊断 | +8 | C |
| 15 | `scripts/card_overlap_check.py` | Docstring 澄清 | +5 | C |
| 16 | `references/multiagent-orchestration.md` | P0 决策树 + 上下文窗口文档 | +80 | D |

**总计**：16 文件，约 +511 行（0 行删除），0 个现有测试预期变更。

---

## 九、验收标准

### Phase A
- [ ] `writing-standards.md` 新增标准 18-20，扩展标准 12，编号不冲突
- [ ] `stage-7-writing.md` 自查清单从 13 项扩至 16 项（新增过渡×2 + 读者校准）
- [ ] writer/auditor 合约 JSON 合法（可被 `json.load()` 解析）
- [ ] `SKILL.md` 标准数量描述与实际一致

### Phase B
- [ ] `contract_check.py --json` 输出含 `QS4_paragraphs` 字段
- [ ] QS4 正确排除标题/引用块/表格/图片行
- [ ] `contract_check.py` 自检通过（若有自检块）
- [ ] auditor contract JSON 含新维度且维度数 ≥22

### Phase C
- [ ] `paragraphs.py` 自检通过（新增 REF 域断言）
- [ ] 集成测试：全管道运行 → .docx 中 REF 域可被 Word F9 正确更新
- [ ] 不传 ref_map 时行为完全不变（regression）
- [ ] `outline_reader.py` 在 YAML 格式错误时产生诊断输出但不崩溃
- [ ] `card_overlap_check.py` docstring 准确描述检测目标

### Phase D
- [ ] `multiagent-orchestration.md` 新增 §10 含三路径决策树
- [ ] `multiagent-orchestration.md` §9 含 Agent 上下文窗口风险条目
- [ ] 红线规则明确：C1/C2/C5 失败不走降级路径

---

## 十、不做的事项（明确排除）

以下来自审计报告的建议经评估后**不在本次方案范围内**：

| 排除项 | 理由 |
|--------|------|
| 数学公式 LaTeX→OMML 转换 | 深度研究报告极少包含数学公式；转换复杂度高但场景覆盖率极低 |
| 英文报告输出支持 | 涉及全部 Agent prompt + 标准 + 合约的英文化，工作量远超本次范围 |
| PDF 直接输出 | 已有 docx→PDF 的外部转换路径，不重复造轮子 |
| 增量更新（单章重写） | 架构改动大（需中间产物持久化 + 差异检测），列入 P2 远期 |
| 术语表/索引自动生成 | 需要 NLP pipeline（术语提取 + 出现位置索引），复杂度高，低优先级 |
| 实时进度追踪（替代 dashboard.md） | 需要 Web UI 或 CLI 交互框架，不属于核心 skill 范围 |
