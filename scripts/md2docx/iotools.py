"""二进制安全 I/O 唯一进出口 + 控制台输出安全包装 + 封面元数据加载。

G-01 硬约束：全项目 `open(` 只允许出现在本文件。任何其他模块需要读写文件，
一律经由本模块提供的函数。

本模块不做任何内容解析（不识别 Markdown、不解析 PNG 结构），仅负责字节层面的
安全读写与控制台编码兜底——这是 01-architecture.md §2.5 二进制安全边界①②的
唯一实现位置。

R17 裁决：PNG IHDR 头（前 33 字节）解析所需的读取动作也必须经本模块的
`read_bytes(path, limit=...)` 完成；IHDR 字节结构的*解析*仍在 assemble/figures.py
（未来任务），本文件只提供"读前 N 字节"的通用能力，不含任何 PNG 格式知识。

新增 cover：`load_cover_metadata()` 读取封面 MD 的 YAML frontmatter，返回 dict。
"""
from __future__ import annotations

import sys
from typing import IO

# ---------------------------------------------------------------------------
# 二进制读写唯一进出口
# ---------------------------------------------------------------------------


def read_bytes(path: str, limit: int | None = None) -> bytes:
    """读取文件的二进制内容。

    唯一读入口：md 正文读取（阶段0 二进制安全边界①）、图片字节流读取（边界③）、
    PNG IHDR 头探测（R17，limit=33）均经此函数。

    Args:
        path: 文件路径。
        limit: 若给定，仅读取前 limit 字节（用于 IHDR 头等场景，避免整文件载入
            内存）；为 None 时读取全部内容。
    """
    with open(path, "rb") as f:
        if limit is None:
            return f.read()
        return f.read(limit)


def write_bytes(path: str, data: bytes) -> None:
    """写出二进制内容（唯一写入口之一）。"""
    with open(path, "wb") as f:
        f.write(data)


def write_text(path: str, text: str) -> None:
    """写出文本内容：显式 `str.encode('utf-8')` 后走 `wb` 写入。

    使用 `wb` 而非文本模式 `w`，是为了保证内部换行符 `\\n` 不被平台相关的
    universal-newline 转译动作篡改（历史问题1"标题截断"的同源风险：文本模式
    I/O 在 Windows 上会做 \\n → \\r\\n 隐式转换，二进制写入彻底规避）。
    """
    write_bytes(path, text.encode("utf-8"))


# ---------------------------------------------------------------------------
# 控制台输出编码安全策略（04-interface-spec.md §1.4 精确规格）
# ---------------------------------------------------------------------------

_console_reconfigured = False


def _try_reconfigure_console() -> None:
    """模块加载或首次调用 console_out 时尝试一次性 reconfigure。

    失败（极旧终端无 reconfigure，或流已被替换为不支持该方法的对象）时静默
    忽略——后续 console_out 的逐条兜底仍然生效，绝不让 reconfigure 失败本身
    抛出异常中断已完成的转换。
    """
    global _console_reconfigured
    if _console_reconfigured:
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    _console_reconfigured = True


# 模块加载时尝试一次（04 §1.4："模块加载或首次调用时尝试"）。
_try_reconfigure_console()


def console_out(msg: str, stream: IO[str] | None = None) -> None:
    """全项目唯一允许的控制台输出路径（经 cli.py 使用）。

    reconfigure 成功时 stream.write(msg) 直接安全；若前置 reconfigure 失败
    （理论场景，如极旧终端），逐条兜底降级为 stream.buffer.write +
    errors='replace'，绝不因控制台编码问题抛出异常中断程序。
    """
    target = stream if stream is not None else sys.stdout
    _try_reconfigure_console()
    try:
        target.write(msg)
    except UnicodeEncodeError:
        buffer = getattr(target, "buffer", None)
        encoding = getattr(target, "encoding", None) or "utf-8"
        if buffer is not None:
            buffer.write(msg.encode(encoding, errors="replace"))
        else:
            # 极端兜底：既无 reconfigure 也无 buffer 属性的流，退化为忽略
            # 无法编码的字符，仍然不抛异常。
            target.write(msg.encode(encoding, errors="replace").decode(encoding))


# ---------------------------------------------------------------------------
# 封面元数据加载（改进 14：封面独立 MD 文档）
# ---------------------------------------------------------------------------


def load_cover_metadata(cover_path: str) -> dict:
    """读取封面 MD 文件的 YAML frontmatter，返回 dict 或空 dict。

    封面文件格式为纯 YAML frontmatter（``---`` 包裹）：
        ---
        title: 报告题名
        title_en: English Title
        report_type: 立项建议书
        org: 申报单位
        date: 2026年7月
        version: V1.0
        header_short: 页眉简称
        ---

    Args:
        cover_path: 封面 MD 文件的绝对路径。

    Returns:
        YAML frontmatter 解析结果 dict；文件不存在/解析失败/无有效 YAML 时返回空 dict。
        绝不抛异常——封面是可选增强，不应因其缺失而阻断转换流程。
    """
    import os

    if not cover_path or not os.path.isfile(cover_path):
        return {}

    try:
        raw = read_bytes(cover_path).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    # 提取 YAML frontmatter（--- 定界符之间）
    parts = raw.split("---")
    if len(parts) < 2:
        return {}

    yaml_text = parts[1].strip()
    if not yaml_text:
        return {}

    try:
        import yaml  # noqa: PLC0415  延迟 import（与 config.py 一致）
    except ImportError:
        return {}

    try:
        data = yaml.safe_load(yaml_text)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001  YAML 解析异常种类繁多，统一回退空 dict
        return {}
