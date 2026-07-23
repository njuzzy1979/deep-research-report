"""命令行参数解析、路径归一化 → RunOptions dataclass（C-01，04-interface-spec.md §1）。

本模块只做参数解析与路径归一化，不执行任何转换逻辑、不读文件内容（01-architecture.md
§3.2 cli.py 职责卡"不做什么"）。

行为开关类选项（strict/allow_missing_figures/appendix_page_break/caption_field_mode/
dump_intermediate/figures_dir/figure_max_width_cm/generate_figures_table_toc）在
argparse 层一律使用 `default=None`，而非 04 §1 参数表字面写出的具体默认值——这是
本实现的一处显式解释性决策：`None` 在 RunOptions 中表示"用户未显式传入"，供
`config.resolve_behavior_flags()`（见 config.py）实现"CLI 显式值 > YAML > 内置
默认"的三态优先级链；04 §1 表格中的"默认值"列描述的是"用户全程不指定任何来源时
的最终生效值"，与 `BehaviorFlags` dataclass 的字段默认值一致，语义并不冲突，只是
在 argparse 层需要用 None 而非该值本身来保留"是否显式传入"这一信息。
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from . import __version__
from .config import FIGURE_MAX_WIDTH_CM_RANGE


@dataclass
class RunOptions:
    """cli.py 的唯一产出：全部选项 + 归一化后的绝对路径。"""

    input_path: str
    output_path: str
    report_path: str

    figures_dir: str | None
    config_path: str | None

    dump_intermediate: bool | None
    strict: bool | None
    allow_missing_figures: bool | None
    caption_field_mode: str | None
    appendix_page_break: bool | None
    figure_max_width_cm: float | None
    generate_figures_table_toc: str | None

    title: str | None
    subtitle: str | None
    report_type: str | None
    organization: str | None
    doc_version: str | None
    date: str | None
    header_short: str | None
    build_date: str | None
    cover_path: str | None

    verbose: bool
    quiet: bool

    def behavior_cli_overrides(self) -> dict:
        """喂给 config.resolve_behavior_flags() 的 cli_values 参数。"""
        return {
            "strict": self.strict,
            "allow_missing_figures": self.allow_missing_figures,
            "appendix_page_break": self.appendix_page_break,
            "caption_field_mode": self.caption_field_mode,
            "dump_intermediate": self.dump_intermediate,
            "figures_dir": self.figures_dir,
            "figure_max_width_cm": self.figure_max_width_cm,
            "generate_figures_table_toc": self.generate_figures_table_toc,
        }

    def metadata_cli_overrides(self) -> dict:
        """供未来 assemble/metadata.py 消费的元数据兜底值（04 §1.2 优先级链）。"""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "report_type": self.report_type,
            "organization": self.organization,
            "version": self.doc_version,
            "date": self.date,
            "header_short": self.header_short,
        }


def _figure_max_width_type(value: str) -> float:
    """--figure-max-width-cm 的 argparse type 校验：越界即参数错误（argparse 层拦截）。"""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--figure-max-width-cm 必须是数字，收到：{value!r}") from exc
    lo, hi = FIGURE_MAX_WIDTH_CM_RANGE
    if not (lo <= parsed <= hi):
        raise argparse.ArgumentTypeError(
            f"--figure-max-width-cm 取值 {parsed} 超出允许范围 [{lo}, {hi}]"
        )
    return parsed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md2docx",
        description="将符合 deep-research-report skill 约定的 Markdown 研究报告转换为"
        "符合《研究报告格式规范》的 Word (.docx) 文档，并产出转换报告。",
    )
    parser.add_argument("--version", action="version", version=f"md2docx {__version__}")

    parser.add_argument("input", help="输入 Markdown 文件路径")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="输出 docx 路径；缺省 = input 同目录同文件名（扩展名替换为 .docx）",
    )

    parser.add_argument(
        "--figures-dir", default=None,
        help="图片搜索追加候选目录（不替换主解析路径）",
    )
    parser.add_argument("--config", dest="config_path", default=None, help="显式指定 YAML 配置文件路径")
    parser.add_argument(
        "--report-path", default=None,
        help="转换报告输出路径；缺省 = <output 去扩展名>.conversion-report.md",
    )
    parser.add_argument(
        "--dump-intermediate", action="store_true", default=None,
        help="额外写出清理后的中间 Markdown（调试用）",
    )
    parser.add_argument(
        "--strict", action="store_true", default=None,
        help="ERROR 级问题直接升级为 FATAL 中止",
    )
    parser.add_argument(
        "--allow-missing-figures", action="store_true", default=None,
        help="图片文件缺失时降级为 WARNING + 文字占位段，而非默认中止",
    )
    parser.add_argument(
        "--caption-field-mode", choices=("text", "field"), default=None,
        help="题注实现档位：text=Tier1（默认，推荐）；field=Tier2",
    )
    parser.add_argument(
        "--appendix-page-break", dest="appendix_page_break",
        action="store_true", default=None,
        help="每个附录 H2 独立起页（默认行为）",
    )
    parser.add_argument(
        "--no-appendix-page-break", dest="appendix_page_break",
        action="store_false",
        help="关闭附录 H2 独立起页",
    )
    parser.add_argument(
        "--figure-max-width-cm", type=_figure_max_width_type, default=None,
        help="图片嵌入宽度上限（cm），校验范围 [8.0, 16.0]",
    )
    parser.add_argument(
        "--generate-figures-table-toc", choices=("auto", "always", "never"), default=None,
        help="图表目录生成策略",
    )

    # 元数据补充组（04 §1.1；仅在 md 头部元数据块对应字段缺失时生效，见 §1.2）
    parser.add_argument("--title", default=None, help="标题兜底值（md 无 H1 时不适用，见 FATAL 场景）")
    parser.add_argument("--subtitle", default=None, help="副标题兜底值")
    parser.add_argument("--report-type", default=None, help="报告类型兜底值")
    parser.add_argument("--org", dest="organization", default=None, help="机构名兜底值")
    parser.add_argument("--doc-version", dest="doc_version", default=None, help="版本号兜底值（R16：非 --version）")
    parser.add_argument("--date", default=None, help="日期兜底值")
    parser.add_argument("--header-short", default=None, help="页眉简称兜底值")
    parser.add_argument(
        "--build-date", default=None,
        help="core_properties 三时间字段所用日期（R16）；未传时取 metadata.date 归一化，"
        "两者皆无则固定回退 2000-01-01，绝不取系统时间",
    )
    parser.add_argument(
        "--cover", dest="cover_path", type=str, default=None,
        help="封面 YAML 文件路径（优先级高于正文 frontmatter）；"
        "封面字段 = cover.md YAML > 正文 md YAML > CLI 参数 > 默认值",
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="store_true", default=False, help="控制台输出提升到 DEBUG 级")
    verbosity.add_argument("-q", "--quiet", action="store_true", default=False, help="控制台仅在非 0 退出码时输出")

    return parser


def _default_output_path(input_path: str) -> str:
    stem, _ext = os.path.splitext(input_path)
    return stem + ".docx"


def _default_report_path(output_path: str) -> str:
    stem, _ext = os.path.splitext(output_path)
    return stem + ".conversion-report.md"


def parse_args(argv: list[str] | None = None) -> RunOptions:
    """解析 argv 并产出 RunOptions；互斥/越界/未知参数等由 argparse 自身报错（exit 2）。"""
    parser = build_arg_parser()
    ns = parser.parse_args(argv)

    input_path = os.path.abspath(ns.input)
    output_path = os.path.abspath(ns.output) if ns.output else _default_output_path(input_path)
    report_path = (
        os.path.abspath(ns.report_path) if ns.report_path else _default_report_path(output_path)
    )
    figures_dir = os.path.abspath(ns.figures_dir) if ns.figures_dir else None
    config_path = os.path.abspath(ns.config_path) if ns.config_path else None

    return RunOptions(
        input_path=input_path,
        output_path=output_path,
        report_path=report_path,
        figures_dir=figures_dir,
        config_path=config_path,
        dump_intermediate=ns.dump_intermediate,
        strict=ns.strict,
        allow_missing_figures=ns.allow_missing_figures,
        caption_field_mode=ns.caption_field_mode,
        appendix_page_break=ns.appendix_page_break,
        figure_max_width_cm=ns.figure_max_width_cm,
        generate_figures_table_toc=ns.generate_figures_table_toc,
        title=ns.title,
        subtitle=ns.subtitle,
        report_type=ns.report_type,
        organization=ns.organization,
        doc_version=ns.doc_version,
        date=ns.date,
        header_short=ns.header_short,
        build_date=ns.build_date,
        cover_path=os.path.abspath(ns.cover_path) if ns.cover_path else None,
        verbose=ns.verbose,
        quiet=ns.quiet,
    )
