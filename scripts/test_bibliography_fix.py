#!/usr/bin/env python3
"""参考文献缺失修复 —— 回归测试自检脚本。

运行方式：
    cd scripts
    python test_bibliography_fix.py

无 pytest 依赖，tmp fixture 用 tempfile.TemporaryDirectory() 现造现删，
每条 check() 独立可读（风格与 assemble/builder.py 等既有脚本一致）。
"""
import json
import re
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

passed = 0
failed = 0


def check(desc: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        print(f"  [FAIL] {desc}  -- {detail}")


def _write_fixture(base: Path, *, with_appendix: bool, drafts_content: str,
                    source_index_csv: str) -> dict:
    drafts_dir = base / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    (drafts_dir / "ch01-1-1-背景.md").write_text(drafts_content, encoding="utf-8")

    sources_dir = base / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    src_csv = sources_dir / "source-index.csv"
    src_csv.write_text(source_index_csv, encoding="utf-8")

    appendix_yaml = (
        '  appendix:\n    - appendix_letter: "A"\n      appendix_title: "术语表"\n'
        if with_appendix else ""
    )
    outline = base / ("outline-with-appendix.md" if with_appendix else "outline-no-appendix.md")
    outline.write_text(f"""---
struct_template: research
title: "空间态势感知测试报告"
structure:
  frontmatter:
    - chapter_title: "空间态势感知测试报告"
      sections: []
  bodymatter:
    - chapter_no: 1
      chapter_title: "绪论"
      sections:
        - section_no: "1.1"
          section_title: "研究背景"
{appendix_yaml}---

正文占位。
""", encoding="utf-8")

    return {"drafts_dir": drafts_dir, "source_index": src_csv, "outline": outline}


MAIN_DRAFT = """### 研究背景

空间态势感知是保障航天安全的关键能力[SRC-001]。近年来，多国加强了相关系统建设[SRC-002, SRC-003]。

本节简要回顾发展历程。
"""

MAIN_CSV = """source_id,title,author_or_org,publisher,publish_date,source_type,url_or_path
SRC-001,《空间态势感知白皮书》,张三,国防工业出版社,2024-03,journal,
SRC-002,国家航天局年度报告,国家航天局,国家航天局,2023-12,official,https://example.gov.cn/report2023
SRC-003,轨道碎片监测技术综述,李四; 王五,航天学报,2022-06,journal,
"""


def run_pipeline(fixture: dict, tmp: Path, tag: str) -> dict:
    from finalize_pipeline import run_finalize_pipeline
    output_path = tmp / f"final-report-{tag}.md"
    result = run_finalize_pipeline(
        drafts_dir=str(fixture["drafts_dir"]),
        outline_path=str(fixture["outline"]),
        source_index_path=str(fixture["source_index"]),
        output_path=str(output_path),
        log_path=str(tmp / f".degradation-log-{tag}.jsonl"),
    )
    return result


def test_with_appendix(tmp: Path):
    print("\n=== 场景1: 有附录，全流程跑通（overall_pass=True） ===")
    fixture = _write_fixture(tmp / "case1", with_appendix=True,
                              drafts_content=MAIN_DRAFT, source_index_csv=MAIN_CSV)
    result = run_pipeline(fixture, tmp / "case1", "appendix")

    check("overall_pass=True", result["overall_pass"], json.dumps(result, ensure_ascii=False)[:800])
    if not result["overall_pass"]:
        return

    md_text = Path(result["output_path"]).read_text(encoding="utf-8")

    hits = re.findall(r"^## 参考文献\s*$", md_text, re.MULTILINE)
    check("恰好一处 '## 参考文献'", len(hits) == 1, f"实际 {len(hits)} 处")

    m = re.search(r"^## 参考文献\s*$", md_text, re.MULTILINE)
    if m:
        tail = md_text[m.end():]
        next_h2 = re.search(r"^## ", tail, re.MULTILINE)
        section = tail[:next_h2.start()] if next_h2 else tail
        entries = re.findall(r"^\[\d+\]\s", section, re.MULTILINE)
        check("条目数=3", len(entries) == 3, f"实际 {len(entries)} 条")

        appendix_m = re.search(r"^## 附录", md_text, re.MULTILINE)
        if appendix_m:
            check("参考文献位于附录之前", m.start() < appendix_m.start())

    check("不存在裸 '# 参考文献'（H1）",
          not re.search(r"^# 参考文献\s*$", md_text, re.MULTILINE))

    from contract_check import check_contract
    r = check_contract(md_text, merged=True, expect_figures=None, stage="stage9")
    check("C1_h1 通过（无新增H1违规）", r["contract"]["C1_h1"]["pass"],
          str(r["contract"]["C1_h1"]))
    check("C9 对全局参考文献不误报", r["contract"]["C9_local_bibliography"]["pass"],
          str(r["contract"]["C9_local_bibliography"]))
    check("contract_check overall_pass=True", r["overall_pass"])

    from delivery_checklist_check import check_reference_completeness
    r03b = check_reference_completeness(md_text)
    check("03b 一一对应检测通过", r03b["status"] == "pass", str(r03b))


def test_no_appendix(tmp: Path):
    print("\n=== 场景2: 无附录，全流程跑通（overall_pass=True） ===")
    fixture = _write_fixture(tmp / "case2", with_appendix=False,
                              drafts_content=MAIN_DRAFT, source_index_csv=MAIN_CSV)
    result = run_pipeline(fixture, tmp / "case2", "noappendix")
    check("overall_pass=True", result["overall_pass"], json.dumps(result, ensure_ascii=False)[:800])
    if not result["overall_pass"]:
        return

    md_text = Path(result["output_path"]).read_text(encoding="utf-8")
    all_h2 = [mm.start() for mm in re.finditer(r"^## ", md_text, re.MULTILINE)]
    bib_m = re.search(r"^## 参考文献\s*$", md_text, re.MULTILINE)
    check("参考文献是文末最后一个H2章节",
          bool(bib_m) and bool(all_h2) and bib_m.start() == all_h2[-1])


def test_local_bib_in_chapter_draft():
    print("\n=== 场景3: 分章草稿局部参考文献残留仍应报错（stage7） ===")
    from contract_check import check_contract
    text = """### 研究背景

正文内容[SRC-001]。

### 参考文献

[1] 手误写的局部参考文献条目
"""
    r = check_contract(text, merged=False, expect_figures=None, stage="stage7")
    check("C9 检出局部参考文献违规",
          not r["contract"]["C9_local_bibliography"]["pass"],
          str(r["contract"]["C9_local_bibliography"]))


def test_variant_suffix_heading():
    print("\n=== 场景4: H2变体后缀标题（审计核心发现）应报错 ===")
    from contract_check import check_contract
    text = """# 报告标题

## 第 1 章：绪论

正文[1]。

## 参考文献列表

[1] xxx
"""
    r = check_contract(text, merged=True, expect_figures=None, stage="stage9")
    c9 = r["contract"]["C9_local_bibliography"]
    check("变体后缀'参考文献列表'被拒绝（不再被末尾锚定绕过）",
          not c9["pass"], str(c9))


def test_mixed_local_and_global():
    print("\n=== 场景5: 局部残留(H3)+全局(H2)混合 应报错 ===")
    from contract_check import check_contract
    text = """# 报告标题

## 第 1 章：绪论

正文正文[1]。

### 参考文献

[1] 不应出现在这里的局部残留

## 参考文献

[1] xxx

## 附录A：术语表
"""
    r = check_contract(text, merged=True, expect_figures=None, stage="stage9")
    c9 = r["contract"]["C9_local_bibliography"]
    check("计数>=2（局部+全局都被计入）", c9["count"] >= 2, str(c9))
    check("判负（不能因命中全局合规就整体放行）", not c9["pass"], str(c9))


def test_duplicate_insertion():
    print("\n=== 场景6: 参考文献重复插入两次 应报错 ===")
    from contract_check import check_contract
    text = """# 报告标题

## 第 1 章：绪论

正文正文[1]。

## 参考文献

[1] xxx

## 附录A：术语表

## 参考文献

[1] xxx（重复插入）
"""
    r = check_contract(text, merged=True, expect_figures=None, stage="stage9")
    c9 = r["contract"]["C9_local_bibliography"]
    check("计数=2", c9["count"] == 2, str(c9))
    check("判负（重复插入不能静默通过）", not c9["pass"], str(c9))


def test_missing_source_index(tmp: Path):
    print("\n=== 场景7: source-index.csv 缺失应结构化失败而非崩溃 ===")
    from finalize_pipeline import run_finalize_pipeline
    fixture = _write_fixture(tmp / "case7", with_appendix=False,
                              drafts_content=MAIN_DRAFT, source_index_csv=MAIN_CSV)
    result = run_finalize_pipeline(
        drafts_dir=str(fixture["drafts_dir"]),
        outline_path=str(fixture["outline"]),
        source_index_path=str(tmp / "not-exist.csv"),
        output_path=str(tmp / "case7" / "final-report.md"),
        log_path=str(tmp / "case7" / ".degradation-log.jsonl"),
    )
    check("overall_pass=False", not result["overall_pass"])
    check("failure_step=convert_refs", result.get("failure_step") == "convert_refs",
          str(result.get("failure_step")))


def test_slash_refs(tmp: Path):
    print("\n=== 场景8: 斜杠分隔引用应报错而非静默跳过 ===")
    from finalize_pipeline import run_finalize_pipeline
    fixture = _write_fixture(
        tmp / "case8", with_appendix=False,
        drafts_content="### 研究背景\n\n不支持的引用格式[SRC-001/SRC-003]。\n",
        source_index_csv=MAIN_CSV,
    )
    result = run_finalize_pipeline(
        drafts_dir=str(fixture["drafts_dir"]),
        outline_path=str(fixture["outline"]),
        source_index_path=str(fixture["source_index"]),
        output_path=str(tmp / "case8" / "final-report.md"),
        log_path=str(tmp / "case8" / ".degradation-log.jsonl"),
    )
    check("overall_pass=False", not result["overall_pass"])
    check("failure_step=convert_refs", result.get("failure_step") == "convert_refs",
          str(result.get("failure_step")))


def test_docx_roundtrip(tmp: Path):
    print("\n=== 场景9: docx 层回读校验（防止 md层正确、docx层丢失） ===")
    import subprocess
    fixture = _write_fixture(tmp / "case9", with_appendix=True,
                              drafts_content=MAIN_DRAFT, source_index_csv=MAIN_CSV)
    from finalize_pipeline import run_finalize_pipeline
    result = run_finalize_pipeline(
        drafts_dir=str(fixture["drafts_dir"]),
        outline_path=str(fixture["outline"]),
        source_index_path=str(fixture["source_index"]),
        output_path=str(tmp / "case9" / "final-report.md"),
        log_path=str(tmp / "case9" / ".degradation-log.jsonl"),
    )
    check("overall_pass=True", result["overall_pass"], json.dumps(result, ensure_ascii=False)[:800])
    if not result["overall_pass"]:
        return
    md_source_path = result["output_path"]

    docx_path = tmp / "case9" / "final-report.docx"
    proc = subprocess.run(
        [sys.executable, "-m", "md2docx", md_source_path, str(docx_path),
         "--allow-missing-figures"],
        cwd=str(SCRIPT_DIR), capture_output=True, text=True, encoding="utf-8",
    )
    check("md2docx 转换成功", docx_path.exists(), proc.stderr[-1500:] if proc.stderr else proc.stdout[-1500:])
    if not docx_path.exists():
        return

    from docx import Document
    d = Document(str(docx_path))
    paras = d.paragraphs
    idx_list = [i for i, p in enumerate(paras) if p.text.strip() == "参考文献"]
    check("docx中存在'参考文献'段落", len(idx_list) == 1, f"命中 {len(idx_list)} 处")
    if idx_list:
        idx = idx_list[0]
        style = paras[idx].style.name if paras[idx].style else ""
        check("该段落样式为 Heading 1（报告级组成部分，与 CHAPTER/APPENDIX 同级）",
              style == "Heading 1", style)

        j = idx + 1
        body_texts = []
        while j < len(paras):
            st = paras[j].style.name if paras[j].style else ""
            if st.startswith("Heading"):
                break
            if paras[j].text.strip():
                body_texts.append(paras[j].text.strip())
            j += 1
        check("Heading后有非空正文段落", len(body_texts) > 0)
        entry_lines = [t for t in body_texts if re.match(r"^\[\d+\]", t)]
        check("docx中条目数=3（防止md层正确docx层丢失）",
              len(entry_lines) == 3, f"实际 {len(entry_lines)}：{entry_lines}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="drr_bib_test_") as tmpdir:
        tmp = Path(tmpdir)
        test_with_appendix(tmp)
        test_no_appendix(tmp)
        test_local_bib_in_chapter_draft()
        test_variant_suffix_heading()
        test_mixed_local_and_global()
        test_duplicate_insertion()
        test_missing_source_index(tmp)
        test_slash_refs(tmp)
        test_docx_roundtrip(tmp)

    print(f"\n=== 总计: {passed} PASS / {failed} FAIL ===")
    sys.exit(1 if failed else 0)
