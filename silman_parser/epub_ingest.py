"""Native EPUB ingestion (sole source of the book text).

The reading order is the spine of content.opf (manifest + itemref),
NOT the alphabetical order of the text/partNNNN.html files.

Native structure used:
- sections = H2 in the spine order (Preface, Acknowledgements, Introduction,
  chapters, tests, answers, articles, indexes) ;
- H3 = subsections, rendered as <h3> in the content ;
- diagrams : <p class="diagram-number">Diagram N</p> (class variants
  diagram-number-sb / diagram-number-ns), side in
  <p class="caption1">...White/Black to move...</p>, level in
  <p class="diagram-number">[Level: ...]</p>. The images images/*.jpeg are
  ignored (the FENs come from PGN studies) ;
- game moves in <span class="bold"> : they become
  <div class="game-notation"> only if extract_san_moves finds at least one
  move AND the span contains a move number (\\d+\\. or ...).
  The <span class="bold">White to move</span> of the captions STAYS prose.
"""

import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

from silman_parser.html_render import html_escape
from silman_parser.san import extract_san_moves, normalize_unicode_artifacts

_XHTML = '{http://www.w3.org/1999/xhtml}'

# NCX namespace (EPUB 2 TOC).
_NCX = '{http://www.daisy.org/z3986/2005/ncx/}'

# H2 titles of front matter (before the first chapter): TOC level 1.
FRONT_MATTER_TITLES = ('Preface', 'Acknowledgements', 'Introduction')

# H2 titles excluded from sections (front pages / tables).
_EXCLUDED_H2_TITLES = {'Copyright', 'Contents'}

# Maximum number of diagrams in the book.
_MAX_DIAGRAM_NUM = 432

# Standalone diagram label in a <p class="diagram-number*">:
# "Diagram 20", "Diagram 39a" (sub-diagram), "Diagram 73 (repeat)".
_DIAGRAM_LABEL_RE = re.compile(
    r'^Diagram\s+(\d+)(?:[a-z])?(?:\s*\([^)]*\))?\s*$', re.IGNORECASE)

# Semantic enrichment patterns.
_LIST_ITEM_RE = re.compile(r'^(»|•)\s*(.*)$', re.DOTALL)
_CALLOUT_MARKER_RE = re.compile(
    r'^<p(?:\s+[^>]*)?>\s*(in a nutshell|philosophy|rule)\s*</p>$',
    re.IGNORECASE)
_QUOTE_RE = re.compile(
    r'^(?P<open>["\u201c\u2018])(?P<body>.+?)(?P<close>["\u201d\u2019])\s*'
    r'(?P<dash>\u2014|\u2013|-)\s*'
    r'(?P<attribution>[^<\s].*?)\s*$',
    re.DOTALL)
_CALLOUT_KINDS = {
    'in a nutshell': 'nutshell',
    'philosophy': 'philosophy',
    'rule': 'rule',
}
_CALLOUT_TITLES = {
    'nutshell': 'In a Nutshell',
    'philosophy': 'Philosophy',
    'rule': 'Rule',
}

# Diagram label embedded in prose (end of a moves paragraph,
# e.g. "... 11.Qd3 a5 - Diagram 45"). Rejected if preceded by a prose
# cross-reference word (see/in/of/from/cf.).
_EMBEDDED_DIAGRAM_RE = re.compile(r'Diagram\s+(\d+)', re.IGNORECASE)
_DIAGRAM_CROSSREF_WORD_RE = re.compile(r'(?i)(?:see|in|of|from|cf\.?)\s+$')

# Move number inside a bold span (1., 1..., 1...) or "..." alone.
_MOVE_NUMBER_RE = re.compile(r'\d+\.|\.\.\.|\u2026')


def _local(tag):
    """Local name of an ElementTree tag (with or without namespace)."""
    if not isinstance(tag, str):
        return ''
    if '}' in tag:
        return tag.rsplit('}', 1)[1]
    return tag


