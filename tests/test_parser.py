#!/usr/bin/env python3
"""Unit tests for the pure parser functions (epub_ingest, san, ...).

Run with:  python3 -m unittest discover -s tests -v
"""

import os
import re
import sys
import unittest

import chess
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silman_parser as p
from silman_parser.epub_ingest import _enrich_content_blocks

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPUB_PATH = os.path.join(REPO_DIR, 'How to Reassess Your Chess 4th ed - Silman.epub')


def make_game(san_moves):
    """Build a chess.pgn.Game with the given main line."""
    game = chess.pgn.Game()
    node = game
    for san in san_moves:
        node = node.add_variation(node.board().parse_san(san))
    return game


def make_book(sections_contents):
    """Build a fake book_data with the given HTML contents."""
    return {
        'sections': [
            {'section_num': i, 'title': f'Sec {i}', 'content': c}
            for i, c in enumerate(sections_contents)
        ]
    }


class TestNormalizeMoveText(unittest.TestCase):
    def test_castling_zeros(self):
        self.assertIn('O-O', p.normalize_move_text('0-0'))
        self.assertIn('O-O-O', p.normalize_move_text('0-0-0'))

    def test_castling_unicode_dashes(self):
        # EPUB: castling with en/em dashes ("0–0", "0—0").
        self.assertIn('O-O', p.normalize_move_text('0–0'))
        self.assertIn('O-O', p.normalize_move_text('0—0'))
        self.assertIn('O-O-O', p.normalize_move_text('0–0–0'))
        self.assertIn('O-O-O', p.normalize_move_text('0—0—0'))
        # "7.0–0": move number + unicode castling
        self.assertIn('O-O', p.normalize_move_text('7.0–0'))

    def test_unicode_ellipsis(self):
        out = p.normalize_move_text('1…Rb8 2.Bxb8')
        self.assertNotIn('…', out)
        self.assertIn('Rb8', out)
        self.assertNotIn('1...', out)

    def test_move_numbers_stripped(self):
        out = p.normalize_move_text('1. e4 e5 2. Nf3')
        self.assertNotIn('1.', out)
        self.assertIn('e4', out)
        self.assertIn('Nf3', out)

    def test_annotations_stripped(self):
        out = p.normalize_move_text('Nf3! Bd3?!')
        self.assertNotIn('!', out)
        self.assertNotIn('?', out)

    def test_results_stripped(self):
        out = p.normalize_move_text('e4 e5 1-0')
        self.assertNotIn('1-0', out)

    # --- P5: results purged BEFORE the number removal ---
    def test_results_stripped_with_trailing_dot(self):
        # "0-1." must not become "0-": r'\d+\.' must not eat the last digit
        # of the result before it is purged.
        out = p.normalize_move_text('1. e4 0-1.')
        self.assertNotIn('0-', out)
        self.assertIn('e4', out)

    def test_half_result_stripped_after_cleanup(self):
        out = p.normalize_move_text('1. e4 e5 1/2-1/2.')
        self.assertNotIn('1/', out)
        self.assertIn('e4', out)


