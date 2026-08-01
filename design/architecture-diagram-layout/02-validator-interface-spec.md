# D5-02：校验器接口规格（`drawio_layout_validator.py`）

> **状态：设计稿，待用户审核，尚未执行**
> 批次归属：**B1**（只读校验器，可独立上线）
> 职责边界：01 号定义"判据算法是什么"，本文定义"这些判据如何被封装成外部可调用的校验器"

---

## 1. 定位裁决（承 00 号 D5-R6）

**新增独立脚本，不扩展 `figure_gate.py`。** 三条理由：

| 理由 | 依据 |
|------|------|
| 输入不同 | `figure_gate` 读 `outline.md` + `*.png`；本校验器读 `*.drawio` 源文件 |
| 依赖不同 | `figure_gate` 在 `Pillow`/`PyYAML` import 失败时直接 `sys.exit(1)`；本校验器**零第三方依赖**，不应继承该失败模式 |
| 回归风险 | `figure_gate` 刚经 D3 三次改动（入口解析、空清单判 FAIL、`_validate_png` 去重），不动它风险最低 |

**调用顺序：本校验器（源文件层）→ `figure_gate.py`（产物层）。** 必须先跑本校验器 —— PNG 层诊断具误导性（3-1 报"宽度 325px 不足"，照此加大 scale 只会得到 650px 的同样残缺图，真因只在源文件层可见）。

---

## 2. CLI 契约

```bash
python scripts/drawio_layout_validator.py [OPTIONS]
```

| 选项 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--figures-dir` | path | `research/figures` | 批量校验目录下全部 `*.drawio` |
| `--file` | path (repeatable) | — | 只校验指定文件，可多次给出；与 `--figures-dir` 互斥 |
| `--ir` | path | — | 校验 IR JSON（B4 后启用，做 G10 拓扑-模式一致性） |
| `--exemptions` | path | `research/figures/layout-exemptions.yaml` | 豁免白名单；文件不存在时视为空白名单（不报错） |
| `--on-compressed` | `decompress\|fail\|skip` | `decompress` | 压缩格式 `.drawio` 处置（承 00 号 §9.4） |
| `--strict` | flag | false | warning 一并计入失败（**仅供人工排查，不可作 CI 默认，也不得用于 manual 图**，见 §6.3 与 I-3） |
| `--mode` | `warn\|block` | `block` | **warn**：所有 error 降级为 warning，恒 exit 0（B1 上线用）；**block**：正常判定（B3 起） |
| `--json` | flag | false | 输出 JSON 而非文本报告 |
| `--report-out` | path | `research/figures/.layout-gate-report.json` | 门禁留痕文件落盘路径（B2 依赖） |
| `--max-manual-ratio` | float | `0.40` | manual 模式占比上限（承 00 号 §9.2；仅 `--ir` 模式生效） |

**命名风格对齐现有仓库**：`--figures-dir`/`--strict`/`--json` 与 `figure_gate.py` 同名同义。

---

## 3. Exit Code 约定（**D5-10 第三轮改造**）

> **改造理由**：第二轮审查 B-C2 指出，调用方一律写 `if ($LASTEXITCODE -ne 0)`，故细分退出码**全部退化为"失败"**，且 **exit 4 会误伤无架构图的合法项目**。同仓库 `figure_gate.py:436-462` 已有正确范式未被采纳。

### 3.1 采纳 figure_gate 的条件性判断范式

**取消 exit 4。** 空清单不再是独立退出码，而是**条件性判断**：

```python
# 复用 figure_gate.py:436-462 的既有范式
if not drawio_files:
    declared = _declared_architecture_figure_count(outline_path)  # 读 core_architecture_figures
    if declared > 0:
        return {"passed": False, "error":
                f"outline 声明 {declared} 张核心架构图，但 figures 目录下 0 个 .drawio"}
    return {"passed": True, "note": "outline 未声明架构图，无需校验"}
