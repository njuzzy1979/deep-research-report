# deep-research-report

Claude Code Skill：**深度研究报告编写全流程方法论**。将"写一份研究报告"这件事拆解为 9 个顺序阶段，用证据驱动 + 架构分析的方式，产出有事实核验、有架构图、经过红队审查的正式研究报告（Markdown + 标准格式 Word）。

## 这个 skill 解决什么问题

直接让 LLM"写一份关于 XX 的报告"，容易出现：
- 论点没有证据支撑，或引用来源真假不分
- 图表和正文数据对不上、临时拼凑
- 长报告写到后面结构塌方，前后论证不咬合
- 排版随意，不符合正式交付的格式要求

本 skill 用**阶段化质量门槛**约束这个过程：前一阶段的产物不达标，不允许进入下一阶段。核心理念是"先打地基，再盖房子"——资料没抽完不写大纲，事实没核验不写正文，架构图没画不分章写作。

## 9 阶段流程

```
阶段1 项目初始化
  → 阶段2 资料搜集、抽取与来源索引
  → 阶段3 事实核验
  → 阶段4 详细大纲
  → 阶段5 专题研究（卡片 + 证据包）
  → 阶段6 核心架构图（先于写作）
  → 阶段7 分章写作 + 数据图表（随写作产出）
  → 阶段8 红队审查
  → 阶段9 定稿整合
```

| 阶段 | 产出 | 质量门槛（示例） |
|---|---|---|
| 1 项目初始化 | 工作目录、分析框架、题名参数 | 用户确认关键参数 |
| 2 资料搜集与抽取 | `research/sources/`、来源索引表、MinerU 解析结果 | 每条来源分级 A/B/C/D 并登记 |
| 3 事实核验 | 事实核验台账（claims-ledger） | 高风险主张全部核验 |
| 4 详细大纲 | 三级标题 + 篇幅建议 + 证据源 + 图表规划 | 用户确认大纲结构 |
| 5 专题研究 | 案例卡片 + 证据包（1–3 页/卡） | 每个核心论点有卡片支撑 |
| 6 核心架构图 | `research/figures/` 下的总览图/架构图/流程图 | 图号、图名、核心要素齐全 |
| 7 分章写作 | 正文 Markdown + 随写作产出的数据图表 | 证据密度、主张-证据-推理链达标 |
| 8 红队审查 | 红队风险清单 | 逻辑漏洞、证据薄弱点已处理 |
| 9 定稿整合 | 终稿 Markdown + 标准格式 `.docx` | 通过 V3.0 格式规范 12 项输出检查 |

**关键设计：图表分两批出**
- **核心架构图**（总览图/架构图/流程图）在写作前完成——依据阶段 1.3 的分析框架即可确定图号和图名，是报告的骨架。
- **数据图表**（对比表/趋势图/市场份额图等）随写作按章产出——必须绑定写作时的具体数据和上下文，阶段 4 只规划"方向"，图号在阶段 7 写作时才分配，避免图表与文字脱节。

## 目录结构

```
deep-research-report/
├── SKILL.md                          # 核心方法论（本 skill 的主体，Claude Code 加载入口）
├── README.md                         # 本文件
├── dashboard.md                      # Darwin 2.0 评估优化记录（评分变化、改进说明）
├── scripts/
│   └── markdown_to_docx.py           # Markdown → 标准格式 Word 一体化转换脚本
├── references/                       # 阶段执行时按需读取的参考文件
│   ├── 研究报告格式规范.md            # 【权威】Word 格式规范 V3.0（遨天科技编制）
│   ├── word-format-spec.md           # 旧版格式规范 v1.0（已归档）
│   ├── claims-ledger-template.csv    # 事实核验台账模板
│   ├── source-index-template.csv     # 来源索引模板
│   ├── red-team-checklist.md         # 红队审查详细清单
│   ├── writing-standards.md          # 写作标准详细说明（12 条标准）
│   ├── architecture-analysis-guide.md # 架构分析方法论指南
│   └── md-to-docx-pitfalls.md        # Markdown→Word 转换踩坑记录
├── evals/
│   └── evals.json                    # 评估用例
├── assets/                           # 静态资源
├── output/                           # 运行时产物（已 gitignore）
└── research/                         # 运行时工作区：sources/extracted/figures 等（已 gitignore）
```

