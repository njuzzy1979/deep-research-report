# deep-research-report

面向支持 Agent Skills 标准的运行时（Claude Code、Codex、Cursor 等）的**深度研究报告编写全流程方法论**。将"写一份研究报告"拆解为 9 个顺序阶段，用证据驱动 + 架构分析的方式，产出有事实核验台账、有架构图、经过写审对抗 + 红队审查的正式研究报告（Markdown + 标准格式 Word .docx）。

**v5.1 起支持跨模型运行**：除 Claude 外，已适配 DeepSeek V4/V3、GLM-4、Qwen3 等模型——通过 `model-profile.json` 声明能力档，自动调整 prompt 构造与输出切分策略。Claude 用户默认零配置，非 Claude 用户执行 `python scripts/model_profile.py --model auto` 一行命令自动适配。

## 这个 skill 解决什么问题

直接让 LLM"写一份关于 XX 的报告"，容易出现：

- 论点没有证据支撑，或引用来源真假不分
- 证据分级/来源取舍/核验过程被当成正文叙事（"后台过程外泄"）
- 卡片字段被逐字誊抄进正文，而非消化转写为判断
- 图表和正文数据对不上、临时拼凑
- 长报告写到后面结构塌方，前后论证不咬合
- 排版随意，不符合正式交付的格式要求

本 skill 用**阶段化质量门槛**约束这个过程：前一阶段的产物不达标，不允许进入下一阶段。核心理念是"先打地基，再盖房子"——资料没抽完不写大纲，事实没核验不写正文，架构图没画不分章写作。

## 方法论特色

| 层级 | 机制 | 解决的问题 |
|------|------|-----------|
| **前台/后台分离** | 标准 0（总纲）：正文只呈现成品判断，证据分级/来源取舍/核验过程下沉脚注或台账 | 编辑部过程外泄进正文——"该来源为 A 级，证据强度较高"这类自证严谨的元评论成为正文叙事对象 |
| **卡片→正文消化转写** | 四铁律 + 卡片重合度检测（`card_overlap_check.py`）+ 论点骨架先行 | 卡片字段被逐字誊抄——写作者把精炼的卡片判断句原样搬进正文，而非消化后重新表达 |
| **写审对抗** | 阶段 7 `chapter_writer_agent`（生成）+ `chapter_auditor_agent`（独立审计）物理分离，盲态预承诺 | V3 R3 死结——写作者自评不可信（看了稿再把标准调松到刚好通过） |
| **红队并行** | 阶段 8 四人格（2×Opus+2×Sonnet）并行审查，独立综合去重 | 单视角审查遗漏；同质化风险 |
| **SSOT 治理** | Agent prompt 强制 Read 外部规范文件，`linkage-constants.json` + `check_linkage_constants.py` 跨文件常量联动校验 | 规范文档腐烂——Agent 内嵌摘要与源文件脱节；关键数值（阈值/限额）在多文件间漂移 |
| **Word 原生动态编号** | `w:numPr` 多级列表 + SEQ 域 + `w:updateFields` 双保险 | 硬编码编号在文档编辑后失序——章节增删后需全篇人工重新核对编号 |
| **跨模型兼容** | `model-profile.json` 能力档声明（tier A/B/C）+ 模型名自动检测 → 自动调整 prompt 策略；非 Claude 宿主退化为单 Agent 极速 + 全套确定性脚本，质量打折但不清零 | 离开 Claude 后 skill 行为未定义——弱模型上 prompt 溢出/红线被忽略/输出格式失控 |

## 9 阶段流程

```
阶段1 项目初始化
  → 阶段2 资料搜集、抽取与来源索引
  → 阶段3 事实核验
  → 阶段4 详细大纲
  → 阶段5 专题研究（卡片 + 证据包）
  → 阶段6 核心架构图（先于写作）
  → 阶段7 分章写作 + 数据图表（随写作产出）+ 写审对抗
  → 阶段8 红队审查（4 人格并行）
  → 阶段9 定稿整合
```

