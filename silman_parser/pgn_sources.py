"""FEN and variation extraction from PGN studies (PGN)."""

import os
import re
import chess
import chess.pgn
from silman_parser.diagram_context import (
    extract_diagram_and_page_numbers,
    extract_players_from_chapter,
    find_diagram_move_context,
    find_diagram_position,
    find_move_sequence_end_index,
    find_position_with_side,
    get_diagram_side,
    get_mainline_moves,
    position_at,
    read_pgn_game_from_slice,
    replay_moves,
)


def extract_study_chapters():
    """Extract study chapters with FENs, moves and diagram numbers."""
    pgns_dir = 'pgn_studies'
    chapters = []
    if not os.path.isdir(pgns_dir):
        return chapters

    for filename in sorted(os.listdir(pgns_dir)):
        if not filename.endswith('.pgn'):
            continue
        path = os.path.join(pgns_dir, filename)
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        offset = 0
        while offset < len(text):
            next_event = text.find('[Event "', offset)
            if next_event == -1:
                break
            header_end = text.find('\n\n', next_event)
            if header_end == -1:
                header_end = len(text)
            headers = text[next_event:header_end]
            event = re.search(r'\[Event "([^"]+)"\]', headers)
            chapter = re.search(r'\[ChapterName "([^"]+)"\]', headers)
            fen = re.search(r'\[FEN "([^"]+)"\]', headers)
            variant = re.search(r'\[Variant "([^"]+)"\]', headers)
            nums = extract_diagram_and_page_numbers(
                event.group(1) if event else '',
                chapter.group(1) if chapter else ''
            )
            body_start = header_end + 2
            next_game = text.find('[Event "', body_start)
            body_end = next_game if next_game != -1 else len(text)
            game = read_pgn_game_from_slice(text, next_event, body_end)
            moves = get_mainline_moves(game) if game else []
            chapter_name = chapter.group(1) if chapter else ''
            chapters.append({
                'filename': filename,
                'event': event.group(1) if event else '',
                'chapter': chapter_name,
                'nums': nums,
                'fen': fen.group(1) if fen else None,
                'variant': variant.group(1) if variant else 'Standard',
                'moves': moves,
                # Full PGN tree (main lines + RAV variations), kept for
                # per-diagram variation extraction.
                'game': game,
                'players': extract_players_from_chapter(chapter_name),
            })
            offset = body_end if next_game == -1 else next_game
    return chapters


