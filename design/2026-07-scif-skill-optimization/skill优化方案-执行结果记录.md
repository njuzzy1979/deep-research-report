# deep-research-report skill 优化方案 · 执行结果记录

> 执行日期：2026-07-30
> 执行依据：`skill优化方案-总览与执行清单.md` 及 D1/D2/D3/D4 四份设计文档
> 目标仓库：`C:\Users\张\.claude\skills\deep-research-report`（独立 git 仓库）
> baseline commit：`82e736d`
> 本次产生 commit：`64f9738` … `8175768`（共 14 个）
> 最终回归：`python scripts/selfcheck.py --level full` → **PASS**（tests/ 368 passed + scripts/md2docx/tests/ 12 passed + 8 项脚本冒烟全 OK）

---

## 一、总体结论

| 指标 | 结果 |
|---|---|
| 设计清单子项总数 | 30 |
| **完成** | **30**（P0 8 项、P1 11 项、P2 5 项、P3 3 项，另含 3 项方案内附带修复项） |
| 部分完成 | 0 |
| 跳过 | 0 |
| 测试基线变化 | baseline **297 passed + 4 failed** → 收尾 **380 passed + 0 failed** |
| 新增测试用例 | 83（4 个新测试文件 + 既有文件增补） |
| 新增脚本 | 4（`outline_structure_gate.py`、`outline_skeleton.py`、`install_project_hooks.py`、`selfcheck.py`）+ 1 个 hook 脚本 |
| SCIF 项目本体（`research/`、`output/`） | **零改动**（已核实：全部文件时间戳仍为 2026-07-29，未产生任何新文件） |

**最强验收信号已达成**：`pytest tests/test_finalize_pipeline.py` 由方案预测的 **4 failed → 17 passed**（实际增补 D2-8/D2-7/D3-2/D3-4 用例后为 35 passed）。

---

## 二、逐项执行记录

### 第 1 批（commit `64f9738`）

| 编号 | 状态 | 文件改动 | 测试验证 |
|---|---|---|---|
| **D1-0** | ✅ 完成 | `md2docx/issues.py` 删除 `:100-101` 被同名覆盖的 `W-HDR-04`/`W-HDR-05` | 验证两码位现均解析为 outline 结构语义定义（`:153`/`:159` 版本），码位总数 44 |
| **D4-10** | ✅ 完成 | `model_profile.py` 补回丢失的 `format_text_report()` 函数定义头 | `python scripts/model_profile.py` 无参调用由 **必抛 NameError** 转为正常输出 tier B 配置，EXIT=0 |
| **D1-A** | ✅ 完成 | `writing_quality_check.py` `CHAPTER_HEADING_PATTERN` 在"第""章"两侧各补 `\s*` | 5/5 正例命中（含此前漏掉的 `## 第 1 章：` 带空格形态），负例 `## 本章结论` 正确不命中 |
| **D3-0** | ✅ 完成 | `delivery_checklist_check.py` 新增 `output_dir`/`delivery_paths` 入参；`finalize_pipeline.py` 加 `--output-dir` 并贯通 | 297 passed，无新增失败。符号一律用 `delivery_` 前缀以区别既有 17 处 `output_path`（合并 Markdown 路径） |

### 第 2 批（commit `abfb755`、`032f6ee`、`ac36bbf`）

