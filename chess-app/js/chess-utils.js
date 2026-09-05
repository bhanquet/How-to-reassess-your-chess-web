/**
 * Pure chess logic (no DOM): move numbering, variations, validation.
 * Uses chess.js v1 (ESM, throws on illegal move).
 */

import { Chess } from 'chess.js';
import { DEFAULT_START_FEN, MAX_FLAT_LINES } from './config.js';

/**
 * Chess-style move number ("15." / "15...") for an absolute ply counted
 * from initialFen.
 *
 * Semantics: the function labels the move **about to be played** at the
 * branching point of a variation (before the variation diverges). SAN convention:
 * - initialFen with White to move: absPly 0 → "1.", 2 → "2.", 4 → "3.", ...
 * - initialFen with Black to move (fullmove already N): absPly 0 → "N..." (Black),
 *   1 → "N+1." (White), 2 → "N+1..." (Black), ...
 */
export function moveNumberLabel(absPly, initialFen) {
    if (!initialFen) return '';
    try {
        const parts = initialFen.split(' ');
        const whiteToMove = (parts[1] || 'w') === 'w';
        const full = parseInt(parts[5] || '1', 10) || 1;
        const whitePlays = (absPly % 2 === 0) === whiteToMove;
        // Number of white / black plies already played before the upcoming move:
        //   whitePliesPlayed = ⌊(absPly+1)/2⌋ (unified formula, works for White/Black to move)
        //   blackPliesPlayed = ⌊absPly/2⌋
        const pliesWhitesPlayed = Math.floor((absPly + 1) / 2);
        const pliesBlacksPlayed = Math.floor(absPly / 2);
        const moveNo = full + (whitePlays ? pliesWhitesPlayed : pliesBlacksPlayed);
        return `${moveNo}${whitePlays ? '.' : '...'}`;
    } catch (e) {
        return '';
    }
}

/**
 * Flattens the variation tree into complete replayable lines from initialFen.
 * Each line: {id, label, moves, absPly, parentId, depth}.
 * absPly = absolute ply of the branching point (0 = main line).
 */
export function flattenVariationLines(mainMoves, variations, initialFen) {
    const lines = [{
        id: 'main', label: 'Main line', moves: mainMoves.slice(),
        absPly: 0, parentId: null, depth: 0
    }];
    const walk = (parent, vars) => {
        (vars || []).forEach((v, vi) => {
            if (lines.length >= MAX_FLAT_LINES) return;
            // `branchPly` = the absolute ply where this variation diverges
            // (field stays `absPly` on the returned line object: public API).
            const branchPly = parent.absPly + (v.branch_ply || 0);
            const moves = parent.moves.slice(0, branchPly).concat(v.moves || []);
            const replaced = parent.moves[branchPly] || 'end';
            const num = moveNumberLabel(branchPly, initialFen);
            const prefix = '› '.repeat(parent.depth + 1);
            const moveCount = (v.moves || []).length;
            const moveCountLabel = `${moveCount} move${moveCount > 1 ? 's' : ''}`;
            const label = `${prefix}Instead of ${num}${replaced} : ${num}${(v.moves || [])[0] || ''} (${moveCountLabel})`
                + variationLabelSuffix(v);
            const line = {
                id: `${parent.id}.${vi}`,
                label,
                moves,
                absPly: branchPly,
                parentId: parent.id,
                depth: parent.depth + 1,
            };
            lines.push(line);
            walk(line, v.variations);
        });
    };
    walk(lines[0], variations);
    return lines;
}

/**
 * Replays a line from initialFen, truncated at the first illegal move.
 * In chess.js v1, `move()` throws on an illegal move — we catch it.
 */
export function validateLineMoves(initialFen, moves) {
    const temp = new Chess();
    try {
        temp.load(initialFen);
    } catch (e) {
        return [];
    }
    const valid = [];
    for (const san of moves || []) {
        let m = null;
        try {
            m = temp.move(san);
        } catch (e) {
            break;
        }
        if (m) valid.push(m.san); else break;
    }
    return valid;
}

/**
 * Builds the replayable lines of a diagram: main line + variations whose
 * branching point is replayable. Shared by inline diagrams and the modal.
 */
export function buildPlayableLines(initialFen, presetMoves, variations) {
    const mainMoves = validateLineMoves(initialFen, presetMoves);
    const lines = [{
        id: 'main', label: 'Main line', moves: mainMoves.slice(),
        absPly: 0, parentId: null, depth: 0
    }];
    for (const line of flattenVariationLines(mainMoves, variations, initialFen)) {
        if (line.id === 'main') continue;
        const valid = validateLineMoves(initialFen, line.moves);
        if (valid.length > line.absPly) {
            lines.push({ ...line, moves: valid });
        }
    }
    return lines;
}

/** Mapping of NAG ($n) to chess symbols. */
const NAG_SYMBOLS = { 1: '!', 2: '?', 3: '!!', 4: '??', 5: '!?', 6: '?!' };

