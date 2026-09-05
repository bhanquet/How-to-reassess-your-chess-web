/**
 * How to Reassess Your Chess - Interactive Application
 * Orchestrator: data loading, sections, events, keyboard.
 * Positions come from diagrams.json (read-only).
 */

import { InlineBoardManager } from './inline-boards.js';
import { ModalBoardManager } from './modal-board.js';
import { buildTOCFromNCX, buildTOCFromSections, closeSidebarMobile, markActiveNavItem, renderNavigation, setSidebarOpen } from './navigation.js';
import { renderSearchResults, searchSections } from './search.js';
import { errorHTML, loadingHTML, noResultsHTML, sectionHTML } from './templates.js';
import { getAlternativesAt, parsePlyOrNull } from './chess-utils.js';

class ChessApp {
    constructor() {
        this.currentSection = 0;
        this.bookData = null;
        this.diagrams = null;
        this.toc = null;
        this.inline = new InlineBoardManager();
        this.modal = new ModalBoardManager();
        this.activeBoardNum = null;
        this.init();
    }

    init() {
        this._initSidebarState();
        this._setupThemeToggle();
        this.loadBookData();
        this.setupEventListeners();
        this.modal.initialize();
        this._setupHashSync();
    }

    /** Initial sidebar state: visible on desktop, hidden on mobile. */
    _initSidebarState() {
        const sidebar = document.getElementById('sidebar');
        const scrim = document.getElementById('sidebar-scrim');
        if (!sidebar) return;
        const isMobile = window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
        if (!isMobile) {
            sidebar.classList.remove('hidden');
            if (scrim) scrim.setAttribute('aria-hidden', 'true');
        }
    }

