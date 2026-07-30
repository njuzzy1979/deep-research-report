#!/usr/bin/env python3
"""阶段 4 骨架 docx 预确认生成器（D1-8）。

用户诉求原文："能否在阶段 4（大纲确认）就生成整个报告的初版 word 模板，里面有
封面、目录、每个章节的一级标题和二级标题……如果这个模板用户确认，那么后续工作
就不要改变这个模板，只是在后续工作中增加内容。"

两步实现，**不新写任何 docx 生成代码**：

1. 合成骨架 Markdown（``research/drafts/.outline-skeleton.md``）——复用
   ``outline_title_extract.build_title_tree()`` 拿层级树，按
   ``frontmatter → bodymatter → appendix`` 顺序输出：
     报告题名 → ``#``；每章 ``chapter_title`` → ``##``；
     每节 ``section_title`` → ``###``
2. 调用既有 md2docx 产出 docx。

层级映射（实测）：``##``→``Heading 1``（用户口中的"一级标题"）、
``###``→``Heading 2``（"二级标题"）、``####``→``Heading 3``。

【硬依赖】本脚本强依赖 D1-1 键名归一化与 D1-9 结构门禁：
  未经 D1-1 时，对真实 outline 提取标题树会得到 **13/13 空标题且 EXIT=0**
  （静默成功），产出一份"16 个空白标题"的 docx。
  未经 D1-9 逼出 section 级数据时，骨架只有章标题、节层完全空白，用户确认
  这样一份骨架恰好落入**"我在阶段 4 已经确认过了"的虚假安全感**——比不做
  这个功能更危险。故本脚本在 section 数据全空时**默认拒绝产出**（需
  ``--allow-empty-sections`` 显式放行，且产出物中带醒目告警）。

【与 D2-9 规则一的接口约定】本脚本只合成 Markdown，docx **一律交给
``python -m md2docx``**，绝不自行 ``from docx import Document``。这是登记在案的
**合法调用正样本**——未来做 hook 误伤率测试时不得把本脚本当违规样本。
两条独立的不命中路径：① 骨架落 ``research/`` 不在 output_dir 下；
② 命令含 md2docx 引用而无 python-docx 特征。

【产物落位】骨架**不进 output/**（``stage-9-finalize.md`` 定义 output/ 为
"最终交付物"目录，骨架是阶段 4 的中间确认件，进 output/ 必然与终稿混淆）。
中间 md 用点号前缀隐藏件约定，且**不得命名为 final-report***（否则被阶段 9
的 glob 误吃）。

用法::

    python scripts/outline_skeleton.py --outline research/outline.md \\
        --cover research/cover.md
    python scripts/outline_skeleton.py --outline research/outline.md --json

退出码：0 = 骨架 md 与 docx 均产出成功；1 = section 数据全空而未显式放行，
       或 md2docx 转换失败；2 = 用法层面错误（outline 不存在等）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from md2docx.assemble.outline_reader import (  # noqa: E402
    extract_yaml_front_matter,
    normalize_outline_structure,
)
from md2docx.issues import IssueCollector  # noqa: E402
from outline_title_extract import build_title_tree  # noqa: E402

OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

SKELETON_MD_RELNAME = ".outline-skeleton.md"
SKELETON_DOCX_RELNAME = "outline-skeleton-preview.docx"

# 每个节标题下的占位提示行。**这一行是必需的**（不是装饰）：
# 若节下完全空白，D2-7 的 docx 回读门禁在修复前会因把 Heading 2 文本误当正文
# 而误判通过；同时它让用户在 Word 中看到明确的"此处待填充"语义，而不是一片
# 疑似渲染失败的空白。
SECTION_PLACEHOLDER = "> （本节内容待阶段 7 写作填充）"

# 骨架文案中**不得出现**的词汇：gate3.py 的 _check_secrecy 是剔除型门禁
# （全文搜索密级关键词，出现即 FATAL）。本 skill 的既定立场是产物一律不带
# 密级标注，故骨架的占位文案须避开这类词，否则骨架自身会触发 gate3 FATAL。
_FORBIDDEN_IN_PLACEHOLDER = ("密级", "内部资料", "秘密", "机密")


def build_skeleton_markdown(structure: dict, report_title: str) -> tuple:
    """把 structure 合成为骨架 Markdown 文本。

    Returns:
        ``(markdown_text, stats)``，``stats`` 含 chapter_count / section_count。
    """
    issues = IssueCollector()
    tree = build_title_tree(normalize_outline_structure(structure), issues)

    lines: list = []
    if report_title:
        lines += [f"# {report_title}", ""]

    section_total = 0

    for fm in tree.get("frontmatter", []) or []:
        title = str(fm.get("chapter_title") or "").strip()
        if title:
            lines += [f"## {title}", "", SECTION_PLACEHOLDER, ""]
        for sec in fm.get("sections", []) or []:
            s = str(sec or "").strip()
            if s:
                lines += [f"### {s}", "", SECTION_PLACEHOLDER, ""]
                section_total += 1

    chapters = tree.get("chapters", []) or []
    for ch in chapters:
        c_title = str(ch.get("chapter_title") or "").strip()
        lines += [f"## {c_title or '(未命名章)'}", ""]
        secs = ch.get("sections", []) or []
        if not secs:
            lines += [
                "> ⚠️ 本章在 outline.md 中**未声明任何节**（section）——"
                "骨架无法呈现其二级标题结构，请回到阶段 4 补齐后重新生成。",
                "",
            ]
        for sec in secs:
            s_title = sec if isinstance(sec, str) else str(
                (sec or {}).get("section_title") or ""
            )
            s_title = s_title.strip()
            if not s_title:
                continue
            lines += [f"### {s_title}", "", SECTION_PLACEHOLDER, ""]
            section_total += 1

    for apx in tree.get("appendix", []) or []:
        letter = str(apx.get("appendix_letter") or "").strip()
        a_title = str(apx.get("appendix_title") or "").strip()
        if a_title:
            head = f"附录{letter}：{a_title}" if letter else f"附录：{a_title}"
            lines += [f"## {head}", "", SECTION_PLACEHOLDER, ""]

    text = "\n".join(lines).rstrip() + "\n"
    stats = {
        "chapter_count": len(chapters),
        "section_count": section_total,
        "chapters_without_sections": [
            str(ch.get("chapter_title") or "")
            for ch in chapters
            if not (ch.get("sections") or [])
        ],
    }
    return text, stats


def generate_skeleton(
    outline_path: str,
    cover_path: str | None = None,
    allow_empty_sections: bool = False,
) -> dict:
    """产出骨架 md + 骨架 docx，返回结构化结果。"""
    result: dict = {
        "outline_path": str(Path(outline_path).resolve()),
        "skeleton_md": None,
        "skeleton_docx": None,
        "stats": {},
        "warnings": [],
        "passed": False,
    }

    op = Path(outline_path)
    if not op.exists():
        result["error"] = f"outline.md 不存在: {outline_path}"
        return result

    parsed, _body = extract_yaml_front_matter(op.read_text(encoding="utf-8", errors="replace"), str(op))
    if not isinstance(parsed, dict) or "structure" not in parsed:
        result["error"] = "outline.md 的 YAML front matter 中缺少 structure 节点"
        return result

    report_title = str(parsed.get("title") or parsed.get("report_title") or "").strip()
    md_text, stats = build_skeleton_markdown(parsed["structure"], report_title)
    result["stats"] = stats

    # 密级词自检：骨架文案不得触发 gate3 的剔除型密级门禁
    for word in _FORBIDDEN_IN_PLACEHOLDER:
        if word in SECTION_PLACEHOLDER:
            result["error"] = f"骨架占位文案含密级关键词「{word}」，会触发 gate3 FATAL"
            return result

    # section 数据全空时默认拒绝产出——避免制造"已确认过结构"的虚假安全感
    if stats["section_count"] == 0 and not allow_empty_sections:
        result["error"] = (
            f"outline.md 声明了 {stats['chapter_count']} 章但**0 个节**，"
            f"骨架只会呈现章标题、节层完全空白。用户确认这样一份骨架会产生"
            f"「我在阶段 4 已经确认过了」的虚假安全感，比不做本功能更危险。\n"
            f"请先回到阶段 4 补齐 structure.bodymatter[*].sections"
            f"（可运行 python scripts/outline_structure_gate.py 查看缺口），"
            f"或显式加 --allow-empty-sections 放行（不推荐）"
        )
        return result

    if stats["chapters_without_sections"]:
        result["warnings"].append(
            f"{len(stats['chapters_without_sections'])} 个章未声明任何节，"
            f"骨架中已就地标注告警：{stats['chapters_without_sections'][:5]}"
        )

    # 中间 md 落 research/drafts/，点号前缀隐藏件；**不得命名为 final-report***
    drafts_dir = op.parent / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    md_path = drafts_dir / SKELETON_MD_RELNAME
    md_path.write_text(md_text, encoding="utf-8")
    result["skeleton_md"] = str(md_path)

    # docx 落 research/，**不进 output/**（output/ 是最终交付物目录）
    docx_path = op.parent / SKELETON_DOCX_RELNAME

    # 【D2-9 合法调用正样本】docx 一律交给 md2docx，绝不自行 from docx import
    cmd = [sys.executable, "-m", "md2docx", str(md_path), str(docx_path)]
    if cover_path and Path(cover_path).exists():
        cmd += ["--cover", str(cover_path)]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True, text=True, encoding="utf-8",
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as e:
        result["error"] = f"调用 md2docx 失败: {e}"
        return result

    result["md2docx_exit"] = proc.returncode
    if proc.returncode != 0:
        result["error"] = (
            f"md2docx 转换失败（exit={proc.returncode}）: "
            f"{(proc.stderr or proc.stdout or '')[-500:]}"
        )
        return result

    result["skeleton_docx"] = str(docx_path)
    result["passed"] = True
    return result


def format_text_report(result: dict) -> str:
    lines = ["=== 阶段4 骨架 docx 预确认生成（D1-8）===", ""]
    if result.get("error"):
        lines.append(f"{FAIL} {result['error']}")
        return "\n".join(lines)

    st = result.get("stats", {})
    # CP3 呈报须附机器判据数字，使用户的确认对象是**数字**而非印象
    lines.append(f"{OK} 骨架已产出。结构判据数字（请据此确认，而非仅凭印象浏览）：")
    lines.append(f"      章（docx Heading 1）: {st.get('chapter_count', 0)}")
    lines.append(f"      节（docx Heading 2）: {st.get('section_count', 0)}")
    for w in result.get("warnings", []):
        lines.append(f"{WARN} {w}")
    lines.append("")
    lines.append(f"      骨架 Markdown: {result.get('skeleton_md')}")
    lines.append(f"      骨架 docx    : {result.get('skeleton_docx')}")
    lines.append("")
    lines.append("请在 Word 中打开骨架 docx，确认章节框架后于 CP3 明确回复确认。")
    lines.append(
        "确认后的 H1/H2 结构进入锁定：新增/拆分/合并章或节须**回到阶段 4** "
        "重走门禁与确认（锁定语义是「变更须走显式回炉」，不是「禁止变更」）。"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段4 骨架 docx 预确认生成（D1-8）：合成骨架 md + 调用 md2docx"
    )
    parser.add_argument("--outline", required=True, help="outline.md 路径")
    parser.add_argument("--cover", default=None, help="cover.md 路径（可选，填充封面）")
    parser.add_argument(
        "--allow-empty-sections", action="store_true",
        help="section 数据全空时仍强行产出骨架（不推荐：会制造虚假安全感）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not Path(args.outline).exists():
        print(f"{FAIL} outline.md 不存在: {args.outline}", file=sys.stderr)
        sys.exit(2)

    result = generate_skeleton(args.outline, args.cover, args.allow_empty_sections)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(result))

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
