"""
配置加载模块 — 三层优先级合并与只读单例 Config。

优先级: CLI 参数 > YAML 配置文件 > 默认配置（default_config.yaml）

用法:
    from .config import Config, load_config

    # 默认配置
    config = load_config()

    # 用户 YAML 覆盖
    config = load_config(config_path='report.yaml')

    # CLI 参数覆盖（最高优先级）
    config = load_config(cli_overrides={'metadata': {'title': '测试报告'}})

    # 颜色解析
    rgb = config.colors.as_tuple('primary')  # → (0, 0, 0)

设计约束 DR-01/DR-02/DR-03:
    - 字体/字号/颜色通过 Config 单例读取，禁止硬编码 "宋体"、Pt(11)、"F2F2F2"
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ── 尝试导入 PyYAML，不可用时回退到 JSON ──
try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ═══════════════════════════════════════════════════════════
# 内嵌配置类（frozen=True 保证不可变）
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FontPair:
    """中英文字体对。"""
    cjk: str = "宋体"
    latin: str = "Times New Roman"


@dataclass(frozen=True)
class FontsConfig:
    """字体方案（V3.0 §3.1）。"""
    body: FontPair = field(default_factory=lambda: FontPair(cjk="宋体", latin="Times New Roman"))
    heading: FontPair = field(default_factory=lambda: FontPair(cjk="微软雅黑", latin="Times New Roman"))
    mono: FontPair = field(default_factory=lambda: FontPair(cjk="宋体", latin="Consolas"))
    table_header: FontPair = field(default_factory=lambda: FontPair(cjk="微软雅黑", latin="Times New Roman"))
    table_body: FontPair = field(default_factory=lambda: FontPair(cjk="宋体", latin="Times New Roman"))
    special: FontPair = field(default_factory=lambda: FontPair(cjk="楷体", latin="Times New Roman"))


@dataclass(frozen=True)
class SizesConfig:
    """字号配置（pt），V3.0 §3.2, §3.3。"""
    cover_title: float = 28.0
    cover_subtitle: float = 14.0
    cover_type: float = 16.0
    cover_info: float = 11.0
    h1: float = 24.0
    h2: float = 16.0
    h3: float = 14.0
    h4: float = 12.0
    h5: float = 12.0
    body: float = 11.0
    table_header: float = 10.0
    table_body: float = 10.5
    quote: float = 10.5
    caption: float = 9.0
    footnote: float = 9.0
    header_footer: float = 9.0


@dataclass(frozen=True)
class PageConfig:
    """页面布局（V3.0 §2），单位 cm。"""
    width: float = 21.0
    height: float = 29.7
    margin_top: float = 2.54
    margin_bottom: float = 2.54
    margin_left: float = 3.17
    margin_right: float = 2.54
    header_distance: float = 1.27
    footer_distance: float = 1.27


@dataclass(frozen=True)
class LineSpacingConfig:
    """行距配置。"""
    body: float = 1.5
    heading: float = 1.0
    caption: float = 1.0
    footnote: float = 1.0
    quote: float = 1.5


@dataclass(frozen=True)
class IndentConfig:
    """缩进配置（cm）。"""
    body_first_line: float = 0.74
    quote_left: float = 1.5
    list_left: float = 1.5
    list_hang: float = 0.75


@dataclass(frozen=True)
class SpacingConfig:
    """段间距配置（pt），V3.0 §3.2。"""
    h1_before: float = 0.0
    h1_after: float = 18.0
    h2_before: float = 24.0
    h2_after: float = 12.0
    h3_before: float = 18.0
    h3_after: float = 8.0
    h4_before: float = 12.0
    h4_after: float = 6.0
    h5_before: float = 8.0
    h5_after: float = 4.0
    body_before: float = 0.0
    body_after: float = 0.0
    title_before: float = 24.0
    title_after: float = 18.0


@dataclass(frozen=True)
class ColorsConfig:
    """配色方案（V3.0 §11），值均为 6 位 HEX 字符串（不含 #）。"""
    primary: str = "000000"
    secondary: str = "555555"
    bg_light: str = "F2F2F2"
    accent: str = "333333"
    separator: str = "BBBBBB"
    link: str = "0563C1"

    def as_tuple(self, name: str) -> Tuple[int, int, int]:
        """将指定颜色名称对应的 HEX 字符串转为 RGB 元组。

        Args:
            name: 颜色字段名，如 "primary", "link"。

        Returns:
            (R, G, B) 三元组，每通道 0-255。

        Raises:
            AttributeError: 名称不存在。
            ValueError: HEX 值格式非法。
        """
        hex_str = getattr(self, name)
        return parse_color(hex_str)

    def __getitem__(self, name: str) -> str:
        """支持 config.colors['primary'] 字典式访问。"""
        return getattr(self, name)