| 阶段 | 产出 | 质量门槛 | 关键特性 |
| ---- | ---- | ---- | ---- |
| 1 项目初始化 | 工作目录、分析框架、题名参数 | 用户确认关键参数 | 智能推断 7 参数；5 种报告类型自动识别；三档协同模式选定 |
| 2 资料搜集与抽取 | 来源索引表 + MinerU 解析结果 | 每条来源分级 A/B/C/D 并登记 | 三工具协作：web-search + paper-search + MinerU；P0 政府/法规 → P1 学术 → P2 媒体 |
| 3 事实核验 | 事实核验台账 | 高风险主张全部核验，强表述降级 | 5 类优先核验主张，6 级核验状态；整个方法论的"地基" |
| 4 详细大纲 | 三级标题 + 篇幅建议 + 图表规划 | 用户确认大纲结构 | 必选骨架 + 可选模块池（按报告类型 + 研究方法触发）；叙事框架格式 |
| 5 专题研究 | 结构化卡片 + 证据包 + card-index.csv | 核心章 ≥3 张卡片；叙事化判断字段必填 | 4 类卡片（案例/技术/架构/理论）；3 类必填"叙事化判断"锚点字段；card_file_path 列登记 |
| 6 核心架构图 | 架构图/流程图（.drawio + .svg + .png） | 图号、图名、核心要素齐全 + 颜色注册表 | 先于写作完成——架构图是报告的骨架；统一灰度色板 + 暗红强调 |
| 7 分章写作 | 正文 Markdown + 随写作产出的数据图表 | 6 条内容质量 + 13 项逐章自查 + 写审对抗通过 | 多 Agent 档：writer+auditor 盲态预承诺 pipeline；论点骨架先行→回填证据→查后台外泄 |
| 8 红队审查 | 红队风险清单 → 逐项处理后更新为最终版 | 高风险 100% 处理，中风险 ≥80% | 8 维度 / 4 人格并行（异构模型）；极速档压缩为 3 维度 |
| 9 定稿整合 | 终稿 Markdown + 标准格式 `.docx` | 13 项交付清单逐项确认 | md→docx 转换器：41 模块 / ~10K 行 / 6 阶段管道 + Word 原生动态编号 + SEQ 域 + 反硬编码 AST 扫描 |

> **🚫 严禁标密**：本 skill 产出的所有研究报告均基于互联网公开资料。报告的任何位置（封面、页眉、页脚、正文、附录）禁止标注密级。

## 多 Agent 协同执行体系（v5）

详见 [`references/multiagent-orchestration.md`](references/multiagent-orchestration.md)。

### 11 个角色

口径：`agents/` 目录下实际存在的 Agent 定义文件数（不含 orchestrator——orchestrator 是主对话采用的编排剧本，未落地为 `agents/` 下的文件；已废弃的 `diagram_agent` 已移入 `agents/deprecated/`，不计入角色数）。

| 角色 | 族 | 模型 | 阶段 | 简介 |
|------|------|------|------|------|
| `report_orchestrator`（主对话剧本） | 编排 | Opus | 1-9 | 分派/门禁/CHECKPOINT/裁决/降级，6 个阻塞点用户确认 |
| `source_collector_agent` | 研究 | Haiku | 2 | 搜集→下载→抽取→来源索引 |
| `fact_verifier_agent` | 研究 | Opus | 3 | 事实核验台账，强表述降级 |
| `outline_architect_agent` | 设计 | Opus | 4 | 产出 outline.md 叙事框架契约 |
| `card_synthesizer_agent` | 设计 | Sonnet | 5 | 台账→结构化卡片 + 证据包 |
| `architecture_chart_agent` | 制图 | Sonnet | 6 | 核心架构图批量产出（总览图/架构图/流程图） |
| `data_chart_agent` | 制图 | Sonnet | 7 | 数据图表随写作按章产出（matplotlib） |
| `chapter_writer_agent` | 写作 | Sonnet | 7 | 逐章写作，卡片→叙事化转写 |
| `chapter_auditor_agent` | 审计 | Opus | 7 | 逐章独立审计（R3 的解），真跑 4 个检查脚本 |
| `redteam_agent`（×4 人格） | 红队 | 2×Opus+2×Sonnet | 8 | 全报告对抗审查，异构模型防同质化 |
| `redteam_synthesizer_agent` | 红队 | Sonnet | 8 | 合并去重 4 份报告→统一风险清单 |
| `finalizer_agent` | 格式 | Haiku | 9 | 合并、合约终检、转换器、13 项交付清单 |

