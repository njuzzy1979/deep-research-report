# Markdown → Word (.docx) 转换踩坑记录与修复方案

本文档记录了在多次实践中发现并修复的全部问题，作为转换脚本的设计参考。

## 数据管道架构（正确版）

```
原始Markdown（可能有BOM、混合行尾、HTML标签、手动编号）
  │
  ├─ 二进制读取 → strip BOM → CRLF→LF → standalone CR→LF
  ├─ 正则清理：HTML divs、图表占位、印刷页数建议、TOC指示文字、封面元数据、全文完
  ├─ 剥离H1/H2/H3手动编号（转换器自动添加"第一章 / 1.1 / 1.1.1"）
  ├─ 剥离列表形式的图引用（- 图X-Y：... → 图X-Y：...）
  ├─ 删除孤立表引用（无实际Markdown表格跟随的表X-Y行）
  ├─ 删除所有 --- 分隔线
  ├─ 插入 --- 分页标记（目录前/证据等级前/每章前/附录前）
  ├─ 英文副标题转换为H2
  ├─ 目录→H1、摘要→H2
  │  ↓ 二进制写入(LF only)
清理后Markdown
  │
  ├─ parse_markdown → 元素列表
  ├─ 封面（add_cover_page）: 中文标题26pt + 英文副标题15pt灰色 + 分隔线 + 编制信息
  ├─ --- → doc.add_page_break()
  ├─ 目录H1 → add_toc_field (begin → instrText → separate → end)
  ├─ 各章H1 → 自动编号"第一章 / 1.1 / 1.1.1"
  ├─ 表格 → 检测表头内容 → 匹配题注 → 表题注在上方居中(黑体加粗12pt)
  ├─ 图片嵌入 → 图题注在下方居中(楷体10.5pt)
  ├─ 表体文字五号(10.5pt)
  │  ↓
最终.docx
```

---

## 全部已修复问题清单

### 问题1：章节标题被截断（"第一章  导"）

**症状**：`第一章  导论与研究方法` 变成 `第一章  导`

**根因**：PowerShell 编译 `final-report.md` 时在中文 UTF-8 字节流中嵌入 `0d`（CR）字符，且出现在行中间而非行末。即使使用 `utf-8-sig` 读取、`replace('\r','')` 处理，text mode 的 `writelines()` 在 Windows 上会重新插入 `\r\n`，导致正则 `^(#\s+)第` 只匹配到 CR 前的"第一章："部分，剥离后标题只剩"导"。

**修复**：
- 二进制读取：`raw = f.read(); raw = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')`
- 二进制写入：`f.write(result.encode('utf-8'))`（避免 Windows text mode 的 `\n→\r\n` 转换）

### 问题2：目录TOC域无法"更新域"

**症状**：Word 中右键目录 → "更新域" 无效

**根因**：Word 的 TOC 域要求严格的三态结构 `begin → instrText → separate → (result) → end`。缺少 `separate` 则 Word 不识别为域。

**修复**：
```python
fldChar_sep = OxmlElement('w:fldChar')
fldChar_sep.set(qn('w:fldCharType'), 'separate')
```
同时 `instrText.text` 不能有前导空格：`'TOC \\o "1-3" \\h \\z'` 而非 `' TOC ...'`

### 问题3：分页符过多/章节内分页

**症状**：章节内部出现多余分页符

**根因**：多次修改过程中，分页逻辑分散在多处：
- H1 段落 → `doc.add_page_break()`（转换器主循环）
- `add_back_matter_h1()` → `doc.add_page_break()`
- `---` 水平线 → `doc.add_page_break()`
- 封面 → `doc.add_page_break()`

导致同一位置触发2-3次分页。

**修复**：**统一分页控制——仅 `---` 触发分页。**
- 转换器主循环：`isinstance(HorizontalRule) → doc.add_page_break()`
- H1 段落：**不触发分页**
- `add_back_matter_h1`：移除 `doc.add_page_break()`
- 封面：保留 `doc.add_page_break()`
- 清理脚本：仅在12个正确位置插入 `---`

### 问题4：标题编号重复（"第一章  第一章：导论"）

**症状**：`# 第一章：导论与研究方法` 渲染为 `第一章  第一章：导论与研究方法`

**根因**：Markdown 手动编号 + 转换器 `add_h1()` 自动加编号

**修复**：清理脚本剥离所有 H1/H2/H3 的手动编号：
```python
RE_H1_CH = re.compile(r'^(#\s+)第' + CN + r'章[：:]\s*')
line = m.group(1) + line[m.end():]  # '# 导论与研究方法'
```

