"""管道编排：阶段 0-6 顺序调度、FATAL 短路至报告、exit code 判定（C-04）。

pipeline.py 是全项目**唯一知道全部阶段**的模块（01-architecture.md §2.0）：各阶段
模块在函数体内延迟 import，不在模块顶层 import——这是因为 textstage/assemble/
validate/render/report 全部是后续任务（C-02/C-05/C-06~C-13）才会落地的模块，本
批次（C-01/C-03/C-04）只搭建编排骨架。

延迟 import 的调用约定（本文件对未来模块提出的占位约定，非既有设计文档给出的精确
签名——01~04 号设计文档只定义了各阶段的输入/输出**数据契约**，没有规定 Python
函数名/调用签名）：每个阶段模块被期望暴露一个模块级入口函数（约定名见各 _stage*
函数内注释）。这是本文件作者的解释性决策，供后续实现任务参考对齐；若后续任务采用
不同的函数签名，需要同步回来更新本文件对应调用点（在交付说明中列为 P3 待确认项）。

FATAL 短路（G1 交叉验证 FAIL-1 修复后的最终契约）：存在两条独立短路通道，run() 在
每个阶段调用后都会显式检查，缺一不可——
    通道①：阶段模块导入失败（ImportError，说明该阶段模块尚未实现）→ 抛
            _StageNotReady，run() 捕获并 append FATAL Issue。
    通道②：阶段模块已就绪、正常执行、正常返回，但执行过程中向传入的 IssueCollector
            append 了一条 FATAL 级 Issue（例如渲染阶段判定某个致命错误后选择继续
            返回而非抛异常）→ run() 在**每次**阶段调用后立即检查
            `issues.has_fatal()`，一旦为真就跳过后续阶段，直接进入阶段6。
阶段模块实现契约（供后续任务 C-02/C-05/C-06 等对齐）：阶段模块产生 FATAL 级问题时，
只需正常 `issues.append(Issue(level=Level.FATAL, ...))` 后正常 return，不要求
import 本模块的任何私有异常类型、不要求自行抛异常来传达 FATAL——短路判断统一由
run() 在通道②完成。若阶段模块内部确实发生了无法恢复的 Python 异常（bug 而非业务
判定），任其向上抛出交给通道①风格的" _StageNotReady 以外的其他异常"处理——本版本
暂不捕获阶段模块内部的非预期异常（超出本批次骨架搭建范围，留待 C-05 起的实现任务
按需补充 try/except，此处不做过度设计）。

FATAL 存在 → 阶段6（报告始终尝试产出——若 report.py 本身也未就绪，降级为
console_out 输出摘要，见 _emit_report）。

exit code 判定（R2 修订后的 03-workflow.md §12.2 状态机）：
    FATAL 存在 → 2
    无 FATAL 但存在 ERROR → 1
    否则 → 0
--strict 下 ERROR 在 IssueCollector.append() 处已就地升级为 FATAL（见 issues.py），
本函数不重复处理升级逻辑，只读取最终 has_fatal()/has_error() 结果。
"""
from __future__ import annotations

import datetime
import importlib
import os

from .cli import RunOptions
from .config import (
    RE_BUILD_DATE_CN,
    RE_BUILD_DATE_ISO,
    BehaviorFlags,
    ConfigError,
    load_yaml_config,
    resolve_behavior_flags,
)
from .iotools import console_out
from .issues import Issue, IssueCollector, Level


class _StageNotReady(Exception):
    """内部信号：某阶段模块尚未实现（延迟 import 失败）。"""

    def __init__(self, stage: str, original: Exception):
        super().__init__(f"阶段 {stage} 模块未就绪：{original}")
        self.stage = stage
        self.original = original


# ---------------------------------------------------------------------------
# G-11：build_date 归一化（core_properties 三时间字段幂等所需）
# ---------------------------------------------------------------------------

BUILD_DATE_FALLBACK = "2000-01-01"


def normalize_build_date(build_date_arg: str | None, metadata_date: str | None) -> str:
    """归一化 build_date 为 "YYYY-MM-DD" 字符串（G-11）。

    优先级：--build-date 显式值 > metadata.date（"2026年7月" 一类格式，来自 md 头部
    元数据）> 固定回退 2000-01-01。绝不取系统时间（R16）。

    使用的正则（RE_BUILD_DATE_CN/RE_BUILD_DATE_ISO）集中定义在 config.py 的格式
    正则模式区（G-06 集中性要求：全部格式正则须单一事实来源存放，避免 AST 反硬编码
    扫描把散落各模块的中文正则误判为内容硬编码差集）。
    """
    for candidate in (build_date_arg, metadata_date):
        if not candidate:
            continue
        candidate = candidate.strip()
        m = RE_BUILD_DATE_ISO.match(candidate)
        if m:
            return candidate
        m = RE_BUILD_DATE_CN.match(candidate)
        if m:
            year, month, day = m.group(1), m.group(2), m.group(3) or "1"
            try:
                return datetime.date(int(year), int(month), int(day)).isoformat()
            except ValueError:
                continue
    return BUILD_DATE_FALLBACK