> **废弃角色说明**：`diagram_agent`（原制图角色，Haiku，阶段 6+7）已于 2026-07-28 废弃，拆分为 `architecture_chart_agent`（阶段 6 核心架构图）+ `data_chart_agent`（阶段 7 数据图表），均升级为 Sonnet。原文件已移入 `agents/deprecated/diagram_agent.md`，不计入上表 11 个角色。
>
> **模型选型原则**：按认知负荷类型分级——强推理/强判断（审计、红队、核验、大纲）用 Opus；结构化生成（写作、卡片合成、红队综合）用 Sonnet；架构语义理解 + 编程（架构图、数据图表）用 Sonnet；机械/模板化（搜集、定稿）用 Haiku。

### 三档协同模式

| 档位 | 触发条件 | 阶段 7 写作 | 阶段 8 红队 | Agent 调用量级 | 跨模型支持 |
|------|---------|-----------|-----------|--------------|-----------|
| **完整多 Agent** | 立项报告(proposal) / ≥40 页 / 核心章 ≥3 | 全部章 writer+auditor 对抗 + loop-until-pass | 4 人格并行 + 综合 | 完整（10+ 角色） | Claude only（需 depth-1 委派） |
| **分层多 Agent**（默认） | 深度研究 30-50 页 / 核心章 2-3 | 仅核心章走对抗，其余 orchestrator 直接写 | 4 人格并行 + 综合 | 标准（6-8 角色） | Claude only（需 depth-1 委派） |
| **单 Agent 极速** | 快速简报(brief) / <15 页 / ≤2 章 | orchestrator 单 Agent + V3 自查兜底 | 3 维度自审 | 最小（回退 V3） | 全模型通用（`core`） |

> 非 Claude 宿主（DeepSeek V4/V3、GLM-4、Qwen3 等）通过 `model-profile.json` 声明能力档。若 `host.agent_delegation=false`（无 depth-1 委派底座），`model_profile.py` 的 C2 二维矩阵硬规则强制降级为单 Agent 极速档。完整可移植性声明见 [PORTABILITY.md](PORTABILITY.md)。

## 写作标准体系（25 条）

| 编号 | 标准 | 作用域 |
|------|------|--------|
| **标准 0** | 前台/后台分离（总纲）——正文只呈现成品判断，编辑部过程（证据分级/来源取舍/核验状态）下沉脚注 | 全报告类型 |
| 标准 1 | 证据驱动——每个关键判断对应至少一个具体来源 | 全类型 |
| 标准 2 | 不确定性标注——未核验事实必须加限定词 | 全类型 |
| 标准 3 | 机制导向——分析"为什么"而非"是什么" | 全类型 |
| 标准 4 | 架构先行——核心架构图在正文写作前完成 | 全类型 |
| 标准 5 | 反碎片化——禁止无逻辑关系的要点堆砌 | 全类型 |
| 标准 6 | 禁止位置性指代——用"如图 3-2"而非"下图""上表" | 全类型 |
| 标准 7 | 证据密度——每自然段 ≥1 个来源引用 | 全类型 |
| 标准 8 | 主张→证据→推理三角——每个关键判断呈完整论证链 | 全类型 |
| 标准 9 | 建议可操作性——谁/做什么/资源/效果指标 | 全类型 |
| 标准 10 | 量化优先——能用数字不用形容词 | 全类型 |
| 标准 11 | 承认边界——每章至少 1 句分析局限 | 全类型 |
| 标准 12 | 摘要自足性——摘要不是目录散文版 | 全类型 |
| 标准 13-17 | 立项报告专属（P1 技术指标量化 / P2 创新点三分 / P3 TRL / P4 里程碑 / P5 研究基础） | proposal 专用 |
| 标准 18 | 章节与节间过渡——叙事连贯性 | 全类型 |
| 标准 19 | 读者层次校准——"知识的诅咒"防御 | 全类型 |
| 标准 20 | 段落长度与信息密度 | 全类型 |
| 标准 21 | 表格写作规范 | 全类型 |
| 标准 22 | 术语一致性 | 全类型 |
| 标准 23 | 直接陈述语气——禁自述开头与自我辩护式元评论 | 全类型 |
| 标准 24 | 正面论证优先——禁以消极性证据/文献空白作为宏观理论贡献判断的核心支撑 | 全类型 |

