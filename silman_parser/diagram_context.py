"""Diagram context in the book (moves before/after, side to move, players)."""

import re
import logging
from io import StringIO
import chess
import chess.pgn
from silman_parser.san import extract_san_moves


logger = logging.getLogger(__name__)


def find_diagram_move_context(book_data, diagram_num):
    """Return the SAN moves located around a diagram.

    First looks for a notation <div class="game-notation"> before the diagram
    (conventional position). As a fallback, also looks after the diagram
    (between this diagram and the next one, or the end of the section) and
    returns the notation closest to the diagram.
    """
    for sec in book_data['sections']:
        content = sec['content']
        pattern = f'<div class="diagram-inline" data-diagram="{diagram_num}">'
        idx = content.find(pattern)
        if idx == -1:
            continue
        before = content[:idx]

        # 1) Notation <div class="game-notation"> before the diagram
        notations = re.findall(r'<div class="game-notation">(.*?)</div>', before)
        if notations:
            return extract_san_moves(notations[-1])

        # 2) Notation <div class="game-notation"> after the diagram
        #    (up to the next diagram or the end of the section)
        after = content[idx + len(pattern):]
        next_diagram = after.find('<div class="diagram-inline"')
        if next_diagram != -1:
            after = after[:next_diagram]
        notations = re.findall(r'<div class="game-notation">(.*?)</div>', after)
        if notations:
            return extract_san_moves(notations[0])
    return []


def extract_diagram_and_page_numbers(event, chapter):
    """Extract the diagram numbers (and "Page NNN") from the PGN headers.

    Handles "Diagram 12", "Diagrams 3 & 4", comma lists, ranges ("5-7"),
    and the "Disgrams" OCR/typo variant found in the PGN study names.
    Also collects "Page NNN" page references.
    """
    text = f"{event} {chapter}"
    results = []

    for m in re.finditer(r'Diagrams?\s+((?:\d+\s*,\s*)+\d+\s*(?:&|and)\s*\d+)', text, re.IGNORECASE):
        parts = re.split(r'\s*,\s*|\s*(?:&|and)\s*', m.group(1))
        results.extend(int(p) for p in parts if p.isdigit())

    for m in re.finditer(r'Diagrams?:?\s+(\d+)\s*(?:&|and)\s*(\d+)', text, re.IGNORECASE):
        results.extend([int(m.group(1)), int(m.group(2))])

    for m in re.finditer(r'Diagrams?\s+(\d+)\s*[-–—]\s*(\d+)', text, re.IGNORECASE):
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < b - a < 20:
            results.extend(range(a, b + 1))

    for m in re.finditer(r'Diagrams?\s+(\d+)(?!\d|\s*[-–—])', text, re.IGNORECASE):
        results.append(int(m.group(1)))

    for m in re.finditer(r'Disgrams?\s+(\d+)\s*(?:&|and)\s*(\d+)', text, re.IGNORECASE):
        results.extend([int(m.group(1)), int(m.group(2))])

    for m in re.finditer(r'\bPage\s+(\d{3,})\b', text, re.IGNORECASE):
        results.append(int(m.group(1)))

    return sorted(set(results))


def read_pgn_game_from_slice(text, start, end):
    """Read a PGN game with its headers from the raw text slice."""
    body = text[start:end].strip()
    if not body:
        return None
    try:
        return chess.pgn.read_game(StringIO(body))
    except Exception:
        return None


def get_mainline_moves(game):
    """Return the list of SAN moves of the game main line."""
    moves = []
    node = game
    while node.variations:
        node = node.variations[0]
        moves.append(node.san())
    return moves


def extract_players_from_chapter(chapter):
    """Extract player names from a Study ChapterName.

    Ex: "Diagram 19: Liviu Dieter Nisipeanu - Vadim Milov"
        -> ("Liviu Dieter Nisipeanu", "Vadim Milov")
    """
    if not chapter:
        return None
    m = re.search(r':\s*(.+)$', chapter)
    if not m:
        return None
    players_part = m.group(1).strip()
    if ' - ' not in players_part:
        return None
    white, black = players_part.split(' - ', 1)
    white = white.strip()
    black = black.strip()
    if not white or not black:
        return None
    return (white, black)


def get_diagram_side(book_data, diagram_num):
    """Return the expected side to move (chess.WHITE / chess.BLACK) or None.

    Looks for "White to move" / "Black to move" in the text right after the
    diagram (first 300 chars).
    """
    context = ''
    for sec in book_data['sections']:
        content = sec['content']
        pattern = f'<div class="diagram-inline" data-diagram="{diagram_num}">'
        idx = content.find(pattern)
        if idx == -1:
            continue
        context = content[idx + len(pattern):idx + len(pattern) + 300]
        break
    if re.search(r'\bWhite\s+to\s+move\b', context):
        return chess.WHITE
    if re.search(r'\bBlack\s+to\s+move\b', context):
        return chess.BLACK
    return None


def replay_moves(initial_fen, moves, strict=False):
    """Replay SAN moves from a start position (single replay helper).

    `initial_fen` None means the standard starting position. Lenient by
    default (stops silently at the first move that cannot be applied, like
    the historical PGN replay); with strict=True raises ValueError on the
    first illegal/unparseable move (validation paths). Returns the board.
    """
    board = chess.Board(initial_fen) if initial_fen else chess.Board()
    for san in moves:
        try:
            board.push_san(san)
        except ValueError:
            if strict:
                raise ValueError(f'illegal move {san!r}') from None
            break
    return board


