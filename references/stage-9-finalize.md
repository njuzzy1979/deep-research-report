---
portability: core
---

# 阶段 9：定稿整合

> 本文件是 deep-research-report skill 的阶段 9 详细 spec，从 SKILL.md 拆分而来。
> 母文件：`../SKILL.md`（流程索引）

---

## 9.0 推荐执行方式：`scripts/finalize_pipeline.py`（方案 §D5）

> **多 Agent 协同体系下（`finalizer_agent` 执行）以及单 Agent 极速档下，均推荐优先使用本脚本**，而非下方 §9.1.x 逐条手动执行 grep/cat/contract_check 命令——脚本已把剥离标记→H1检测替换→结构驱动合并→引用转换→合约终检（`--merged --stage stage9`）→13项交付清单这 6 个顺序强依赖步骤串成单一 Python 流程，消除人工/弱模型记错步骤顺序的风险。下方 §9.1/§9.1.x 的分步说明仍保留，作为脚本不可用环境下的手动兜底参考、以及理解每一步具体做什么的详细说明。

```bash
python scripts/finalize_pipeline.py \
  --drafts-dir research/drafts --outline research/outline.md \
  --source-index research/sources/source-index.csv \
  --output research/drafts/final-report.md \
  --glossary research/glossary.md --figures-dir research/figures \
  --redteam-diff research/redteam-resolution-diff.md --json
```

JSON 输出含 `failure_step` 枚举字段（`strip_markers`/`h1_check`/`merge`/`convert_refs`/`contract_check`/`delivery_checklist`，外加可选第 7 步 `verify_docx`），标出具体哪一步失败，退出码 0/1/2 语义见脚本内 docstring。

**权威路由表在 `agents/finalizer_agent.md`**（唯一副本，含按调用点行号的二级键；此处**不做副本**——两处副本必然漂移）。本节只给出可直接执行的路由动作摘要：

| `failure_step` | 立即可执行的动作 |
| --- | --- |
| `strip_markers` | 检查 `research/drafts/` 是否存在且含 `ch*.md`；模块 import 失败则检查 Python 环境 |
| `h1_check` | 回报 orchestrator（脚本内部错误） |
| `merge` | 先读 `failure_reason`：含"解析失败"→ **回炉 `outline_architect_agent`** 修 outline.md 语法；含"键名归一化异常"→ **改脚本不改 outline**，回报 orchestrator |
| `convert_refs` | CSV 问题 → **回炉 `source_collector_agent`**；斜杠引用 → **回炉对应 `chapter_writer_agent`** 改逗号分隔 |
| `contract_check` | 先比对下方"已知系统性冲突"两条；确系内容违规才**回炉对应写作环节** |
| `delivery_checklist` | 按 `detail.failed_items` 对照 13 项清单**回炉对应环节** |
| `verify_docx` | `detail.empty_headings` 非空即"章节是空的"形态 → 回报 orchestrator，**禁止手动改 docx** |

**失败时的动作闭集**：允许——读错误输出、查路由表、**回炉**对应 Agent、升级呈报用户。禁止——自行编写替代实现、在违规产物上打补丁、把半成品当成品交付、静默改判、跳过失败步骤、用"超出工具链能力"免责。

**不要把 `.partial` / `.stale-*` 当交付物**：管线全程写 `.partial`，全部步骤通过才原子转正（D2-8）。正式产物名存在即等价 `overall_pass: true`。

> **⚠️ 已知系统性冲突（实现阶段实测确认，详见实现报告）**：`contract_check` 步骤在真实报告场景下可能因两处既有脚本组件间的矛盾而失败——(1) `merge_drafts.assemble_merged()` 按规范插入的标准章容器 `## 第 X 章：<chapter_title>` 会被 `contract_check.py` 的 C2（手动编号检测）判为 `fatal`；(2) `convert_references.py` 转换出的正常纯数字引用 `[N]` 会被 C6 判负。这两处不是 `finalize_pipeline.py` 的实现缺陷，是 `contract_check.py` 既有判定规则与 stage9 合并产物格式之间此前从未被真正验证过的冲突（此前 `merge_drafts.py` 自身的阶段 E/F 校验只 WARN 不阻断，从未让这一冲突真正生效过）。命中时不应回炉重写章节内容，应回报 orchestrator 决定人工豁免或另行修订 `contract_check.py`（后者超出阶段9执行者权限）。