# ---------------------------------------------------------------------------
# 阶段编排
# ---------------------------------------------------------------------------
#
# 下方各 _stageN_* 函数只负责"定位并调用阶段模块的约定入口函数"，不做 FATAL
# 短路判断——FATAL 短路统一由 run() 在每次调用后检查 issues.has_fatal() 完成
# （见模块 docstring"阶段模块实现契约"）。各阶段模块内部若判定 FATAL，只需
# `issues.append(Issue(level=Level.FATAL, ...))` 后正常 return 即可。


def _resolve_behavior(options: RunOptions, issues: IssueCollector) -> BehaviorFlags:
    """加载 YAML 配置并与 CLI 参数合并出最终 BehaviorFlags（04 §1.2/§3.3）。

    --config 显式指定但文件不存在 → ConfigError，由调用方 run() 转换为参数错误
    （FATAL/exit 2，04 §3.3："找不到文件即报参数错误"）。
    """
    md_dir = os.path.dirname(options.input_path)
    yaml_data = load_yaml_config(options.config_path, md_dir, issues)
    return resolve_behavior_flags(options.behavior_cli_overrides(), yaml_data)


def _stage0_normalize(options: RunOptions, issues: IssueCollector) -> tuple[str, dict]:
    """阶段0：读取/规范化（01 §2.1）。约定入口：textstage.normalize.normalize(path, issues)。"""
    try:
        module = importlib.import_module(".textstage.normalize", package=__package__)
    except ImportError as exc:
        raise _StageNotReady("0-规范化", exc) from exc
    return module.normalize(options.input_path, issues)


def _stage1_clean(text: str, issues: IssueCollector, dump_path: str | None = None) -> str:
    """阶段1：清理（01 §2.2）。约定入口：textstage.clean.clean(text, issues, dump_path)。"""
    try:
        module = importlib.import_module(".textstage.clean", package=__package__)
    except ImportError as exc:
        raise _StageNotReady("1-清理", exc) from exc
    return module.clean(text, issues, dump_path)


def _stage2_parse(cleaned, issues: IssueCollector):
    """阶段2：解析（01 §2.3）。约定入口：textstage.parse.parse(cleaned, issues)。"""
    try:
        module = importlib.import_module(".textstage.parse", package=__package__)
    except ImportError as exc:
        raise _StageNotReady("2-解析", exc) from exc
    return module.parse(cleaned, issues)


def _stage3_assemble(tokens, options: RunOptions, flags: BehaviorFlags, issues: IssueCollector):
    """阶段3：IR 构建（01 §2.4）。约定入口：assemble.builder.build(tokens, options, flags, issues)。"""
    try:
        module = importlib.import_module(".assemble.builder", package=__package__)
    except ImportError as exc:
        raise _StageNotReady("3-IR构建", exc) from exc
    return module.build(tokens, options, flags, issues)


def _stage4_validate(document_ir, issues: IssueCollector):
    """阶段4：渲染前校验（01 §2.4）。约定入口：validate.validate(document_ir, issues)。"""
    try:
        module = importlib.import_module(".validate", package=__package__)
    except ImportError as exc:
        raise _StageNotReady("4-渲染前校验", exc) from exc
    module.validate(document_ir, issues)
    return document_ir


def _stage5_render(document_ir, options: RunOptions, flags: BehaviorFlags, issues: IssueCollector):
    """阶段5：渲染（01 §2.0）。约定入口：render.document.render(document_ir, options, flags, issues)。"""
    try:
        module = importlib.import_module(".render.document", package=__package__)
    except ImportError as exc:
        raise _StageNotReady("5-渲染", exc) from exc
    return module.render(document_ir, options, flags, issues)


def _emit_report(options: RunOptions, issues: IssueCollector, source_meta=None,
                  gate3_results: dict | None = None, document_ir=None) -> None:
    """阶段6：转换报告（始终尝试产出）。

    约定入口：report.generate(options, issues, source_meta)。若 report.py 尚未
    实现（ImportError），按任务书要求降级为 console_out 输出摘要，不让"报告模块
    也未就绪"变成二次 FATAL——报告是附属产物，其自身缺失不应掩盖已收集的 Issue。
    """
    try:
        module = importlib.import_module(".report", package=__package__)
    except ImportError:
        _emit_fallback_summary(options, issues)
        return
    module.generate(options, issues, source_meta, gate3_results=gate3_results, document_ir=document_ir)