@dataclass(frozen=True)
class HeaderFooterConfig:
    """页眉页脚配置。"""
    header_text: str = "{title}"
    header_show_on_cover: bool = False
    header_show_on_toc: bool = False
    page_number_summary: str = "roman"
    page_number_body: str = "arabic"


@dataclass(frozen=True)
class TableConfig:
    """表格配置（V3.0 §5.1）。"""
    width_pct: float = 90.0
    border_outer: float = 1.5
    border_header_sep: float = 1.0
    border_inner: float = 0.5
    alt_row_color: str = "F2F2F2"
    repeat_header: bool = True

    def alt_row_color_tuple(self) -> Tuple[int, int, int]:
        """交替行底色 RGB 元组。"""
        return parse_color(self.alt_row_color)


@dataclass(frozen=True)
class CoverConfig:
    """封面配置（V3.0 §7）。"""
    top_spacing_cm: float = 6.0
    show_separator: bool = True
    separator_char: str = "━"  # "━"
    separator_repeat: int = 40


@dataclass(frozen=True)
class TocConfig:
    """目录配置。"""
    levels: int = 3
    show_page_numbers: bool = True
    hyperlinks: bool = True


@dataclass(frozen=True)
class MarkdownConfig:
    """Markdown 约定识别配置。"""
    enable_front_matter: bool = True
    heading_auto_number: bool = True
    strip_manual_numbering: bool = True
    recognize_special_blocks: bool = True


@dataclass(frozen=True)
class MetadataConfig:
    """报告元数据。"""
    title: str = ""
    subtitle: str = ""
    subtype: str = "深度研究报告"
    org: str = ""
    version: str = "V1.0"
    date: str = ""
    header_short: str = ""


# ═══════════════════════════════════════════════════════════
# 顶层配置类
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Config:
    """研究报告格式配置单例（只读）。

    所有字体/字号/颜色/布局配置均从此对象读取，代码中不硬编码具体值。
    满足设计约束 DR-01, DR-02, DR-03。
    """
    metadata: MetadataConfig = field(default_factory=MetadataConfig)
    fonts: FontsConfig = field(default_factory=FontsConfig)
    sizes: SizesConfig = field(default_factory=SizesConfig)
    page: PageConfig = field(default_factory=PageConfig)
    line_spacing: LineSpacingConfig = field(default_factory=LineSpacingConfig)
    indent: IndentConfig = field(default_factory=IndentConfig)
    spacing: SpacingConfig = field(default_factory=SpacingConfig)
    colors: ColorsConfig = field(default_factory=ColorsConfig)
    header_footer: HeaderFooterConfig = field(default_factory=HeaderFooterConfig)
    table: TableConfig = field(default_factory=TableConfig)
    cover: CoverConfig = field(default_factory=CoverConfig)
    toc: TocConfig = field(default_factory=TocConfig)
    markdown: MarkdownConfig = field(default_factory=MarkdownConfig)


# ═══════════════════════════════════════════════════════════
# 嵌套字典 → 嵌套 dataclass 构造
# ═══════════════════════════════════════════════════════════

# 每个顶层键映射到对应的 dataclass 类型，用于从 dict 构造
_CONFIG_CLASS_MAP: Dict[str, type] = {
    "metadata": MetadataConfig,
    "fonts": FontsConfig,
    "sizes": SizesConfig,
    "page": PageConfig,
    "line_spacing": LineSpacingConfig,
    "indent": IndentConfig,
    "spacing": SpacingConfig,
    "colors": ColorsConfig,
    "header_footer": HeaderFooterConfig,
    "table": TableConfig,
    "cover": CoverConfig,
    "toc": TocConfig,
    "markdown": MarkdownConfig,
}

# fonts 下的子结构映射
_FONT_KEY_MAP: Dict[str, type] = {
    "body": FontPair,
    "heading": FontPair,
    "mono": FontPair,
    "table_header": FontPair,
    "table_body": FontPair,
    "special": FontPair,
}