```

**效果对比**：

| 场景 | 旧设计（exit 4） | 新设计（条件性判断） |
|------|----------------|-------------------|
| 纯文字报告（`core_architecture_figures: 0`） | ❌ exit 4 → 被判失败 → **误伤** | ✅ **exit 0** + note |
| 声明 15 张但目录为空 | exit 4 | ✅ **exit 1**（真失败） |

**判断权在 outline 的声明，不在 Agent 的临时判断** —— Agent 不能以"我觉得这个报告不需要图"为由跳过门禁。且**与 `figure_gate.py` 复用同一字段**，不新增声明来源。

### 3.2 最终退出码表（三档）

| code | 语义 | 触发条件 |
|-----:|------|---------|
| **0** | PASS | 无 error（warning 不阻断，除 `--strict`）；或 outline 未声明架构图 |
| **1** | 校验失败 | 存在任一 error；或 outline 声明 >0 而目录为空 |
| **2** | 部分校验 | 有文件被 skip（`--on-compressed skip`）→ **不可视为通过** |

**脚本自身错误**（目录不存在、豁免文件格式非法）**并入 exit 1**，细分原因写 JSON 的 `error` 字段。

> **设计原则**：**退出码只承载"能否继续"，细分语义全部走 JSON。** 三档中 1/2 都是"不可继续"，故即便调用方只判 `!= 0` 也**不会误判**——这是刻意让退化无害。

---

## 4. JSON 输出 Schema

**核心要求：每个 issue 必须携带可直接生成数值化修复反馈的完整证据**（承 00 号 §9.3、01 号 §4），不得是笼统的 `true/false`。

```jsonc
{
  "schema_version": "d5-layout-1",
  "passed": false,
  "exit_code": 1,
  "generated_at": "2026-07-30T14:22:31+08:00",
  "validator_version": "0.1.0",
  "tool_invocation": "drawio_layout_validator.py --figures-dir research/figures",

  "summary": {
    "files_total": 15,
    "files_passed": 11,
    "files_failed": 3,
    "files_skipped": 1,
    "errors": 7,
    "warnings": 12,
    "vertex_total": 376,            // 口径A：所有 vertex="1"
    "vertex_geometry_valid": 370,   // 口径C：四个几何值均可 float()
    "vertex_geometry_broken": 6,    // A-C 差值 —— 最高优先级告警信号
    "manual_ratio": null            // 仅 --ir 模式下有值
  },

  "items": [
    {
      "file": "3-1-SCI六层认知升维金字塔.drawio",
      "format": "plain",            // plain | compressed
      "passed": false,
      "vertex_total": 6,
      "vertex_geometry_valid": 0,
      "page": { "width": 1300, "height": 940 },
      "content_bbox": null,         // 几何损坏时无法计算
      "checks": {
        "G1_geometry_integrity": "fail",
        "G2_overlap":            "skip",   // G1 失败时后续几何判据无意义
        "G3_overflow":           "skip",
        "G4_grid_alignment":     "skip",
        "G5_aspect_ratio":       "skip",
        "G6_embedded_caption":   "pass",
        "G7_fake_diagram":       "pass",
        "G10_topology_mode":     "not_applicable",  // 需 --ir
        "G11_legend_placement":  "not_applicable"   // 无图例元素
      },
      "issues": [
        {
          "check": "G1_geometry_integrity",
          "error_code": "GEOMETRY_INVALID",
          "severity": "error",
          "cells": [
            { "id": "L6", "attr": "x",     "literal": "None" },
            { "id": "L6", "attr": "width", "literal": "None" }
          ],
          "message": "6 个 vertex 的 x/width 字面值为字符串 \"None\"（共 12 处）",
          "feedback": "节点 L1~L6 的 x 与 width 属性值为 \"None\"，非数值。该文件导出的 PNG 仅 325px 宽。此为生成器缺陷，不可通过重试修复。",
          "retryable": false
        }
      ]
    },
    {
      "file": "11-1-国际空间认知智能竞争格局矩阵.drawio",
      "passed": false,
      "checks": { "G2_overlap": "fail", "G11_legend_placement": "fail" },
      "issues": [
        {
          "check": "G2_overlap",
          "error_code": "HARD_OVERLAP",
          "severity": "error",
          "pair": [
            { "id": "ql3", "x": 80,  "y": 400, "w": 624, "h": 26,
              "ink": { "x": 236, "y": 402, "w": 312, "h": 22 } },
            { "id": "p10", "x": 660, "y": 390, "w": 150, "h": 70,
              "ink": { "x": 672, "y": 404, "w": 126, "h": 42 } }
          ],
          "overlap": { "w": 80, "h": 17, "area": 1360, "basis": "ink_inflated" },
          "message": "节点 ql3 与 p10 墨迹相交 80×17px",
          "feedback": "节点 ql3(x=80,y=400,w=624,h=26) 与 p10(x=660,y=390,w=150,h=70) 墨迹重叠 80×17px（面积1360）。建议：象限散点避碰间距不足，增大 dh 或减少该象限散点数。",
          "retryable": true
        },
        {
          "check": "G2_overlap",
          "error_code": "SOFT_OVERLAP_GRAY_ZONE",
          "severity": "warning",
          "pair": [ { "id": "leg1", "...": "..." }, { "id": "leg2", "...": "..." } ],
          "overlap": { "w": 57, "h": 3, "area": 171, "basis": "ink_inflated" },
          "message": "AABB 相交但墨迹相交厚度仅 3px —— 灰区，不静默放行",
          "feedback": "图例条目 leg1/leg2 贴边。根因可能是图例未置于内容区外（见 G11）。",
          "retryable": true
        }
      ]
    },
    {
      "file": "8-1-SCOS十四层总体架构.drawio",
      "passed": true,
      "checks": { "G1_geometry_integrity": "pass", "G2_overlap": "pass",
                  "G3_overflow": "pass", "G4_grid_alignment": "warning" },
      "issues": [
        {
          "check": "G4_grid_alignment",
          "error_code": "GRID_MISALIGNED",
          "severity": "warning",
          "metrics": { "aligned": 38, "total": 64, "rate": 59.4, "threshold": 90.0 },
          "message": "网格对齐率 59.4% < 90%",
          "feedback": "38/64 个几何值对齐 gridSize=10。仅影响人工编辑吸附手感，不影响导出观感。",
          "retryable": true
        }
      ]
    }
  ],

  "skipped": [
    { "file": "x.drawio", "reason": "compressed_and_skip_requested" }
  ],
  "exemptions_applied": [
    { "file": "11-1-...drawio", "cells": ["q1bg","q2bg","q3bg","q4bg"],
      "check": "G2_overlap", "source": "style:background_marker" }
  ]
}
```

### 4.1 `checks` 的四态取值

| 值 | 语义 |
|----|------|
| `pass` | 判据通过 |
| `fail` | 判据命中 error |
| `warning` | 判据命中 warning（含 G2 三态判定的灰区） |
| `skip` | **前置判据失败致本判据无意义**（G1 失败 → G2/G3/G4/G5 全部 skip） |
| `not_applicable` | 该图不含相关元素（无图例 → G11）或缺少输入（无 `--ir` → G10） |

> **`skip` 与 `pass` 必须严格区分**。3-1 若把 G2 记为 `pass`（"没检测到重叠"），会产出"仅 1 项失败、其余全绿"的误导性报告 —— 实际是**根本无法检测**。这正是编排器前期用 366 单一口径时踩过的坑。

### 4.2 `severity` 与 `retryable` 的对应

`retryable` 直接驱动 04 号的重试路由，取值须与 01 号 §3.1 判据表一致：

| error_code | severity | retryable |
|-----------|:--------:|:---------:|
| `GEOMETRY_INVALID` | error | **false**（生成器 bug） |
| `EMBEDDED_CAPTION` | error | **false**（移文本到 Markdown 即可） |
| `MANUAL_UNJUSTIFIED` | error | **false** |
| `FLOW_RECONVERGENT`（G10a） | error | **false**（须转 manual，不可改模式重试） |
| `GRID_HAS_CONNECTED_STRUCTURE`（G10a） | error | **false**（同上） |
| `STAR_NO_UNIQUE_HUB` / `STAR_HUB_NOT_DOMINANT` / `STAR_NO_EDGES`（G10a） | error | **false**（同上） |
| `STACK_MOSTLY_NONADJACENT`（G10b，B4 后） | error | **false**（同上） |
| `HARD_OVERLAP` | error | true |
| `CONTENT_OVERFLOW_FATAL` | error | true |
| `FAKE_DIAGRAM` | error | true |
| `LEGEND_INSIDE_CONTENT` | error | true |
| `SOFT_OVERLAP_GRAY_ZONE` | warning | true |
| `CONTENT_OVERFLOW_WARN` | warning | true |
| `GRID_MISALIGNED` | warning | true |
| `ASPECT_RATIO_EXTREME` | warning | true |

---

## 5. 文本报告格式

对齐 `figure_gate.py` 的 `format_report()` 风格（`[OK]`/`[FAIL]`/`[WARN]` + 分节 + 总判定行）。以实测真实数据为样例：

```
============================================================
布局质量门禁报告 (drawio_layout_validator) — B1
============================================================

