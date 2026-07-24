# deep-research-report

面向支持 Agent Skills 标准的运行时（Claude Code、Codex、Cursor、OpenClaw 等）的**深度研究报告编写全流程方法论**。将"写一份研究报告"拆解为 9 个顺序阶段，用证据驱动 + 架构分析的方式，产出有事实核验、有架构图、经过红队审查的正式研究报告（Markdown + 标准格式 Word .docx）。

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

| 阶段 | 产出 | 质量门槛 | 关键特性 |
| ---- | ---- | ---- | ---- |
| 1 项目初始化 | 工作目录、分析框架、题名参数 | 用户确认关键参数 | 智能推断 7 参数；工具路径配置 `tool-paths.json` |
| 2 资料搜集与抽取 | 来源索引表 + MinerU 解析结果 | 每条来源分级 A/B/C/D 并登记 | 三工具协作：web-search + paper-search + MinerU |
| 3 事实核验 | 事实核验台账 | 高风险主张全部核验，强表述降级 | 5 类优先核验主张，6 级核验状态 |
| 4 详细大纲 | 三级标题 + 篇幅建议 + 图表规划 | 用户确认大纲结构 | 必选骨架 + 可选模块池（按研究方法触发） |
| 5 专题研究 | 案例卡片 + 证据包 + card-index | 每个核心论点有卡片支撑 | 4 类卡片（案例/技术/理论/架构），card-index.csv 可追溯 |
| 6 核心架构图 | 架构图/流程图（.drawio + .svg + .png） | 图号、图名、核心要素齐全 + 颜色注册表 | drawio MCP + 桌面版 + fireworks-tech-graph + Mermaid |
| 7 分章写作 | 正文 Markdown + 随写作产出的数据图表 | 6 条内容质量标准（A-F）+ 图表类型合规检查 | matplotlib 全局样式模板 + 自动颜色校验 |
| 8 红队审查 | 红队风险清单 → 逐项处理后更新为最终版 | 高风险 100% 处理，中风险 ≥80% | 逐条过→直接改正文→记录结果→标记 `[红队 R00X]` |
| 9 定稿整合 | 终稿 Markdown + 标准格式 `.docx` | 通过 V3.1 格式规范 12 项输出检查 | md→docx 转换器 v2：38 模块 / ~15,000 行 / 6 阶段管道 + 反硬编码 AST 扫描 |

> **🚫 严禁标密**：本 skill 产出的所有研究报告均基于互联网公开资料。报告的任何位置（封面、页眉、页脚、正文、附录）禁止标注密级。

## 目录结构

```
deep-research-report/
├── SKILL.md                             # 核心方法论（本 skill 的主体）
├── README.md                            # 本文件
├── dashboard.md                         # Darwin 2.0 评估优化记录
├── .gitignore                           # 排除 research/ output/ tests/
├── scripts/
│   ├── md2docx.py                       # md→docx 转换器入口 shim
│   ├── md2docx/                         # 转换器 v2 主包（37 模块）
│   │   ├── cli.py / config.py           # CLI 参数 + YAML 配置
│   │   ├── iotools.py / ir.py / issues.py  # I/O 唯一入口 + IR + Issue 跟踪
│   │   ├── pipeline.py                  # 6 阶段管道编排
│   │   ├── textstage/                   # 规范化 / 清理 / 解析 / 行内
│   │   ├── assemble/                    # 元数据 / 标题 / 图表 / 分页
│   │   ├── render/                      # 渲染（封面/目录/标题/正文/图表/页眉页脚）
│   │   ├── validate.py / report.py / gate3.py  # 校验 + 报告 + 门禁
│   │   └── ...
│   └── chart_checks.py                  # 图表质量自动检查（DPI/颜色/注册表）
├── design/
│   ├── md-to-docx-design-v2/            # 转换器 v2 完整设计（7 份文档）
│   └── chart-quality-constraints/       # 图表质量约束方案（9 份文档 + .mplstyle）
├── references/                          # 阶段执行时按需读取的参考文件
│   ├── tool-paths.json                  # 外部工具路径集中配置
│   ├── 研究报告格式规范.md               # 【权威】Word 格式规范 V3.1
│   ├── claims-ledger-template.csv       # 事实核验台账模板
│   ├── source-index-template.csv        # 来源索引模板
│   ├── card-index-template.csv          # 卡片索引模板
│   ├── color-mapping-rules.yaml         # 项目级颜色映射规则
│   ├── red-team-checklist.md            # 红队审查详细清单
│   ├── writing-standards.md             # 写作标准详细说明（12 条标准）
│   ├── architecture-analysis-guide.md   # 架构分析方法论指南
│   └── md-to-docx-pitfalls.md           # Markdown→Word 转换踩坑记录
├── assets/                              # 静态资源
├── evals/                               # 评估用例
├── research/                            # 运行时工作区（gitignored）
└── output/                              # 运行时产物（gitignored）
```