### 问题5：HTML标签残留（`<div style='page-break...'>`）

**症状**：文档中出现原始 HTML 标签文本

**根因**：`final-report.md` 合并时用 PowerShell 插入的 `<div>` 分页标签，转换器不解析 HTML

**修复**：清理脚本正则匹配并删行

### 问题6：图表占位符未替换

**症状**：文档中出现 `**图表占位**：图1-1：...` 文本

**根因**：Markdown 粗体包裹的占位文本

**修复**：`RE_CHART = re.compile(r'\*{0,2}图表占位\*{0,2}[：:]\s*')`

### 问题7：建议印刷页数未删除

**症状**：`（第一章完，建议印刷页数：8页）` 残留在文档中

**修复**：`RE_PAGE = re.compile(r'^[（(](?:第...章完|摘要完)[，,]建议印刷页数[：:]\s*\d+\s*页[）)]\s*$')`

### 问题8：图题重复/图题与内容不对应

**症状**：同一张图有2-3个重复题注，或"图2-1"显示的是雷达图

**根因**：
- `embed_images.py` 的 Phase 3 清理逻辑把刚嵌入的题注也删了（正则匹配到 `图X-Y：`）
- `fix_captions.py` 用数字顺序分配 `FIG_CAPS` 列表，但文档中图片的实际顺序不同
- 列表形式的图引用（`- 图2-1：...`）未被清理脚本处理

**修复**：
- `embed_images.py` Phase 3：仅删除不在图片/题注相邻位置的孤立引用，保留题注
- `fix_captions.py`：不再手动添加图题注（embed_images 已处理）
- 清理脚本：新增 `RE_LIST_FIG` 剥离列表前缀（`- 图X-Y：... → 图X-Y：...`）

### 问题9：表题注全部错误

**症状**：表题注用的是顺序硬编码列表，完全不对应表格内容

**根因**：`fix_captions.py` 用 `TBL_CAPS[tbl_idx]` 顺序分配，不看表格内容

**修复**：基于**表头内容正则匹配**：
```python
TABLE_MATCHERS = [
    (r'术语.*英文全称.*核心含义',  '表1-1：SSA/SDA/STM概念辨析'),
    (r'区域.*市场规模.*占比.*增长率', '表2-1：全球SSA市场区域分布'),
    ...
]
matched = False
for pattern, caption in TABLE_MATCHERS:
    if pattern.search(header_text):
        caption_text = caption
        matched = True
        break
```

### 问题10：证据等级说明——不再产生此内容

**历史症状**：旧版报告在目录后生成独立的 H2"证据等级说明"节，向读者解释 A/B/C/D 信源分级体系，该节需要独立起页。

**根因与修正**：按 Standard 0（前台/后台分离），信源分级属于内部质量控制，读者不应看到。该独立节不再由 `chapter_writer_agent` 生成。清理脚本中 `## 证据等级说明` 前的 `---` 插入规则保留，作为处理遗留报告数据的兜底（若旧版 md 文件仍有此节，转换器仍能正确分页），但新生成的报告不应出现此内容（详见 `references/研究报告格式规范.md` V3.2 变更记录和 `references/writing-standards.md` 标准 0 新增的参考文献分级标注反例）。

### 问题11：首章未从新页开始

**症状**：第一章"导论与研究方法"紧贴前一页内容

**根因**：`first_chapter` 标志跳过了首章分页

**修复**：移除 `first_chapter` 标志，所有章统一通过 `---` 触发分页

### 问题12：封面排版设计不足

**症状**：封面只有标题一行，缺乏编制单位、日期等信息

**修复**：新增 `add_cover_page()` 函数：
- 顶部留白6行
- 中文标题 26pt 黑体居中
- 英文副标题 15pt Arial 灰色
- 分隔线 `━━`
- 编制单位 / 日期 / 版本 三行居中对齐（已移除密级，依据 V3.0 §一 严禁标密规则）

### 问题13：表体文字过大

**症状**：表体文字为 12pt（小四），规范要求 10.5pt（五号）

**修复**：`set_run_font(run, FONT_CJK_BODY, FONT_LATIN_BODY, SIZE_SMALL)` 替代 `SIZE_BODY`

### 问题14：MetaLine 误判导致正文静默丢失

