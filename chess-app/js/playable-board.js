/**
 * Shared core logic of a playable chessboard (inline or modal).
 * Wraps ONE Chess instance (chess.js v1) + ONE Chessboard instance
 * (cm-chessboard v8) + navigation state (moves, variations).
 *
 * The official `Markers`, `PromotionDialog` and `Accessibility` extensions
 * replace the old [data-square] hack (chessboard.js + jQuery).
 * The public API (`attach`, `loadDiagram`, `goToMove`, `undo`, `switchLine`,
 * `goToStart`, `goToDiagramPosition`, `flip`, `destroy`, `_handleMove`,
 * `_afterPositionChange`) is shared by `inline-boards.js` and `modal-board.js`,
 * which only delegate.
 */

import { Chess } from 'chess.js';
import {
    Chessboard,
    COLOR,
    INPUT_EVENT_TYPE,
    FEN,
} from 'cm-chessboard';
import { Markers, MARKER_TYPE } from 'cm-chessboard/src/extensions/markers/Markers.js';
import { Arrows, ARROW_TYPE } from 'cm-chessboard/src/extensions/arrows/Arrows.js';
import { PromotionDialog } from 'cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js';
import { Accessibility } from 'cm-chessboard/src/extensions/accessibility/Accessibility.js';

import { DEFAULT_START_FEN } from './config.js';
import {
    buildPlayableLines,
    createCustomLine,
    getAlternativesAt,
} from './chess-utils.js';
import { buildMoveListHTML, variationOptionsHTML } from './templates.js';

/** Piece animation speed (ms): smooth without being sluggish. */
const ANIM_DURATION = 220;

/** Detects whether the user prefers reduced motion. */
function prefersReducedMotion() {
    return typeof window !== 'undefined'
        && !!window.matchMedia
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function normalizeFen(fen) {
    return (fen && fen !== 'start') ? fen : DEFAULT_START_FEN;
}

/** Shows a temporary toast at the bottom of the screen (illegal move feedback, etc.). */
function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    if (typeof navigator !== 'undefined' && navigator.vibrate) {
        try { navigator.vibrate(50); } catch (e) { /* ignore */ }
    }
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => { toast.hidden = true; }, 2000);
}

export class PlayableBoard {
    /**
     * @param {string} boardId - DOM id of the board container.
     * @param {object} resolve - DOM accessors (inline nodes are recreated on
     *   every section change, so we retrieve them via accessors).
     */
    constructor(boardId, resolve) {
        this.boardId = boardId;
        this.resolve = resolve;
        this.board = null;
        this.markers = null;
        this.arrows = null;
        this.game = null;
        this.initialFen = DEFAULT_START_FEN;
        /** Moves of the main line (reference for `reset` / main-line nav). */
        this.mainLineMoves = [];
        /** Absolute ply of the diagram position in the book (the 📖 marker). */
        this.diagramPlyIndex = 0;
        this.allMoves = [];
        this.currentIndex = 0;
        this.lines = [];
        this.currentLineId = 'main';
        this.customLines = [];
        this._customCounter = 0;
        /** Timestamp (ms) of the last goToMove(), for the 30 ms held-key debounce. */
        this._lastGoTo = 0;
    }

    /** Creates the Chessboard + Chess and enables input. Called once. */
    attach(fen) {
        const realFen = normalizeFen(fen);
        const game = new Chess();
        try {
            game.load(realFen);
        } catch (e) {
            console.error('Invalid FEN for board', this.boardId, realFen);
        }
        this.game = game;

        // Persistent flip per diagram (key local to boardId).
        const flipKey = `board:flip:${this.boardId}`;
        const savedFlip = this._loadPref(flipKey);
        const orientation = savedFlip === 'b' ? COLOR.black : COLOR.white;

        const el = this.resolve.boardEl?.();
        if (!el) {
            console.error('No board element for', this.boardId);
            return;
        }

        const noAnimation = prefersReducedMotion();
        this.board = new Chessboard(el, {
            position: realFen,
            orientation,
            responsive: true,
            assetsUrl: './cm-chessboard/',
            style: {
                animationDuration: noAnimation ? 0 : ANIM_DURATION,
                pieces: { file: 'pieces/staunty.svg' },
            },
            extensions: [
                { class: Markers, props: { autoMarkers: null } },
                { class: Arrows },
                { class: PromotionDialog },
                { class: Accessibility, props: { visuallyHidden: true } },
            ],
        });
        this.markers = this.board.getExtension(Markers);
        this.arrows = this.board.getExtension(Arrows);
        // Input is enabled by `_enableInputForTurn()` (called from
        // `loadDiagram()`), not here: cm-chessboard throws if enableMoveInput
        // is called twice without disableMoveInput in between.
    }