### 9.0.1 门禁对应（方案 §D1）

本阶段对应 `multiagent-orchestration.md` §5 门禁体系中的 **G(交付)** 一行（沿用现有门禁实名，非虚构 G0-G8）：

| 门禁/阶段 | 新增调用 | 调用者 | 失败路由 |
| --- | --- | --- | --- |
| **G(交付)** | `degradation_report.py`（**12 项 → 13 项清单**，第 13 项"降级台账确认"由 `scripts/delivery_checklist_check.py` 聚合调用，见 §9.1） | `finalizer_agent` | 未确认降级 → **阻断 CP6** |

---

## 9.1 整合清单

> **与方案 §D6 的对应关系**：下方是人工核对口径的整合清单（历史沿革，逐项对应写作规范原文）；方案 §D6 "12 项 → 13 项清单"是其**脚本化聚合版本**（`scripts/delivery_checklist_check.py`，10 项可脚本化 + 2 项 manual_required + 第 13 项降级台账确认，见 §9.0 D5 管道第 6 步 `delivery_checklist`）——推荐执行方式下由脚本自动核对前 11 项中的可脚本化部分，人工只需核对 manual_required 的 2 项与全文通读。两份清单条目大体一一对应，不是相互独立的两套标准。

- [ ] 统一术语（同一概念在全文中使用相同名称）
- [ ] **全文术语一致性核对**：运行 `scripts/term_consistency_check.py`，以 `research/glossary.md` 为基准，检查合并后 `final-report.md` 全文。确认无 banned_forms 泄露、所有原创核心概念的 preferred_form 被逐字使用、aliases 首次使用时已标注
- [ ] **统一引用格式**：正文上标编号 `[N]` → 文末参考文献列表按 GB/T 7714-2015 格式，首次出现顺序排列。同一来源多次引用合并为同一编号。**确认参考文献列表中无 `[A]`/`[B]`/`[C]`/`[D]` 信源分级前缀**
- [ ] **参考文献去重与编号统一**：检查是否存在同一来源以不同编号出现的情况——合并为同一编号；确认所有 `[N]` 在正文和参考文献列表之间一一对应，无遗漏无多余
- [ ] 图表编号统一（图 N-M：章号-图序）
- [ ] 交叉引用检查（"如图 X-Y 所示"与实际图表编号一致）
- [ ] **输出隔离标记剥离**：所有分章文件中 `[AGENT-OUTPUT-START]` / `[AGENT-OUTPUT-END]` 标记行（含可选 `:<nonce>` 十六进制后缀，两种形式均须剥离）已删除（F1 违规检测）
- [ ] **写作者自声明剥离**：各分章文件中 `### 写作者自声明（第 X 章）` 区块已完整删除
- [ ] **红队批注剥离**：`> [红队 RXXX 已改写/已补证据]` 等引用块已删除
- [ ] **字数统计残留清理**：`全文约 XXXX 字`、`本章字数约 XXXX` 等已删除（C8 检查）
- [ ] **引用格式转换**：`convert_references.py` 已执行，所有 `[SRC-XXX]` 已转为 `[N]` 纯数字引用（C7 检查）
- [ ] **局部参考文献清理**：任一分章文件中不存在独立 `## 参考文献` 或 `### 参考文献` 节（C9 检查）
- [ ] 各章草稿合并为完整 Markdown 终稿（`research/drafts/final-report.md`）
- [ ] **剥离写作者自声明与审校批注块**：合并分章文件前，删除各分章文件中的"写作者自声明"区块（`### 写作者自声明（第 X 章）`及其下方内容，chapter_writer_agent 契约产出的审计中间数据）与"红队/阶段9审校批注"引用块（`> [红队 RXXX 已改写]`格式，阶段8红队审查过程标记）——这两类是**工作流协作元数据**，从未打算出现在最终交付文档中。**本步仍是第一防线**；`textstage/clean.py` 侧已实现兜底规则 R-12/R-14（见 §9.2），会在脚本转换阶段兜底清理遗漏，但不应作为跳过本步人工核对的理由
- [ ] 封面文件 `research/cover.md` 存在且内容完整（标题/副标题/报告类型/机构/日期/版本/页眉简称），转换时使用 `--cover research/cover.md` 参数
- [ ] **红队风险清单处理确认**：逐条核对风险清单中的实际处理结果，确认正文已按处理结果修改；未处理的中风险项已在附录中列出原因
- [ ] 全文通读至少一遍