> 详细示例与反例见 [`references/writing-standards.md`](references/writing-standards.md)（标准 0-24，共 25 条）。标准 7-12 即旧版 A-F 标签，已于 2026-07-26 统一为数字编号。

## 自动化检查脚本（15 个）

| 脚本 | 触发阶段 | 功能 | 调用方 |
|------|---------|------|--------|
| `contract_check.py` | 阶段 7 审计 | 合约 C1-C9 + 量化 QS1-QS4 | `chapter_auditor_agent` |
| `claim_strength_check.py` | 阶段 7 审计 | 扫描强表述词，交叉核对 claims-ledger.csv | `chapter_auditor_agent` |
| `card_overlap_check.py` | 阶段 7 审计 | n-gram 滑动窗口检测卡片-正文重合度 | `chapter_auditor_agent` |
| `chart_checks.py` | 阶段 6/7 | 图表 DPI/颜色/注册表自动检查 | `architecture_chart_agent` / `data_chart_agent` |
| `figure_gate.py` | 阶段6 CP + 阶段9 | 全自动文件系统级图表存在性检查（FATAL阻断） | orchestrator |
| `check_linkage_constants.py` | CI/维护 | 扫描 `linkage-const` 标记，与 `linkage-constants.json` 比对 | 开发者 |
| `check_no_hardcode.py` | CI | AST 扫描内容硬编码 + 结构违规 + schema 漂移 | 开发者 |
| **🆕 跨模型兼容性优化新增（2026-07-28）** |
| `model_profile.py` | 阶段 1 初始化 | 加载能力档（`--model auto` 自动检测模型名并生成配置） | orchestrator |
| `output_envelope_check.py` | 每阶段 | Agent 输出标记配对 + nonce 校验 + 噪声比率 | orchestrator |
| `schema_validate.py` | 每阶段 | JSON 输出 schema 校验 | orchestrator / `precommit_consistency_check.py` |
| `outline_title_extract.py` | 阶段 4 | 双向一致性检查：YAML 结构清单 vs Markdown 正文标题 | orchestrator |
| `phase_a_to_json.py` | 阶段 7 | Phase A 确认式 Markdown → JSON 落盘转换 | orchestrator |
| `precommit_consistency_check.py` | 阶段 7 | Phase A/B 承诺一致性机械校验（红线 A5） | orchestrator（不由 auditor 自调） |
| `writing_quality_check.py` | 阶段 7 | 写作质量 Lint（缩写展开检测 + 段落信息密度） | orchestrator |
| `delivery_checklist_check.py` | 阶段 9 | 交付清单逐项机械检查 | orchestrator |
| `finalize_pipeline.py` | 阶段 9 | 定稿管道编排（merge_drafts + convert_references + contract_check） | orchestrator |
| `degradation_log.py` | 全局 | 降级事件台账写入 | 各脚本 |
| `degradation_report.py` | 阶段 9 | 降级台账聚合报告（阻断未确认 L-显著事件） | orchestrator |

## 转换器卡片-正文重合度检测

阶段 7 审计的"资产·转写维度"（P0-6）检测写作者是否将卡片字段逐字誊抄进正文：

- **机制**：`card_overlap_check.py` 对正文与每张卡片做 n-gram（探测粒度 12 字）滑动窗口重合检测
- **阈值**：单张卡片最长连续重合 ≥46 字（P75，据 104 张卡片 + `final-report.md` 实测校准）→ 候选 OVERLAP-HIT
- **豁免**：外文原文直引 / 精确数字+单位 / 机构专有名 / 法条标准编号（逐字一致是正当的）
- **判罚**：单章非专有 OVERLAP-HIT ≥2 处 → 审计维度 block → 触发 REVISE

## md→docx 转换器 v2

阶段 9 使用自研转换器（`scripts/md2docx/`，41 模块 / ~10K 行 Python）将 Markdown 转换为符合 V3.2 格式规范的 .docx：