def _emit_fallback_summary(options: RunOptions, issues: IssueCollector) -> None:
    """report.py 未就绪时的降级摘要输出（经 console_out，全项目唯一控制台出口约定见 04 §1.4）。

    注意：console_out 的"全项目唯一允许调用方"约定在 04 §1.4 中指派给 cli.py；
    此处 pipeline.py 在 report.py 缺失时的降级摘要属于任务书本身明确要求的例外
    路径（"报告模块也可能未就绪，则降级 console_out 输出摘要"），故直接调用
    iotools.console_out，不经 cli.py 中转。
    """
    counts = issues.count_by_level()
    lines = [
        "=" * 60,
        "md2docx 转换报告（降级摘要：report.py 尚未实现）",
        "=" * 60,
        f"输入文件：{options.input_path}",
        f"输出文件：{options.output_path}",
        f"问题统计：FATAL={counts[Level.FATAL]} ERROR={counts[Level.ERROR]} "
        f"WARNING={counts[Level.WARNING]} INFO={counts[Level.INFO]}",
        "",
    ]
    for issue in issues:
        loc = f"行{issue.source_line}" if issue.source_line is not None else "-"
        lines.append(f"[{issue.level.value}] {loc} | {issue.code} | {issue.message}")
    lines.append("=" * 60)
    console_out("\n".join(lines) + "\n")


def _determine_exit_code(issues: IssueCollector) -> int:
    if issues.has_fatal():
        return 2
    if issues.has_error():
        return 1
    return 0


def run(options: RunOptions) -> int:
    """按阶段0-6 顺序调度；FATAL 短路至阶段6；返回最终 exit code。"""
    # --config 显式路径不存在属于参数错误范畴（04 §3.3），在能创建 IssueCollector
    # 之前就可能发生（因为 strict 取值本身来自尚待加载的配置），故用一个临时
    # collector 承接：即使 strict 未知，ConfigError 场景下也必然是 FATAL，不受
    # strict 影响。
    issues = IssueCollector(strict=False)
    try:
        flags = _resolve_behavior(options, issues)
    except ConfigError as exc:
        issues.append(Issue(level=Level.FATAL, code="E-CFG-01", stage="pipeline", message=str(exc)))
        _emit_report(options, issues)
        return _determine_exit_code(issues)

    # strict 已知后，用正确的 strict 值重建 collector，并保留前面已收集的 Issue
    # （load_yaml_config 阶段可能已经产生 E-YML-01 等）。
    if flags.strict != issues.strict:
        resolved_issues = IssueCollector(strict=flags.strict)
        for issue in issues:
            resolved_issues.append(issue)
        issues = resolved_issues

    if not os.path.isfile(options.input_path):
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-IO-01",
                stage="pipeline",
                message=f"输入文件不存在：{options.input_path}",
                suggestion="请检查路径拼写，或确认文件已生成",
            )
        )
        _emit_report(options, issues)
        return _determine_exit_code(issues)

    # 阶段0-5 顺序调度。每个阶段调用后立即检查 has_fatal()（FAIL-1 修复：阶段模块
    # 正常返回但已 append FATAL Issue 的场景，不能仅靠异常短路捕获）。
    document_ir = None
    gate3_results = None
    try:
        text, source_meta = _stage0_normalize(options, issues)
        if issues.has_fatal():
            _emit_report(options, issues, source_meta)
            return _determine_exit_code(issues)

        # dump_intermediate：写出清理前规范化文本（调试用）
        dump_path = None
        if flags.dump_intermediate:
            stem, _ext = os.path.splitext(options.input_path)
            dump_path = stem + "-cleaned.md"
        cleaned = _stage1_clean(text, issues, dump_path)
        if issues.has_fatal():
            _emit_report(options, issues, source_meta)
            return _determine_exit_code(issues)

        tokens = _stage2_parse(cleaned, issues)
        if issues.has_fatal():
            _emit_report(options, issues, source_meta)
            return _determine_exit_code(issues)

        document_ir = _stage3_assemble(tokens, options, flags, issues)
        if issues.has_fatal():
            _emit_report(options, issues, source_meta)
            return _determine_exit_code(issues)

        document_ir = _stage4_validate(document_ir, issues)
        if issues.has_fatal():
            _emit_report(options, issues, source_meta)
            return _determine_exit_code(issues)

        _stage5_render(document_ir, options, flags, issues)
        # 阶段5 之后无需再检查——紧接着就是阶段6，has_fatal() 的判定结果只影响
        # exit code（_determine_exit_code 已覆盖），不影响是否调用 _emit_report
        # （阶段6 始终尝试产出，见模块 docstring）。

        # 阶段5.5：门3 输出校验（在报告生成前运行，结果传入报告）
        gate3_results = None
        try:
            gate3_module = importlib.import_module(".gate3", package=__package__)
            gate3_results = gate3_module.run_gate3(
                options.output_path, document_ir, issues, flags
            )
        except ImportError:
            pass  # gate3.py 未就绪时静默跳过，不影响报告生成
    except _StageNotReady as exc:
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-SYS-01",
                stage="pipeline",
                message=f"转换器内部错误：阶段模块未就绪（{exc.stage}）",
                suggestion="该阶段对应的实现任务尚未完成，请联系维护者",
            )
        )

    _emit_report(options, issues, source_meta, gate3_results=gate3_results, document_ir=document_ir)
    return _determine_exit_code(issues)
