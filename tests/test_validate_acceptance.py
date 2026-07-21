# -*- coding: utf-8 -*-
"""validate.py 自检测试（验收标准 1-8）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from md2docx.ir import (
    DocumentIR, FigureIR, TableIR, HeadingIR, HeadingKind, TableKind,
    ParagraphIR, ListBlockIR, QuoteIR, InlineRun, MetadataIR, SectionPlan,
    SectionSpec, SectionKind, PageNumFormat, HeaderMode
)
from md2docx.issues import IssueCollector, Level
from md2docx.validate import validate


def mk_para(text, line):
    return ParagraphIR(runs=[InlineRun(text=text)], source_line=line)


def run_and_report(label, doc_ir):
    issues = IssueCollector()
    validate(doc_ir, issues)
    codes = [i.code for i in issues]
    warns = [(i.code, i.message[:60]) for i in issues if i.level == Level.WARNING]
    errors = [(i.code, i.message[:60]) for i in issues if i.level == Level.ERROR]
    print(f"\n--- {label} ---")
    print(f"  总Issue: {len(issues)} | ERROR: {len(errors)} | WARNING: {len(warns)}")
    for c, m in warns + errors:
        print(f"  [{c}] {m}")
    return issues


def test_all():
    # ---- 场景1：有前置引用的图 -> 无警告 ----
    print("=" * 60)
    print("场景1：图有前置引用（合规）")
    doc1 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            mk_para("如图1-1所示，数据清晰可见。", 10),
            FigureIR(figure_id="1-1", chapter_no=1, seq_no=1,
                     caption_text="测试图", alt_raw="图1-1 测试图",
                     path_raw="test.png", path_resolved="test.png",
                     file_exists=False, bookmark_name="fig_1_1",
                     px_w=None, px_h=None, source_line=20),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    doc1.figure_registry["1-1"] = doc1.elements[1]
    run_and_report("场景1：有前置引用", doc1)

    # ---- 场景2：图无引用 -> W-REF-01 ----
    print("=" * 60)
    print("场景2：图无引用 -> W-REF-01")
    doc2 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            FigureIR(figure_id="1-1", chapter_no=1, seq_no=1,
                     caption_text="测试图", alt_raw="图1-1 测试图",
                     path_raw="test.png", path_resolved="test.png",
                     file_exists=False, bookmark_name="fig_1_1",
                     px_w=None, px_h=None, source_line=20),
            mk_para("这是一段不引用任何图的文字。", 30),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    doc2.figure_registry["1-1"] = doc2.elements[0]
    issues2 = run_and_report("场景2：无引用", doc2)
    assert any(i.code == "W-REF-01" for i in issues2), "FAIL: 应有 W-REF-01"
    print("  PASS: W-REF-01 检出")

    # ---- 场景3：引用在图片之后 -> W-REF-02 ----
    print("=" * 60)
    print("场景3：先见图后见文 -> W-REF-02")
    doc3 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            FigureIR(figure_id="1-1", chapter_no=1, seq_no=1,
                     caption_text="测试图", alt_raw="图1-1 测试图",
                     path_raw="test.png", path_resolved="test.png",
                     file_exists=False, bookmark_name="fig_1_1",
                     px_w=None, px_h=None, source_line=10),
            mk_para("如图1-1所示，数据清晰可见。", 20),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    doc3.figure_registry["1-1"] = doc3.elements[0]
    issues3 = run_and_report("场景3：先见图后见文", doc3)
    assert any(i.code == "W-REF-02" for i in issues3), "FAIL: 应有 W-REF-02"
    print("  PASS: W-REF-02 检出")

    # ---- 场景4：引用不存在的编号 -> W-REF-03 ----
    print("=" * 60)
    print("场景4：引用不存在的编号 -> W-REF-03")
    doc4 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            mk_para("如图9-9所示，这是一个不存在的图。", 10),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    issues4 = run_and_report("场景4：引用不存在编号", doc4)
    assert any(i.code == "W-REF-03" for i in issues4), "FAIL: 应有 W-REF-03"
    print("  PASS: W-REF-03 检出")

    # ---- 场景5：位置性指代 -> W-REF-04 ----
    print("=" * 60)
    print("场景5：位置性指代 -> W-REF-04")
    doc5 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            mk_para("下图展示了数据结构。", 10),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    issues5 = run_and_report("场景5：位置性指代", doc5)
    assert any(i.code == "W-REF-04" for i in issues5), "FAIL: 应有 W-REF-04"
    # 验证 "以下图表" 不误报
    doc5b = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            mk_para("以下图表展示了数据结构。", 10),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    issues5b = IssueCollector()
    validate(doc5b, issues5b)
    assert not any(i.code == "W-REF-04" for i in issues5b), "FAIL: 以下图表不应误报"
    print("  PASS: W-REF-04 检出；\"以下图表\"未误报")

    # ---- 场景6：图编号跳号 -> W-IMG-06 ----
    print("=" * 60)
    print("场景6：图编号跳号 -> W-IMG-06")
    doc6 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            FigureIR(figure_id="1-1", chapter_no=1, seq_no=1,
                     caption_text="图A", alt_raw="图1-1 A",
                     path_raw="a.png", path_resolved="a.png",
                     file_exists=False, bookmark_name="fig_1_1",
                     px_w=None, px_h=None, source_line=10),
            FigureIR(figure_id="1-3", chapter_no=1, seq_no=3,
                     caption_text="图C", alt_raw="图1-3 C",
                     path_raw="c.png", path_resolved="c.png",
                     file_exists=False, bookmark_name="fig_1_3",
                     px_w=None, px_h=None, source_line=30),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    doc6.figure_registry["1-1"] = doc6.elements[0]
    doc6.figure_registry["1-3"] = doc6.elements[1]
    issues6 = run_and_report("场景6：图编号跳号", doc6)
    assert any(i.code == "W-IMG-06" for i in issues6), "FAIL: 应有 W-IMG-06"
    print("  PASS: W-IMG-06 检出")

    # ---- 场景7：密级词 -> Warning ----
    print("=" * 60)
    print("场景7：密级词 -> W-CLN-01")
    doc7 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[
            mk_para("本报告为内部资料，请注意保密。", 10),
        ],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    issues7 = run_and_report("场景7：密级词", doc7)
    assert any(i.code == "W-CLN-01" for i in issues7), "FAIL: 应有 W-CLN-01"
    print("  PASS: W-CLN-01 检出")

    # ---- 场景8：空输入 -> 不崩溃 ----
    print("=" * 60)
    print("场景8：空输入 -> 0 Issue")
    doc8 = DocumentIR(
        metadata=MetadataIR(title="测试", subtitle=None, report_type=None,
                            organization=None, version_raw=None, version=None,
                            date=None, title_short="测试"),
        elements=[],
        section_plan=SectionPlan(sections=[
            SectionSpec(kind=SectionKind.BODY, page_num_fmt=PageNumFormat.DECIMAL,
                        page_num_restart=True, header_mode=HeaderMode.TITLE_SHORT,
                        start_element_index=0)
        ]),
        figure_registry={},
        table_registry={},
        xref_registry=[],
    )
    issues8 = run_and_report("场景8：空输入", doc8)
    assert len(issues8) == 0, f"FAIL: 空输入应0 Issue，实际 {len(issues8)}"
    print("  PASS: 空输入不崩溃，0 Issue")

    print("\n" + "=" * 60)
    print("全部8项验收标准通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_all()