## 使用方式

当用户提出"研究报告、深度分析、白皮书、政策研究、行业分析、技术评估、可行性研究"等相关请求时，skill 会自动触发。也可以直接输入：

> 帮我写一份关于 XX 行业的深度研究报告

依次执行阶段 1–9，在每个质量门槛处与用户确认，最终产出：
- Markdown 终稿
- 符合 V3.1 规范的标准格式 `.docx`（封面 + TOC 域 + 图表题注 + 页眉页脚 + 全框线表格）
- `research/figures/` 下的全部架构图与数据图表（PNG 300dpi + SVG 源文件）

### 极速模式

时间 < 3 天或篇幅 < 20 页时自动触发：阶段 2-3 合并（边收集边核验）→ 大纲降为二级标题 → 只出 1 张总览图 → 写作只强制执行标准 A（证据密度）+ D（量化优先）→ 红队压缩为 3 项 → 交付 Markdown 终稿。**阶段 3（事实核验）和阶段 8（红队审查）仍不可跳过**。

## md→docx 转换器 v2

阶段 9 使用自研转换器（`scripts/md2docx/`）将 Markdown 转换为符合 V3.1 格式规范的 .docx：

| 特性 | 实现 |
| ---- | ---- |
| 封面 | 标题 + 副标题 + 机构 + 日期 + 版本，无密级字段 |
| 目录 | Word 原生 TOC 域（`begin→instrText→separate→end` 四态），按 F9 更新 |
| 图表目录 | PAGEREF 域混合方案（图表 ≥10 时自动生成） |
| 编号 | 文本显式编号（第一章 / 1.1 / 1.1.1），100% 动态解析 |
| 图片 | PNG 嵌入，`![图X-Y 标题](路径)` 动态解析，零硬编码映射 |
| 表格 | 全框线（含竖线）、交替行灰底、表头重复、垂直居中 |
| 页码 | 摘要罗马数字 + 正文阿拉伯数字，四节方案 |
| 门禁 | 14 项输出校验（密级复检、分页一致性、域三态等） |
| 反硬编码 | `check_no_hardcode.py`（AST 扫描内容硬编码 + 结构违规 + M7 schema 漂移）+ 换样本金标准测试（CI 必跑） |

转换器设计文档位于 `design/md-to-docx-design-v2/`（7 份，含架构/算法/工作流/接口/裁决/审计）。

## 图表绘制质量约束

阶段 6/7 出图遵循统一的图表质量约束方案（`design/chart-quality-constraints/`）：

- **配色**：7 档学术灰度色板 + 单强调色 #D62728，禁止彩色
- **字体**：宋体 + Times New Roman，标签 10pt / 图例 9pt（V3.1 §5.2）
- **一致性**：跨图颜色映射注册表（`color-registry.csv`），同概念同色
- **matplotlib**：全局样式模板（`matplotlib-report-style.mplstyle`），`plt.style.use()` 一键加载
- **检查**：`scripts/chart_checks.py` 自动检查 DPI / 颜色 / 注册表
- **反模式**：禁止 3D 图表、>5 扇区饼图、双 Y 轴滥用等 12 项

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
| **Mermaid** | 简单流程图备选（≤15 节点） | 内联 Markdown，无需安装 |

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
