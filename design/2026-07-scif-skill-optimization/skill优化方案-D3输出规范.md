# D3：输出规范与测试基建方案

> **本文档性质：设计稿，尚未执行。不涉及对本次 SCIF 报告产出的修复。skill 源文件未被改动。**
> 上级文档：`skill优化方案-总览与执行清单.md`

---

## 一、output 目录混乱实况（实测）

```
final-report.docx                0.27 MB   21:56   ← 合规产物（finalize_pipeline→md2docx），但命名不合 §9.2
SCIF_V1.0.conversion-report.md   0.01 MB   21:39
SCIF_V1.0.docx                   3.96 MB   21:38   ← orchestrator 违规手写产物，从未清理
```

两个格式、大小、质量完全不同的 docx 混在同一目录。**用户和后续 Agent 都无法从文件名判断哪个是应交付版本**——而且更糟：违规产物的命名（`SCIF_V1.0.docx`）看起来**比**合规产物（`final-report.docx`）**更像**正式交付物。

---

## 二、根因：命名规范由提示词执行，脚本侧零约束

| 位置 | 实测内容 |
|---|---|
| `stage-9-finalize.md:113-121` | CLI 示例写 `output/报告题名_v1.0.docx`，"报告题名"是**占位字面量**，不是变量 |
| `stage-9-finalize.md:153` | 转换报告命名同样为占位字面量 |
| `finalizer_agent.md:92` | 交接段落把 `output/报告题名_v1.0.docx` **写死在提示词里**，要求 Agent 自行替换 |
| `md2docx/cli.py:189-196` | `_default_output_path()` = 输入路径换扩展名；**md2docx 对"报告题名"和"版本号"一无所知** |
| `finalize_pipeline.py` | 全文无任何 `docx`/`md2docx`/`--cover` 相关代码；管线第 6 步结束就 return，**docx 生成完全在管线之外** |

**结论：命名规范的执行者是 LLM 读提示词后手打路径。** 这是"凡依赖人工执行的规范必被违反"的教科书案例。

---

## 三、figure_gate 完全空转 —— 本次审计最严重的门禁失效

### 3.1 实测：声明了 15 张图，一张都没检查过

真实 `research/outline.md`：
- `:18` 明写 `core_architecture_figures: 15`
- `:93` `figures_manifest:` 之后是 **YAML 列表**（`- fig_id: ...`）
- 条目键名为 `fig_id` / `fig_title` / `fig_type` / `chapter` / `description`

而 `figure_gate.py` 侧：

| 位置 | 行为 | 结果 |
|---|---|---|
| `:99-100` | `if manifest is not None and not isinstance(manifest, dict): return None` | **list 被判格式不符，直接返回 None** |
| `:177-204` | `build_checklist_from_manifest()` 读 `architecture_figures`/`data_figures` 子键与 `figure_id`/`figure_no` | 即便结构改对，**键名也全部落空** |
| `:108-163` | 降级路径从 Markdown 正文提取 `🏗️ **核心架构图**` 标记 | 真实 outline 无此标记，**同样落空** |
| `:357-365` | `checklist` 为空时返回 `passed: True` | **exit 0，PASS** |

**实跑结果**：`[INFO] 未找到图表规划清单 … EXIT=0`

### 3.2 这推翻了原方案的靶子

原方案（D4-6）把全部力气放在 `check_figure_exists()` 新增检查项上，但**该函数在真实项目里一次都没被调用过**（checklist 为空 → 循环 0 次迭代）。

**不修入口，新增再多检查都是死代码。**

同理，`figure_gate.py:285-288` 的"无 `glob_pattern` 无条件放行"——`build_checklist_from_manifest:187` 是无条件 `f"*{fno}*.png"`，归一化后 **15/15 条目全都有 glob_pattern**，该分支在真实项目**一次都没执行到**。删它对真实项目 **0 影响**，降为 P3 纯清理项，**不得计入验收**。

### 3.3 修复方案（D3-1，P0）

