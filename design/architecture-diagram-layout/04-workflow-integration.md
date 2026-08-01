# D5-04：流程接入与门禁编排

> **状态：设计稿，待用户审核，尚未执行**
> 本文承载多处被其他文档引用的定案：00 号 §3.1 的核心结论、A-5 重试预算的流程落地、批次介入节点

---

## 1. 接入点总览

| 接入位置 | 现状 | D5 改动 | 批次 |
|---------|------|---------|------|
| `agents/architecture_chart_agent.md` §自检 | 只调 `figure_gate.py` | 前置调用布局校验器 + 禁止吞码写法 | B2/B3 |
| `references/stage-6-diagrams.md` **§6.10**（新增） | §6.9 为 figure_gate 调用点 | 新增布局校验调用点 | B3 |
| `references/stage-6-diagrams.md` §阶段6质量门槛 | 7 项勾选 + 1 项机器门禁 | 追加 2 项机器门禁勾选 | B3 |
| `references/multiagent-orchestration.md` §5 `G(出图)` | 仅 `figure_gate.py` | 扩为两级门禁 + 失败路由 | B3 |
| `SKILL.md` 反例清单 | 22 条 | 追加 **23-26 条** | B3 |
| `references/stage-9-finalize.md` | 转换前跑 figure_gate | 追加布局复检（mtime 比对） | B3 |

**章节编号核实**：`stage-6-diagrams.md` 现有 §6.9 为 figure_gate 节，故 D5 新增节为 **§6.10**（不占用已有编号）。
**反例编号核实**：现有第 21 条为"脚本失败后自行编写替代代码绕过管线"、第 22 条为"失败时不查 `failure_step` 路由表"，**均属管线失败处置，与图表无关** → D5 从 **23** 起。

---

## 2. `stage-6-diagrams.md` §6.10 内容草案

```markdown
### 6.10 drawio_layout_validator.py 布局几何门禁（D5，**必须先于 §6.9 执行**）

**为什么必须先跑**：§6.9 的 figure_gate 检查的是 PNG 产物，其诊断对布局缺陷具
**误导性**。实测：3-1 因 6 个 vertex 的 `x`/`width` 字面值为 `"None"`（XML 合法但
语义损坏）导出了 325px 宽的废图，figure_gate 正确报 FAIL 但提示为"宽度不足"——
照此提示去加大导出 scale 只会得到 650px 的同样残缺图。**真因只在 .drawio 源文件层可见。**

CHECKPOINT 之前必须按序执行两级门禁。**本项目运行环境为 Windows PowerShell 5.1**，故以 PowerShell 为主写法：

    # 门禁 1（源文件层，零依赖）
    python scripts/drawio_layout_validator.py --figures-dir research/figures
    if ($LASTEXITCODE -ne 0) { throw "布局门禁失败(exit=$LASTEXITCODE)，不得进入 §6.9" }

    # 门禁 2（产物层，现有）
    python scripts/figure_gate.py --outline research/outline.md `
        --figures-dir research/figures --stage stage6
    if ($LASTEXITCODE -ne 0) { throw "图表门禁失败(exit=$LASTEXITCODE)，不得交付" }

bash / Git Bash 环境下的等价写法：

    python scripts/drawio_layout_validator.py --figures-dir research/figures
    if [ $? -ne 0 ]; then echo "布局门禁失败"; exit 1; fi

**退出码判定口径**：

| exit | 含义 | 处置 |
|:---:|---|---|
| 0 | 通过 | 进入下一级 |
| 1 | 校验失败 | 查 §6.10.1 路由表 |
| 2 | 部分校验（有文件被 skip） | **不得视为通过**，按失败处理 |
| 3 | 脚本自身错误 | 修配置后重跑 |
| 4 | 目录下 0 个 .drawio | **不得视为通过**——若项目确实无架构图，须显式跳过本门禁 |