| 编号 | 状态 | 文件改动 | 测试验证 |
|---|---|---|---|
| **D1-1** | ✅ 完成 | 新增 `outline_reader.normalize_outline_structure()` + `_coerce_chapter_no()`；贯通 4 个消费端入口；**删除** `finalize_pipeline.py:191-204` 就地 mutate 适配层；修正 merge 失败文案 | **A1 达成：4 failed → 17 passed**。真实 outline 实测 lookup size **0 → 16**（CHAPTER 13 / FRONT_MATTER 2 / APPENDIX 1）；**A7 幂等**：`normalize(normalize(x)) == normalize(x)` 为 True |
| **D1-5** | ✅ 完成 | `merge_drafts.py` 新增 `_demote_headings()`（跳过代码块、上限钳制 H6）+ 同章内文件去重 | 真实 drafts 实测：「本章结论」作为 H2 **13 → 0**、作为 H3 为 13；**相邻 H2 对数 = 0**（事故形态消除）；**A2** 各 `ch*.md` 出现次数全部恰为 1；**A6** 无重复章容器 H2 |
| **D2-8** | ✅ 完成 | `finalize_pipeline.py` 新增 `_promote_partial()`/`_partial_path_for()`/`_mark_stale_output()`/`_derive_run_id()`；全程写 `.partial`，全通过才原子转正 | 新增 4 用例：失败时正式产物名不存在而 `.partial` 保留、成功时 `.partial` 转正消失、run_id 确定性（12 位 hex）、失败时旧产物改名 `.stale-<run_id>` |
| **D3-1** | ✅ 完成 | `figure_gate.py` 新增 `_normalize_list_manifest()`（支持 list 形态 + 键名映射）、`_declared_architecture_figure_count()`；空清单判 FAIL | 真实 outline 实测：`total` **0 → 15**、found 15、**invalid 1 精确定位到 D3 §3.4 预期的 `3-1`（325px < 1102px）**、`passed` 由**恒 True** 转为 False |
| **D3-5** | ✅ 完成 | 删除 `check_figure_exists` 的"无 glob_pattern 即 found=True/valid=True"无条件放行分支 | 对真实项目 0 影响（归一化后 15/15 条目均有 glob_pattern），按方案要求**不计入验收** |

### 第 3 批（commit `f75039d`、`e92079e`、`54ed312`、`e9c4764`）

| 编号 | 状态 | 文件改动 | 测试验证 |
|---|---|---|---|
| **D1-2** | ✅ 完成 | `headings.py:482` 静默返回改为按声明数分流：`E-OL-03`(ERROR)+降级台账 / `I-OL-04`(INFO)；新增 `_count_declared_entries()`；补 `record_degradation` import 兜底块；`E-OL-03` 纳入 `STRICT_ESCALATION_EXEMPT_CODES` | 两分支各自正确触发（含 level 与文案）。新码位 `E-OL-03`/`I-OL-04` 均为全新码位，避开 D1-0 删除的死码位 |
| **D1-6** | ✅ 完成 | 新增 `--structure-overlay=off\|warn\|strict`（载体 `BehaviorFlags.structure_overlay`，登记进 `BEHAVIOR_ENUM_FIELDS`）；W-HDR-04 **按 kind 聚合** | 三态实测：`off` 零 issue；`warn` 下 6 个未命中聚合为 **2 条** W-HDR-04（而非 6 行）+ 1 条 I-HDR-08；`strict` 下 4 条 E-HDR-09 且 SUBSECTION 仍放行 |
| **D1-9** | ✅ 完成 | **新增** `scripts/outline_structure_gate.py`（S1-S6 + 三态）；`stage-4-outline.md` 新增门禁节、质量门槛加 2 项、CP3 文案扩写；`outline_architect_agent.md` 补 section 级产出要求（步 5） | **新增 15 用例**。真实 outline 实测：S1/S2/S4/S6 通过，**S3 正确捕获 13 章全部 0 节**（N4 根因），S5 告警标题集合不一致；warn 下 EXIT=0（存量不阻断）、strict 下 EXIT=1、off 下 EXIT=0 |
| **D2-7** | ✅ 完成 | `finalize_pipeline.py` 新增 `verify_docx_structure()` + 管线第 7 步（可选步）；FAILURE_STEPS 由 6 扩为 7 | **新增 6 用例**。五形态实测：**骨架无正文 pass=False（原设计漏检项已修）**、事故形态 False、重复章标题 False、健康产物 True、章数不符 False |
| **D3-2** | ✅ 完成 | 新增 `append_provenance()`/`load_provenance_paths()`/`sanitize_filename_stem()`/`emit_delivery()`；sidecar `research/.provenance.jsonl` | **新增 5 用例**：成功后写入、append-only 累积、拒绝非 hex run_id、GBK 字节截断、docx 与转换报告 stem 一致且路径回写 |
| **D3-4** | ✅ 完成 | 新增 `archive_stale_outputs()`，**首版只报告不移动** | **新增 3 用例**，含核心反例断言：违规的 `SCIF_V1.0.docx` 必须落 `unknown_files`、合规的 `final-report.docx` 落 `known_artifacts`、**两个文件都不被移动** |

