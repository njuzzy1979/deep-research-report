# D1：标题体系修复方案（P0）

> **本文档性质：设计稿，尚未执行。不涉及对本次 SCIF 报告产出的修复。skill 源文件未被改动。**
> 上级文档：`skill优化方案-总览与执行清单.md`

---

## 一、用户可见现象与技术链路

**用户反馈**："最后生成的报告居然有些章节都是空的。"

在 Word 导航窗格点开"第 1 章"，正文区一片空白；而紧挨着的"本章结论"下面却有几千字。

**实测证据**（python-docx 读取 `research/drafts/final-report.docx` 的 140 个标题）：13 章全部呈现同一模式——

```
第X章《标题》     Heading 1，紧随其后 0 字符
本章结论          Heading 1，携带数百至数千字正文
```

所有正文被错误"过继"给了章内第一个小节标题，而不是挂在真正的章标题下。

---

## 二、故障链路完整还原

| 环节 | 组件 | 行为 | 是否失效 |
|---|---|---|---|
| ① 写作 | `stage-7-writing.md` R1 红线 | 强制每章草稿第一个 H2 逐字为 `## 本章结论` | 符合自身契约 |
| ② 合并 | `merge_drafts.assemble_merged()` `:250` | 插入 `## 第 {c_no} 章：{c_title}` 作为章容器（**同为 H2**） | 符合自身契约 |
| ③ — | — | **产出「两个相邻 H2」**：`## 第1章：导论` 紧接 `## 本章结论` | ← 断层产生处 |
| ④ 键名 | 真实 `outline.md` 用 `section_no`/`section_title`/`subsections` | 与 schema 权威键名 `chapter_no`/`chapter_title`/`sections` 不符 | **失效** |
| ⑤ 白名单 | `outline_reader._build_structure_lookup()` | 按 schema 读 `chapter_no` → 全部落空，**lookup size = 0** | 被④拖垮 |
| ⑥ 静默 | `headings.py:482` `if not lookup: return results` | 直接返回，三个诊断码永不触发 | **失效且无声** |
| ⑦ 分类 | `classify_and_number()` h.level==2 分支 | 无白名单可依，纯文本 H2 一律 default → `HeadingKind.CHAPTER` | 连带失效 |
| ⑧ 渲染 | `builder.py` → docx | 两个 H2 都成 Heading 1，正文归属第二个 | 最终现象 |

**关键认知**：链路上每个组件单独看都符合自己的契约，**从未有任何测试跑过完整链路**。

---

## 三、【核心】键名契约定案

### 3.1 schema 是权威，`outline_reader.py` 是无辜的

主控实测 `schemas/outline-structure.schema.json`：

```
/properties/structure/properties/bodymatter/items  required = ['chapter_no', 'chapter_title']
/properties/structure/properties/appendix/items    required = ['appendix_letter', 'appendix_title']
顶层                                                required = ['struct_template', 'title', 'structure']
```

**定案**：
- `outline_reader._build_structure_lookup()` 按 `chapter_no` 读取，**完全符合权威契约，本体无缺陷，不得修改其字段读取语义**。
- 违规方有两个：**产出端**（真实 `outline.md` 写成 `section_no`）与**适配层**（`finalize_pipeline.py:191-204` 照着不合规输入反向硬编码）。

> 主控此前曾误判"白名单读错键名"，schema 实测后已纠正。此处记录以防实施者沿用错误判断。

### 3.2 适配层是"修好上游反而崩溃"的反模式

`finalize_pipeline.py:191-204` 现状：

```python
for item in structure.get("bodymatter", []):
    item["chapter_no"] = int(item.get("section_no", "?"))   # ← 合规输入时 get 返回 "?" → int("?") → ValueError
    item["chapter_title"] = item.get("section_title", "")
    if item.get("subsections"):
        item["sections"] = item["subsections"]              # ← 字段名错配，见 3.4
    else:
        item["sections"] = [{"section_no": str(item["chapter_no"]), "section_title": item["chapter_title"]}]
```

三个缺陷：
1. **对合规输入必崩**——已含 `chapter_no` 而无 `section_no` 时，`int("?")` 抛 ValueError。
2. **就地 mutate**，且适配结果**只喂给 `assemble_merged`，没有流到 md2docx 的 lookup**——所以白名单空转在本次运行中依然发生。
3. **`sections` 与 `subsections` 字段名错配**（见 3.4）。

### 3.3 现网已有 4 个红灯（实测）

```
$ python -m pytest tests/test_finalize_pipeline.py -q
4 failed, 13 passed
AssertionError: 实际 failure_step=merge，已执行步骤=['strip_markers','h1_check','merge']
invalid literal for int() with base 10: '?'
```

`int("?")` 不是理论风险，是**当前就在红的测试**。修复后应转 **17 passed**——这是本方案最强的验收信号。

### 3.4 比"标题为空"严重得多：同一章正文重复拼接 N 遍

`merge_drafts.py:254-263` 消费 `sections` 元素时取 `section_no`/`section_title`；而适配层塞进去的是 `subsections`，其 schema 键为 `subsection_no`/`subsection_title` —— **取到空串**。

后果链：`find_draft_files(drafts_dir, c_no, "")` → 首个精确 glob 落空 → 回落到 `ch01-*.md` **章级通配符** → **同一章正文按 subsections 数量重复拼接 N 遍**。

这解释了事故的另一半现象。**验收必须加断言**：合并产物中每个 `ch{XX}-*.md` 的内容出现次数**恰为 1**。现有 4 个 failed 用例全部卡在 merge 之前，无一能捕获此 bug，仅断言"17 passed"不够。

### 3.5 实测：只修 `chapter_no` 不够

```
first chapter keys: ['section_no', 'section_title', 'pages', 'subsections']
has 'sections' key: False
subsections value: []
LOOKUP SIZE: 0
```

- lookup **整体 size = 0**，不只 CHAPTER 分支落空。
- `outline_reader.py:228` 的 SECTION 分支读 `ch.get("sections", [])`，真实 outline **无此键**，且 `subsections` 值为**空列表**。
- 即使修好 CHAPTER 键名，**SECTION 条目仍为 0**，113 个 H3 全走推断分类。

### 3.6 第四个消费端（补位设计新发现）

除 `outline_reader`、`merge_drafts`、`finalize_pipeline` 外，**`outline_title_extract.py:build_title_tree()` 是第四个消费端**，同样依赖 `structure.bodymatter[*].sections[*].section_title`。归一化若只覆盖三处仍有漏洞。

---

## 四、【核心】白名单修复 ≠ H2 兜底降级的替代方案

