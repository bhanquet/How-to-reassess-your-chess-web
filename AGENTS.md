# AGENTS.md — How to Reassess Your Chess (interactive study app)

Personal-study web app for Silman's *How to Reassess Your Chess* (4th ed.).
Book text = logical sections (one per EPUB H2, split if >15k chars) + 432 interactive diagrams.

## Layout

```
.                                           # repo root
├── *.epub                                  # native EPUB, sole text source (parser input)
├── pgn_studies/                           # PGN studies → FENs + full games
├── silman_parser/                          # parser package: config, epub_ingest, san,
│                                           # segmentation, html_render, diagram_context,
│                                           # study, overrides, build (entry: `python3 -m silman_parser.build`)
├── tests/                                  # test_parser.py (pure fns) + test_data.py (JSON invariants)
├── docker-compose.yml                      # static Nginx on :5174
└── chess-app/                              # frontend (see chess-app/README.md)
    ├── index.html / vite.config.js / package.json / Dockerfile / nginx.conf
    ├── css/ (base, diagrams, modal, components, responsive)
    ├── js/ (app=orchestrator ChessApp; playable-board=shared core PlayableBoard;
    │        inline-boards / modal-board managers; chess-utils; templates; navigation; search)
    ├── data/ (book_structure.json, diagrams.json, diagrams_manual_overrides.json, toc.json)
    ├── public/ + dist/                     # generated (gitignored)
    └── tests/                              # vitest (chess-utils, search)
```

## Sources & pipeline

- EPUB is the only text source. Order = `content.opf` spine, not filename order.
  Sections = H2, subsections = H3 → `<h3>`. `Diagram N` = `<p class="diagram-number*">`
  → `<div class="diagram-inline" data-diagram="N">`; `<span class="bold">` moves →
  `<div class="game-notation">`. Side/level from `caption1` / `[Level: …]`. `images/*` ignored.
- FENs come from `pgn_studies/`, never the EPUB (100%: 429 parsed + 3 exclusive overrides, 4 entries).
  Overrides in `diagrams_manual_overrides.json`, applied last by `apply_manual_overrides()`
  (strict: FEN parseable, moves replayable, `fen == replay(initial_fen, moves[:index])`, fail-fast).
  To add one: add key with `fen`/`initial_fen`/`moves`/`source`/`comment`, regenerate.
- `book_structure.json`: `{section_num, title, level (1 = front-matter/"Part ", else 2), original_page: 0, content}`,
  long sections split via `split_long_sections()` → ` (continued N/M)` suffix.
- `diagrams.json[N]`: `{fen, initial_fen, moves, diagram_move_index, variations (recursive RAV tree,
  lvl-1 branch_ply relative to moves, nested relative to parent; max 12 lvl-1), entries[]}`.
  Frontend flattens via `flattenVariationLines()` (chess-utils.js).
- `toc.json`: native EPUB TOC lvl 1–2, starts at `Preface`.
- Regenerate: `python3 -m silman_parser.build` → writes the 3 JSON files. **Never edit `book_structure.json` by hand.**

## Run

```bash
cd chess-app && npm install && npm run dev      # http://localhost:5173
npm run build && npm run preview                 # build → dist/ (prebuild fills public/), preview :4173
docker compose up -d --build                    # optional, from root → :5174
```

## Frontend notes

- `PlayableBoard` = one chess.js v1 `Chess` + one cm-chessboard v8 `Chessboard` (+ Markers/PromotionDialog/Accessibility); shared by inline + modal.
- Inline boards lazy-mount via `IntersectionObserver` (200px margin); skeleton renders on section change.
- `navigation.js` builds the tree from `sections` order, groups ` (continued N/M)` under one chapter.
- Styling: cm-chessboard squares are SVG `rect.square` colored via `fill` (diagrams.css);
  theme via `light-dark()` vars (base.css); pieces at `public/cm-chessboard/pieces/staunty.svg`.
- HTML invariants: diagrams = `<div class="diagram-inline" data-diagram="N">`, scores = `<div class="game-notation">`, never `<div>` inside `<p>`.

## Tests & deps

```bash
python3 -m unittest discover -s tests -v   # backend (stdlib only; test_data checks FENs via python-chess, fen/index consistency, xrefs; KNOWN_STALE must stay empty)
cd chess-app && npm test                    # frontend vitest (39 tests)
python3 -m json.tool chess-app/data/book_structure.json > /dev/null  # + same for diagrams.json, toc.json
```

Deps (npm, no CDN): chess.js ^1.4, cm-chessboard ^8.13, vite ^5.4, vitest ^1.6.

Personal use only — book © Jeremy Silman.