    /** Enables input for the side to move. Idempotent. */
    _enableInputForTurn() {
        if (!this.board) return;
        const turn = this.game?.turn() || COLOR.white;
        // cm-chessboard throws if enableMoveInput is called without a prior disable
        if (this.board.isMoveInputEnabled?.()) {
            this.board.disableMoveInput();
        }
        this.board.enableMoveInput((event) => this._onInput(event), turn);
    }

    /** cm-chessboard event handler. */
    _onInput(event) {
        if (!this.game) return false;

        if (event.type === INPUT_EVENT_TYPE.movingOverSquare) {
            return; // ignore
        }

        if (event.type === INPUT_EVENT_TYPE.moveInputStarted) {
            const piece = this.game.get(event.squareFrom);
            const turn = this.game.turn();
            const isMine = piece && (
                (turn === 'w' && piece.color === 'w') ||
                (turn === 'b' && piece.color === 'b')
            );
            if (!isMine) return false;
            // Highlight legal moves
            const moves = this.game.moves({ square: event.squareFrom, verbose: true });
            if (this.markers) {
                for (const m of moves) {
                    this.markers.addMarker(MARKER_TYPE.dot, m.to);
                }
            }
            return moves.length > 0;
        }

        if (event.type === INPUT_EVENT_TYPE.validateMoveInput) {
            return this._handleMove(event.squareFrom, event.squareTo, {
                allowPromotion: true,
                event,
            });
        }

        if (event.type === INPUT_EVENT_TYPE.moveInputFinished) {
            // Clean up legal-move dots after the move
            if (this.markers) {
                this.markers.removeMarkers(MARKER_TYPE.dot);
            }
            // Re-enable input for the new side to move
            this._enableInputForTurn();
        }
    }

    /**
     * Plays a move `from -> to` (mouse or click-click), handles promotion.
     * Returns `true` if the move is played, `false` otherwise.
     */
    _handleMove(from, to, { allowPromotion = false, event = null } = {}) {
        if (!this.game) return false;

        // chess.js v1: move() throws on an illegal move
        let move = null;
        try {
            move = this.game.move({ from, to, promotion: 'q' });
        } catch (e) {
            move = null;
        }

        // If not played and promotion is possible → show the dialog
        if (!move && allowPromotion) {
            let legalPromos = [];
            try {
                legalPromos = this.game.moves({ square: from, verbose: true })
                    .filter(m => m.to === to && m.promotion);
            } catch (e) {
                legalPromos = [];
            }
            if (legalPromos.length > 0) {
                return this._askPromotion(from, to, this.game.turn(), event);
            }
        }

        if (!move) {
            // Illegal move → visual reset after animation + feedback
            const board = event?.chessboard || this.board;
            if (board && board.state?.moveInputProcess) {
                board.state.moveInputProcess.then(() => {
                    board.setPosition(this.game.fen(), true);
                });
            }
            showToast('Illegal move');
            return false;
        }

        // Move OK
        this._commitMove(move);
        // Sync board after animation
        const board = event?.chessboard || this.board;
        if (board && board.state?.moveInputProcess) {
            board.state.moveInputProcess.then(() => {
                board.setPosition(this.game.fen(), true).then(() => {
                    this._paintHighlights();
                });
            });
        }
        return true;
    }

