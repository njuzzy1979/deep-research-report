# 阶段 2：资料搜集、抽取与来源索引

> 本文件是 deep-research-report skill 的阶段 2 详细 spec，从 SKILL.md 拆分而来。
> 母文件：`../SKILL.md`（流程索引）

---

## 2.0 资料搜集

**执行依据阶段 1.1a 的研究范围确认结果**：

- **范围 A（仅用户素材）**：跳过本步骤，直接进入 2.2 文本抽取。
- **范围 B（素材 + 扩展搜集）或用户未提供任何素材**——按以下优先级搜集资料：

### 搜集优先级

| 优先级 | 资料类型 | 用哪个工具 | 说明 |
|--------|---------|-----------|------|
| **P0 - 必收** | 政府公文、法规、行业标准、专利 | web-search-skill `search` | A 级来源，报告的事实锚点 |
| **P0 - 必收** | 权威媒体首发报道（Reuters/Bloomberg/NHK 等） | web-search-skill `search` | B 级来源，事件和产业动态依据 |
| **P1 - 应收尽收** | 学术论文（arXiv/PubMed/SSRN 等） | paper-search `search` + `download` | L2 级来源，提供理论和方法论支撑 |
| **P1 - 应收尽收** | 智库报告、行业分析 | web-search-skill `search` + `extract` | C 级来源，提供趋势判断和行业视角 |
| **P2 - 按需补充** | 公司财报/公告、技术社区、行业协会 | web-search-skill `extract`（已知 URL） | 补充具体数据和案例 |
| **P2 - 按需补充** | 深度多源综合研究 | web-search-skill `research` | 当主题跨多个领域、需要综合大量来源时使用 |

### 下载保存（先保存再解析）

**搜索到资料后，先下载保存到 `research/sources/`，再解析提取内容到 `research/extracted/`。**

这是为了确保来源追溯链完整——即使原始 URL 失效，本地仍有存档可查。流程如下：

```
搜索 → 登记到 source-index.csv（状态=待下载，先占 source_id）
     → 下载保存到 research/sources/（状态=已下载，记录 local_path）
     → 解析提取内容到 research/extracted/（状态=已抽取）
```

| 资料类型 | 下载方式 | 保存路径 |
|---------|---------|---------|
| **PDF**（论文/报告/公文） | paper-search `download` 或 curl/wget 直接下载 | `research/sources/Sxxx-原始文件名.pdf` |
| **网页**（新闻/博客/百科） | web-search-skill `extract` → 将提取得到的正文保存为 .md | `research/sources/Sxxx-网页标题.md` |
| **多媒体**（视频/音频/交互） | 暂不支持下载 | 仅记录 URL，`local_path` 留空并注明"在线资源" |

**下载完成后**：
1. 在 source-index.csv 中记录 `local_path`（相对于项目根目录的路径）
2. 更新 `extraction_status` 为"已下载"
3. 然后参照 §2.3 使用 MinerU 或 extract 进行文本抽取，完成后将 `extraction_status` 更新为"已抽取"

---

### 工具 1：web-search-skill——通用网页搜索

**路径配置**：`references/tool-paths.json` 中 `web_search_skill.absolute_path` 字段。如为空则使用相对路径 `web-search-skill/scripts/search.js`。

> **执行前**：先读取 `references/tool-paths.json`，取 `web_search_skill.absolute_path`。若已填写 → `node "<absolute_path>" ...`；若为空 → `node "web-search-skill/scripts/search.js" ...`。

**5 个子命令**，按场景选用：

| 子命令 | 用途 | 报告编写中的典型场景 | 命令示例 |
|--------|------|-------------------|---------|
| **search** | 关键词搜索 | 查最新政策、行业数据、新闻报道 | `node …/search.js search "中国商业航天 政策 2025" --max 10` |
| **extract** | 提取已知 URL 的正文内容 | 批量读取已找到的文章/报告原文 | `node …/search.js extract <url1> <url2> --format markdown` |
| **crawl** | 整站爬取 | 爬取某机构网站全部页面（如国务院政策文件库） | `node …/search.js crawl <url> --limit 20 --select-paths /policies/.*` |
| **map** | 列出站点 URL 结构 | 先看网站有哪些页面，再决定爬取哪些 | `node …/search.js map <url>` |
| **research** | 深度多源研究报告（异步，15-60s） | 跨领域综合问题，需要引用标注的报告 | `node …/search.js research "问题" --model pro --length long` |