### 9.1.x 分章合并——H1 冲突预防（解决 D-1）

> 本节对应 v3 优化方案修改 4.6.1、v5 清单 #21。在多 Agent 协同体系下，本步骤由 `finalizer_agent` 执行；单 Agent 档下由 orchestrator 执行。分文件写作时各章独立用 H2（见 stage-7-writing.md §7.2.2），已从源头预防 D-1，本步是合并前的**终检兜底**。

**合并前检查**：在合并所有分章文件之前，先 grep 每个文件中 H1 的数量：

```bash
for f in research/drafts/ch*.md; do
  count=$(grep -c "^# " "$f")
  if [ "$count" -gt 0 ]; then
    echo "WARNING: $f 包含 $count 个 H1——合并后会产生多个主标题"
  fi
done
```

**如果任一分章文件包含 H1 → 在合并前将分章文件中的 H1 替换为 H2。**
**合并后的 final-report.md 只能有 1 个 H1（即前言/导论，或由阶段 9 自动添加）。**

**合并命令（推荐使用 cat + 转换器自动编号，不要在 PowerShell 中手动拼接）**：

```bash
# 正确方式：按顺序 cat 分章文件，转换器自动处理编号
cat research/drafts/ch01-*.md research/drafts/ch02-*.md ... > research/drafts/final-report-body.md
```

**合并后终检**：对合并后的 `final-report.md` 运行合约终检（v5 清单 #6 复用）——

```bash
python scripts/contract_check.py research/drafts/final-report.md --merged --stage stage9
```

`--merged` 模式下 C1 允许恰好 1 个 H1；若 > 1 则说明分章 H1 未清理干净，回到上一步替换为 H2。`--stage stage9` 与 `scripts/finalize_pipeline.py`（见 §9.0）内部调用 `check_contract(merged=True, stage="stage9")` 的参数口径保持一致（stage9 下 C2 severity 升级为 fatal、C7 由 WARN 升级为 FATAL）——本节手动兜底命令仅在 §9.0 脚本不可用时使用，仍应带上该参数，避免因遗漏 `--stage stage9` 而得到比脚本化路径更宽松（因而不可信）的通过结果。

## 9.2 自动导出标准 Word 文档（.docx）——必须执行

**研究报告的最终交付物必须是格式规范的 Word 文档。本阶段自动执行，不需要用户单独要求。**

> **✅ 转换器 v2 已完成实现与验证（2026-07-24）**：新版转换器（`scripts/md2docx/` 包，六阶段管道：规范化→清理→解析→IR 装配→渲染前校验→渲染→门3 输出校验→转换报告）已按 [`design/md-to-docx-design-v2/00-master-design.md`](../design/md-to-docx-design-v2/00-master-design.md) 完成 C-01~C-16 全部改动并通过测试套件（`scripts/md2docx/tests/`）。原 `scripts/markdown_to_docx.py` 的 FIGURE_MAP 硬编码缺陷已被"图/表三元组 100% 动态解析 + 反硬编码红线（`check_no_hardcode.py` AST 扫描 + 换样本金标准测试）"根治。下方 CLI 调用示例与"脚本自动完成的全部处理"表格均已同步为实际实现的准确参数名与行为。