    /** Records a successful move into the navigation history. */
    _commitMove(move) {
        const ply = this.currentIndex;
        const baseBefore = this.allMoves.slice(); // copy for createCustomLine
        const forwardSan = this.allMoves[ply];

        if (this.currentIndex < this.allMoves.length) {
            this.allMoves = this.allMoves.slice(0, this.currentIndex);
        }
        this.allMoves.push(move.san);
        this.currentIndex = this.allMoves.length;

        // Novelty detection: move differs from the forward line, or
        // (at end of line) move is absent from known book alternatives.
        let isNovelty = false;
        if (forwardSan !== undefined) {
            isNovelty = move.san !== forwardSan;
        } else {
            const alts = getAlternativesAt(this.lines, ply);
            isNovelty = !alts.some((a) => a.san === move.san);
        }

        if (isNovelty) {
            const line = createCustomLine(baseBefore, ply, move.san, {
                idPrefix: 'custom',
                counter: ++this._customCounter,
                parentId: this.currentLineId,
            });
            this.customLines.push(line);
            this.lines.push(line);
            this.currentLineId = line.id;
            this._syncVarSelect();
        }

        this._afterPositionChange();
    }

    /** Shows the cm-chessboard promotion dialog. */
    _askPromotion(from, to, color, event) {
        const board = event?.chessboard || this.board;
        if (!board || typeof board.showPromotionDialog !== 'function') {
            // Fallback: queen
            return this._tryPromote(from, to, 'q');
        }
        board.showPromotionDialog(to, color, (result) => {
            if (result && result.type === 'pieceSelected' && result.piece) {
                const piece = result.piece.charAt(1); // 'wq' → 'q'
                this._tryPromote(from, to, piece);
            } else {
                // Cancelled: reset the board
                board.setPosition(this.game.fen(), true);
            }
        });
        return true;
    }

    /** Tries a move with a given promotion piece. */
    _tryPromote(from, to, promo) {
        let move = null;
        try {
            move = this.game.move({ from, to, promotion: promo });
        } catch (e) {
            move = null;
        }
        if (move) {
            this._commitMove(move);
            if (this.board) {
                this.board.setPosition(this.game.fen(), true).then(() => {
                    this._paintHighlights();
                });
            }
        } else {
            if (this.board) this.board.setPosition(this.game.fen(), true);
        }
    }

    destroy() {
        if (this.board && typeof this.board.destroy === 'function') {
            try { this.board.destroy(); } catch (e) { /* ignore */ }
        }
        this.board = null;
        this.markers = null;
        this.arrows = null;
    }

    /**
     * (Re)loads playable lines: main line + variations (flattened tree).
     * Only lines whose branching point is replayable are kept.
     */
    loadDiagram({ initialFen, moves = null, variations = [], diagramPlyIndex = 0 }) {
        const realFen = normalizeFen(initialFen);
        this.initialFen = realFen;
        this.lines = buildPlayableLines(realFen, moves, variations);
        this.customLines = [];
        this._customCounter = 0;
        this.mainLineMoves = this.lines[0].moves.slice();
        this.diagramPlyIndex = Math.min(Math.max(0, diagramPlyIndex), this.mainLineMoves.length);
        this.allMoves = this.mainLineMoves.slice();
        this.currentLineId = 'main';
        this._syncVarSelect();
        this.goToMove(this.diagramPlyIndex);
        this._enableInputForTurn();
    }

    /** Undo the last played move. */
    undo() {
        if (!this.allMoves.length || !this.initialFen) return;
        this.allMoves.pop();
        this.goToMove(this.allMoves.length);
    }

    switchLine(lineId, gotoPly = null) {
        const line = (this.lines || []).find(l => l.id === lineId);
        if (!line) return;
        this.allMoves = line.moves.slice();
        this.currentLineId = line.id;
        // Branching point of the line (`branchPly`, i.e. `line.absPly`); the
        // caller's `gotoPly` (a current-ply target) always wins when given.
        const branchPly = line.absPly;
        const target = gotoPly ?? (line.id === 'main'
            ? Math.min(Math.max(0, this.diagramPlyIndex), this.allMoves.length)
            : Math.min(branchPly, this.allMoves.length));
        // force: the requested jump (often branching ply + 1) must not be
        // swallowed by the goToMove anti-debounce guard.
        this.goToMove(target, true);
    }

    /** Restores the main line to the diagram position in the book. */
    goToDiagramPosition() {
        this.allMoves = this.mainLineMoves.slice();
        this.currentLineId = 'main';
        // Purge custom variations (created by the user).
        this.customLines = [];
        if (this.lines && this.lines.length) {
            this.lines = this.lines.filter((l) => !String(l.id || '').startsWith('custom-'));
        }
        this._syncVarSelect();
        this.goToMove(this.diagramPlyIndex);
    }