**常用参数**：
- `--engine auto`（默认）：含中文自动走百度，纯英文走 Tavily
- `--engine both`：中英文同时搜索，两边结果对比（跨国对比话题用）
- `--max N`：返回结果数，默认 10
- `--days N`：限定 N 天内发布的内容（时效性话题用）
- `--json`：输出 JSON，方便程序化处理

**搜索策略**：
1. 先用 **search** 跑 3-5 个核心关键词，广度覆盖
2. 对重要结果用 **extract** 读全文，提取关键数据和判断
3. 仅在以下情况用 **research**：（a）主题跨 ≥3 个领域 或（b）需要深度综合大量来源 → `--model pro --length long`
4. **不要用 research 做简单搜索**——它异步且昂贵，普通查资料走 search

---

### 工具 2：paper-search——学术论文搜索与下载

**路径配置**：CLI 命令 `paper-search`（通过 `uv tool install paper-search-mcp` 安装），skill 目录 `paper-search/`（相对于 skill 根目录）。

**3 个子命令**，覆盖论文全流程：

| 子命令 | 用途 | 典型命令 |
|--------|------|---------|
| **search** | 多源并发搜索（20+ 平台，自动去重） | `paper-search search "<关键词>" -s arxiv,semantic -n 10` |
| **download** | 下载论文 PDF | `paper-search download arxiv <paper_id> -o research/sources/` |
| **read** | 提取论文全文文本 | `paper-search read arxiv <paper_id>` |

**常用参数**：
- `-s` 指定来源，逗号分隔：`arxiv,semantic,pubmed,crossref,biorxiv,core,zenodo` 等。默认 `all`
- `-n` 每源结果数，默认 5。高效搜索用 `-s arxiv,semantic -n 10`
- `-y` 年份过滤（仅 semantic 源）
- `paper-search sources` 列出全部可用数据源

**使用流程**：
1. 用 `search` 搜论文（优先 `-s arxiv,semantic` 提速，来源更多时加 `crossref,core`）
2. 将返回结果（含标题/作者/年份/摘要/PDF链接/DOI）登记到 `source-index.csv`
3. 如需阅读全文，用 `read` 提取文本；如需存档 PDF，用 `download` 下载到 `research/sources/`
4. 所有 API key 均为可选（Semantic Scholar/CORE/Unpaywall 邮箱等），配置后提升请求限额；不配置也能正常使用

**适用场景**：
- 报告需要学术文献支撑（如技术评估报告的方法论部分）
- 前沿技术领域的文献综述
- 需要引用论文中的实验数据或理论框架

> **与 web-search-skill 的分工**：web-search-skill 用于搜新闻/政策/行业报告/公司信息（以时效性和广度为主），paper-search 用于搜学术论文（以深度和可引用性为主）。不要用一个替代另一个——两者互补。

---

### 搜集完成后的整理

搜集到的每份资料，登记到 `research/sources/source-index.csv`，字段：
`source_id, title, language, author_or_org, publisher, publish_date, access_date, url_or_path, source_type, credibility_level, relevant_chapters, local_path, extraction_status, notes`

**先登记再抽取**。不跳步——登记是后续核验和引用的唯一凭证。

---

## 2.1 资料可信度分级（通用标准）

| 等级 | 来源类型 | 用法 |
|---|---|---|
| **A** | 官方文件、法律/法规、原始论文/标准、专利、合同公告、审计报告 | 可作为关键事实依据 |
| **B** | Reuters/AP/FT/Economist 等高公信力媒体、权威行业期刊 | 可作为事件和产业动态依据 |
| **C** | 智库报告、行业分析、公司博客、技术社区、行业协会 | 趋势判断可用，关键事实需交叉验证 |
| **D** | 自媒体、未署名转述、社交媒体、二手编译、逐字稿 | **仅作线索**，不直接入正文 |

> **领域适配**：用户可为特定领域调整 A/B 级来源列表（如医疗领域的 FDA/WHO/NEJM，金融领域的 SEC/央行/审计报告）。

## 2.2 资料清单登记

为每份素材建立元数据记录（`research/sources/source-index.csv`），字段：

`source_id, title, language, author_or_org, publisher, publish_date, access_date, url_or_path, source_type, credibility_level, relevant_chapters, local_path, extraction_status, notes`

其中 `local_path` 为下载到本地的文件路径（相对项目根目录），`extraction_status` 为处理状态（待下载/已下载/已抽取/失败）。

## 2.3 文本抽取——使用 MinerU 精准解析

对搜集到的所有 PDF/DOCX/PPT/HTML/图片素材，使用 MinerU VLM API 进行高精度文本抽取。