class TestExtractSanMoves(unittest.TestCase):
    def test_basic_line(self):
        self.assertEqual(p.extract_san_moves('1. e4 e5 2. Nf3 Nc6'), ['e4', 'e5', 'Nf3', 'Nc6'])

    def test_castling(self):
        self.assertIn('O-O', p.extract_san_moves('1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O'))

    def test_captures_and_checks(self):
        moves = p.extract_san_moves('1. exd5+ Qxd5')
        self.assertEqual(moves, ['exd5+', 'Qxd5'])

    def test_empty(self):
        self.assertEqual(p.extract_san_moves(''), [])
        self.assertEqual(p.extract_san_moves('blabla ... ...'), [])

    def test_ignores_results(self):
        self.assertEqual(p.extract_san_moves('1. e4 e5 1/2-1/2'), ['e4', 'e5'])

    def test_extract_black_ellipsis_move_number(self):
        self.assertEqual(p.extract_san_moves('1. e4 Nf6 16... e5'),
                         ['e4', 'Nf6', 'e5'])

    # --- EPUB: unicode ellipses "…" and castling with unicode dashes ---
    def test_extract_unicode_ellipsis(self):
        self.assertEqual(p.extract_san_moves('1…Rb8 2.Bxb8'), ['Rb8', 'Bxb8'])
        self.assertEqual(p.extract_san_moves('63…Nf2 64.Be2 Nxg4'),
                         ['Nf2', 'Be2', 'Nxg4'])

    def test_extract_unicode_castling(self):
        moves = p.extract_san_moves('10.f4 0–0 11.Bxa7 Rxa7 12.g4 b5 13.0–0–0')
        self.assertIn('O-O', moves)
        self.assertIn('O-O-O', moves)
        self.assertNotIn('0–0', moves)


class TestHtmlEscape(unittest.TestCase):
    def test_html_escape_no_lt_semicolon_artifact(self):
        # Escaped "fa<;ade" must NEVER produce "fa&lt;;ade"
        out = p.html_escape('pawn-fa<;ade.')
        self.assertIn('pawn-facade', out)
        self.assertNotIn('&lt;;', out)


class TestEnrichContentBlocks(unittest.TestCase):
    """Semantic enrichment: lists, callouts, blockquotes."""

    @staticmethod
    def _block(html, href=None, anchor=None):
        return {'html': html, 'href': href, 'anchor': anchor}

    def test_list_main_and_sub_items(self):
        blocks = [
            self._block('<p>»Parent A</p>'),
            self._block('<p>•Child 1</p>'),
            self._block('<p>•Child 2</p>'),
            self._block('<p>»Parent B</p>'),
        ]
        out = _enrich_content_blocks(blocks)
        self.assertEqual(len(out), 1)
        self.assertIn('<ul class="book-list">', out[0]['html'])
        self.assertIn('<ul class="book-list book-list-sub">', out[0]['html'])
        self.assertIn('<li>Parent A<ul', out[0]['html'])
        self.assertIn('<li>Child 1</li>', out[0]['html'])
        self.assertIn('<li>Parent B</li>', out[0]['html'])
        self.assertNotIn('»', out[0]['html'])
        self.assertNotIn('•', out[0]['html'])

    def test_callout_marker_consumes_next_paragraph(self):
        blocks = [
            self._block('<p>philosophy</p>'),
            self._block('<p>Think before you move.</p>'),
            self._block('<p>Normal prose.</p>'),
        ]
        out = _enrich_content_blocks(blocks)
        self.assertEqual(len(out), 2)
        self.assertIn('<aside class="callout callout-philosophy">', out[0]['html'])
        self.assertIn('<h4 class="callout-title">Philosophy</h4>', out[0]['html'])
        self.assertIn('<p>Think before you move.</p>', out[0]['html'])
        self.assertNotIn('philosophy</p>', out[0]['html'])
        self.assertEqual(out[1]['html'], '<p>Normal prose.</p>')

    def test_callout_preserves_anchor(self):
        blocks = [
            self._block('<p>rule</p>'),
            self._block('<p id="rule-42">Always castle.</p>'),
        ]
        out = _enrich_content_blocks(blocks)
        self.assertIn('id="rule-42"', out[0]['html'])

    def test_blockquote_with_attribution(self):
        blocks = [
            self._block('<p>“A sound plan makes heroes.” —G.M. Kotov</p>'),
        ]
        out = _enrich_content_blocks(blocks)
        self.assertEqual(len(out), 1)
        self.assertIn('<blockquote class="book-quote">', out[0]['html'])
        self.assertIn('<p>“A sound plan makes heroes.”</p>', out[0]['html'])
        self.assertIn('<cite>—G.M. Kotov</cite>', out[0]['html'])

    def test_prose_paragraph_unchanged(self):
        blocks = [self._block('<p>Just a normal paragraph.</p>')]
        out = _enrich_content_blocks(blocks)
        self.assertEqual(out, blocks)


