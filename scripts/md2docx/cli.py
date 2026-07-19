"""CLI 入口 — md2docx 命令行工具。"""
import sys
import os
import re
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description='Markdown → Word (.docx) 研究报告转换器\n严格遵循《研究报告格式规范 V3.0》')
    parser.add_argument('input', help='Markdown 文件路径')
    parser.add_argument('-o', '--output', default=None, help='输出 .docx 路径')
    parser.add_argument('--config', '-c', default=None, help='YAML 配置文件路径')
    parser.add_argument('--title', '-t', default=None, help='报告题名')
    parser.add_argument('--org', default=None, help='编制机构')
    parser.add_argument('--subtitle', default=None, help='副标题')
    parser.add_argument('--version', default=None, help='版本号')
    parser.add_argument('--date', default=None, help='日期')
    parser.add_argument('--images', '-i', default=None, help='图片目录')
    parser.add_argument('--dry-run', action='store_true', help='仅预处理和解析')
    parser.add_argument('--validate-only', action='store_true', help='仅验证 Markdown 格式')
    parser.add_argument('--debug', action='store_true', help='保留中间产物')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f'[ERROR] 文件不存在: {args.input}')
        sys.exit(1)

    if not args.output:
        ip = Path(args.input)
        args.output = str(Path.cwd() / ip.with_suffix('.docx').name)

    from .config import load_config
    from .preprocessor import preprocess
    from .parser import parse_markdown
    from .ir import build_ir

    cli_overrides = {'metadata': {}}
    if args.title: cli_overrides['metadata']['title'] = args.title
    if args.org: cli_overrides['metadata']['org'] = args.org
    if args.subtitle: cli_overrides['metadata']['subtitle'] = args.subtitle
    if args.version: cli_overrides['metadata']['version'] = args.version
    if args.date: cli_overrides['metadata']['date'] = args.date

    config = load_config(args.config, cli_overrides)

    # Phase 1: 预处理
    print('[1/4] 预处理 Markdown…')
    try:
        lines, metadata = preprocess(args.input, config)
    except Exception as e:
        print(f'[ERROR] 预处理失败: {e}')
        sys.exit(1)

    merged = {
        'title': metadata.get('title') or config.metadata.title,
        'subtitle': metadata.get('subtitle') or config.metadata.subtitle,
        'subtype': config.metadata.subtype,
        'org': metadata.get('org') or config.metadata.org,
        'version': metadata.get('version') or config.metadata.version,
        'date': metadata.get('date') or config.metadata.date,
        'header_short': metadata.get('header_short') or config.metadata.header_short or config.metadata.title,
    }

    clean_text = '\n'.join(lines)
    if args.debug:
        cp = args.input.replace('.md', '-cleaned.md')
        with open(cp, 'w', encoding='utf-8') as f:
            f.write(clean_text)
        print(f'  调试: → {cp}')

    # Phase 2: 解析
    print('[2/4] 解析 Markdown…')
    elements = parse_markdown(clean_text)

    if args.dry_run:
        print('\n--- Dry-run ---')
        from collections import Counter
        stats = Counter(type(e).__name__ for e in elements)
        for t, c in sorted(stats.items()):
            print(f'  {t}: {c}')
        print(f'  总元素: {len(elements)}, 行数: {len(lines)}')
        return

    # Phase 3: IR
    print('[3/4] 构建 IR…')
    ir = build_ir(elements, merged)

    if args.validate_only:
        print(f'  章节: {len(ir.body_chapters)} 章')
        print(f'  图片: {len(ir.figure_registry)} 张')
        print(f'  表格: {len(ir.table_registry)} 个')
        issues = []
        if not merged['title']:
            issues.append('[WARN] 未指定报告标题 (--title / front matter)')
        if not merged['org']:
            issues.append('[WARN] 未指定编制机构 (--org / front matter)')
        for i in issues: print(f'  {i}')
        return

    # Phase 4: 渲染
    print('[4/4] 渲染 Word 文档…')
    from .renderer.document import DocumentBuilder
    from .renderer.cover import render_cover
    from .renderer.toc import add_toc, add_figure_toc, add_table_toc
    from .renderer.headings import (HeadingNumbering, render_h1, render_h2, render_h3,
                                    render_h4, render_h5, render_front_h2, render_front_h3,
                                    render_back_h1, render_back_h2)
    from .renderer.body import render_body, render_blockquote, render_code_block, render_list_item
    from .renderer.tables import render_table
    from .renderer.images import embed_all_images
    from .renderer.helpers import remove_mark
    from .postprocessor import fix_table_captions, validate_output
    from .parser import (Heading, Paragraph, CodeBlock, BlockQuote, HorizontalRule,
                         EmptyLine, ListItem, TableElement, ImageElement)

    builder = DocumentBuilder(config)
    doc = builder.doc

    has_summary = any(
        hasattr(e, 'text') and e.text and ('摘要' in e.text or '执行摘要' in e.text)
        for e in ir.front_matter if isinstance(e, Heading)
    )
    builder.build_sections(ir, has_summary=has_summary)

    # 渲染封面
    render_cover(doc, config)

    numbering = HeadingNumbering()
    in_front = True
    in_back = False
    pending_tbl_cap = None

    all_elems = list(ir.front_matter)
    for ch_elem in ir.body_chapters:
        all_elems.append(Heading(1, ch_elem.chapter.title))
        all_elems.extend(ch_elem.elements)
    all_elems.extend(ir.back_matter)

    for elem in all_elems:
        if isinstance(elem, EmptyLine):
            continue

        if isinstance(elem, HorizontalRule):
            doc.add_page_break()
            continue

        if isinstance(elem, Heading):
            text = remove_mark(elem.text)

            if elem.level == 1:
                if '目录' in text:
                    add_toc(doc, config)
                    continue
                if any(kw in text for kw in ['参考文献', '附录', '术语表', '索引', '图表索引', '资料清单']):
                    in_back = True
                    in_front = False
                    render_back_h1(doc, text, config)
                    continue
                in_front = False
                render_h1(doc, text, numbering, config)

            elif elem.level == 2:
                if any(kw in text for kw in ['参考文献', '附录', '术语表', '索引', '图表索引', '资料清单']):
                    in_back = True
                    in_front = False
                if in_front:
                    if '目录' in text:
                        add_toc(doc, config)
                    else:
                        render_front_h2(doc, text, config)
                elif in_back:
                    render_back_h2(doc, text, config)
                else:
                    render_h2(doc, text, numbering, config)

            elif elem.level == 3:
                if in_front or in_back:
                    render_front_h3(doc, text, config)
                else:
                    render_h3(doc, text, numbering, config)

            elif elem.level == 4:
                render_h4(doc, text, config)

            elif elem.level == 5:
                render_h5(doc, text, config)

        elif isinstance(elem, Paragraph):
            tbl_m = re.match(r'^\*\*表\s*(\d+)[-−]\s*(\d+)\s+(.+?)\*\*\s*$', elem.text)
            if tbl_m:
                pending_tbl_cap = f'表{tbl_m.group(1)}-{tbl_m.group(2)}  {tbl_m.group(3)}'
                continue
            tbl_m2 = re.match(r'^表\s*\d+[-−]\s*\d+[：:]\s*(.+)', elem.text)
            if tbl_m2:
                pending_tbl_cap = elem.text
                continue
            render_body(doc, elem.text, config)

        elif isinstance(elem, CodeBlock):
            render_code_block(doc, elem.lines, config)

        elif isinstance(elem, BlockQuote):
            render_blockquote(doc, elem.lines, config)

        elif isinstance(elem, ListItem):
            render_list_item(doc, elem, config)

        elif isinstance(elem, TableElement):
            render_table(doc, elem, pending_tbl_cap, config)
            pending_tbl_cap = None

        elif isinstance(elem, ImageElement):
            pass

    # 后处理
    images_dir = args.images
    if not images_dir:
        default_figures = os.path.join(os.path.dirname(os.path.abspath(args.input)), 'figures')
        if os.path.isdir(default_figures):
            images_dir = default_figures
    if images_dir:
        count = embed_all_images(doc, ir.figure_registry, config, images_dir)
        print(f'  嵌入图片: {count} 张')

    tbl_count = fix_table_captions(doc, ir.table_registry, config)
    print(f'  处理表格: {tbl_count} 个')

    for w in validate_output(doc, ir, config):
        print(f'  {w}')

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or '.', exist_ok=True)
    doc.save(args.output)
    print(f'\n[OK] Word 文档已生成: {args.output}')
    print(f'  字体: 标题={config.fonts.heading.cjk}+{config.fonts.heading.latin} | '
          f'正文={config.fonts.body.cjk}+{config.fonts.body.latin}')
    print(f'  字号: H1={config.sizes.h1}pt H2={config.sizes.h2}pt 正文={config.sizes.body}pt')
    print(f'  页码: 摘要罗马数字 + 正文阿拉伯数字')
    print(f'  [NOTE] 请在 Word/WPS 中打开，右键目录 → "更新域"以获取页码。')


if __name__ == '__main__':
    main()
