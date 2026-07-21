"""文档头元数据装配：MetaLine → MetadataIR（C-05a）。

将文本阶段产出的 MetaLine 列表与 CLI/YAML 兜底值合并，按优先级链
（md 元数据块 > CLI 参数 > YAML 默认值）产出 MetadataIR。

设计依据：02-algorithms.md §D.3、04-interface-spec.md §1.2。
"""
from __future__ import annotations

import re

from ..config import RE_VERSION_SPLIT
from ..ir import MetadataIR
from ..issues import Issue, IssueCollector, Level
from ..textstage.tokens import MetaLine

# 编译版本拆分正则（来自 config.py 的单一事实来源）
_VERSION_RE = re.compile(RE_VERSION_SPLIT)


def _has_cjk(ch: str) -> bool:
    """判断字符是否属于 CJK 宽字符区（用于半角宽度估算）。"""
    return (
        "一" <= ch <= "鿿"
        or "　" <= ch <= "〿"
        or "＀" <= ch <= "￯"
    )


def _truncate_cjk(s: str, max_width: int) -> str:
    """按半角显示宽度截断字符串：CJK 字符计 2 宽，其余计 1。

    Args:
        s: 待截断字符串。
        max_width: 最大半角宽度（含）。

    Returns:
        截断后的字符串，保证其半角宽度 ≤ max_width。
    """
    result: list[str] = []
    w = 0
    for ch in s:
        cw = 2 if _has_cjk(ch) else 1
        if w + cw > max_width:
            break
        result.append(ch)
        w += cw
    return "".join(result)


def extract_metadata(
    meta_lines: list[MetaLine],
    h1_text: str | None,
    cli_overrides: dict,
    yaml_defaults: dict | None,
    issues: IssueCollector,
) -> MetadataIR:
    """从 MetaLine 列表和外部来源装配 MetadataIR。

    Args:
        meta_lines: Token 流中提取的 MetaLine 列表。
        h1_text: 第一个 HeadingToken(level=1) 的 raw_text；无 H1 时为 None。
        cli_overrides: RunOptions.metadata_cli_overrides() 的返回值。
        yaml_defaults: YAML metadata_defaults 块（已校验）；无配置时为 None 或 {}。
        issues: IssueCollector 实例。

    Returns:
        全部字段已填充的 MetadataIR 实例（缺失字段为 None）。

    优先级链（04 §1.2）：md 元数据块 > CLI 参数 > YAML 默认值。
    """
    # ------------------------------------------------------------------
    # 第一步：从 MetaLine 列表提取 md 元数据字段
    # ------------------------------------------------------------------
    md_subtitle: str | None = None
    md_report_type: str | None = None
    md_organization: str | None = None
    md_version_raw: str | None = None

    for ml in meta_lines:
        key = ml.key.strip()
        value = ml.value.strip()
        if key == "副标题":
            md_subtitle = value
        elif key == "报告类型":
            md_report_type = value
        elif key == "编制机构":
            md_organization = value
        elif key == "版本":
            md_version_raw = value

    # ------------------------------------------------------------------
    # 第二步：版本字段二次拆分（正则 ^(V[\d.]+)\s*[|｜]\s*(.+)$）
    # ------------------------------------------------------------------
    md_version: str | None = None
    md_date: str | None = None
    if md_version_raw:
        m = _VERSION_RE.match(md_version_raw)
        if m:
            md_version = m.group(1)
            md_date = m.group(2)
        else:
            # 拆分失败：整体存入 version，date 为 None，记 I-CLN-05
            md_version = md_version_raw
            md_date = None
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="assemble",
                    message=(
                        f"版本字段格式不匹配「Vx.y | 日期」模式，"
                        f"整体存入 version：{md_version_raw!r}"
                    ),
                    suggestion="建议将版本字段改为「V1.0 | 2026年7月」格式",
                )
            )

    # ------------------------------------------------------------------
    # 第三步：优先级链合并（md > CLI > YAML）
    # ------------------------------------------------------------------
    yaml_defaults = yaml_defaults or {}

    # title：优先取 h1_text；无 H1 → FATAL（E-SYS-01）
    if h1_text:
        title = h1_text
    else:
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-SYS-01",
                stage="assemble",
                message="文档缺少 H1 标题（无法确定报告主标题），中止 IR 构建",
                suggestion="请在 md 文件开头添加一级标题（# 标题）",
            )
        )
        title = ""

    # subtitle：md 副标题 > CLI --subtitle（YAML 不含此字段）
    subtitle = md_subtitle or cli_overrides.get("subtitle") or None

    # report_type：md 报告类型 > CLI --report-type > YAML report_type_default
    report_type = (
        md_report_type
        or cli_overrides.get("report_type")
        or yaml_defaults.get("report_type_default")
        or None
    )

    # organization：md 编制机构 > CLI --org > YAML organization
    organization = (
        md_organization
        or cli_overrides.get("organization")
        or yaml_defaults.get("organization")
        or None
    )

    # version：md 拆分结果 > CLI --doc-version
    version = md_version or cli_overrides.get("version") or None

    # date：md 拆分结果 > CLI --date
    date = md_date or cli_overrides.get("date") or None

    # title_short（页眉简称）：CLI --header-short > YAML header_short > 自动截断
    header_short_cli = cli_overrides.get("header_short")
    header_short_yaml = yaml_defaults.get("header_short")
    if header_short_cli:
        title_short = header_short_cli
    elif header_short_yaml:
        title_short = header_short_yaml
    elif title:
        # 自动截断：取前 N 个半角宽度 ≤ 12
        title_short = _truncate_cjk(title, 12)
    else:
        title_short = None

    return MetadataIR(
        title=title,
        subtitle=subtitle,
        report_type=report_type,
        organization=organization,
        version_raw=md_version_raw,
        version=version,
        date=date,
        title_short=title_short,
    )