**工具路径**：`references/tool-paths.json` 中 `mineru.absolute_path` 字段。如已填写则使用该绝对路径；如为空则使用相对路径 `mineru/scripts/mineru_parse.py`。  

> **执行前**：先读取 `references/tool-paths.json`，取 `mineru.absolute_path`。若已填写 → `python "<absolute_path>" ...`；若为空 → `python "mineru/scripts/mineru_parse.py" ...`。  
**前提**：`MINERU_TOKEN` 环境变量已配置  
**能力**：OCR 扫描件识别、公式提取、表格还原、结构化 Markdown 输出

> **超限文档自动拆分**：`mineru_parse.py` 内置自动处理——单文件超过 200 页或 200MB 时，自动本地切分为多个分片、分别解析、最后合并为完整 `full.md`，用户无需手动分批。前提：`pip install pypdf`（PDF 拆分所需，常规调用不需要）；若 Word 文档超限还需 LibreOffice 的 `soffice` 在 PATH 中（用于先转 PDF 再拆分）。Token 通过 `MINERU_TOKEN` 环境变量读取（在 https://mineru.net/apiManage 申请）。

### 使用方式

```bash
python "mineru/scripts/mineru_parse.py" \
  research/sources/<文件> \
  --output-dir research/extracted \
  --language ch
```

### 按文件类型选择参数

| 素材类型 | 推荐参数 | 说明 |
|---------|---------|------|
| **PDF（文字型）** | `--language ch` | 中文为主用 `ch`，英文用 `en` |
| **PDF（扫描件/图片型）** | `--language ch`（OCR 默认开启） | 不要加 `--no-ocr`，保持 OCR 开启 |
| **Office 文档**（.docx/.doc/.ppt/.xlsx） | `--language ch` | MinerU 原生支持 Office 格式 |
| **HTML 网页存档** | `--language ch --model-version MinerU-HTML` | HTML 须用专用模型，不支持 `--extra-formats` |
| **图片**（.png/.jpg/.bmp 等） | `--language ch` | 纯图片默认走 VLM OCR |

### 批量处理

素材较多时（≤50 个），一次性提交整个目录：

```bash
python "mineru/scripts/mineru_parse.py" \
  research/sources/ \
  --output-dir research/extracted \
  --language ch
```

### 输出结构

每个文件在 `research/extracted/<文件名>/` 下生成：

```
research/extracted/
└── <文件名>/
    ├── full.md           # ← 主要使用此文件：结构化 Markdown（含表格/公式/图片）
    ├── images/           #   抽取的图片
    ├── layout.json       #   版面信息
    └── full.docx         #   （可选）--extra-formats docx
```

**抽取后**：将每个文件的 `full.md` 作为后续核验和分析的原文依据。原始素材**不移动、不改名、不删除**。

> **为什么用 MinerU 而不是简单的 `extract`？** web-search-skill 的 `extract` 适合网页正文快速抓取，但 MinerU 对 PDF 扫描件 OCR、表格还原、公式识别的精度远超普通提取——研究报告频繁处理学术论文 PDF 和政府公文扫描件，这些用普通提取会丢失表格数据和公式内容。

> **⚠️ 如果 MinerU 解析失败**（Token 过期 / API 限流 / 文件格式不支持）：
> 1. **Token 问题** → 检查 `MINERU_TOKEN` 环境变量，在 [mineru.net/apiManage](https://mineru.net/apiManage) 重新申请
> 2. **API 限流** → 等待 60 秒后重试，失败则拆分批次（每次 ≤10 个文件）
> 3. **文件格式不支持** → 降级使用 web-search-skill `extract` 抓取文本（丢失表格/公式精度，在 source-index.csv 的 `extraction_notes` 标注"降级提取"）
> 4. **仍失败** → 该文件标记为"抽取失败"，在 source-index.csv 的 `extraction_status` 填 `failed`，不阻塞其他文件；后续核验阶段对该来源的数据持"未经核验"标识

### ▶ 阶段 2 质量门槛

- [ ] 资料搜集完成（研究范围为 B 或未提供素材时，已执行 2.0 搜集流程；范围为 A 时已在 1.1a 明确记录）
- [ ] 所有素材完成文本抽取（PDF/Office 类走 MinerU，网页类走 web-search-skill `extract`）
- [ ] 每份素材有完整的元数据记录
- [ ] 每份素材标注了可信度等级（A/B/C/D）
- [ ] D 级材料中的事实陈述已标记为"待核验"
- [ ] 论文类资料（如有）已通过 paper-search 搜索并登记（需 PDF 时用 `download` 下载）