def read_spine_order(epub_path):
    """Return the list of XHTML files in the spine reading order.

    Reads META-INF/container.xml to locate content.opf, then maps the
    manifest (id -> href) with the spine itemrefs.
    """
    with zipfile.ZipFile(epub_path) as zf:
        container = zf.read('META-INF/container.xml').decode('utf-8')
        m = re.search(r'full-path="([^"]+\.opf)"', container)
        if not m:
            raise ValueError('content.opf not found in META-INF/container.xml')
        opf_path = m.group(1)
        opf = zf.read(opf_path).decode('utf-8')
        manifest = dict(re.findall(r'<item\s+id="([^"]+)"\s+href="([^"]+)"', opf))
        spine = re.search(r'<spine[^>]*>(.*?)</spine>', opf, re.S)
        if not spine:
            raise ValueError('spine missing from content.opf')
        idrefs = re.findall(r'<itemref[^>]*idref="([^"]+)"', spine.group(1))
        base = posixpath.dirname(opf_path)
        hrefs = []
        for rid in idrefs:
            href = manifest.get(rid)
            if href is None:
                continue
            if base and not href.startswith(base):
                href = posixpath.join(base, href)
            hrefs.append(href)
    return hrefs


def parse_ncx_toc(epub_path):
    """Parse the native EPUB TOC (toc.ncx navMap) into a tree.

    Returns a list of nodes {'title', 'src', 'anchor', 'children'}:
    - 'title' : navLabel text (as published, hierarchy and order preserved) ;
    - 'src'   : content src of the navPoint ("text/partXXXX.html" or
      "text/partXXXX.html#_idParaDest-N") ;
    - 'anchor': fragment id of the src (_idParaDest-N), or None ;
    - 'children': nested navPoints (recursive).

    The 166 navPoints of the EPUB form: Title Page (children Copyright /
    Contents / Preface / Acknowledgements / Introduction), Parts One to Nine
    (chapters + sub-chapters), Answers to Tests and the Appendix.
    """
    with zipfile.ZipFile(epub_path) as zf:
        content = zf.read('toc.ncx').decode('utf-8')
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f'toc.ncx: XML parse error: {exc}') from exc

    def parse_point(np):
        label = np.find(_NCX + 'navLabel')
        title = _itertext(label) if label is not None else ''
        content_el = np.find(_NCX + 'content')
        src = content_el.get('src', '') if content_el is not None else ''
        fragment = src.rsplit('#', 1)[1] if '#' in src else None
        return {
            'title': ' '.join(title.split()),
            'src': src,
            'anchor': fragment,
            'children': [parse_point(c) for c in np.findall(_NCX + 'navPoint')],
        }

    nav_map = root.find(_NCX + 'navMap')
    if nav_map is None:
        raise ValueError('toc.ncx: <navMap> not found')
    return [parse_point(np) for np in nav_map.findall(_NCX + 'navPoint')]


def normalize_notation(text):
    """Normalize the notation for display in <div class="game-notation">.

    Keeps the move numbers and annotations, fixes the EPUB unicode
    artifacts (shared normalize_unicode_artifacts).
    """
    text = normalize_unicode_artifacts(text)
    # Space after "..." ("1...Rb8" -> "1... Rb8") then strip the trailing
    # " - " ("... 11.Qd3 a5 - Diagram 45").
    text = re.sub(r'\.\.\.\s*', '... ', text)
    text = re.sub(r'\s*-\s*$', '', text)
    return ' '.join(text.split())


def _text_is_game_notation(text):
    """A <span class="bold"> becomes game-notation if SAN moves + number.

    Counter-example: "<span class=\"bold\">White to move</span>" of the
    captions contains neither a move number nor a SAN move -> stays prose.
    """
    norm = text.replace('\u2026', '...')
    if not _MOVE_NUMBER_RE.search(norm):
        return False
    return bool(extract_san_moves(norm))


def _itertext(el):
    """Text of all descendants of an element (with cleanup)."""
    return ' '.join(''.join(el.itertext()).split())


def _caption_side(text):
    """Side (white/black) read in a <p class="caption1">, else None."""
    if re.search(r'\bWhite\s+to\s+move\b', text, re.IGNORECASE):
        return 'white'
    if re.search(r'\bBlack\s+to\s+move\b', text, re.IGNORECASE):
        return 'black'
    return None