class TestSplitLongSections(unittest.TestCase):
    @staticmethod
    def _section(paras, **extra):
        # Sections come from the EPUB ingest with per-block metadata.
        sec = {
            'title': 'T',
            'level': 1,
            'original_page': 1,
            'content': '\n\n'.join(paras),
            'blocks': [{'html': para, 'href': None, 'anchor': None}
                       for para in paras],
        }
        sec.update(extra)
        return sec

    def test_short_unchanged(self):
        secs = [self._section(['abc'])]
        self.assertEqual(p.split_long_sections(secs, max_chars=100), secs)

    def test_long_split_preserves_content(self):
        paras = [f'Paragraph {i} with some content here.' for i in range(20)]
        secs = [self._section(paras)]
        result = p.split_long_sections(secs, max_chars=100)
        self.assertGreater(len(result), 1)
        rejoined = '\n\n'.join(r['content'] for r in result)
        self.assertEqual(rejoined, '\n\n'.join(paras))

    def test_missing_original_page_defaults_zero(self):
        # Native EPUB sections have no printed page: the parts emitted by the
        # split take original_page = 0.
        paras = [f'Paragraph {i} with some content here.' for i in range(20)]
        sec = self._section(paras, level=2)
        del sec['original_page']
        out = p.split_long_sections([sec], max_chars=100)
        self.assertGreater(len(out), 1)
        self.assertTrue(all(r['original_page'] == 0 for r in out))


