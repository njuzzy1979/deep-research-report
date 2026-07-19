"""脚注支持 — 每章独立编号。P1 实现。"""
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def render_footnote_ref(para, fn_id, config):
    """在段落中插入脚注引用标记。"""
    fonts = config.fonts
    sizes = config.sizes

    r = para.add_run()
    rPr = r._element.get_or_add_rPr()
    vertAlign = OxmlElement('w:vertAlign')
    vertAlign.set(qn('w:val'), 'superscript')
    rPr.append(vertAlign)
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:eastAsia'), fonts.body.cjk)
    rFonts.set(qn('w:ascii'), fonts.body.latin)
    rPr.insert(0, rFonts)
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), str(int(sizes.footnote * 2)))
    rPr.append(sz)
    fn_ref = OxmlElement('w:footnoteReference')
    fn_ref.set(qn('w:id'), str(fn_id))
    r._element.append(fn_ref)


def build_footnotes_part(doc, footnotes, config):
    """构建文档的脚注部分。"""
    try:
        fp = doc.part.footnotes_part
    except Exception:
        return
    if not footnotes or not fp:
        return
    fn_elem = fp.element
    for fn in list(fn_elem):
        ft = fn.get(qn('w:type'))
        if ft not in ('separator', 'continuationSeparator'):
            fn_elem.remove(fn)
    for fd in footnotes:
        fe = OxmlElement('w:footnote')
        fe.set(qn('w:id'), str(fd['id']))
        p = OxmlElement('w:p')
        pPr = OxmlElement('w:pPr')
        ps = OxmlElement('w:pStyle')
        ps.set(qn('w:val'), 'FootnoteText')
        pPr.append(ps)
        p.append(pPr)
        r_ref = OxmlElement('w:r')
        rPr_r = OxmlElement('w:rPr')
        va = OxmlElement('w:vertAlign')
        va.set(qn('w:val'), 'superscript')
        rPr_r.append(va)
        r_ref.append(rPr_r)
        r_ref.append(OxmlElement('w:footnoteRef'))
        p.append(r_ref)
        rs = OxmlElement('w:r')
        ts = OxmlElement('w:t')
        ts.set(qn('xml:space'), 'preserve')
        ts.text = ' '
        rs.append(ts)
        p.append(rs)
        rt = OxmlElement('w:r')
        t = OxmlElement('w:t')
        t.set(qn('xml:space'), 'preserve')
        t.text = fd['text']
        rt.append(t)
        p.append(rt)
        fe.append(p)
        fn_elem.append(fe)