def _level_from_text(text):
    """Level read in a <p class="diagram-number">[Level: ...]</p>."""
    m = re.search(r'\[Level:\s*([^\]]+)\]', text)
    if m:
        return m.group(1).strip()
    return None


def _split_diagram_labels(text):
    """Split a paragraph text on embedded 'Diagram N' labels.

    Returns a list of tuples ('text'|'diagram', value). Prose references
    ("see Diagram 5 in Chapter 2", "the position in diagram 36") stay text.
    """
    segments = []
    pos = 0
    for m in _EMBEDDED_DIAGRAM_RE.finditer(text):
        num = int(m.group(1))
        if num < 1 or num > _MAX_DIAGRAM_NUM:
            continue
        if _DIAGRAM_CROSSREF_WORD_RE.search(text[:m.start()]):
            continue
        if m.start() > pos:
            segments.append(('text', text[pos:m.start()]))
        segments.append(('diagram', str(num)))
        pos = m.end()
    if pos < len(text):
        segments.append(('text', text[pos:]))
    return segments or [('text', text)]


def _paragraph_contains_game_notation(el):
    """True if the paragraph contains a <span class="bold"> of moves.

    The embedded 'Diagram N' labels only become divs in moves paragraphs
    (end of game line in the answers): prose references ("see diagram 73",
    "(diagram 108)", "step back to diagram 242") stay text.
    """
    for node in el.iter():
        if _local(node.tag) == 'span':
            classes = node.get('class', '').split()
            if 'bold' in classes and _text_is_game_notation(_itertext(node)):
                return True
    return False


def _paragraph_blocks(el):
    """Split a <p> (or equivalent element) into output blocks.

    Returns a list of tuples:
    - ('p', prose_text) ;
    - ('notation', moves_text) for <span class="bold"> of moves ;
    - ('diagram', number) for 'Diagram N' labels (standalone or embedded at
      the end of a moves line in the answers).
    """
    has_notation = _paragraph_contains_game_notation(el)
    parts = []

    def handle(node):
        tag = _local(node.tag)
        if tag == 'span':
            classes = node.get('class', '').split()
            text = _itertext(node)
            if 'bold' in classes and _text_is_game_notation(text):
                parts.append(('notation', normalize_notation(text)))
            else:
                parts.append(('text', text))
        elif tag == 'br':
            parts.append(('text', ' '))
        elif tag == 'img':
            pass
        else:
            # Link, emphasis, or inline container: recurse.
            for child in node:
                handle(child)
        if node.tail:
            parts.append(('text', node.tail))

    if el.text:
        parts.append(('text', el.text))
    for child in el:
        handle(child)

    blocks = []
    text_buf = []

    def flush_text():
        joined = ' '.join(''.join(text_buf).split())
        text_buf.clear()
        if joined:
            blocks.append(('p', html_escape(joined)))

    for kind, value in parts:
        if kind == 'notation':
            flush_text()
            if value:
                blocks.append(('notation', value))
        elif has_notation:
            for seg_kind, seg_val in _split_diagram_labels(value):
                if seg_kind == 'diagram':
                    flush_text()
                    blocks.append(('diagram', seg_val))
                else:
                    text_buf.append(seg_val)
        else:
            text_buf.append(value)
    flush_text()
    return blocks


def _split_p_html(html):
    """Return (inner_text, anchor_id) for a <p> or <p id=\"...\"> block."""
    m = re.match(r'<p(?:\s+[^>]*)?>(.*?)</p>\s*$', html, re.DOTALL)
    if not m:
        return None, None
    id_m = re.search(r'\sid="([^"]+)"', html)
    return m.group(1), (id_m.group(1) if id_m else None)


def _callout_marker_kind(html):
    """Return canonical callout kind if the <p> is a marker, else None."""
    m = _CALLOUT_MARKER_RE.match(html.strip())
    if m:
        return _CALLOUT_KINDS.get(m.group(1).lower())
    return None


def _list_item_tuple(html):
    """Return (marker, text, anchor) if the <p> is a list item, else None."""
    text, anchor = _split_p_html(html)
    if text is None:
        return None
    m = _LIST_ITEM_RE.match(text)
    if not m:
        return None
    return m.group(1), m.group(2), anchor


