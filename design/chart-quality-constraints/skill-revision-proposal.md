# SKILL.md 修订建议

> 来源：design/chart-quality-constraints/00-chart-quality-design.md
> 目标：精确描述每项修订的措辞、插入位置、变更理由

---

## 修订 1：阶段 6 质量门槛 —— 新增 3 项

**插入位置**：SKILL.md 第 696 行（`🔴 CHECKPOINT` 之前，现有 5 项门槛的 `- [ ]` 列表下面）

**新增内容**：

```markdown
- [ ] **颜色映射注册表已创建**：`research/figures/color-registry.csv` 已建立，至少覆盖本报告所有核心分析章对应的架构图首张图。每个节点/实体的颜色登记后，后续出图直接复用，确保同一概念的跨图一致性
- [ ] **配色符合灰度色板**：所有架构图仅在灰度色板（#000000 / #333333 / #555555 / #777777 / #999999 / #BBBBBB / #DDDDDD / #F2F2F2 / #FFFFFF）中选择颜色。如使用强调色，仅限暗红 #D62728 且全图 ≤3 处。抽查 2 张图确认无违规彩色
- [ ] **PNG 分辨率达标**：所有 PNG 宽度 ≥1102px（对应 14cm 宽、~9pt 文字在 200dpi 下的最低打印可读阈值，与阶段 9 转换器已有的 W-IMG-02 检查一致）
```

---

## 修订 2：阶段 6 工具 A（drawio）——补充 prompt 约束模板引用

**插入位置**：SKILL.md 第 591 行（`写入: 将返回的 xml 字段内容...` 之后）

**新增内容**：

```markdown
**图表样式约束**：调用 `mcp__drawio__create_diagram` 时，在 Mermaid/XML 描述之后注入样式约束文本（完整模板见 `design/chart-quality-constraints/chart-quality-checklist.md` 第四节）：
- 配色：灰度色板 + 暗红 #D62728 唯一强调色
- 字体：≥12px（≈9pt），标题 ≥14px
- 边框：1pt #333333，箭头 1.5pt
- 背景：纯白 #FFFFFF
- 图例：>2 种灰度/形状时必须附
```

---

## 修订 3：阶段 7 写作循环 —— 步骤 3 插入 matplotlib 样式加载

**插入位置**：SKILL.md 第 751 行（`3. 立即产出该章的数据图表` 之后，`写作中遇到对比数据 → 出对比表...` 之前）

**修改内容**：将现有第 3 步替换为：

```markdown
3. **立即产出该章的数据图表**：
   a. **【新增】加载报告图表样式模板**：
      ```python
      import matplotlib.pyplot as plt
      plt.style.use('design/chart-quality-constraints/matplotlib-report-style.mplstyle')
      ```
      此模板设定了全报告统一的字体（宋体+TNR）、字号（标签10pt/刻度9pt/图例9pt）、
      灰度色板（7档）、300dpi 等全局参数。**每张图出图前必须先执行此语句**。
   b. 选择图表类型——对照 `design/chart-quality-constraints/00-chart-quality-design.md`
      第 3.4 节的"图表类型选择决策表"，禁止使用 3D 图表和 >5 扇区的饼图
   c. 写作中遇到对比数据 → 出对比表；遇到时间序列 → 出折线图；遇到占比 → 出饼图
      （≤5 项；>5 项用横向条形图）。所有数据图表用 `dpi=300` + `bbox_inches='tight'`
      保存到 `research/figures/`，文件命名 `<图号>-<描述>.png`
   d. **【新增】颜色注册**：若图中出现了新的概念/实体（`color-registry.csv` 中无记录），
      在 `color-registry.csv` 中登记其颜色映射
```

---

## 修订 4：阶段 7 质量门槛 —— 新增 3 项

**插入位置**：SKILL.md 第 838 行（`- [ ] 摘要自足性检查` 之后，`---` + `阶段 8` 之前）

**新增内容**：

```markdown
- [ ] **matplotlib 样式模板已加载**：所有数据图表的出图脚本/notebook 以 `plt.style.use('design/chart-quality-constraints/matplotlib-report-style.mplstyle')` 开头，未使用系统默认样式（grep 检查所有含 `plt.savefig` 或 `plt.show` 的文件）
- [ ] **图表类型合规**：每张数据图表的类型在决策表"首选"或"次选"列中。若使用了"禁止"类型（3D图表、>5扇区饼图等），已给出书面理由（记录在阶段 7 质量门槛备注中）
- [ ] **色盲友好**：饼图使用了阴影线（hatch）区分扇区，多系列折线图使用了不同 dash 样式 + 图例标注。纯灰度图像除外（3 档以上灰度差异足够区分）
```

---

## 修订 5：阶段 8 红队审查 —— 新增"图表一致性"维度

**插入位置**：SKILL.md 阶段 8 红队审查清单（具体行数取决于现有审查维度列表）

**新增内容**：

```markdown
5. **图表一致性审查**：
   - [ ] 抽查 3 组不同章中的同概念图（如同一实体在不同架构图中的颜色是否一致？注册表是否准确？）
   - [ ] 抽查 2 张数据图表，确认配色在灰度打印下仍可区分（截图 → 去色 → 各系列仍可分辨）
   - [ ] 所有图表是否有数据来源标注（架构图的图注/数据图的来源行）
   - [ ] 图题的描述是否传达了核心发现而非仅"X与Y的关系图"
```

---

## 修订 6：dataviz skill 集成触发点（可选）

**插入位置**：SKILL.md 阶段 7 末尾（质量门槛之前），或作为单独的提示框

**新增内容**：

```markdown
> **dataviz 颜色校验（可选）**：如果项目环境中 `dataviz` skill 可用，在阶段 7 首张数据图表
> 产出后触发 `/dataviz` 进行颜色合规校验。若不可用，执行 `python scripts/chart_checks.py
> --colors --figures-dir research/figures/` 作为等价替代。校验结果不阻塞写作流程，
> 仅记录到阶段 7 质量门槛备注中。
```

---

## 修订 7：V3.1 格式规范联动

**待用户审批后逐条执行**（不在本轮自动改动）：

| 修订 | 内容 | 位置 |
|------|------|------|
| §5.2 补充 | "配色""字体"两行后加注："精确灰度色板见 design/chart-quality-constraints/00-chart-quality-design.md §3.1" | 格式规范 §5.2 |
| §5.3 替换 | 用决策表替换现有推荐表 | 格式规范 §5.3 |
| §十一 补充 | "配色方案"表后加注灰度色板精确值 | 格式规范 §十一 |