# ---------------------------------------------------------------------------
# 自检（验收标准）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    collector = IssueCollector()

    # 测试1：正常流程（有 H1 + 完整元数据）
    meta_lines = [
        MetaLine(key="副标题", value="中国城市轨道交通发展报告", source_line=2),
        MetaLine(key="报告类型", value="年度研究报告", source_line=3),
        MetaLine(key="编制机构", value="交通运输部", source_line=4),
        MetaLine(key="版本", value="V1.0 | 2026年7月", source_line=5),
    ]
    result = extract_metadata(
        meta_lines=meta_lines,
        h1_text="中国城市轨道交通发展报告（2025）",
        cli_overrides={},
        yaml_defaults={},
        issues=collector,
    )
    assert result.title == "中国城市轨道交通发展报告（2025）", f"title mismatch: {result.title}"
    assert result.subtitle == "中国城市轨道交通发展报告", f"subtitle mismatch: {result.subtitle}"
    assert result.report_type == "年度研究报告", f"report_type mismatch: {result.report_type}"
    assert result.organization == "交通运输部", f"organization mismatch: {result.organization}"
    assert result.version_raw == "V1.0 | 2026年7月", f"version_raw mismatch: {result.version_raw}"
    assert result.version == "V1.0", f"version mismatch: {result.version}"
    assert result.date == "2026年7月", f"date mismatch: {result.date}"
    # title_short 自动截断："中国城市轨道交通发展报告（2025）" CJK 计 2×13+2=28 > 12
    # → 截断为前 6 个 CJK 字符 = "中国城市轨道"
    assert result.title_short is not None, "title_short should not be None"
    assert len(result.title_short) <= 6, f"title_short too long: {result.title_short!r}"
    print("测试1 通过：正常流程")

    # 测试2：无 H1 → FATAL
    collector2 = IssueCollector()
    result2 = extract_metadata(
        meta_lines=[],
        h1_text=None,
        cli_overrides={},
        yaml_defaults={},
        issues=collector2,
    )
    assert result2.title == "", f"title should be empty on FATAL, got: {result2.title!r}"
    assert collector2.has_fatal(), "should have FATAL when H1 missing"
    print("测试2 通过：无 H1 → FATAL")

    # 测试3：CLI 兜底生效
    collector3 = IssueCollector()
    result3 = extract_metadata(
        meta_lines=[],
        h1_text="报告标题",
        cli_overrides={"subtitle": "CLI副标题", "report_type": "CLI报告类型"},
        yaml_defaults={},
        issues=collector3,
    )
    assert result3.subtitle == "CLI副标题", f"CLI subtitle override: {result3.subtitle}"
    assert result3.report_type == "CLI报告类型", f"CLI report_type override: {result3.report_type}"
    print("测试3 通过：CLI 兜底")

    # 测试4：YAML 兜底生效
    collector4 = IssueCollector()
    result4 = extract_metadata(
        meta_lines=[],
        h1_text="报告标题",
        cli_overrides={},
        yaml_defaults={"organization": "YAML机构", "report_type_default": "YAML类型", "header_short": "YAML简称"},
        issues=collector4,
    )
    assert result4.organization == "YAML机构", f"YAML org: {result4.organization}"
    assert result4.report_type == "YAML类型", f"YAML type: {result4.report_type}"
    assert result4.title_short == "YAML简称", f"YAML header_short: {result4.title_short}"
    print("测试4 通过：YAML 兜底")

    # 测试5：版本拆分失败（I-CLN-05）
    collector5 = IssueCollector()
    result5 = extract_metadata(
        meta_lines=[MetaLine(key="版本", value="2026年7月第一版", source_line=5)],
        h1_text="测试标题",
        cli_overrides={},
        yaml_defaults={},
        issues=collector5,
    )
    assert result5.version_raw == "2026年7月第一版"
    assert result5.version == "2026年7月第一版", f"version should be raw: {result5.version}"
    assert result5.date is None, f"date should be None on split failure: {result5.date}"
    assert any(i.code == "I-CLN-05" for i in collector5), "should have I-CLN-05"
    print("测试5 通过：版本拆分失败 → I-CLN-05")

    # 测试6：CLI header_short 优先于 YAML header_short
    collector6 = IssueCollector()
    result6 = extract_metadata(
        meta_lines=[],
        h1_text="报告标题",
        cli_overrides={"header_short": "CLI简称"},
        yaml_defaults={"header_short": "YAML简称"},
        issues=collector6,
    )
    assert result6.title_short == "CLI简称", f"CLI header_short should win: {result6.title_short}"
    print("测试6 通过：CLI header_short > YAML header_short")

    # 测试7：优先级链 md > CLI > YAML
    collector7 = IssueCollector()
    result7 = extract_metadata(
        meta_lines=[
            MetaLine(key="副标题", value="md副标题", source_line=2),
            MetaLine(key="报告类型", value="md报告类型", source_line=3),
            MetaLine(key="编制机构", value="md机构", source_line=4),
        ],
        h1_text="md标题",
        cli_overrides={"subtitle": "CLI副标题", "report_type": "CLI类型", "organization": "CLI机构"},
        yaml_defaults={"organization": "YAML机构", "report_type_default": "YAML类型"},
        issues=collector7,
    )
    assert result7.subtitle == "md副标题", f"md subtitle wins: {result7.subtitle}"
    assert result7.report_type == "md报告类型", f"md report_type wins: {result7.report_type}"
    assert result7.organization == "md机构", f"md organization wins: {result7.organization}"
    print("测试7 通过：md > CLI > YAML 优先级链")

    print("\n全部 metadata 自检通过 ✓")