**格式标准**：严格遵循 [`references/研究报告格式规范.md`](研究报告格式规范.md)（V3.1，遨天科技编制），该规范涵盖了文档全生命周期的格式要求：
- 文档结构（封面/摘要/目录/正文/参考文献/附录）
- 页面布局（A4、左边距 3.17cm、右边距 2.54cm、1.5 倍行距、首行缩进 2 字符）
- 字体与标题体系（标题 微软雅黑/Times New Roman、正文 宋体/Times New Roman；H1 24pt/H2 16pt/H3 14pt/正文 11pt）
- 图表编号系统（图 X-Y / 表 X-Y，章内序号）
- 表格规范（全框线含竖线、1.5pt 顶底线、交替行灰底 #F2F2F2、表头 10pt 微软雅黑加粗）
- 页眉页脚（页眉右对齐含 1pt 黑色底线、摘要罗马数字页码、正文阿拉伯数字页码）
- 封面设计、参考文献格式（GB/T 7714-2015，上标编号，按首次出现顺序排列）、特殊元素（定义框/案例框/趋势提示）
- Word 技术实现规范（TOC 域、多级列表、交叉引用、样式继承）
- 输出检查清单（13 项，§10.3）

使用本 skill 内置的一体化转换脚本（整合了 Markdown 清理、Word 生成、图片嵌入、表题注匹配）：

```bash
python -m md2docx \
  research/drafts/final-report.md \
  output/报告题名_v1.0.docx \
  --title "报告题名" \
  --figures-dir research/figures \
  --cover research/cover.md \
  --outline research/outline.md
```

**脚本自动完成的全部处理**（截至本文档更新时，`textstage/clean.py` 规则表已实现至 R-14，含兜底规则 R-12/R-13/R-14）：

| 处理阶段 | 内容 |
|---------|------|
| **Markdown 清理** | 二进制安全读取（自动处理 BOM / CRLF / 嵌入 CR）、剥离手动标题编号（兼容带编号/不带编号两种输入）、删除 HTML div 标签、删除"图表占位"标记、删除"建议印刷页数"行、删除 TOC 指示文字、删除封面元数据、删除"全文完"、删除孤立表引用、剥离列表图引用前缀、清理阶段8红队过程标记（`[红队 RXXX 已改写/已补证据]`）|
| **R-12：写作者自声明块删除**（✅ 已有兜底） | 兜底删除各分章文件中残留的"写作者自声明"区块（`### 写作者自声明（第 X 章）`/`### 作者自声明`标题及其下方内容，到下一个同级/更高级标题或文件末尾为止）。**第一防线仍是 `finalizer_agent` 在合并阶段主动剥离（见 §9.1）**——脚本侧此规则作为兜底防线，防止主防线遗漏或分章文件格式变化时残留漏网 |
| **R-13：引号全角化**（✅ 已实现） | 有状态引号开合配对算法：逐字符扫描正文中的直引号（`"` U+0022），根据当前"是否处于引号内"状态交替转换为中文全角弯引号开引号（`"`）/闭引号（`"`），修复引号字符类型与 V3.1 格式规范不符的问题。全文扫描结束仍处于"引号内"状态时记录 W-CLN-05 警告，提示人工复核未闭合引号（不强行回退已完成的替换） |
| **R-14：红队/审校批注块删除**（✅ 已实现） | 删除形如 `> [红队 RXXX 已改写]` / `> [阶段9 ...]` 开头的引用块（阶段8红队审查与阶段9审校过程中产生的批注，非最终交付内容）——与"Markdown 清理"行中已实现的行内红队标记清理（`[红队 RXXX ...]`）是同类根因下的不同残留形态：行内标记嵌在正文句子中已被清理，引用块整段以 `>` 起始独立成块，本规则处理该形态 |
| **Word 文档生成** | 封面（中文标题 26pt + 英文副标题 + 编制信息）、目录 TOC 域（begin→instrText→separate→end）、标题自动编号（第一章 / 1.1 / 1.1.1）、正文首行缩进 2 字符 / 1.5 倍行距、表格格式化（表头灰底加粗、表体五号 10.5pt）、页眉/页脚（居中页码）、分页控制（每个 H2 章节边界唯一触发，附录各篇默认独立起页） |
| **图片嵌入** | PNG 图表按 `![图X-Y 标题](路径)` 语法 100% 动态解析嵌入（零硬编码映射表），强制显式指定嵌入宽度（不信任源文件 DPI 元数据），图题注在下方居中 |
| **表题注修复** | 基于 `**表X-Y 标题**` 加粗题注行与紧邻表格的邻接关系动态关联（零硬编码），表题注在上方居中（黑体加粗 12pt）|