这是本次审计**最重要的一次纠正**。

发现层 A3 与设计层 D1 都主张"修白名单可一石二鸟"。审查层 R2 反对，主控亲自跑探针实测，**推翻该论断**：

```
LOOKUP after normalize: 13          ← 白名单确实修好了
by kind: {'CHAPTER': 13}
本章结论 count: 13
本章结论 kinds: {'CHAPTER'}          ← 仍然全部是 CHAPTER！
SAMPLE: [('本章结论','CHAPTER','第二章'), ('本章结论','CHAPTER','第四章')]
W-HDR-04 count: 126
```

**机理**：`apply_structure_overlay()` 语义是"**命中即覆盖，未命中只发 WARNING、不改分类**"（`headings.py:489-507`）。`## 本章结论` 不在 outline 里 → 未命中 → 保持推断的 `CHAPTER`，甚至继续占用章号。

**交叉印证**：补位设计 D1-bis 在独立路径上自行写出同一结论——"批次 1 落地后 `本章结论` 仍是 CHAPTER，批次 3（层级下沉）才真正消除"。两个独立来源互证。

> **结论：D1-1（白名单）与 D1-5（层级下沉）是并列的两个 P0。只修白名单，用户投诉不会消失。D1-5 是治愈用户投诉的关键单点。**

---

## 五、修复方案

### D1-0（P2）删除 `issues.py` 两条死码位

**问题**：`issues.py:100-101` 定义的 `W-HDR-04`/`W-HDR-05` 被 `:153`/`:159` 同名覆盖。Python dict 后者胜出，前者是死代码。

**方案**：删除 `:100-101` 两行。新增诊断码**不得复用**这两个码位。

**验证**：`python -c "from md2docx.issues import ISSUE_CODES; print(ISSUE_CODES['W-HDR-04'].message)"` 输出应与 `:153` 定义一致。

---

### D1-1（P0）键名归一化，贯通四个消费端

**选址**：`outline_reader.py` 新增**前置纯函数** `normalize_outline_structure(structure) -> structure`。

**设计原则**：
1. **按层级映射，不做全局替换**——`sections[*].section_no` 是合法的节编号，不能被误改。
2. **不改 `_build_structure_lookup` 本体的任何字段读取**——它符合权威契约。
3. **双向兼容**：权威键优先，缺失才回落旧键；回落事实写 notes 上报，**不静默接受**。

```python
def normalize_outline_structure(structure: dict) -> dict:
    """将旧键名 outline 归一化为 schema 权威键名（非破坏性，返回新 dict）。

    映射规则（按层级，非全局）：
      bodymatter[*]: section_no->chapter_no, section_title->chapter_title,
                     subsections->sections
      appendix[*]:   section_no->appendix_letter, section_title->appendix_title
      frontmatter[*]: section_title->chapter_title
    顶层 report_title->title 由调用方处理（不在 structure 节点内）。
    """
    if not isinstance(structure, dict):
        return structure
    out = {k: v for k, v in structure.items()}

    body = []
    for ch in structure.get("bodymatter", []) or []:
        if not isinstance(ch, dict):
            continue
        c = dict(ch)
        if "chapter_no" not in c and "section_no" in c:
            c["chapter_no"] = _coerce_chapter_no(c.get("section_no"))
        if "chapter_title" not in c and "section_title" in c:
            c["chapter_title"] = c.get("section_title", "")
        if "sections" not in c:
            c["sections"] = c.get("subsections") or []
        body.append(c)
    out["bodymatter"] = body

    apx = []
    for a in structure.get("appendix", []) or []:
        if not isinstance(a, dict):
            continue
        x = dict(a)
        if "appendix_letter" not in x and "section_no" in x:
            x["appendix_letter"] = str(x.get("section_no", "")).strip()
        if "appendix_title" not in x and "section_title" in x:
            x["appendix_title"] = x.get("section_title", "")
        apx.append(x)
    out["appendix"] = apx

    front = []
    for f in structure.get("frontmatter", []) or []:
        if not isinstance(f, dict):
            continue
        y = dict(f)
        if "chapter_title" not in y and "section_title" in y:
            y["chapter_title"] = y.get("section_title", "")
        y.setdefault("sections", y.get("subsections") or [])
        front.append(y)
    out["frontmatter"] = front
    return out


def _coerce_chapter_no(raw) -> int:
    """把 '1' / '1.0' / 1 / '0.1' 等安全转为 int；不可解析返回 0（不抛异常）。"""
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).strip().split(".")[0])
    except (ValueError, AttributeError):
        return 0
```

**五个调用点**：

| # | 文件 | 位置 | 说明 |
|---|---|---|---|
| 1 | `outline_reader.py` | `_build_structure_lookup()` 入口 | md2docx 主路径 |
| 2 | `outline_reader.py` | `build_structure_manifest()` 入口 | md2docx 台账路径 |
| 3 | `merge_drafts.py` | `parse_outline_yaml()` 返回前 | **同时覆盖 CLI 路径与 finalize_pipeline 导入路径** |
| 4 | `outline_title_extract.py` | `build_title_tree()` 入口 | 第四消费端 |
| 5 | 顶层题名 | `report_title` → `title` | 不在 structure 节点内，调用方处理 |

**同步删除** `finalize_pipeline.py:191-204` 的就地 mutate（改为依赖调用点 3）。**不这么做两处适配必然漂移。**

**同步修正** `finalize_pipeline.py:210` 的误导文案：现为"outline.md **解析**异常"，而 `int("?")` 崩在 `:192` 被 `:210` 捕获——用户看到只会去改 outline，但缺陷在脚本。改为区分"outline 解析失败"与"键名适配失败"。

**验证**：
- `pytest tests/test_finalize_pipeline.py` 从 **4 failed** 转 **17 passed**
- 断言合并产物中各 `ch{XX}-*.md` 内容出现次数**恰为 1**
- `test_structured_fixture.py` 已用权威键名，归一化应为**恒等变换**——现成的幂等性回归证据

---

### D1-2（P0）修复静默失效

**问题**：`headings.py:482` `if not lookup: return results` 无声返回，三个诊断码永不触发。

**方案**：区分两种情形——

```python
if not lookup:
    declared = _count_declared_entries(structure)   # 统计 structure 中声明的条目总数
    if declared > 0:
        issues.append(Issue(
            level=Level.ERROR, code="E-OL-03", stage="assemble",
            message=(f"outline 声明了 {declared} 个结构条目，但展平后查找表为空——"
                     f"键名契约不匹配，结构注入已失效"),
            suggestion="检查 outline.md 是否使用 schema 权威键名（chapter_no/chapter_title/sections）",
        ))
        record_degradation(...)   # 写降级台账
    else:
        issues.append(Issue(
            level=Level.INFO, code="I-OL-04", stage="assemble",
            message="outline 未声明结构条目，跳过结构注入（合理场景）",
        ))
    return results
```

