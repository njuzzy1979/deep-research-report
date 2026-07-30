# D2：orchestrator 护栏体系方案（P0）

> **本文档性质：设计稿，尚未执行。不涉及对本次 SCIF 报告产出的修复。skill 源文件未被改动。**
> 上级文档：`skill优化方案-总览与执行清单.md`

---

## 一、事故行为链复盘

| 步 | 实际发生 | skill 本应拦住却没拦住的缺口 |
|---|---|---|
| 1 | `finalize_pipeline.py` 首次运行因缺 `--source-index` 报错 | 必需参数未在 `finalizer_agent.md`/`stage-9-finalize.md` 中显式完整列出 |
| 2 | 补参后 `overall_pass:false`、`failure_step:delivery_checklist`，**留下 388 字符的空 final-report.md** | **管线失败却留下半成品，且无任何标记**——下游/人类会误认为是成功产物 |
| 3 | orchestrator 未查路由表，**自写 Python 正则脚本**合并 13 章 | **skill 中不存在"禁止自行编写替代代码"的任何条文** |
| 4 | 手写合并把 `## 本章结论` 误当章标题，目录出现 13 个重复 | 无机器门禁校验产物结构 |
| 5 | orchestrator **又自写 python-docx** 生成 `SCIF_V1.0.docx`（格式全错） | **无任何机制阻止直接调用 python-docx 绕过转换器** |
| 6 | 用户严厉批评 | — |
| 7 | orchestrator 改用正则"打补丁" | 无"禁止在违规产物上打补丁"条文 |
| 8 | 最终分派 `finalizer_agent`（Haiku）严格调脚本，`overall_pass:true` | ← 正确路径，且该 Agent 顺带修好了两个底层 bug |

**关键断点在第 3 步**：路由表当时**存在且完善**（`finalizer_agent.md:55-63`，6 个 failure_step 枚举各有明确路由），但它写在**子 Agent 的定义文件**里。orchestrator 亲自跑脚本时，该文件**从未进入上下文**。

> **第一原则（贯穿本方案）：约束 orchestrator 的条文必须写进 orchestrator 必读文件（`SKILL.md` + `multiagent-orchestration.md`），不能只写在 `agents/*.md`。**

---

## 二、【必读】护栏有效性的残酷现实

本节是审查层 R4 的核心裁决，与设计层 D2 的自评从两个独立方向得出同一结论，**不予粉饰**。

### 2.1 机器强制层在这个系统里完全不存在

`references/multiagent-orchestration.md:128` 自述：

> "**无 Hook 级强制**：所有 Agent 边界与预承诺纪律都是 prompt-level，无确定性 PreToolUse hook 拦截"

实测：skill 目录下无 `.claude/hooks` 配置，用户级 `settings.json` 无 hooks 段。

**任何新增的文档条文都只是在同一个失效层面上又加了几行。**

### 2.2 "20 条反例没拦住，第 21 条凭什么能拦住？"

这是对本方案文档层部分最尖锐的质疑，正面回答：

1. **数量与效力反相关**——清单越长，单条被注意到的概率越低。加第 21 条是稀释，不是加固。
2. **第 20 条措辞已是全表最强硬**（"exit code 非零即阻断，零人工干预"），但它约束的 `figure_gate.py` 当时有 AttributeError 跑都跑不起来，且 `stage-6-diagrams.md:18` 只在**表格单元格**提过一次 figure_gate（非可执行调用点）。**最强措辞 + 零可执行调用点 = 零效果。**
3. **适用对象错位**——反例清单针对的是**被分派的子 Agent**，而本次肇事者是 orchestrator 自己，它不像子 Agent 那样被强制注入契约文件。
4. **反证**：Haiku 跑的 `finalizer_agent` 成功了，因为 `finalizer_agent.md` 是**被强制注入**的契约文件。

> **有效的不是"规矩写得好"，而是"规矩被强制进入了上下文"。**

**裁决：第 21 条反例、Tier 严格度表等纯文档护栏的预期效力评估为"接近零"，本方案不将其计入有效交付项。**

### 2.3 证据 D 八步的反事实推演

