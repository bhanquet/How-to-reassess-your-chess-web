/**
 * Tests chess-utils.js — uses the real chess.js v1 library (ESM).
 */
import { describe, it, expect } from 'vitest';
import {
    buildPlayableLines,
    createCustomLine,
    flattenVariationLines,
    getAlternativesAt,
    moveNumberLabel,
    validateLineMoves,
} from '../js/chess-utils.js';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('moveNumberLabel', () => {
    it('absPly 0 White to move → "1."', () => {
        expect(moveNumberLabel(0, START)).toBe('1.');
    });
    it('absPly 1 White to move → "1..."', () => {
        expect(moveNumberLabel(1, START)).toBe('1...');
    });
    it('absPly 2 White to move → "2."', () => {
        expect(moveNumberLabel(2, START)).toBe('2.');
    });
    it('absPly 0 Black to move (fullmove N=15) → "15..."', () => {
        const f = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 15';
        expect(moveNumberLabel(0, f)).toBe('15...');
    });
    it('absPly 1 Black to move → "16."', () => {
        const f = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 15';
        expect(moveNumberLabel(1, f)).toBe('16.');
    });
    it('empty FEN → ""', () => {
        expect(moveNumberLabel(0, '')).toBe('');
    });
});

describe('validateLineMoves', () => {
    it('legal SAN → kept as-is', () => {
        expect(validateLineMoves(START, ['e4', 'e5', 'Nf3'])).toEqual(['e4', 'e5', 'Nf3']);
    });
    it('illegal SAN → truncated at first invalid', () => {
        expect(validateLineMoves(START, ['e4', 'xe5', 'Nf3'])).toEqual(['e4']);
    });
    it('invalid FEN → []', () => {
        expect(validateLineMoves('not-a-fen', ['e4'])).toEqual([]);
    });
    it('null/undefined → []', () => {
        expect(validateLineMoves(START, null)).toEqual([]);
        expect(validateLineMoves(START, undefined)).toEqual([]);
    });
});

describe('flattenVariationLines', () => {
    it('no variation → only "main"', () => {
        const lines = flattenVariationLines(['e4', 'e5'], [], START);
        expect(lines.length).toBe(1);
        expect(lines[0].id).toBe('main');
        expect(lines[0].moves).toEqual(['e4', 'e5']);
    });
    it('one variation at ply 2 (Black 3rd move e5 → e6)', () => {
        const lines = flattenVariationLines(
            ['e4', 'e5', 'Nf3'],
            [{ branch_ply: 2, moves: ['e6', 'Nc3'], variations: [] }],
            START
        );
        expect(lines.length).toBe(2);
        expect(lines[1].id).toBe('main.0');
        expect(lines[1].moves).toEqual(['e4', 'e5', 'e6', 'Nc3']);
        expect(lines[1].absPly).toBe(2);
    });
});

describe('buildPlayableLines', () => {
    it('variation whose first move is illegal → removed entirely', () => {
        // e9 does not exist → truncated to [e4]; valid.length=1, line.absPly=1
        // → 1>1 false → variation removed.
        const lines = buildPlayableLines(
            START,
            ['e4', 'e5'],
            [{ branch_ply: 1, moves: ['e9', 'Nf3'], variations: [] }],
            START
        );
        expect(lines.length).toBe(1);
        expect(lines[0].id).toBe('main');
    });
    it('playable variation is kept', () => {
        const lines = buildPlayableLines(
            START,
            ['e4', 'e5'],
            [{ branch_ply: 1, moves: ['c5', 'Nf3'], variations: [] }],
            START
        );
        expect(lines.length).toBe(2);
        expect(lines[1].moves).toEqual(['e4', 'c5', 'Nf3']);
    });
});