**新码位说明**：使用 `E-OL-03`（ERROR）/ `I-OL-04`（INFO）**全新码位**，不复用 D1-0 中删除的死码位。

**实施注意**：`headings.py` 当前**未 import `record_degradation`**，须照抄 `builder.py:55-61` 的 import 兜底块，否则 md2docx 作为包被独立调用时 ImportError。

`E-OL-03` 加入 `issues.py:258` 的 `STRICT_ESCALATION_EXEMPT_CODES`（与 W-OL-01/02 同族，走延迟阻断而非 `--strict` 下升 FATAL 短路渲染）。

---

### D1-5（P0）层级下沉 —— 治愈用户投诉的关键单点

**裁决**：`stage-7-writing.md` 的 **R1 红线本体不改**（`## 本章结论` 在分章草稿中仍为 H2），真正的修复点在**合并器层级下沉**。

**理由**：
1. R1 的立法目的是"章首唯一入口"，不是"H2 = 章"。`writer-template.md:90` 已明确分章文件的 H2 非章。
2. 改写作阶段会连带打断 7 处文件的对称结构。
3. 实测 `contract_check.py` 与 `writing_quality_check.py` 全文**都没有"本章结论"字面量**，此改动不涉及任何脚本同步。

**方案**：`merge_drafts.assemble_merged()` 在拼接每份分章草稿时，将其内部所有 H2 统一降为 H3、H3 降为 H4（依此类推），使章容器 H2 成为该章唯一的 H2。

```python
def _demote_headings(content: str, levels: int = 1) -> str:
    """把 Markdown 正文中的标题整体下沉 N 级（H2->H3, H3->H4 ...）。
    跳过代码块内的 # 行。
    """
    out, in_fence = [], False
    for line in content.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line); continue
        if not in_fence:
            m = re.match(r"^(#{2,5})(\s+.*)$", line)
            if m:
                out.append("#" * min(len(m.group(1)) + levels, 6) + m.group(2)); continue
        out.append(line)
    return "\n".join(out)
```

在 `:273` `lines.append(content.strip())` 前调用：`content = _demote_headings(content)`。

**同步修改** `stage-7-writing.md` 的层级表：增加一行说明"分章草稿的 H2 在合并阶段由 `assemble_merged` 自动下沉为 H3，章容器 H2 由合并器生成；作者无需也不应在草稿中书写章标题"。

**为什么不选"未命中白名单一律降级 SECTION"**（补位设计给出三条实测破坏证据）：
- `breaks.py` 的 BODY 节起点依赖 CHAPTER 判定，全量降级会使起点消失
- `figures.py` 图号章前缀全丢
- 精确文本匹配下，outline 与正文的标点差异会**误伤真章**

**为什么不选"对『本章结论』做字符串特判"**：
- 特判只治一个字符串，骨架里其他固定 H2 同样会误判，治标不治本
- 层级下沉后特判即成死代码

> 注：曾有方案援引 `config.py:290` 的反硬编码红线来否决字符串特判。**该援引是错的**——实测该口诀原文为"换一份完全不同主题的报告，该字符串是否仍必须出现在代码里？**是 → 结构关键词（允许）**"，"本章结论"来自骨架、与主题无关，属**允许**一侧。此处改用上述两条理由。

---

### D1-6（P1）三态开关 + 告警聚合

**问题**：白名单启用后 W-HDR-04 从 0 暴增至 **126 条**（113 个 H3 落榜 + 13 个"本章结论"）。转换报告原有 67 条 WARNING，翻到 190+ 会使人工复核清单直接失效。

**方案**：
1. 新增 `--structure-overlay=off|warn|strict` 三态，默认 `warn`。存量项目走 `warn`，新项目走 `strict`。
2. **W-HDR-04 按 kind 聚合输出**——"113 个 SECTION 级 heading 未在 outline 声明"一条，而非逐条 113 行。

> 主控此前预判"正文标题带编号前缀会导致精确匹配大面积 miss"，**实测为反**：`classify_and_number` 会先剥离编号，`## 第 1 章：导论：空间认知智能的时代命题` 被剥成 `导论：空间认知智能的时代命题`，与 outline 的 `section_title` **逐字相同 → 13/13 命中**。miss 的真正原因是 outline 的 `subsections` 全空。

---

### D1-A（P1）修复恒 pass 的虚假门禁

**问题**：`writing_quality_check.py` 的 `CHAPTER_HEADING_PATTERN` 无法匹配 `assemble_merged` 产出的带空格格式"第 1 章"，导致 E2 章间过渡检查对所有合并终稿**恒零命中、恒 pass**。

这与 `figure_gate.py` 的静默放行同属"门禁存在但从不生效"——**比没有门禁更危险，因为提供虚假保证**。

**方案**：正则"第"后与"章"前各补 `\s*`。实测 5/5 全通过验证有效。

---

## 六、连锁影响与向后兼容

| 组件 | 影响 | 评估 |
|---|---|---|
| `breaks.py` 分页 | 伪章消失 → 多余分页符消失 | **改善** |
| `render/toc.py` 目录 | 13 个并列"本章结论"变为各章下的二级条目 | **改善** |
| `figures.py` 图号 | chapter_map 从含伪章的 6 元素变为干净 3 元素 | **根治图号错位** |
| 页眉 | 无影响（TITLE_SHORT 取自 metadata） | 无 |
| `gate3.py` | 章号连续，门 3 由必挂转为可通过 | **改善** |

**golden 快照零破坏**（四条实测证据）：
1. golden 的对象是 `contract_check.py --json` 输出，**不经过 md2docx 装配链**
2. 8 份 fixture **全部不含 YAML front matter / structure 节点**，overlay 不执行
3. `test_integration.py` grep `structure|outline|lookup` **零命中**，且 fixture 无 outline → `structure_titles=None`，诊断不触发
4. 8 份 fixture **无一是 `assemble_merged` 产物**，故合并行为变更不触及快照

**结论：无需 `UPDATE_GOLDEN` 刷新。**

`test_structured_fixture.py` 已用权威键名 → 归一化为恒等变换 → **不受影响，反而是幂等性的现成回归证据**。

---

## 七、验收标准

### 必过项