1. **修 `extract_manifest_from_yaml` 支持 list 形态**：映射 `fig_id`→`figure_id`、`fig_title`→`title`、`fig_type` 含"架构"→`architecture`。
2. **清单为空时判 FAIL 而非 PASS**——stage9 且 outline 声明了 `core_architecture_figures > 0` 时，空清单直接 FATAL。
3. **与 D1 合并为同一工作项**：figure_gate 的失效根因与 D1 的 outline 键名契约是**同源问题**。若各修各的，`outline_reader`/`figure_gate`/`merge_drafts` 三处会产生三套互不知情的容错逻辑。

### 3.4 验收判据必须重写

原判据"对现存 15 张图跑新门禁，断言 ≥13 张 FAIL"——**实测约 3 张**。若写进方案会导致验收永远不通过，反向逼迫实施者放宽门禁。

**改为逐检查项列出预期命中集合**（可复现白盒断言）：

| 断言 | 预期 |
|---|---|
| `total == 15` | 而非当前的 0 |
| `invalid >= 1` 且能定位到 `3-1` 的 325px 宽度问题 | 现有规则 |
| `10-1` / `8-1` 触发 0-edge 反伪图告警 | 新增规则 |
| 几何重叠命中 `{11-1, 3-2, 4-1, 7-2, 12-1, 4-2}` 六张 | 新增规则 |

### 3.5 R1 实测的新增检查命中率（据此调整优先级）

| 新增检查 | 实测 FAIL 数 | 判定 |
|---|---|---|
| vertex≥3 且有 edge | 2（`10-1` vertex=108/edge=0、`8-1` vertex=16/edge=0）；vertex 最小值 6 | 阈值过松，但 0-edge 有效 |
| fontSize<12 | **0**（实际最小 12/14/16） | **完全空转 → 降 WARN** |
| 内嵌题注 | **0**（题注统一在 Markdown） | **完全空转 → 降 WARN** |
| 几何重叠 >10% | 6 张 | **唯一有效项** |

**以 0 命中的检查作为门禁核心，属于为不存在的问题写代码。**

### 3.6 实施注意

- **正面确认**：15 个 `.drawio` 实测 `plain=True/compressed=False`，`ET.fromstring()` 15/15 成功，**无 deflate+base64**。XML 解析方案**不需重写**。
- **几何重叠须排除容器类**（`swimlane`/`container=1`/`group`）与图例块，否则 `11-1` 的 50 对里大量是正常矩阵单元嵌套，会淹没真实缺陷。
- **反伪图判据须排除 4 张无同名 drawio 源的 matplotlib PNG**（`1-1-timeline`、`10-2-TRL-heatmap`、`11-2-radar`、`3-4-OODA-2.0`），否则误伤。
- **`:252` 的 dpi 短路**：`if dpi[0] and ...` 使 dpi 元数据为 `(0,0)` 的 **11/19 张 PNG 被静默放行**。应改为 dpi 缺失时报 WARN。
- **PNG 校验逻辑在函数内出现两遍**（主 glob 分支 `:231-257` + 模糊回退分支 `:262-284`）且**不等价**（主分支多 `w<1 or h<1` 检查）。**只改一处则另一处成绕过路径**。建议先抽出 `_validate_png(path) -> list[str]` 单一函数。
- **`stage-6-diagrams.md` 全文 208 行，`figure_gate` 仅 `:18` 表格单元格提及**，6 处 `python` 调用无一是 figure_gate。**必须内嵌进 `finalize_pipeline.py` 成为第 0 步**，否则修了脚本也没人调。

---

## 四、delivery_checklist 对 output 目录零感知（D3-0，P0）

**实测**：

```
delivery_checklist_check.py 中 output_dir / output/ 命中数：0

def run_delivery_checklist(
    merged_file, glossary_path=None, drafts_dir=None, outline_path=None,
    figures_dir=None, redteam_diff_path=None, log_path=None,
) -> dict:
```

七个入参**全部指向 research 侧**，脚本对交付目录完全没有感知能力。这是 D3-2/D3-4 的**前置条件**——不补入参，后续所有 output 相关门禁都无处落脚。

**方案**：新增 `output_dir` 入参并贯通到 `finalize_pipeline.py` 调用点。新增检查项须显式标注**不进 `manual_required`**（`overall_pass` 在 `:363-368` 按 status 过滤，非硬编码，无需改动）。

