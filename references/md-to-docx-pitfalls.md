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

### 问题10：证据等级说明未独立起页

**症状**：证据等级说明跟在目录页面后面，不是新的一页

**修复**：清理脚本在 `## 证据等级说明` 前插入 `---`

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