> **禁止吞码**（D5 反例第 26 条）。以下写法会使门禁静默失效：
>
>     # ❌ 取到的是 tail 的退出码，永远 0
>     python scripts/drawio_layout_validator.py ... | tail -40; echo $?
>     # ❌ PowerShell 中 $? 是布尔，不是原生 exe 的整数退出码
>     python scripts/drawio_layout_validator.py ...; if ($?) { "通过" }
>     # ✅ PowerShell 正确写法
>     python scripts/drawio_layout_validator.py ...
>     if ($LASTEXITCODE -ne 0) { throw "布局门禁失败" }
```

### 2.1 §阶段 6 质量门槛追加项

在现有 7 项勾选之后追加：

```markdown
- [ ] **已运行 `drawio_layout_validator.py` 且 exit code 为 0**（D5，机器校验；exit 2/4 同样视为未通过）
- [ ] **几何损坏顶点数为 0**（报告 `summary.vertex_geometry_broken`——该值 > 0 表示存在 XML 合法但语义损坏的图，会导出废品）
```

### 2.2 一处必须同步更正的既有断言

`stage-6-diagrams.md:231` 原文：

> **诚实标注**：`fontSize < 12` 与"内嵌题注"两项检查在真实项目上实测 **0 命中**……属"为不存在的问题写代码"，故**不作为阻断依据**。

**须改为**（承 00 号 §3.2）：

```markdown
> **诚实标注（D5 更正）**：此处原将两项检查合并断言为"0 命中"，实测证明**必须拆分**：
> - `fontSize < 12`：**确为 0 命中**（全库最小字号 12，13/15 张统一 16）→ 维持不作阻断依据；
> - **内嵌题注：断言被证伪**。实测 12-1(`bottomNote`)、4-1(`note1`)、4-2(`note2`) 三处
>   真实存在，且其中 2 处正是画布溢出源。"0 命中"的真因是**当时的检查器从不解析
>   `.drawio` 文件**——用错误的观测面积得出"问题不存在"，再据此关掉检查。
>   该项自 D5 起由 `drawio_layout_validator.py` G6 实检，**作为阻断依据**。
>
> **教训**：任何"0 命中"结论必须附测量口径；合并断言必须拆分。
```

---

## 3. `G(出图)` 门禁改造

### 3.1 改造后的门禁表行（`multiagent-orchestration.md` §5）

| report 门禁 | 语义 | 负责角色 | 失败路由 |
|------------|------|---------|---------|
| G(出图) | 架构图产出达标：**①** `drawio_layout_validator.py` 源文件层几何校验（G1-G11）**②** `figure_gate.py` 逐文件验证存在性/宽度/DPI。**①先于②** | `architecture_chart` | 查 D5 路由表（本文 §3.2）；`retryable=false` 类直接上报 orchestrator |

### 3.2 失败路由表（对齐 SKILL.md 现有 `failure_step` 机制）

> **设计依据**：`multiagent-orchestration.md:242` 记录的事故教训是"路由表存在且完善，但写在子 Agent 定义文件里，orchestrator 亲自跑脚本时该文件从未进入上下文"。故 **D5 路由表必须写进 orchestrator 必读文件**（`SKILL.md` + `multiagent-orchestration.md`），不可只写在 `agents/architecture_chart_agent.md`。

| error_code | 判据 | 重试 | 路由动作 | 退回到 Agent 的哪一步 |
|-----------|------|:---:|---------|---------------------|
| `GEOMETRY_INVALID` | G1 | **否** | **直接上报 orchestrator 并停机** | 不退回——属生成器缺陷，重试无效 |
| `EMBEDDED_CAPTION` | G6 | **否** | 移除画布内图注 mxCell，文本移入 Markdown 正文题注 | 出图步骤（单点修改，不重新布局） |
| `FLOW_RECONVERGENT` | G10a | **否** | **强制转 `layout_mode: manual`**（`manual_kind: forced`） | IR 构造步骤（**禁止改模式重试**） |
| `GRID_HAS_CONNECTED_STRUCTURE` | G10a | **否** | 同上 | 同上 |
| `STAR_NO_UNIQUE_HUB` / `STAR_HUB_NOT_DOMINANT` / `STAR_NO_EDGES` | G10a | **否** | 同上 | 同上 |
| `STACK_MOSTLY_NONADJACENT` | **G10b**（B4 后生效） | **否** | 同上 | 同上 |
| `MANUAL_UNJUSTIFIED` | — | **否** | 补 `manual_reason` + 实际尝试 `attempted_modes` | IR 构造步骤 |
| `HARD_OVERLAP` | G2 | 是 | ①增大 gap/density ②换 layout_mode ③拆图 | 布局参数步骤 |
| `CONTENT_OVERFLOW_FATAL` | G3 | 是 | 换模式或拆图 | 布局参数步骤 |
| `LEGEND_INSIDE_CONTENT` | G11 | 是 | 图例移至内容底边下方 ≥20px | 出图步骤 |
| `FAKE_DIAGRAM` | G7 | 是 | 重新出图，禁止 text box 内嵌 Mermaid 源码 | 出图步骤（从头） |
| `XML_MALFORMED` / `DECOMPRESS_FAILED` | — | 是 | 重新生成该文件 | 出图步骤 |
| warning 类 | G4/G5/G2 灰区 | 是（非阻断） | 记录，不阻断 | — |

> **D5-02 错误码订正**：本表此前列有 `TOPOLOGY_MODE_MISMATCH`、`FLOW_BRANCHING`、`FLOW_MERGING`、`STACK_NONADJACENT_EDGE` 等**代码中已不存在**的枚举值。现已与 01 号 §3.7 的 G10a/G10b 实际返回值逐一对齐。

### 3.3 重试预算与熔断（A-5 定案的流程落地）

| 项 | 取值 | 依据 |
|----|------|------|
| 重试上限 | **3 轮**（第 4 次不过即上报） | fireworks 三次协议 + excalidraw 5 轮安全阀 → 取保守下界 |
| 熔断条件 | **单调性熔断**：本轮 error 总数 ≥ 上轮 → 立即停止，不耗尽预算 | ICLR 2024：无外部反馈的自我纠错会持续退化 |
| 反馈内容 | 必须是 JSON `issues[].feedback` 的**确定性数值化描述**，禁止"再看一眼你的图" | 同上 |
| 不计入预算 | `retryable=false` 的四类 | 它们不是"再试一次可能好"的问题 |
| 升级出口 | 3 轮未过 / 熔断触发 → 上报 orchestrator → 登记已知限制 + 标注人工介入 | `SKILL.md` 失败处置红线第 ④ 项"升级呈报用户并停机" |

**收敛性论证**：与"LLM 反复手调坐标"不同，B4 之后每轮重试修改的是 **IR 语义**（换模式/拆图/调 gap 参数），每次都实质改变生成器输入，不在同一失效算子上打转。**但 B1~B3 阶段（尚无 IR）重试仍是"Agent 手改坐标"，收敛性无保障** → 见 §6 局限 W-1。

---

## 4. manual 逃生舱的流程

```
Agent 构造 IR
   │
   ├─ 选定 layout_mode ∈ {stack,pyramid,flow,star,grid,quadrant}
   │     │
   │     ▼  生成器尝试布局
   │  G10 拓扑-模式一致性校验
   │     │
   │     ├─ 一致 ──────────────────► 生成 .drawio ─► 门禁1 ─► 门禁2
   │     │
   │     └─ G10a 错误码（FLOW_RECONVERGENT / GRID_HAS_CONNECTED_STRUCTURE / STAR_*）
   │            │  ❌ 禁止：换个模式再试（等于穷举绕过语义检查）
   │            ▼  ✅ 必须：转 manual
   └────► layout_mode: manual
            │  强制字段（缺失 → MANUAL_UNJUSTIFIED error）：
            │    manual_reason     非空
            │    attempted_modes   须为生成器【实际尝试过】的模式 + 各自失败原因
            ▼
        计入 manual_ratio 统计
            │
            ├─ ratio ≤ 40% ─► 继续（该图走 strict 校验、重试预算 0）
            └─ ratio > 40% ─► **exit 非零**，本次运行整体失败