| # | 断言 | 说明 |
|---|---|---|
| A1 | `pytest tests/test_finalize_pipeline.py` **4 failed → 17 passed** | 最强信号 |
| A2 | 合并产物中各 `ch{XX}-*.md` 内容出现次数**恰为 1** | 捕获重复拼接 bug，现有用例无一覆盖 |
| A3 | 对含 `## 本章结论` 的 fixture 跑 overlay，断言其 kind == `SECTION`、number 为二元组 | D1-5 专项 |
| A4 | docx 回读：**每个 Heading 1 到下一个 Heading 1 之间必须有非空正文** | 直接对应用户投诉 |
| A5 | Heading 1 数量 == outline 声明章数 | 防伪章 |
| A6 | 不得出现文本重复的 Heading 1 | 防 13 个"本章结论" |
| A7 | 归一化对已合规 outline 为**恒等变换** | 幂等性 |

### 手工验证命令

```bash
python -c "
from docx import Document
d = Document(r'output/<报告题名>_v1.0.docx')
prev, buf, bad = None, [], []
for p in d.paragraphs:
    if p.style.name == 'Heading 1':
        if prev and not ''.join(buf).strip(): bad.append(prev)
        prev, buf = p.text, []
    elif prev: buf.append(p.text)
if prev and not ''.join(buf).strip(): bad.append(prev)
print('空章标题:', bad if bad else '无')
"
```

---

## 八、测试基建（D1-7，P1）

**Owner 裁决**：`tests/test_e2e_draft_to_docx.py` 由 **D1 为唯一 owner**（D3 曾计划建同一文件，已裁定 D3 只提供 fixture 不建测试文件，避免互相覆盖）。

**fixture 设计要点**：必须真实还原 `merge_drafts` 产物形态——每份分章草稿的首个 H2 逐字为 `## 本章结论`、不写章容器 H2（由合并器生成）。**刻意逐字复刻 `writer-template.md` 骨架，防止为让测试变绿而削弱真实性。**

**现有 fixture 失真实证**：`scripts/md2docx/tests/test_fixtures/multi-chapter.md:19-23` 为「H2 章标题 → 正文 → H3」结构，**完全不含"两个相邻 H2"这一致命组合**。这是缺陷从未被测出的直接原因。

---

## 九、阶段 4 骨架 docx 预确认（D1-9 前置 + D1-8 本体）

> **编号说明**：D1-3/D1-4 在本文档历次修订中**从未被占用**（全库 grep 零命中，无历史说明）。为避免后续实施者误以为存在遗失章节，此处明确记录：**D1-3/D1-4 为空号，永久保留不再启用**，新增子项从 D1-8 起编。

> 本节回应用户建议："能否在阶段 4（大纲确认）就生成整个报告的初版 word 模板，里面有封面、目录、每个章节的一级标题和二级标题……如果这个模板用户确认，那么后续工作就不要改变这个模板，只是在后续工作中增加内容。"

### 9.1 技术可行性：已实测证实，且不需要修改 md2docx

**实测探针**（临时目录 `/tmp`，未触碰 skill 与项目目录，跑完即删）：用一份只含标题、零正文的 Markdown 加一份 `cover.md`，调用**未经任何修改的** md2docx：

```bash
python -m md2docx skeleton.md out.docx --cover cover.md
EXIT=0
```

产出 `out.docx` 实测含：封面（题名 26pt + 机构 + 版本日期）、`TOC Heading` + TOC 域（`instrText` 存在）、`Heading 1` × 2、`Heading 2` × 2，`W-` 级告警仅 1 条（`W-PB-01`）。

**结论：骨架生成是 md2docx 现有能力的真子集，零脚本改造即可产出。** 这一条比原先预判的"高可行性"更强——连 `--skeleton-only` 子命令都不是必需的（见 §9.5 与 D2-9 的接口对齐）。

**层级映射实测**（决定"用户所说的二级标题"到底指什么）：

| Markdown | docx 样式 | 用户口中的称法 |
|---|---|---|
| `##` | `Heading 1` | 一级标题（章） |
| `###` | `Heading 2` | 二级标题（节） |
| `####` | `Heading 3` | 三级标题（小节） |

叠加 D1-5 层级下沉后，终稿中章容器 `##`→`Heading 1`、草稿原 H2（`本章结论`）下沉为 `###`→`Heading 2`、草稿正文节原 H3 下沉为 `####`→`Heading 3`。**即用户要求"骨架含 H1/H2"，在数据上对应 outline 的 `bodymatter[*].chapter_title` 与 `bodymatter[*].sections[*].section_title` 两层。**

### 9.2 【致命前提】section 级数据当前根本不存在 —— 本项不能直接实施

这是本节最重要的发现，**它推翻了"阶段 4 数据已齐备"这一原始假设**。

真实 `research/outline.md` 实测：

| 度量 | 实测值 | 命令/方法 |
|---|---|---|
| `subsections` 字段总数 | 16 | `grep -c "subsections:"` |
| 其中值为空列表 `[]` 的 | **16（100%）** | `grep -c "subsections: \[\]"` |
| YAML 声明的 section 级条目 | **0** | 同上 |
| outline.md 正文（169 行后）章级 `##` 标题 | 16 | `awk` 提取 |
| outline.md 正文节级 `###` 标题 | **2**（仅 0.1/0.2 前置件） | 同上 |
| 散文形式的节号引用（如"（1.1节）"） | 74，且第 7/8 章各仅 2 处 | `grep -o "（[0-9]\+\.[0-9]\+节）"` |
| 终稿 `output/SCIF_V1.0.docx` 实际 `Heading 2` | **113** | python-docx 回读 |

**三个数字的落差是本项的核心风险：YAML 声明 0 → 散文提及 74 → 实际产出 113。**

若照原建议直接实施，阶段 4 产出的骨架 docx 将只有 16 个章标题、节层完全空白，用户在 Word 里看到的是一份**缺失约 100 个二级标题**的框架。用户确认这样一份骨架，恰好落入用户自己在初步分析中担心的陷阱——**"我在阶段 4 已经确认过了"的虚假安全感，比不做这个功能更危险**。

**更糟的实测**：现在就用第四消费端 `outline_title_extract.py` 对真实 outline 提取标题树：

```
$ python scripts/outline_title_extract.py --outline research/outline.md --json
章条目数: 13
chapter_title 为空的: 13        ← 100%
chapter_no 为 null 的: 13       ← 100%
sections 为空的: 13
consistency_warnings: 18（全为 markdown_only）
EXIT=0                          ← 静默成功
```

