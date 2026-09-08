#!/usr/bin/env python3
"""Integrity tests for the generated data (chess-app/data/*.json).

These tests verify the invariants described in AGENTS.md:
logical sections, referenced diagrams, valid FENs, coherent TOC.

Run with:  python3 -m unittest discover -s tests -v
"""

import json
import os
import re
import unittest

import chess

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'chess-app', 'data',
)

GENERATED_FILES = ('book_structure.json', 'diagrams.json', 'toc.json')


def _missing_generated():
    return [n for n in GENERATED_FILES
            if not os.path.exists(os.path.join(DATA_DIR, n))]


def load(name):
    with open(os.path.join(DATA_DIR, name), encoding='utf-8') as f:
        return json.load(f)


class TestBookStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = _missing_generated()
        if missing:
            raise unittest.SkipTest(
                f'generated data missing ({", ".join(missing)}): buy the EPUB and run '
                'python3 -m silman_parser.build')
        cls.book = load('book_structure.json')

    def test_metadata(self):
        self.assertEqual(self.book['title'], 'How to Reassess Your Chess')
        self.assertEqual(self.book['author'], 'Jeremy Silman')
        self.assertEqual(self.book['type'], 'sections')

    def test_total_sections_consistent(self):
        self.assertEqual(self.book['total_sections'], len(self.book['sections']))
        self.assertGreater(len(self.book['sections']), 0)

    def test_section_numbers_sequential(self):
        for i, sec in enumerate(self.book['sections']):
            self.assertEqual(sec['section_num'], i)

    def test_section_required_keys(self):
        for sec in self.book['sections']:
            for key in ('section_num', 'title', 'level', 'original_page', 'content'):
                self.assertIn(key, sec)
            self.assertTrue(sec['title'])
            self.assertTrue(sec['content'].strip())

    def test_balanced_tags(self):
        for sec in self.book['sections']:
            content = sec['content']
            self.assertEqual(content.count('<p'), content.count('</p>'),
                             f"section {sec['section_num']}: unbalanced <p>")
            self.assertEqual(content.count('<div'), content.count('</div>'),
                             f"section {sec['section_num']}: unbalanced <div>")

    def test_no_div_inside_p(self):
        for sec in self.book['sections']:
            for m in re.finditer(r'<p>(.*?)</p>', sec['content'], re.DOTALL):
                self.assertNotIn('<div', m.group(1),
                                 f"section {sec['section_num']}: <div> inside <p>")

    def test_diagram_refs_are_numeric(self):
        for sec in self.book['sections']:
            for m in re.finditer(r'data-diagram="([^"]+)"', sec['content']):
                self.assertTrue(m.group(1).isdigit(),
                                f"section {sec['section_num']}: non-numeric ref")