def _build_fonts_config(data: Dict[str, Any]) -> FontsConfig:
    """从 dict 构造 FontsConfig，处理每个字体对的 cjk/latin。"""
    kwargs = {}
    for key, cls in _FONT_KEY_MAP.items():
        if key in data and isinstance(data[key], dict):
            kwargs[key] = cls(**data[key])
        else:
            kwargs[key] = cls()
    return FontsConfig(**kwargs)


def _config_from_dict(data: Dict[str, Any]) -> Config:
    """从扁平字典递归构建嵌套 Config 实例。"""
    kwargs = {}
    for key, cls in _CONFIG_CLASS_MAP.items():
        value = data.get(key, {})
        if not isinstance(value, dict):
            value = {}
        if key == "fonts":
            kwargs[key] = _build_fonts_config(value)
        else:
            kwargs[key] = cls(**value)
    return Config(**kwargs)


# ═══════════════════════════════════════════════════════════
# 深度合并与文件加载
# ═══════════════════════════════════════════════════════════


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归深度合并两个字典。

    override 中的值覆盖 base 中的同名键。两个字典中都是 dict 的键递归合并，
    否则 override 的值直接替换 base 的值。

    Args:
        base: 基础字典（会被浅拷贝，原对象不被修改）。
        override: 覆盖字典。

    Returns:
        合并后的新字典。
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    """加载 YAML（或 JSON）配置文件。

    Args:
        path: 配置文件路径。

    Returns:
        解析后的字典。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 文件解析失败。
    """
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        if _HAS_YAML:
            try:
                data = yaml.safe_load(f)
                if data is None:
                    return {}
                return data
            except yaml.YAMLError as e:
                raise ValueError(f"YAML 解析失败 ({path}): {e}") from e
        else:
            # PyYAML 不可用，回退到 JSON
            try:
                data = json.load(f)
                return data
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"JSON 解析失败 ({path}): {e}。"
                    f"请安装 PyYAML（pip install pyyaml）以支持 YAML 格式。"
                ) from e


def _get_default_config_path() -> Path:
    """返回包内默认配置文件路径。"""
    return Path(__file__).parent / "default_config.yaml"


def _load_defaults() -> Dict[str, Any]:
    """加载默认配置字典。

    优先从 default_config.yaml 加载（PyYAML 可用时），
    否则回退到硬编码的默认值。
    """
    default_path = _get_default_config_path()

    if _HAS_YAML and default_path.exists():
        return _load_yaml_file(default_path)

    # PyYAML 不可用或文件缺失时，使用硬编码默认值
    # （结构与 default_config.yaml 完全一致）
    if not _HAS_YAML:
        import warnings
        warnings.warn(
            "PyYAML 未安装，使用硬编码默认配置。"
            "建议安装 PyYAML: pip install pyyaml"
        )

    # 回退硬编码默认值 — 与 default_config.yaml 一字不差
    return {
        "metadata": {
            "title": "", "subtitle": "", "subtype": "深度研究报告",
            "org": "", "version": "V1.0", "date": "", "header_short": "",
        },
        "fonts": {
            "body": {"cjk": "宋体", "latin": "Times New Roman"},
            "heading": {"cjk": "微软雅黑", "latin": "Times New Roman"},
            "mono": {"cjk": "宋体", "latin": "Consolas"},
            "table_header": {"cjk": "微软雅黑", "latin": "Times New Roman"},
            "table_body": {"cjk": "宋体", "latin": "Times New Roman"},
            "special": {"cjk": "楷体", "latin": "Times New Roman"},
        },
        "sizes": {
            "cover_title": 28, "cover_subtitle": 14, "cover_type": 16,
            "cover_info": 11, "h1": 24, "h2": 16, "h3": 14, "h4": 12,
            "h5": 12, "body": 11, "table_header": 10, "table_body": 10.5,
            "quote": 10.5, "caption": 9, "footnote": 9, "header_footer": 9,
        },
        "page": {
            "width": 21.0, "height": 29.7,
            "margin_top": 2.54, "margin_bottom": 2.54,
            "margin_left": 3.17, "margin_right": 2.54,
            "header_distance": 1.27, "footer_distance": 1.27,
        },
        "line_spacing": {
            "body": 1.5, "heading": 1.0, "caption": 1.0,
            "footnote": 1.0, "quote": 1.5,
        },
        "indent": {
            "body_first_line": 0.74, "quote_left": 1.5,
            "list_left": 1.5, "list_hang": 0.75,
        },
        "spacing": {
            "h1_before": 0, "h1_after": 18, "h2_before": 24, "h2_after": 12,
            "h3_before": 18, "h3_after": 8, "h4_before": 12, "h4_after": 6,
            "h5_before": 8, "h5_after": 4, "body_before": 0, "body_after": 0,
            "title_before": 24, "title_after": 18,
        },
        "colors": {
            "primary": "000000", "secondary": "555555", "bg_light": "F2F2F2",
            "accent": "333333", "separator": "BBBBBB", "link": "0563C1",
        },
        "header_footer": {
            "header_text": "{title}", "header_show_on_cover": False,
            "header_show_on_toc": False, "page_number_summary": "roman",
            "page_number_body": "arabic",
        },
        "table": {
            "width_pct": 90, "border_outer": 1.5, "border_header_sep": 1.0,
            "border_inner": 0.5, "alt_row_color": "F2F2F2", "repeat_header": True,
        },
        "cover": {
            "top_spacing_cm": 6.0, "show_separator": True,
            "separator_char": "━", "separator_repeat": 40,
        },
        "toc": {
            "levels": 3, "show_page_numbers": True, "hyperlinks": True,
        },
        "markdown": {
            "enable_front_matter": True, "heading_auto_number": True,
            "strip_manual_numbering": True, "recognize_special_blocks": True,
        },
    }


