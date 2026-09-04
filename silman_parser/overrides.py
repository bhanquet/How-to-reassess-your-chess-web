"""Manual overrides for diagrams unresolvable by parsing."""

import json
import os
import chess
from silman_parser.config import MANUAL_OVERRIDES_FILE
from silman_parser.diagram_context import replay_moves
from silman_parser.study import validate_variation_tree


def load_manual_overrides():
    """Load the manual overrides (source of truth for the diagrams that
    automatic parsing cannot resolve)."""
    if not os.path.exists(MANUAL_OVERRIDES_FILE):
        return {}
    with open(MANUAL_OVERRIDES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f'{MANUAL_OVERRIDES_FILE}: expected a JSON object')
    return data


def apply_manual_overrides(diagrams_flat, overrides):
    """Apply the manual overrides to diagrams_flat (wins over everything).

    Strict validation (fail-fast): parseable FEN, replayable moves from
    initial_fen, and diagram_move_index consistent with fen.
    """
    applied = 0
    for num, ov in overrides.items():
        key = str(num)
        if key not in diagrams_flat:
            raise ValueError(
                f'override {key}: diagram unknown to the book')
        fen = ov.get('fen')
        if not fen:
            raise ValueError(f'override {key}: missing "fen" key')
        try:
            chess.Board(fen)
        except ValueError:
            raise ValueError(f'override {key}: invalid FEN: {fen!r}')
        moves = ov.get('moves')
        idx = ov.get('diagram_move_index', 0)
        initial_fen = ov.get('initial_fen')
        if moves is None:
            if idx != 0:
                raise ValueError(
                    f'override {key}: without moves, diagram_move_index must be 0')
        else:
            if not initial_fen:
                raise ValueError(
                    f'override {key}: "initial_fen" required with "moves"')
            try:
                replay_moves(initial_fen, moves, strict=True)
            except ValueError as e:
                raise ValueError(f'override {key}: {e}')
            if not (0 <= idx <= len(moves)):
                raise ValueError(
                    f'override {key}: diagram_move_index out of bounds')
            replay_fen = replay_moves(initial_fen, moves[:idx], strict=True).fen()
            if replay_fen != fen:
                raise ValueError(
                    f'override {key}: fen/index inconsistency '
                    f'(replay={replay_fen!r})')
        data = diagrams_flat[key]
        data['fen'] = fen
        data['initial_fen'] = initial_fen or fen
        data['moves'] = moves
        data['diagram_move_index'] = idx
        # The override replaces the main line: any previously extracted PGN
        # variations are stale, unless the override provides its own tree
        # (validated recursively).
        ov_vars = ov.get('variations')
        if ov_vars is None:
            data['variations'] = []
        else:
            validate_variation_tree(initial_fen, moves, ov_vars, key)
            data['variations'] = ov_vars
        applied += 1
    return applied