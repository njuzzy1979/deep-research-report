# deep-research-report

面向支持 Agent Skills 标准的运行时（Claude Code、Codex、Cursor、OpenClaw 等）的**深度研究报告编写全流程方法论**。将"写一份研究报告"拆解为 9 个顺序阶段，用证据驱动 + 架构分析的方式，产出有事实核验、有架构图、经过红队审查的正式研究报告（Markdown + 标准格式 Word）。

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

| 阶段 | 产出 | 质量门槛（示例） | 关键特性 |
|---|---|---|---|
| 1 项目初始化 | 工作目录、分析框架、题名参数 | 用户确认关键参数 | 智能推断 7 参数，≤2 项标 ⚠️；工具路径配置（`tool-paths.json`） |
| 2 资料搜集与抽取 | `research/sources/`、来源索引表、MinerU 解析结果 | 每条来源分级 A/B/C/D 并登记 | 三工具协作：web-search + paper-search + MinerU |
| 3 事实核验 | 事实核验台账（claims-ledger） | 高风险主张全部核验，强表述降级 | 5 类优先核验主张，6 级核验状态 |
| 4 详细大纲 | 三级标题 + 篇幅建议 + 证据源 + 图表规划 | 用户确认大纲结构 | 必选骨架 + 可选模块池（按研究方法触发） |
| 5 专题研究 | 案例卡片 + 证据包 + card-index 索引 | 每个核心论点有卡片支撑，claim_id 绑定台账 | 4 类卡片，证据包 = claim_id + 来源，card-index.csv 可追溯 |
| 6 核心架构图 | `research/figures/` 下架构图/流程图 | 图号、图名、核心要素齐全 | drawio MCP + 桌面版导出 SVG + fireworks-tech-graph |
| 7 分章写作 | 正文 Markdown + 随写作产出的数据图表 | 证据密度、主张-证据-推理链达标 | 编号使用规范（7.2），6 条内容质量标准（A-F） |
| 8 红队审查 | 红队风险清单 → 逐项处理后更新为最终版 | 高风险 100% 处理，中风险 ≥80% | 8.3 风险清单处理闭环：逐条过 → 直接改正文 → 记录结果 → 标记 `[红队 R00X]` |
| 9 定稿整合 | 终稿 Markdown + 标准格式 `.docx` | 通过 V3.0 格式规范 12 项输出检查 | 一体化转换脚本（Markdown 清理 → Word 生成 → 图片嵌入） |

**图表分两批出**：
- **核心架构图**（总览图/架构图/流程图）在写作前完成——依据阶段 1.3 的分析框架即可确定图号和图名，是报告的骨架。
- **数据图表**（对比表/趋势图/市场份额图等）随写作按章产出——必须绑定写作时的具体数据和上下文，阶段 4 只规划"方向"，图号在阶段 7 写作时才分配，避免图表与文字脱节。

## 目录结构

```
deep-research-report/
├── SKILL.md                          # 核心方法论（本 skill 的主体，加载入口）
├── README.md                         # 本文件
├── dashboard.md                      # Darwin 2.0 评估优化记录
├── scripts/
│   └── markdown_to_docx.py           # Markdown → 标准格式 Word 一体化转换脚本
├── references/                       # 阶段执行时按需读取的参考文件
│   ├── tool-paths.json               # 外部工具路径集中配置
│   ├── 研究报告格式规范.md            # 【权威】Word 格式规范 V3.0（遨天科技编制）
│   ├── word-format-spec.md           # 旧版格式规范 v1.0（已归档）
│   ├── claims-ledger-template.csv    # 事实核验台账模板
│   ├── source-index-template.csv     # 来源索引模板
│   ├── card-index-template.csv       # 卡片索引模板
│   ├── red-team-checklist.md         # 红队审查详细清单
│   ├── writing-standards.md          # 写作标准详细说明（12 条标准）
│   ├── architecture-analysis-guide.md # 架构分析方法论指南
│   └── md-to-docx-pitfalls.md        # Markdown→Word 转换踩坑记录
├── evals/
│   └── evals.json                    # 评估用例
├── assets/                           # 静态资源
├── output/                           # 运行时产物（已 gitignore）
└── research/                         # 运行时工作区（已 gitignore）
```

## 使用方式

当用户提出"研究报告、深度分析、白皮书、政策研究、行业分析、技术评估、可行性研究"等相关请求时，skill 会自动触发（见 `SKILL.md` frontmatter 的 `description` 字段）。也可以直接输入自然语言请求，如：

> 帮我写一份关于 XX 行业的深度研究报告

依次执行阶段 1–9，在每个质量门槛处与用户确认，最终在 `output/` 下产出：
- Markdown 终稿
- 符合 V3.0 规范的标准格式 `.docx`
- `research/figures/` 下的全部架构图与数据图表

### 极速模式

时间 < 3 天或篇幅 < 20 页时，可压缩流程（跳过专题卡片、大纲降到二级标题等），但**阶段 3（事实核验）和阶段 8（红队审查）不可跳过**——详见 `SKILL.md` 「常见问题」一节。

### 工具路径配置

首次使用时，编辑 `references/tool-paths.json`，将各工具的 `absolute_path` 字段填写为实际安装路径（留空表示该工具未安装）。配置完成后所有命令自动读取。

## 外部依赖

### 资料搜集与抽取工具