**症状**：分章正文中以加粗标签开头的普通段落（如 `**创新内容**：本项目在……方面实现了突破`）在转换后从文档中消失，且转换脚本不报错、不留痕迹——只有逐段比对原文与产出才能发现丢字。

**根因**：`textstage/parse.py` 的 `_RX_META` 元数据行识别窗口原本设定为"H1 之后、第一个 `---` 之前"，窗口范围过宽。正文中出现的加粗标签段落（如立项报告的"创新内容"小节）恰好落在这个窗口内，被正则误判为封面/前置元数据行（MetaLine），随后被 `assemble/builder.py` 当作已消费的元数据静默丢弃，不生成任何段落节点。

**修复**：
- `textstage/parse.py`：新增 `meta_window_closed` 标志，在遇到 H1 之后第一个"非空白、非元数据格式"的行时立即关闭元数据识别窗口，此后的加粗标签段落不再被误判
- `assemble/builder.py`：对未被识别为已知元数据键的 MetaLine，不再静默丢弃，而是降级还原为普通段落节点，保证内容不丢失（即便窗口收窄仍有漏判，也有兜底）
- `assemble/metadata.py`：新增诊断信息收集，记录被识别/降级的元数据行清单，供转换报告核查

### 问题15：门3章节连续性检查的"空真值陷阱"导致假通过

**症状**：分章文件普遍缺失 H2 章容器标题（即问题1的结构缺陷）时，门3（`gate3.py`）的章节连续性校验没有报错，转换流程"顺利"生成了 docx，直到人工目视检查才发现标题编号退化为扁平的"0.1～0.57"格式。

**根因**：Python 中 `all(x is None for x in [])` 对空列表返回 `True`。原始校验逻辑先收集"手动编号的章节序号"列表，再对该列表做"是否连续"判断；当全部章节都没有 H2 容器（即列表本身为空，而非"值为 None"）时，空列表触发了"无手动编号，属于正常情况，跳过校验"的分支，而不是触发"结构性缺失，应报错"的分支——两种"没有编号"的语义（真的没写章级标题 vs. 写了但都不带手动编号）被同一段代码混为一谈。

**修复**：
- `assemble/headings.py::_check_chapter_continuity()`：显式区分 `orig_nums`（收集到的原始编号列表）为空列表（结构性缺失 → ERROR）与列表非空但全部为 `None`（正常场景：故意不使用手动编号 → 静默跳过）两种情况
- `gate3.py::_check_heading_continuity()`：在做逐类型连续性检查之前，先判断 `chapters` 集合本身是否为空，为空时直接产出 `W-HDR-01` 级别 ERROR，不再进入后续可能被空列表短路的检查分支

### 问题16：引号未转换为中文全角弯引号

**症状**：正文中残留西文直引号 `"`（U+0022），与《研究报告格式规范》V3.1 要求的中文全角弯引号 `"`/`"` 不一致，人工逐处替换成本高且容易漏改嵌套引号。

**根因**：现有清理规则表（R-03～R-11）未覆盖引号转换；直接用无状态的全局替换（如"所有 `"` 都换成 `"`）无法处理引号的开合语义——同一个字符在不同位置应转换为不同的全角符号，需要按上下文动态判断当前处于"开引号待闭合"还是"闭引号后待新开"状态。

**修复现状**：**已实现（R-13）**。`textstage/clean.py` 新增有状态清理规则 R-13（`_convert_quotes_stateful()`），逐字符扫描正文，维护"当前是否处于引号内"的布尔状态，按开合位置将直引号动态映射为 `"`（开）/`"`（合）；围栏代码块/行内代码内的引号豁免不转换；全文扫描结束仍处于"引号内"状态时输出未闭合警告（供人工复核）。已通过自检测试覆盖跨行配对、未闭合警告、围栏代码块豁免三类边界场景。

`final-report.md` 实测复盘：R-13 落地后转换报告曾报出 1 处 `W-CLN-05`（引号未闭合）警告，经逐行奇偶性状态机扫描定位到源文档第 1685 行——三个并列引号短语中第二个短语漏写了开引号，属于写作层面的真实疏漏，而非 R-13 算法边界处理缺陷。修复该处写作疏漏（补全缺失的开引号）后，全文引号奇偶性归零，`W-CLN-05` 警告消失，证实 R-13 算法本身逻辑正确。

### 问题17：写作/审校过程批注块残留正文（区别于问题2/14的"整块残留"）