### 第 4 批（commit `6596016`、`16a2a04`、`00adbe9`、`673e1fc`、`1bc50b9`、`8175768`）

| 编号 | 状态 | 文件改动 | 测试验证 |
|---|---|---|---|
| **D2-1** | ✅ 完成（**原文由本次撰写**） | `SKILL.md` 反例清单**一次性**追加第 21/22 条 | 实测第 21/22 条各出现 **1 次**（编号冲突防护生效，未产生两个第 21 条） |
| **D2-2** | ✅ 完成（**原文由本次撰写**） | `SKILL.md` 引用块（简版）+ `multiagent-orchestration.md` 新增"失败处置红线"独立节（全版）：允许四件 / 严禁六件 + 确定性失败禁止重试 | 文档一致性测试全绿。两节均**显式标注效力接近零**并列出 5 个真正有效的产物层机器门禁 |
| **D2-5** | ✅ 完成 | `finalizer_agent.md` 路由表改为**按调用点二级键**（19 调用点归为看 `failure_reason` 的二级判据）+ verify_docx 行；`stage-9-finalize.md` 补可执行路由动作摘要 | **验收判据按方案要求重设计**：原判据 `grep failure_step ≥ 1` 已满足、零证伪能力；改为断言含"回炉"路由动作文本——**实测由 0 处增至 7 处** |
| **D4-12** | ✅ 完成 | `multiagent-orchestration.md` §5 补齐 4 个有名无实门禁（`G(收集)`/`G(核验)`/`G(卡片)`/`G(出图)`）；12→13 项跨 5 处订正 | 实测剩余"12 项交付清单"表述 **归零**。刻意保留 stage-9 的"12 项 → 13 项清单"历史沿革与 README:186 的图表反模式 12 项（与交付清单无关） |
| **D1-8** | ✅ 完成 | **新增** `scripts/outline_skeleton.py` | **新增 13 用例**。**U7 硬约束已遵守**：本项在 D1-9 完成并在真实 outline 上验证后才启动；步 4（按 kind 分级）随 D1-6 落地。实测合规 outline（2 章 4 节）EXIT=0，回读 docx 确认 `Heading 1`=2 章、`Heading 2`=4 节、封面与 TOC 域就位；**真实 SCIF outline（13 章 0 节）被正确拒绝**（EXIT=1） |
| **D1-7** | ✅ 完成 | **新增** `tests/test_e2e_draft_to_docx.py` + `tests/fixtures/e2e-merge/`（outline + 2 份草稿 + source-index） | **新增 12 用例**，覆盖 I1-I7/A2-A7 与全链路（合并 → md2docx → python-docx 回读）。fixture **刻意逐字复刻 writer-template 骨架**，并专设 2 条"fixture 真实性自检"用例防止未来为让测试变绿而削弱真实性 |
| **D2-9** | ✅ 完成 | **新增** `.claude/hooks/guard_docx_bypass.py`、`.claude/hooks-template/settings.fragment.json`、`scripts/install_project_hooks.py`；`stage-1-init.md` §1.2 挂接、`stage-9-finalize.md` §9.0.0 幂等补下发 | **新增 21 用例**，含 §5.4 第 5 条要求的**误伤率测试**：违规样本 4 类全部 deny，合法样本（md2docx 调用、**骨架生成器**、D2-7 只读回读、无关命令）全部放行；合并不覆盖用户配置、幂等无重复条目、拒绝覆盖坏 JSON |
| **D4-9** | ✅ 完成 | `stage-2-collection.md` 门槛按 source_type **分桶** + 新增 §2.1.1 可信度升级路径；`source_collector_agent.md` 第 8 条初始分级不得默认全 D | 实施注意已遵守：CSV 字段行两处重复出现，**未做全文替换**；未误引"收尾自检清单项"为门槛 |
| **D4-8** | ✅ 完成 | `multiagent-orchestration.md` 新增 §4.1：失败分类表 + 4 类外部 CLI 超时上限与规定动作 + MinerU 专项 | **MinerU 澄清已遵守**：明确本项要补的不是分片（已内置），而是"分片后单片仍超时无规定动作"；工具路径引用带 tool-paths.json 解析步骤 |
| **D4-3** | ✅ 完成 | `multiagent-orchestration.md` 新增 §7.5.1（7 项严格度 × A/B/C） | **定案已遵守**：并入 §7.5 作为 7.5.1，**未新开"第三维"**（与既有"二维决策矩阵""正交的第二维""两者独立生效"三处措辞不冲突）。已标注纯文档约定、不计入有效交付项 |
| **D3-3 / D4-6** | ✅ 完成 | `stage-6-diagrams.md` 新增 §6.9（figure_gate 可执行调用点 + 判定口径表）、质量门槛与 CHECKPOINT 文案；`architecture_chart_agent.md` 补自检节与 2 条 MUST NOT | 修掉"有门禁名、无可执行调用点"：此前 figure_gate 只出现在 §一表格单元格，6 处 python 调用无一是它 |
| **D1-5 文档** | ✅ 完成 | `stage-7-writing.md` 层级表后补层级下沉说明（三行对照表 + 成因） | R1 红线本体未改（符合裁决）；明确"作者无需也不应书写章标题" |

