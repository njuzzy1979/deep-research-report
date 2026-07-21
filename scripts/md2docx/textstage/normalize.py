"""阶段0：二进制读取与行尾规范化。

设计依据：01-architecture.md §2.1，02-algorithms.md §D.2 R-01/R-02。

本模块是 pipeline 接触文件系统的第一个阶段，负责：
  - 二进制安全读取（经 iotools.read_bytes）
  - UTF-8 BOM 剥离（R-01）
  - 行尾归一化：CRLF/CR → LF（R-02）
  - UTF-8 解码

解码失败时产出 FATAL Issue（E-ENC-01）并返回空文本，不抛异常——
让 pipeline 通过 IssueCollector.has_fatal() 统一判定终止条件。
"""
from __future__ import annotations

from ..iotools import read_bytes
from ..issues import Issue, IssueCollector, Level


def normalize(path: str, issues: IssueCollector) -> tuple[str, dict]:
    """阶段0：读取文件并做二进制规范化。

    Args:
        path: 输入 .md 文件绝对路径
        issues: IssueCollector，用于报告 FATAL/INFO

    Returns:
        (text, source_meta)：
        - text: str，UTF-8 解码后的完整文本，\\n 行尾
        - source_meta: dict，含 'has_bom' (bool), 'crlf_count' (int),
          'cr_count' (int), 'byte_size' (int)

    Raises:
        不抛异常；UTF-8 解码失败时向 issues append FATAL(E-ENC-01) 后
        返回 ("", source_meta)。
    """
    # 1. 二进制读取（唯一读入口，G-01）
    raw = read_bytes(path)

    # 2. 基础元数据
    source_meta: dict = {
        "has_bom": raw.startswith(b"\xef\xbb\xbf"),
        "byte_size": len(raw),
    }

    # 3. R-01：UTF-8 BOM 剥离
    if source_meta["has_bom"]:
        raw = raw[3:]

    # 4. 行尾统计（先 CRLF 后孤立 CR，保证 cr_count 是真正的孤立 CR 数）
    crlf_count = raw.count(b"\r\n")
    raw_after_crlf = raw.replace(b"\r\n", b"\n")
    cr_count = raw_after_crlf.count(b"\r")

    # 5. R-02：行尾归一化（CRLF → LF，孤立 CR → LF）
    raw = raw_after_crlf.replace(b"\r", b"\n")

    source_meta["crlf_count"] = crlf_count
    source_meta["cr_count"] = cr_count

    # 6. UTF-8 解码
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        issues.append(
            Issue(
                level=Level.FATAL,
                code="E-ENC-01",
                stage="normalize",
                message="输入文件无法以 UTF-8 解码",
                source_line=None,
                element_ref=path,
                suggestion="请确认输入文件为合法 UTF-8 编码；"
                "可尝试用 Notepad++ 或 VS Code 另存为 UTF-8",
            )
        )
        return ("", source_meta)

    # 7. 记录规范化台账（I-CLN-05）
    if crlf_count > 0 or cr_count > 0:
        issues.append(
            Issue(
                level=Level.INFO,
                code="I-CLN-05",
                stage="normalize",
                message=(
                    f"行尾归一化：{crlf_count} CRLF + "
                    f"{cr_count} 孤立CR → LF"
                ),
                source_line=None,
                element_ref=path,
                suggestion=None,
            )
        )

    return (text, source_meta)