---

## 五、命名下沉（D3-2，P1）

### 5.1 真实风险与被夸大的风险

**被夸大的**：原方案担心中文题名导致非法字符/超长。实测真实 `report_title`（38 字符）：
- Windows 非法字符 `<>:"/\|?*` **命中 0 个**
- 完整路径 86 字符、归档路径 111 字符，**远低于 MAX_PATH 260**

→ `sanitize_filename_stem` 保留但**降为 P1**，截断阈值应按 **GBK 字节 ≤120** 而非字符数。

**真风险**：`output\SCIF_V1.0.conversion-report.md` 的 `:4` 与 `:114` **两处硬编码绝对路径**引用 docx。一旦重命名立即失效。

→ `emit_delivery` **必须同时重命名 docx 与 conversion-report 且 stem 严格一致**，并回写这两处路径。

**另一实测坑**：该 conversion-report 的转换时间是 **`2000-01-01 00:00:00`**，说明 md2docx 时间戳本身有 bug。归档目录的 `<stamp>` **必须用 `datetime.now()` 现取**，禁止复用该时间源，否则所有归档目录撞成同一个 `_archive/20000101-000000/`。

### 5.2 符号命名约束

`finalize_pipeline.py` 中 `output` 一词有 **17 处**，全部指 `output_path`（合并后 **Markdown** 路径），与交付目录是两回事。

**新增符号一律加 `delivery_` 前缀**（`delivery_dir`/`delivery_docx_path`），`--output-dir` 的 help 文本须显式区分于既有 `--output`。

### 5.3 骨架 docx 的命名与落位（D1-8 引入的新产物，纳入本节治理）

D1-8 会在**阶段 4** 新增两个产物。为避免重演 §一"两个 docx 混在 output 目录、且违规产物看起来更像正式交付物"的旧事故，定案如下：

| 产物 | 定案路径 | 理由 |
|---|---|---|
| 骨架 docx | `research/outline-skeleton-preview.docx` | **不进 `output/`**——`stage-9-finalize.md:147` 定义 `output/` 为"最终交付物"目录。骨架是阶段 4 的中间确认件，进 `output/` 必然与终稿混淆 |
| 骨架中间 md | `research/drafts/.outline-skeleton.md` | 点号前缀，与既有 `.degradation-log.jsonl`/`.provenance.jsonl` 同款隐藏件约定 |

**三条强制约束**：

1. **文件名必须含 `skeleton` 与 `preview` 双重语义标识**，与交付物命名模式 `<报告题名>_v1.0.docx` 无任何前缀重叠——确保人和 glob 都能一眼区分。
2. **中间 md 不得命名为 `final-report*`**，否则会被阶段 9 的 glob 误吃（`find_draft_files` 的章级通配符回落机制见 D1 §3.4）。
3. **阶段 9 `emit_delivery` 若检出骨架文件仍在，只 WARNING 列出交人判断，不自动删除、不自动归档**——与 §六第 3 条对 `SCIF_V1.0.docx` 的处置口径完全一致（`_is_skill_artifact` **禁止**基于文件名正则判定）。

**与 D2-7 的关系**：骨架 docx 不进入 D2-7 的 docx 回读门禁范围（走独立入口、不经 `finalize_pipeline.py`，第 7 步只对 `emit_delivery` 实际写出的路径清单生效）。**注意 D2-7 自身有一处漏检会让骨架"通过"门禁**（把 `Heading 2` 文本当正文收集），详见 D2 文档 §3 D2-7 处的标注与 D1 文档 §9.4.4。

---

## 六、归档机制（D3-4，P2）—— 按文件名判定会颠倒

**致命陷阱**：若 `_is_skill_artifact` 按文件名模式（如 `*_v*.docx`）判定：

| 文件 | 实际性质 | 按文件名判定的结果 |
|---|---|---|
| `SCIF_V1.0.docx` | 违规手写产物，**是整个事故的物证** | **命中 → 被静默归档移走** |
| `final-report.docx` | 真正的合规产物 | 不匹配 `_v<版本>` → **反而不被识别** |

**判定结果与事实完全颠倒。**