describe('getAlternativesAt', () => {
    // Lines produced by flattenVariationLines, including nested branches.
    const lines = [
        { id: 'main', moves: ['e4', 'e5', 'Nf3'], absPly: 0, parentId: null, depth: 0, label: 'Main line' },
        { id: 'main.0', moves: ['e4', 'c5'], absPly: 1, parentId: 'main', depth: 1, label: '› Instead of 1...e5 : 1...c5 (1 move)' },
        { id: 'main.1', moves: ['e4', 'e5', 'Nc3'], absPly: 2, parentId: 'main', depth: 1, label: '› Instead of 2.Nf3 : 2.Nc3 (1 move)' },
        { id: 'main.1.0', moves: ['e4', 'e5', 'Nc3', 'Nc6'], absPly: 3, parentId: 'main.1', depth: 2, label: '›› Instead of 2...Nf6 : 2...Nc6 (1 move)' },
    ];

    it('returns lines whose branching point == currentPly', () => {
        const alts = getAlternativesAt(lines, 1);
        expect(alts).toHaveLength(1);
        expect(alts[0].lineId).toBe('main.0');
        expect(alts[0].san).toBe('c5');
        expect(alts[0].absPly).toBe(1);
        expect(alts[0].depth).toBe(1);
        expect(alts[0].length).toBe(2);
        expect(alts[0].label).toContain('1...c5');
    });

    it('handles nested branches (depth 2) at their own ply', () => {
        const alts = getAlternativesAt(lines, 3);
        expect(alts).toHaveLength(1);
        expect(alts[0].lineId).toBe('main.1.0');
        expect(alts[0].san).toBe('Nc6');
        expect(alts[0].depth).toBe(2);
    });

    it('multiple alternatives at the same ply', () => {
        const multi = lines.concat([
            { id: 'main.2', moves: ['e4', 'c6'], absPly: 1, parentId: 'main', depth: 1, label: '› Instead of 1...e5 : 1...c6 (1 move)' },
        ]);
        const alts = getAlternativesAt(multi, 1);
        expect(alts.map((a) => a.lineId)).toEqual(['main.0', 'main.2']);
    });

    it('no match → []', () => {
        expect(getAlternativesAt(lines, 4)).toEqual([]);
        expect(getAlternativesAt(lines, 99)).toEqual([]);
    });

    it('always excludes the main line', () => {
        expect(getAlternativesAt(lines, 0)).toEqual([]);
    });

    it('tolerates null/undefined lines', () => {
        expect(getAlternativesAt(null, 1)).toEqual([]);
        expect(getAlternativesAt(undefined, 1)).toEqual([]);
    });
});

describe('createCustomLine', () => {
    it('builds the line with explicit id and absPly=currentIndex', () => {
        const line = createCustomLine(['e4', 'e5', 'Nf3'], 2, 'Nc3', { id: 'custom-1', parentId: 'main', depth: 1 });
        expect(line.id).toBe('custom-1');
        expect(line.label).toBe('My variation : Nc3');
        expect(line.moves).toEqual(['e4', 'e5', 'Nc3']);
        expect(line.absPly).toBe(2);
        expect(line.parentId).toBe('main');
        expect(line.depth).toBe(1);
    });

    it('truncates moves before currentIndex and inserts the new move', () => {
        const line = createCustomLine(['d4', 'd5', 'c4', 'e6'], 2, 'Nf3');
        expect(line.moves).toEqual(['d4', 'd5', 'Nf3']);
        expect(line.absPly).toBe(2);
    });

    it('currentIndex 0 → new line from initial position', () => {
        const line = createCustomLine(['e4', 'e5'], 0, 'd4', { id: 'custom-0' });
        expect(line.moves).toEqual(['d4']);
        expect(line.absPly).toBe(0);
    });

    it('generates id via idPrefix+counter when id is absent', () => {
        const line = createCustomLine(['e4'], 1, 'c5', { idPrefix: 'custom', counter: 7 });
        expect(line.id).toBe('custom-7');
    });

    it('default parentId/depth values', () => {
        const line = createCustomLine(['e4'], 1, 'c5');
        expect(line.parentId).toBeNull();
        expect(line.depth).toBe(1);
    });

    it('stays pure: does not alter original baseMoves', () => {
        const base = ['e4', 'e5'];
        createCustomLine(base, 1, 'c5');
        expect(base).toEqual(['e4', 'e5']);
    });
});

describe('flattenVariationLines — label enrichment', () => {
    it('without comment or nags → historical format unchanged', () => {
        const lines = flattenVariationLines(
            ['e4', 'e5', 'Nf3'],
            [{ branch_ply: 2, moves: ['e6'], variations: [] }],
            START
        );
        expect(lines[1].label).toBe('› Instead of 2.Nf3 : 2.e6 (1 move)');
    });

    it('with comment → " — comment" suffix truncated to 80 chars', () => {
        const longComment = 'x'.repeat(120);
        const lines = flattenVariationLines(
            ['e4', 'e5', 'Nf3'],
            [{ branch_ply: 2, moves: ['e6'], variations: [], comment: longComment }],
            START
        );
        expect(lines[1].label.endsWith(' — ' + 'x'.repeat(80))).toBe(true);
        expect(lines[1].label).not.toContain('x'.repeat(81));
    });

    it('with nags → NAG symbols added', () => {
        const lines = flattenVariationLines(
            ['e4', 'e5', 'Nf3'],
            [{ branch_ply: 2, moves: ['e6'], variations: [], nags: [1, 3, 5] }],
            START
        );
        expect(lines[1].label.endsWith(' — ! !! !?')).toBe(true);
    });

    it('comment + nags combined', () => {
        const lines = flattenVariationLines(
            ['e4', 'e5', 'Nf3'],
            [{ branch_ply: 2, moves: ['e6'], variations: [], comment: 'solid', nags: [2] }],
            START
        );
        expect(lines[1].label.endsWith(' — solid ?')).toBe(true);
    });
});