来源: research/figures （15 个 .drawio）
顶点统计: 376 总计 / 370 几何可解析 / 6 几何损坏  ← 损坏 > 0 即最高优先级

--- 几何损坏 (FATAL, 不可重试) ---
  [FAIL] 3-1-SCI六层认知升维金字塔.drawio
         L1~L6 的 x/width 字面值为 "None"（12 处）
         -> 该文件导出 PNG 仅 325px 宽。生成器缺陷，重试无效。
         -> G2/G3/G4/G5 因此无法检测（记 skip，非 pass）

--- 硬重叠 (FATAL) ---
  [FAIL] 11-1-国际空间认知智能竞争格局矩阵.drawio
         ql3(80,400,624,26) <-> p10(660,390,150,70) 墨迹相交 80x17px
         ql4(560,400,624,26) <-> p12(...) 墨迹相交 6x26px
         (已豁免 4 块象限背景板 q1bg~q4bg)

--- 内嵌图注 (FATAL, 不可重试) ---
  [FAIL] 12-1: bottomNote  "图注：SCIF理论体系全景展示..."（同时右溢 +207px）
  [FAIL] 4-1:  note1       "图注：六维空间世界模型..."（同时右溢 +100px）
  [FAIL] 4-2:  note2       "图注：空间世界预测模型..."