# ═══════════════════════════════════════════════════════════
# 公共 API
# ═══════════════════════════════════════════════════════════


def parse_color(hex_str: str) -> Tuple[int, int, int]:
    """将 6 位 HEX 颜色字符串转为 RGB 元组。

    Args:
        hex_str: 6 位十六进制颜色字符串（如 "000000", "0563C1"），
                 不带头部 '#'。

    Returns:
        (R, G, B) 元组，每通道 0-255。

    Raises:
        ValueError: hex_str 不是 6 位十六进制字符串。

    Examples:
        >>> parse_color("000000")
        (0, 0, 0)
        >>> parse_color("0563C1")
        (5, 99, 193)
        >>> parse_color("F2F2F2")
        (242, 242, 242)
    """
    hex_str = hex_str.strip().lstrip('#')
    if len(hex_str) != 6:
        raise ValueError(
            f"颜色值必须是 6 位 HEX 字符串，收到: '{hex_str}'"
        )
    try:
        return (
            int(hex_str[0:2], 16),
            int(hex_str[2:4], 16),
            int(hex_str[4:6], 16),
        )
    except ValueError as e:
        raise ValueError(
            f"无效的 HEX 颜色值: '{hex_str}'"
        ) from e


def load_config(
    config_path: Optional[str] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> Config:
    """加载配置，三层优先级合并。

    1. 加载默认配置（default_config.yaml 或硬编码回退）
    2. 合并用户 YAML/JSON 配置文件（config_path）
    3. 应用 CLI 参数覆盖（cli_overrides）—— 最高优先级

    Args:
        config_path: 用户配置文件路径（.yaml / .yml / .json）。
                     为 None 时仅使用默认配置。
        cli_overrides: CLI 参数覆盖字典，顶层键与 YAML 结构一致。
                       例如 {'metadata': {'title': '测试'}}

    Returns:
        冻结的 Config 实例（不可修改）。

    Raises:
        FileNotFoundError: config_path 指定的文件不存在。
        ValueError: 配置文件解析失败。

    Examples:
        >>> config = load_config()
        >>> config.fonts.body.cjk
        '宋体'
        >>> config.sizes.body
        11.0

        >>> config = load_config(cli_overrides={'metadata': {'title': 'Test'}})
        >>> config.metadata.title
        'Test'
    """
    # 第一层：默认配置
    config_dict = _load_defaults()

    # 第二层：用户配置文件
    if config_path:
        user_dict = _load_yaml_file(Path(config_path))
        config_dict = deep_merge(config_dict, user_dict)

    # 第三层：CLI 参数覆盖
    if cli_overrides:
        config_dict = deep_merge(config_dict, cli_overrides)

    return _config_from_dict(config_dict)