class TestDiagrams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = _missing_generated()
        if missing:
            raise unittest.SkipTest(
                f'generated data missing ({", ".join(missing)}): buy the EPUB and run '
                'python3 -m silman_parser.build')
        cls.diagrams = load('diagrams.json')

    def test_not_empty(self):
        self.assertGreater(len(self.diagrams), 0)

    def test_required_keys(self):
        for num, d in self.diagrams.items():
            for key in ('number', 'occurrences', 'fen', 'initial_fen',
                        'moves', 'diagram_move_index', 'variations', 'entries'):
                self.assertIn(key, d, f'diagram {num}: missing key {key}')
            self.assertEqual(d['number'], num)
            self.assertTrue(d['entries'])

    def test_fens_valid(self):
        for num, d in self.diagrams.items():
            for key in ('fen', 'initial_fen'):
                fen = d.get(key)
                if fen is None:
                    continue
                try:
                    chess.Board(fen)
                except ValueError:
                    self.fail(f'diagram {num}: invalid {key}: {fen!r}')

    def test_moves_valid_types(self):
        for num, d in self.diagrams.items():
            moves = d.get('moves')
            if moves is None:
                continue
            self.assertIsInstance(moves, list, f'diagram {num}: moves is not a list')
            self.assertIsInstance(d['diagram_move_index'], int)
            self.assertGreaterEqual(d['diagram_move_index'], 0)
            self.assertLessEqual(d['diagram_move_index'], len(moves))

    def test_moves_legal_from_startpos(self):
        """Diagrams reconstructed from the starting position
        (parser passes 1-2) have all moves playable."""
        checked = 0
        for num, d in self.diagrams.items():
            if not d.get('moves') or d.get('initial_fen') != chess.STARTING_FEN:
                continue
            board = chess.Board(chess.STARTING_FEN)
            for san in d['moves']:
                try:
                    board.push_san(san)
                except ValueError:
                    self.fail(f'diagram {num}: illegal move {san!r}')
                    break
            checked += 1
        self.assertGreater(checked, 0, 'no startpos diagram to check')

    def test_stale_records_documented(self):
        """Diagrams off the starting position whose moves are not playable
        from initial_fen: the frontend ignores them (break at the first
        illegal move, cf. initializeInlineBoard/showDiagram).
        Any NEW entry here signals a parser regression; if a known entry is
        fixed, remove it from KNOWN_STALE."""
        # Diagram 16: fixed by the EPUB rebuild (moves_match from
        # STARTING_FEN, legal moves and coherent fen/index) -> empty set.
        KNOWN_STALE = set()
        stale = set()
        for num, d in self.diagrams.items():
            if not d.get('moves') or not d.get('initial_fen'):
                continue
            if d['initial_fen'] == chess.STARTING_FEN:
                continue
            board = chess.Board(d['initial_fen'])
            try:
                for san in d['moves']:
                    board.push_san(san)
            except ValueError:
                stale.add(num)
        self.assertEqual(stale, KNOWN_STALE,
                         f'unexpected incoherent records: {stale - KNOWN_STALE} '
                         f'(fixed: {KNOWN_STALE - stale} to remove from KNOWN_STALE)')

    def test_diagram_move_index_yields_diagram_fen(self):
        """Playing diagram_move_index moves from initial_fen must give fen
        (diagrams reconstructed from the starting position)."""
        checked = 0
        for num, d in self.diagrams.items():
            if not d.get('moves') or not d.get('initial_fen') or not d.get('fen'):
                continue
            if d['initial_fen'] != chess.STARTING_FEN:
                continue
            board = chess.Board(d['initial_fen'])
            for san in d['moves'][:d['diagram_move_index']]:
                board.push_san(san)
            self.assertEqual(board.fen(), d['fen'],
                             f'diagram {num}: fen/index inconsistency')
            checked += 1
        self.assertGreater(checked, 0, 'no complete diagram to check')

    def test_variations_replay_recursively(self):
        """Each branch replays from initial_fen + parent line.

        Diagrams whose main line does not replay (KNOWN_STALE cases): their
        variations are ignored by the frontend like the main line."""

        def check(base_fen, parent_moves, branches, num, path):
            line = chess.Board(base_fen)
            for san in parent_moves:
                line.push_san(san)  # raises if the parent line is not replayable
            for i, br in enumerate(branches or []):
                where = f'{path}[{i}]'
                bp = br.get('branch_ply')
                self.assertIsInstance(bp, int, f'diagram {num}: {where}')
                self.assertGreaterEqual(bp, 0, f'diagram {num}: {where}')
                self.assertLessEqual(bp, len(parent_moves),
                                     f'diagram {num}: {where} out of bounds')
                b = chess.Board(base_fen)
                for san in parent_moves[:bp]:
                    b.push_san(san)
                for san in br.get('moves', []):
                    try:
                        b.push_san(san)
                    except ValueError:
                        self.fail(f'diagram {num}: {where} illegal move {san!r}')
                b2 = chess.Board(base_fen)
                for san in parent_moves[:bp]:
                    b2.push_san(san)
                check(b2.fen(), br.get('moves', []),
                      br.get('variations', []), num, where)

        checked = skipped = 0
        for num, d in sorted(self.diagrams.items(), key=lambda kv: int(kv[0])):
            if not d.get('variations') or not d.get('moves') or not d.get('initial_fen'):
                continue
            try:
                check(d['initial_fen'], d['moves'], d['variations'], num, '')
                checked += 1
            except ValueError:
                skipped += 1  # non-replayable main line (cf. KNOWN_STALE)
        self.assertGreater(checked, 0, 'no variation to check')


class TestManualOverrides(unittest.TestCase):
    """The manual overrides (diagrams unresolvable by parsing)
    are applied verbatim in diagrams.json."""

    @classmethod
    def setUpClass(cls):
        missing = _missing_generated()
        if missing:
            raise unittest.SkipTest(
                f'generated data missing ({", ".join(missing)}): buy the EPUB and run '
                'python3 -m silman_parser.build')
        cls.diagrams = load('diagrams.json')
        path = os.path.join(DATA_DIR, 'diagrams_manual_overrides.json')
        with open(path, encoding='utf-8') as f:
            cls.overrides = json.load(f)

    def test_overrides_applied_verbatim(self):
        self.assertGreater(len(self.overrides), 0, 'no override defined')
        for num, ov in self.overrides.items():
            self.assertIn(num, self.diagrams, f'override {num} unknown')
            d = self.diagrams[num]
            self.assertEqual(d['fen'], ov['fen'], f'override {num} not applied')
            self.assertEqual(d['initial_fen'], ov['initial_fen'])
            self.assertEqual(d['moves'], ov['moves'])
            self.assertEqual(d['diagram_move_index'],
                             ov['diagram_move_index'])

    def test_overrides_self_consistent(self):
        for num, ov in self.overrides.items():
            board = chess.Board(ov['fen'])  # valid FEN
            if ov.get('moves') is None:
                continue
            replay = chess.Board(ov['initial_fen'])
            for san in ov['moves'][:ov['diagram_move_index']]:
                replay.push_san(san)  # legal moves
            self.assertEqual(replay.fen(), ov['fen'],
                             f'override {num}: fen/index inconsistency')


