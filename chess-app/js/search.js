/**
 * Full-text search in the book sections.
 */

import { escapeHtml, searchResultsHTML } from './templates.js';

/**
 * Normalizes text for search: lowercase + strip diacritics
 * (naïve → naive) to tolerate missing/extra accents.
 */
function normalize(s) {
    return (s || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');
}

/** Escapes a string for use in a RegExp. */
function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Searches for `rawQuery` in the section contents.
 * Returns {query, results} with score, occurrence count, highlighted
 * excerpt (mark) preserving original case.
 *
 * Content is HTML: tags are stripped before extraction.
 */
export function searchSections(bookData, rawQuery) {
    const query = (rawQuery || '').trim();
    const results = [];
    if (!query || !bookData) return { query, results };

    const normQuery = normalize(query);
    const queryWords = normQuery.split(/\s+/).filter(w => w.length > 0);

    bookData.sections.forEach((section, index) => {
        const plainText = section.content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ');
        const normText = normalize(plainText);

        let count = 0;
        let pos = 0;
        while ((pos = normText.indexOf(normQuery, pos)) !== -1) {
            count++;
            pos += normQuery.length;
        }
        if (count === 0) return;

        let score = count;
        if (normalize(section.title).includes(normQuery)) score += 50;
        if (queryWords.length > 1 && queryWords.every(w => normText.includes(w))) score += 10;

        const matchIndex = normText.indexOf(normQuery);
        const start = Math.max(0, matchIndex - 80);
        const end = Math.min(plainText.length, matchIndex + query.length + 80);
        const excerpt = plainText.substring(start, end);
        const context = escapeHtml(excerpt).replace(
            new RegExp(`(${escapeRegex(escapeHtml(query))})`, 'gi'),
            '<mark>$1</mark>'
        );

        results.push({ section: index, title: section.title, context, count, score });
    });

    results.sort((a, b) => b.score - a.score);
    return { query, results };
}

/** Displays results; onSelect(sectionNum) on click or keyboard on a result. */
export function renderSearchResults(contentArea, results, query, onSelect) {
    contentArea.innerHTML = searchResultsHTML(results, query);
    contentArea.querySelectorAll('.search-result').forEach((result, index) => {
        const select = () => onSelect(results[index].section);
        result.addEventListener('click', select);
        result.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                select();
            }
        });
    });
}