假设全部文档层护栏落地，重放事故：真正需要拦住的第 2/3/4/5 步，**0 步被拦住**。

---

## 三、三层护栏设计

### L1 文档层（效力：接近零，但提供可引用判据）

| 编号 | 内容 | 状态 |
|---|---|---|
| D2-1 | `SKILL.md` 反例清单新增 21/22 条 | **须补齐可粘贴原文** |
| D2-2 | `multiagent-orchestration.md` 新增"失败处置红线"节 | **须补齐可粘贴原文** |

**实测约束**：反例清单为**表格形式 20 行**（`| 1 |`…`| 20 |`），位于 `SKILL.md:197-216`，编号连续无缺号。**D2 与 D4 若各自追加会产生两个第 21 条**——只允许一次性追加：

- **21**：脚本/Agent 失败后自行编写替代代码绕过管线
- **22**：失败时不查 `failure_step` 路由表即自主决策

**失败处置红线（闭集定义）**——失败时**允许**的动作只有四件：读取错误输出、查路由表、回炉对应 Agent、升级呈报用户。**严禁**六件：自行编写替代实现、在违规产物上打补丁、把半成品当成品交付、静默改判、跳过失败步骤、用"超出工具链能力"免责。

> **诚实标注：D2-1~D2-4 当前只有设计说明，无可直接粘贴的完整 Markdown 原文。转入实施前必须补齐，否则是设计稿不是实施规格。**

### L2 流程层

#### D2-5（P2）补齐 failure_step 路由表

**实测数据**（穷举 `_finish(` 全部调用点）：

```
定义 1 处（:128）+ 调用 19 处
strip_markers      3 处（142/148/161）
h1_check           1 处（176）  ← 仅在异常时产出 failure_step
merge              4 处（183/208/210/228）
convert_refs       5 处（243/250/252/268/296）
contract_check     3 处（303/309/312）
delivery_checklist 3 处（322/335/338）
去重枚举 = 6 个
```

> **主控曾误判"`h1_check` 是路由表盲区"**——因提取枚举的正则字符类 `[a-z_]+` 不含数字，漏掉了含数字的 `h1_check`。R1/R3/R4 三方独立指出并纠正。**枚举确为 6 个，路由表无需按数量修正。**

**真正的缺陷不是"少一行"，而是同一枚举下不同调用点根因完全不同**：