| 特性 | 实现 |
| ---- | ---- |
| 封面 | 标题 + 副标题 + 机构 + 日期 + 版本，无密级字段 |
| 目录 | Word 原生 TOC 域（四态 `begin→instrText→separate→end`），按 F9 更新 |
| 章节编号 | Word 原生多级列表（`w:numPr`）：章/节/小节三级共享计数器，"第1章"/"1.1"/"1.1.1"自动联动；附录独立字母编号 |
| 图表编号 | SEQ 域自动编号（`SEQ 图 \* ARABIC` / `SEQ 表 \* ARABIC`），`placeholder_text` 避免 F9 前空白 |
| 图片 | PNG 嵌入，`![图X-Y 标题](路径)` 动态解析，图号可选（`图(?:1-1)? 标题` 均合法） |
| 表格 | 全框线（含竖线）、交替行灰底、表头重复、垂直居中；表号可选同图 |
| 页码 | 摘要罗马数字 + 正文阿拉伯数字，四节方案 |
| 域更新 | `w:updateFields` 文档级设置，Word 打开时自动更新所有域（SEQ/PAGEREF/TOC 双保险） |
| 引号 | R-13 有状态全角化（`"`→`"`/`"`）+ R-20 引号字体修正（`add_run_segments` 宋体覆盖） |
| 清理 | R-12 写作者自声明块删除兜底 + R-14 红队批注块删除兜底 |
| 门禁 | 14 项 gate3 输出校验（密级复检、编号连续性、分页一致性、域三态等） |
| 反硬编码 | `check_no_hardcode.py` AST 扫描 + 换样本金标准测试（CI 必跑） |

> 转换器设计文档位于 `design/md-to-docx-design-v2/`（7 份）。踩坑记录见 [`references/md-to-docx-pitfalls.md`](references/md-to-docx-pitfalls.md)（代码层）和 [`references/writing-process-pitfalls.md`](references/writing-process-pitfalls.md)（流程层），两者互补。

## 图表绘制质量约束

阶段 6/7 出图遵循统一的图表质量约束方案（`design/chart-quality-constraints/`）：

- **配色**：7 档学术灰度色板 + 单强调色 #D62728，禁止彩色
- **字体**：宋体 + Times New Roman，标签 10pt / 图例 9pt（V3.1 §5.2）
- **一致性**：跨图颜色映射注册表（`color-registry.csv`），同概念同色
- **matplotlib**：全局样式模板（`matplotlib-report-style.mplstyle`），`plt.style.use()` 一键加载
- **检查**：`scripts/chart_checks.py` 自动检查 DPI / 颜色 / 注册表
- **反模式**：禁止 3D 图表、>5 扇区饼图、双 Y 轴滥用等 12 项

## 目录结构