```

> **即时门禁而非滞后统计**（承 00 号 §9.2）：manual 占比在**单次运行内**判定。原设计的"连续 2 个项目"滞后统计意味着前两个项目已经烂掉才发现。

### 4.1 死锁隐患与解法（自查发现，必须定案）

**推演**：若一个项目有 10 张图，其中 6 张拓扑确实不匹配任何模式：

```
6 张触发 G10a 错误码（如 FLOW_RECONVERGENT）
   → 路由表禁止改模式重试，强制转 manual
   → manual_ratio = 60% > 40%
   → exit 非零，整体失败
   → 但路由表又不允许改模式
   → 无合法出路 = 死锁
```

**这是两条规则叠加产生的死锁，必须解开。定案如下：**

**manual 分两类计数，只对"主动 manual"设限：**

| 类别 | 触发方式 | 是否计入 `manual_ratio` 上限 |
|------|---------|---------------------------|
| **被迫 manual**（`forced`） | G10 判定拓扑无对应模式后**由生成器自动转入** | ❌ **不计入** |
| **主动 manual**（`elective`） | Agent 未经模式尝试**直接声明** manual | ✅ 计入，上限 40% |

```jsonc
{ "layout_mode": "manual", "manual_kind": "forced",
  "manual_reason": "...", "attempted_modes": [ ... ] }