**症状**：终稿正文中出现形如 `> [红队 R012 已改写]` 或 `> [阶段9 审校：已核实数据来源]` 的引用块（Markdown blockquote），整段独立成块，不像问题14那样是"一整段内容被误判丢失"，而是"协作过程的批注本身被当作正文内容保留了下来"。

**根因**：与问题2（写作者自声明残留）同属"工作流协作元数据混入最终交付物"的根因家族，但**残留形态不同**：写作者自声明是"标题级"整块（`### 写作者自声明（第 X 章）`及其下方内容），本问题是"引用块级"独立批注（以 `>` 起始、无标题、散落在正文各处，数量可能有 5-10 处之多）。现有清理规则表中的 R-06a 只处理**行内**红队标记（嵌在正文句子中间的 `[红队 RXXX ...]` 片段），未覆盖**独立成块**的引用块形态，两种形态需要不同的正则/解析策略（行内片段删除 vs. 整块删除）。

**修复现状**：**已实现（R-14）**。`textstage/clean.py` 新增清理规则 R-14，识别以 `> [红队 R\d+...]` 或 `> [阶段9...]` 开头的 blockquote 块并整块删除，作为 `finalizer_agent` 合并阶段主动剥离（主防线，见 `stage-9-finalize.md` §9.1）之外的兜底防线（次防线），已通过自检测试确认不会误伤正文中的正常引用块。`final-report.md` 实测转换报告确认该类批注块残留检查为 0 处。

### 问题18：三层编号体系全部硬编码为静态文本，未使用 Word 原生动态编号机制

**症状**：章节编号（"第一章/1.1/1.1.1"）、图表编号（"图 3-2""表 3-2"）、正文交叉引用（"如图 3-2 所示"）三类编号在 docx 中均以**字面文本**形式写入，不是 Word 原生的动态编号域。后果：报告中途插入/删除/调换任意一章、一图或一表，其后所有编号需要全篇人工重新核对，转换脚本无法通过"更新域"自动重排；交叉引用一旦对应的图表编号发生偏移，正文引用文字不会跟着变化，容易产生"如图 3-2 所示"但实际该图已变成"图 3-3"的错配。

**根因**：`render/headings.py`（章节编号）、`render/figures.py` 与 `render/tables.py`（图表题注编号）、`render/paragraphs.py`（正文交叉引用文字）四处渲染代码在最初实现时均直接拼接编号字符串写入段落文本，未接入 OOXML 原生的 `w:numPr`（多级列表编号）、`SEQ` 域（图表自动编号）、`REF` 域（交叉引用自动跟随）机制。这是一种"看起来能用就没人质疑底层机制"的架构级技术债——手动拼接的编号在**首次生成时**结果正确，缺陷只在后续编辑、章节重排时才暴露，因此长期未被发现。`gate3.py::_check_figure_table_continuity()` 现有校验逻辑也只是比对字面编号序列有无跳号（`if seq != expected`），属于"数值层面查漏"，未校验编号是否真正绑定在动态域机制上。

**修复现状**：**部分完成，正文交叉引用（REF 域）尚未接入**：
- 章节编号：**已实现**。`render/numbering.py` 定义了 `w:abstractNum`/`w:num` 多级列表，`render/styles.py` 将 Heading 1~3 样式绑定统一 `numId`（三级共享同一计数器），`render/headings.py` 不再拼接 `display_number` 文本，改为对标题段落设置 `w:numPr`（`w:ilvl`+`w:numId`），并在测试阶段断言三级标题样式均已正确绑定 `numPr`
- 图表编号：**已实现**。`render/figures.py`/`render/tables.py` 新增 `caption_field_mode="field"` 开关，开启后题注编号由 `SEQ 图 \* ARABIC`/`SEQ 表 \* ARABIC` 域生成（通过 `oxml_helpers.make_field()`），不再是静态拼接数字；`final-report.md` 实测转换命令已默认传入 `--caption-field-mode field`
- 正文交叉引用：**尚未开始**。`render/paragraphs.py` 尚未接入 `REF` 域机制，正文中"如图 X-Y 所示"仍是字面文本，`validate.py::xref_registry` 目前只在校验阶段填充（供 W-REF-01/02/04 等警告使用），尚未被渲染阶段消费为域替换指令
- 校验策略：`gate3.py::_check_figure_table_continuity()` 已做部分结构性调整——对不参与编号体系的哨兵值（`chapter_no==0` 的未编号图）不再强行套入连续性假设而是整组排除，但对真正参与编号的图表仍是"数值跳号比对"（`if seq != expected`），**尚未**升级为直接校验 `SEQ`/`numPr` 域本身是否正确挂载的"纯结构性存在检查"
- 详见 `references/writing-process-pitfalls.md` 问题6（该问题的完整根因链与工作流层面影响）