**即：今天若基于现有管线搓一个骨架生成器，它会产出一份「16 个空白标题」的 docx，并且 exit 0 不报错。** 这是 D1 键名契约断裂在阶段 4 的直接投影，也是本项**强依赖 D1-1 先完工**的硬证据（依赖判断成立，不可解耦——解耦的唯一办法是在骨架生成器里再抄一份归一化逻辑，那正是 D1 §3.2 判定为反模式的"第二处适配层"）。

### 9.3 D1-9（P1）阶段 4 结构完整性门禁 —— D1-8 的强制前置项

**问题**：`stage-4-outline.md:320` 的质量门槛明写"大纲含三级标题（章→节→小节）"，`:324` 明写"用户确认了大纲结构"，`:326` 是 🔴 CHECKPOINT 🛑 STOP。**但阶段 4 全文零脚本调用**（grep `python`/`scripts/` 零命中），整个质量门槛是**人工勾选的复选框**。

本次事故的实证：这一项被勾选通过，而实际 `subsections` 16/16 为空。**这是根因 R-B（规范依赖人工执行而无机器门禁）在阶段 4 的一个此前未被记录的实例**——既有五份文档中"阶段 4"/"stage-4" 全库零命中，本项是首次覆盖该阶段。

**方案**：新增 `scripts/outline_structure_gate.py`，在阶段 4 CP3 之前强制执行：

| 检查项 | 判据 | 级别 |
|---|---|---|
| S1 | YAML `structure` 存在且经 `normalize_outline_structure()` 后 `bodymatter` 非空 | FATAL |
| S2 | 每个 `bodymatter[*]` 有非空 `chapter_title` | FATAL |
| S3 | 每个 `bodymatter[*].sections` **条目数 ≥ 2** | FATAL |
| S4 | 每个 `sections[*]` 有非空 `section_no` 与 `section_title` | FATAL |
| S5 | YAML 声明的章标题集合 == Markdown 正文 `##` 标题集合（去编号后） | WARNING |
| S6 | `section_title` 不含编号前缀（复用 `headings.py` 的 `_strip_section`） | WARNING |

**S3 的阈值 ≥2 而非 ≥1 的理由**：只有 1 个节的章，其节标题必然与章标题语义重复，是"为过门禁而填一行"的典型形态。实测真实 outline 的散文节号分布中，第 7 章与第 8 章各仅 2 处引用，而这两章的篇幅预算是全报告最大的（20 页 / 18 页）——**散文侧本身就已呈现"大章缺节"的欠规划特征**，S3 正是要把这类问题挡在阶段 4，而不是留到阶段 7 由 Writer 即兴补齐。

**诚实标注 S3 的副作用**：它会使**存量项目的 outline 100% 无法通过阶段 4 门禁**（当前 16/16 空）。因此 S3 必须与 D1-6 同款的三态开关配套：`--structure-gate=off|warn|strict`，存量走 `warn`，新项目走 `strict`。**首版默认 `warn`**，与 U3/U4 的既定处置口径一致。

**这一项的价值独立于 D1-8**：即使用户最终不采纳骨架 docx，S1-S4 也应落地——它修的是"阶段 4 唯一的用户确认阻断点，其质量门槛无任何机器校验"这个结构缺陷。

### 9.4 D1-8（P2）骨架 docx 生成与 H1/H2 锁定

#### 9.4.1 功能设计

**输入**：`research/outline.md`（经 D1-1 归一化后的 structure）+ `research/cover.md`（实测已存在，含 `title`/`title_en`/`report_type`/`org`/`date`/`version`/`header_short` 七个字段，足够填满封面，**无需新增 schema 字段**）。

**处理**：新增 `scripts/outline_skeleton.py`，两步：

1. **合成骨架 Markdown**（`research/drafts/.outline-skeleton.md`）——复用 `outline_title_extract.build_title_tree()` 拿层级树（**依赖 D1-1 完工，否则全是空标题**），按 `frontmatter → bodymatter → appendix` 顺序输出：
   - 报告题名 → `#`
   - 每章 `chapter_title` → `##`
   - 每节 `section_title` → `###`
   - **不写任何正文**，每个 `###` 之下留一行占位提示 `> （本节内容待阶段 7 写作填充）`
2. **调用既有 md2docx**（不新写 docx 生成代码）：
   ```bash
   python -m md2docx research/drafts/.outline-skeleton.md \
     research/outline-skeleton-preview.docx \
     --cover research/cover.md
   ```

**为什么占位提示行是必需的**：§9.4.4 将说明，若节下完全空白，D2-7 的 docx 回读门禁会因其 `elif` 分支把 `Heading 2` 文本误当正文而**误判通过**；占位行同时也让用户在 Word 中看到明确的"此处待填充"语义，而非疑似渲染失败的空白。

**产物命名与落位**（避免重演 D3 §一"两个 docx 混在 output 目录分不清"的旧事故）：

| 事项 | 定案 | 理由 |
|---|---|---|
| 目录 | `research/`，**不进 `output/`** | `stage-9-finalize.md:147` 定义 `output/` 为"最终交付物"目录。骨架是中间确认件，进 `output/` 必然与终稿混淆 |
| 文件名 | `outline-skeleton-preview.docx` | 含 `skeleton`/`preview` 双重语义标识，与 `报告题名_v1.0.docx` 的交付物命名模式无任何前缀重叠 |
| 中间 md | `research/drafts/.outline-skeleton.md`（点号前缀） | 与既有 `.degradation-log.jsonl`/`.provenance.jsonl` 同款隐藏件约定，且**不得命名为 `final-report*`**，否则被阶段 9 的 glob 误吃 |
| 生命周期 | 阶段 9 `emit_delivery` 时若检出该文件仍在，**WARNING 列出交人判断**，不自动删 | 与 D3 §六第 3 条对 `SCIF_V1.0.docx` 的处置口径一致（禁止按文件名自动移动） |

**与 CP3 的挂接**：在 `stage-4-outline.md:317` 的质量门槛清单中，`:324`"用户确认了大纲结构"之前插入两项：

```
- [ ] 已运行 outline_structure_gate.py，S1-S4 全部通过（D1-9）
- [ ] 已生成 research/outline-skeleton-preview.docx，用户在 Word 中确认了章节框架（D1-8）
```

并把 `:326` 的 CHECKPOINT 文案扩为"用户确认大纲结构（含章标题/**节标题**/篇幅建议/证据源/图表规划）**及骨架 docx 的标题框架**后进入阶段 5"。

#### 9.4.2 锁定机制设计

**核心认知：D1-5 落地后，"H1/H2 不可新增"这个不变量在机制上已大部分成立，不需要全新机制。**