### 方案内的附带修复项（随主项一并落地）

| 项 | 出处 | 落实情况 |
|---|---|---|
| D1-1 归一化对非空 `subsections` 会产出 `section_title=None` | 总览 §七第 4 条 / D1 §十第 4 条 | ✅ 已按裁决**不做跨层级映射**——`sections` 与 `subsections` 是独立层级（`outline_reader` 与 `outline_title_extract` 均分别消费），整体赋值会使 `section_title` 取到 None。"章无 sections 时的草稿查找兜底"下沉为 `_chapter_section_entries()` 的合并期局部构造，**不回写 structure**（避免虚拟 section 标题覆盖 lookup 中的 CHAPTER 条目） |
| D2-7 把 `Heading 2` 文本当正文收集 | 总览 §七第 4 条 / D1 §9.4.4 / D2 §3 标注 | ✅ 已修：`elif prev is not None and not style_name.startswith("Heading")`。已加专门用例断言"只有骨架无正文"的 docx 被判 FAIL |
| `_validate_png` 在两个分支重复且不等价 | D3 §3.6 | ✅ 已抽出单一函数，口径取较严的主分支（含 `w<1 or h<1`）——只改一处则另一处成绕过路径 |
| `figure_gate` dpi 短路静默放行 | D3 §3.6 | ✅ 已修（见下方偏差说明） |
| D4-7 matplotlib 降级须先验证 | D4 §D4-7 | ✅ `data_chart_agent.md` 已补"未执行验证的降级判定无效" |

---

## 三、与原方案设计的偏差（含原因）

共 3 处，均为实施中实测触发、已在 commit message 与代码注释中就地记录：

### 偏差 1：`figure_gate` 的 DPI 缺失走独立 `warnings` 通道，不计入 `errors`

- **方案原文**（D3 §3.6）："`:252` 的 dpi 短路使 dpi 元数据为 `(0,0)` 的 11/19 张 PNG 被静默放行。应改为 dpi 缺失时报 WARN。"
- **实施中的实测**：若把 DPI 缺失计入 `errors`，真实项目 `invalid` 由 1 变为 **15/15 全红**（实测 15 张架构图全部无 dpi 元数据）。
- **处置**：新增独立 `warnings` 字段承载，**不影响 pass/fail 判定**。
- **理由**：这正是 D3 §3.4 明确警示的反模式——"若写进方案会导致验收永远不通过，反向逼迫实施者放宽门禁"。方案原文说的是"报 WARN"，本实现严格按"WARN 不等于硬失败"落地，与 §3.4 的验收判据（`total==15`、`invalid>=1` 且定位到 `3-1`）完全一致。

