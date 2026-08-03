# -*- coding: utf-8 -*-
"""term_consistency_check.py 回归测试。

覆盖真实项目实测命中的 bug：
全角括号未被 base_form 提取正则识别，导致要求整段（含英文全称）逐字
重现，与 glossary 自身"首次出现需在括号内插入'，以下简称XXX'"的规则冲突。
"""
from __future__ import annotations

import term_consistency_check as tcc


def _entry(term_id, preferred_form, scope="全报告", category="原创核心概念"):
    return {
        "term_id": term_id,
        "preferred_form": preferred_form,
        "scope": scope,
        "category": category,
        "banned_forms": [],
    }


# ---------------------------------------------------------------------------
# 全角括号提取
# ---------------------------------------------------------------------------

def test_fullwidth_parens_stripped_from_base_form():
    """preferred_form 用全角括号包裹英文全称时，base_form 应只保留括号外
    的中文部分——此前只匹配半角括号，全角形式完全不生效。"""
    entries = [_entry("GL-009", "SCIF理论闭环（SCI-SCIF-SCOS-SCA-NG-SSA Theoretical Loop）")]
    # 正文只出现中文基础形式 + 括号内首次简称展开，不逐字复现英文全称本身
    body = "本报告的核心主张是SCIF理论闭环（SCI-SCIF-SCOS-SCA-NG-SSA Theoretical Loop，以下简称SCIF闭环）。"
    violations = tcc.check_preferred_form_fidelity(body, entries)
    assert violations == []


def test_fullwidth_parens_violation_when_base_form_truly_missing():
    """确认修复没有让检查失去效力——base_form 确实缺失时仍应报 FAIL。"""
    entries = [_entry("GL-009", "SCIF理论闭环（SCI-SCIF-SCOS-SCA-NG-SSA Theoretical Loop）")]
    body = "本报告未使用该核心概念。"
    violations = tcc.check_preferred_form_fidelity(body, entries)
    assert len(violations) == 1
    assert violations[0]["term_id"] == "GL-009"


def test_halfwidth_parens_still_supported():
    """半角括号的旧行为不应因本次修复而回退。"""
    entries = [_entry("GL-X", "测试概念(Test Concept)")]
    body = "正文中使用了测试概念这一提法。"
    violations = tcc.check_preferred_form_fidelity(body, entries)
    assert violations == []


# ---------------------------------------------------------------------------
# scope 字段——当前版本（2026-08-03）的 check_preferred_form_fidelity
# 尚未实现 scope 章节过滤，所有 scope 的术语均按"全报告"同等处理；
# 以下测试作为 scope 过滤功能的设计规格留底，等源模块实现对应参数后改写。
# 当前版本：scope 不做过滤，术语在任何章节缺失时均报违规（保守方向）。
# ---------------------------------------------------------------------------
