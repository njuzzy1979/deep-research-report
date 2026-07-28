---
portability: core
---

# 术语表（Glossary）

> 本文件是 deep-research-report skill 的术语表模板。由 `card_synthesizer_agent` 在阶段 5 完成卡片合成后编译产出，供阶段 7 `chapter_writer_agent`（术语统一参考）和 `chapter_auditor_agent`（术语一致性审计基准）使用。
>
> **性质**：硬性约束——本文件定义的 `preferred_form` 是报告中该概念的唯一合法表述，`banned_forms` 中的变体绝对禁止出现在正文中。

---

## 一、术语表条目格式（YAML front matter）

每条术语的完整元数据以 YAML front matter 形式记录在本文件末尾的 `## 四、术语元数据（YAML）` 节中。单条术语的 YAML 结构如下：

```yaml
glossary:
  - term_id: "GL-001"
    preferred_form: "空间认知智能（Space Cognitive Intelligence, SCI）"
    aliases: ["SCI", "Space Cognitive Intelligence"]
    banned_forms: ["空间智能", "空间认知 AI"]
    definition: "在空间域中持续感知环境状态、理解实体行为、推理演化趋势、预测未来态势、记忆关键经验、自主生成决策的机器认知能力"
    scope: "全报告"
    category: "原创核心概念"
    source_card: "THEORY-01"
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `term_id` | string | 是 | 术语唯一标识，格式 `GL-XXX`（XXX 为三位数字序号） |
| `preferred_form` | string | 是 | **首选表述**——报告中该概念的唯一合法文字形式。含中文全称和英文全称/缩写（如有） |
| `aliases` | list[string] | 否 | 允许的别名/简称列表。这些形式可以在正文中使用，但首次使用时必须标注（如"空间认知智能（Space Cognitive Intelligence，以下简称 SCI）"） |
| `banned_forms` | list[string] | 否 | **禁止使用的混淆形式**列表。Writer 绝对不得在正文中使用这些变体 |
| `definition` | string | 是 | 术语的精确定义，1-3 句 |
| `scope` | string | 是 | 适用范围：`"全报告"`（跨章核心概念，全文术语一致性检查的必检项）或 `"第X章"`（仅在某章内使用的局部术语） |
| `category` | string | 是 | 术语分类：`"原创核心概念"` / `"技术术语"` / `"行业通用术语"` / `"项目专有名词"` |
| `source_card` | string | 否 | 来源卡片编号（如 `THEORY-01`），指向阶段 5 产出的理论卡 |

---

## 二、人类可读术语表（正文格式）

以下为术语表的 Markdown 人类可读格式。此格式供 Writer 和 Auditor 快速查阅，也是最终报告中可选附录"术语表"的模板。

### 原创核心概念

**GL-001 空间认知智能（Space Cognitive Intelligence, SCI）**

- **定义**：在空间域中持续感知环境状态、理解实体行为、推理演化趋势、预测未来态势、记忆关键经验、自主生成决策的机器认知能力。
- **适用范围**：全报告
- **允许简称**：SCI、Space Cognitive Intelligence
- **来源卡片**：THEORY-01

**GL-002 态势认知环路（Situation Awareness Loop, SAL）**

- **定义**：描述空间态势认知系统"感知-理解-推理-预测-决策"五个阶段闭合循环的概念模型。
- **适用范围**：第2章、第3章
- **来源卡片**：THEORY-02

### 技术术语

**GL-010 双行轨道根数（Two-Line Element, TLE）**

- **定义**：美国太空军定期发布的空间目标轨道参数标准格式，包含轨道六根数及摄动项。
- **适用范围**：第3章、第4章
- **允许简称**：TLE
- **来源卡片**：TECH-05

### 项目专有名词

**GL-020 空间态势认知智能框架（SCIF）**

- **定义**：本项目提出的面向空间域态势认知的多智能体协同框架，整合感知、推理、预测与决策能力。
- **适用范围**：全报告
- **来源卡片**：ARCH-01

---

## 三、术语一致性规则（硬性约束）

1. **原创概念只使用 `preferred_form`**：`category` 为 `"原创核心概念"` 的术语，正文中必须逐字使用其 `preferred_form`（含括号内的英文全称/缩写）。不得使用 `banned_forms` 中的任何变体。

2. **别名首次使用必须标注**：`aliases` 中列出的简称在正文中首次出现时，必须附带完整标注（如"以下简称 XXX"）。

3. **首次出现判断以 glossary 为准**：某概念是否"首次出现"以 glossary 中 `scope` 字段为准。`scope="全报告"` 的概念在全报告范围内只做一次首次展开；`scope="第X章"` 的概念在对应章内首次出现时展开。

4. **同一概念全文使用同一 `preferred_form`**：不允许同一概念在不同章中出现表述变异（如第 3 章写"态势认知智能"、第 5 章写"空间态势认知智能"）。

---

## 四、术语元数据（YAML）

```yaml
# 术语表元数据（YAML 格式）
# 由 card_synthesizer_agent 在阶段 5 编译产出
# 供 term_consistency_check.py 脚本解析和审计

glossary:
  - term_id: "GL-001"
    preferred_form: "空间认知智能（Space Cognitive Intelligence, SCI）"
    aliases: ["SCI", "Space Cognitive Intelligence"]
    banned_forms: ["空间智能", "空间认知 AI"]
    definition: "在空间域中持续感知环境状态、理解实体行为、推理演化趋势、预测未来态势、记忆关键经验、自主生成决策的机器认知能力"
    scope: "全报告"
    category: "原创核心概念"
    source_card: "THEORY-01"
```

> **使用说明**：上方的 YAML 块是模板示例。实际使用时，`card_synthesizer_agent` 会根据阶段 5 产出的理论卡（theory-cards）中的原创概念，编译完整的术语元数据，替换此示例块。