### 问题19：SEQ/PAGEREF 域缓存值为空，Word 打开时图表编号显示空白（问题18 图表编号"已实现"后的遗留缺陷）

**症状**：问题18将图表编号切换为 `SEQ` 域后，实测生成的 docx 用 Word 打开，图/表编号处显示为空白（而非正确数字），需要用户手动全选正文按 F9 才能看到编号——对普通用户而言等同于"编号是空的"这一可见故障。

**根因**：OOXML 域的四态结构 `begin → instrText → separate → end` 中，`separate` 与 `end` 之间的内容是域的**缓存显示值**，Word 在未执行"更新域"操作前直接显示这段缓存内容；若该区间为空（没有任何 `w:t` 文本节点），显示效果就是空白。`oxml_helpers.py::make_field()` 最初实现只生成了 `begin/instrText/separate/end` 四个 fldChar 标记本身，从未在 `separate` 和 `end` 之间插入任何占位文本——这一缺口在文件内早有先例：`render/toc.py::_add_field_with_placeholder()`（PAGEREF 域，图表目录页码）已经实现了"插入占位文本"的正确模式，但从未被抽取为 `oxml_helpers.py` 的通用能力，也未被 `render/figures.py`/`render/tables.py` 的 SEQ 域调用点复用，导致同一模块内"同一类问题、一部分点已修、一部分点未修"。

**修复现状**：**已实现**。
- `oxml_helpers.py::make_field()` 新增可选参数 `placeholder_text`，提供时在 `separate` 与 `end` 之间插入对应的 `w:t` 文本节点作为域缓存显示值。
- `render/figures.py` 调用 SEQ 域时传入 `placeholder_text=str(bookmark_id)`——`bookmark_id` 是模块级全局自增计数器（每渲染一张图 +1），其取值序列与 Word 实际计算 `SEQ 图 \* ARABIC` 域时的全局递增序列语义一致（**注意**：不能用 `figure.seq_no`，后者是章节内相对序号，会在多章场景下产生跨章重复值，与 SEQ 域的全篇累加语义不符）。
- `render/tables.py` 调用 SEQ 域时传入 `placeholder_text=str(bm_id + 1)`——`bm_id` 是仅正文表消费的全局书签计数器（0-based，+1 转 1-based），语义与 figures.py 对称。
- `render/document.py::render_document()` 新增 `set_update_fields_on_open()` 调用（写入 `settings.xml` 的 `w:updateFields`），作为双保险：即使占位符因未来某处遗漏而不准确，Word 打开文档时也会自动触发一次全局域更新，用真实计算值覆盖占位符。
- 实测验证：用修复后代码重新生成 `final-report.md` 对应 docx，解析 `document.xml` 确认 8 个 `SEQ 图` 域缓存值为连续的 `1`～`8`，11 个 `SEQ 表` 域缓存值为连续的 `1`～`11`，`settings.xml` 中 `w:updateFields` 已正确写入；`render/figures.py` 自检新增覆盖 `caption_field_mode="field"` 路径的用例（验证 SEQ 域占位符非空且为连续递增整数）。
- **已确认不受影响的范围**：章节标题编号（`w:numPr` 多级列表机制）不是 `fldChar` 域，不存在"缓存值为空"这一失效模式，问题18的章节编号部分未受此缺陷影响。
- **已知遗留、非本次范围**：图表目录（TOC 附属的 `PAGEREF fig_x_y`/`PAGEREF tbl_x_y`）域缓存值仍为空格占位符——页码在渲染阶段确实无法预先算出（不同于 SEQ 域可以用全局计数器精确复现），只能依赖 `w:updateFields` 这一道防线，Word 打开时会自动补齐；这与本次用户报告的"图/表编号空白"是不同的域，不在本次修复范围内。

---

### 问题20：全角弯引号字符字体错误地继承 Times New Roman（西文字体），而非中文正文字体

**症状**：docx 正文中的全角弯引号（`"` U+201C / `"` U+201D，问题16 R-13 规则转换产出）渲染字体为 Times New Roman，与其前后的中文正文字符（宋体/微软雅黑等，视所在区域而定）不一致——引号在视觉上比周围中文字符明显偏窄、字形不协调。用户要求"只改双引号字体为宋体，不改动其他任何字体定义"。

