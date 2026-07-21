"""assemble 包：IR 域（阶段3），负责 Token 流 → DocumentIR 的语义装配。

本包将文本阶段（textstage）产出的 Token 列表，按文档结构语义分类、编号、
组装为中间表示（IR），供后续校验与渲染阶段消费。

子模块：
    metadata  — 文档头元数据装配（MetaLine → MetadataIR）
    headings  — 标题语义分类、编号剥离与结构化重编（HeadingToken → HeadingIR）
    figures   — 图三元组动态解析（ImageToken → FigureIR）
    tables    — 表题注三件套关联（Token 流 → TableIR）
    breaks    — 分页/分节规划（PageBreakIR 唯一生成点，产出 SectionPlan）
    builder   — IR 构建总控（编排全部子模块，产出 DocumentIR）
"""
from __future__ import annotations
