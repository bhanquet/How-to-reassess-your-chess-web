# AGENTS.md — How to Reassess Your Chess (interactive study app)

Personal-study web app for Silman's *How to Reassess Your Chess* (4th ed.).
Book text = logical sections (one per EPUB H2, split if >15k chars) + 432 interactive diagrams.

## Layout

```
.                                           # repo root
├── *.epub                                  # native EPUB, sole text source (parser input)
├── pgn_studies/                            # Local PGN studies → FENs + full games
├── silman_parser/                          # parser package: config, epub_ingest, san,
│                                           # segmentation, html_render, diagram_context,
│                                           # pgn_sources, build (entry: `python3 -m silman_parser.build`)
├── tests/                                  # test_parser.py (pure fns) + test_data.py (JSON invariants)
├── docs/                                   # screenshot-app.png (README illustration)
├── package.json / package-lock.json        # root-only: @playwright/mcp runner
├── docker-compose.yml                      # static Nginx on :5174
└── chess-app/                              # frontend (usage: root README)
    ├── index.html / vite.config.js / package.json / Dockerfile / nginx.conf
    ├── css/ (base, diagrams, modal, components, responsive)
    ├── js/ (app=orchestrator ChessApp; playable-board=shared core PlayableBoard;
    │        inline-boards / modal-board managers; chess-utils; templates; navigation; search; config)
    ├── data/ (book_structure.json, diagrams.json, toc.json = generated locally,
    │        gitignored, see below)
    ├── public/ + dist/                     # generated (gitignored)
    └── tests/                              # vitest (chess-utils, search)
```

## Sources & pipeline

- EPUB is the only text source. Order = `content.opf` spine, not filename order.
  Sections = H2, subsections = H3 → `<h3>`. `Diagram N` = `<p class="diagram-number*">`
  → `<div class="diagram-inline" data-diagram="N">`; `<span class="bold">` moves →
  `<div class="game-notation">`. Side/level from `caption1` / `[Level: …]`. `images/*` ignored.
- FENs come from `pgn_studies/`, never the EPUB (100%: all 432 parsed).
  6 diagrams need an explicit pin (141, 201, 209, 213, 320, 407):
  a chapter with `[DiagramNumber "N"]` + `[DiagramPly "K"]` pins diagram N to ply K of its own
  mainline (parsed in `extract_study_chapters`, applied by `apply_pgn_pins`; precedence:
  `chapter_fen` → `pgn_pin` → passes 1-2). Fail-fast if only one
  header is present or the ply/diagram is invalid. To fix a position: edit the PGN chapter
  (or its pin headers), regenerate.
- `book_structure.json`, `diagrams.json`, `toc.json`: generated locally, gitignored
  (copyrighted text, never committed). `book_structure.json`: `{section_num, title, level (1 = front-matter/"Part ", else 2), original_page: 0, content}`,
  long sections split via `split_long_sections()` → ` (continued N/M)` suffix.
- `diagrams.json[N]`: `{fen, initial_fen, moves, diagram_move_index, variations (recursive RAV tree,
  lvl-1 branch_ply relative to moves, nested relative to parent; max 12 lvl-1), entries[]}`.
  Frontend flattens via `flattenVariationLines()` (chess-utils.js).
- `toc.json`: native EPUB TOC (166 nodes, depth 0–3), starts at `Title Page`.
- Regenerate: buy the EPUB legally, place it at repo root as
  `How to Reassess Your Chess 4th ed - Silman.epub` (see `silman_parser/config.py:INPUT_FILE`),
  then `python3 -m silman_parser.build` → writes the 3 JSON files. **Never edit `book_structure.json` by hand.**
  The 3 JSON files are gitignored so the public repo contains no book text.

## Run

```bash
# once per machine: python-chess (parser + tests need it) —
# venv (recommended): python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
# or system-wide: pip install --user -r requirements.txt
pip install -r requirements.txt
python3 -m silman_parser.build   # required first: needs the purchased EPUB at root
cd chess-app && npm install && npm run dev      # http://localhost:5173
npm run build && npm run preview                 # build → dist/ (prebuild fills public/), preview :4173
docker compose up -d --build                    # optional, from root → :5174 (generate data first)
```
Docker note: the Dockerfile intentionally does NOT generate data (it would require
copying the private EPUB into the public image). Generate locally before `docker build`.

## Frontend notes

- `PlayableBoard` = one chess.js v1 `Chess` + one cm-chessboard v8 `Chessboard` (+ Markers/Arrows/PromotionDialog/Accessibility); shared by inline + modal.
- Inline boards lazy-mount via `IntersectionObserver` (400px margin); skeleton renders on section change.
- `navigation.js` builds the tree from `sections` order, groups ` (continued N/M)` under one chapter.
- Styling: cm-chessboard squares are SVG `rect.square` colored via `fill` (diagrams.css);
  theme via `light-dark()` vars (base.css); pieces at `public/cm-chessboard/pieces/staunty.svg`.
- HTML invariants: diagrams = `<div class="diagram-inline" data-diagram="N">`, scores = `<div class="game-notation">`, never `<div>` inside `<p>`.

## Tests & deps

```bash
python3 -m unittest discover -s tests -v   # backend (needs python-chess; test_data checks FENs via python-chess, fen/index consistency, xrefs; KNOWN_STALE must stay empty)
cd chess-app && npm test                    # frontend vitest (42 tests)
python3 -m json.tool chess-app/data/book_structure.json > /dev/null  # + same for diagrams.json, toc.json
```

Deps (npm, no CDN): chess.js ^1.4, cm-chessboard ^8.13, vite ^8.2, vitest ^4.1.

Personal use only — book © Jeremy Silman. The public repo contains no book text
(generated JSONs are gitignored); buy the EPUB to regenerate locally.