### 偏差 2：D1-7 的 I1 断言作用域显式限定为"正文章"

- **实测发现**：`assemble_merged()` 对 `appendix` **只输出标题行、不拼接任何内容**（附录无对应草稿文件，属既有设计），故附录标题天然"无正文"。
- **处置**：把 I1/A4 的作用域在代码与 docstring 中**显式限定为正文章**（`## 第 N 章：`），而非笼统放宽断言。
- **理由**：不放宽针对用户投诉本体（正文章为空）的断言强度，同时不为既有设计行为制造假失败。

### 偏差 3：`FAILURE_STEPS` 由 6 个扩为 7 个，第 7 步为可选步

- **方案原文**（D2-7）："新增第 7 步 `verify_docx`"。
- **实施细节**：第 7 步仅在传入 `--verify-docx` 时执行；`format_text_report` 对未传参的情形显示"未执行（docx 未被回读校验）"而非误报"前序步骤已阻断"；同步修正既有 `test_success_path_all_steps_pass`（该用例遍历 `FAILURE_STEPS` 断言每步 pass，需排除可选步）。
- **理由**：docx 生成本就在管线之外（方案实测结论），强制要求 docx 路径会使所有不出 docx 的调用失败。

---

## 四、执行中发现并修复的新问题（方案未预见）

| # | 问题 | 处置 |
|---|---|---|
| 1 | `_strip_section()` 实际签名为 `(raw_text, source_line, issues)` 三参，方案 D1-9 S6 按两参调用 | 实施时按真实签名传 `(raw, 0, issues)`，8 个用例由红转绿 |
| 2 | `apply_structure_overlay()` 的参数顺序是 `(results, structure, ...)`，与直觉相反 | 验证探针一度传反导致早期 return；已确认正式调用点（`builder.py:244`）顺序正确 |
| 3 | md2docx 的 `FRONT_BACK_WORDS`（`config.py:293`）含"导论""术语表"等词，章标题逐字命中时会被识别为**前置件**而非章，docx 中降为 `Heading 2` | **既有设计行为，未改动**（判别口诀允许结构关键词）。骨架生成只是把它显性化了；已在 commit message 中记录，验证时改用非结构关键词标题以隔离该因素 |
| 4 | `RunOptions` 是全无默认值的 dataclass，中途插入带默认值字段会破坏字段顺序约束 | `structure_overlay` 放在末尾并带默认值 |
| 5 | `scripts/selfcheck.py`（D3 §7.5 要求的一键自检入口）**此前并不存在** | 已新建，覆盖两套测试目录 + 8 项脚本命令行冒烟（纯 pytest 覆盖不到"脚本能否作为命令行工具正常调用"这一层，D4-10 的"基本用法必崩"正是因此长期未被发现） |

---

## 五、方案本身承认的未闭环局限（**未尝试强行修完美**，按定案范围实施）

以下 5 项是设计文档已诚实标注的设计局限，**不是本次实施的缺陷**。实施时按原文范围落地，并在代码注释/文档中原样保留标注：

| # | 局限 | 所在 | 本次处置 |
|---|---|---|---|
| 1 | **D2-9 递归漏洞**：orchestrator 对项目 `.claude/settings.json` 有写权限，可编辑该文件关掉 hooks 以绕过规则本身 | D2 §5.4 第 2 条 | 未加"禁止修改 `.claude/**`"那一层（会连带挡住用户手动调整项目 hooks 的正常需求，方案要求用户二次确认）。已在 hook 脚本注释、下发脚本输出、`stage-1-init.md` 三处明示 |
| 2 | **`--structure-overlay=off` 可绕过 D1-8 全部校验** | D1 §9.4.3 | 机器强制力上限止于"strict 下报 ERROR"，已在 `apply_structure_overlay` docstring 中标注 |
| 3 | **纯文档护栏效力接近零** | D2 §2.2 / §四 | D2-1/D2-2/D4-3 均**显式标注**效力接近零、不计入有效交付项，并列出真正有效的 5 个产物层机器门禁 |
| 4 | **用户确认疲劳**（C3，本项最大软风险，无机器手段可防） | D1 §9.5 | 按方案缓解措施执行：CP3 呈报附机器判据数字（章数/节数），使确认对象是数字而非印象 |
| 5 | **D2-9 下发时机盲区**（半路接手会话） | D2 §5.4 第 3 条 | 已按方案建议在阶段 9 入口补幂等下发（§9.0.0），闭掉该盲区 |