**根因**：OOXML 的 `w:rFonts` 元素通过 `w:ascii`（默认西文字体）/`w:eastAsia`（中文字体）/`w:hAnsi`/`w:cs` 四个属性分别控制不同 Unicode 范围字符的字体渲染。全角弯引号字符（U+201C/U+201D）在 Unicode 分类上不落在 CJK 表意文字范围内，Word 按字符属性判定其应使用 `w:ascii`/`w:hAnsi` 指定的西文字体渲染，而非 `w:eastAsia` 指定的中文字体——即便该 run 与周围中文文字同属一个 `<w:r>`。转换器全篇渲染模块（`render/paragraphs.py`、`tables.py`、`lists.py`、`special.py`、`figures.py`、`headings.py`、`toc.py`、`cover.py`、`headerfooter.py` 等）在设置 run 字体时，只在少数位置显式设置了 `w:eastAsia`（中文字体），`w:ascii`/`w:hAnsi` 普遍留空或继承 Normal 样式的默认值（Times New Roman），导致同一个 run 内如果同时含中文字符与引号字符，中文部分正确显示中文字体，引号部分却回退到西文默认字体——这一失效模式与 R-13（问题16）引入的引号全角化改动是独立的两层问题：R-13 只负责把字符从直引号换成全角弯引号，不涉及字体渲染层面的 ascii/eastAsia 分离。

**修复**：
- 新增 `oxml_helpers.py::add_run_segments(paragraph, text, apply_format=None)` 通用辅助函数：按引号字符（`"`/`"`）与非引号字符把输入文本拆分为多个 segment，逐 segment 创建独立的 `<w:r>`，对引号 segment 额外设置 `w:rFonts` 的 `w:ascii`/`w:hAnsi`（以及为兼容部分 Word/WPS 版本对复杂脚本判定，同步设置 `w:cs`）为"宋体"；`apply_format` 回调参数允许调用方在拆分后仍然对每个 run 应用原有的字号/颜色/加粗等格式（回调签名 `(run, is_quote) -> None`），从而保证"只改字体、不改除字体外的其他 run 级属性"。
- 全篇渲染模块中所有原本直接调用 `paragraph.add_run(text)`/`cell.add_run(text)` 拼接可能含引号字符文本的位置，改为调用 `add_run_segments()`（含 `render/toc.py` 中硬编码的更新提示文案 `hint_text`、图表目录标签、`cover.py` 封面各段落文本、`headerfooter.py` 页眉报告简称等此前遗漏排查的位置）。
- 未改动任何其他字体/字号/颜色/加粗等既有格式设置逻辑——`add_run_segments()` 的默认格式回调仅负责透传原有格式，字体覆盖只针对引号 segment 生效。
- **实测验证**：重新生成 `final-report.md` 对应生产 docx（`output/*_v1.0.docx`），解析 `document.xml` 统计：4508 个"纯引号字符"run（长度≤3且含全角引号）全部 `w:ascii == w:hAnsi == "宋体"`；842 处不含引号的普通 run 仍保留原有 `Times New Roman`（证明非引号文本字体定义未被误改）；全文直引号（U+0022）残留计数为 0，全角左/右引号计数均为 2254（配对一致）。门3（gate3）12 项检查全部通过，无新增 WARNING/ERROR。

---

## 关键设计决策

### 1. 分页符统一由 `---` 控制

**原则**：只有清理脚本插入的 `---` 触发分页，转换器中其他任何地方不触发分页（封面除外）。

### 2. 二进制安全的数据管道

**原则**：所有文件读写使用二进制模式（`'rb'`/`'wb'`），中间处理 `\n` 分隔，仅在最终输出时 encode。

### 3. 图片题注由 embed_images 负责，表题注由 fix_captions 负责

**原则**：
- 图片：`embed_images.py` 知道图ID→文件映射，天然知道正确题注
- 表格：`fix_captions.py` 通过表头内容匹配题注，不依赖顺序

### 4. 标题编号由转换器负责，不依赖 Markdown 手工编号

**原则**：清理脚本剥离所有手工编号，转换器 `add_h1/h2/h3` 统一添加"第一章 / 1.1 / 1.1.1"。

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `scripts/markdown_to_docx.py` | 主转换器：清理 + 转换 + 图片嵌入 + 表题注修复 |
| `references/word-format-spec.md` | Word 文档格式规范（字体/字号/行距/标题体系） |
| `SKILL.md` | 阶段9：定稿整合——自动导出 Word 文档 |