```

**理由**：`--max-manual-ratio` 的立法目的是**防止 Agent 用 manual 绕过布局纪律**，而非惩罚"图的拓扑客观上不属于五种模式"。后者是**模式库覆盖不足**，责任在设计方而非 Agent —— 用门禁失败去惩罚它，只会逼 Agent 谎报模式（选一个能通过 G10 的错模式），**反而制造 C-1 那类"几何全绿但语义错误"的图**，与 G10 的初衷正相反。

**但 `forced` 比例仍须可观测**（否则模式库缺陷会被永久掩盖）：

| forced 占比 | 处置 |
|------------|------|
| ≤ 30% | 正常，仅记录 |
| > 30% | **报 warning**（不阻断）："模式库覆盖不足，N/M 张图无对应模式，建议评估新增布局模式" |
| — | 该比例写入 `summary.manual_forced_ratio`，是评估"是否需要第六种模式"的**唯一数据来源** |

> `forced` 不阻断但要**响亮地记录**。这与 00 号 §9.2「B4/B5 可被数据否决」是同一思路：让设计缺陷暴露为可观测数据，而不是转化为对执行者的惩罚。

---

## 5. 批次介入节点

| 批次 | 介入节点 | 生效范围 | 是否改变产出路径 |
|------|---------|---------|----------------|
| **B1'** | §6.10 门禁 1 调用点（**`--mode warn`**）+ 零参数判据 G1/G6/G7/**G10a** + PNG/bbox 比值反查 | 只读校验，warn 模式恒 exit 0 | ❌ 否 |
| **B1''** | 追加 G2/G3/G5/G11（含拟合参数） | 同上 | ❌ 否 |
| **B2** | Agent 自检节 + 留痕文件 `.layout-gate-report.json` | 退出码可靠传递 | ❌ 否 |
| **B3** | §6.10 转 blocking + G(出图) 路由表 + 反例 23-26 + §231 断言更正 | 门禁生效阻断 | ⚠️ 是（开始阻断） |
| **B4** | IR schema + 生成器（新增 `drawio_generator.py`） | **G10 首次真正生效** | ✅ 是（坐标来源变更） |
| **B5** | Agent 切换为只输出 IR | 手写坐标路径关闭 | ✅ 是 |
| B6 | 边路由校验（候选，本期不做） | — | — |

### 5.1 warn → blocking 的切换条件（**D5-15 已与 B4/B5 解耦**）

B1' 以 **warn** 上线。切换为 blocking 的条件**仅依赖零参数判据**：

1. `summary.vertex_geometry_broken == 0`（G1）
2. G6 内嵌图注命中数 == 0
3. 无 `retryable=false` 类 error（G1/G6/G10a）
4. 连续 2 次运行满足 1-3

**与 B4/B5 无关** —— 四条均可在 B1' 阶段测得。原设计要求"100% 经生成器产出"会导致 B4/B5 被放弃时**门禁永久停在 warn = 死锁**，已消除。详见 03 号 §8。

---

## 6. 与既有脚本的关系

| 脚本 | 关系 | 处置 |
|------|------|------|
| `figure_gate.py` | **并列后置**，职责正交（本校验器读 `.drawio`，它读 `.png`） | 不修改 |
| `chart_checks.py` | **不挂入阶段 6** | 实测：它在阶段 6 有**零调用点**，且依赖的 `color-registry.csv` 在真实项目**不存在** → 挂上会立刻引入 100% 失败的新门禁，重演 `stage-6-diagrams.md:229` 警示的"门禁全红→反向逼迫放宽" |
| `chart_checks.py` vs `figure_gate.py` | **既存口径矛盾**：前者对缺失 DPI 判 FAIL，后者判 warning，对同一目录结论相反 | D5 **不擅自统一**（超出范围），仅标注 |
| `selfcheck.py` | **建议注册（已核实可行）** | 见 §6.1 |
| `degradation_log.py` | 校验器降级时记账 | 沿用 `try/except ImportError` no-op 写法 |

### 6.1 `selfcheck.py` 注册方式（已核实，W-3 结案）

**核实结论：`selfcheck.py` 不吞退出码。** 证据（`scripts/selfcheck.py`）：

```python
def _run(cmd, cwd):                                      # :63-68
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, ...)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

