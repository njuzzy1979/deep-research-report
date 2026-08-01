# -*- coding: utf-8 -*-
"""drawio_layout_validator.py 的单元测试（B1'：G1+G6+G7+G10a）。

覆盖范围（对齐 02 号设计文档 §2/§3/§4 的最小子集承诺）：
- G1 几何完整性判据：正常文件 PASS，含 BAD_LITERALS（如 x="None"）的文件 FAIL
- G6 内嵌图注判据：CAPTION_IDS/CAPTION_PAT 命中 FAIL；同时用测试如实标注 R2 已知
  局限（`<b>图注：</b>` 类 HTML 包裹文本的假阴性，06 号文档裁决不修复）
- G7 伪图检测判据：Mermaid 源码关键字命中 FAIL，且 error_code=FAKE_DIAGRAM 为
  唯一 retryable=True 的判据
- G10a 拓扑-模式一致性判据：flow/star/grid/quadrant 四路 mode-dispatch 全覆盖，
  以及未提供 --ir 时的 not_applicable 分支、stack/pyramid/manual 的不适用分支
- exit code 三档约定中的 0（PASS）与 1（校验失败）两档（本骨架版本暂无 skip 场景，
  exit 2 暂不在覆盖范围内，见脚本头部"范围声明"）
- --mode warn 恒 passed=True / exit_code=0，但 summary.errors 计数不被静默清零
  （对应 D5 反例 26"禁止吞码"的设计意图：warn 模式退化但不掩盖数据）
- 空目录场景按"未声明架构图"分支判 PASS
- --report-out 留痕文件确实落盘，且内容与函数返回值一致
- --file 与 --figures-dir 各自独立工作
- --ir 参数：与 --file 一一对应、个数不一致报错、文件不存在报错、
  --figures-dir 批量模式下忽略并打印 INFO
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import drawio_layout_validator as dlv


_GOOD_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="a" value="A" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="120" height="60" as="geometry" />
        </mxCell>
        <mxCell id="b" value="B" vertex="1" parent="1">
          <mxGeometry x="240" y="40" width="120" height="60" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

_BAD_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="L1" value="L1" vertex="1" parent="1">
          <mxGeometry x="None" y="40" width="None" height="60" as="geometry" />
        </mxCell>
        <mxCell id="L2" value="L2" vertex="1" parent="1">
          <mxGeometry x="40" y="120" width="120" height="60" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

_MALFORMED_XML = "<mxfile><this is not valid xml"


# ---------------------------------------------------------------------------
# G6 fixtures：CAPTION_IDS 命中 / CAPTION_PAT 命中 / R2 已知局限（HTML 包裹假阴性）
# ---------------------------------------------------------------------------

_G6_HIT_BY_ID_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="a" value="A" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="120" height="60" as="geometry" />
        </mxCell>
        <mxCell id="note" value="补充说明文字" vertex="1" parent="1">
          <mxGeometry x="40" y="120" width="300" height="30" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

_G6_HIT_BY_PATTERN_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="a" value="A" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="120" height="60" as="geometry" />
        </mxCell>
        <mxCell id="capText1" value="图注：这是说明文字" vertex="1" parent="1">
          <mxGeometry x="40" y="120" width="300" height="30" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

# R2 已知局限（06 号文档 §3.3.3 裁决不修复）：CAPTION_PAT 直接匹配 value 原文，
# 未先 strip_html() 剥离标签，故 `<b>图注：</b>` 类 HTML 包裹文本产生假阴性。
_G6_HTML_WRAPPED_MISS_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="a" value="A" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="120" height="60" as="geometry" />
        </mxCell>
        <mxCell id="capText2" value="&lt;b&gt;图注：&lt;/b&gt;这是说明文字" vertex="1" parent="1">
          <mxGeometry x="40" y="120" width="300" height="30" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

# ---------------------------------------------------------------------------
# G7 fixture：value 中残留 Mermaid 源码关键字
# ---------------------------------------------------------------------------

_G7_FAKE_DIAGRAM_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="fakeDiagram" value="flowchart TD&#10;A--&gt;B" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="200" height="60" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

# ---------------------------------------------------------------------------
# G10a fixtures：flow 模式重汇合 / 线性链（需含边，source/target 引用 vertex id）
# ---------------------------------------------------------------------------

_G10A_FLOW_RECONVERGENT_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="A" value="A" vertex="1" parent="1"><mxGeometry x="40" y="40" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="B" value="B" vertex="1" parent="1"><mxGeometry x="200" y="0" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="C" value="C" vertex="1" parent="1"><mxGeometry x="200" y="80" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="D" value="D" vertex="1" parent="1"><mxGeometry x="360" y="40" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="e1" edge="1" source="A" target="B" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e2" edge="1" source="A" target="C" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e3" edge="1" source="B" target="D" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e4" edge="1" source="C" target="D" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""

_G10A_FLOW_LINEAR_DRAWIO = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="test">
  <diagram>
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageWidth="1000" pageHeight="800">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="A" value="A" vertex="1" parent="1"><mxGeometry x="40" y="40" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="B" value="B" vertex="1" parent="1"><mxGeometry x="200" y="40" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="C" value="C" vertex="1" parent="1"><mxGeometry x="360" y="40" width="80" height="40" as="geometry" /></mxCell>
        <mxCell id="e1" edge="1" source="A" target="B" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="e2" edge="1" source="B" target="C" parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


@pytest.fixture
def good_file(tmp_path):
    p = tmp_path / "good.drawio"
    p.write_text(_GOOD_DRAWIO, encoding="utf-8")
    return p


@pytest.fixture
def bad_file(tmp_path):
    p = tmp_path / "bad.drawio"
    p.write_text(_BAD_DRAWIO, encoding="utf-8")
    return p


@pytest.fixture
def figures_dir(tmp_path, good_file, bad_file):
    return tmp_path


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def g6_hit_by_id_file(tmp_path):
    return _write(tmp_path, "g6_by_id.drawio", _G6_HIT_BY_ID_DRAWIO)


@pytest.fixture
def g6_hit_by_pattern_file(tmp_path):
    return _write(tmp_path, "g6_by_pattern.drawio", _G6_HIT_BY_PATTERN_DRAWIO)


@pytest.fixture
def g6_html_wrapped_miss_file(tmp_path):
    return _write(tmp_path, "g6_html_wrapped.drawio", _G6_HTML_WRAPPED_MISS_DRAWIO)


@pytest.fixture
def g7_fake_diagram_file(tmp_path):
    return _write(tmp_path, "g7_fake.drawio", _G7_FAKE_DIAGRAM_DRAWIO)


@pytest.fixture
def g10a_flow_reconvergent_file(tmp_path):
    return _write(tmp_path, "g10a_reconvergent.drawio", _G10A_FLOW_RECONVERGENT_DRAWIO)


@pytest.fixture
def g10a_flow_linear_file(tmp_path):
    return _write(tmp_path, "g10a_linear.drawio", _G10A_FLOW_LINEAR_DRAWIO)


@pytest.fixture
def ir_flow_file(tmp_path):
    p = tmp_path / "flow.ir.json"
    p.write_text(json.dumps({"layout_mode": "flow"}), encoding="utf-8")
    return p


@pytest.fixture
def ir_stack_file(tmp_path):
    p = tmp_path / "stack.ir.json"
    p.write_text(json.dumps({"layout_mode": "stack/pyramid"}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# check_g1() 判据本体
# ---------------------------------------------------------------------------

def test_check_g1_detects_none_literal():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_BAD_DRAWIO)
    vertex_elems = [c for c in root.iter("mxCell") if c.get("vertex") == "1"]
    bad = dlv.check_g1(vertex_elems)
    bad_ids = {b["id"] for b in bad}
    assert bad_ids == {"L1"}
    assert any(b["attr"] == "x" and b["literal"] == "None" for b in bad)
    assert any(b["attr"] == "width" and b["literal"] == "None" for b in bad)


def test_check_g1_passes_valid_geometry():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_GOOD_DRAWIO)
    vertex_elems = [c for c in root.iter("mxCell") if c.get("vertex") == "1"]
    bad = dlv.check_g1(vertex_elems)
    assert bad == []


# ---------------------------------------------------------------------------
# check_g6() 判据本体
# ---------------------------------------------------------------------------

def test_check_g6_hits_caption_ids():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G6_HIT_BY_ID_DRAWIO)
    cells = list(root.iter("mxCell"))
    hits = dlv.check_g6(cells)
    assert hits == ["note"]


def test_check_g6_hits_caption_pattern():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G6_HIT_BY_PATTERN_DRAWIO)
    cells = list(root.iter("mxCell"))
    hits = dlv.check_g6(cells)
    assert hits == ["capText1"]


def test_check_g6_html_wrapped_caption_is_known_false_negative():
    """R2 已知局限（06 号文档 §3.3.3 裁决不修复）：`<b>图注：</b>` 类 HTML

    包裹文本因 CAPTION_PAT 未先 strip_html() 而产生假阴性——本测试如实
    记录该行为为"预期不命中"，而非验证判据"正确工作"。若未来有人修复
    R2，这条测试会失败，提醒同步更新 06 号文档裁决记录。
    """
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G6_HTML_WRAPPED_MISS_DRAWIO)
    cells = list(root.iter("mxCell"))
    hits = dlv.check_g6(cells)
    assert hits == []


def test_check_g6_passes_when_no_caption():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_GOOD_DRAWIO)
    cells = list(root.iter("mxCell"))
    assert dlv.check_g6(cells) == []


# ---------------------------------------------------------------------------
# check_g7() 判据本体
# ---------------------------------------------------------------------------

def test_check_g7_detects_mermaid_keyword():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G7_FAKE_DIAGRAM_DRAWIO)
    cells = list(root.iter("mxCell"))
    hits = dlv.check_g7(cells)
    hit_ids = {cid for cid, _ in hits}
    assert hit_ids == {"fakeDiagram"}
    assert any(kw == "flowchart" for _, kw in hits)
    assert any(kw == "-->" for _, kw in hits)


def test_check_g7_passes_when_no_mermaid_keyword():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_GOOD_DRAWIO)
    cells = list(root.iter("mxCell"))
    assert dlv.check_g7(cells) == []


# ---------------------------------------------------------------------------
# extract_topology() / check_g10a() 判据本体
# ---------------------------------------------------------------------------

def test_extract_topology_reads_vertices_and_edges():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G10A_FLOW_RECONVERGENT_DRAWIO)
    cells = list(root.iter("mxCell"))
    V, E = dlv.extract_topology(cells)
    assert V == {"A", "B", "C", "D"}
    assert len(E) == 4
    assert ("A", "B") in E and ("C", "D") in E


def test_check_g10a_flow_reconvergent():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G10A_FLOW_RECONVERGENT_DRAWIO)
    V, E = dlv.extract_topology(list(root.iter("mxCell")))
    verdict, detail = dlv.check_g10a("flow", V, E)
    assert verdict == "FLOW_RECONVERGENT"
    assert detail["n_vertex"] == 4
    assert detail["n_edge"] == 4


def test_check_g10a_flow_linear_passes():
    import xml.etree.ElementTree as ET
    root = ET.fromstring(_G10A_FLOW_LINEAR_DRAWIO)
    V, E = dlv.extract_topology(list(root.iter("mxCell")))
    verdict, detail = dlv.check_g10a("flow", V, E)
    assert verdict is None
    assert detail["n_vertex"] == 3


def test_check_g10a_star_no_edges():
    V, E = {"A", "B", "C"}, []
    verdict, _ = dlv.check_g10a("star", V, E)
    assert verdict == "STAR_NO_EDGES"


def test_check_g10a_star_no_unique_hub():
    # A-B, A-C, D-B：B 与 A 同为度数 2，无唯一 hub
    V = {"A", "B", "C", "D"}
    E = [("A", "B"), ("A", "C"), ("D", "B")]
    verdict, detail = dlv.check_g10a("star", V, E)
    assert verdict == "STAR_NO_UNIQUE_HUB"
    assert set(detail["hubs"]) == {"A", "B"}


def test_check_g10a_star_hub_not_dominant():
    # center 度数 3，次高度 2：3 < max(3, 2*2)=4，不达支配阈值
    V = {"center", "a", "b", "c", "d"}
    E = [("center", "a"), ("center", "b"), ("center", "c"), ("a", "d"), ("b", "d")]
    verdict, detail = dlv.check_g10a("star", V, E)
    assert verdict == "STAR_HUB_NOT_DOMINANT"
    assert detail["hub"] == "center"


def test_check_g10a_star_hub_dominant_passes():
    # center 度数 7，次高度 1：7 >= max(3, 1*2)=3，通过（对齐 3-2 实测基线）
    V = {"center", "d1", "d2", "d3", "d4", "d5", "d6", "d7"}
    E = [("center", f"d{i}") for i in range(1, 8)]
    verdict, detail = dlv.check_g10a("star", V, E)
    assert verdict is None
    assert detail["hub"] == "center"


def test_check_g10a_grid_no_edges_passes():
    V, E = {"A", "B", "C"}, []
    verdict, _ = dlv.check_g10a("grid", V, E)
    assert verdict is None


def test_check_g10a_grid_has_connected_structure():
    # 6 个顶点里 4 个连成一条链，4 > 6/3=2，命中
    V = {"A", "B", "C", "D", "E", "F"}
    E = [("A", "B"), ("B", "C"), ("C", "D")]
    verdict, detail = dlv.check_g10a("grid", V, E)
    assert verdict is not None
    assert verdict.startswith("GRID_HAS_CONNECTED_STRUCTURE")
    assert detail["largest_component"] == 4


def test_check_g10a_quadrant_uses_same_logic_as_grid():
    V = {"A", "B", "C", "D", "E", "F"}
    E = [("A", "B"), ("B", "C"), ("C", "D")]
    verdict_grid, _ = dlv.check_g10a("grid", V, E)
    verdict_quadrant, _ = dlv.check_g10a("quadrant", V, E)
    assert verdict_grid == verdict_quadrant


def test_check_g10a_unknown_mode():
    verdict, _ = dlv.check_g10a("bogus_mode", {"A"}, [])
    assert verdict == "UNKNOWN_MODE(bogus_mode)"


# ---------------------------------------------------------------------------
# validate_one_file()
# ---------------------------------------------------------------------------

def test_validate_one_file_good(good_file):
    item = dlv.validate_one_file(good_file)
    assert item["passed"] is True
    assert item["vertex_total"] == 2
    assert item["vertex_geometry_valid"] == 2
    assert item["checks"]["G1_geometry_integrity"] == "pass"
    assert item["checks"]["G6_embedded_caption"] == "pass"
    assert item["checks"]["G7_fake_diagram"] == "pass"
    assert item["checks"]["G10a_topology"] == "not_applicable"
    assert item["issues"] == []


def test_validate_one_file_bad(bad_file):
    item = dlv.validate_one_file(bad_file)
    assert item["passed"] is False
    assert item["vertex_total"] == 2
    assert item["vertex_geometry_valid"] == 1
    assert item["checks"]["G1_geometry_integrity"] == "fail"
    assert len(item["issues"]) == 1
    issue = item["issues"][0]
    assert issue["error_code"] == "GEOMETRY_INVALID"
    assert issue["severity"] == "error"
    assert issue["retryable"] is False


def test_validate_one_file_g6_hit(g6_hit_by_id_file):
    item = dlv.validate_one_file(g6_hit_by_id_file)
    assert item["passed"] is False
    assert item["checks"]["G6_embedded_caption"] == "fail"
    issue = next(i for i in item["issues"] if i["check"] == "G6_embedded_caption")
    assert issue["error_code"] == "EMBEDDED_CAPTION"
    assert issue["retryable"] is False
    assert issue["cells"] == ["note"]


def test_validate_one_file_g7_hit(g7_fake_diagram_file):
    item = dlv.validate_one_file(g7_fake_diagram_file)
    assert item["passed"] is False
    assert item["checks"]["G7_fake_diagram"] == "fail"
    issue = next(i for i in item["issues"] if i["check"] == "G7_fake_diagram")
    assert issue["error_code"] == "FAKE_DIAGRAM"
    assert issue["retryable"] is True


def test_validate_one_file_g10a_without_ir_is_not_applicable(g10a_flow_reconvergent_file):
    """未提供 ir_path 时 G10a 不臆测 mode，记为 not_applicable，不影响 passed。"""
    item = dlv.validate_one_file(g10a_flow_reconvergent_file)
    assert item["checks"]["G10a_topology"] == "not_applicable"
    assert item["passed"] is True


def test_validate_one_file_g10a_with_ir_flow_reconvergent(g10a_flow_reconvergent_file, ir_flow_file):
    item = dlv.validate_one_file(g10a_flow_reconvergent_file, ir_path=ir_flow_file)
    assert item["passed"] is False
    assert item["checks"]["G10a_topology"] == "fail"
    issue = next(i for i in item["issues"] if i["check"] == "G10a_topology")
    assert issue["error_code"] == "FLOW_RECONVERGENT"
    assert issue["retryable"] is False


def test_validate_one_file_g10a_with_ir_flow_linear_passes(g10a_flow_linear_file, ir_flow_file):
    item = dlv.validate_one_file(g10a_flow_linear_file, ir_path=ir_flow_file)
    assert item["passed"] is True
    assert item["checks"]["G10a_topology"] == "pass"


def test_validate_one_file_g10a_stack_mode_not_applicable(g10a_flow_linear_file, ir_stack_file):
    """layout_mode=stack/pyramid 时 G10a 不适用（01 号文档 §3.7.1，交 G10b）。"""
    item = dlv.validate_one_file(g10a_flow_linear_file, ir_path=ir_stack_file)
    assert item["checks"]["G10a_topology"] == "not_applicable"
    assert item["passed"] is True


def test_validate_one_file_malformed_xml(tmp_path):
    p = tmp_path / "malformed.drawio"
    p.write_text(_MALFORMED_XML, encoding="utf-8")
    item = dlv.validate_one_file(p)
    assert item["passed"] is False
    assert item["issues"][0]["error_code"] == "XML_PARSE_ERROR"
    assert item["issues"][0]["retryable"] is False


# ---------------------------------------------------------------------------
# run_validator()：exit code 与 mode=warn
# ---------------------------------------------------------------------------

def test_run_validator_all_pass(good_file):
    result = dlv.run_validator([good_file])
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["summary"]["errors"] == 0


def test_run_validator_block_mode_fails_on_bad_file(good_file, bad_file):
    result = dlv.run_validator([good_file, bad_file], mode="block")
    assert result["passed"] is False
    assert result["exit_code"] == 1
    assert result["summary"]["errors"] == 1
    assert result["summary"]["files_total"] == 2
    assert result["summary"]["files_failed"] == 1
    assert result["summary"]["files_passed"] == 1


def test_run_validator_warn_mode_degrades_without_hiding_errors(good_file, bad_file):
    """warn 模式必须恒 passed=True/exit=0，但 errors 计数不能被静默清零——

    对应 D5 反例 26"禁止吞码"的设计意图：模式退化了判定结论，但底层数据
    仍如实保留，供人工事后排查，而不是让 warn 模式看起来"什么问题都没有"。
    """
    result = dlv.run_validator([good_file, bad_file], mode="warn")
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["summary"]["errors"] == 1
    assert result["summary"]["files_failed"] == 1


def test_run_validator_strict_mode_no_warnings_still_passes(good_file):
    """骨架版本 G1 无 warning 级别产出，strict 对全 PASS 场景应无影响。"""
    result = dlv.run_validator([good_file], strict=True)
    assert result["passed"] is True
    assert result["exit_code"] == 0


def test_run_validator_g10a_skipped_no_ir_counted(good_file, g10a_flow_reconvergent_file):
    """未提供 ir_files 时全部文件的 G10a 记为 not_applicable，计入汇总计数器。"""
    result = dlv.run_validator([good_file, g10a_flow_reconvergent_file])
    assert result["summary"]["g10a_skipped_no_ir"] == 2


def test_run_validator_g10a_partial_ir_only_counts_missing(good_file, g10a_flow_reconvergent_file, ir_flow_file):
    """ir_files 与 files 一一对应，只有实际传 None 的文件才计入 skipped 计数器。"""
    result = dlv.run_validator(
        [good_file, g10a_flow_reconvergent_file],
        ir_files=[None, ir_flow_file],
    )
    assert result["summary"]["g10a_skipped_no_ir"] == 1
    assert result["passed"] is False  # g10a_flow_reconvergent_file 在 flow 模式下 FLOW_RECONVERGENT


# ---------------------------------------------------------------------------
# CLI（子进程调用，覆盖 --figures-dir / --file / --report-out / 空目录 / exit code）
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(dlv.__file__).resolve()


def _run_cli(args, cwd=None):
    # 脚本内部已将 stdout/stderr reconfigure 为 UTF-8（见脚本头部 Windows 兜底），
    # 但 subprocess.run(text=True) 在 Windows 上默认按系统 ANSI 代码页（GBK）解码，
    # 会把含中文路径（如用户名"张"）的 UTF-8 字节错误拆解，产生看似合法实则损坏的
    # 转义序列，导致下游 json.loads 报 "Invalid \escape"。显式指定 encoding="utf-8"
    # 与脚本侧保持一致，而非降级为忽略中文路径这类回避测试。
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)] + args,
        capture_output=True, text=True, encoding="utf-8", cwd=cwd,
    )


def test_cli_figures_dir_exit_code_and_report(figures_dir, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--figures-dir", str(figures_dir),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 1
    assert report_out.exists()
    data = json.loads(report_out.read_text(encoding="utf-8"))
    assert data["exit_code"] == 1
    assert data["summary"]["files_total"] == 2
    assert data["summary"]["files_failed"] == 1


def test_cli_file_flag(good_file, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(good_file),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 0
    data = json.loads(report_out.read_text(encoding="utf-8"))
    assert data["summary"]["files_total"] == 1
    assert data["passed"] is True


def test_cli_file_flag_missing_file_errors(tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(tmp_path / "nonexistent.drawio"),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 1
    assert not report_out.exists()


def test_cli_empty_dir_passes(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--figures-dir", str(empty_dir),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 0
    data = json.loads(report_out.read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert "note" in data


def test_cli_warn_mode_exit_zero_despite_errors(figures_dir, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--figures-dir", str(figures_dir),
        "--mode", "warn",
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 0
    data = json.loads(report_out.read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["summary"]["errors"] == 1


def test_cli_json_flag_outputs_valid_json(good_file, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(good_file),
        "--json",
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 0
    parsed = json.loads(proc.stdout)
    assert parsed["schema_version"] == dlv.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# CLI --ir 参数（个数一致性 / 文件存在性 / mode-dispatch 生效 / 批量模式忽略）
# ---------------------------------------------------------------------------

def test_cli_ir_flag_drives_g10a_mode_dispatch(g10a_flow_reconvergent_file, ir_flow_file, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(g10a_flow_reconvergent_file),
        "--ir", str(ir_flow_file),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 1
    data = json.loads(report_out.read_text(encoding="utf-8"))
    item = data["items"][0]
    assert item["checks"]["G10a_topology"] == "fail"
    issue = next(i for i in item["issues"] if i["check"] == "G10a_topology")
    assert issue["error_code"] == "FLOW_RECONVERGENT"


def test_cli_ir_flag_omitted_is_not_applicable(g10a_flow_reconvergent_file, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(g10a_flow_reconvergent_file),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 0
    data = json.loads(report_out.read_text(encoding="utf-8"))
    assert data["items"][0]["checks"]["G10a_topology"] == "not_applicable"
    assert data["summary"]["g10a_skipped_no_ir"] == 1


def test_cli_ir_flag_count_mismatch_errors(good_file, g10a_flow_reconvergent_file, ir_flow_file, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(good_file),
        "--file", str(g10a_flow_reconvergent_file),
        "--ir", str(ir_flow_file),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 1
    assert not report_out.exists()
    assert "一一对应" in proc.stderr


def test_cli_ir_flag_missing_file_errors(g10a_flow_reconvergent_file, tmp_path):
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--file", str(g10a_flow_reconvergent_file),
        "--ir", str(tmp_path / "nonexistent.ir.json"),
        "--report-out", str(report_out),
    ])
    assert proc.returncode == 1
    assert not report_out.exists()


def test_cli_ir_flag_ignored_in_figures_dir_mode(figures_dir, ir_flow_file, tmp_path):
    """--figures-dir 批量模式下无法与 --ir 一一对应，忽略并打印 INFO 提示，不报错。"""
    report_out = tmp_path / "report.json"
    proc = _run_cli([
        "--figures-dir", str(figures_dir),
        "--ir", str(ir_flow_file),
        "--report-out", str(report_out),
    ])
    assert "--figures-dir 批量模式下无法与 --ir 一一对应" in proc.stderr
    data = json.loads(report_out.read_text(encoding="utf-8"))
    assert data["summary"]["g10a_skipped_no_ir"] == data["summary"]["files_total"]