/**
 * Enriched suffix for a variation label: comment truncated to 80 characters,
 * then NAG symbols. Returns '' if there is nothing to add. Does not escape
 * anything (templates.js handles that).
 */
export function variationLabelSuffix(v) {
    const parts = [];
    if (v && typeof v.comment === 'string' && v.comment) {
        parts.push(v.comment.length > 80 ? v.comment.slice(0, 80) : v.comment);
    }
    if (v && Array.isArray(v.nags) && v.nags.length) {
        const syms = v.nags.map((n) => {
            const num = parseInt(String(n).replace(/^\$/, ''), 10);
            return (!Number.isNaN(num) && NAG_SYMBOLS[num]) ? NAG_SYMBOLS[num] : `$${n}`;
        });
        parts.push(syms.join(' '));
    }
    return parts.length ? ` — ${parts.join(' ')}` : '';
}

/**
 * Returns the alternative variations available at a given absolute ply.
 *
 * Matching criterion (documented): a line is an alternative at ply
 * `currentPly` if **its branching point** (`line.absPly`) equals exactly
 * `currentPly`. The 'main' line is excluded (it is the baseline, not an
 * alternative). Excluding the currently played line is the caller's
 * responsibility.
 *
 * The `absPly` field on lines/alternatives IS the branching point (`branchPly`
 * concept); the `currentPly` parameter is the position being queried. The two
 * are the same value only when the caller asks "what can I play here?".
 *
 * @param {Array<{id,moves,absPly,parentId,depth,label}>} lines
 *   Lines produced by buildPlayableLines/flattenVariationLines.
 * @param {number} currentPly Current absolute ply (0 = starting position).
 * @returns {Array<{lineId,san,label,absPly,depth,length}>}
 *   `san` = first diverging move (first move specific to the variation);
 *   `length` = number of moves in the line.
 */
export function getAlternativesAt(lines, currentPly) {
    return (lines || [])
        .filter((l) => l && l.id !== 'main' && l.absPly === currentPly)
        .map((l) => ({
            lineId: l.id,
            san: l.moves[l.absPly] || '',
            label: l.label,
            absPly: l.absPly,
            depth: l.depth,
            length: l.moves.length,
        }));
}

/**
 * Builds a "custom variation" line (move proposed by the user instead of the
 * current move). Pure function: no chess validation here (it stays in
 * validateLineMoves/buildPlayableLines).
 *
 * @param {string[]} baseMoves Moves of the baseline line (typically moves from a
 *   parent or the main line).
 * @param {number} currentIndex Index of the move to replace in baseMoves.
 * @param {string} newSan Proposed move (SAN).
 * @param {object} [opts] { id, idPrefix, counter, parentId, depth }
 *   - id: explicit id (e.g. 'custom-3'). Otherwise generated `${idPrefix}-${counter}`.
 * @returns {{id,label,moves,absPly,parentId,depth}}
 *   label = `My variation : <san>` ; moves = baseMoves[0..currentIndex) + newSan ;
 *   absPly = currentIndex.
 */
export function createCustomLine(baseMoves, currentIndex, newSan, {
    id, idPrefix = 'custom', counter = 0, parentId = null, depth = 1,
} = {}) {
    const moves = (baseMoves || []).slice(0, currentIndex).concat([newSan]);
    return {
        id: id ?? `${idPrefix}-${counter}`,
        label: `My variation : ${newSan}`,
        moves,
        absPly: currentIndex,
        parentId,
        depth,
    };
}

/**
 * Parses a `data-ply` attribute into a number, or `null` when absent/invalid.
 * Shared NaN→null fallback for move and variation jumps (`.var-jump` buttons
 * may omit a meaningful ply).
 */
export function parsePlyOrNull(value) {
    const ply = parseInt(value, 10);
    return Number.isNaN(ply) ? null : ply;
}

/**
 * Unpacks a diagrams.json entry into the shape consumed by the playable
 * boards (PlayableBoard.loadDiagram + the inline caption).
 *
 * The FEN fallback is unified on `DEFAULT_START_FEN` — inline boards used to
 * fall back to `'start'`, the modal to `DEFAULT_START_FEN`; both normalize to
 * the same position, so this single code path is used everywhere.
 *
 * @param {object|null} d diagrams.json[N]
 * @returns {{ fen: string|null, initialFen: string, moves: string[]|null,
 *   variations: object[], diagramPlyIndex: number, side: string|null,
 *   level: string|null, hasPosition: boolean }}
 */
export function unpackDiagramData(d) {
    const fen = d?.fen || null;
    return {
        fen,
        initialFen: d?.initial_fen || fen || DEFAULT_START_FEN,
        moves: d?.moves || null,
        variations: d?.variations || [],
        diagramPlyIndex: d?.diagram_move_index ?? 0,
        side: d?.entries?.[0]?.side || null,
        level: d?.entries?.[0]?.level || null,
        hasPosition: !!fen,
    };
}
