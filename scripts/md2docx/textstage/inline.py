"""阶段2 行内 Markdown 语法解析。

设计依据：01-architecture.md §2.3，02-algorithms.md §D.1 上下文保护。

逐字符扫描，按优先级处理：
  1. 行内代码 `` `...` ``（最高优先级，内部不解析其他格式）
  2. 粗体 `` **...** ``
  3. 斜体 `` *...* ``（非双星号）
  4. 超链接 `` [text](url) ``
  5. 上标 `` ^...^ ``（防御性支持，样本 0 处）

核心规则：
  - 代码 span 内跳过所有其他规则
  - 未识别语法的文本 → InlineRun(text=原文, 格式全 False)
  - 星号不配对（如 `` **text `` 缺闭合）→ 原样保留为纯文本，不报错
  - 绝不丢字：整行所有字符完整映射到返回的 InlineRun 列表
"""
from __future__ import annotations

from ..ir import InlineRun
from ..issues import IssueCollector


def parse_inline(
    text: str, source_line: int, issues: IssueCollector
) -> list[InlineRun]:
    """解析单行文本中的行内 Markdown 语法。

    Args:
        text: 单行文本（已经归一化为 \\n 行尾的 str）
        source_line: 原始 md 行号（供 Issue 定位）
        issues: IssueCollector（保留参数供未来扩展，当前行内解析不产 Issue）

    Returns:
        list[InlineRun]，每个 InlineRun 的 text 为纯文本（语法标记已剥离），
        bold/italic/code/superscript/link_url 为对应的格式标志。
    """
    return _scan(text, source_line)


def _scan(text: str, source_line: int) -> list[InlineRun]:
    """逐字符扫描主循环。

    将代码 span（`` ` ``）作为最高优先级先行提取，非代码区域再递归解析
    粗体/斜体/链接/上标。这样保证了代码 span 内部的 `` ** `` 等不被误解析。
    """
    runs: list[InlineRun] = []
    i = 0
    plain_buf: list[str] = []

    def _flush_plain() -> None:
        """将 plain_buf 积累的普通文本刷出为一个 InlineRun。"""
        if plain_buf:
            runs.append(InlineRun(text="".join(plain_buf)))
            plain_buf.clear()

    while i < len(text):
        # ================================================================
        # 优先级1：行内代码 `...`
        # ================================================================
        if text[i] == "`":
            _flush_plain()
            end = text.find("`", i + 1)
            if end != -1:
                # 成对反引号 → 代码 run
                runs.append(InlineRun(text=text[i + 1 : end], code=True))
                i = end + 1
            else:
                # 孤立反引号 → 原样保留为普通文本
                plain_buf.append("`")
                i += 1
            continue

        # ================================================================
        # 优先级2：粗体 **...**
        # ================================================================
        if text[i : i + 2] == "**":
            _flush_plain()
            end = text.find("**", i + 2)
            if end != -1:
                # 递归解析粗体内部文本
                inner_text = text[i + 2 : end]
                inner_runs = _scan(inner_text, source_line)
                for r in inner_runs:
                    if not r.code:
                        r.bold = True
                runs.extend(inner_runs)
                i = end + 2
                continue
            else:
                # 不配对 → 原样保留 ** 两个字符
                plain_buf.append("*")
                plain_buf.append("*")
                i += 2
                continue

        # ================================================================
        # 优先级3：斜体 *...*（单星号，非双星号）
        # ================================================================
        if text[i] == "*":
            _flush_plain()
            end = text.find("*", i + 1)
            if end != -1:
                # 递归解析斜体内部文本
                inner_text = text[i + 1 : end]
                inner_runs = _scan(inner_text, source_line)
                for r in inner_runs:
                    if not r.code:
                        r.italic = True
                runs.extend(inner_runs)
                i = end + 1
                continue
            else:
                # 不配对 → 原样保留 *
                plain_buf.append("*")
                i += 1
                continue

        # ================================================================
        # 优先级4：超链接 [text](url)
        # ================================================================
        if text[i] == "[":
            _flush_plain()
            close_br = text.find("](", i + 1)
            if close_br != -1:
                close_pr = text.find(")", close_br + 2)
                if close_pr != -1:
                    link_text = text[i + 1 : close_br]
                    link_url = text[close_br + 2 : close_pr]
                    # 递归解析链接文本内部格式
                    link_runs = _scan(link_text, source_line)
                    for r in link_runs:
                        r.link_url = link_url
                    runs.extend(link_runs)
                    i = close_pr + 1
                    continue
            # 不是合法链接语法 → [ 原样保留
            plain_buf.append("[")
            i += 1
            continue

        # ================================================================
        # 优先级5：上标 ^...^（防御性支持）
        # ================================================================
        if text[i] == "^":
            _flush_plain()
            end = text.find("^", i + 1)
            if end != -1 and end > i + 1:
                # 非空上标
                runs.append(
                    InlineRun(text=text[i + 1 : end], superscript=True)
                )
                i = end + 1
                continue
            elif end == i + 1:
                # 空上标 ^^ → 原样保留
                plain_buf.append("^")
                plain_buf.append("^")
                i = end + 1
                continue
            else:
                # 不配对 → 原样保留 ^
                plain_buf.append("^")
                i += 1
                continue

        # ================================================================
        # 普通字符 → 积累到 plain_buf
        # ================================================================
        plain_buf.append(text[i])
        i += 1

    # 收尾：刷出剩余的普通文本
    _flush_plain()
    return runs