def extract_fens_from_study_games(book_data, diagrams_flat, chapters):
    """Try to extract missing FENs from the complete Study games."""
    # --- Pass 1: match by moves (existing) ---
    for ch in chapters:
        if ch['fen'] or not ch['nums'] or not ch['moves']:
            continue
        # FEN-less chapters start from the standard position: their parsed
        # game already IS the replayed main line (no separate replay step).
        game = ch['game']
        if game is None:
            continue
        start_fen = game.board().fen()
        for num in ch['nums']:
            key = str(num)
            if key not in diagrams_flat or diagrams_flat[key].get('fen'):
                continue
            target_moves = find_diagram_move_context(book_data, num)
            if not target_moves:
                continue
            match_end = find_move_sequence_end_index(game, target_moves)
            if match_end is None:
                continue
            board = position_at(game, match_end)
            diagrams_flat[key]['fen'] = board.fen()
            diagrams_flat[key]['initial_fen'] = start_fen
            diagrams_flat[key]['moves'] = ch['moves']
            diagrams_flat[key]['diagram_move_index'] = match_end
            diagrams_flat[key]['matched_by'] = 'moves_match'

    # --- Pass 2: match by chapter / player names ---
    # For diagrams without a FEN, associate the diagram number with the
    # corresponding study chapter (chapters are named by diagram numbers in
    # the PGN study). The diagram position is determined by:
    #   1. the book moves before/after the diagram (exact match),
    #   2. otherwise the 'len(moves) - 1' heuristic (position before the final move),
    #   3. validated by the side ("White to move" / "Black to move").
    for ch in chapters:
        if ch['fen'] or not ch['nums'] or not ch['moves']:
            continue
        if len(ch['moves']) < 10:
            continue
        has_real_players = bool(ch.get('players')) and 'Player' not in ch['players']
        game = ch['game']
        if game is None:
            continue
        start_fen = game.board().fen()
        for num in ch['nums']:
            key = str(num)
            if key not in diagrams_flat or diagrams_flat[key].get('fen'):
                continue
            # Find the diagram position in the game
            diagram_index = find_diagram_position(book_data, num, game, ch['moves'])
            if diagram_index is None:
                continue
            # For "Player - Player" chapters (no real players), only apply if
            # the position was found by move matching (the chapter is then
            # verified). Otherwise the game cannot be verified against the book.
            if not has_real_players and diagram_index == len(ch['moves']) - 1:
                continue
            board = position_at(game, diagram_index)
            # Validate the side: if the book says "White/Black to move" and the
            # position does not match, step back until the right side is found.
            side = get_diagram_side(book_data, num)
            if side is not None and board.turn != side:
                new_index = find_position_with_side(game, diagram_index, side)
                if new_index is None:
                    continue
                diagram_index = new_index
                board = position_at(game, diagram_index)
            diagrams_flat[key]['fen'] = board.fen()
            diagrams_flat[key]['initial_fen'] = start_fen
            diagrams_flat[key]['moves'] = ch['moves']
            diagrams_flat[key]['diagram_move_index'] = diagram_index
            diagrams_flat[key]['matched_by'] = diagrams_flat[key].get(
                'matched_by', 'chapter_heuristic')

MAX_VARIATIONS_PER_DIAGRAM = 12


def collect_mainline_and_branches(node, board):
    """Walk the children of a PGN node.

    `board` is the position at the node (before the child moves).
    Returns (main_moves, variations) where the `branch_ply` values are
    relative to `main_moves`. The SANs are generated from the board, so they
    are legal by construction (try/except safety net).

    Each branch also carries, when present on the sibling move that opens it,
    its PGN comment and NAGs (keys `comment`: str, default '' ; `nags`: list,
    default []). No truncation here: the frontend truncates the display. The
    recursion guarantees that nested branches receive the same keys.
    """
    main_moves = []
    branches = []
    cur = node
    b = board.copy()
    while cur.variations:
        for sib in cur.variations[1:]:
            sb = b.copy()
            try:
                first = sb.san(sib.move)
            except Exception:
                continue
            sb.push(sib.move)
            rest, nested = collect_mainline_and_branches(sib, sb)
            # The full variant line includes the sibling move: the nested
            # branch_ply values (relative to `rest`) are shifted by 1.
            for n in nested:
                n['branch_ply'] += 1
            branches.append({
                'branch_ply': len(main_moves),
                'moves': [first] + rest,
                'variations': nested,
                'comment': (sib.comment or '').strip(),
                'nags': list(sib.nags or []),
            })
        nxt = cur.variations[0]
        try:
            san = b.san(nxt.move)
        except Exception:
            break
        main_moves.append(san)
        b.push(nxt.move)
        cur = nxt
    return main_moves, branches


def extract_variation_tree(game, main_moves, diagram_index):
    """Extract the RAV variation tree branching at/after `diagram_index`.

    Top-level `branch_ply` is relative to `main_moves`; nested levels are
    relative to the `moves` of their parent. Only branches with
    `branch_ply >= diagram_index` are kept (what precedes the diagram does not
    concern its display).
    """
    if game is None or not main_moves:
        return []
    try:
        _, branches = collect_mainline_and_branches(game, game.board())
    except Exception:
        return []
    kept = [br for br in branches if br['branch_ply'] >= diagram_index]
    # Sort by relevance before truncation: the branch closest to the diagram
    # first (minimal branch_ply - diagram_index), and at equal distance the
    # longest first (stable sort otherwise -> PGN order kept).
    kept.sort(key=lambda br: (br['branch_ply'] - diagram_index, -len(br['moves'])))
    return kept[:MAX_VARIATIONS_PER_DIAGRAM]