| 工具 | 用途 | 安装 / 下载 | 配置说明 | 测试状态 |
|------|------|------------|---------|:--:|
| **web-search-skill** | 通用网页搜索（Tavily + 百度双引擎），5 个子命令 | [下载](https://github.com/njuzzy1979/web-search-skill)：`git clone https://github.com/njuzzy1979/web-search-skill.git` | 环境变量 `TAVILY_API_KEY` + `QIANFAN_API_KEY`。脚本 `web-search-skill/scripts/search.js` | ✅ |
| **paper-search** | 学术论文搜索与下载（20+ 数据源），3 个子命令 | `uv tool install paper-search-mcp` | CLI 命令 `paper-search`，无需额外配置 | ✅ |
| **MinerU** | 文档精准解析（PDF/Office/图片/HTML → Markdown），含 OCR/表格/公式 | [下载](https://github.com/njuzzy1979/MinerU-Skill)：`git clone https://github.com/njuzzy1979/MinerU-Skill.git mineru` | 环境变量 `MINERU_TOKEN`（在 [mineru.net/apiManage](https://mineru.net/apiManage) 申请）。脚本 `mineru/scripts/mineru_parse.py` | ✅ |

### 出图工具

| 工具 | 用途 | 安装 / 下载 | 配置说明 | 测试状态 |
|------|------|------------|---------|:--:|
| **drawio（MCP）** | 架构图、流程图生成 `.drawio` | 无需安装，Claude Code MCP 内置 | `mcp__drawio__create_diagram` | ✅ |
| **draw.io 桌面版** | `.drawio` → `.svg` 导出 | 从 [draw.io 官网](https://github.com/jgraph/drawio-desktop/releases) 下载安装 | 本机路径 `D:\Program Files\draw.io`，已写入 `tool-paths.json`。其他机器通过 `where draw.io` / `which draw.io` 查找 | ✅ |
| **fireworks-tech-graph** | 技术架构图，16 种模板，导出 `.svg` + `.png` | 将 skill 克隆到技能目录 | 依赖 `cairosvg`（`pip install cairosvg`）。脚本 `fireworks-tech-graph/scripts/generate-from-template.py` | ✅ |
| **Mermaid** | 简单流程图备选 | 内联 Markdown，无需安装 | ` ```mermaid ` 代码块 | ✅ |

### 路径约定

所有外部 skill 脚本通过**相对路径**引用：

```
<skill-root>/
├── deep-research-report/     ← 本 skill
├── web-search-skill/         ← 外部 skill（同级目录）
├── mineru/                   ← 外部 skill（同级目录）
├── fireworks-tech-graph/     ← 外部 skill（同级目录）
└── paper-search/             ← 外部 skill（同级目录）
```

绝对路径统一配置在 `references/tool-paths.json` 中，跨机器部署时只需修改该文件。

## Word 格式规范

阶段 9 生成的 `.docx` 严格遵循 `references/研究报告格式规范.md`（V3.0，遨天科技编制），涵盖字体体系（标题 微软雅黑/TNR、正文 宋体/TNR）、标题字号、页边距、全框线表格（含竖线、交替行灰底）、题注格式、页眉页脚（罗马数字/阿拉伯数字分页）、封面设计、参考文献（GB/T 7714 适配 + 信源分级 L1–L5）等。转换脚本 `scripts/markdown_to_docx.py` 是唯一的格式实现依据，整合了 Markdown 清理 → Word 生成 → 图片嵌入 → 表题注修复的全流程。

## 工具验证记录

2026-07-17 完成全部 5 个外部工具实测验证：

| 工具 | 测试内容 | 结果 |
|------|---------|:--:|
| web-search-skill | 搜索"中国商业航天 2025 政策"，百度引擎 | ✅ |
| paper-search | arxiv 搜索 "commercial space industry chain" | ✅ |
| MinerU | 解析 PDF 论文（1.9MB）+ DOCX 报告（72KB） | ✅ |
| draw.io MCP | Mermaid 流程图生成 `.drawio` | ✅ |
| draw.io 桌面版 | SVG 导出（32KB，含内嵌 XML），v30.2.6 | ✅ |
| fireworks-tech-graph | architecture 模板 SVG 生成 + 2x PNG 导出 | ✅ |

## 评估优化记录

本 skill 使用 [darwin-skill](../darwin-skill) 方法论完成两轮评估优化：

| 轮次 | 日期 | 阶段 | 分数 | Δ | 主要改进 |
|------|------|------|------|:--:|---------|
| 第 1 轮 | 2026-06-10 | 基线 → R2 | 71.0 → 83.8 | +12.8 | 检查点设计、失败模式编码、反例黑名单 |
| 第 2 轮 | 2026-07-17 | 基线 → R3 | 81.6 → 86.8 | +5.2 | P0 runtime 中立、dim5 路径执行指引、dim7 去重、dim8 全量实测 |

第 2 轮 final 9 维度评分：

| dim | 维度 | 得分 | dim | 维度 | 得分 |
|:---:|------|:---:|:---:|------|:---:|
| 1 | Frontmatter 质量 | 9/10 | 6 | 资源整合度 | 9/10 |
| 2 | 工作流清晰度 | 9/10 | 7 | 整体架构 | 9/10 |
| 3 | 失败模式编码 | 9/10 | 8 | 实测表现 | 8/10 |
| 4 | 检查点设计 | 9/10 | 9 | 反例与黑名单 | 9/10 |
| 5 | 可执行具体性 | 9/10 | — | **加权总分** | **86.8** |

> 详见 `dashboard.md`。