def _build_callout_html(kind, title, body_items):
    """Build <aside class="callout callout-{kind}"> with title + body <p>s.

    body_items is a list of (inner_html, anchor_id) tuples.
    """
    body = ''.join(
        f'<p id="{anchor}">{text}</p>' if anchor else f'<p>{text}</p>'
        for text, anchor in body_items
    )
    aside_anchor = ''
    for _, anchor in body_items:
        if anchor:
            aside_anchor = f' id="{anchor}"'
            break
    return (
        f'<aside class="callout callout-{kind}"{aside_anchor}>'
        f'<h4 class="callout-title">{html_escape(title)}</h4>'
        f'<div class="callout-body">{body}</div>'
        '</aside>'
    )


def _build_list_html(items):
    """Build <ul class="book-list"> from list item tuples.

    items: list of (marker, inner_html, anchor_id). '»' starts a top-level
    item; following '•' items are nested under the preceding '»' item.
    """
    if not items:
        return ''
    parts = ['<ul class="book-list">']
    i = 0
    while i < len(items):
        marker, text, anchor = items[i]
        if marker == '»':
            j = i + 1
            while j < len(items) and items[j][0] == '•':
                j += 1
            sub_items = items[i + 1:j]
            id_attr = f' id="{anchor}"' if anchor else ''
            if sub_items:
                parts.append(f'<li{id_attr}>{text}'
                             '<ul class="book-list book-list-sub">')
                for _, sub_text, sub_anchor in sub_items:
                    sub_id = f' id="{sub_anchor}"' if sub_anchor else ''
                    parts.append(f'<li{sub_id}>{sub_text}</li>')
                parts.append('</ul></li>')
            else:
                parts.append(f'<li{id_attr}>{text}</li>')
            i = j
        else:
            # A sub-item without a preceding main item is rendered top-level.
            id_attr = f' id="{anchor}"' if anchor else ''
            parts.append(f'<li{id_attr}>{text}</li>')
            i += 1
    parts.append('</ul>')
    return ''.join(parts)


def _build_blockquote_html(text, anchor):
    """Build <blockquote class="book-quote"> if text matches quote — author."""
    m = _QUOTE_RE.match(text)
    if not m:
        return None
    body = m.group('body')
    attribution = m.group('attribution')
    open_q = m.group('open')
    close_q = m.group('close')
    dash = m.group('dash')
    id_attr = f' id="{anchor}"' if anchor else ''
    return (
        f'<blockquote class="book-quote"{id_attr}>'
        f'<p>{open_q}{body}{close_q}</p>'
        f'<cite>{dash}{attribution}</cite>'
        '</blockquote>'
    )


def _enrich_content_blocks(blocks):
    """Transform prose blocks into semantic HTML: callouts, lists, blockquotes."""
    # Pass 1: callout markers consume the immediately following paragraph.
    enriched = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        kind = _callout_marker_kind(b.get('html', ''))
        if kind is not None:
            body_items = []
            i += 1
            if i < len(blocks):
                text, anchor = _split_p_html(blocks[i].get('html', ''))
                if text is not None:
                    body_items.append((text, anchor))
                    i += 1
            title = _CALLOUT_TITLES.get(kind, kind.title())
            html = _build_callout_html(kind, title, body_items)
            enriched.append({
                'html': html,
                'href': b.get('href'),
                'anchor': b.get('anchor'),
            })
            continue
        enriched.append(b)
        i += 1

    # Pass 2: lists and blockquotes.
    result = []
    i = 0
    while i < len(enriched):
        b = enriched[i]
        html = b.get('html', '')
        if html.startswith('<p'):
            item = _list_item_tuple(html)
            if item is not None:
                items = [item]
                j = i + 1
                while j < len(enriched):
                    next_html = enriched[j].get('html', '')
                    if not next_html.startswith('<p'):
                        break
                    next_item = _list_item_tuple(next_html)
                    if next_item is None:
                        break
                    items.append(next_item)
                    j += 1
                result.append({
                    'html': _build_list_html(items),
                    'href': b.get('href'),
                    'anchor': b.get('anchor'),
                })
                i = j
                continue

            text, anchor = _split_p_html(html)
            if text is not None:
                bq = _build_blockquote_html(text, anchor)
                if bq is not None:
                    result.append({
                        'html': bq,
                        'href': b.get('href'),
                        'anchor': b.get('anchor'),
                    })
                    i += 1
                    continue
        result.append(b)
        i += 1
    return result