class TestEpubIngest(unittest.TestCase):
    """Native EPUB ingestion (H2 sections, diagrams, game-notation)."""

    @classmethod
    def setUpClass(cls):
        cls.result = p.parse_epub(EPUB_PATH)
        cls.sections = cls.result['sections']
        cls.diagrams = cls.result['diagrams']
        cls.toc = cls.result['toc']

    def test_spine_order_preface_before_knights(self):
        titles = [s['title'] for s in self.sections]
        self.assertLess(titles.index('Preface'), titles.index('Knights'))

    def test_front_matter_levels(self):
        # Preface/Acknowledgements/Introduction (front) = level 1; the
        # second "Introduction" (Part Five) = level 2.
        by_title = {}
        for s in self.sections:
            by_title.setdefault(s['title'], []).append(s['level'])
        self.assertEqual(by_title['Preface'], [1])
        self.assertEqual(by_title['Acknowledgements'], [1])
        self.assertEqual(by_title['Introduction'], [1, 2])

    def test_intro_witness_complete(self):
        content = self.sections[0]['content']
        self.assertIn('4th Edition was written to elicit that kind of experience',
                      content)
        self.assertIn('paradigm shift', content)

    def test_ellipsis_moves_become_game_notation(self):
        # "1.b7 ... 1…Rb8 2.Bxb8 Rxb8 3.Qc6 Qd8" (part0008) -> game-notation
        found = False
        for s in self.sections:
            if '<div class="diagram-inline" data-diagram="3">' in s['content']:
                notations = re.findall(
                    r'<div class="game-notation">(.*?)</div>', s['content'])
                moves = []
                for n in notations:
                    moves.extend(p.extract_san_moves(n))
                self.assertIn('Rb8', moves)
                self.assertIn('Bxb8', moves)
                self.assertIn('Qd8', moves)
                found = True
                break
        self.assertTrue(found, 'diagram 3 not found in the sections')

    def test_caption_side_stays_prose(self):
        # "White to move" / "Black to move" are never absorbed into a
        # game-notation (counter-example <span class="bold">White to move</span>).
        for s in self.sections:
            for m in re.finditer(r'<div class="game-notation">(.*?)</div>',
                                 s['content']):
                self.assertNotIn('White to move', m.group(1),
                                 f'section {s["title"]}')
                self.assertNotIn('Black to move', m.group(1))
        self.assertTrue(any('<p>White to move</p>' in s['content']
                            for s in self.sections))

    def test_diagram_block_no_residual_label(self):
        # A "Diagram 3" block becomes a div, without a residual "Diagram 3" text.
        for s in self.sections:
            if '<div class="diagram-inline" data-diagram="3">' in s['content']:
                plain = re.sub(r'<[^>]+>', '', s['content'])
                self.assertNotIn('Diagram 3', plain)
                break
        else:
            self.fail('diagram 3 not found in the sections')

    def test_432_unique_diagrams_cover_1_to_432(self):
        nums = {int(n) for n in self.diagrams}
        self.assertEqual(set(range(1, 433)), nums)

    def test_diagram_entries_have_side_or_level_sometimes(self):
        # At least one diagram has a side read in the caption1.
        sides = {e['side'] for entries in self.diagrams.values() for e in entries}
        self.assertIn('white', sides)
        self.assertIn('black', sides)
        # And [Level: ...] levels are attached (test diagrams).
        levels = [e['level'] for entries in self.diagrams.values() for e in entries
                  if e['level']]
        self.assertGreater(len(levels), 100)

    def test_balanced_tags(self):
        for s in self.sections:
            self.assertEqual(s['content'].count('<p'), s['content'].count('</p>'),
                             f'section {s["title"]}: unbalanced <p>')
            self.assertEqual(s['content'].count('<div'), s['content'].count('</div>'),
                             f'section {s["title"]}: unbalanced <div>')

    def test_toc_starts_with_preface(self):
        # Backward-compatible flat H2 TOC of parse_epub: still available.
        self.assertEqual(self.toc[0]['title'], 'Preface')
        self.assertEqual(self.toc[0]['level'], 1)

    def test_ncx_toc_hierarchical(self):
        """parse_ncx_toc returns the native toc.ncx tree (166 navPoints):
        Title Page first, then Part One > Imbalances / Learning the ABCs
        with its 12 anchored children + Summary."""
        ncx = p.parse_ncx_toc(EPUB_PATH)
        self.assertEqual(ncx[0]['title'], 'Title Page')
        self.assertEqual(ncx[0]['src'], 'text/part0000.html')
        self.assertIsNone(ncx[0]['anchor'])
        self.assertEqual([c['title'] for c in ncx[0]['children']][:3],
                         ['Copyright', 'Contents', 'Preface'])
        part_one = ncx[1]
        self.assertEqual(part_one['title'], 'Part One / The Concept of Imbalances')
        imbalances = part_one['children'][0]
        self.assertEqual(imbalances['title'], 'Imbalances / Learning the ABCs')
        self.assertEqual(imbalances['src'], 'text/part0008.html')
        self.assertEqual(len(imbalances['children']), 13)
        anchored = [c for c in imbalances['children'] if c['anchor']]
        self.assertEqual(len(anchored), 12)
        self.assertEqual(anchored[0]['anchor'], '_idParaDest-9')
        self.assertEqual(anchored[0]['src'],
                         'text/part0008.html#_idParaDest-9')


class TestDiagramNumberFromPgn(unittest.TestCase):
    def test_single(self):
        self.assertIn(12, p.extract_diagram_and_page_numbers('', 'Diagram 12: Foo - Bar'))

    def test_pair_with_and(self):
        nums = p.extract_diagram_and_page_numbers('', 'Diagrams 3 & 4: Foo - Bar')
        self.assertIn(3, nums)
        self.assertIn(4, nums)

    def test_range(self):
        nums = p.extract_diagram_and_page_numbers('Event Diagrams 5-7', '')
        self.assertEqual(nums, [5, 6, 7])


class TestPlayers(unittest.TestCase):
    def test_extract_players(self):
        players = p.extract_players_from_chapter('Diagram 19: Liviu Dieter Nisipeanu - Vadim Milov')
        self.assertEqual(players, ('Liviu Dieter Nisipeanu', 'Vadim Milov'))

    def test_no_players(self):
        self.assertIsNone(p.extract_players_from_chapter('Diagram 19: Tactic time'))


