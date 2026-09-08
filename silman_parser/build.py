"""Orchestration of the full pipeline (entry point).

Source: native EPUB (see epub_ingest). FENs and variations always come from
study PGNs (pgn_studies/).
"""

import json
import os
import re
import sys
import zipfile

from silman_parser.config import DIAGRAMS_FILE, INPUT_FILE, OUTPUT_FILE, TOC_FILE
from silman_parser.epub_ingest import parse_epub, parse_ncx_toc
from silman_parser.pgn_sources import (
    apply_pgn_pins,
    extract_diagram_variations,
    extract_fens_from_study_games,
    extract_study_chapters,
)
from silman_parser.segmentation import split_long_sections


def _write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_anchor_map(sections):
    """id="..." in the final section content -> first section_num holding it."""
    anchor_map = {}
    for sec in sections:
        for m in re.finditer(r'id="([^"]+)"', sec['content']):
            anchor_map.setdefault(m.group(1), sec['section_num'])
    return anchor_map


def _build_file_map(sections):
    """source file (spine href) -> first section_num containing a block of it."""
    file_map = {}
    for sec in sections:
        for href in sec.get('source_hrefs', []):
            file_map.setdefault(href, sec['section_num'])
    return file_map


def _resolve_ncx_nodes(nodes, anchor_map, file_map):
    """Resolve each NCX node to a section number.

    Resolution per node: anchor -> section via the anchor map (with a
    fallback to the file map), otherwise via the file map (first section of
    the source file). Unresolvable nodes get section=None.
    """
    resolved = []
    for node in nodes:
        anchor = node.get('anchor')
        src_file = node['src'].split('#')[0]
        section = anchor_map.get(anchor) if anchor else None
        if section is None:
            section = file_map.get(src_file)
        resolved.append({
            'title': node['title'],
            'src': node['src'],
            'section': section,
            'anchor': anchor,
            'children': _resolve_ncx_nodes(node.get('children', []),
                                           anchor_map, file_map),
        })
    return resolved


def main():
    if not os.path.isfile(INPUT_FILE):
        print(f"Error: EPUB not found: {INPUT_FILE!r}", file=sys.stderr)
        print(file=sys.stderr)
        print("The book text is not included in this repository (copyright).", file=sys.stderr)
        print("To generate the data:", file=sys.stderr)
        print("  1. Buy the EPUB legally.", file=sys.stderr)
        print(f"  2. Place it at the repository root as {INPUT_FILE!r}.", file=sys.stderr)
        print("  3. Run this command again from the repository root:", file=sys.stderr)
        print("       python3 -m silman_parser.build", file=sys.stderr)
        raise SystemExit(1)

    print(f"Analyzing {INPUT_FILE}...")

    try:
        parsed = parse_epub(INPUT_FILE)
    except zipfile.BadZipFile:
        print(f"Error: {INPUT_FILE!r} is not a valid EPUB file.", file=sys.stderr)
        print("Make sure it is the original, unmodified EPUB (4th edition).", file=sys.stderr)
        raise SystemExit(1)
    sections = split_long_sections(parsed['sections'], max_chars=15000)
    print(f"Logical sections: {len(sections)}")

    html_sections = [
        {
            'section_num': i,
            'title': sec['title'],
            'level': sec['level'],
            'original_page': 0,
            'content': sec['content'].strip(),
            'source_hrefs': sec.get('source_hrefs', []),
            'anchors': sec.get('anchors', []),
        }
        for i, sec in enumerate(sections)
        if sec['content'].strip()
    ]

    book = {
        'title': 'How to Reassess Your Chess',
        'author': 'Jeremy Silman',
        'edition': '4th Edition',
        'type': 'sections',
        'total_sections': len(html_sections),
        'sections': html_sections,
    }

    _write_json(OUTPUT_FILE, book)
    print(f"Structure saved to {OUTPUT_FILE}")

    # Diagrams: native EPUB entries (number, side, level, context).
    diagrams_flat = {
        num: {
            'number': num,
            'occurrences': len(entries),
            'fen': None,
            'initial_fen': None,
            'moves': None,
            'diagram_move_index': 0,
            'variations': [],
            'entries': entries,
        }
        for num, entries in parsed['diagrams'].items()
    }

    study_chapters = extract_study_chapters()

    # Pass 0: study chapters with an explicit starting FEN.
    for ch in study_chapters:
        for num in ch['nums']:
            data = diagrams_flat.get(str(num))
            if data is None or not ch['fen']:
                continue
            data['fen'] = ch['fen']
            data['initial_fen'] = ch['fen']
            data['moves'] = ch['moves']
            data['diagram_move_index'] = 0
            data['matched_by'] = 'chapter_fen'

    # PGN pins: diagrams explicitly pinned to a ply of their own chapter
    # mainline (via [DiagramNumber]/[DiagramPly]).
    n_pins = apply_pgn_pins(diagrams_flat, study_chapters)
    if n_pins:
        print(f"PGN pins applied: {n_pins}")

    # Passes 1-2: reconstruction from the complete games (moves + side).
    extract_fens_from_study_games(book, diagrams_flat, study_chapters)

    # RAV variations of the PGN chapters (branching at/after the diagram).
    n_var = extract_diagram_variations(diagrams_flat, study_chapters)
    if n_var:
        print(f"Diagrams with variations: {n_var}")

    # Native NCX TOC: resolve the 166 hierarchical navPoints to sections.
    ncx_nodes = parse_ncx_toc(INPUT_FILE)
    toc_tree = _resolve_ncx_nodes(ncx_nodes,
                                  _build_anchor_map(html_sections),
                                  _build_file_map(html_sections))

    _write_json(DIAGRAMS_FILE, diagrams_flat)
    _write_json(TOC_FILE, toc_tree)

    # Statistics: grouping by match source
    sources = {}
    for d in diagrams_flat.values():
        src = d.get('matched_by') or 'unmatched'
        sources[src] = sources.get(src, 0) + 1
    print(f"- FEN sources: {sources}")

    # Truncated variations
    n_truncated = sum(1 for d in diagrams_flat.values()
                      if d.get('variations') and d.get('_var_truncated'))
    if n_truncated:
        print(f"- Diagrams with truncated variations: {n_truncated}")

    n_fen = sum(1 for d in diagrams_flat.values() if d.get('fen'))
    print(f"- Diagrams with FEN: {n_fen}/{len(diagrams_flat)}")

    print(f"\nStatistics:")
    print(f"- Sections: {len(html_sections)}")
    print(f"- Unique diagrams: {len(diagrams_flat)}")
    print(f"- Diagram occurrences: {sum(d['occurrences'] for d in diagrams_flat.values())}")
    print(f"- TOC entries: {len(toc_tree)} (NCX navPoints)")
    print("\nProcessing complete!")


if __name__ == "__main__":
    main()