**脚本依赖**：`pip install python-docx pillow`

> **重要**：转换后的 .docx 需要在 Microsoft Word 或 WPS Office 中打开，右键点击目录区域选择"更新域"以生成实际目录页码。（TOC 域的正确结构 `begin→instrText→separate→end` 已内置，更新域即可正常生成页码；WPS 不保证自动更新域，需用户手动触发。）

> **⚠️ 如果 md→docx 转换失败**（脚本报错 / 图片缺失 / 格式异常）：
> 1. **图片文件缺失** → 检查 `research/figures/` 中是否所有 PNG 都存在；缺失的图用占位框替代（转换器自动处理，exit code 1），后续补图后重跑
> 2. **Python 依赖缺失** → `pip install python-docx pillow pyyaml`
> 3. **Markdown 语法异常** → 查看 `.conversion-report.md` 中的 ERROR/WARNING 列表，修正源 md 中对应行后重跑
> 4. **仍失败** → 回退到 Pandoc 基础转换：`pandoc final-report.md -o output.docx --reference-doc=template.docx`（丢失 V3.1 精确格式——TOC域/封面/图表题注/页眉页脚均需手动补做）

## 9.3 最终交付物

- **Word 文档**（`.docx`）——主要交付物，自动生成于 `output/` 目录，严格遵循 [`研究报告格式规范 V3.1`](研究报告格式规范.md)
- 正文 Markdown 终稿（`research/drafts/final-report.md`）——中间产物，供版本管理
- 附录（独立文件或附于正文后）
- 图表源文件（`.drawio` / `.svg` / `.png`，位于 `research/figures/`；PNG 均为 300dpi+ 含 pHYs 元数据，是 docx 嵌入的唯一格式，SVG 仅供人工编辑）
- 事实核验台账（`research/claims/claims-ledger.csv`）
- 红队风险清单
- 转换报告（`output/报告题名_v1.0.conversion-report.md`）——记录清理动作台账、渲染前后校验结果、需人工复核清单
- 清理后的 Markdown——**默认不生成**（内存直通处理，不落盘）；如需调试排查，加 `--dump-intermediate` 参数可选生成 `research/drafts/final-report-cleaned.md`

**交付前对照 V3.1 规范 §10.3 的输出检查清单逐项确认：**
- [ ] 封面完整（标题/副标题/机构/日期/版本），**无密级标注**
- [ ] 字体体系正确（标题 微软雅黑+TNR、正文 宋体+TNR）
- [ ] 所有章节编号连续无跳号
- [ ] 所有图表编号连续且与正文交叉引用一致
- [ ] 表格均为全框线（含竖线），跨页长表表头重复
- [ ] 表格交替行灰底，表头 10pt 微软雅黑加粗
- [ ] 页码正确（摘要罗马数字，正文阿拉伯数字）
- [ ] 页眉右对齐含 1pt 黑色底线，页脚居中
- [ ] 无空白页/多余分页符
- [ ] 链接可点击
- [ ] 目录自动生成且可跳转
- [ ] 文末参考文献完整，按 GB/T 7714-2015 格式，首次出现顺序编号，无信源分级标注

🔴 CHECKPOINT · 🛑 STOP：全部 13 项交付清单确认通过后，报告正式定稿。任一项未通过 → 对照症状回到对应阶段修复（封面/字体 → 阶段9 整合；编号/图表 → 阶段7 写作；表格/页码/页眉 → 重新运行阶段9 转换脚本）。