class TestGameMatching(unittest.TestCase):
    def setUp(self):
        self.moves = ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6', 'Ba4', 'Nf6']
        self.game = make_game(self.moves)

    def test_get_mainline_moves(self):
        self.assertEqual(p.get_mainline_moves(self.game), self.moves)

    def test_find_exact_match(self):
        self.assertEqual(p.find_exact_match(self.game, ['Nf3', 'Nc6', 'Bb5']), 5)
        self.assertIsNone(p.find_exact_match(self.game, ['d4', 'd5']))
        self.assertIsNone(p.find_exact_match(self.game, []))

    def test_find_exact_match_partial_not_accepted(self):
        # Trailing garbage breaks the contiguous match (no partial fallback)
        self.assertIsNone(
            p.find_exact_match(self.game, ['Nf3', 'Nc6', 'Bb5', 'a6', 'zzz']))

    def test_find_exact_match_non_contiguous(self):
        # A gap in the sequence (skipping Nc6) is not a match
        self.assertIsNone(p.find_exact_match(self.game, ['e5', 'Nf3', 'Bb5']))

    def test_find_exact_match_empty(self):
        self.assertIsNone(p.find_exact_match(self.game, []))


class TestPositionHelpers(unittest.TestCase):
    def test_position_at_turn(self):
        game = make_game(['e4', 'e5'])
        self.assertTrue(p.position_at(game, 0).turn == chess.WHITE)
        self.assertTrue(p.position_at(game, 1).turn == chess.BLACK)
        self.assertTrue(p.position_at(game, 2).turn == chess.WHITE)

    def test_find_position_with_side(self):
        game = make_game(['e4', 'e5', 'Nf3'])
        self.assertEqual(p.find_position_with_side(game, 3, chess.WHITE), 2)
        self.assertEqual(p.find_position_with_side(game, 3, chess.BLACK), 3)


class TestDiagramContextHelpers(unittest.TestCase):
    def setUp(self):
        self.book = make_book([
            '<p>Intro</p><div class="diagram-inline" data-diagram="7"></div>'
            '<p>White to move. This is great.</p>',
            '<p>Other</p><div class="diagram-inline" data-diagram="8"></div>'
            '<p>Black to move 1... Nf6.</p><div class="diagram-inline" data-diagram="9"></div>',
        ])

    def test_get_diagram_side(self):
        import chess as ch
        self.assertEqual(p.get_diagram_side(self.book, '7'), ch.WHITE)
        self.assertEqual(p.get_diagram_side(self.book, '8'), ch.BLACK)