def position_at(game, index):
    """Return the board after `index` moves of the main line.

    Delegates to the shared replay helper (replay_moves) on the main-line
    SANs, honoring a game FEN header when present.
    """
    start_fen = game.headers.get('FEN') if game.headers else None
    return replay_moves(start_fen, get_mainline_moves(game)[:index])


def find_position_with_side(game, start_index, side):
    """Walk back in the game until a position with the right side to move."""
    for i in range(start_index, -1, -1):
        if position_at(game, i).turn == side:
            return i
    return None


def find_exact_match(game, target_moves):
    """Find an exact contiguous match of target_moves in the game main line.

    Returns the end index of the match (number of moves played) or None.
    Unlike find_move_sequence_end_index, does not accept partial matches
    (avoids false positives caused by text artifacts).
    """
    if not target_moves:
        return None
    game_moves = get_mainline_moves(game)
    for start in range(len(game_moves) - len(target_moves) + 1):
        if game_moves[start:start + len(target_moves)] == target_moves:
            return start + len(target_moves)
    return None


def _moves_from_html(segment, take_last):
    """Extract SAN moves from the chosen <div class="game-notation"> block.

    Returns the SAN moves of the last/first notation block (depending on
    `take_last`), or [] when no notation block is present.
    """
    notations = re.findall(r'<div class="game-notation">(.*?)</div>', segment)
    if not notations:
        return []
    return extract_san_moves(notations[-1] if take_last else notations[0])


def get_moves_before_diagram(book_data, diagram_num, window=1500):
    """Return the SAN moves in the text right before a diagram."""
    for sec in book_data['sections']:
        content = sec['content']
        pattern = f'<div class="diagram-inline" data-diagram="{diagram_num}">'
        idx = content.find(pattern)
        if idx == -1:
            continue
        before = content[max(0, idx - window):idx]
        moves = _moves_from_html(before, take_last=True)
        if moves:
            return moves
    return []


def get_moves_after_diagram(book_data, diagram_num, window=1500):
    """Return the SAN moves in the text right after a diagram."""
    for sec in book_data['sections']:
        content = sec['content']
        pattern = f'<div class="diagram-inline" data-diagram="{diagram_num}">'
        idx = content.find(pattern)
        if idx == -1:
            continue
        after = content[idx + len(pattern):idx + len(pattern) + window]
        moves = _moves_from_html(after, take_last=False)
        if moves:
            return moves
    return []


def adjust_index_for_side_to_move(game, idx, expected_side):
    """Validate the expected side of a candidate index and fix an off-by-one.

    The side of the position after `idx` plies is always the opposite of the
    color of the last move played (by parity), so a "last move" test has no
    discriminating power. We simply validate the position against
    `expected_side`, optionally correcting an extra ply (+1) by stepping back
    one ply if the previous position matches the expected side.
    Returns the valid index, or None if no position matches.
    """
    if idx is None or idx < 0:
        return None
    if expected_side is None:
        return idx
    if position_at(game, idx).turn == expected_side:
        return idx
    # Extra +1 ply: the real position is one ply earlier.
    if idx > 0 and position_at(game, idx - 1).turn == expected_side:
        return idx - 1
    return None


def find_diagram_position(book_data, diagram_num, game, all_moves):
    """Find the index of the diagram position in the game.

    Strategy:
    1. Book moves BEFORE the diagram -> the position is after those moves
       (longest prefix exactly matching the game).
    2. Book moves AFTER the diagram -> the position is before those moves
       (longest prefix exactly matching the game).
       Used first when the moves before are ambiguous (noisy text) and their
       side does not match the text.
    3. Fallback: before the last move of the main line (len-1).

    Each candidate is validated against the expected side ("White/Black to
    move" in the text, see get_diagram_side) and corrected for off-by-one
    (+1 ply) errors via adjust_index_for_side_to_move. A candidate whose side
    does not match is rejected, which switches to the moves after the diagram
    or to a shorter prefix.
    """
    expected_side = get_diagram_side(book_data, diagram_num)

    # 1. Moves before the diagram
    before_moves = get_moves_before_diagram(book_data, diagram_num)
    if before_moves:
        for length in range(len(before_moves), 0, -1):
            match_end = find_exact_match(game, before_moves[:length])
            if match_end is not None:
                idx = adjust_index_for_side_to_move(game, match_end, expected_side)
                if idx is not None:
                    return idx
                logger.warning(
                    "find_diagram_position D%s: 'before' candidate idx=%d "
                    "rejected (side mismatch, expected=%s)",
                    diagram_num, match_end,
                    'white' if expected_side == chess.WHITE
                    else ('black' if expected_side == chess.BLACK else '?'),
                )
    # 2. Moves after the diagram
    after_moves = get_moves_after_diagram(book_data, diagram_num)
    if after_moves:
        for length in range(len(after_moves), 0, -1):
            match_end = find_exact_match(game, after_moves[:length])
            if match_end is not None:
                if match_end - length < 0:
                    continue
                idx = adjust_index_for_side_to_move(
                    game, match_end - length, expected_side)
                if idx is not None:
                    return idx
    # 3. Fallback: len-1
    if expected_side is None:
        return len(all_moves) - 1
    if position_at(game, len(all_moves) - 1).turn == expected_side:
        return len(all_moves) - 1
    if len(all_moves) - 2 >= 0 and position_at(game, len(all_moves) - 2).turn == expected_side:
        return len(all_moves) - 2
    logger.warning(
        "find_diagram_position D%s: len-1 fallback invalid against expected "
        "side=%s (intentionally invalid)",
        diagram_num,
        'white' if expected_side == chess.WHITE
        else ('black' if expected_side == chess.BLACK else '?'),
    )
    return len(all_moves) - 1