另有两项方案标注的"待后续测量"事项，**本次未强行提前**：

- **节级标题命中率从未实测**（D1 §十第 5 条）：真实 outline 的 section 数据仍为空（S3 在 warn 下不阻断），故 `strict` 是否可作默认值仍待新项目产出真实 section 后测量。
- **U6 切换 `strict` 的触发判据**：已按裁决要求写成**客观可验证**判据——"连续 3 个新项目的 outline 在未经人工补写的情况下自然通过 S1-S4"，同时写入 `STRICT_SWITCH_CONSECUTIVE_PROJECTS` 常量注释与 `stage-4-outline.md`，两处口径一致。N=3 的取值理由亦已注明（低于 3 无法排除偶然，高于 3 会让切换无限期推迟）。

---

## 六、commit 清单

| commit | 内容 |
|---|---|
| `64f9738` | batch1: D1-0/D4-10/D1-A/D3-0 四项低风险修复 |
| `abfb755` | batch2: D1-1 键名归一化贯通四消费端 + D1-5 层级下沉 |
| `032f6ee` | batch2: D2-8 失败时不留半成品 |
| `ac36bbf` | batch2: D3-1 figure_gate 入口修复 + D3-5 删除无条件放行 |
| `f75039d` | batch3: D1-2 修复静默失效 + D1-6 三态开关与告警聚合 |
| `e92079e` | batch3: D1-9 阶段4 结构完整性门禁 |
| `54ed312` | batch3: D2-7 docx 回读校验 |
| `e9c4764` | batch3: D3-2 provenance sidecar + emit_delivery + D3-4 归档报告 |
| `6596016` | batch4: D2-1/D2-2 文档层护栏条文 + D2-5 路由表 + D4-12 一致性订正 |
| `16a2a04` | batch4: D1-8 骨架 docx 预确认 |
| `00adbe9` | batch4: D1-7 端到端测试 + fixture + selfcheck.py |
| `673e1fc` | batch4: D2-9 PreToolUse hook 项目级分发 |
| `1bc50b9` | batch4: D4-9/D4-8/D4-3/D4-6/D4-7 存量问题文档层修复 |
| `8175768` | D1-5 doc: stage-7-writing.md 补层级下沉说明 |

---

## 七、用户投诉的治愈情况

用户原始投诉："**最后生成的报告居然有些章节都是空的。**"

| 环节 | 治愈手段 | 实测证据 |
|---|---|---|
| 根因消除 | D1-5 层级下沉 | 真实 drafts 上「本章结论」作为 H2 **13 → 0**、**相邻 H2 对数 = 0** |
| 结构注入恢复 | D1-1 键名归一化 | lookup size **0 → 16** |
| 静默失效可见化 | D1-2 `E-OL-03` | 键名契约断裂由静默返回转为 ERROR + 降级台账 |
| 运行时拦截 | D2-7 docx 回读 | "Heading 1 下 0 字符"与"全文只有骨架"两种形态均被捕获 |
| 半成品不落地 | D2-8 `.partial` 转正 | 正式产物名存在即等价 `overall_pass: true` |
| 左移到阶段 4 | D1-9 + D1-8 | 结构缺口在"尚未写一字"时即被 S3 捕获（真实 outline 13 章全 0 节） |
| 回归防护 | D1-7 端到端 fixture | 首次有测试覆盖"两个相邻 H2"这一致命组合 |