```
deep-research-report/
├── SKILL.md                              # 核心方法论（skill 主体，模块化入口）
├── README.md                             # 本文件
├── dashboard.md                          # Darwin 2.0 评估优化记录
├── PORTABILITY.md                        # 可移植性边界声明（人读版）
├── portability-manifest.json             # 可移植性边界声明（机读版，CI 校验用）
├── linkage-constants.json                # SSOT 跨文件数值常量（7 个阈值/限额）
├── model-profile.json                    # 能力档声明（仓库默认 tier A = Claude 安全基线）
├── model-profile.{claude,deepseek,unknown}.example.json  # 三份 tier A/B/C 示例
├── model-profile.local.json              # 用户本地覆盖（.gitignore 保护，不提交）
├── .gitignore                            # 排除 research/ output/ .local.json
├── agents/                               # 11 个 Agent 定义（prompt + 契约）
│   ├── chapter_writer_agent.md           # 写作者（Sonnet）
│   ├── chapter_auditor_agent.md          # 审计者（Opus，R3 的解）
│   ├── redteam_agent.md                  # 红队 4 人格（异构 2×Opus+2×Sonnet）
│   ├── redteam_synthesizer_agent.md      # 红队综合去重（Sonnet）
│   ├── outline_architect_agent.md        # 大纲设计（Opus）
│   ├── card_synthesizer_agent.md         # 卡片合成（Sonnet）
│   ├── source_collector_agent.md         # 资料搜集（Haiku）
│   ├── fact_verifier_agent.md            # 事实核验（Opus）
│   ├── architecture_chart_agent.md       # 核心架构图（Sonnet，阶段6；drawio MCP）
│   ├── data_chart_agent.md               # 数据图表（Sonnet，阶段7）
│   ├── finalizer_agent.md                # 定稿整合（Haiku）
│   ├── deprecated/                       # 已废弃角色归档
│   └── contracts/                        # writer_contract.json + auditor_contract.json
├── scripts/
│   ├── contract_check.py                 # 合约 + 量化检查（审计 Agent 确定性工具）
│   ├── claim_strength_check.py           # 强表述扫描
│   ├── card_overlap_check.py             # 卡片-正文重合度检测
│   ├── chart_checks.py                   # 图表 DPI/颜色/注册表检查
│   ├── figure_gate.py                    # 全自动图表存在性门禁（FATAL阻断）
│   ├── check_linkage_constants.py        # SSOT 数值一致性校验
│   ├── convert_references.py             # [SRC-XXX] → [N] 引用格式转换
│   ├── merge_drafts.py                   # 分章草稿合并管道
│   ├── term_consistency_check.py         # 术语一致性检查
│   ├── model_profile.py                  # 能力档加载 + --model auto 自动配置
│   ├── output_envelope_check.py          # Agent 输出标记配对 + nonce + 噪声
│   ├── schema_validate.py                # JSON schema 校验（Draft 2020-12）
│   ├── outline_title_extract.py          # YAML 结构清单 vs Markdown 标题一致性
│   ├── phase_a_to_json.py               # Phase A 确认式 Markdown → JSON 落盘
│   ├── precommit_consistency_check.py    # Phase A/B 承诺一致性机械校验（红线 A5）
│   ├── writing_quality_check.py          # 写作质量 Lint（缩写 + 信息密度）
│   ├── delivery_checklist_check.py       # 13 项交付清单逐项机械检查
│   ├── finalize_pipeline.py              # 定稿管道编排
│   ├── degradation_log.py                # 降级事件台账写入
│   ├── degradation_report.py             # 降级台账聚合报告
│   ├── md2docx.py                        # md→docx 转换器入口 shim
│   └── md2docx/                          # 转换器 v2 主包（41 模块）
│       ├── cli.py / config.py            # CLI + 配置
│       ├── iotools.py / ir.py / issues.py # I/O 入口 + IR 定义 + Issue 跟踪
│       ├── pipeline.py                   # 6 阶段管道编排
│       ├── textstage/                    # normalize / clean / parse / inline / tokens
│       ├── assemble/                     # metadata / headings / figures / tables / builder / breaks
│       ├── render/                       # cover / toc / headings / numbering / paragraphs / lists /
│       │                                 # tables / figures / special / document / styles / oxml_helpers /
│       │                                 # headerfooter
│       ├── validate.py / report.py / gate3.py  # 校验 + 报告 + 门禁
│       └── check_no_hardcode.py          # AST 反硬编码扫描
├── schemas/                              # JSON Schema 定义（Draft 2020-12）
│   ├── model-profile.schema.json         # model-profile.json 结构约束
│   ├── auditor-phase-a.schema.json       # Phase A 盲态预承诺落盘格式
│   ├── auditor-phase-b.schema.json       # Phase B 明态打分流盘格式
│   ├── outline-structure.schema.json     # outline.md YAML 结构清单约束
│   └── writer-selfclaim.schema.json      # Writer 自声明格式约束
├── tests/                                # 测试目录（CI 必跑，280+ 项）
│   ├── conftest.py                       # fixtures + 台账隔离
│   ├── test_model_profile.py             # 能力档加载 + auto_configure 测试
│   ├── test_phase_a_to_json.py           # Phase A JSON 转换
│   ├── test_precommit_consistency_check.py  # 一致性校验
│   ├── test_output_envelope_check.py     # 输出信封
│   ├── test_schema_validate.py           # schema 校验
│   ├── test_outline_title_extract.py     # 标题提取
│   ├── test_degradation_report.py        # 台账报告
│   ├── test_golden_snapshot.py           # L2 黄金快照基线
│   ├── test_structured_fixture.py        # 结构化 fixture（含真实 subsections）
│   ├── test_agent_contracts.py           # Agent 合约一致性（hint 覆盖率等）
│   ├── test_doc_consistency.py           # 文档一致性（角色数/标准数等）
│   ├── test_envelope_nonce.py            # nonce 生成/匹配
│   ├── test_writing_quality_check.py     # 写作质量
│   ├── test_delivery_checklist_check.py  # 交付清单
│   ├── test_finalize_pipeline.py         # 定稿管道
│   ├── fixtures/structured-sample/       # 结构化测试数据
│   └── golden/                           # 8 份黄金样本快照
├── design/
│   ├── model-compatibility-audit-report.md        # 跨模型兼容性问题诊断（30 项发现）
│   ├── model-compatibility-optimization-plan.md   # 跨模型兼容性优化方案 V1.3（已执行完成）
│   ├── md-to-docx-design-v2/             # 转换器 v2 完整设计（7 份文档）
│   └── chart-quality-constraints/        # 图表质量约束方案（9 份文档 + .mplstyle）
├── references/                           # 阶段/Agent 执行时按需读取的参考文件
│   ├── stage-1-init.md through stage-9-finalize.md  # 9 阶段独立 spec
│   ├── appendix-report-types.md          # 报告类型适配 + 分报告类型行文要点
│   ├── appendix-converter-contract.md    # 转换器合约 C1-C9
│   ├── writing-standards.md              # 写作标准详细说明（标准 0-22）
│   ├── writing-process-pitfalls.md       # 写作/协同流程踩坑记录（流程层根因分析）
│   ├── md-to-docx-pitfalls.md            # 转换器踩坑记录（代码层修复方案）
│   ├── multiagent-orchestration.md       # 多 Agent 编排总纲
│   ├── workflow-stage7.md / workflow-stage8.md  # 阶段 7/8 编排脚本规格
│   ├── red-team-checklist.md             # 红队审查 8 维度详细清单（含极速档 3 维度）
│   ├── architecture-analysis-guide.md    # 架构分析方法论指南
│   ├── 研究报告格式规范.md               # 【权威】Word 格式规范 V3.1
│   ├── claims-ledger-template.csv        # 事实核验台账模板
│   ├── source-index-template.csv         # 来源索引模板
│   ├── card-index-template.csv           # 卡片索引模板
│   ├── color-mapping-rules.yaml          # 项目级颜色映射规则
│   └── tool-paths.json                   # 外部工具路径集中配置
├── assets/                               # 静态资源
├── evals/                                # 评估用例
├── research/                             # 运行时工作区（gitignored）
└── output/                               # 运行时产物（gitignored）
```

