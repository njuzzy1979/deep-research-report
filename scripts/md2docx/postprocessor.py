"""后处理：表题注修复、图片嵌入、孤立引用清理、完整性验证。"""
import re
from docx.oxml.ns import qn
from .renderer.helpers import get_para_text, has_image, get_table_header_text, make_xml_para


def fix_table_captions(doc, table_registry=None, config=None):
    W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    tbl_tag = '{' + W_NS + '}tbl'
    p_tag = '{' + W_NS + '}p'

    body = list(doc.element.body)
    new = []
    tbl_count = 0

    for child in body:
        tag = child.tag
        if tag == tbl_tag:
            tbl_count += 1
            hdr = get_table_header_text(child)
            caption = None
            if table_registry:
                for tbl_id, tbl_meta in table_registry.items():
                    if tbl_meta.header_text and tbl_meta.header_text in hdr:
                        caption = f'表{tbl_meta.id}  {tbl_meta.caption}'
                        break
            if not caption:
                caption = _fallback_match(hdr, table_registry)
            if not caption:
                caption = '表'

            cap_cjk = '宋体'
            cap_latin = 'Times New Roman'
            cap_size = 9
            cap_color = '555555'
            if config:
                cap_cjk = config.fonts.body.cjk
                cap_latin = config.fonts.body.latin
                cap_size = config.sizes.caption
                cap_color = config.colors.secondary

            new.append(make_xml_para(caption, cjk=cap_cjk, latin=cap_latin,
                                     size_pt=cap_size, color_hex=cap_color))
            new.append(child)
            continue

        if tag == p_tag and has_image(child):
            new.append(child)
            continue

        if tag == p_tag and re.match(r'图\s*\d+[-−]\s*\d+', get_para_text(child)):
            prev_img = (new and new[-1].tag == p_tag and has_image(new[-1]))
            if prev_img:
                new.append(child)
            continue

        t = get_para_text(child) if tag == p_tag else ''
        if tag == p_tag and t:
            if re.match(r'(●\s*)?图\s*\d+[-−]\s*\d+[：:]', t):
                prev_has_img = (new and new[-1].tag == p_tag and has_image(new[-1]))
                if not prev_has_img:
                    continue
            if re.match(r'(●\s*)?表\s*\d+[-−]\s*\d+[：:]', t):
                continue
        new.append(child)

    for c in list(doc.element.body):
        doc.element.body.remove(c)
    for c in new:
        doc.element.body.append(c)
    return tbl_count


def _fallback_match(header_text, table_registry):
    if not table_registry or not header_text:
        return None
    best_score = 0
    best_caption = None
    hdr_words = set(header_text)
    for tbl_id, tbl_meta in table_registry.items():
        if not tbl_meta.header_text:
            continue
        tbl_words = set(tbl_meta.header_text)
        if not hdr_words or not tbl_words:
            continue
        intersection = hdr_words & tbl_words
        union = hdr_words | tbl_words
        score = len(intersection) / len(union) if union else 0
        if score > best_score and score > 0.3:
            best_score = score
            best_caption = f'表{tbl_meta.id}  {tbl_meta.caption}'
    return best_caption


def validate_output(doc, ir, config=None):
    warnings = []
    body_text = '\n'.join(p.text for p in doc.paragraphs)
    for fig_id, fig_meta in ir.figure_registry.items():
        if f'图{fig_id}' not in body_text and fig_id not in body_text:
            warnings.append(f'[WARN] 图{fig_id} ({fig_meta.caption}) 未在文档中找到')
    for tbl_id, tbl_meta in ir.table_registry.items():
        if f'表{tbl_id}' not in body_text and tbl_id not in body_text:
            warnings.append(f'[WARN] 表{tbl_id} ({tbl_meta.caption}) 未在文档中找到')
    if ir.body_chapters:
        expected_ch = 1
        for ch_elem in ir.body_chapters:
            if ch_elem.chapter.number != expected_ch:
                warnings.append(
                    f'[WARN] 章节编号不连续: 期望第{expected_ch}章，实际第{ch_elem.chapter.number}章')
            expected_ch += 1
    return warnings