    /** Manual light / dark / auto theme handling with persistence. */
    _setupThemeToggle() {
        const toggle = document.getElementById('theme-toggle');
        const options = document.getElementById('theme-options');
        if (!toggle || !options) return;

        const apply = (value) => {
            const html = document.documentElement;
            if (value === 'auto') {
                html.removeAttribute('data-theme');
            } else {
                html.setAttribute('data-theme', value);
            }
            try {
                localStorage.setItem('theme', value);
            } catch (e) { /* ignore */ }
            options.querySelectorAll('button').forEach(btn => {
                const selected = btn.dataset.value === value;
                btn.setAttribute('aria-selected', String(selected));
            });
            const labelBtn = options.querySelector(`button[data-value="${value}"]`);
            const label = labelBtn ? labelBtn.textContent : value;
            const labelEl = toggle.querySelector('.theme-toggle-label');
            if (labelEl) labelEl.textContent = label;
        };

        const saved = (() => {
            try { return localStorage.getItem('theme'); } catch (e) { return null; }
        })();
        apply(saved && ['light', 'dark', 'auto'].includes(saved) ? saved : 'auto');

        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const expanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', String(!expanded));
            options.hidden = expanded;
        });

        options.addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-value]');
            if (!btn) return;
            apply(btn.dataset.value);
            toggle.setAttribute('aria-expanded', 'false');
            options.hidden = true;
        });

        document.addEventListener('click', (e) => {
            if (!toggle.contains(e.target) && !options.contains(e.target)) {
                toggle.setAttribute('aria-expanded', 'false');
                options.hidden = true;
            }
        });

        options.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                toggle.setAttribute('aria-expanded', 'false');
                options.hidden = true;
                toggle.focus();
            }
        });
    }

    loadBookData() {
        const contentArea = document.getElementById('content-area');
        contentArea.innerHTML = loadingHTML();

        const fetchJSON = (url) => fetch(url).then(r => {
            if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
            return r.json();
        });

        // The NCX TOC is optional: a missing/invalid toc.json falls back to
        // the sections-derived TOC.
        const tocPromise = fetchJSON('data/toc.json').catch(() => null);

        Promise.all([
            fetchJSON('data/book_structure.json'),
            fetchJSON('data/diagrams.json'),
            tocPromise,
        ])
            .then(([bookData, diagrams, tocData]) => {
                this.bookData = bookData;
                this.diagrams = diagrams;
                this.toc = this._isValidNcxTree(tocData)
                    ? buildTOCFromNCX(tocData)
                    : buildTOCFromSections(bookData);
                renderNavigation(
                    document.getElementById('nav-tree'),
                    this.toc,
                    (section, anchor) => this.loadSection(section, anchor),
                );
                const restored = this._restoreSectionFromHashOrStorage();
                this.loadSection(restored.section, restored.anchor);
            })
            .catch(error => {
                console.error('Error loading book data:', error);
                contentArea.innerHTML = errorHTML(
                    `Unable to load book: ${error.message}`,
                    { label: 'Retry', onClick: () => this.loadBookData() },
                );
            });
    }

    /** True if `tocData` looks like the native NCX tree from toc.json. */
    _isValidNcxTree(tocData) {
        if (!Array.isArray(tocData) || !tocData.length) return false;
        const check = (node) => {
            if (!node || typeof node !== 'object') return false;
            if (typeof node.title !== 'string' || !node.title) return false;
            if (typeof node.src !== 'string' || !node.src) return false;
            if (!Array.isArray(node.children)) return false;
            return node.children.every(check);
        };
        return tocData.every(check);
    }

    /** Determine the starting point: hash → localStorage → section 0. */
    _restoreSectionFromHashOrStorage() {
        const hashMatch = window.location.hash.match(/^#s(\d+)(?:-([\w-]+))?$/);
        if (hashMatch) {
            const n = parseInt(hashMatch[1], 10);
            if (!Number.isNaN(n)) return { section: n, anchor: hashMatch[2] || null };
        }
        try {
            const saved = localStorage.getItem('currentSection');
            if (saved !== null) {
                const n = parseInt(saved, 10);
                if (!Number.isNaN(n)) return { section: n, anchor: null };
            }
        } catch (e) { /* localStorage may be blocked */ }
        return { section: 0, anchor: null };
    }

    loadSection(sectionNum, anchor = null) {
        if (!this.bookData || !this.bookData.sections) return;
        const totalSections = this.bookData.sections.length;
        sectionNum = Math.max(0, Math.min(sectionNum, totalSections - 1));
        this.currentSection = sectionNum;
        const section = this.bookData.sections[sectionNum];
        const contentArea = document.getElementById('content-area');
        contentArea.innerHTML = sectionHTML(section, sectionNum, totalSections);

        const bindNav = (id, delta) => {
            document.getElementById(id)?.addEventListener('click', () => this.loadSection(sectionNum + delta));
        };
        bindNav('prev-page', -1);
        bindNav('next-page', 1);
        bindNav('prev-page-bottom', -1);
        bindNav('next-page-bottom', 1);

        document.getElementById('main-content').scrollTop = 0;
        this.inline.renderIn(contentArea, this.diagrams);
        if (anchor) {
            // NCX deep link: scroll to the anchored heading once rendered.
            const target = document.getElementById(anchor);
            if (target) {
                requestAnimationFrame(() => {
                    target.scrollIntoView({ behavior: 'auto', block: 'start' });
                });
            }
        }
        markActiveNavItem(this.currentSection, anchor, this._isSectionInView(this.currentSection));
        const hash = anchor ? `#s${sectionNum}-${anchor}` : `#s${sectionNum}`;
        try {
            window.history.replaceState(null, '', hash);
            localStorage.setItem('currentSection', String(sectionNum));
        } catch (e) { /* ignore */ }
    }

    /** True if the TOC entry for `sectionNum` is already visible in the sidebar. */
    _isSectionInView(sectionNum) {
        const el = document.querySelector(`.nav-item[data-section="${sectionNum}"]`);
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return true;
        const sRect = sidebar.getBoundingClientRect();
        return rect.top >= sRect.top && rect.bottom <= sRect.bottom;
    }

    /**
     * Shared click dispatcher for move buttons, used by the modal move list
     * and the inline diagram move lists.
     *
     * `.move.var-jump` buttons (variation quick-jumps) are ALSO `.move[data-ply]`
     * (their data-ply = branching ply + 1), so they are intercepted FIRST and
     * routed to `onSwitchLine`. Plain `.move[data-ply]` buttons go to
     * `onGoToMove`. Returns true when the click was consumed by a move button,
     * so the caller can skip its own dispatch (e.g. the `.diag-btn` actions).
     */
    _handleMoveClick(e, { onSwitchLine, onGoToMove }) {
        const varJump = e.target.closest('.move.var-jump');
        if (varJump) {
            const lineId = varJump.dataset.line;
            const ply = parsePlyOrNull(varJump.dataset.ply);
            onSwitchLine(varJump, lineId, ply);
            return true;
        }
        const moveBtn = e.target.closest('.move[data-ply]');
        if (!moveBtn) return false;
        const ply = parsePlyOrNull(moveBtn.dataset.ply);
        if (ply !== null) onGoToMove(moveBtn, ply);
        return true;
    }

    /**
     * Keyboard navigation map (ArrowLeft/ArrowRight/Home/End) for a playable
     * board, relative to its current navigation state. Shared by the modal and
     * the focused inline diagram so both boards navigate identically.
     */
    _buildNavigationActions(board, goToMove) {
        return {
            ArrowLeft: () => goToMove(board.currentIndex - 1),
            ArrowRight: () => goToMove(board.currentIndex + 1),
            Home: () => goToMove(0),
            End: () => goToMove(board.allMoves.length),
        };
    }

    setupEventListeners() {
        document.getElementById('menu-toggle').addEventListener('click', () => {
            const sidebar = document.getElementById('sidebar');
            setSidebarOpen(sidebar.classList.contains('hidden'));
        });

        // Mobile scrim: click outside sidebar closes it
        document.getElementById('sidebar-scrim')?.addEventListener('click', () => {
            setSidebarOpen(false);
        });

        document.querySelector('.close-modal').addEventListener('click', () => {
            this.modal.close();
        });

        window.addEventListener('click', (e) => {
            const modal = document.getElementById('chess-modal');
            if (e.target === modal) this.modal.close();
        });

        // Minimal modal focus trap (Tab/Shift+Tab cycle).
        document.getElementById('chess-modal').addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;
            const focusables = Array.from(
                document.querySelectorAll(
                    '#chess-modal button, #chess-modal select, #chess-modal [tabindex]:not([tabindex="-1"])'
                )
            ).filter(el => !el.disabled && el.offsetParent !== null);
            if (focusables.length === 0) return;
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        });

        document.getElementById('flip-board').addEventListener('click', () => {
            this.modal.flip();
        });

        document.getElementById('position-board')?.addEventListener('click', () => {
            this.modal.goToStart();
        });

        document.getElementById('undo-board')?.addEventListener('click', () => {
            this.modal.undo();
        });

        document.getElementById('reset-board').addEventListener('click', () => {
            this.modal.goToDiagramPosition();
        });

        document.getElementById('modal-var-select')?.addEventListener('change', (e) => {
            this.modal.switchLine(e.target.value);
        });

        document.getElementById('modal-first')?.addEventListener('click', () => this.modal.goToMove(0));
        document.getElementById('modal-prev')?.addEventListener('click', () => this.modal.goToMove(this.modal.state.currentIndex - 1));
        document.getElementById('modal-next')?.addEventListener('click', () => this.modal.goToMove(this.modal.state.currentIndex + 1));
        document.getElementById('modal-last')?.addEventListener('click', () => this.modal.goToMove(this.modal.state.allMoves.length));

        // Click on a modal move: display the position (shared dispatcher
        // routes `.move.var-jump` variation jumps BEFORE `.move[data-ply]`).
        document.getElementById('move-list')?.addEventListener('click', (e) => {
            this._handleMoveClick(e, {
                onSwitchLine: (_btn, lineId, ply) => this.modal.switchLine(lineId, ply),
                onGoToMove: (_btn, ply) => this.modal.goToMove(ply),
            });
        });

        document.getElementById('search-btn').addEventListener('click', () => this.performSearch());
        const searchInput = document.getElementById('search-input');
        let searchDebounce = null;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchDebounce);
            const q = searchInput.value.trim();
            if (q.length < 2) return;
            searchDebounce = setTimeout(() => this.performSearch(q), 250);
        });
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchDebounce);
                this.performSearch();
            } else if (e.key === 'Escape') {
                searchInput.value = '';
                clearTimeout(searchDebounce);
                this.loadSection(this.currentSection);
            }
        });

        const contentArea = document.getElementById('content-area');

        contentArea.addEventListener('click', (e) => {
            // Move clicks: shared dispatcher routes `.move.var-jump` variation
            // jumps BEFORE plain `.move[data-ply]` moves. Focus the wrapper so
            // keyboard navigation follows the clicked diagram.
            const wrapper = e.target.closest('.diagram-playable-wrapper');
            const num = wrapper?.dataset.diagram;
            const handled = this._handleMoveClick(e, {
                onSwitchLine: (_btn, lineId, ply) => {
                    if (!num) return;
                    wrapper.focus({ preventScroll: true });
                    this.inline.switchLine(num, lineId, ply);
                },
                onGoToMove: (_btn, ply) => {
                    if (!num) return;
                    wrapper.focus({ preventScroll: true });
                    this.inline.goToMove(num, ply);
                },
            });
            if (handled) return;

            const btn = e.target.closest('.diag-btn');
            const numBtn = btn?.dataset.diagram;
            if (!numBtn) return;

            const diagWrapper = contentArea.querySelector(`.diagram-playable-wrapper[data-diagram="${numBtn}"]`);
            if (diagWrapper) diagWrapper.focus({ preventScroll: true });

            const d = this.inline.get(numBtn);
            const actions = {
                'diag-first': () => this.inline.goToMove(numBtn, 0),
                'diag-prev': () => d && this.inline.goToMove(numBtn, d.currentIndex - 1),
                'diag-flip': () => this.inline.flip(numBtn),
                'diag-next': () => d && this.inline.goToMove(numBtn, d.currentIndex + 1),
                'diag-last': () => d && this.inline.goToMove(numBtn, d.allMoves.length),
                'diag-position': () => this.inline.goToStart(numBtn),
                'diag-reset': () => {
                    this.inline.goToDiagramPosition(numBtn);
                    const select = contentArea.querySelector(`.diag-var-select[data-diagram="${numBtn}"]`);
                    if (select) select.value = 'main';
                },
                'diag-expand': () => this.modal.show(numBtn, this.diagrams?.[numBtn], {
                    opener: btn,
                    startIndex: d ? d.currentIndex : 0,
                }),
            };
            for (const [cls, action] of Object.entries(actions)) {
                if (btn.classList.contains(cls)) {
                    action();
                    break;
                }
            }
        });

        contentArea.addEventListener('change', (e) => {
            if (e.target.classList && e.target.classList.contains('diag-var-select')) {
                const num = e.target.dataset.diagram;
                if (num) this.inline.switchLine(num, e.target.value);
            }
        });

        // `mouseover` is more reliable than `focusin/focusout` to only lose
        // the active board when the mouse actually leaves the wrapper.
        contentArea.addEventListener('mouseover', (e) => {
            const wrapper = e.target.closest('.diagram-playable-wrapper');
            if (wrapper) this.activeBoardNum = wrapper.dataset.diagram;
        });
        contentArea.addEventListener('mouseleave', (e) => {
            const wrapper = e.target.closest('.diagram-playable-wrapper');
            if (wrapper) this.activeBoardNum = null;
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (this.modal.isOpen) this.modal.close();
                return;
            }

            const modalNav = this._buildNavigationActions(
                this.modal.state,
                (index) => this.modal.goToMove(index),
            );
            if (this.modal.isOpen && modalNav[e.key]) {
                e.preventDefault();
                modalNav[e.key]();
                return;
            }

            const wrapper = document.activeElement?.closest('.diagram-playable-wrapper');
            const focusedBoardNum = wrapper?.dataset.diagram ?? null;
            const inlineData = focusedBoardNum ? this.inline.get(focusedBoardNum) : null;
            const inlineNav = inlineData
                ? this._buildNavigationActions(
                    inlineData,
                    (index) => this.inline.goToMove(focusedBoardNum, index),
                )
                : null;
            if (inlineNav && inlineNav[e.key]) {
                e.preventDefault();
                inlineNav[e.key]();
                return;
            }

            if (e.key === 'v' || e.key === 'V') {
                const tag = (e.target.tagName || '').toLowerCase();
                if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
                const board = this.modal.isOpen ? this.modal.state : (this.activeBoardNum ? this.inline.get(this.activeBoardNum) : null);
                if (!board) return;
                const cycle = (getAlternativesAt(board.lines, board.currentIndex) || [])
                    .filter((a) => !String(a.lineId).startsWith('custom-'));
                if (cycle.length === 0) return;
                const idx = cycle.findIndex((a) => a.lineId === board.currentLineId);
                const next = cycle[(idx + 1) % cycle.length];
                e.preventDefault();
                if (this.modal.isOpen) {
                    this.modal.switchLine(next.lineId, next.absPly + 1);
                } else {
                    this.inline.switchLine(this.activeBoardNum, next.lineId, next.absPly + 1);
                }
                return;
            }

            if (e.key === 'ArrowLeft') this.loadSection(this.currentSection - 1);
            if (e.key === 'ArrowRight') this.loadSection(this.currentSection + 1);
        });
    }

    /** React to hash changes (#sN / #sN-anchor) entered in the URL bar. */
    _setupHashSync() {
        window.addEventListener('hashchange', () => {
            const restored = this._restoreSectionFromHashOrStorage();
            if (restored.section !== this.currentSection) {
                this.loadSection(restored.section, restored.anchor);
            }
        });
    }

    performSearch(queryOverride) {
        const rawQuery = (queryOverride ?? document.getElementById('search-input').value).trim();
        if (!rawQuery || !this.bookData) return;
        const { results } = searchSections(this.bookData, rawQuery);
        const contentArea = document.getElementById('content-area');
        if (results.length > 0) {
            renderSearchResults(contentArea, results, rawQuery,
                (section) => this.loadSection(section));
        } else {
            contentArea.innerHTML = noResultsHTML(rawQuery);
        }
    }

    showError(message, retry) {
        const contentArea = document.getElementById('content-area');
        contentArea.innerHTML = errorHTML(message, retry);
        if (retry) {
            contentArea.querySelector('.error-action')?.addEventListener('click', retry.onClick);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.chessApp = new ChessApp();
});