**定案**：
1. `_is_skill_artifact` **只能**基于"本次 `emit_delivery` 实际写出的路径清单"或 sidecar provenance 记录判定，**绝对禁止**基于文件名正则。无记录的一律视为用户文件，不动。
2. `archive_stale_outputs` **首版只报告不移动**，移动需 `--archive-stale` 显式开启。
3. 对 `SCIF_V1.0.docx` 这类文件，正确处置是 delivery_checklist **显式 WARN 列出交人判断**，而非归档掉。

---

## 七、测试基建 —— fixture 失真是缺陷从未被测出的直接原因

### 7.1 实证对比

**现有 fixture** `scripts/md2docx/tests/test_fixtures/multi-chapter.md:19-25`：

```
## 多智能体协同感知架构          ← H2 章标题

本章提出四层三域的多智能体...    ← 紧跟正文

### 四层架构设计                 ← 下一级是 H3
```

**真实产物** `research/drafts/final-report.md`：

```
##  第 1 章：导论：空间认知智能的时代命题     ← merge_drafts 插入的章容器 H2
##  本章结论                                  ← 草稿文件首行，也是 H2  ★致命组合★
### 摘要
...
## 第 2 章：理论范式革命：从空间计算到空间认知
## 本章结论                                  ← 再次
（13 章全部如此，共 13 个 `## 本章结论`）
```

**现有 fixture 完全没有覆盖真实产物的核心形态。**

这也说明："目录出现 13 个重复本章结论"**不是** orchestrator 手写脚本独有的 bug，而是 `assemble_merged()` + 真实草稿模板共同产生的**结构性形态**——只是从未有任何 fixture 或测试见过它。

### 7.2 Owner 裁决

`tests/test_e2e_draft_to_docx.py` 由 **D1 为唯一 owner**。D3 曾计划建同一路径文件（4 用例）与 D1（11 用例）冲突——**同一文件两套用例，谁先落地谁被覆盖**。

**分工**：D3 只提供 fixture（`tests/fixtures/e2e-merge/`），不建测试文件。

### 7.3 fixture 设计要点

必须真实还原 `merge_drafts` 产物形态：
- 每份分章草稿首个 H2 逐字为 `## 本章结论`
- **不写章容器 H2**（由合并器生成）
- 含多章、图表引用、附录、前后置件
- 配套 outline.md 用**权威键名**（`chapter_no`/`chapter_title`/`sections`）

**刻意逐字复刻 `writer-template.md` 骨架，防止为让测试变绿而削弱真实性。**

### 7.4 结构不变量断言清单

| # | 断言 | 捕获的缺陷 |
|---|---|---|
| I1 | 每个 Heading 1 到下一个 Heading 1 之间必须有非空正文 | **直接对应用户投诉** |
| I2 | Heading 1 数量 == outline 声明章数 | 伪章 |
| I3 | 不得出现文本重复的 Heading 1 | 13 个"本章结论" |
| I4 | 各 `ch{XX}-*.md` 内容在合并产物中出现次数恰为 1 | **重复拼接 bug** |
| I5 | 图表编号章号前缀与所属章一致 | 图号错位 |
| I6 | lookup size > 0 且 CHAPTER 数 == 声明章数 | 白名单空转 |
| I7 | 归一化对已合规 outline 为恒等变换 | 幂等性 |

### 7.5 接入方式

- 新用例并入既有 `tests/` 目录，沿用现有 `conftest.py`
- 提供一键自检命令：`python scripts/selfcheck.py --level full`，覆盖 `tests/` 与 `scripts/md2docx/tests/` 两套
- `test_structured_fixture.py` 已用权威键名，是归一化幂等性的**现成回归证据**，无需新建

---

## 八、未经交叉验证的风险

1. `extract_manifest_from_yaml` 改造后对**混合形态**（部分条目 dict、部分 list）的处理未实测。
2. 归档机制的 provenance 依赖 D2-6 的 sidecar 先落地，存在跨方案时序依赖。
3. `_validate_png` 抽取重构会触及两个分支的既有行为差异（主分支多 `w<1 or h<1`），需确认合并后不改变既有判定结果。
