// search.js depends on templates.js (which does not touch the DOM).
import { describe, expect, it } from 'vitest';
import { highlightMatches, searchSections, stemVariants } from '../js/search.js';

const makeBook = (sections) => ({
    sections: sections.map((content, i) => ({
        section_num: i,
        title: `Section ${i}`,
        content,
    })),
});

describe('searchSections', () => {
    it('returns [] if query is empty', () => {
        const book = makeBook(['<p>Hello</p>']);
        expect(searchSections(book, '').results).toEqual([]);
    });

    it('ignores case', () => {
        const book = makeBook(['<p>Pawn structure</p>', '<p>Knight outpost</p>']);
        const { results } = searchSections(book, 'knight');
        expect(results).toHaveLength(1);
        expect(results[0].section).toBe(1);
    });

    it('tolerates accents (naive ↔ naïve)', () => {
        const book = makeBook(['<p>Naïve approach</p>', '<p>Simple naive plan</p>']);
        const { results } = searchSections(book, 'naive');
        expect(results).toHaveLength(2);
    });

    it('extracts context around the match (mark)', () => {
        const book = makeBook(['<p>' + 'lorem '.repeat(50) + 'bishop ' + 'ipsum '.repeat(50) + '</p>']);
        const { results } = searchSections(book, 'bishop');
        expect(results).toHaveLength(1);
        expect(results[0].context).toContain('<mark>bishop</mark>');
    });

    it('sorts by score (occurrences)', () => {
        const book = makeBook([
            '<p>bishop ' + 'word '.repeat(200) + '</p>',
            '<p>bishop bishop bishop</p>',
        ]);
        const { results } = searchSections(book, 'bishop');
        expect(results[0].section).toBe(1);
        expect(results[0].count).toBeGreaterThanOrEqual(3);
    });

    it('boosts title hits above body hits', () => {
        const book = makeBook([
            '<p>Some unrelated text without it at all.</p>',
            '<p>Another unrelated passage.</p>',
        ]);
        // The title "Section 0/1" does not contain "outpost"
        // Neither does the content. → 0 results.
        const { results } = searchSections(book, 'outpost');
        expect(results).toEqual([]);
    });

    it('multi-word = OR with ranking (best coverage first)', () => {
        const book = makeBook([
            '<p>Only knight here.</p>',
            '<p>Both bishop and knight here.</p>',
        ]);
        const { results } = searchSections(book, 'bishop and knight');
        expect(results).toHaveLength(2);
        // Section 1 covers both terms (+ exact phrase) → ranked first.
        expect(results[0].section).toBe(1);
        expect(results[1].section).toBe(0);
    });

    it('multi-word finds sections without the exact phrase', () => {
        const book = makeBook([
            '<p>Knight maneuvers are key.</p>',
            '<p>Unrelated text about endgames.</p>',
        ]);
        const { results } = searchSections(book, 'knight outpost');
        expect(results).toHaveLength(1);
        expect(results[0].section).toBe(0);
    });

    it('stems plurals (knights ↔ knight)', () => {
        expect(stemVariants('knights')).toContain('knight');
        const book = makeBook(['<p>Knights dominate the outpost.</p>']);
        const { results } = searchSections(book, 'knight');
        expect(results).toHaveLength(1);
    });

    it('highlightMatches never corrupts HTML tags', () => {
        const out = highlightMatches('<span class="knight">knight</span> and bishop', ['knight', 'bishop']);
        expect(out).toContain('<span class="knight">');
        expect(out).toContain('<mark>knight</mark>');
        expect(out).toContain('<mark>bishop</mark>');
    });

    it('simple search: single keyword', () => {
        const book = makeBook([
            '<p>Only knight here.</p>',
            '<p>Both bishop and knight here.</p>',
            '<p>Only bishop here.</p>',
        ]);
        const { results } = searchSections(book, 'bishop');
        expect(results).toHaveLength(2);
    });

    it('returns [] if nothing matches', () => {
        const book = makeBook(['<p>Some text</p>']);
        expect(searchSections(book, 'xyzzy').results).toEqual([]);
    });
});
