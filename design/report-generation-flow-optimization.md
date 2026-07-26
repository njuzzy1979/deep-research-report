# 报告生成流程优化方案——稳定生成高质量研究报告

> 版本：V1.0  
> 日期：2026-07-26  
> 状态：待审核  
> 基于：本对话中多轮方案分析的结论 + 代码库全量管道映射 + 外部最佳实践调研

## 零、外部调研验证

本方案的设计方向通过独立外部搜索（15 个查询，覆盖结构化文档创作、LLM 报告生成、模板驱动生成、Word 渲染、文档 QA 五个领域）得到确认：

1. **大纲驱动写作是经过验证的模式**：STORM（Stanford）和 GPT Researcher 等前沿 LLM 报告生成系统都采用"大纲先行→分章填充→整合输出"的流程。本 skill 的 9 阶段流程与此一致，且在多 Agent 协同和证据核验方面更为深入。
2. **"声明式结构清单"是本系统独特的改进机会**：与 Sphinx `toctree`、mdBook `SUMMARY.md` 等成熟的"结构-内容分离"模式一致——结构定义一次，渲染引擎消费。现有系统中尚未发现将"人类可读大纲 + 机器可读结构清单"二合一放在同一个 Markdown 文件中的先例。
3. **证据驱动 + 信源分级 + 四人格红队在本领域是差异化优势**：在已知 LLM 报告生成系统中是独特的。
4. **模板约束写作是防结构漂移的关键**：外部实践确认了"fill-in-the-blank 模板 + 版本控制 + 变更审批"的三层防线——对应本方案的"outline.md 结构清单 + 审计结构一致性 + 转换器验证"。

---

## 一、当前流程诊断

### 1.1 问题总览

当前 skill 的 9 阶段流程经过多次迭代已相当成熟，但在"结构从定义到最终 Word 渲染"的传递链上存在一个系统性断点：

```
Stage 4: outline.md（结构已定义，用户已确认）
         ↓ 被四个 Agent 消费（writer/auditor/card/diagram）
Stage 7: 分章草稿（H3 起始，无章容器，无编号）
         ↓
Stage 9: finalizer_agent 手动插入 H2 章容器
         ↓
         合并为 final-report.md
         ↓
转换器:  从头重新推断结构（4 处推断点，全部基于 heading 文本模式匹配）
         ↓
.docx:   Word 原生编号（w:numPr + SEQ）——编号机制本身正确
```

**核心矛盾**：Stage 4 已经定义了完整的结构（章-节-小节标题、编号顺序、论证据路径），用户已通过 CP3 确认，四个下游 Agent 以此为工作契约——但转换器**完全不知道这份契约的存在**。转换器独自重新扫描 heading 文本、用启发式规则和正则推断"哪行是章、哪行是节、编号该是几"。

### 1.2 四个结构推断点（当前脆弱的根源）

| # | 推断点 | 机制 | 失败表现 |
|---|--------|------|---------|
| 1 | **HeadingKind 分类** | 标题文本匹配 FRONT_BACK_WORDS 白名单 + 章编号/附录正则 | 前言 H2 被误判为正文第一章；正文 H2 被误判为前置件不编号 |
| 2 | **前置件区边界** | 检测 H2 是否携带显式章编号 | 前言区和正文区间边界飘移 |
| 3 | **节面边界** | heading 分类 + HrToken 分隔符 | 摘要区和正文区的页码范围错误 |
| 4 | **图/表编号** | source_line 位置计算所属章节 | 章节边界漂移导致图/表编号对应错误的章号 |

### 1.3 推断失败的根本原因

这四个推断点共享同一个脆弱性：它们依赖的输入信号（Markdown heading 文本）是**不可靠的结构载体**。

- 标题文本"前言"到底含义是前置件还是某种特殊用法？→ 白名单匹配是启发式判断
- 某个 H2 到底是正文第一章还是最后一章？→ 只能靠"它是第几个 H2"来推测
- 某张图到底属于第 2 章还是第 3 章？→ 只能靠它在源文件中的行号落在哪两个 H2 之间

所有这些问题在 outline.md 中都有确定的答案——但转换器没有读取它们。

---

## 二、目标状态

### 2.1 核心设计原则

