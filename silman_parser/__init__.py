"""Semantic parser for "How to Reassess Your Chess" (4th Edition).

Split into modules by responsibility:
- config : paths and constants
- epub_ingest : native EPUB ingestion (H2 sections, diagrams, moves)
- san : SAN notation cleanup
- segmentation : subdivision of oversized sections
- html_render : HTML escaping helper (html_escape)
- diagram_context : diagram context in the book (moves, side)
- pgn_sources : FENs and variations from study PGNs
- overrides : manual overrides for unresolvable diagrams
- build : orchestration (main)

Re-exports the public API used by the pipeline (silman_parser.build) and the
tests.
"""

from silman_parser.config import (
    DIAGRAMS_FILE,
    INPUT_FILE,
    MANUAL_OVERRIDES_FILE,
    OUTPUT_FILE,
    TOC_FILE,
)
from silman_parser.diagram_context import (
    adjust_index_for_side_to_move,
    extract_diagram_and_page_numbers,
    extract_players_from_chapter,
    find_diagram_move_context,
    find_diagram_position,
    find_exact_match,
    find_position_with_side,
    get_diagram_side,
    get_mainline_moves,
    get_moves_after_diagram,
    get_moves_before_diagram,
    position_at,
    replay_moves,
)
from silman_parser.epub_ingest import parse_epub, parse_ncx_toc
from silman_parser.html_render import html_escape
from silman_parser.pgn_sources import (
    extract_diagram_variations,
    extract_fens_from_study_games,
    extract_study_chapters,
    extract_variation_tree,
    validate_variation_tree,
)
from silman_parser.overrides import apply_manual_overrides, load_manual_overrides
from silman_parser.san import (
    extract_san_moves,
    normalize_move_text,
    normalize_unicode_artifacts,
)
from silman_parser.segmentation import split_long_sections

# `main` is imported lazily: importing silman_parser.build at package
# import time makes `python3 -m silman_parser.build` emit
# "RuntimeWarning: 'silman_parser.build' found in sys.modules ...".
def __getattr__(name):
    if name == 'main':
        from silman_parser.build import main
        return main
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


__all__ = [
    'DIAGRAMS_FILE',
    'INPUT_FILE',
    'MANUAL_OVERRIDES_FILE',
    'OUTPUT_FILE',
    'TOC_FILE',
    'main',
    'adjust_index_for_side_to_move',
    'apply_manual_overrides',
    'extract_diagram_and_page_numbers',
    'extract_diagram_variations',
    'extract_fens_from_study_games',
    'extract_study_chapters',
    'extract_players_from_chapter',
    'extract_san_moves',
    'extract_variation_tree',
    'find_diagram_move_context',
    'find_diagram_position',
    'find_exact_match',
    'find_position_with_side',
    'get_diagram_side',
    'get_mainline_moves',
    'get_moves_after_diagram',
    'get_moves_before_diagram',
    'html_escape',
    'load_manual_overrides',
    'normalize_move_text',
    'normalize_unicode_artifacts',
    'parse_epub',
    'parse_ncx_toc',
    'position_at',
    'replay_moves',
    'split_long_sections',
    'validate_variation_tree',
]