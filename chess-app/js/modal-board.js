/**
 * Enlarged modal chessboard (draggable, with moves and variations).
 * Thin wrapper: open/close cycle + delegation to a single PlayableBoard.
 * All board logic lives in playable-board.js.
 * Relies on `PlayableBoard` (chess.js v1 + cm-chessboard v8) imported as ESM
 * modules from playable-board.js; no global CDN dependency.
 */

import { DEFAULT_START_FEN } from './config.js';
import { unpackDiagramData } from './chess-utils.js';
import { PlayableBoard } from './playable-board.js';

const modalResolvers = {
    boardEl: () => document.getElementById('chess-board'),
    movesEl: () => document.getElementById('move-list'),
    plyEl: () => document.getElementById('modal-ply'),
    turnEl: () => document.getElementById('modal-turn'),
    firstBtn: () => document.getElementById('modal-first'),
    prevBtn: () => document.getElementById('modal-prev'),
    nextBtn: () => document.getElementById('modal-next'),
    lastBtn: () => document.getElementById('modal-last'),
    varSelect: () => document.getElementById('modal-var-select'),
    varsBox: () => document.getElementById('modal-vars'),
};

export class ModalBoardManager {
    constructor() {
        this.playable = new PlayableBoard('chess-board', modalResolvers);
        this.returnFocusTo = null;
    }

    /**
     * The underlying PlayableBoard. This getter exists for app.js, which reads
     * the navigation state as `modal.state.currentIndex / .allMoves`.
     */
    get state() {
        return this.playable;
    }

    /** Underlying chess.js `Chess` instance (direct game reads). */
    get chess() {
        return this.playable.game;
    }

    /** Underlying cm-chessboard instance (direct board reads). */
    get board() {
        return this.playable.board;
    }

    get isOpen() {
        const el = document.getElementById('chess-modal');
        return !!el && el.getAttribute('aria-hidden') === 'false';
    }

    open() {
        const modal = document.getElementById('chess-modal');
        modal.style.display = 'block';
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');
        // Force board resize after the modal is displayed
        if (this.playable.board && typeof this.playable.board.resize === 'function') {
            requestAnimationFrame(() => this.playable.board.resize());
        }
        // Initial focus on the board
        const content = modal.querySelector('.modal-content');
        content?.focus();
    }

    close() {
        const modal = document.getElementById('chess-modal');
        if (!modal) return;
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
        // Return focus to the element that opened the modal
        if (this.returnFocusTo && document.contains(this.returnFocusTo)) {
            this.returnFocusTo.focus();
        }
        this.returnFocusTo = null;
    }

    initialize() {
        this.playable.attach(DEFAULT_START_FEN);
        this.playable.loadDiagram({
            initialFen: DEFAULT_START_FEN,
            moves: [],
            variations: [],
            diagramPlyIndex: 0,
        });
    }

    /** Shows diagram `num` in the modal (preserving the inline index). */
    show(num, diagramData, opts = {}) {
        const title = document.getElementById('diagram-title');
        const { initialFen, moves, variations, diagramPlyIndex } = unpackDiagramData(diagramData);

        title.textContent = `Diagram ${num}`;
        this.returnFocusTo = opts.opener || document.activeElement;

        this.playable.loadDiagram({ initialFen, moves, variations, diagramPlyIndex });
        // Preserve the current inline index if provided
        if (typeof opts.startIndex === 'number' && opts.startIndex >= 0) {
            this.goToMove(opts.startIndex);
        }

        this.open();
        this.updateMoveList();
    }

    /** Returns to the initial position (before any move). */
    goToStart() {
        this.playable.goToStart();
    }

    switchLine(lineId, ply = null) {
        this.playable.switchLine(lineId, ply);
    }

    /** Restores the main line to the diagram position in the book. */
    goToDiagramPosition() {
        this.playable.goToDiagramPosition();
    }

    /** Undo the last played move. */
    undo() {
        this.playable.undo();
    }

    flip() {
        this.playable.flip();
    }

    goToMove(index) {
        this.playable.goToMove(index);
    }

    updateMoveList() {
        this.playable.updateMoveList();
    }
}