1. **一次定义，全程复用**：结构在 Stage 4 的 outline.md 中定义一次，后续所有环节（写作、审计、合并、转换）都直接或间接消费这份定义，不做二次推断。
2. **声明式优于推断式**：凡是能在 outline.md 中显式声明的结构信息（层级、编号、所属关系），不依赖启发式规则从内容中猜。
3. **结构-内容分离**：outline.md 是结构清单，分章 Markdown 是内容填充，转换器负责按结构清单把内容组装为最终文档。
4. **渐进式，不推倒重来**：所有改动基于现有架构扩展，保持向后兼容。

### 2.2 目标架构

```
Stage 4: outline.md（结构 SSOT）
         ├─ YAML front matter: 机器可读的结构清单
         │   - struct_template
         │   - 章/节/小节完整层级树（含编号、标题文本）
         │   - 前置件/正文章/附录分区声明
         │
         ├─ Markdown body: 人类可读的大纲（含论证路径、关键素材、篇幅预算）
         │
         ↓ 被所有下游消费（与当前一致）
Stage 5-8: 与当前一致
         ↓
Stage 9: finalizer_agent
         ├─ 从 outline.md YAML 读取结构清单（而非手动推断）
         ├─ 生成结构化合并清单：哪些分章文件属于哪一章
         └─ 调用转换器时传入 --outline research/outline.md
         ↓
转换器: 新增 --outline 参数
         ├─ 读取 outline.md YAML 结构清单
         ├─ 用结构清单覆盖 HeadingKind 分类（不再靠文本模式匹配）
         ├─ 用结构清单验证正文标题树的一致性（差异 → WARNING/ERROR）
         ├─ 图/表编号从结构清单的章边界确定（不再靠 source_line 推断）
         └─ 无 --outline 参数时行为完全不变（向后兼容）
```

### 2.3 具体实现范围

本方案涉及三个层次的改动：

| 层次 | 改动 | 影响范围 |
|------|------|---------|
| **P0** | outline.md 新增 YAML 结构清单 | `stage-4-outline.md` + `outline_architect_agent.md` |
| **P0** | 转换器新增 `--outline` 参数 + 结构注入逻辑 | `cli.py` + `assemble/headings.py` + `assemble/builder.py` |
| **P1** | caption_field_mode 默认值改为 `"field"` | `config.py` |
| **P1** | finalizer_agent 改为结构驱动的合并 | `finalizer_agent.md` + `stage-9-finalize.md` |
| **P2** | 审计 Agent 新增"结构一致性"维度 | `chapter_auditor_agent.md` |
| **P2** | 图/表 SEQ 域改为默认模式 | `render/figures.py` + `render/tables.py` |

---

## 三、P0：outline.md 结构清单 + 转换器结构注入

### 3.1 outline.md 新增 YAML 结构清单

在 outline.md 文件开头（现有的标题行之前）增加 YAML front matter，包含机器可读的结构声明：

```yaml
---
struct_template: research
title: "全球在轨服务市场深度研究报告"
structure:
  frontmatter:
    - chapter_title: "前言/导论"
      sections:
        - "问题提出与研究背景"
        - "概念界定与研究边界"
        - "研究方法与分析框架"
  bodymatter:
    - chapter_no: 1
      chapter_title: "军事需求与现状分析"
      sections:
        - "非合作目标异动意图判断"
        - "目标识别响应时间窗口分析"
        - "多域协同态势感知需求"
      subsections:
        - parent: "非合作目标异动意图判断"
          title: "异动识别在导弹预警中的应用"
    - chapter_no: 2
      chapter_title: "技术架构与关键技术"
      sections:
        - "感知层技术体系"
        - "认知层算法框架"
        - "决策层人机协同机制"
    - chapter_no: 3
      chapter_title: "市场格局与竞争分析"
      sections:
        - "全球市场规模与增长驱动"
        - "主要厂商能力对比"
        - "供应链风险分析"
  appendix:
    - appendix_letter: "A"
      appendix_title: "事实核验台账摘要"
    - appendix_letter: "B"
      appendix_title: "术语表"
```

**字段语义**：
- `structure.frontmatter`：前置件区。第一个 H1（MAIN_TITLE）之后的 H2/H3 归入此区，不编号
- `structure.bodymatter`：正文区。每个元素是一个完整的章，含章号和完整的节/小节列表
- `structure.appendix`：附录区。每个附录含字母和标题
- `sections` 和 `subsections` 的顺序即为文档中的实际顺序