def _diagram_label_num(el):
    """Diagram number if the <p> is a standalone label, else None.

    ("Diagram 20", "Diagram 39a", "Diagram 73 (repeat)") in a class
    diagram-number*/diagram-number-sb/diagram-number-ns.
    """
    classes = el.get('class', '').split()
    if not any(c.startswith('diagram-number') for c in classes):
        return None
    text = _itertext(el)
    m = _DIAGRAM_LABEL_RE.match(text)
    if m:
        return m.group(1)
    return None


def parse_epub(epub_path):
    """Parse the full EPUB (spine order).

    Returns:
    - 'sections' : list of {'title', 'level', 'content', 'blocks',
      'source_hrefs', 'anchors'} (one per H2), the content being final HTML
      with blocks joined by '\\n\\n' ; 'blocks' carries per-block
      {'html', 'href', 'anchor'}, 'source_hrefs' the ordered unique hrefs of
      the source files of the section blocks, 'anchors' the H3 ids in order ;
    - 'diagrams' : {num: [{'number','side','level','line','context'}]} ;
    - 'toc' : list of {'title', 'level'} of the H2 sections (flat, kept for
      backward compatibility; the hierarchical TOC comes from
      parse_ncx_toc()).
    """
    hrefs = read_spine_order(epub_path)
    # Uniform 4-tuples: ('h2'|'h3', title, href, node_id_or_None) for
    # headings, ('p'|'notation'|'diagram', value, href, node_id_or_None)
    # for content blocks (node_id set when an h4/h5/h6 heading id must be
    # preserved as a paragraph anchor for the NCX TOC).
    records = []
    with zipfile.ZipFile(epub_path) as zf:
        for href in hrefs:
            if not href.endswith(('.html', '.xhtml')):
                continue
            try:
                root = ET.fromstring(zf.read(href))
            except (KeyError, ET.ParseError):
                continue
            body = root.find(_XHTML + 'body')
            if body is None:
                continue

            # Part division pages (<h1 class="part">) and front pages:
            # no section content.
            h1s = body.findall('.//' + _XHTML + 'h1')
            if any(_local(h.get('class', '')).startswith('part') for h in h1s):
                continue
            h2s = body.findall('.//' + _XHTML + 'h2')
            if any(_itertext(h) in _EXCLUDED_H2_TITLES for h in h2s):
                continue

            for el in body.iter():
                tag = _local(el.tag)
                if tag == 'h2':
                    records.append(('h2', _itertext(el), href, el.get('id')))
                elif tag == 'h3':
                    title = _itertext(el)
                    if title:
                        records.append(('h3', title, href, el.get('id')))
                elif tag == 'p':
                    label_num = _diagram_label_num(el)
                    if label_num is not None:
                        records.append(('diagram', label_num, href, None))
                    else:
                        for blk in _paragraph_blocks(el):
                            records.append((blk[0], blk[1], href, None))
                elif tag in ('h4', 'h5', 'h6'):
                    # Paragraph headers (article, para-title...): prose.
                    # The source id (e.g. _idParaDest-36 on <h5
                    # class="sub-chapter-l">) is kept on the first emitted
                    # block so NCX anchors can scroll to it.
                    node_id = el.get('id')
                    for i, blk in enumerate(_paragraph_blocks(el)):
                        records.append((blk[0], blk[1], href,
                                        node_id if i == 0 else None))

    # --- Sections: one per H2, with TOC level ---
    h2_titles = [rec[1] for rec in records if rec[0] == 'h2']
    front_count = 0
    while front_count < len(h2_titles) and h2_titles[front_count] in FRONT_MATTER_TITLES:
        front_count += 1

    sections = []
    current = None
    h2_index = 0
    for rec in records:
        kind, value, href, node_id = rec
        if kind == 'h2':
            level = 1 if (h2_index < front_count or value.startswith('Part ')) else 2
            h2_index += 1
            current = {
                'title': value,
                'level': level,
                'blocks': [],
                'source_hrefs': [href] if href else [],
                'anchors': [],
            }
            sections.append(current)
        elif current is not None:
            if href and href not in current['source_hrefs']:
                current['source_hrefs'].append(href)
            if kind == 'h3':
                if node_id:
                    current['anchors'].append(node_id)
                    current['blocks'].append({
                        'html': f'<h3 id="{html_escape(node_id)}">{html_escape(value)}</h3>',
                        'href': href,
                        'anchor': node_id,
                    })
                else:
                    current['blocks'].append({
                        'html': f'<h3>{html_escape(value)}</h3>',
                        'href': href,
                        'anchor': None,
                    })
            elif kind == 'p':
                html = f'<p>{value}</p>'
                if node_id:
                    # Heading-derived paragraph preserving its NCX anchor.
                    html = f'<p id="{html_escape(node_id)}">{value}</p>'
                current['blocks'].append({'html': html, 'href': href,
                                          'anchor': node_id})
            elif kind == 'notation':
                current['blocks'].append({
                    'html': f'<div class="game-notation">{value}</div>',
                    'href': href,
                    'anchor': None,
                })
            else:  # diagram
                current['blocks'].append({
                    'html': f'<div class="diagram-inline" data-diagram="{value}"></div>',
                    'href': href,
                    'anchor': None,
                })

    for sec in sections:
        sec['blocks'] = _enrich_content_blocks(sec['blocks'])
        sec['content'] = '\n\n'.join(b['html'] for b in sec['blocks'])

    # --- Diagrams: entries with side/level/context ---
    diagrams = {}
    for idx, rec in enumerate(records):
        if rec[0] != 'diagram':
            continue
        value = rec[1]
        entry = {
            'number': value,
            'side': _nearest_side(records, idx),
            'level': _nearest_level(records, idx),
            'line': idx,
            'context': _following_prose(records, idx, 200),
        }
        diagrams.setdefault(value, []).append(entry)

    toc = []
    for i, title in enumerate(h2_titles):
        level = 1 if (i < front_count or title.startswith('Part ')) else 2
        toc.append({'title': title, 'level': level})
    return {'sections': sections, 'diagrams': diagrams, 'toc': toc}