# ---------------------------------------------------------------------------
# 自检（模块直接运行时执行）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from ..issues import IssueCollector

    issues = IssueCollector()

    def _check(case: str, expected_count: int, desc: str) -> None:
        result = parse_inline(case, 0, issues)
        # 校验不丢字
        total = "".join(r.text for r in result)
        assert total == case, (
            f"丢字！原文={case!r}，还原={total!r}"
        )
        assert len(result) == expected_count, (
            f"{desc}：期望 {expected_count} 个 run，实际 {len(result)} 个"
        )
        print(f"  PASS: {desc}")

    print("=== inline.py 自检 ===")

    # 1. 普通文本
    r = parse_inline("普通文本", 0, issues)
    assert len(r) == 1
    assert r[0].text == "普通文本"
    assert not r[0].bold and not r[0].italic and not r[0].code
    print("  PASS: 普通文本")

    # 2. 粗体 + 普通
    r = parse_inline("**粗体**文字", 0, issues)
    assert len(r) == 2
    assert r[0].text == "粗体" and r[0].bold
    assert r[1].text == "文字" and not r[1].bold
    print("  PASS: **粗体**文字")

    # 3. 代码 + 普通
    r = parse_inline("`code`普通", 0, issues)
    assert len(r) == 2
    assert r[0].text == "code" and r[0].code
    assert r[1].text == "普通" and not r[1].code
    print("  PASS: `code`普通")

    # 4. 粗体内嵌代码
    r = parse_inline("**粗`内嵌`体**", 0, issues)
    assert len(r) == 3, f"期望3个run，实际{len(r)}: {r}"
    assert r[0].text == "粗" and r[0].bold and not r[0].code
    assert r[1].text == "内嵌" and r[1].code and not r[1].bold
    assert r[2].text == "体" and r[2].bold and not r[2].code
    print("  PASS: **粗`内嵌`体**")

    # 5. 斜体
    r = parse_inline("*斜体*", 0, issues)
    assert len(r) == 1
    assert r[0].text == "斜体" and r[0].italic
    print("  PASS: *斜体*")

    # 6. 链接
    r = parse_inline("[链接](url)", 0, issues)
    assert len(r) == 1
    assert r[0].text == "链接" and r[0].link_url == "url"
    print("  PASS: [链接](url)")

    # 7. 上标（防御性）
    r = parse_inline("E=mc^2^", 0, issues)
    assert len(r) == 2
    assert r[0].text == "E=mc"
    assert r[1].text == "2" and r[1].superscript
    print("  PASS: E=mc^2^")

    # 8. 缺闭合的粗体 → 原样保留
    r = parse_inline("**未闭合", 0, issues)
    assert len(r) == 1
    assert r[0].text == "**未闭合" and not r[0].bold
    print("  PASS: **未闭合（缺闭合→原样）")

    # 9. 缺闭合的代码 → 原样保留
    r = parse_inline("`未闭合代码", 0, issues)
    assert len(r) == 1
    assert r[0].text == "`未闭合代码" and not r[0].code
    print("  PASS: `未闭合代码（缺闭合→原样）")

    # 10. 混合场景
    r = parse_inline("**粗**和*斜*和`代码`混合", 0, issues)
    total = "".join(run.text for run in r)
    assert total == "粗和斜和代码混合", f"还原文本不匹配: {total!r}"
    # 粗 run
    assert r[0].text == "粗" and r[0].bold
    # 普通 "和"
    assert r[1].text == "和" and not r[1].bold
    # 斜 run
    assert r[2].text == "斜" and r[2].italic
    # 普通 "和"
    assert r[3].text == "和" and not r[3].italic
    # 代码 run
    assert r[4].text == "代码" and r[4].code
    # 普通 "混合"
    assert r[5].text == "混合"
    print("  PASS: **粗**和*斜*和`代码`混合")

    # 11. 链接内含粗体
    r = parse_inline("[**粗链接**](http://a.b)", 0, issues)
    assert len(r) == 1
    assert r[0].text == "粗链接" and r[0].bold and r[0].link_url == "http://a.b"
    print("  PASS: [**粗链接**](http://a.b)")

    # 12. 代码内 ** 不被解析
    r = parse_inline("`**不是粗体**`", 0, issues)
    assert len(r) == 1
    assert r[0].text == "**不是粗体**" and r[0].code and not r[0].bold
    print("  PASS: `**不是粗体**`（代码内不解析粗体）")

    # 13. 不丢字抽样（中文标点混合）
    r = parse_inline("中国城市轨道交通——现状与展望（2025）", 0, issues)
    total = "".join(run.text for run in r)
    assert total == "中国城市轨道交通——现状与展望（2025）"
    print("  PASS: 中文标点混合不丢字")

    # 14. 空字符串
    r = parse_inline("", 0, issues)
    assert len(r) == 0
    print("  PASS: 空字符串")

    print(f"\n=== 全部 {14} 项自检通过 ===")