理由（实测支撑）：
- 章容器 H2（→docx `Heading 1`）**只能**由 `merge_drafts.assemble_merged()` 从 outline 的 `chapter_title` 生成（`stage-7-writing.md:119`/`:136` 两处明文要求分章文件"不写章容器 H2"）。作者物理上无法新增 `Heading 1`。
- 分章草稿内部所有标题经 D1-5 统一下沉一级，作者写的 H3 正文节变成 `####`→docx `Heading 3`。**即作者的笔无法触达 docx 的 `Heading 1`/`Heading 2` 两层。**

**因此真正需要新增的只有一条校验**：作者是否在已声明的节之外，新增了 outline 未声明的**节级**标题（下沉后的 `###`→`Heading 2`）。

**实测确认现状不足**：`apply_structure_overlay()`（`headings.py` 约 `:474-548`）**不按层级区分**——循环只按 `ir.text.strip()` 查 lookup，未命中时把 `CHAPTER`/`SECTION`/`SUBSECTION`/`APPENDIX` 四种 kind **一律**塞进同一个 `unmatched_headings` 列表，统一发同一条 `W-HDR-04`（`:533-548`）。用户设想的"按层级区分裁决"在现状中确实不存在，需要增量细化。

**D1-8 的增量设计**（在 D1-6 三态开关基础上按 kind 分级，**不新增开关**）：

| 未命中的 heading kind | 语义 | `warn` 模式 | `strict` 模式 |
|---|---|---|---|
| `CHAPTER` | 新增了 outline 未声明的章 | WARNING（沿用 W-HDR-04） | **FATAL**（违反锁定） |
| `SECTION` | 新增了 outline 未声明的节 | WARNING | **FATAL**（违反锁定） |
| `SUBSECTION` | 在已声明节下新增小节 | INFO（新码位 `I-HDR-08`） | INFO（**放行**） |
| `APPENDIX` | 附录条目未声明 | WARNING | WARNING |

**改动量**：在 `:526-536` 的 `elif ir.kind in (...)` 分支处按 kind 分流到两个列表，`:533` 的单一 WARNING 循环拆成"结构锁定违规"与"深化新增（INFO）"两支。**约 25 行，半天。** 新码位 `I-HDR-08` 须避开 D1-0 删除的死码位与 D1-2 新增的 `E-OL-03`/`I-OL-04`。

**这条设计同时解决了用户诉求 3（"新增的 H3/H4 有明确位置标定"）**：`SUBSECTION` 放行的前提是它能被 `_find_parent_section_idx()` 归属到某个已声明的父节；归属失败的"孤儿 subsection"在 `outline_reader` 侧已有台账记录（`outline_title_extract.py:237-238` 明文说明该机制已存在），本项只需把该台账项从静默升为 INFO 可见。**无需新建位置标定机制。**

#### 9.4.3 "锁定"必须是可撤销的 —— 退路设计

**这对矛盾是本项最需要诚实处理的部分**：报告写作中"某章需拆成两章""某节应提升为章"是真实且常见的研究深化结果。若把 H1/H2 锁成硬不可变，方案会与真实研究流程冲突，而冲突的实际结局通常不是用户回头改大纲，而是**实施者或模型悄悄放宽门禁**——这正是 D2 §2.2 已论证过的失效模式。

**定案：锁定的语义是"变更须走显式回炉"，不是"禁止变更"。**

| 场景 | 处置 | 机制 |
|---|---|---|
| 已声明节下新增小节（H4+） | 直接放行 | `I-HDR-08` INFO 记录 |
| 需新增/拆分/合并章或节 | **回到阶段 4**：改 outline → 重跑 D1-9 门禁 → 重新生成骨架 → 重新 CP3 确认 | 复用既有 CP3 阻断，**不新增流程节点** |
| 阶段 7/9 检出未声明的章/节 | `strict` 下 FATAL，报错文案**必须直接给出回炉指令** | 见下 |

报错文案须逐字给出可执行动作，否则会重演 D2 §四对 D2-5 的批评"路由表给不出有效动作时，自写代码在模型看来是唯一剩余选项"：

```
E-HDR-09：检出 outline 未声明的 SECTION 级标题「<标题>」（行 N）。
这违反了阶段 4 已确认的 H1/H2 结构锁定。
允许的动作只有两个：
  (a) 若该节确应存在 → 回到阶段 4：更新 research/outline.md 的
      structure.bodymatter[<章号>].sections，重跑 outline_structure_gate.py，
      重新生成骨架 docx 并请用户重新确认 CP3；
  (b) 若该节不应存在 → 将其降为 H4（小节）并挂到已声明的父节之下。
禁止的动作：放宽门禁、删除本告警、改用 --structure-overlay=off 绕过。
```

**诚实标注（不可回避）**：上述"禁止的动作"三条属于 D2 已判定"效力接近零"的纯文档约束——`--structure-overlay=off` 是 D1-6 设计的合法开关，orchestrator 完全可以用它绕过本项全部校验。**本项的机器强制力上限止于"在 `strict` 模式下报 FATAL"，无法阻止调用方改用 `warn`/`off`。** 这与 D2-9 的递归漏洞（可编辑 `settings.json` 关掉 hook）是同一类未闭环问题，不宜粉饰。

#### 9.4.4 与 D2-7 的冲突 —— 顺带暴露 D2-7 自身的一个缺陷

**实测**：把 D2-7 设计稿的 `verify_docx_structure()` 原样跑在骨架 docx 上，结果是 **`pass = True`、`empty_headings = []`**。

**机理**：D2-7 的收集逻辑是

```python
if p.style.name == "Heading 1": ...
elif prev is not None: buf.append(p.text)     # ← Heading 2 也走这一支
```

`Heading 2` 不等于字面量 `"Heading 1"`，于是**节标题文本被当作正文收集**。只要某个 `Heading 1` 后面跟着任一非空 `Heading 2`，该章就被判为"有正文"。

**两个后果，都必须写进方案**：

1. **D2-7 存在漏检**（本次新发现，不在 D2 原文中）：一份"只有标题、完全没有正文"的 docx 能通过 D2-7。这削弱了 D2 §四给它的"高有效性"评级——它能捕获本次事故的形态（`Heading 1` 后紧跟 `Heading 1`），但捕获不到"全文只有骨架"这一形态。**建议 D2-7 的 `buf` 收集改为只累加非标题样式段落**（`elif prev is not None and not p.style.name.startswith("Heading")`），约 1 行改动。
2. **D1-8 必须显式豁免**：骨架 docx **绝对不能**进入 D2-7/`gate3`/`delivery_checklist` 的检查范围。豁免的实现方式**不能靠文件名正则**（D3 §六已实测证明按文件名判定会颠倒），而应靠：骨架生成走独立入口，**不经过 `finalize_pipeline.py`**——管线第 7 步 `verify_docx` 只对 `emit_delivery` 实际写出的路径清单生效。骨架不在该清单内，天然不被检查。**零新增豁免逻辑。**