--- 灰区与告警 (WARN, 不阻断) ---
  [WARN] 11-1: leg1<->leg2 AABB相交但墨迹厚度仅 3px（灰区）
  [WARN] 11-1: 图例位于内容区内部（G11）—— 疑为上条灰区的根因
  [WARN] 8-2:  网格对齐率 23.0% < 90%
  [WARN] 12-1: 内容跨度 1.15x pageWidth（<1.8x 硬失败线）

--- 逐项详情 ---
  [OK]    8-1-SCOS十四层总体架构.drawio        16 顶点  0 重叠  0 溢出
  [OK]    10-1-SCIF关键技术路线图.drawio      108 顶点  0 重叠  0 溢出
  [FAIL]  3-1-SCI六层认知升维金字塔.drawio       6 顶点  几何损坏
  ...

=== 总判定: FAIL (7 errors, 12 warnings) — exit 1 ===
留痕: research/figures/.layout-gate-report.json
```

---

## 6. 豁免机制（白名单式，非开关）

承 00 号 D5-R3：豁免必须**具名**、且**出现在报告中可被审计**。

### 6.1 两条豁免来源

```yaml
# research/figures/layout-exemptions.yaml
exemptions:
  - file: "11-1-国际空间认知智能竞争格局矩阵.drawio"
    check: G2_overlap
    cells: [q1bg, q2bg, q3bg, q4bg]
    reason: "四象限背景板，与散点的包含关系为有意设计"