result["smoke"][name] = {"exit": code, "passed": code == 0, ...}   # :85-88
sys.exit(0 if result["passed"] else 1)                             # :130
```

它显式捕获 `returncode` 并以 `code == 0` 判定，最终按聚合结果 `sys.exit`。**故注册进去是有效的，不会白做。**

**注册方式**：在 `_SMOKE_COMMANDS` 元组（`selfcheck.py:51-60`）追加一行：

```python
("drawio_layout_validator --help", ["scripts/drawio_layout_validator.py", "--help"]),
```

> **注意注册的是 `--help` 冒烟，不是真实校验**。`_SMOKE_COMMANDS` 的既有语义是"关键脚本的命令行可执行性冒烟"（`selfcheck.py:50` 注释），全部 8 条现有条目都是 `--help` 或无参调用。**不应**在此注册真实的 figures 目录校验 —— 那会使 selfcheck 依赖具体项目数据，而它是 skill 级自检。真实校验的调用点是 §2 的 §6.10。

---

## 7. 阶段 9 终稿前复检

**必要性**：`.drawio` 可能在阶段 7-8 被人工编辑（逃生舱的正当用途），此前的校验结论即失效。且人工用 draw.io 另存会把文件变成 base64+deflate 压缩格式。

```bash
# 阶段 9 转换前
python scripts/drawio_layout_validator.py --figures-dir research/figures \
    --on-compressed decompress