#### 9.4.5 与 D2-9 规则一的接口对齐

**结论：本项与 D2-9 规则一无冲突，且不需要为其设计 `--skeleton-only` 子命令。**

D2-9 规则一（D2 文档 `:271-275`）的 deny 条件是三者同时成立：目标在 output_dir 下、扩展名 `.docx`、命令含 python-docx 特征而**不含 md2docx 引用**。逐条比对本项：

| 规则一条件 | 本项实际 | 是否命中 |
|---|---|---|
| 目标在 `output_dir` 下 | 骨架落 `research/`，**不在 output_dir** | 不命中 |
| 命令含 python-docx 特征、不含 md2docx | 骨架生成**就是调用 `python -m md2docx`** | 不命中 |

**两条独立的不命中路径**，任一条即足以排除误伤。**前提是 §9.4.1 的定案必须被遵守：骨架生成器只合成 Markdown，docx 一律交给 md2docx，绝不自行 `from docx import Document`。** 这条约束应写进 D2-9 的 hook 脚本注释，作为"合法调用样例"记录，避免未来实施者做误伤率测试（D2 §5.4 第 5 条）时把本项当违规样本。

**须同步告知 D2-9 的一点**：`scripts/outline_skeleton.py` 是**新增脚本**，而 D2-9 规则二的路径黑名单含 `<skill_root>/scripts/**`。规则二禁止的是"在报告编写会话中修改 skill 脚本本体"，新增该脚本属于**实施本方案时**的 skill 开发行为，不在报告编写会话内，不受规则二约束。此处记录以免混淆。

#### 9.4.6 密级问题：经核实是伪问题，撤回

原先列为局限的"骨架封面若涉密级标注，schema 无对应字段"经实测**不成立，应撤回**：

- `gate3.py:103-144` 的 `_check_secrecy` 是**剔除型**门禁——"全文搜索密级关键词，出现即 FATAL"（`:106` docstring 逐字），关键词表在 `config.py:311`。
- `stage-9-finalize.md:157` 交付清单逐字要求"封面完整（标题/副标题/机构/日期/版本），**无密级标注**"。

**即本 skill 的既定立场是产物一律不带密级标注。** 骨架 docx 不需要密级字段，outline schema 也不需要为此新增字段。反之需注意：**骨架的封面/占位文案中不得出现"密级""内部资料"等 `config.py:311` 表内词汇**，否则骨架自身会触发 gate3 FATAL（若将来有人把骨架接入 gate3 检查）。

### 9.5 利弊分析

**收益**：

| # | 收益 | 强度判定 |
|---|---|---|
| B1 | 把"结构错误"的发现点从阶段 9（终稿已成型）提前到阶段 4（尚未写一字），是本方案中**唯一的左移型措施** | 高，但**条件性**——仅在 D1-9 落地、section 数据真实存在时成立 |
| B2 | 用户得到与最终 Word 同源渲染的框架视图，确认对象从"读 YAML/Markdown 大纲"变为"看 Word 导航窗格" | 中高，符合用户原始诉求 |
| B3 | 逼出 outline 的 section 级数据（经 D1-9），**顺带修复 113 个 H3 全走推断分类**这一 D1 §3.5 已记录但无处着手的存量问题 | **高，且是意外收益**——D1-6 实测的 126 条 W-HDR-04 中 113 条源于此 |
| B4 | 阶段 4 首次获得机器门禁，补上根因 R-B 在该阶段的空洞 | 中高 |
| B5 | 骨架生成走既有 md2docx，零新增 docx 代码，无新增维护面 | 中 |

**代价与风险**：

| # | 代价/风险 | 诚实评估 |
|---|---|---|
| C1 | **强依赖 D1-1**。未完工即实施，产出 16 个空白标题的骨架且 EXIT=0（已实测） | 硬依赖，无法解耦 |
| C2 | **D1-9 的 S3 会使存量项目 100% 卡在阶段 4**（16/16 空） | 必须配三态开关，首版 `warn`，与 U3/U4 口径一致 |
| C3 | 增加一个用户确认动作（打开 Word 看骨架）。用户确认疲劳后可能草率点过，届时骨架反而**提供虚假安全感** | **本项最大的软风险，无机器手段可防**。缓解：CP3 呈报须附 S1-S4 的机器判据数字（如"13 章 / 87 节已声明"），使确认对象是数字而非印象 |
| C4 | 锁定与研究深化的矛盾。退路（回炉阶段 4）依赖用户配合；用户嫌麻烦时，实际结局多为放宽门禁 | 无法机制性闭环，见 §9.4.3 诚实标注 |
| C5 | 阶段 4 多出 2 个产物（骨架 md + 骨架 docx），是 D3 治理的新增对象 | 已按 §9.4.1 定案落 `research/`、双重语义命名、阶段 9 只 WARN 不自动删 |
| C6 | `strict` 模式的 FATAL 可被 `--structure-overlay=off` 完全绕过 | 机器强制力上限，已诚实标注 |
| C7 | 新增脚本 2 个（`outline_structure_gate.py`/`outline_skeleton.py`）+ 1 处 headings.py 改动 + 4 处文档改动，长期维护面扩大 | 中等；两个脚本均为纯读 YAML + 生成文本，无外部依赖 |

**不做本项的后果**：D1-1/D1-5 完工后，用户投诉的"章节是空的"会消失，但"outline 只声明章不声明节 → 113 个节标题全靠 Writer 即兴 → 结构与大纲不可核对"这个问题仍在，且**没有任何其他子项覆盖它**（D1-6 只是把它聚合成一条告警，不解决数据缺失）。

### 9.6 优先级判定

**D1-9 判 P1，D1-8 判 P2。**

判定依据严格对照既有标准（D2-9 被判 P1 的理由是"产物层面已有替代路径、非阻塞"）：

| 维度 | D1-9（结构门禁） | D1-8（骨架 docx + 锁定） |
|---|---|---|
| 是否阻塞交付 | 否——存量项目 outline 空 section 仍能产出 docx | 否 |
| 是否有替代路径 | **无**。阶段 4 当前零机器校验，无任何其他子项覆盖 | **有**。D1-1/D1-5/D2-7 已能在产物层面捕获结构异常；骨架仅是提前可视化 |
| 是否治愈已发生的用户投诉 | 否（投诉由 D1-5 治愈） | 否 |
| 不做的后果 | 阶段 4 唯一的用户阻断点继续无机器判据；113 个节标题继续走推断 | 用户少一次可视化确认，结构错误发现点仍在阶段 9 |
| 依赖 | D1-1 | D1-1 + D1-9 + D1-6 |