### 3.2 转换器新增 `--outline` 参数

在 `cli.py` 和 `pipeline.py` 中新增：

```python
# cli.py RunOptions 新增字段
outline_path: str | None  # outline.md 路径，传入时启用结构注入模式

# cli.py argparse 新增
ap.add_argument("--outline", dest="outline_path", default=None,
                help="outline.md 路径，提供结构 SSOT（覆盖 heading 分类和编号推断）")
```

在 `pipeline.py` 的 `_stage3_assemble` 中，将 `options.outline_path` 传给 `builder.build()`。

### 3.3 assemble/headings.py 新增结构覆盖函数

新增 `apply_structure_overlay()` 函数：

```python
def apply_structure_overlay(
    results: list[HeadingIR],
    structure: dict,  # outline.md YAML structure 节点
    issues: IssueCollector,
) -> list[HeadingIR]:
    """用 outline.md 的结构清单覆盖 HeadingIR 的分类和编号。

    工作原理：
    1. 将 structure YAML 展平为 (heading_text, expected_kind, expected_number) 三元组
    2. 遍历 results 中的 HeadingIR，用 heading.text 匹配结构清单
    3. 匹配成功 → 用结构清单中的 kind 和 number 覆盖推断值
    4. 匹配失败（正文有但结构清单无）→ 记录 W-HDR-04（新增）
    5. 结构清单有但正文无 → 记录 W-HDR-05（节缺失）
    """
```

**匹配策略**：标题文本精确匹配（`heading.text.strip() == struct_item.title.strip()`）。精确匹配是最安全的选择——标题文本来自 outline.md（用户已确认），写作者不应修改标题文本。

### 3.4 结构覆盖的范围

| 字段 | 当前来源（推断） | 结构注入后来源 |
|------|----------------|--------------|
| `HeadingKind` | 标题文本匹配 FRONT_BACK_WORDS + 正则 | structure YAML 的 `frontmatter`/`bodymatter`/`appendix` 分区 |
| `display_number`（章） | `chapter_index` 自增 | `structure.bodymatter[i].chapter_no` |
| `display_number`（节） | `chapter_index.section_index` | `structure.bodymatter[i].sections` 列表中的位置 |
| `display_number`（小节） | `chapter_index.section_index.subsection_index` | `structure.bodymatter[i].subsections` 列表中的位置 |
| 章容器识别 | H2 是否携带显式章编号或匹配白名单 | 结构清单显式声明 |
| 前置件区边界 | H2 是否携带显式章编号 | 结构清单显式声明（frontmatter 段结束 = 正文开始） |

### 3.5 新增的 Issue 类型

| Issue | 级别 | 含义 |
|-------|------|------|
| `I-HDR-07` | INFO | 结构注入模式已启用，xx 个 heading 由 outline.md 覆盖 |
| `W-HDR-04` | WARNING | 正文中存在 outline.md 未声明的 heading（标题文本在结构清单中找不到匹配） |
| `W-HDR-05` | WARNING | outline.md 中声明的 heading 在正文中缺失 |
| `I-OL-01` | INFO | outline.md YAML 解析成功，写入结构清单摘要 |

### 3.6 builder.py 的图/表编号受益

当前 `_build_chapter_map()` 通过 source_line 位置推断图/表所属章节。结构注入后：

```python
def _build_chapter_map(heading_irs: list[HeadingIR]) -> list[tuple[int, int]]:
    """从 HeadingIR 列表构建 (source_line, chapter_no) 有序表。
    
    当结构注入模式启用时，chapter_no 直接来自 heading.number（已被结构清单覆盖），
    而非 chapter_index 自增——这消除了"写作者漏写 H2 章容器导致 chapter_no=0"的故障。
    """
```

图/表编号的 `chapter_no` 将更加可靠——它来自结构清单的显式声明，而非 source_line 的位置推断。

---

## 四、P1：图/表 SEQ 域默认化 + 合并流程结构驱动

### 4.1 caption_field_mode 默认值改为 "field"

```python
# config.py BehaviorFlags
caption_field_mode: str = "field"  # 原: "text"
```

