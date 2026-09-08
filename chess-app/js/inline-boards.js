/**
 * Playable inline diagrams (rendered directly in the text).
 * Thin wrapper: DOM construction + Map<num, PlayableBoard>.
 * Lazy initialization via IntersectionObserver: PlayableBoard (ChessBoard + Chess)
 * is only attached when the diagram enters the viewport. The wrappers and HTML
 * skeleton are always present.
 * Relies on `PlayableBoard` (chess.js v1 + cm-chessboard v8) imported as ESM
 * modules from playable-board.js; no global CDN dependency.
 */

import { inlineWrapperHTML } from './templates.js';
import { unpackDiagramData } from './chess-utils.js';
import { PlayableBoard } from './playable-board.js';

function resolversFor(num) {
    const wrapperSel = `.diagram-playable-wrapper[data-diagram="${num}"]`;
    const btn = (cls) => () => document.querySelector(`${wrapperSel} ${cls}`);
    return {
        boardEl: () => document.getElementById(`inline-board-${num}`),
        movesEl: () => document.getElementById(`inline-moves-${num}`),
        plyEl: () => document.getElementById(`inline-ply-${num}`),
        turnEl: () => document.getElementById(`inline-turn-${num}`),
        firstBtn: btn('.diag-first'),
        prevBtn: btn('.diag-prev'),
        nextBtn: btn('.diag-next'),
        lastBtn: btn('.diag-last'),
        varSelect: () => document.querySelector(`.diag-var-select[data-diagram="${num}"]`),
        varsBox: () => document.getElementById(`inline-vars-${num}`),
    };
}

export class InlineBoardManager {
    constructor() {
        /** num (string) -> PlayableBoard (attached on demand) */
        this.boards = new Map();
        /** num -> { initialFen, moves, variations, diagramPlyIndex } */
        this.pending = new Map();
        /** num -> skeleton wrapper HTMLDivElement */
        this.wrappers = new Map();
        this.diagrams = null;
        this.observer = null;
    }

    get(num) {
        return this.boards.get(num);
    }

    /** (Re)renders all inline diagrams found in `container`. */
    renderIn(container, diagrams) {
        // Cleanup old observer + previous boards
        this.observer?.disconnect();
        this.observer = null;
        this.boards.forEach(board => board.destroy());
        this.boards.clear();
        this.pending.clear();
        this.wrappers.clear();
        this.diagrams = diagrams || null;

        container.querySelectorAll('.diagram-inline').forEach(el => {
            const num = el.dataset.diagram;
            const {
                fen, initialFen, moves, variations, diagramPlyIndex,
                side, level, hasPosition,
            } = unpackDiagramData(diagrams?.[num]);

            const wrapper = document.createElement('div');
            wrapper.className = 'diagram-playable-wrapper';
            wrapper.dataset.diagram = num;
            wrapper.tabIndex = 0;

            let captionText = `Diagram ${num}`;
            if (side) captionText += ` — ${side === 'white' ? 'White' : 'Black'} to move`;
            if (level) captionText += ` [${level}]`;

            wrapper.innerHTML = inlineWrapperHTML(num, captionText, hasPosition);

            el.replaceWith(wrapper);

            this.wrappers.set(num, wrapper);
            this.pending.set(num, { initialFen, moves, variations, diagramPlyIndex });
        });

        if (this.wrappers.size === 0) return;

        // IntersectionObserver: attach on first visible pass.
        // Fallback for browsers without IO: attach immediately.
        if (typeof IntersectionObserver === 'undefined') {
            this.wrappers.forEach((_, num) => this._attachIfNeeded(num));
            return;
        }
        this.observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                const num = entry.target.dataset.diagram;
                this._attachIfNeeded(num);
                this.observer.unobserve(entry.target);
            }
        }, { rootMargin: '400px 0px', threshold: 0.01 });
        this.wrappers.forEach(w => this.observer.observe(w));
    }

    _attachIfNeeded(num) {
        if (this.boards.has(num)) return;
        const pending = this.pending.get(num);
        const wrapper = this.wrappers.get(num);
        if (!pending || !wrapper) return;
        const playable = new PlayableBoard(`inline-board-${num}`, resolversFor(num));
        playable.attach(pending.initialFen);
        playable.loadDiagram({
            initialFen: pending.initialFen,
            moves: pending.moves,
            variations: pending.variations,
            diagramPlyIndex: pending.diagramPlyIndex,
        });
        this.boards.set(num, playable);
    }

    switchLine(num, lineId, ply = null) {
        this._attachIfNeeded(num);
        this.boards.get(num)?.switchLine(lineId, ply);
    }

    /** Returns to the initial position (before any move). */
    goToStart(num) {
        this._attachIfNeeded(num);
        this.boards.get(num)?.goToStart();
    }

    /** Restores the main line to the diagram position in the book. */
    goToDiagramPosition(num) {
        this._attachIfNeeded(num);
        this.boards.get(num)?.goToDiagramPosition();
    }

    flip(num) {
        this._attachIfNeeded(num);
        this.boards.get(num)?.flip();
    }

    goToMove(num, index) {
        this._attachIfNeeded(num);
        this.boards.get(num)?.goToMove(index);
    }

    /** Current FEN of diagram `num` (attaches the board if needed). */
    getFen(num) {
        this._attachIfNeeded(num);
        try {
            return this.boards.get(num)?.game?.fen() || null;
        } catch (e) {
            return null;
        }
    }
}