class TestToc(unittest.TestCase):
    """The TOC is the native NCX tree (toc.ncx navMap) resolved to the
    book sections: hierarchical nodes {'title', 'src', 'section', 'anchor',
    'children'}."""

    @classmethod
    def setUpClass(cls):
        missing = _missing_generated()
        if missing:
            raise unittest.SkipTest(
                f'generated data missing ({", ".join(missing)}): buy the EPUB and run '
                'python3 -m silman_parser.build')
        cls.toc = load('toc.json')
        cls.book = load('book_structure.json')

    def test_not_empty(self):
        self.assertGreater(len(self.toc), 0)

    def test_node_shape(self):
        def check(nodes, path=''):
            for i, n in enumerate(nodes):
                p = f'{path}[{i}]'
                for key in ('title', 'src', 'section', 'anchor', 'children'):
                    self.assertIn(key, n, f'{p}: missing key {key}')
                self.assertTrue(n['title'], f'{p}: empty title')
                self.assertTrue(n['src'].startswith('text/part'),
                                f'{p}: bad src {n["src"]!r}')
                self.assertIsNone(n['section']) if n['section'] is None \
                    else self.assertIsInstance(n['section'], int)
                check(n['children'], p)
        check(self.toc)

    def test_starts_with_title_page(self):
        self.assertEqual(self.toc[0]['title'], 'Title Page')
        self.assertIsNone(self.toc[0]['section'])
        child_titles = [c['title'] for c in self.toc[0]['children']]
        self.assertEqual(child_titles[:3], ['Copyright', 'Contents', 'Preface'])
        # Preface (front matter) resolves to section 0.
        preface = next(c for c in self.toc[0]['children']
                       if c['title'] == 'Preface')
        self.assertEqual(preface['section'], 0)

    def test_part_one_imbalances_children(self):
        part_one = self.toc[1]
        self.assertTrue(part_one['title'].startswith('Part One'))
        self.assertIsNone(part_one['section'])
        imbalances = part_one['children'][0]
        self.assertEqual(imbalances['title'], 'Imbalances / Learning the ABCs')
        # 13 NCX navPoints: 12 anchored entries (_idParaDest-9..20) + Summary.
        self.assertEqual(len(imbalances['children']), 13)
        anchored = [c for c in imbalances['children'] if c['anchor']]
        self.assertEqual(len(anchored), 12)
        # Objective mapping depends on the section split, which is sensitive
        # to the HTML length emitted by the parser. After semantic enrichment
        # (lists compact many <p> blocks into one <ul>) and the removal of
        # the redundant side-to-move captions (shown by the diagram header),
        # the boundary shifts: 9-17 -> section 3, 18-19 -> section 4,
        # 20 -> section 5.
        by_anchor = {c['anchor']: c['section'] for c in anchored}
        for num in range(9, 18):
            self.assertEqual(by_anchor[f'_idParaDest-{num}'], 3)
        for num in (18, 19):
            self.assertEqual(by_anchor[f'_idParaDest-{num}'], 4)
        self.assertEqual(by_anchor['_idParaDest-20'], 5)
        summary = imbalances['children'][-1]
        self.assertEqual(summary['title'], 'Summary')
        self.assertIsNotNone(summary['section'])

    def test_all_sections_exist(self):
        total = len(self.book['sections'])

        def check(nodes, path=''):
            for i, n in enumerate(nodes):
                p = f'{path}[{i}]'
                if n['section'] is not None:
                    self.assertGreaterEqual(n['section'], 0, p)
                    self.assertLess(n['section'], total, p)
                check(n['children'], p)
        check(self.toc)

    def test_all_anchors_exist_in_resolved_section(self):
        def check(nodes, path=''):
            for i, n in enumerate(nodes):
                p = f'{path}[{i}]'
                if n['anchor'] and n['section'] is not None:
                    content = self.book['sections'][n['section']]['content']
                    self.assertIn(f'id="{n["anchor"]}"', content,
                                  f'{p}: anchor {n["anchor"]} not in '
                                  f'section {n["section"]}')
                check(n['children'], p)
        check(self.toc)


class TestCrossReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = _missing_generated()
        if missing:
            raise unittest.SkipTest(
                f'generated data missing ({", ".join(missing)}): buy the EPUB and run '
                'python3 -m silman_parser.build')
        cls.book = load('book_structure.json')
        cls.diagrams = load('diagrams.json')

    def test_all_inline_diagrams_known(self):
        refs = set()
        for sec in self.book['sections']:
            refs.update(re.findall(r'data-diagram="(\d+)"', sec['content']))
        unknown = refs - set(self.diagrams.keys())
        self.assertEqual(unknown, set(), f'unknown referenced diagrams: {unknown}')

    def test_diagram_entries_have_side_or_level(self):
        missing = [num for num, d in self.diagrams.items()
                   if not any(e.get('side') or e.get('level') for e in d['entries'])]
        # Informative: at least half of the diagrams have side/level
        self.assertLess(len(missing), len(self.diagrams) / 2,
                        f'{len(missing)} diagrams without side nor level')


if __name__ == '__main__':
    unittest.main()