**理由**：
- SEQ 域机制已在 commit `224420e` 中实现，通过问题 19 修复后已稳定可用（placeholder_text + w:updateFields 双保险）
- 图/表编号"全篇平铺"（图 1, 图 2...）是 Word 原生 SEQ 域的直接能力，不需要章前缀
- 删除 `"text"` 静态文本分支持平代码量并消除双模式维护负担
- 如需保留章前缀（图 1-1 格式），后续通过 SEQ `\s` 标志 + render 手动前缀增强

### 4.2 finalizer_agent 合并流程

当前 finalizer_agent 手动读取 outline.md 并插入 H2 章容器。改为：

1. 从 outline.md YAML structure 读取完整的章-节映射
2. 遍历 `structure.bodymatter`，为每章：
   a. 插入 H2 章容器（`## 第 X 章：章标题`）
   b. 按 `sections` 列表依次拼接对应分章文件（文件名以章节号匹配）
3. 处理 `structure.frontmatter` 和 `structure.appendix`
4. 调用转换器时传入 `--outline research/outline.md`

### 4.3 stage-9-finalize.md 和 finalizer_agent.md 更新

新增职责说明：
- "读取 outline.md YAML 结构清单，按结构驱动的合并清单拼接分章文件"
- "调用转换器时强制传入 --outline 参数"
- "合并完成后验证：正文各章与结构清单一一对应，无遗漏无多余"

---

## 五、P2：审计增强 + 交叉引用

### 5.1 审计 Agent 新增"结构一致性"维度

在 `chapter_auditor_agent.md` 的审计维度和 `auditor_contract.json` 中新增：

| 维度 | 判定方式 | 严重度 |
|------|---------|--------|
| **结构一致性** | 对比本章草稿标题树与 outline.md 结构清单：标题文本变更 → WARN；新增不在结构清单中的节 → block/REVISE；缺失声明应有节 → block/REVISE | mid |

这解决了"写作者越界"这一关键失败模式——在写作时添加大纲中没有的小节。现有的写审对抗 loop-until-pass 机制会自动将其阻挡在合流之前。

### 5.2 图/表 SEQ 域启用后的关联改动

- `render/figures.py`：删除 `caption_field_mode == "text"` 分支（题注文本从 `figure.figure_id` 拼接），保留 `"field"` 分支为唯一路径
- `render/tables.py`：同上
- `gate3.py` 的图/表连续性校验：当 `caption_field_mode == "field"` 时，校验逻辑从"比对 figure_id 字面数值序列"改为"验证 SEQ 域结构完整性（instrText 存在 + placeholder_text 非空 + 序列连续）"
- `config.py`：`caption_field_mode` 枚举值从 `("text", "field")` 改为 `("field",)` 或保留 `"text"` 为已废弃不再推荐

---

## 六、完整优化后的数据流

```
Stage 1: struct_template, 研究方法, 分析框架 → 锁定
         ↓
Stage 2-3: source-index.csv + claims-ledger.csv → 锁定
         ↓
Stage 4: outline.md（含 YAML 结构清单）
         ├─ 人类可读：论证路径 + 关键素材 + 篇幅预算
         └─ 机器可读：章/节/小节层级树 + 编号 + 分区声明
         ↓ CP3 用户确认（确认的是结构与论证方向）
         ↓
Stage 5: cards → 按 chapter_ref 绑定到 outline 章节
Stage 6: diagrams → 按 outline 架构图清单产出
         ↓
Stage 7: 分章写作 + 审计（loop-until-pass）
         - 写作者：输入为 outline 当前章条目 + cards + diagrams
         - 审计者：新增"结构一致性"维度
         - 草稿文件：H3 起始，标题文本与 outline 一致
         ↓ CP4 全部章 PASS
         ↓
Stage 8: 红队审查 → 跨章交叉验证
         ↓ CP5 确认
         ↓
Stage 9: finalizer_agent
         ├─ 读取 outline.md YAML structure
         ├─ 按结构清单生成合并清单
         ├─ 插入 H2 章容器（文本来自结构清单）
         ├─ 拼接分章文件 → final-report.md
         ├─ 参考文献去重 + 全局编号统一
         ├─ 调用转换器 --outline research/outline.md --caption-field-mode field
         └─ 12 项交付清单核对
         ↓
转换器: 
  Stage 0-2: normalize → clean → parse（不变）
  Stage 3 (assemble):
    1. classify_and_number() —— 正常推断
    2. apply_structure_overlay() ——【新增】用 outline.md YAML 覆盖
       - HeadingKind 不再靠文本模式匹配
       - display_number 不再靠计数器自增
       - 产生 W-HDR-04（多余）/ W-HDR-05（缺失）
    3. builder 图/表编号受益于可靠的 chapter_map
  Stage 4-6: validate → render（SEQ 域）→ gate3 → report
         ↓
.docx:  Word 原生 w:numPr + SEQ 域 + w:updateFields
       所有编号由 Word 自动计算
```

