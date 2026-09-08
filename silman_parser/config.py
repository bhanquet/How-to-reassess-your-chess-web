"""Data paths and constants.

The text source is the native EPUB (structure: H2 sections in the spine
order, see epub_ingest). Buy it legally and place it at the repo root
under INPUT_FILE. Generated JSONs are gitignored (see README).
"""


INPUT_FILE = 'How to Reassess Your Chess 4th ed - Silman.epub'

OUTPUT_FILE = 'chess-app/data/book_structure.json'

DIAGRAMS_FILE = 'chess-app/data/diagrams.json'

TOC_FILE = 'chess-app/data/toc.json'

MANUAL_OVERRIDES_FILE = 'chess-app/data/diagrams_manual_overrides.json'