## 使用方式

本 skill 面向支持 Agent Skills 标准的运行时（Claude Code、Codex、Cursor、OpenClaw 等）。当用户提出"研究报告、深度分析、白皮书、政策研究、行业分析、技术评估、可行性研究"等相关请求时，skill 会自动触发（见 `SKILL.md` frontmatter 的 `description` 字段）。也可以直接输入自然语言请求，如：

> 帮我写一份关于 XX 行业的深度研究报告

Claude 会依次执行阶段 1–9，在每个质量门槛处与用户确认，最终在 `output/` 下产出：
- Markdown 终稿
- 符合 V3.0 规范的标准格式 `.docx`
- `research/figures/` 下的全部架构图与数据图表

### 极速模式

时间 < 3 天或篇幅 < 20 页时，可压缩流程（跳过专题卡片、大纲降到二级标题等），但**阶段 3（事实核验）和阶段 8（红队审查）不可跳过**——详见 `SKILL.md` 「常见问题」一节。

## 外部依赖

本 skill 编排以下工具完成具体执行（均为 skill 层调用外部 CLI/MCP，非本仓库自带）：

| 阶段 | 工具 | 用途 |
|---|---|---|
| 2 | web-search-skill | 通用网页搜索（Tavily + 百度双引擎） |
| 2 | paper-search | 学术论文搜索、下载、全文提取 |
| 2 | MinerU | 文档精准解析（PDF/Office/图片/HTML → Markdown，OCR/表格/公式） |
| 6 | drawio（MCP + 桌面版） | 架构图、流程图，导出 `.drawio` + `.drawio.svg` |
| 6 | fireworks-tech-graph | 技术架构图，16 种模板，导出 `.svg` + `.png` |
| 6 | Mermaid | 简单流程图备选，内联 Markdown |

详细路径、命令示例见 `SKILL.md` 末尾「参考文件」章节。

## 辅助工具安装与配置

本 skill 依赖以下外部工具完成资料搜集、文档解析和架构图绘制。这些工具**不属于本 skill 仓库**，需要单独安装。安装后本 skill 通过**相对路径**（相对于 skill 根目录）调用，无需配置绝对路径。

### 资料搜集工具

