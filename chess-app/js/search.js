/**
 * Full-text search in the book sections.
 *
 * Tolerant matching (P1.5): multi-word queries use OR semantics with
 * ranking (exact-phrase bonus, title bonus, term coverage) instead of
 * strict AND-reject, plus light English stemming (knights → knight).
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

/** Minimal English stopwords: dropped from OR terms (phrase still counts). */
const STOPWORDS = new Set([
    'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with',
    'is', 'are', 'was', 'were', 'be', 'been', 'by', 'as', 'at', 'it', 'its',
    'this', 'that', 'these', 'those', 'from', 'into', 'you', 'your', 'he',
    'she', 'they', 'we', 'i', 'not', 'but', 'if', 'then', 'so', 'such',
]);

/** Splits normalized text into searchable tokens (len > 1). */
function tokenize(normText) {
    return normText.split(/[^a-z0-9]+/).filter(w => w.length > 1);
}

/**
 * Light stemming variants for one token: the token itself plus
 * de-pluralized forms (knights → knight, bishops → bishop, boxes → box).
 */
export function stemVariants(word) {
    const out = new Set([word]);
    if (word.length > 4) {
        if (word.endsWith('ies')) out.add(word.slice(0, -3) + 'y');
        if (word.endsWith('es')) out.add(word.slice(0, -2));
        if (word.endsWith('s')) out.add(word.slice(0, -1));
    } else if (word.length > 3 && word.endsWith('s')) {
        out.add(word.slice(0, -1));
    }
    return [...out];
}

/** Counts non-overlapping occurrences of `needle` in `haystack`. */
function countOccurrences(haystack, needle) {
    if (!needle) return 0;
    let count = 0;
    let pos = 0;
    while ((pos = haystack.indexOf(needle, pos)) !== -1) {
        count++;
        pos += needle.length;
    }
    return count;
}

/**
 * Wraps every occurrence of `terms` in `<mark>`, without touching HTML
 * tags (splits on tags, marks text parts only). Case-insensitive.
 */
export function highlightMatches(html, terms) {
    const clean = (terms || []).filter(t => t && t.length > 1).slice(0, 8);
    if (!clean.length) return html == null ? '' : String(html);
    const pattern = new RegExp(`(${clean.map(escapeRegex).join('|')})`, 'gi');
    return String(html).split(/(<[^>]*>)/g).map((part, i) =>
        (i % 2 === 1) ? part : part.replace(pattern, '<mark>$1</mark>'),
    ).join('');
}

/**
 * Searches for `rawQuery` in the section contents.
 * Returns {query, results} with score, occurrence count, matched terms
 * and highlighted excerpt (mark) preserving original case.
 *
 * Content is HTML: tags are stripped before extraction.
 */
export function searchSections(bookData, rawQuery) {
    const query = (rawQuery || '').trim();
    const results = [];
    if (!query || !bookData) return { query, results };

    const normQuery = normalize(query);
    const terms = tokenize(normQuery).filter(t => !STOPWORDS.has(t));
    // Query made only of stopwords/short tokens → phrase-only fallback.
    const phraseOnly = terms.length === 0;
    const termVars = terms.map(t => stemVariants(t));

    bookData.sections.forEach((section, index) => {
        const plainText = section.content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ');
        const normText = normalize(plainText);
        const normTitle = normalize(section.title);

        // Exact-phrase occurrences (old behavior, kept as a bonus signal).
        const phraseCount = countOccurrences(normText, normQuery);
        const phraseTitle = normTitle.includes(normQuery);

        if (phraseOnly) {
            if (phraseCount === 0 && !phraseTitle) return;
            const score = phraseCount * 2 + (phraseTitle ? 50 : 0);
            const matchIndex = normText.indexOf(normQuery);
            results.push({
                section: index,
                title: section.title,
                context: buildExcerpt(plainText, matchIndex, query, [query]),
                count: phraseCount,
                score,
                terms: [query],
            });
            return;
        }

        let score = phraseCount * 2;
        let count = phraseCount;
        const matched = [];
        let firstPos = phraseCount > 0 ? normText.indexOf(normQuery) : -1;

        termVars.forEach((variants, i) => {
            let hits = 0;
            let titleHit = false;
            for (const v of variants) {
                const c = countOccurrences(normText, v);
                hits += c;
                if (c > 0) {
                    const p = normText.indexOf(v);
                    if (firstPos === -1 || p < firstPos) firstPos = p;
                }
                if (normTitle.includes(v)) titleHit = true;
            }
            if (hits > 0 || titleHit) {
                matched.push(terms[i]);
                score += hits * 2 + (titleHit ? 20 : 0);
                count += hits;
            }
        });

        if (matched.length === 0) return;

        // Coverage bonus: all query terms present in one section ranks first.
        score += Math.round((matched.length / termVars.length) * 15);
        if (phraseTitle) score += 30;

        results.push({
            section: index,
            title: section.title,
            context: buildExcerpt(plainText, firstPos, query, matched),
            count,
            score,
            terms: matched,
        });
    });

    results.sort((a, b) => b.score - a.score);
    return { query, results };
}

/** Builds an ~80-char-context excerpt around `matchIndex`, marked up. */
function buildExcerpt(plainText, matchIndex, query, terms) {
    const at = matchIndex >= 0 ? matchIndex : 0;
    const start = Math.max(0, at - 80);
    const end = Math.min(plainText.length, at + query.length + 80);
    const excerpt = plainText.substring(start, end);
    return highlightMatches(escapeHtml(excerpt), terms);
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