def _norm_san(san):
    """Normalize a SAN for comparison: strip the check/mate suffix.

    The comparison stays case-sensitive otherwise (SANs generated by
    python-chess and those from the book are all uppercase).
    """
    if not isinstance(san, str):
        return san
    return san.rstrip('+#')


def _mainline_matches(data_moves, chapter_moves, idx):
    """Compare the diagram main line with the chapter main line.

    Returns True if the normalized lines (suffix +/# ignored) are equal, or
    if they lead to the same position after `idx` moves from the standard
    starting position (chapter PGNs have no FEN header when a line is
    present, so the start is standard). If either replay fails, falls back to
    the strict list comparison (historical behavior).
    """
    norm_data = [_norm_san(m) for m in data_moves]
    norm_ch = [_norm_san(m) for m in chapter_moves]
    if norm_data == norm_ch:
        return True
    try:
        b1 = chess.Board()
        for san in data_moves[:idx]:
            b1.push_san(san)
        b2 = chess.Board()
        for san in chapter_moves[:idx]:
            b2.push_san(san)
    except Exception:
        return data_moves == chapter_moves
    return b1.fen() == b2.fen()


def extract_diagram_variations(diagrams_flat, chapters):
    """Fill diagrams_flat[num]['variations'] from the PGN trees.

    Variations are only attached if the diagram main line (`data['moves']`)
    matches the chapter one: equal after SAN normalization (suffix +/#
    ignored) or leading to the same position at `diagram_move_index` (replay
    from the standard position). Guarantees that the `branch_ply` values
    designate the right moves. Limited to MAX_VARIATIONS_PER_DIAGRAM; the rest
    is reported via `_var_truncated = True` in the diagram entry.
    """
    count = 0
    for ch in chapters:
        game = ch.get('game')
        if game is None or not ch.get('moves'):
            continue
        for num in ch['nums']:
            key = str(num)
            data = diagrams_flat.get(key)
            if data is None or not data.get('moves'):
                continue
            if data.get('variations'):
                continue
            idx = data.get('diagram_move_index', 0)
            if not _mainline_matches(list(data['moves']), list(ch['moves']), idx):
                continue
            all_branches = extract_variation_tree(game, ch['moves'], idx)
            if not all_branches:
                continue
            data['variations'] = all_branches
            if len(all_branches) > MAX_VARIATIONS_PER_DIAGRAM:
                data['_var_truncated'] = len(all_branches) - MAX_VARIATIONS_PER_DIAGRAM
            count += 1
    return count


def validate_variation_tree(base_fen, parent_moves, branches, num, path=''):
    """Validate a variation tree against a parent line (fail-fast).

    Each branch must replay from `base_fen` + `parent_moves[:branch_ply]`.
    """
    try:
        replay_moves(base_fen, parent_moves, strict=True)
    except ValueError as e:
        raise ValueError(f'override {num}: parent line not replayable {path!r}: {e}')
    for i, br in enumerate(branches or []):
        where = f'{path}[{i}]'
        bp = br.get('branch_ply')
        if not isinstance(bp, int) or not (0 <= bp <= len(parent_moves)):
            raise ValueError(f'override {num}: invalid branch_ply at {where}')
        try:
            replay_moves(base_fen, parent_moves[:bp] + br.get('moves', []),
                         strict=True)
        except ValueError as e:
            raise ValueError(f'override {num}: variation not replayable at {where}: {e}')
        branch_fen = replay_moves(base_fen, parent_moves[:bp], strict=True).fen()
        validate_variation_tree(branch_fen, br.get('moves', []),
                                br.get('variations', []), num, where)