## 使用方式

当用户提出"研究报告、深度分析、白皮书、政策研究、行业分析、技术评估、可行性研究"等相关请求时，skill 会自动触发。也可以直接输入：

> 帮我写一份关于 XX 行业的深度研究报告

依次执行阶段 1–9，在每个质量门槛处与用户确认，最终产出：
- Markdown 终稿
- 符合 V3.2 规范的标准格式 `.docx`（封面 + TOC 域 + 动态多级列表编号 + SEQ 图/表域 + 页眉页脚 + 全框线表格）
- `research/figures/` 下的全部架构图与数据图表（PNG 300dpi + SVG 源文件）

### 跨模型适配（DeepSeek V4/V3、GLM-4、Qwen3 等）

**Claude 用户默认零配置**——仓库自带的 `model-profile.json` 已经是完整的 Claude 能力档。非 Claude 用户在启动 skill 后第一件事：

```bash
# 自动探测当前模型并生成匹配的能力档配置
python scripts/model_profile.py --model auto
```

Orchestrator 会自动完成这一步，用户无需手动干预。脚本从环境变量探测模型名，匹配内置映射表（Claude→A、DeepSeek V4→B/380K、DeepSeek V3/GLM-4/Qwen3→B/8K），生成 `.gitignore` 保护的 `model-profile.local.json`。