```

**mtime 比对判据**：若任一 `.drawio` 的 mtime **晚于** `.layout-gate-report.json` 的 `generated_at`，则报告已过期 → 必须重跑。

> **诚实标注**：该机制**无法覆盖"编辑后不重跑"** —— 若操作者既编辑了图又不跑门禁，mtime 比对本身也不会被执行（承 00 号 L-7）。这是自觉性约束，非机器强制。

---

## 8. 完整时序

```
┌─ 阶段 6 出图 ────────────────────────────────────────────────┐
│                                                              │
│  [Agent] 读 outline.md + 架构卡                              │
│      │                                                       │
│      ▼  B4后: 构造 IR（零坐标）    B1-B3: 直接写 .drawio      │
│  [Agent] ──────────────┬──────────────────────────┐          │
│                        │ B4后                     │ B1-B3    │
│                   [脚本] drawio_generator.py       │          │
│                        │ 确定性坐标 + snap + bbox反推│          │
│                        └──────────┬───────────────┘          │
│                                   ▼                          │
│                          research/figures/*.drawio           │
│                                   │                          │
│  ┌────────────────────────────────▼─────────────────────────┐│
│  │ [脚本] 门禁1  drawio_layout_validator.py  (G1-G11)       ││
│  │        → .layout-gate-report.json  (留痕)                ││
│  └────────────────────────────────┬─────────────────────────┘│
│         exit≠0 ─────────┐         │ exit=0                   │
│                         ▼         ▼                          │
│              [orchestrator]    导出 PNG                       │
│              查 §3.2 路由表        │                          │
│                 │                 ▼                          │
│      retryable=false ──► 停机   [脚本] 门禁2 figure_gate.py   │
│      retryable=true  ──┐          │ (存在性/宽度/DPI)         │
│         ≤3轮 且 未熔断  │          │                          │
│              └─回Agent─┘     exit=0 ▼                        │
│                              🔴 CHECKPOINT → 阶段 7           │
└──────────────────────────────────────────────────────────────┘
                                    │
┌─ 阶段 9 终稿前 ────────────────────▼─────────────────────────┐
│  mtime(.drawio) > report.generated_at ? ──► 重跑门禁1        │
│  再跑 figure_gate.py --stage stage9                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. 门禁执行可验证性（承 00 号 §3.1）

**问题重述**：`figure_gate.py` 有效、Agent 定义也明文要求"exit code 非零即不得交付"，**缺陷图仍然交付了**。实跑证实门禁能拦住 3-1（exit=1）。失效路径收窄为"从未执行"或"退出码被吞"。

### 9.1 三项机制

| 机制 | 内容 | 能防住什么 | 防不住什么 |
|------|------|-----------|-----------|
| **留痕文件** | 校验器落 `.layout-gate-report.json`（含 `generated_at`/`tool_invocation`/逐文件结论） | "从未执行"——文件不存在即判失败 | 伪造文件 |
| **mtime 比对** | 报告 `generated_at` 必须晚于所有 `.drawio` 的 mtime | "跑了旧版本"/"改图后不重跑" | 篡改时间戳 |
| **禁止吞码** | 反例第 26 条 + §6.10 正误写法对照 | `\| tail` / `$?` 类静默失效 | 故意不检查 |

### 9.2 诚实评估

**这套机制不构成密码学意义的保证。** Agent 理论上可以伪造 `.layout-gate-report.json`。它的作用是：

1. 把"什么都不做就能通过"变为"必须主动伪造才能通过"——**提高绕过成本**；
2. 留下**可审计痕迹**——报告内容与实际 `.drawio` 不符是可被复核发现的。

> 与 `SKILL.md:228` 的自我评估一致：真正有效的护栏是产物层面的机器门禁。**D5 的留痕机制属于"提高成本 + 可审计"，不属于"不可绕过"。** 不做过度承诺。

---

## 10. 本层未闭环局限

| # | 局限 |
|---|------|
| **W-1** | **B1~B3 阶段重试的收敛性无保障**。§3.3 的收敛论证依赖"每轮修改 IR 语义"，但 IR 是 B4 才有的。B1-B3 阶段重试仍是"Agent 手改坐标"——**正是被证明失效的算子**。故 B1-B3 期间应把重试预算视为**尽力而为**，主要价值在于"可观测"而非"可修复"。 |
| **W-2** | ~~G10 在 B1-B3 恒为 not_applicable~~ → **已部分解除**：第三轮拆分为 **G10a**（零阈值纯边集，**B1 生效**，实跑覆盖 11/15 张、0 假阳 0 假阴）与 **G10b**（stack 的 rank，B4 后生效，覆盖余 4 张）。**C-1 在 B1 阶段对 11/15 张图已生效**；仅 stack 类 4 张仍待 B4。 |
| **W-3** | ~~`selfcheck.py` 集成方式未验证~~ → **已结案，见 §6.1**：实测 `selfcheck.py` 不吞码（`subprocess.run` 捕获 `returncode`、`code == 0` 判定、`sys.exit(0 if passed else 1)`），注册有效。 |
| **W-4** | **两级门禁增加了一个可跳过环节**。此前只有一道 figure_gate，现在有两道；若操作者只跑第二道（更熟悉的那道），布局校验就被绕过。**门禁数量增加本身会稀释每道门禁被执行的概率** —— 这是本设计引入的新风险，缓解手段仅为 §9 的留痕。**待第二轮审查裁决是否应合并为单一入口脚本。** |
| **W-6** | **`forced` manual 的判定权在生成器，而生成器由 D5 设计**。若模式库覆盖不足，生成器会大量判 `forced`，而 `forced` 不阻断 → 布局纪律实质放宽。§4.1 用"forced >30% 报 warning"暴露该情况，但 **warning 不阻断，故理论上可长期停留在高 forced 状态**。这是为解开死锁付出的代价，属知情取舍。 |
| **W-5** | **阶段 9 复检的触发依赖 mtime，而 git checkout / 文件复制会重置 mtime**。跨机器传递项目目录后 mtime 全部变新，会触发不必要的重跑（假阳性，可接受）；但若 mtime 被设为过去时间则漏检（假阴性）。未采用内容哈希——因为哈希需要读全部文件内容，与"零依赖轻量"目标冲突（可接受的取舍，但须知情）。 |