class TestMovesAroundDiagram(unittest.TestCase):
    def setUp(self):
        self.book = make_book([
            '<div class="game-notation">1. e4 e5 2. Nf3</div>'
            '<div class="diagram-inline" data-diagram="10"></div>'
            '<div class="game-notation">2... Nc6 3. Bb5</div>',
        ])

    def test_before(self):
        self.assertEqual(
            p.get_moves_before_diagram(self.book, '10'), ['e4', 'e5', 'Nf3']
        )

    def test_after(self):
        self.assertEqual(
            p.get_moves_after_diagram(self.book, '10'), ['Nc6', 'Bb5']
        )

    def test_find_diagram_move_context(self):
        self.assertEqual(
            p.find_diagram_move_context(self.book, '10'), ['e4', 'e5', 'Nf3']
        )

    def test_find_diagram_position(self):
        game = make_game(['e4', 'e5', 'Nf3', 'Nc6', 'Bb5'])
        idx = p.find_diagram_position(self.book, '10', game, ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5'])
        self.assertEqual(idx, 3)  # position after the moves before the diagram


class TestVariationTree(unittest.TestCase):
    def setUp(self):
        # Main line: e4 e5 Nf3 Nc6 Bb5
        # + branch at ply 0 (d4 sec) and at ply 2 (d4 exd4, with Nf6 nested).
        game = chess.pgn.Game()
        e4 = game.add_variation(game.board().parse_san('e4'))
        e5 = e4.add_variation(e4.board().parse_san('e5'))
        nf3 = e5.add_variation(e5.board().parse_san('Nf3'))
        nc6 = nf3.add_variation(nf3.board().parse_san('Nc6'))
        nc6.add_variation(nc6.board().parse_san('Bb5'))
        d4 = e5.add_variation(e5.board().parse_san('d4'))
        d4.add_variation(d4.board().parse_san('exd4'))
        d4.add_variation(d4.board().parse_san('Nf6'))
        game.add_variation(game.board().parse_san('d4'))
        self.game = game
        self.main = p.get_mainline_moves(game)

    def test_branches_after_diagram_only(self):
        self.assertEqual(p.extract_variation_tree(self.game, self.main, 3), [])

    def test_branch_at_diagram_index_kept(self):
        tree = p.extract_variation_tree(self.game, self.main, 2)
        self.assertEqual(len(tree), 1)
        br = tree[0]
        self.assertEqual(br['branch_ply'], 2)
        self.assertEqual(br['moves'], ['d4', 'exd4'])

    def test_nested_branch_ply_relative_to_parent_line(self):
        tree = p.extract_variation_tree(self.game, self.main, 0)
        d4_branch = [b for b in tree if b['branch_ply'] == 2][0]
        self.assertEqual(len(d4_branch['variations']), 1)
        nested = d4_branch['variations'][0]
        # Nf6 replaces exd4 = index 1 of the parent line [d4, exd4]
        self.assertEqual(nested['branch_ply'], 1)
        self.assertEqual(nested['moves'], ['Nf6'])

    def test_single_move_branch(self):
        tree = p.extract_variation_tree(self.game, self.main, 0)
        # Each branch also carries comment (default '') and nags (default [])
        self.assertIn({'branch_ply': 0, 'moves': ['d4'], 'variations': [],
                       'comment': '', 'nags': []}, tree)

    def test_no_game_or_moves(self):
        self.assertEqual(p.extract_variation_tree(None, self.main, 0), [])
        self.assertEqual(p.extract_variation_tree(self.game, [], 0), [])

    def test_validate_ok(self):
        tree = p.extract_variation_tree(self.game, self.main, 0)
        p.validate_variation_tree(chess.STARTING_FEN, self.main, tree, 'X')

    def test_validate_illegal_rejected(self):
        # After e4 e5, White to move: Nf6 (a black move) is illegal
        bad = [{'branch_ply': 2, 'moves': ['Nf6'], 'variations': []}]
        with self.assertRaises(ValueError):
            p.validate_variation_tree(chess.STARTING_FEN, self.main, bad, 'X')

    def test_validate_bad_branch_ply_rejected(self):
        bad = [{'branch_ply': 99, 'moves': ['d4'], 'variations': []}]
        with self.assertRaises(ValueError):
            p.validate_variation_tree(chess.STARTING_FEN, self.main, bad, 'X')

    def test_extract_diagram_variations_needs_matching_mainline(self):
        flat = {'7': {'moves': list(self.main), 'diagram_move_index': 2,
                      'variations': []}}
        chapters = [{'game': self.game, 'moves': list(self.main), 'nums': [7]}]
        self.assertEqual(p.extract_diagram_variations(flat, chapters), 1)
        self.assertEqual(len(flat['7']['variations']), 1)
        # Different main line and different position at the diagram
        # -> no attachment (stale branch_ply)
        flat2 = {'7': {'moves': ['d4', 'd5'], 'diagram_move_index': 2,
                       'variations': []}}
        self.assertEqual(p.extract_diagram_variations(flat2, chapters), 0)
        self.assertEqual(flat2['7']['variations'], [])

    def test_extract_diagram_variations_prefix_mainline_attaches(self):
        # The diagram line is a prefix of the chapter line, but the position
        # at diagram_move_index matches -> variations attached.
        flat = {'7': {'moves': ['e4', 'e5'], 'diagram_move_index': 2,
                      'variations': []}}
        chapters = [{'game': self.game, 'moves': list(self.main), 'nums': [7]}]
        self.assertEqual(p.extract_diagram_variations(flat, chapters), 1)
        self.assertEqual(len(flat['7']['variations']), 1)
        br = flat['7']['variations'][0]
        self.assertEqual(br['branch_ply'], 2)
        self.assertEqual(br['moves'], ['d4', 'exd4'])


class TestVariationTreeEnrichment(unittest.TestCase):
    """Comments and NAGs of sibling moves propagated into the branches."""

    def _sibling_game(self, comment='', nags=()):
        game = chess.pgn.Game()
        e4 = game.add_variation(game.board().parse_san('e4'))
        e4.add_variation(e4.board().parse_san('e5'))
        sib = game.add_variation(game.board().parse_san('d4'))
        sib.comment = comment
        sib.nags = list(nags)
        sib.add_variation(sib.board().parse_san('d5'))
        return game

    def test_comment_and_nags_attached(self):
        game = self._sibling_game('Center control', [1, 6])
        tree = p.extract_variation_tree(game, p.get_mainline_moves(game), 0)
        self.assertEqual(len(tree), 1)
        br = tree[0]
        self.assertEqual(br['comment'], 'Center control')
        self.assertEqual(br['nags'], [1, 6])

    def test_comment_stripped(self):
        game = self._sibling_game('  Keep the center.  ')
        tree = p.extract_variation_tree(game, p.get_mainline_moves(game), 0)
        self.assertEqual(tree[0]['comment'], 'Keep the center.')

    def test_defaults_when_empty(self):
        game = self._sibling_game()
        tree = p.extract_variation_tree(game, p.get_mainline_moves(game), 0)
        self.assertEqual(tree[0]['comment'], '')
        self.assertEqual(tree[0]['nags'], [])

    def test_nested_branches_get_keys(self):
        # nested branch: d4 exd4 (1...Nf6) -> Nf6 carries comment/nags
        game = chess.pgn.Game()
        e4 = game.add_variation(game.board().parse_san('e4'))
        e5 = e4.add_variation(e4.board().parse_san('e5'))
        e5.add_variation(e5.board().parse_san('Nf3'))
        d4 = e5.add_variation(e5.board().parse_san('d4'))
        d4.add_variation(d4.board().parse_san('exd4'))
        nf6 = d4.add_variation(d4.board().parse_san('Nf6'))
        nf6.comment = 'Soltis'
        nf6.nags = [1]
        game.add_variation(game.board().parse_san('d4'))
        tree = p.extract_variation_tree(game, p.get_mainline_moves(game), 0)
        d4_branch = [b for b in tree if b['branch_ply'] == 2][0]
        nested = d4_branch['variations'][0]
        self.assertEqual(nested['branch_ply'], 1)
        self.assertEqual(nested['moves'], ['Nf6'])
        self.assertEqual(nested['comment'], 'Soltis')
        self.assertEqual(nested['nags'], [1])
        # The parent branch, without comment, keeps the defaults
        self.assertEqual(d4_branch['comment'], '')
        self.assertEqual(d4_branch['nags'], [])


class TestVariationTreeSorting(unittest.TestCase):
    """Sort by relevance: closest to the diagram first, and at equal
    distance the longest first (stable relative order)."""

    def test_closest_and_longest_first(self):
        game = chess.pgn.Game()
        e4 = game.add_variation(game.board().parse_san('e4'))
        e5 = e4.add_variation(e4.board().parse_san('e5'))
        nf3 = e5.add_variation(e5.board().parse_san('Nf3'))
        nf3.add_variation(nf3.board().parse_san('Nc6'))
        nf3.add_variation(nf3.board().parse_san('d5'))
        d4 = e5.add_variation(e5.board().parse_san('d4'))
        d4.add_variation(d4.board().parse_san('exd4'))
        d4.add_variation(d4.board().parse_san('Nf6'))
        e5.add_variation(e5.board().parse_san('Bc4'))
        d4root = game.add_variation(game.board().parse_san('d4'))
        d4root.add_variation(d4root.board().parse_san('e5'))
        d4root.add_variation(d4root.board().parse_san('d5'))
        tree = p.extract_variation_tree(game, p.get_mainline_moves(game), 0)
        # top-level branches: ply0 (d4), ply2 (d4), ply2 (Bc4), ply3 (d5
        # under Nf3) -> sort by relevance: closest to the diagram first
        self.assertEqual([b['branch_ply'] for b in tree], [0, 2, 2, 3])
        # at equal distance, the longest first (d4 before Bc4)
        at_ply2 = [b for b in tree if b['branch_ply'] == 2]
        self.assertEqual([len(b['moves']) for b in at_ply2], [2, 1])

    def test_before_diagram_excluded_then_pertinence(self):
        game = chess.pgn.Game()
        e4 = game.add_variation(game.board().parse_san('e4'))
        e5 = e4.add_variation(e4.board().parse_san('e5'))
        e5.add_variation(e5.board().parse_san('Nf3'))
        e5.add_variation(e5.board().parse_san('d4'))
        game.add_variation(game.board().parse_san('d4'))
        tree = p.extract_variation_tree(game, p.get_mainline_moves(game), 2)
        self.assertEqual([b['branch_ply'] for b in tree], [2])


class TestMainlineMatching(unittest.TestCase):
    """SAN normalization + position comparison for _mainline_matches."""

    def test_suffix_only_difference_matches(self):
        from silman_parser.study import _mainline_matches
        # Real line with checkmate: 1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#
        data = ['e4', 'e5', 'Qh5', 'Nc6', 'Bc4', 'Nf6', 'Qxf7#']
        chapter = ['e4', 'e5', 'Qh5', 'Nc6', 'Bc4', 'Nf6', 'Qxf7']
        self.assertTrue(_mainline_matches(data, chapter, 7))

    def test_case_sensitive(self):
        from silman_parser.study import _mainline_matches
        # Normalization does not change case: 'qH5' != 'Qh5'
        data = ['e4', 'e5', 'Qh5']
        chapter = ['e4', 'e5', 'qH5']
        self.assertFalse(_mainline_matches(data, chapter, 3))

    def test_same_position_at_idx_matches(self):
        from silman_parser.study import _mainline_matches
        data = ['e4', 'e5']            # truncated diagram line
        chapter = ['e4', 'e5', 'Nf3', 'Nc6']
        self.assertTrue(_mainline_matches(data, chapter, 2))

    def test_different_position_no_match(self):
        from silman_parser.study import _mainline_matches
        data = ['d4', 'd5']
        chapter = ['e4', 'e5', 'Nf3']
        self.assertFalse(_mainline_matches(data, chapter, 2))

    def test_unreplayable_falls_back_to_strict(self):
        from silman_parser.study import _mainline_matches
        # Nf6 as White's 2nd move is illegal: replay impossible ->
        # falls back to strict comparison (different lists -> False)
        data = ['e4', 'Nf6']
        chapter = ['e4', 'e5', 'Nf3']
        self.assertFalse(_mainline_matches(data, chapter, 2))

    def test_norm_san_strips_check_and_mate_suffixes(self):
        from silman_parser.study import _norm_san
        self.assertEqual(_norm_san('Qxf7#'), 'Qxf7')
        self.assertEqual(_norm_san('Nf3+'), 'Nf3')
        self.assertEqual(_norm_san('O-O'), 'O-O')
        self.assertEqual(_norm_san('e4'), 'e4')


if __name__ == '__main__':
    unittest.main()