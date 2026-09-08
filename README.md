# How to Reassess Your Chess — Interactive Study App

Interactive web app for personal study of *How to Reassess Your Chess* (4th Edition) by Jeremy Silman.
The book text is organized into logical sections (one per EPUB H2, subdivided when long) with 432 interactive diagrams.

> **Copyright:** the public repo contains **no book text**. Buy the EPUB legally,
> place it at the repo root, then generate the data locally (see below).

## Layout

```
.
├── How to Reassess Your Chess 4th ed - Silman.epub  # Native EPUB — sole source of the text
│                        # NOT in git: buy it legally and place it here (exact filename,
│                        # see silman_parser/config.py:INPUT_FILE)
├── pgn_studies/                      # PGN studies (PGNs) — source of FENs and full games
├── silman_parser/                     # Parser package (one module per concern)
│   ├── config.py                      # Paths
│   ├── epub_ingest.py                 # EPUB ingestion (spine order, H2 sections, diagrams)
│   ├── san.py / segmentation.py
│   ├── html_render.py / diagram_context.py / pgn_sources.py / overrides.py
│   └── build.py                       # main() entry point
├── tests/                             # test_parser.py (pure functions) + test_data.py (JSON invariants)
├── chess-app/                         # Web app (see chess-app/README.md for details)
│   ├── index.html / vite.config.js / package.json
│   ├── css/ / js/                      # ES modules (ChessApp, PlayableBoard, Inline/Modal managers)
│   ├── data/                          # generated book_structure/diagrams/toc.json (gitignored,
│   │                                     # regenerate locally) + diagrams_manual_overrides.json (versioned)
│   └── tests/                         # vitest (chess-utils, search)
```

## Quickstart

### 0. Buy the book, place the EPUB

1. Buy *How to Reassess Your Chess* (4th ed., Jeremy Silman) as EPUB from a legal store.
2. Copy the file to the **repo root** with this exact name:
   ```
   How to Reassess Your Chess 4th ed - Silman.epub
   ```
   (see `silman_parser/config.py:INPUT_FILE`). It stays local — never committed.

### 1. Regenerate data (from repo root)

```bash
python3 -m silman_parser.build
```

Reads the EPUB following the `content.opf` spine order, splits into logical
sections (one per H2), matches diagrams against `pgn_studies/`, applies
`diagrams_manual_overrides.json` last, and writes
`chess-app/data/{book_structure,diagrams,toc}.json` (gitignored).
Without these files the app shows a "book not generated" error — normal on a fresh clone.

### 2. Run the app (after step 1)

```bash
cd chess-app
npm install   # once (vite, vitest, chess.js, cm-chessboard)
npm run dev   # http://localhost:5173
```

Production build:

```bash
npm run build    # prebuild copies data/ + cm-chessboard assets into public/, then vite build -> dist/
npm run preview  # http://localhost:4173
```

## Data

- `book_structure.json`: logical sections of HTML, one per EPUB H2 (`level` 1 for front-matter / "Part " answers, 2 otherwise; `original_page` is always 0). `<div class="diagram-inline" data-diagram="N">` for diagrams, `<div class="game-notation">` for games. Never edit by hand — generated.
- `diagrams.json`: 432 diagrams with `fen` / `initial_fen` / `moves` / `diagram_move_index` + recursive `variations` tree from PGN RAVs (flattened in-app by `flattenVariationLines()`). FEN coverage is 100% (429 via parsing + 3 via exclusive overrides; 4 override entries total).
- `diagrams_manual_overrides.json`: hardcoded fixes for diagrams unresolvable by parsing (no usable PGN chapter, chapter with another game, or historical position). Validated strictly (`fen` parseable, moves replayable, `fen == replay(initial_fen, moves[:index])`, fail-fast).
- `toc.json`: native EPUB table of contents (levels 1–2, starts with `Preface`).

Frontend stack: vanilla JS + chess.js v1 + cm-chessboard v8 (SVG squares, `staunty.svg` pieces), Vite 5 dev/build, Vitest tests. Inline boards lazy-mount via `IntersectionObserver`; modal board is draggable with chess.js move logic.

## Tests

```bash
python3 -m unittest discover -s tests -v   # backend: parser + generated-JSON invariants (stdlib only)
cd chess-app && npm test                    # frontend: 23 vitest tests (chess-utils + search)
```

JSON sanity checks:

```bash
python3 -m json.tool chess-app/data/book_structure.json > /dev/null
python3 -m json.tool chess-app/data/diagrams.json > /dev/null
python3 -m json.tool chess-app/data/toc.json > /dev/null
```

See `chess-app/README.md` for app usage (navigation, inline diagrams, search, keyboard shortcuts) and `AGENTS.md` for contributor conventions.

## License

The app code is yours to share. The book is © Jeremy Silman — no book text is
included in this repo (EPUB + generated JSONs are gitignored). Each user buys
the EPUB and generates the data locally for personal study.
