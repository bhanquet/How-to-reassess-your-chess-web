"""Subdivision of oversized EPUB sections.

Logical sectioning is now the native EPUB structure (H2 in the spine order,
see epub_ingest): this module only keeps the subdivision of the already
built sections.
"""

def split_long_sections(sections, max_chars=12000):
    """Subdivide very long sections at natural boundaries.

    The 'continued N/M' label reflects the real number of parts emitted after
    the block-based split (not a simple theoretical ceil).

    Every section carries per-block metadata ('blocks' = list of
    {'html', 'href', 'anchor'}), provided by the EPUB ingest (epub_ingest):
    each part inherits the source hrefs and H3 anchors of the blocks it
    contains. Blocks are never split.
    """
    result = []
    for sec in sections:
        content = sec['content']
        if len(content) <= max_chars:
            result.append(sec)
            continue

        blocks = sec['blocks']
        items = blocks

        # Greedy grouping by blocks (blocks are never split: no mid-word
        # cut). Boundaries land between '\n\n' separators because the content
        # is '\n\n'.join(html) and each separator counts +2.
        parts = []
        current = []
        current_len = 0
        for item in items:
            item_len = len(item['html'])
            if current_len + item_len > max_chars and current:
                parts.append(current)
                current = []
                current_len = 0
            current.append(item)
            current_len += item_len + 2
        if current:
            parts.append(current)

        total_parts = len(parts)
        for part_num, group in enumerate(parts, start=1):
            title_suffix = f' (continued {part_num}/{total_parts})' if total_parts > 1 else ''
            hrefs = []
            anchors = []
            for item in group:
                href = item.get('href')
                if href and href not in hrefs:
                    hrefs.append(href)
                anchor = item.get('anchor')
                if anchor and anchor not in anchors:
                    anchors.append(anchor)
            result.append({
                'title': sec['title'] + title_suffix,
                'level': sec['level'],
                'original_page': sec.get('original_page', 0),
                'content': '\n\n'.join(item['html'] for item in group),
                'blocks': group,
                'source_hrefs': hrefs or sec.get('source_hrefs', []),
                'anchors': anchors,
            })

    return result