    /** Returns to the initial position (before any move). */
    goToStart() {
        this.goToMove(0);
    }

    flip() {
        if (!this.board || typeof this.board.setOrientation !== 'function') return;
        const current = this.board.getOrientation ? this.board.getOrientation() : COLOR.white;
        const next = current === COLOR.white ? COLOR.black : COLOR.white;
        this.board.setOrientation(next);
        try {
            localStorage.setItem(`board:flip:${this.boardId}`, next === COLOR.black ? 'b' : 'w');
        } catch (e) { /* ignore */ }
    }

    /** Reads a local preference (board:xxx). */
    _loadPref(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    goToMove(index, force = false) {
        if (!this.game || !this.board) return;
        // Anti-repeat debounce: avoids replaying N moves on each held-key tick.
        // `force` (switchLine / variation jumps) bypasses the guard — without
        // it, the goToMove immediately following a switchLine (which sets
        // `_lastGoTo` through a non-forced call) would fall inside the 30 ms
        // window and be swallowed.
        const now = Date.now();
        if (!force && now - this._lastGoTo < 30) return;
        this._lastGoTo = now;
        index = Math.max(0, Math.min(index, this.allMoves.length));
        // Rebuild the game and replay moves.
        const game = new Chess();
        try {
            game.load(this.initialFen);
        } catch (e) { return; }
        for (let i = 0; i < index; i++) {
            try { game.move(this.allMoves[i]); } catch (e) { break; }
        }
        this.game = game;
        this.currentIndex = index;
        // Transition animation.
        this.board.setPosition(game.fen(), true).then(() => {
            this._afterPositionChange();
        });
    }

    updateMoveList() {
        const movesEl = this.resolve.movesEl?.();
        if (!movesEl) return;
        // Book alternatives at the current ply (fork), excluding the current line
        // and custom variations (these are continuations, not forks).
        const alts = (getAlternativesAt(this.lines, this.currentIndex) || [])
            .filter((a) => a.lineId !== this.currentLineId)
            .filter((a) => !String(a.lineId).startsWith('custom-'));
        movesEl.innerHTML = buildMoveListHTML(
            this.allMoves, this.currentIndex, this.initialFen,
            this.currentLineId === 'main' ? this.diagramPlyIndex : null,
            alts
        );
        // NOTE: we do NOT call `current.scrollIntoView()` here — with
        // `block: 'nearest'`, when the move-list fits within its max-height
        // (≤ 1-2 moves), the browser scrolls up to the next scrollable ancestor,
        // which is the whole page, causing a scroll "snap" when the IO attaches
        // a board. The `.current-move` CSS class is enough to visually mark the
        // current move.
        const moves = movesEl;
        if (moves && moves.scrollHeight > moves.clientHeight) {
            // Internally scrollable list: center the current move WITHOUT
            // triggering page scroll.
            const current = movesEl.querySelector('.current-move');
            if (current) {
                const top = current.offsetTop - moves.offsetTop;
                const target = top - (moves.clientHeight - current.offsetHeight) / 2;
                moves.scrollTop = Math.max(0, target);
            }
        }
    }

    _syncVarSelect() {
        const select = this.resolve.varSelect?.();
        const varsBox = this.resolve.varsBox?.();
        if (!select || !varsBox) return;
        if (this.lines.length > 1) {
            select.innerHTML = variationOptionsHTML(this.lines);
            // Custom variations are in this.lines: preserve current selection if it
            // still exists, otherwise fall back to 'main'.
            const current = this.currentLineId;
            select.value = this.lines.some((l) => l.id === current) ? current : 'main';
            varsBox.hidden = false;
        } else {
            varsBox.hidden = true;
        }
    }

    _refreshMeta() {
        const boardEl = this.resolve.boardEl?.();
        if (boardEl && this.game) {
            const white = this.game.turn() === 'w';
            const num = boardEl.id.startsWith('inline-board-')
                ? boardEl.id.replace('inline-board-', '')
                : null;
            const label = num
                ? `${white ? 'White' : 'Black'} to move — diagram ${num}`
                : `${white ? 'White' : 'Black'} to move — enlarged board`;
            boardEl.setAttribute('aria-label', label);
        }

        const plyEl = this.resolve.plyEl?.();
        if (plyEl) {
            const base = this.allMoves.length === 0
                ? 'Initial position'
                : `Move ${this.currentIndex} / ${this.allMoves.length}`;
            let variants = 0;
            try {
                variants = getAlternativesAt(this.lines, this.currentIndex)
                    .filter((a) => !String(a.lineId).startsWith('custom-')).length;
            } catch (e) {
                variants = 0;
            }
            plyEl.textContent = variants > 0
                ? `${base} · ${variants} variation${variants > 1 ? 's' : ''}`
                : base;
        }
        const turnEl = this.resolve.turnEl?.();
        if (turnEl && this.game) {
            const white = this.game.turn() === 'w';
            turnEl.innerHTML = `<span class="dot ${white ? 'white' : 'black'}"></span> ${white ? 'White to move' : 'Black to move'}${this.game.inCheck() ? ' — check!' : ''}`;
        }
        const atStart = this.currentIndex <= 0;
        const atEnd = this.currentIndex >= this.allMoves.length;
        this.resolve.firstBtn?.()?.toggleAttribute('disabled', atStart);
        this.resolve.prevBtn?.()?.toggleAttribute('disabled', atStart);
        this.resolve.nextBtn?.()?.toggleAttribute('disabled', atEnd);
        this.resolve.lastBtn?.()?.toggleAttribute('disabled', atEnd);
    }

    /** Highlights the last move + king in check via the Markers extension. */
    _paintHighlights() {
        if (!this.markers || !this.game) return;
        this.markers.removeMarkers(MARKER_TYPE.framePrimary);
        this.markers.removeMarkers(MARKER_TYPE.frameDanger);
        this.markers.removeMarkers(MARKER_TYPE.square);

        const hist = this.game.history({ verbose: true });
        const last = hist[hist.length - 1];
        if (last) {
            this.markers.addMarker(MARKER_TYPE.framePrimary, last.from);
            this.markers.addMarker(MARKER_TYPE.framePrimary, last.to);
        }
        if (this.game.inCheck()) {
            const turn = this.game.turn();
            const board = this.game.board();
            for (let r = 0; r < 8; r++) {
                for (let f = 0; f < 8; f++) {
                    const p = board[r][f];
                    if (p && p.type === 'k' && p.color === turn) {
                        const sq = 'abcdefgh'[f] + (8 - r);
                        this.markers.addMarker(MARKER_TYPE.frameDanger, sq);
                    }
                }
            }
        }
    }

    /** Call after every position change. */
    _afterPositionChange() {
        this.updateMoveList();
        this._refreshMeta();
        this._paintHighlights();
        this._paintVariationArrows();
    }

    /**
     * Draws up to 3 arrows (ARROW_TYPE.secondary) on the from→to squares of
     * book alternative moves available at the current position. Custom
     * variations (the current line itself) are skipped. Must never throw:
     * any error is swallowed.
     */
    _paintVariationArrows() {
        if (!this.arrows || !this.game) return;
        try {
            this.arrows.removeArrows();
            const alternatives = getAlternativesAt(this.lines, this.currentIndex);
            let drawn = 0;
            for (const alt of alternatives) {
                if (drawn >= 3) break;
                if (String(alt.lineId).startsWith('custom-')) continue; // current line, not an alternative
                const fromTo = this._resolveArrow(alt.san);
                if (fromTo) {
                    this.arrows.addArrow(ARROW_TYPE.secondary, fromTo.from, fromTo.to);
                    drawn++;
                }
            }
        } catch (e) {
            // Never crash the board because of an arrow issue.
        }
    }

    /** Resolves a SAN into {from,to} squares on a copy of the current position. */
    _resolveArrow(san) {
        if (!san || !this.game) return null;
        let clone;
        try {
            clone = new Chess();
            clone.load(this.game.fen());
        } catch (e) {
            return null;
        }
        try {
            const legal = clone.moves({ verbose: true });
            const m = legal.find((mv) => mv.san === san);
            return m ? { from: m.from, to: m.to } : null;
        } catch (e) {
            return null;
        }
    }
}