自动匹配的模型到能力档映射，以及降级策略，详见 [SKILL.md §模型能力档](SKILL.md#模型能力档model-profilejson) 和 [`scripts/model_profile.py`](scripts/model_profile.py) 的 `_MODEL_RULES` 映射表。离开 Claude 后 skill 退化成什么样子，可以保留哪些能力，详见 [PORTABILITY.md](PORTABILITY.md)。

### 极速模式

时间 < 3 天或篇幅 < 20 页时自动触发：阶段 2-3 合并（边收集边核验）→ 大纲降为二级标题 → 只出 1 张总览图 → 写作只强制执行标准 7（证据密度）+ 标准 10（量化优先）→ 红队压缩为 3 项 → 交付 Markdown 终稿。**阶段 3（事实核验）和阶段 8（红队审查）仍不可跳过**。

## 外部依赖

### 资料搜集与抽取

| 工具 | 用途 | 配置 |
| ---- | ---- | ---- |
| **web-search-skill** | 通用网页搜索（Tavily + 百度双引擎） | 环境变量 `TAVILY_API_KEY` + `QIANFAN_API_KEY` |
| **paper-search** | 学术论文搜索与下载（20+ 数据源） | `uv tool install paper-search-mcp` |
| **MinerU** | 文档精准解析（PDF/Office/图片/HTML → Markdown） | 环境变量 `MINERU_TOKEN`（[申请](https://mineru.net/apiManage)） |

### 出图工具

| 工具 | 用途 | 配置 |
| ---- | ---- | ---- |
| **drawio（MCP）** | 架构图/流程图生成 `.drawio` | 无需安装，MCP 内置 |
| **draw.io 桌面版** | `.drawio` → `.svg` / `.png` 导出 | 路径见 `tool-paths.json` |
| **fireworks-tech-graph** | 技术架构图，10+ 模板 | `pip install cairosvg` |
| **Mermaid** | 简单流程图备选（≤15 节点） | 内联 Markdown |
| **mermaid-cli (mmdc)** | Mermaid → PNG 渲染 | `npm install -g @mermaid-js/mermaid-cli`；路径见 `tool-paths.json` |

### 转换与检查

| 工具 | 用途 | 配置 |
| ---- | ---- | ---- |
| **md2docx** | Markdown → 标准格式 Word | `pip install python-docx pillow pyyaml` |
| **chart_checks.py** | 图表 DPI / 颜色 / 注册表自动检查 | `pip install pillow numpy` |

## 评估优化记录

本 skill 使用 [darwin-skill](../darwin-skill) 方法论完成三轮评估优化：

| 轮次 | 日期 | 分数 | Δ | 主要改进 |
| ---- | ---- | ---- | :-: | ---- |
| 第 1 轮 | 2026-06-10 | 71.0 → 83.8 | +12.8 | 检查点设计、失败模式编码、反例黑名单 |
| 第 2 轮 | 2026-07-17 | 81.6 → 86.8 | +5.2 | P0 runtime 中立、dim5 路径执行指引、dim7 去重、dim8 全量实测 |
| 第 3 轮 | 2026-07-21 | 74.2 → 78.8 | +4.6 | dim4 补 3 CHECKPOINT + dim3 补 3 fallback + dim7 FAQ 精简 |

> 第 3 轮基线较低是因为评估 rubric 升级到 v2.0（新增 dim9 反例黑名单维度，dim3/dim5 权重加大）。

当前 9 维度评分：

| dim | 维度 | 权重 | 得分 | dim | 维度 | 权重 | 得分 |
| :-: | ---- | :-: | :-: | :-: | ---- | :-: | :-: |
| 1 | Frontmatter 质量 | 7 | 8/10 | 6 | 资源整合度 | 4 | 9/10 |
| 2 | 工作流清晰度 | 12 | 8/10 | 7 | 整体架构 | 12 | 9/10 |
| 3 | 失败模式编码 | 12 | 9/10 | 8 | 实测表现 | 23 | 8/10 |
| 4 | 检查点设计 | 6 | 8/10 | 9 | 反例与黑名单 | 6 | 8/10 |
| 5 | 可执行具体性 | 17 | 8/10 | — | 加权总分 | 100 | 78.8 |

> 详见 `dashboard.md`。