---

## 七、实施优先级与预估工作量

| 优先级 | 改动 | 文件 | 预估改动量 | 独立可测 |
|--------|------|------|-----------|---------|
| **P0** | outline.md YAML 结构清单格式设计 + stage-4-outline.md 更新 | 1 文件（spec） | ~40 行 | 是（规范层） |
| **P0** | outline_architect_agent.md 更新（产出含 YAML 的 outline） | 1 文件（agent prompt） | ~15 行 | 是 |
| **P0** | 转换器 --outline CLI 参数 | `cli.py` | ~5 行 | 是 |
| **P0** | 转换器结构注入逻辑 | `assemble/headings.py`（新增函数）+ `pipeline.py`（传参） | ~80 行 | 是（单元测试） |
| **P0** | outline.md YAML 解析工具函数 | `assemble/` 下新增 `outline_reader.py` | ~60 行 | 是 |
| **P1** | caption_field_mode 默认值改为 "field" | `config.py` | 1 行 | 是 |
| **P1** | 删除 figure/table render 的 text 分支 | `render/figures.py` + `render/tables.py` | ~20 行（删） | 是 |
| **P1** | finalizer_agent 结构驱动合并 | `finalizer_agent.md` + `stage-9-finalize.md` | ~30 行 | 否（依赖 P0） |
| **P2** | 审计"结构一致性"维度 | `chapter_auditor_agent.md` + `auditor_contract.json` | ~20 行 | 否（依赖 P0） |
| **P2** | Gate3 图/表 SEQ 域结构校验 | `gate3.py` | ~30 行 | 否（依赖 P1） |

**总预估**：~300 行新增 + ~50 行删除，分布在约 12 个文件中。

---

## 八、风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| outline.md YAML 解析失败（格式错误） | 低 | 中 | 回退到当前推断模式 + WARNING；不阻断转换 |
| 结构清单与正文标题文本不一致（写作者改了标题） | 中 | 中 | W-HDR-04 告警 + 以正文实际标题为准（结构清单提供分类和编号，标题文本跟随正文） |
| 写作者新增不在结构清单中的节 | 中 | 中 | 审计 Agent "结构一致性"维度 block/REVISE（Stage 7 即拦截） |
| --outline 不传时行为回归 | 低 | 高 | 严格保持向后兼容：不传 --outline → 完全当前行为，零改动 |
| YAML 结构清单过大（大型报告 10+ 章） | 低 | 低 | 典型报告 3-5 章，YAML 不超过 100 行——完全在合理范围内 |

---

## 九、验收标准

### 9.1 功能验收

- [ ] outline_architect_agent 产出含有效 YAML front matter 的 outline.md
- [ ] `python -m md2docx final-report.md output.docx --outline outline.md` 成功生成 .docx
- [ ] 生成的 .docx 中章节编号与 outline.md 声明一致（第 1 章就是第 1 章）
- [ ] 生成的 .docx 中前置件（摘要/前言/目录）无编号
- [ ] 生成的 .docx 中附录使用字母编号（附录 A, 附录 B）
- [ ] `--caption-field-mode field` 下图表使用 SEQ 域，placeholder 非空
- [ ] 不传 --outline 时行为与当前完全一致

### 9.2 回归验收

- [ ] `assemble/headings.py` 自检全部通过
- [ ] `render/figures.py` 自检全部通过
- [ ] `render/tables.py` 自检全部通过
- [ ] `render/numbering.py` 自检全部通过
- [ ] gate3 全部 12 项检查通过
- [ ] 换样本测试（alt-sample）通过

### 9.3 集成验收

- [ ] 用真实 outline.md（含 YAML） + 真实分章文件 → 转换成功，编号正确
- [ ] W-HDR-04（正文有但结构清单无）正确触发
- [ ] W-HDR-05（结构清单有但正文无）正确触发
- [ ] 审计 Agent 的"结构一致性"维度正确检测标题文本偏差