| `merge` 的 4 个调用点 | 真实根因 | 正确路由 |
|---|---|---|
| `:183` | `merge_drafts` 模块 import 失败 | 检查 Python 环境/路径 |
| `:208` / `:210` | `parse_outline_yaml` 失败 | 检查 outline.md 语法 |
| `:228` | `assemble_merged`/**键名适配层异常** | **改脚本，不是改 outline** |

现表对 `merge` 统一路由到"回炉 `outline_architect_agent`"。而 `int("?")` 崩在 `:192` 被 `:210` 的 except 捕获，`failure_reason` 文案是"outline.md **解析**异常"——**路由错、文案本身也在误导**：用户看到只会去改 outline，但缺陷在脚本第 192 行。

**方案**：
1. 路由表按**调用点行号**做二级键（19 行），而非只按 6 个 failure_step。
2. **同步修正 `finalize_pipeline.py:210` 的文案**，区分"outline 解析失败"与"键名适配失败"。
3. `finalizer_agent.md` 维护**唯一权威表**（不做副本，两处副本必然漂移）；`stage-9-finalize.md` 侧补入**可执行的路由动作文本**。

**验证判据重设计**：原判据 `grep -c "failure_step" stage-9-finalize.md ≥ 1` **当前已满足**（`:25` 已有一处），零证伪能力。改为：断言该文件含**路由动作**文本（如 `回炉 outline_architect_agent`），可用 `grep -c "回炉"` 验证。

### L3 机器层（唯一真正有效的一层）

#### D2-8（P0）失败时不留半成品 —— 唯一切断事故因果链的措施

**这是全方案最高杠杆的一条**（约 15 行代码，半天工作量）。

事故第 2 步留下 388 字符的空 `final-report.md`，直接诱发第 3 步的"我来手动修一下"。切断这一环，整条链就断了。

**方案**：全程写 `.partial` 后缀，6 步全通过后原子 rename 转正。

**为什么不选另两个策略**：
- **删除**：有害于诊断与断点续传
- **头部插 FAILED 标记**：文件名不变，下游仍会误吃；且标记行可能被 `clean.py` 的清理规则吃掉

**核心不变量**：**正式产物名的存在本身即等价于 `overall_pass:true`，不需要任何人去判断。**

**Windows 平台必须补的两种失败模式**（实机验证）：

```python
def _promote_partial(partial_path: Path, final_path: Path) -> None:
    """把 .partial 原子转正。必须与最终目标同目录（避免跨卷）。"""
    try:
        os.replace(partial_path, final_path)      # 同盘原子，无中间态
    except PermissionError as e:
        # WinError 5：目标被占用（用户正开着 Word/VSCode 看上一版报告）
        raise RuntimeError(
            f"无法覆盖 {final_path}：文件正被其他程序占用。"
            f"请关闭后重跑。半成品已保留在 {partial_path}"
        ) from e
    except OSError as e:
        # EXDEV：跨卷 rename
        raise RuntimeError(
            f"跨卷移动失败（{partial_path} 与 {final_path} 不在同一磁盘）。"
            f"请将 --output-dir 指向与草稿同盘的路径"
        ) from e
```

**约束**：`.partial` **必须与最终目标同目录**生成；失败时**保留不删**（供诊断）。

**stale 产物处置**：失败且检测到上次成功的正式产物仍在时，**主动改名**为 `.stale-<run_id>` 而非仅告警——否则用户不一定会去读告警，仍会拿旧产物当本次结果。

**断点续传影响**：管线纯前向无状态，不读取上次 `.partial`，不影响重跑。

---

#### D2-7（P0）docx 回读校验 —— 交付物当前从未被任何门禁检查过

**实测**：`finalize_pipeline.py` 第 6 步 `delivery_checklist` 结束后**直接 return**。docx 生成完全在管线之外，是 `stage-9-finalize.md` 里的一段 bash 示例（`output/报告题名_v1.0.docx` 是**字面占位符**，需模型自行替换）。

**后果：最终交付物从未被任何门禁检查过。**

**为什么必须是 docx 层校验**：用户投诉的"章节都是空的"这一症状，在 md 层面**无法发现**——`## 第X章` 紧跟 `## 本章结论` 在 Markdown 里是完全合法的结构。**只有渲染成 docx 才暴露为"Heading 1 下 0 字符"。**

**方案**：新增第 7 步 `verify_docx`，打开生成的 docx 断言结构不变量：

```python
def verify_docx_structure(docx_path: str, expected_chapters: int) -> dict:
    from docx import Document
    d = Document(docx_path)
    h1s, empty, prev, buf = [], [], None, []
    for p in d.paragraphs:
        if p.style.name == "Heading 1":
            if prev is not None and not "".join(buf).strip():
                empty.append(prev)
            h1s.append(p.text); prev, buf = p.text, []
        elif prev is not None:
            buf.append(p.text)
    if prev is not None and not "".join(buf).strip():
        empty.append(prev)
    dup = [t for t in set(h1s) if h1s.count(t) > 1]
    return {
        "pass": not empty and not dup and len(h1s) == expected_chapters,
        "empty_headings": empty,        # ← 直接对应用户投诉
        "duplicate_headings": dup,      # ← 13 个"本章结论"
        "h1_count": len(h1s), "expected": expected_chapters,
    }
```

> D3 的端到端 pytest 用例方向正确，但那是**测试**；这一条是**运行时门禁**。两者都需要。

> **⚠ 本函数有一处漏检，实施时必须一并修（D1-8 设计时实测发现）**：`elif prev is not None: buf.append(p.text)` 这一支会把 `Heading 2` 的**标题文本**当作正文收集——`"Heading 2" != "Heading 1"`，于是走了 elif。后果：只要某个 `Heading 1` 后面跟着任一非空 `Heading 2`，该章即被判为"有正文"。**实测**：把本函数原样跑在一份"只有封面+TOC+H1/H2、完全无正文"的骨架 docx 上，得 `pass=True`、`empty_headings=[]`。
>
> 即本门禁能捕获本次事故的形态（`Heading 1` 紧跟 `Heading 1`），但**捕获不到"全文只有骨架"的形态**。这削弱了 §四给它的"高有效性"评级——高有效性仅对本次事故形态成立。
>
> **修法**（约 1 行）：`elif prev is not None and not p.style.name.startswith("Heading"): buf.append(p.text)`。修后须复测 A4 断言仍成立。
>
> **与 D1-8 的关系**：骨架 docx **不进入**本门禁的检查范围——骨架走独立入口、不经 `finalize_pipeline.py`，而第 7 步只对 `emit_delivery` 实际写出的路径清单生效，故天然不被检查，**零新增豁免逻辑**（不得按文件名正则豁免，理由见 D3 §六）。详见 D1 文档 §9.4.4。

---

#### D2-6（P1）provenance 出处标记 —— 载体必须是 sidecar

**目标**：使"这份产物是否走了规范管线"从人工判断变成一行校验。事故中 `SCIF_V1.0.docx`（手写）与 `final-report.docx`（合规）在文件系统层面**完全无法区分**。

**【重要】内嵌 HTML 注释方案已被否决**——三条独立实测破坏面，任一条都足以否决：

1. **会渲染进 docx**：`textstage/clean.py` 对 `<!-- -->` **零处理**（grep `!--`/`comment` 零命中），注释原样穿过，`parse()` 把它变成普通 ParagraphToken，出现在 docx 正文第一段。且 `contract_check.py:79` 的 C5 `BANNED_PATTERNS` 不匹配 `<!--`，**门禁全程沉默**。
2. **会打掉 YAML**：若写在 front matter 之前，`extract_yaml_front_matter` 因 `if not text.startswith("---")` 返回 `(None, 原文)` → **整份 outline 结构清单失效**，与 D1 修复直接对冲。
3. **存量全灭**：`research/` 与 `output/` 下**无任何文件含 `produced-by`**。新增门禁判 fail → 既有项目 **100% `overall_pass:false` / `failure_step:delivery_checklist`**，与事故现场一模一样的失败态。

**定案**：载体改为**旁路 sidecar** `research/.provenance.jsonl`（append-only）。这与既有的 `research/.degradation-log.jsonl` 是同款成熟机制（后者已存在 3537 字节）。**零渲染风险、零 YAML 风险。**

**抗伪造**：复用 `scripts/output_envelope_check.py` **已实现的 nonce 原语**（`[0-9a-f]{6,16}` 十六进制 + 三重误匹配防护 + `tests/test_envelope_nonce.py` 覆盖）。**不要另起炉灶发明新格式**——现成抗伪造原语就在同一目录。

**run_id 必须确定性**：由 outline + drafts 文件名 + 合并正文的 SHA-1 派生 12 位 hex，**不用随机数/时间戳**，否则打破 md2docx 的 G-11 幂等要求（`00-master-design.md:202`）。

> 注：曾有方案称非确定性 run_id 会"打破 golden 快照与 G-11 幂等"。**golden 那半句是错的**——golden 快照对象是 `contract_check --json` 输出，不经 md2docx。只保留 G-11。

**门禁强度**：新增检查项**首版只能 WARN 或 `manual_required`**（`delivery_checklist_check.py:358-365` 已有该语义且明确"不计入自动 pass/fail"，零新增机制）。升级为 fail 需"连续 2 个新项目自然产生标记"后再切。

**越界声明**：若要在 `gate3.py` 加第 4 项 Fatal，须显式声明——`gate3.py:4` 明文"仅三类：密级复检/分页规划一致性 R15/域三态结构"，是被 M3 裁决**明文封闭的闭集**。加第 4 项**等于修改 M3 裁决**，须同步更新 docstring。

**耦合数字同步**：`delivery_checklist` 实测为 **13 项**，"13"是跨 4 处的耦合数字（`finalizer_agent.md:70`、`:49`、`:63` 两次）。**且 `multiagent-orchestration.md:66` 已写"12 项"与代码不一致，是既有缺陷**，须一并订正。

---

## 四、护栏有效性排序表

| 护栏 | 类型 | 能否拦住事故 | 有效性 | 理由 |
|---|---|---|---|---|
| **D2-8 半成品清理** | 机器强制 | **能**（切断第 2→3 步） | **高** | 正式产物名存在即等价成功，无需任何人判断 |
| **D2-7 docx 回读校验** | 机器强制 | **能**（拦住第 5 步产物） | **高** | 唯一能捕获"章节空"症状的运行时手段 |
| **D2-6 provenance sidecar** | 机器强制 | 部分（可事后判别） | 中高 | 使手写产物无法冒充；但首版仅 WARN |
| D3-0 delivery_checklist 补 output_dir | 机器强制 | 部分 | 中 | 前置条件，当前对 output 目录**零感知** |
| D2-5 路由表补齐 | 流程/文档 | 否 | 中 | 修的是**能力缺口**非纪律缺口——路由表给不出有效动作时，自写代码在模型看来是唯一剩余选项 |
| D2-3/D2-4 CHECKPOINT 话术 | 纯文档 | 否 | 中低 | 改变输出形状，把违规从隐蔽变显式自陈；但模型可填假信息 |
| D2-1/D2-2 反例与红线条文 | 纯文档 | **否** | **低** | 见 §2.2 四条论证 |
| Tier 严格度表 | 纯文档 | **否** | **低** | 与既有 §7 上表同样只能靠自律，而这正是本次失效模式 |

**统计：15 个条目中 12 个是纯文档约束（80%），仅 3 个可做成机器强制。**

**若只能实施两项，就实施 D2-8 和 D2-7。**

---

## 五、D2-9（P1）PreToolUse hook 项目级分发机制 —— U1/U2 定案

> **本节为用户裁决后的具体设计，替代此前"需用户决策"的 U1/U2 空白项。裁决意见：作用范围收窄到"每次写报告的工作空间"，源文件放在 skill 目录，随阶段 1 下发到项目目录。**

### 5.1 裁决方案的核心机制

**利用 Claude Code hooks 本身的作用域规则，而不是 matcher 表达式，来实现隔离**：Claude Code 的 `settings.json` 若放在**项目级** `.claude/settings.json`，只在该项目目录被打开为工作区时加载生效；放在用户级 `~/.claude/settings.json` 则全局生效。**因此把 hook 配置写成项目级文件，天然只在这一个工作空间生效，不影响其他项目、其他 skill**——这是 Claude Code 机制自带的隔离边界，不需要 hook 脚本自己判断"当前是不是这个 skill"。

**分发载体复用既有先例**：`model_profile.py:_write_local_override`（`:370-400`）已经在做"探测环境 → 生成本地配置文件 → 写入 `_PROJECT_ROOT`（即当前工作目录/项目根）"这件事，`stage-1-init.md:33` 明确其行为——若目标文件已存在则跳过、不覆盖。阶段 1.2"建立工作目录"（`stage-1-init.md:191`）是这个机制当前生效的位置。**hook 配置下发复用同一环节、同一模式**，不新开一个流程节点。

**实测确认**（核实本次裁决方案的技术前提）：`scripts/model_profile.py:460-471` 现状是 `out_path = _PROJECT_ROOT / "model-profile.local.json"`，若已存在则跳过、不覆盖，否则调用 `_write_local_override(config)` 写入——与本节设想的"探测/首次进入即下发、已存在则跳过"完全同构，可直接仿照实现，不必另起一套下发逻辑。

### 5.2 源文件与目标文件

| 位置 | 内容 | 性质 |
|---|---|---|
| `skill_root/.claude/hooks/guard_docx_bypass.py` | hook 脚本本体（新增，源文件） | 随 skill 版本管理，skill 升级即更新 |
| `skill_root/.claude/hooks-template/settings.fragment.json` | 待合并进项目 `.claude/settings.json` 的 hooks 配置片段模板 | 随 skill 版本管理 |
| `project_root/.claude/hooks/guard_docx_bypass.py` | 阶段 1.2 下发时**复制**的脚本副本 | 项目工作空间私有 |
| `project_root/.claude/settings.json` | 阶段 1.2 下发时**合并写入**的 hooks 配置段 | 项目工作空间私有 |

**复制而非路径引用**：曾考虑让项目配置直接引用 skill 目录内脚本的绝对路径，但若 skill 目录被移动/重装/多版本共存，已下发到各项目的 hook 会静默失效且无告警。**定案为复制脚本内容 + 在文件头写入来源 skill 版本号**，牺牲一点"skill 升级后项目侧自动同步"的便利，换取路径稳定性。若 skill 有重大 hook 逻辑更新，需要一个显式的"重新下发"步骤（见 5.5）。

**实测确认 skill 目录当前状态**：`skill_root/.claude/` 目录**已存在但为空**（无 `settings.json`、无 `hooks/` 子目录）。本方案在此空目录下新建上述源文件，不与任何既有内容冲突。

### 5.3 hook 判断逻辑（两条规则合一，同一份脚本）

对应 U1（禁止绕过 md2docx 直写 docx）与 U2（禁止修改 skill 脚本本体）设计为**同一个 PreToolUse hook 脚本的两条规则**，而非两套独立机制：

```
规则一（原 U1）：matcher 命中 Write/Bash 工具，且：
  - 目标路径在本项目 output_dir 下、扩展名为 .docx
  - 且本次调用的调用栈/命令内容包含 python-docx 特征（如 "from docx import Document"、
    "Document()"）而不含 "md2docx" 模块引用
  → deny，提示："docx 生成须经 finalize_pipeline.py → md2docx，禁止直接调用 python-docx"

规则二（原 U2）：matcher 命中 Write/Edit 工具，且目标路径落在
  <skill_root>/scripts/**、<skill_root>/agents/**、<skill_root>/references/** 内
  （即 skill 脚本/契约文件本体，而非项目工作空间文件）
  → deny，提示："skill 脚本本体不可在报告编写会话中修改，如需调整请在 skill 开发场景下进行"
```

**为什么合并成一份**：两条规则的裁决动作相同（deny + 固定提示），共用同一份 `settings.json` hooks 段和同一次下发时机，避免 D2-1/D2-2 已警示过的"两处副本必然漂移"问题在 hook 层重演。

### 5.4 必须诚实标注的局限（不可回避）

1. **只读保护不是文件系统级的强只读**：U2 原设想"脚本目录只读保护"若理解为 Windows 文件属性（`attrib +r`）或权限位，实际效力有限——多数写操作在遇到只读属性时会报错而非静默失败，但这不是安全边界，且部分写入逻辑可能在写入前主动清除只读属性（需实测确认 Claude Code 的 Write/Edit 工具行为，本文档不假设）。**真正生效的是规则二这条 PreToolUse deny，而不是文件系统权限本身**——U2 在本方案中被重新定义为"hook 层面的路径黑名单"，不是"操作系统只读位"。
2. **hook 配置本身可被同一个 orchestrator 关掉，形成递归漏洞**：orchestrator 在报告编写会话中拥有对 `project_root/.claude/settings.json` 的 Write/Edit 权限，理论上可以直接编辑这个文件把 hooks 段删掉或改宽松，从而绕过规则一、二本身。**这是本方案未闭环的部分，必须向用户明示**——除非再加一层"禁止修改 `.claude/settings.json` 本身"的规则（可以作为规则二的路径黑名单再加一条 `project_root/.claude/**`），但这样做会连带挡住用户自己想手动调整项目 hooks 配置的正常需求，需要用户在实施前二次确认是否要加这一层。
3. **下发时机的覆盖盲区**：分发动作挂在阶段 1.2，若某次会话是"半路接手"（跳过阶段 1、直接从已有草稿进入阶段 7-9，这正是本次事故的实际形态之一），hook 不会被下发，规则一、二在该会话中不生效。**建议**：在阶段 9（`stage-9-finalize.md`）入口也补一次幂等检测——若 `project_root/.claude/settings.json` 缺少本 hook 的 marker 字段，先补下发再继续，避免只覆盖"从阶段 1 开始的会话"这一种路径。
4. **合并语义而非覆盖**：本次核实 `E:\Program\文档编写\空间态势认知智能框架研究-1\` 当前**没有** `.claude` 目录，本项目首次下发是新建、零风险。但作为通用机制写入 skill 后，未来任何已有 `.claude/settings.json`（可能已含用户自定义的其他 hooks）的项目下发时，**必须做 JSON 层面的合并（hooks 数组去重追加），严禁整文件覆盖**，否则会静默清除用户已有的项目配置。
5. **误伤边界仍需实测**：规则一的"含 python-docx 特征但不含 md2docx 引用"这一判断依据的是命令行文本模式匹配，无法识别"合法但间接"的调用路径（例如脚本先 import 一个自己封装的中间模块、内部才调用 python-docx）。**上线前需要用一批合法与违规两类样本用例做误伤率测试**，不能假设规则一次写对。

### 5.6 与 D1-8（阶段 4 骨架 docx）的接口对齐

D1-8 会新增 `scripts/outline_skeleton.py`，其职责是在阶段 4 产出一份只含封面/目录/H1/H2 的骨架 docx。**该脚本与规则一无冲突，经逐条比对确认**：

| 规则一的 deny 条件 | D1-8 实际行为 | 是否命中 |
|---|---|---|
| 目标路径在 `output_dir` 下 | 骨架落 `research/outline-skeleton-preview.docx`，**不在 output_dir** | 不命中 |
| 扩展名 `.docx` | 是 | 命中 |
| 含 python-docx 特征而不含 md2docx 引用 | 骨架生成**只合成 Markdown，docx 一律交给 `python -m md2docx`**，绝不自行 `from docx import Document` | 不命中 |

**两条独立的不命中路径**，任一条即足以排除误伤，因此**不需要为骨架生成设计 `--skeleton-only` 子命令或任何白名单例外**。

**须写入 hook 脚本注释的两点**（供 §5.4 第 5 条的误伤率测试使用）：
1. 把"合成骨架 md + 调用 `python -m md2docx`"登记为**合法调用正样本**，避免未来实施者把它当违规样本，反向逼松规则一。
2. `outline_skeleton.py` / `outline_structure_gate.py` 是**新增** skill 脚本，落在规则二黑名单 `<skill_root>/scripts/**` 内。规则二禁止的是"在**报告编写会话**中修改 skill 脚本本体"，而新增这两个脚本属于**实施本优化方案时**的 skill 开发行为，不在报告编写会话内，**不受规则二约束**。此处记录以免混淆。

### 5.5 工作量与优先级

| 子项 | 工作量 |
|---|---|
| hook 脚本本体（规则一+二） | 半天 |
| 项目级下发脚本（阶段 1.2 挂载点 + JSON 合并逻辑） | 半天 |
| 阶段 9 幂等补下发 | 2 小时 |
| 误伤率测试用例 | 半天 |

**优先级定为 P1**（不进最小可交付集）：理由是 D2-8（半成品清理）与 D2-7（docx 回读校验）已经能在**产物层面**捕获同一类事故（半成品不落地、结构异常门禁拦截），是更低成本、无递归漏洞的替代路径；D2-9 是在**行为层面**提前拦截，属于纵深防御的加强层，而非唯一防线。

---

## 六、编号与插入位置的实测约束

| 事项 | 实测 | 约束 |
|---|---|---|
| 反例清单 | 表格 20 行，`SKILL.md:197-216` | 只允许一次性追加 21/22，避免 D2/D4 各自追加产生两个第 21 条 |
| §7.6 编号 | `multiagent-orchestration.md:105` 明写"正交的**第二维**"、`:107` "两者独立生效"、`:89` 标题"**二维**决策矩阵" | 插入"第三维 §7.6"与已成文措辞**直接矛盾**。定案：**并入 §7.5 表格作为第三列**；若坚持独立成节则须同步改写三处"二维"表述 |
| 门禁名 | `multiagent-orchestration.md:23-33` 引用 8 个门禁名，§5 表（`:62-67`）只定义 4 个 | 有名无实的是 **4 个**（`G(收集)`/`G(核验)`/`G(卡片)`/`G(出图)`），须全部补齐 |
| 交付清单项数 | 代码 13 项，`multiagent-orchestration.md:66` 写"12 项" | 既有不一致，须一并订正 |