| 工具 | 用途 | 安装方式 | 配置说明 |
|------|------|---------|---------|
| **web-search-skill** | 通用网页搜索（Tavily + 百度双引擎），支持关键词搜索、URL 提取、整站爬取、深度研究报告 | [下载](https://github.com/njuzzy1979/web-search-skill)：`git clone https://github.com/njuzzy1979/web-search-skill.git web-search-skill` | 设置环境变量 `TAVILY_API_KEY` 和 `QIANFAN_API_KEY`。脚本位于 `web-search-skill/scripts/search.js` |
| **paper-search** | 学术论文搜索与下载（20+ 数据源），支持多源并发搜索、PDF 下载、全文提取 | `uv tool install paper-search-mcp`，并将 skill 克隆到 Claude Code 技能目录 | CLI 命令为 `paper-search`，无需额外配置。skill 目录为 `paper-search/` |
| **MinerU** | 文档精准解析（PDF/Office/图片/HTML → Markdown），含 OCR 扫描件识别、表格还原、公式提取 | [下载](https://github.com/njuzzy1979/MinerU-Skill)：`git clone https://github.com/njuzzy1979/MinerU-Skill.git mineru` | 设置环境变量 `MINERU_TOKEN`（在 [mineru.net/apiManage](https://mineru.net/apiManage) 申请）。脚本位于 `mineru/scripts/mineru_parse.py` |

### 出图工具

| 工具 | 用途 | 安装方式 | 配置说明 |
|------|------|---------|---------|
| **draw.io 桌面版** | 架构图、流程图绘制，导出 `.drawio` + `.svg` | 从 [draw.io 官网](https://github.com/jgraph/drawio-desktop/releases) 下载安装 | 本机已安装（`D:\Program Files\draw.io`），路径已写入 `tool-paths.json`。其他机器需安装后通过 `where draw.io`（Win）或 `which draw.io`（Linux/macOS）查找路径 |
| **fireworks-tech-graph** | 技术架构图生成，16 种模板，导出 `.svg` + `.png` | 将 skill 克隆到 Claude Code 技能目录 | 依赖 `cairosvg`（`pip install cairosvg`）。脚本位于 `fireworks-tech-graph/scripts/generate-from-template.py` |
| **Mermaid** | 简单流程图备选，内联到 Markdown | 无需安装，Claude Code 原生支持 | 直接在 Markdown 中使用 ` ```mermaid ` 代码块 |

### 路径约定

所有外部 skill 的脚本通过**相对路径**引用，相对于本 skill 的根目录：

```
<skill-root>/
├── deep-research-report/     ← 本 skill
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── web-search-skill/         ← 外部 skill（同级目录）
│   └── scripts/search.js
├── mineru/                   ← 外部 skill（同级目录）
│   └── scripts/mineru_parse.py
├── fireworks-tech-graph/     ← 外部 skill（同级目录）
│   └── scripts/generate-from-template.py
└── paper-search/             ← 外部 skill（同级目录）
    └── SKILL.md
```

Claude Code 在加载 skill 时会自动在技能目录中搜索，因此只要外部 skill 与本 skill 处于同一父目录下，相对路径即可正确解析。

### 工具路径配置

所有外部工具的**绝对路径**集中配置在 `references/tool-paths.json` 文件中。首次使用时，将各工具的 `absolute_path` 字段填写为实际安装路径即可。配置完成后，SKILL.md 中的所有命令会自动读取该文件中的路径。

| 工具 | JSON 键名 | 填写示例 |
|------|----------|---------|
| web-search-skill | `web_search_skill.absolute_path` | `"C:\\Users\\xxx\\.claude\\skills\\web-search-skill\\scripts\\search.js"` |
| MinerU | `mineru.absolute_path` | `"C:\\Users\\xxx\\.claude\\skills\\mineru\\scripts\\mineru_parse.py"` |
| draw.io 桌面版 | `drawio_desktop.absolute_path` | `"D:\\Program Files\\draw.io\\draw.io.exe"` |
| fireworks-tech-graph | `fireworks_tech_graph.absolute_path` | `"C:\\Users\\xxx\\.claude\\skills\\fireworks-tech-graph\\scripts\\generate-from-template.py"` |
| paper-search | 无需配置 | CLI 命令 `paper-search` 已加入系统 PATH |

> **提示**：如果某个工具未安装，对应的 `absolute_path` 保持为空字符串 `""` 即可，skill 在执行时会跳过该工具并使用相对路径或给出提示。

## Word 格式规范

阶段 9 生成的 `.docx` 严格遵循 `references/研究报告格式规范.md`（V3.0，遨天科技编制），涵盖字体体系（标题微软雅黑/TNR、正文宋体/TNR）、标题字号、页边距、全框线表格（含竖线、交替行灰底）、题注格式、页眉页脚（罗马数字/阿拉伯数字分页）、封面设计、参考文献格式（GB/T 7714 适配 + 信源分级 L1–L5）等，转换脚本 `scripts/markdown_to_docx.py` 是唯一的格式实现依据。

## 评估优化记录

本 skill 使用 [darwin-skill](../darwin-skill) 方法论完成过一轮完整评估优化（9 维度评分 + 迭代改进），基线 71.0 分 → 最终 83.8 分，详见 `dashboard.md`。
