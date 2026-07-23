# 阶段 9：定稿整合

> 本文件是 deep-research-report skill 的阶段 9 详细 spec，从 SKILL.md 拆分而来。
> 母文件：`../SKILL.md`（流程索引）

---

## 9.1 整合清单

- [ ] 统一术语（同一概念在全文中使用相同名称）
- [ ] 统一引用格式（`[来源机构，日期，《标题》，URL]`）
- [ ] 图表编号统一（图 N-M：章号-图序）
- [ ] 交叉引用检查（"如图 X-Y 所示"与实际图表编号一致）
- [ ] 各章草稿合并为完整 Markdown 终稿（`research/drafts/final-report.md`）
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
python scripts/contract_check.py research/drafts/final-report.md --merged
```

`--merged` 模式下 C1 允许恰好 1 个 H1；若 > 1 则说明分章 H1 未清理干净，回到上一步替换为 H2。

## 9.2 自动导出标准 Word 文档（.docx）——必须执行

**研究报告的最终交付物必须是格式规范的 Word 文档。本阶段自动执行，不需要用户单独要求。**

> **⚠️ 转换器重建中（2026-07-20起）**：原 `scripts/markdown_to_docx.py`（及 `scripts/md2docx/` 包）因存在 FIGURE_MAP 硬编码缺陷（换报告后图表静默丢失嵌入）已被删除。新版转换器（v2）的完整设计方案见 [`design/md-to-docx-design-v2/00-master-design.md`](../design/md-to-docx-design-v2/00-master-design.md)，已通过用户审批，实现阶段完成前，本节下方的 CLI 调用示例与"脚本自动完成的全部处理"表格暂保留作为**目标行为规格**参考，具体参数名/入口文件路径以实现完成后的实际代码为准，届时本节将同步更新为准确的调用方式。

**格式标准**：严格遵循 [`references/研究报告格式规范.md`](研究报告格式规范.md)（V3.1，遨天科技编制），该规范涵盖了文档全生命周期的格式要求：
- 文档结构（封面/摘要/目录/正文/参考文献/附录）
- 页面布局（A4、左边距 3.17cm、右边距 2.54cm、1.5 倍行距、首行缩进 2 字符）
- 字体与标题体系（标题 微软雅黑/Times New Roman、正文 宋体/Times New Roman；H1 24pt/H2 16pt/H3 14pt/正文 11pt）
- 图表编号系统（图 X-Y / 表 X-Y，章内序号）
- 表格规范（全框线含竖线、1.5pt 顶底线、交替行灰底 #F2F2F2、表头 10pt 微软雅黑加粗）
- 页眉页脚（页眉右对齐含 1pt 黑色底线、摘要罗马数字页码、正文阿拉伯数字页码）
- 封面设计、参考文献格式（GB/T 7714 适配版 + 信源分级 A/B/C/D，与阶段2.1通用标准一致）、特殊元素（定义框/案例框/趋势提示）
- Word 技术实现规范（TOC 域、多级列表、交叉引用、样式继承）
- 输出检查清单（12 项，§10.3）

使用本 skill 内置的一体化转换脚本（整合了 Markdown 清理、Word 生成、图片嵌入、表题注匹配；**参数名为目标规格，实现完成后以实际代码为准**）：

```bash
python -m md2docx \
  research/drafts/final-report.md \
  output/报告题名_v1.0.docx \
  --title "报告题名" \
  --images research/figures \
  --cover research/cover.md
```

**脚本自动完成的全部处理**：

| 处理阶段 | 内容 |
|---------|------|
| **Markdown 清理** | 二进制安全读取（自动处理 BOM / CRLF / 嵌入 CR）、剥离手动标题编号（兼容带编号/不带编号两种输入）、删除 HTML div 标签、删除"图表占位"标记、删除"建议印刷页数"行、删除 TOC 指示文字、删除封面元数据、删除"全文完"、删除孤立表引用、剥离列表图引用前缀、清理阶段8红队过程标记（`[红队 RXXX 已改写/已补证据]`）|
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
- [ ] 文末参考文献完整，含信源分级标注

🔴 CHECKPOINT · 🛑 STOP：全部 12 项交付清单确认通过后，报告正式定稿。任一项未通过 → 对照症状回到对应阶段修复（封面/字体 → 阶段9 整合；编号/图表 → 阶段7 写作；表格/页码/页眉 → 重新运行阶段9 转换脚本）。
