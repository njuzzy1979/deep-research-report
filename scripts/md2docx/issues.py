"""Issue 数据类型、分级枚举、代码注册表与 IssueCollector。

本模块只定义数据结构，不做任何打印/落盘（由 report.py 消费 IssueCollector 产出报告）。
Issue 代码以 02-algorithms.md §0.3 总表为唯一权威（R8），本文件照抄该表并按
00-master-design.md 的裁决补充少量新码（每个新码都带出处注释）。

IssueCollector 由 pipeline.py 创建，作为显式参数传入各阶段（不用全局单例，保证可测试性
与阶段归属清晰——01-architecture.md §6.2）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# 分级枚举
# ---------------------------------------------------------------------------

class Level(Enum):
    """问题分级：FATAL/ERROR/WARNING/INFO（01-architecture.md §6.1）。"""

    FATAL = "FATAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# ---------------------------------------------------------------------------
# Issue 数据类
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    """单条问题记录（01-architecture.md §6.2 骨架 + R8 补充字段）。

    字段：
        level         分级
        code          稳定编码，如 E-IMG-01 / W-XREF-01（见下方 ISSUE_CODE_REGISTRY）
        stage         产生该问题的阶段名（normalize/clean/parse/assemble/validate/
                      render/report/pipeline 等）
        message       人读描述（中文）
        source_line   回溯到原始 md 行号；不适用时为 None
        element_ref   定位到具体元素，如 "图2-2" / "表4-1" / "H2:第三章"；不适用为 None
        suggestion    修复建议；不适用为 None
        gate          来源门禁编号（R8），如 "gate1"/"gate2"/"gate3"；非门禁产生的
                      Issue（如管道内部错误）为 None
        needs_review  R8：非独立第五分级，而是叠加在任意分级之上的标记，表示该问题
                      需要人工复核（如密级弱信号命中）；默认 False
    """

    level: Level
    code: str
    stage: str
    message: str
    source_line: int | None = None
    element_ref: str | None = None
    suggestion: str | None = None
    gate: str | None = None
    needs_review: bool = False


# ---------------------------------------------------------------------------
# Issue 代码注册表（02-algorithms.md §0.3 为唯一权威；新增码逐条注明出处裁决号）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IssueCodeInfo:
    """代码注册表条目：级别为文档原表标注的“典型/默认”级别，仅供文档速查用途。

    注意：Issue 实例的实际 level 由抛出点显式构造决定，registry 不会反过来强制覆盖
    已构造 Issue 的 level（例如 E-ENC-01 在 02 §0.3 表中标注为“错误”，但阶段0 解码
    失败属于 01-architecture.md §6.1 定义的 FATAL 场景，抛出点会显式使用
    Level.FATAL——这是记录在案的既有裁决，不是本注册表的缺陷）。
    """

    level: Level
    description: str
    provenance: str


ISSUE_CODE_REGISTRY: dict[str, IssueCodeInfo] = {
    # ---- 02 §0.3 总表（原样照抄，唯一权威） ----
    "E-ENC-01": IssueCodeInfo(Level.ERROR, "输入文件非法 UTF-8", "02 §0.3"),
    "E-IMG-01": IssueCodeInfo(Level.ERROR, "图片文件不存在（全部回退路径失败）", "02 §0.3"),
    "E-IMG-02": IssueCodeInfo(Level.ERROR, "引用 SVG 且无同名 PNG 可替代", "02 §0.3"),
    "W-IMG-01": IssueCodeInfo(Level.WARNING, "图片 alt 不匹配“图X-Y”模式（按无题注普通图处理）", "02 §0.3"),
    "W-IMG-02": IssueCodeInfo(Level.WARNING, "图片像素宽 <1102px（14cm 下不足 200dpi，印刷模糊风险）", "02 §0.3"),
    "I-IMG-03": IssueCodeInfo(Level.INFO, "图片像素宽 1102-1653px（不足 300dpi，可接受）", "02 §0.3"),
    "W-IMG-04": IssueCodeInfo(Level.WARNING, "图号章号与所在章重编后章序不一致", "02 §0.3"),
    "W-IMG-05": IssueCodeInfo(Level.WARNING, "图号重复", "02 §0.3"),
    "W-IMG-06": IssueCodeInfo(Level.WARNING, "章内图号跳号或乱序", "02 §0.3"),
    "W-IMG-07": IssueCodeInfo(Level.WARNING, "行内混排图片（已抽出为独立块渲染）", "02 §0.3"),
    "W-IMG-08": IssueCodeInfo(Level.WARNING, "网络图片 URL（不嵌入，文字占位）", "02 §0.3"),
    "W-TBL-01": IssueCodeInfo(Level.WARNING, "孤立表题注（加粗“表X-Y”整行段后未紧跟表格，保留渲染）", "02 §0.3"),
    "W-TBL-02": IssueCodeInfo(Level.WARNING, "表号重复/跳号/章号不一致", "02 §0.3"),
    "W-HDR-01": IssueCodeInfo(Level.WARNING, "章/节原手动编号与重编结果不一致（跳号/重复/乱序）", "02 §0.3"),
    "W-HDR-02": IssueCodeInfo(Level.WARNING, "附录原字母与重编字母不一致", "02 §0.3"),
    "W-HDR-03": IssueCodeInfo(Level.WARNING, "出现多个 H1（首个为主标题，其余降级为章处理）", "02 §0.3"),
    "W-HDR-04": IssueCodeInfo(Level.WARNING, "md H5/H6 标题疑似带手动编号（不剥离，提示人工）", "02 §0.3"),
    "W-HDR-05": IssueCodeInfo(Level.WARNING, "前置件（摘要等）内出现下级标题（不编号渲染）", "02 §0.3"),
    "W-CLN-01": IssueCodeInfo(Level.WARNING, "密级弱信号命中（仅提示，不改正文）", "02 §0.3"),
    "I-CLN-02": IssueCodeInfo(Level.INFO, "密级强信号已过滤（记录原文）", "02 §0.3"),
    "W-CLN-03": IssueCodeInfo(Level.WARNING, "文末孤立斜体说明段，疑似过程残留（保留渲染）", "02 §0.3"),
    "W-CLN-04": IssueCodeInfo(Level.WARNING, "疑似 HTML 标签残留（非整行 div，不删除仅提示）", "02 §0.3"),
    "I-CLN-05": IssueCodeInfo(Level.INFO, "清理规则删除/剥离动作台账（每动作一条）", "02 §0.3"),
    "W-REF-01": IssueCodeInfo(Level.WARNING, "图/表存在但正文 0 引用", "02 §0.3"),
    "W-REF-02": IssueCodeInfo(Level.WARNING, "先见图后见文（首次正文引用晚于图/表位置）", "02 §0.3"),
    "W-REF-03": IssueCodeInfo(
        Level.WARNING,
        "正文引用了不存在的图/表编号（含孤立图引用行形状检测，02 §E.3 两处复用同一代码）",
        "02 §0.3 / 02 §E.3",
    ),
    "W-REF-04": IssueCodeInfo(Level.WARNING, "“上图/下图/上表/下表”位置性指代残留", "02 §0.3"),
    "W-PB-01": IssueCodeInfo(Level.WARNING, "H2 前缺分页已自动补插（记录位置）", "02 §0.3"),
    "I-PB-02": IssueCodeInfo(Level.INFO, "相邻重复分页已去重", "02 §0.3"),
    # ---- 00-master-design.md 裁决新增码（逐条注明出处裁决号） ----
    "I-PB-03": IssueCodeInfo(
        Level.INFO,
        "分节符吸收 HrToken 留痕：H2 边界原有的显式 --- 被分节符接管，未重复触发分页",
        "R4（00-master §3.3）",
    ),
    "I-TOC-01": IssueCodeInfo(
        Level.INFO,
        "“目录→图表目录”换页：breaks.py 规划 origin=AUTO_TOC 的 PageBreakIR",
        "M1（00-master §4.1）",
    ),
    "W-SEC-02": IssueCodeInfo(
        Level.WARNING,
        "检测到 N 个位于首个内容节之前的前导元素（标题/段落），已并入首个内容节"
        "渲染，请确认其位置符合预期（四节方案下并入 ABSTRACT 节，用罗马页码/"
        "摘要页眉）",
        "P-007（07-p3-fixes-design.md §3.3(c)）",
    ),
    "I-HDR-06": IssueCodeInfo(
        Level.INFO,
        "识别到标题后的前置件 H1（如“前言/导论”），已作为前置件区起点，"
        "未按多余 H1 降级（不发 W-HDR-03）",
        "P-006（07-p3-fixes-design.md §2.4 P006-1）",
    ),
    "W-FM-01": IssueCodeInfo(
        Level.WARNING,
        "前置件区内累计 N 个无编号 H2；若含正文章请为正文首章补显式编号"
        "（第X章 / 一、）以标示正文起点",
        "P-006（07-p3-fixes-design.md §2.4 P006-3 候选 C1）",
    ),
    "E-YML-01": IssueCodeInfo(
        Level.ERROR,
        "配置文件包含 metadata_defaults/behavior/report 三块之外的顶层键、块内白名单外"
        "字段，或 behavior 字段类型/值域不合法（已忽略/回退该字段）",
        "M7（00-master §4.1）；G1 交叉验证复检更名 W-YML-01→E-YML-01（级别本就是 ERROR，"
        "原 W 前缀与级别不符，属命名缺陷，一并修正）",
    ),
    "E-SEC-01": IssueCodeInfo(
        Level.FATAL,
        "门3 密级复检命中：门1/门2 的过滤未能拦截全部密级字样，视为过滤规则缺陷，"
        "中止产出并删除临时文件",
        "00-master §3.3 M3 Fatal 闭集第一类 / 03-workflow.md §3.3 第2项",
    ),
    "E-SYS-01": IssueCodeInfo(
        Level.FATAL,
        "转换器内部错误：阶段模块未就绪（延迟 import 时捕获 ImportError/AttributeError）",
        "本实现批次（C-01/C-04）新增：02/00 文档定义的代码全部针对内容处理算法，未覆盖"
        "“阶段实现模块尚未落地”这一构建期基础设施场景，故新增；参见 00-master §6 C-04 行"
        "“对缺失模块 ImportError 时产出 FATAL Issue”",
    ),
    "E-IO-01": IssueCodeInfo(
        Level.FATAL,
        "输入文件不存在或不可读（区别于 E-ENC-01 的“文件存在但非法 UTF-8”）",
        "本实现批次（C-04）新增：03-workflow.md §2.2 门1“md 文件存在性/可读性”与"
        "“md 编码可解码性”是两个独立的 Fatal 判据，02 §0.3 只登记了后者（E-ENC-01），"
        "前者需要独立代码以免语义混用",
    ),
    "E-CFG-01": IssueCodeInfo(
        Level.FATAL,
        "配置文件错误：--config 显式指定的路径不存在（参数级语义，区别于 E-SYS-01"
        "“阶段实现模块未就绪”这一构建期内部错误语义）",
        "G1 交叉验证裁决 DEV-1：pipeline.py 原先将 ConfigError 复用 E-SYS-01 上报，"
        "语义有误——ConfigError 是 04-interface-spec.md §3.3 定义的参数错误"
        "（“找不到文件即报参数错误”），不是阶段模块缺失，故新增专用代码",
    ),
}


# ---------------------------------------------------------------------------
# IssueCollector
# ---------------------------------------------------------------------------

@dataclass
class IssueCollector:
    """收集全流程 Issue；由 pipeline.py 创建并显式传参给各阶段（不用全局单例）。

    strict=True 时，append() 会把 ERROR 级问题就地升级为 FATAL（04-interface-spec.md
    §1.3："--strict 模式下，任何本应为 ERROR 级的处理直接短路为 FATAL"）。升级逻辑
    集中在这一唯一入口，避免每个阶段各自重复判断 strict 标志（呼应本设计"单一触发点"
    的一贯思想）。
    """

    strict: bool = False
    issues: list[Issue] = field(default_factory=list)

    def append(self, issue: Issue) -> None:
        if self.strict and issue.level is Level.ERROR:
            issue.level = Level.FATAL
        self.issues.append(issue)

    def has_fatal(self) -> bool:
        return any(i.level is Level.FATAL for i in self.issues)

    def has_error(self) -> bool:
        return any(i.level is Level.ERROR for i in self.issues)

    def count_by_level(self) -> dict[Level, int]:
        counts: dict[Level, int] = {lvl: 0 for lvl in Level}
        for issue in self.issues:
            counts[issue.level] += 1
        return counts

    def __iter__(self):
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)