```

**自动识别（无需人工登记）**：`style` 含 `swimlane`/`group`/`container=1`，或显式 `is_background=true` 标记 → 自动豁免 G2，并记入 `exemptions_applied`。

### 6.2 反滥用约束

| 约束 | 说明 |
|------|------|
| 无通配符 | `cells` 不接受 `*`；必须逐个具名 |
| 无 check 级全关 | 不提供 `--skip-check G2` 之类选项 |
| 必填 `reason` | 缺失 → exit 3（配置非法） |
| 强制留痕 | 所有生效豁免写入 `exemptions_applied`，可被审计"是否有人靠加豁免让门禁变绿" |
| 仅豁免 G2 | 豁免机制**只对重叠判据开放**。G1（几何损坏）/G6（内嵌图注）**不可豁免** |

> **诚实标注**：豁免文件本身可被 Agent 写入。这是"提高绕过成本"而非"杜绝绕过"（承 00 号 L-4）。可审计性是唯一防线 —— 报告里 `exemptions_applied` 的膨胀是可观测信号。

### 6.3 manual 图的校验模式（**D5-09 解开第二层死锁**）

> **第二轮审查 B-C1 发现的死锁**：原设计规定 manual 图"强制走 `--strict` + 重试预算 0"。而 `--strict` 把 warning 一并计入失败 —— 实测现有 15 张图共 **12 个 warning**，strict 下**全部转红**。任何进入 manual 的图都必然失败且无重试机会 → **无出路**。

**定案（取代原规定）**：

| 项 | 原设计 | **第三轮定案** |
|----|--------|-------------|
| 校验模式 | `--strict`（warning 计入失败） | **常规模式**（warning 不阻断） |
| 重试预算 | **0** | **1** |
| error 判定 | 同常规 | 同常规（**不加严**） |

**理由**：
1. `--strict` 的立法目的是**人工排查时看全部问题**，不是惩罚 manual。用它做 manual 的门禁属工具误用。
2. manual 图的 error 判据与常规图**完全相同**（G1/G2/G6 该拦的照拦）—— manual 豁免的是"布局模式纪律"，**不是几何质量**。
3. 重试预算 1 而非 0：manual 图的坐标由 Agent 手写，**至少应给一次按数值化反馈修正的机会**。0 预算意味着"一次不过即上报"，与 `retryable=true` 的 error 语义矛盾。

**约束不变**：manual 仍须填 `manual_reason` + `attempted_modes`（缺失 → `MANUAL_UNJUSTIFIED`），仍计入 `manual_ratio`（`elective` 类），仍在报告中登记。**放宽的只是"用错了的 strict 开关"和"自相矛盾的 0 预算"。**

---

## 7. 容错与降级

| 场景 | 处置 |
|------|------|
| 压缩格式 `.drawio` | 默认 `decompress`（`base64` + `zlib.decompress(data,-15)` + `urllib.parse.unquote`，纯标准库，实测可行） |
| `ET.parse()` 抛 `ParseError` | 记 error（`XML_MALFORMED`），**不 skip** —— XML 坏了是真缺陷 |
| 解压失败 | 记 error（`DECOMPRESS_FAILED`） |
| 目录 0 个文件 | **条件性判断**（D5-10）：outline 声明 >0 → **exit 1**；声明 0 → **exit 0** + note。**不再使用 exit 4** |
| `record_degradation` 不可用 | 沿用 `figure_gate.py` 的 `try/except ImportError` → no-op 降级写法 |

**依赖策略**：**零第三方依赖**（`xml.etree.ElementTree`/`re`/`html`/`unicodedata`/`base64`/`zlib`/`json`/`argparse`/`pathlib` 全为标准库）。`yaml` 仅用于读豁免文件 —— 若 `PyYAML` 不可用则降级为"豁免文件不可读 → 视为空白名单 + warning"，**不因此失败**（豁免只会让门禁更宽松，读不到反而更严）。

---

## 8. 单元测试规格（**D5-11 事实订正**）

> **原文错误**：本节此前称"仓库唯一测试目录为 `scripts/md2docx/tests/`"。**这是事实错误。**
>
> **实际情况**（证据 `scripts/selfcheck.py:45-48`）：
>
> ```python
> _TEST_SUITES = (
>     ("tests", "tests"),                        # <- 顶层 tests/ 确实存在
>     ("md2docx-tests", "scripts/md2docx/tests"),
> )
> ```
>
> 顶层 `tests/` 存在且被 `selfcheck.py` 覆盖。**新测试应放顶层 `tests/`**，命名 `tests/test_drawio_layout_validator.py`，这样会被 `selfcheck.py` 的 `_TEST_SUITES` 自动纳入，无需额外注册。

用实测数据构造 fixture：

| fixture | 内容 | 断言 |
|---------|------|------|
| `broken_none.drawio` | 6 个 vertex 的 `x`/`width` = `"None"` | exit 1；`G1=fail`；`G2..G5=skip`（**非 pass**）；`retryable=false` |
| `bg_overlap.drawio` | 4 块背景板 + 12 散点，2 对硬重叠 | 豁免生效后 `errors=2`；`exemptions_applied` 含 4 个 bg |
| `gray_zone.drawio` | 两个图例条目垂直贴边 2px | `G2=warning` 而非 fail；`basis=ink_inflated` |
| `overflow.drawio` | 内容跨度 1.15× / 2.0× pageWidth | 前者 warning、后者 error |
| `caption.drawio` | 含 `图注：` 开头的 mxCell | `G6=fail`；`retryable=false` |
| `flow_reconvergent.drawio` | 主链 + 3 分支 + 汇合（仿 4-2） | `G10a=fail`，`error_code=FLOW_RECONVERGENT` |
| `grid_with_spine.drawio` | 声明 grid 但含连通骨架（仿 7-1） | `G10a=fail`，`GRID_HAS_CONNECTED_STRUCTURE` |
| `clean.drawio` | 16 顶点、0 重叠、100% 对齐 | exit 0 |
| `empty_dir/` + outline 声明 0 张 | 无 `.drawio` | **exit 0** + note（D5-10 条件性判断） |
| `empty_dir/` + outline 声明 15 张 | 无 `.drawio` | **exit 1**（真失败） |
| `compressed.drawio` | base64+deflate | `decompress` 下正常校验；`skip` 下 exit 2 |

---

## 9. 本层未闭环局限

| # | 局限 |
|---|------|
| I-1 | **`--ir` 模式（G10b）在 B1 阶段无输入可用**。现有 `.drawio` 无 `rank` 字段（实测 0/15），G10b 只能在 B4 之后生效。**但 G10a 不受此限** —— 第三轮已拆分，G10a 用纯边集判定，**在 B1 即可生效并已实跑通过**（0 假阳 0 假阴）。故 C-1 在 B1 阶段**部分生效**（flow/star/grid 覆盖 11/15 张），仅 stack 类 4 张待 B4。 |
| I-5 | **`INK_INFLATE` 与 `MIN_INK_THICKNESS` 方向对冲**，安全窗口约 6%。两参数不应各自独立调整，但接口未提供联动校验机制 —— 实施者可能只改一个而破坏平衡。 |
| I-2 | **报告留痕文件可被伪造**。校验器写 `.layout-gate-report.json`，但无签名机制。下游只能校验"存在 + mtime 晚于 .drawio"，无法证明内容真实（承 L-4）。 |
| I-3 | **`--strict` 会使当前 15 张图全红**（12 个 warning 全部升级为 error）。故 strict **不应作为默认门禁模式**，仅用于人工排查。若误将 strict 设为 CI 默认，会重演 `stage-6-diagrams.md:229` 警示的"门禁全红→反向逼迫放宽"。 |
| I-4 | **`exemptions_applied` 的审计依赖人看**。膨胀是可观测信号，但没有机制自动判定"豁免过多"。未设阈值 —— 因为缺乏基线数据知道多少算多。 |
