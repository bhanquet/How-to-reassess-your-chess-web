/**
 * HTML builders (pure strings, no DOM) for sections, inline diagrams,
 * search and errors.
 */

import { moveNumberLabel } from './chess-utils.js';

/** Small HTML escape for generated labels. */
export function escapeHtml(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** List of clickable moves with the current move highlighted (modern style).
 *
 * Each move is a <button class="move" data-ply="N"> where N = ply reached
 * after this move (1..moves.length). A "start" button (data-ply="0")
 * represents the initial position. `diagramPly` (optional) marks the
 * diagram position in the book with a 📖 marker.
 */
export function buildMoveListHTML(moves, currentIndex, initialFen = null, diagramPly = null, alternatives = []) {
    const list = moves || [];
    let html;
    const atStart = currentIndex === 0;
    const startAria = atStart ? ' aria-current="step"' : '';
    if (list.length === 0) {
        html = `<button type="button" class="move move-start ${atStart ? 'current-move' : ''}" data-ply="0" title="Initial position"${startAria}>⊙ Initial position</button>`;
    } else {
        html = `<button type="button" class="move move-start${atStart ? ' current-move' : ''}" data-ply="0" title="Return to initial position"${startAria}>⊙</button>`;
        for (let i = 0; i < list.length; i++) {
            const ply = i + 1;
            // Reuse the shared move-number label from chess-utils.js (labels
            // the move about to be played at ply `i`). `moveNumberLabel` uses
            // "..." for Black moves; the number span is only rendered for the
            // first move and White moves (single trailing dot).
            const num = moveNumberLabel(i, initialFen);
            const showNum = i === 0 || (num.endsWith('.') && !num.endsWith('...'));
            const isCurrent = ply === currentIndex;
            const isDiag = ply === diagramPly;
            const cls = [isCurrent && 'current-move', isDiag && 'diagram-pos'].filter(Boolean).join(' ');
            const ariaCurrent = isCurrent ? ' aria-current="step"' : '';
            const title = isDiag ? `${escapeHtml(list[i])} — diagram position` : escapeHtml(list[i]);
            html += `<span class="move-pair" role="listitem">${showNum ? `<span class="move-num">${escapeHtml(num)}</span>` : ''}<button type="button" class="move${cls ? ' ' + cls : ''}" data-ply="${ply}" title="${title}"${ariaCurrent}>${escapeHtml(list[i])}${isDiag ? ' 📖' : ''}</button></span>`;
        }
    }
    // Alternative variations at the current move (fork): up to 3 quick-jump
    // buttons + a counter if more. Each button shows the first diverging move
    // and the total length of the line.
    const alts = alternatives || [];
    if (alts.length > 0) {
        html += `<span class="var-fork" role="group" aria-label="Alternative moves">`;
        for (const a of alts.slice(0, 3)) {
            const absPly = Number(a?.absPly) || 0;
            const len = Number(a?.length) || 0;
            const san = escapeHtml(a?.san) || '?';
            html += `<button type="button" class="move var-jump" data-line="${escapeHtml(a?.lineId)}" data-ply="${absPly + 1}" title="${escapeHtml(a?.label)}">↳ ${san} (${len} moves)</button>`;
        }
        if (alts.length > 3) {
            html += `<span class="var-more">+${alts.length - 3} others</span>`;
        }
        html += `</span>`;
    }
    return html;
}

/** Complete page for a section (header + navigation + content). */
export function sectionHTML(section, sectionNum, totalSections) {
    const progress = ((sectionNum + 1) / totalSections * 100).toFixed(1);
    const origPage = section.original_page > 0 ? section.original_page + 1 : null;
    const navBtn = (id, delta, label) =>
        `<button id="${id}" ${sectionNum + delta < 0 || sectionNum + delta >= totalSections ? 'disabled' : ''}>${label}</button>`;
    return `
        <div class="page-header">
            <h1 class="section-title">${escapeHtml(section.title)}</h1>
            <div class="progress-bar"><div class="progress-fill" style="width: ${progress}%"></div></div>
            <div class="page-info">
                <span>Section ${sectionNum + 1} / ${totalSections} · ${progress}%${origPage ? ` · printed p. ${origPage}` : ''}</span>
            </div>
        </div>
        <div class="page-navigation">
            ${navBtn('prev-page', -1, '← Previous')}
            ${navBtn('next-page', 1, 'Next →')}
        </div>
        <div class="content-text">${section.content}</div>
        <div class="page-navigation bottom">
            ${navBtn('prev-page-bottom', -1, '← Previous')}
            ${navBtn('next-page-bottom', 1, 'Next →')}
        </div>
    `;
}

/** Body of a playable inline diagram (replaces the placeholder div). */
export function inlineWrapperHTML(num, captionText, hasPosition) {
    return `
        <div class="diagram-playable-header">
            <span class="diagram-badge">#${escapeHtml(num)}</span>
            <span class="diagram-playable-caption">${escapeHtml(captionText)}</span>
            ${!hasPosition ? '<span class="diagram-missing-badge">⚠ default position</span>' : ''}
        </div>
        <div class="diagram-playable-board" id="inline-board-${num}" role="application" aria-roledescription="chessboard" aria-label="Chessboard for diagram ${escapeHtml(num)}"></div>
        <div class="diagram-playable-meta" aria-live="polite">
            <span class="ply-counter" id="inline-ply-${num}"></span>
            <span class="turn-dot" id="inline-turn-${num}"></span>
        </div>
        <div class="diagram-playable-controls" role="toolbar" aria-label="Diagram ${escapeHtml(num)} navigation" aria-controls="inline-board-${num}">
            <button type="button" class="diag-btn diag-first" data-diagram="${num}" title="Start of line (Home)" aria-label="Start of line" aria-keyshortcuts="Home">⏮</button>
            <button type="button" class="diag-btn diag-prev" data-diagram="${num}" title="Previous move (←)" aria-label="Previous move" aria-keyshortcuts="ArrowLeft">◀</button>
            <button type="button" class="diag-btn diag-next" data-diagram="${num}" title="Next move (→)" aria-label="Next move" aria-keyshortcuts="ArrowRight">▶</button>
            <button type="button" class="diag-btn diag-last" data-diagram="${num}" title="End of line (End)" aria-label="End of line" aria-keyshortcuts="End">⏭</button>
            <button type="button" class="diag-btn diag-expand" data-diagram="${num}" title="Enlarge diagram" aria-label="Enlarge">⛶</button>
        </div>
        <details class="diag-more">
            <summary>More actions</summary>
            <div class="diag-more-actions">
                <button type="button" class="diag-btn diag-flip" data-diagram="${num}" title="Flip board" aria-label="Flip board">⇅ Flip</button>
                <button type="button" class="diag-btn diag-position" data-diagram="${num}" title="Return to initial position (before any move)" aria-label="Initial position">⊙ Start</button>
                <button type="button" class="diag-btn diag-reset" data-diagram="${num}" title="Return to diagram position in book 📖" aria-label="Diagram position">📖 Book</button>
                <button type="button" class="diag-btn diag-fen" data-diagram="${num}" title="Copy current FEN to clipboard" aria-label="Copy FEN">⧉ FEN</button>
                <button type="button" class="diag-btn diag-lichess" data-diagram="${num}" title="Open current position on Lichess" aria-label="Open on Lichess">♞ Lichess</button>
            </div>
        </details>
        <div class="diagram-playable-moves" id="inline-moves-${num}" role="list" aria-label="Moves for diagram ${escapeHtml(num)}">
            <em>No moves played</em>
        </div>
        <p class="diagram-playable-hint visually-hidden">⏮ start · ◀ ▶ move by move · ⇅ flip · ⊙ initial position · 📖 book position · ⛶ enlarge</p>
        <div class="diagram-playable-vars" id="inline-vars-${num}" hidden>
            <label>Variation:
                <select class="diag-var-select" data-diagram="${num}" aria-label="Choose a variation"></select>
            </label>
        </div>
    `;
}

/** Options for a variation select from playable lines. */
export function variationOptionsHTML(lines) {
    return lines
        .map(l => `<option value="${escapeHtml(l.id)}">${escapeHtml(l.label)}</option>`)
        .join('');
}

/** Search results page. */
export function searchResultsHTML(results, query) {
    let html = `<h1>Search results for "${escapeHtml(query)}" (${results.length} found)</h1>`;
    results.forEach(result => {
        html += `
            <div class="search-result" tabindex="0" role="button">
                <strong>${escapeHtml(result.title)}</strong>
                <p>...${result.context}...</p>
            </div>
        `;
    });
    return html;
}

/** Full content-area loading spinner. */
export function loadingHTML() {
    return `
        <div class="loading-message" role="status" aria-live="polite">
            <div class="loading-spinner" aria-hidden="true"></div>
            <p>Loading book…</p>
        </div>
    `;
}

/** Friendly "book data not generated" panel (replaces the raw JSON error).
 *
 * The book text is never committed (copyright): book_structure.json,
 * diagrams.json and toc.json are generated locally from the legally
 * purchased EPUB. When they are missing the fetch either 404s or resolves
 * to the SPA fallback (index.html), whose "<" breaks JSON.parse — so this
 * panel explains how to import the data instead of showing the raw error.
 */
export function missingDataHTML(detail = '') {
    const detailHtml = detail
        ? `<details class="missing-detail"><summary>Technical details</summary><code>${escapeHtml(detail)}</code></details>`
        : '';
    return `
        <div class="missing-data" role="alert">
            <h2>Book data not found</h2>
            <p>The book text is <strong>not included</strong> in this repository
            (copyright). Generate it locally from your legally purchased EPUB:</p>
            <ol>
                <li>Buy the EPUB legally.</li>
                <li>Place it at the repository root as<br><code>How to Reassess Your Chess 4th ed - Silman.epub</code></li>
                <li>From the repository root, run:<br><code>python3 -m silman_parser.build</code></li>
                <li>Then restart the app:<br><code>cd chess-app &amp;&amp; npm run dev</code></li>
            </ol>
            <p class="hint">This creates the generated files
            <code>chess-app/data/book_structure.json</code>,
            <code>diagrams.json</code> and <code>toc.json</code> (gitignored).</p>
            <button type="button" class="error-action missing-retry">Retry</button>
            ${detailHtml}
        </div>
    `;
}

/** Inline error banner with optional action. */
export function errorHTML(message, action = null) {
    const actionHtml = action
        ? `<button type="button" class="error-action">${escapeHtml(action.label)}</button>`
        : '';
    return `
        <div class="error-message" role="alert">
            <h2>Error</h2>
            <p>${escapeHtml(message)}</p>
            ${actionHtml}
        </div>
    `;
}

/** Inline "no results" banner (replaces alert()). */
export function noResultsHTML(query) {
    return `
        <div class="no-results" role="status">
            <p>No results for <strong>${escapeHtml(query)}</strong>.</p>
            <p class="hint">Try other keywords (e.g. "outpost", "bishop pair").</p>
        </div>
    `;
}