**D1-8 不进最小可交付集**：理由与 D2-9 同构——它是"确认体验与提前发现"的加强层，而非唯一防线；且它自身依赖链最长（三个前置项），提前实施只会产出空白骨架。

**D1-9 高于 D1-8 一级**的理由：它的价值不依赖 D1-8 是否被采纳，且它是 D1-8 全部收益成立的前提；同时它独立修复了一个此前未被任何子项覆盖的阶段（阶段 4）。

### 9.7 实施步骤与工作量

| 步 | 内容 | 工作量 | 前置 |
|---|---|---|---|
| 1 | `outline_structure_gate.py`：S1-S6 六项检查 + `--structure-gate` 三态开关 | 半天 | D1-1 |
| 2 | `stage-4-outline.md` 挂接：质量门槛加 2 项、`:326` CHECKPOINT 文案扩写、新增脚本调用段 | 1 小时 | 步 1 |
| 3 | `outline_skeleton.py`：合成骨架 md + 调用 md2docx | 半天 | D1-1、步 1 |
| 4 | `headings.py` 按 kind 分级裁决 + 新码位 `I-HDR-08`/`E-HDR-09` | 半天 | D1-6 |
| 5 | `outline_architect_agent.md` 补 section 级产出要求（见下） | 1 小时 | — |
| 6 | 测试：骨架 md 幂等、S1-S4 各自的红/绿用例、按 kind 分级的四类断言 | 半天 | 步 1/3/4 |

**合计约 2.4 人天**（D1-9 约 0.75 天、D1-8 约 1.65 天）。

**步 5 的必要性（本次新发现的产出端根因）**：`agents/outline_architect_agent.md:49-53` 的"YAML `section_title` 纯文字要求"通篇只规定**格式**（不许带编号前缀），**从未要求必须产出 section 级条目**；`:47` 只要求"包含机器可读的结构清单（`structure` 节点）"。**这是 `subsections` 16/16 全空的产出端根因**——生产者契约没要求，生产者就没写。不改这一处，D1-9 的门禁会在每个新项目上把 `outline_architect_agent` 卡住，而后者不知道该补什么。

**在总览"实施路线图"中的插入位置**：

- **D1-9 → 第 3 批**（与 D1-2/D1-6 同批）。理由：依赖 D1-1（第 2 批）完工，且与 D1-6 的三态开关模式同构，同批实施可共用开关设计与测试脚手架。
- **D1-8 → 第 4 批**（与 D1-7 同批）。理由：依赖 D1-9（第 3 批）与 D1-6（第 3 批）；且 D1-7 的端到端 fixture 可复用骨架 md 作为一个新增用例形态。

### 9.8 用户裁决（U6/U7，已定案）

对应总览文档 §六 U6/U7，用户已给出明确裁决，本节记录裁决结果与实施约束，供后续实施阶段直接引用，不再是待定项：

| 决策项 | 裁决结果 | 实施约束 |
| --- | --- | --- |
| **U6**（D1-9 的 S3 是否 `strict`） | **首版 `--structure-gate=warn`**，与 U3/U4 同口径 | 切换到 `strict` 的触发条件须在实施 `outline_structure_gate.py`（步 1）时一并写入代码注释与 `stage-4-outline.md`：建议判据为"连续 N 个新项目的 outline 自然产出非空 section"（N 值留待实施时结合项目节奏确定，本方案不预设具体数字），而非无限期搁置。理由见 D2 文档 §2.2——纯口头"待补齐后再切"若无客观判据，等同于永不切换 |
| **U7**（是否采纳 D1-8） | **采纳，排第 4 批**，以 D1-9 落地为硬前置 | D1-8 的步 3/4/6（`outline_skeleton.py`、`headings.py` 按 kind 分级、测试）**不得早于 D1-9 完成且验证通过**（即 §9.7 步 1 的 S1-S4 在真实 outline 上跑出非空 section 数据）才启动，避免重演"提前实施只产出空白骨架"的风险（见 §9.2、§9.6 已论证的依赖关系）。这一约束是对 §9.6"D1-8 不进最小可交付集"判断的具体化，不改变已定的第 3/4 批排期 |

**两项裁决均未改变本章 §9.3-9.7 已设计的技术方案本身**——用户是在"是否做、何时做、按什么口径做"层面做出选择，具体的 S1-S6 检查项、按 kind 分级裁决表、退路设计（§9.4.3）等均照原设计执行。

---

## 十、未经交叉验证的风险

R1/R2/R3/R4 四个审查视角均已返回并纳入。仍需实施时注意：

1. `_demote_headings` 对**表格内 `#` 字符**、**HTML 块**的处理未做实测，需在实施时补测。
2. 三态开关的默认值选择（`warn`）基于"存量项目不应被阻断"的判断，若用户希望强约束可改 `strict`。
3. 归一化的第 5 个调用点（顶层 `report_title`→`title`）不在 structure 节点内，各调用方需各自处理，存在遗漏风险。
4. **D1-1 归一化对非空 `subsections` 的映射存在潜在缺陷（本次新发现，实施 D1-1 时必须一并修）**：schema 实测 `sections` 的 items 键为 `{section_no, section_title}`，而 `subsections` 的 items 键为 `{parent_section_no, subsection_no, subsection_title}`——**两者内层键名不同**。D1-1 §5 的 `c["sections"] = c.get("subsections") or []` 是**整体赋值**，非空时会把 subsection 结构塞进 sections 位置，`section_title` 取到 `None`（已用 Python 复现）。当前被"16/16 全空"掩盖，一旦 D1-9 逼出真实 section 数据，该缺陷即刻暴露，且症状与 D1 §3.4 描述的适配层字段错配同构。**修法**：`subsections → sections` 须做内层键映射（`subsection_no→section_no`、`subsection_title→section_title`），或明确二者为不同层级不做映射（`outline_title_extract.py:186`/`:206` 实测是把两者当**独立层级**分别消费的，倾向后者）。
5. D1-8 §9.4.2 的按 kind 分级裁决，其 `SECTION` 判定依赖 `classify_and_number` 的推断准确性；D1-6 实测显示章标题剥离编号后 13/13 命中，但**节级标题的命中率从未实测**（因真实数据为空），S3 落地后需补一次真实命中率测量，再决定 `strict` 是否可作为默认值。