def _nearest_side(records, idx, window=60):
    """Side of the <p class="caption1"> closest to the diagram.

    First looks for the first caption1 AFTER the diagram (up to the next
    diagram); otherwise the last caption1 BEFORE the diagram (up to the
    previous diagram). The side is only used for entry metadata: the side
    used by the FEN matching (get_diagram_side) is re-read from the HTML
    content, which keeps the caption text.
    """
    side = None
    # First: captions after the diagram, up to the next diagram.
    for j in range(idx + 1, min(len(records), idx + 1 + window)):
        kind, value = records[j][0], records[j][1]
        if kind == 'diagram':
            break
        if kind == 'p':
            s = _caption_side(value)
            if s:
                return s
    # Then: captions before the diagram, up to the previous diagram.
    for j in range(idx - 1, max(-1, idx - 1 - window), -1):
        kind, value = records[j][0], records[j][1]
        if kind == 'diagram':
            break
        if kind == 'p':
            s = _caption_side(value)
            if s:
                side = s
    return side


def _nearest_level(records, idx, window=30):
    """Closest [Level: ...] to the diagram (searches forward)."""
    for j in range(idx + 1, min(len(records), idx + 1 + window)):
        kind, value = records[j][0], records[j][1]
        if kind == 'diagram':
            break
        if kind == 'p':
            lvl = _level_from_text(value)
            if lvl:
                return lvl
    return None


def _following_prose(records, idx, limit):
    """First 200 characters of the prose following the diagram."""
    out = []
    length = 0
    for j in range(idx + 1, len(records)):
        kind, value = records[j][0], records[j][1]
        if kind == 'diagram':
            break
        if kind == 'p':
            text = re.sub(r'\s+', ' ', value)
            take = limit - length
            if take <= 0:
                break
            out.append(text[:take])
            length += len(text)
            if length >= limit:
                break
    return ' '.join(out)[:limit]