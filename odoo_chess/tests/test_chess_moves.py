# -*- coding: utf-8 -*-
import chess

from odoo.tests.common import TransactionCase

from odoo.addons.odoo_chess.models.chess_bot import get_bot_move, CHESS_BOTS


class TestChessMoves(TransactionCase):
    """Test chess move validation and special moves."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_white = cls.env['res.users'].create({
            'name': 'White Player',
            'login': 'white_moves_test',
            'email': 'white_moves@test.com',
        })
        cls.user_black = cls.env['res.users'].create({
            'name': 'Black Player',
            'login': 'black_moves_test',
            'email': 'black_moves@test.com',
        })

    def _create_active_game(self):
        """Helper to create an active game."""
        return self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

    def test_pawn_single_push(self):
        """Test pawn single square advance."""
        game = self._create_active_game()
        result = game.with_user(self.user_white).action_make_move('e2e3')

        self.assertTrue(result.get('success'))
        self.assertEqual(result['san'], 'e3')

    def test_pawn_double_push(self):
        """Test pawn double square advance from starting position."""
        game = self._create_active_game()
        result = game.with_user(self.user_white).action_make_move('e2e4')

        self.assertTrue(result.get('success'))
        self.assertEqual(result['san'], 'e4')

    def test_pawn_capture(self):
        """Test pawn capture."""
        game = self._create_active_game()

        # Set up position for capture
        game.with_user(self.user_white).action_make_move('e2e4')
        game.with_user(self.user_black).action_make_move('d7d5')

        result = game.with_user(self.user_white).action_make_move('e4d5')

        self.assertTrue(result.get('success'))
        self.assertIn('x', result['san'])  # Capture notation

    def test_castling_kingside(self):
        """Test kingside castling."""
        game = self._create_active_game()

        # Set up for castling: move knight and bishop out of the way
        moves = [
            ('e2e4', self.user_white),
            ('e7e5', self.user_black),
            ('g1f3', self.user_white),  # Knight out
            ('b8c6', self.user_black),
            ('f1c4', self.user_white),  # Bishop out
            ('g8f6', self.user_black),
        ]

        for uci, player in moves:
            game.with_user(player).action_make_move(uci)

        # Now castle kingside
        result = game.with_user(self.user_white).action_make_move('e1g1')

        self.assertTrue(result.get('success'))
        self.assertEqual(result['san'], 'O-O')

    def test_castling_queenside(self):
        """Test queenside castling."""
        game = self._create_active_game()

        # Set up for queenside castling
        moves = [
            ('d2d4', self.user_white),
            ('d7d5', self.user_black),
            ('b1c3', self.user_white),  # Knight out
            ('b8c6', self.user_black),
            ('c1f4', self.user_white),  # Bishop out
            ('c8f5', self.user_black),
            ('d1d2', self.user_white),  # Queen out
            ('d8d7', self.user_black),
        ]

        for uci, player in moves:
            game.with_user(player).action_make_move(uci)

        # Now castle queenside
        result = game.with_user(self.user_white).action_make_move('e1c1')

        self.assertTrue(result.get('success'))
        self.assertEqual(result['san'], 'O-O-O')

    def test_knight_move(self):
        """Test knight L-shaped move."""
        game = self._create_active_game()
        result = game.with_user(self.user_white).action_make_move('g1f3')

        self.assertTrue(result.get('success'))
        self.assertEqual(result['san'], 'Nf3')

    def test_bishop_diagonal_move(self):
        """Test bishop diagonal movement."""
        game = self._create_active_game()

        game.with_user(self.user_white).action_make_move('e2e4')
        game.with_user(self.user_black).action_make_move('e7e5')

        result = game.with_user(self.user_white).action_make_move('f1c4')

        self.assertTrue(result.get('success'))
        self.assertEqual(result['san'], 'Bc4')

    def test_illegal_move_through_piece(self):
        """Test that piece cannot move through another piece."""
        game = self._create_active_game()

        # Try to move rook through pawn
        result = game.with_user(self.user_white).action_make_move('a1a5')

        self.assertTrue(result.get('error'))

    def test_illegal_move_into_check(self):
        """Test that king cannot move into check."""
        # Set up a position where moving king would be into check
        game = self._create_active_game()
        game.fen = 'k7/8/8/8/8/8/4r3/4K3 w - - 0 1'  # King vs King+Rook

        # Try to move king into check (e1f1 - rook controls f-file? Actually e-file)
        # The rook is on e2, so king on e1 is already attacked
        # Let's use a simpler example
        game.fen = 'k7/8/8/8/8/8/8/r3K3 w - - 0 1'  # Rook on a1

        # King can't move to d1 because rook attacks it
        result = game.with_user(self.user_white).action_make_move('e1d1')

        self.assertTrue(result.get('error'))

    def test_en_passant(self):
        """Test en passant capture."""
        game = self._create_active_game()

        # Set up for en passant
        moves = [
            ('e2e4', self.user_white),
            ('a7a6', self.user_black),
            ('e4e5', self.user_white),
            ('d7d5', self.user_black),  # Black pawn double push - enables en passant
        ]

        for uci, player in moves:
            game.with_user(player).action_make_move(uci)

        # En passant capture
        result = game.with_user(self.user_white).action_make_move('e5d6')

        self.assertTrue(result.get('success'))

    def test_promotion(self):
        """Test pawn promotion."""
        game = self._create_active_game()

        # Set up position with pawn ready to promote
        game.fen = '8/P7/8/8/8/8/8/k1K5 w - - 0 1'

        # Promote to queen
        result = game.with_user(self.user_white).action_make_move('a7a8q')

        self.assertTrue(result.get('success'))
        self.assertIn('Q', game.fen)  # Queen appeared

    def test_move_history_recorded(self):
        """Test that moves are recorded in history."""
        game = self._create_active_game()

        game.with_user(self.user_white).action_make_move('e2e4')
        game.with_user(self.user_black).action_make_move('e7e5')
        game.with_user(self.user_white).action_make_move('g1f3')

        self.assertEqual(len(game.move_ids), 3)
        self.assertEqual(game.move_ids[0].uci, 'e2e4')
        self.assertEqual(game.move_ids[0].san, 'e4')
        self.assertEqual(game.move_ids[1].uci, 'e7e5')
        self.assertEqual(game.move_ids[2].uci, 'g1f3')

    def test_stalemate_detection(self):
        """Test stalemate detection."""
        game = self._create_active_game()

        # Famous stalemate position
        game.fen = 'k7/8/1K6/8/8/8/8/7Q w - - 0 1'

        # This move creates stalemate
        result = game.with_user(self.user_white).action_make_move('h1a1')

        # After Qa1, black king has no legal moves but is not in check = stalemate
        self.assertEqual(game.state, 'completed')
        self.assertEqual(game.result, 'draw')
        self.assertEqual(game.result_reason, 'stalemate')

    def test_check_indication(self):
        """Test that check is detected."""
        game = self._create_active_game()

        # Set up for quick check
        moves = [
            ('e2e4', self.user_white),
            ('f7f6', self.user_black),
            ('d1h5', self.user_white),  # Queen gives check
        ]

        for uci, player in moves:
            game.with_user(player).action_make_move(uci)

        self.assertTrue(game.is_check)
        self.assertIn('+', game.move_ids[-1].san)  # Check notation


class TestChessBot(TransactionCase):
    """Test chess bot functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Test Player',
            'login': 'test_bot_player',
            'email': 'test_bot@test.com',
        })

    def test_beginner_bot_returns_legal_move(self):
        """Test that beginner bot returns a legal move."""
        fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
        board = chess.Board(fen)

        move_uci = get_bot_move('beginner_bob', fen)

        self.assertIsNotNone(move_uci)
        move = chess.Move.from_uci(move_uci)
        self.assertIn(move, board.legal_moves)

    def test_casual_bot_returns_legal_move(self):
        """Test that casual bot returns a legal move."""
        fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
        board = chess.Board(fen)

        move_uci = get_bot_move('casual_carl', fen)

        self.assertIsNotNone(move_uci)
        move = chess.Move.from_uci(move_uci)
        self.assertIn(move, board.legal_moves)

    def test_randy_ram_returns_legal_move(self):
        """Test that Randy Ram (hardest bot) returns a legal move."""
        fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
        board = chess.Board(fen)

        move_uci = get_bot_move('randy_ram', fen)

        self.assertIsNotNone(move_uci)
        move = chess.Move.from_uci(move_uci)
        self.assertIn(move, board.legal_moves)

    def test_bot_finds_capture(self):
        """Test that bot finds obvious captures."""
        # Position with free queen capture
        fen = 'k7/8/8/8/4q3/8/8/4K2R w - - 0 1'  # Rook can take queen

        move_uci = get_bot_move('serious_sam', fen)

        # Bot should find the queen capture
        self.assertEqual(move_uci, 'h1e1')  # Rook takes queen

    def test_all_bots_defined(self):
        """Test that all expected bots are defined."""
        expected_bots = ['beginner_bob', 'casual_carl', 'serious_sam', 'randy_ram']
        for bot_key in expected_bots:
            self.assertIn(bot_key, CHESS_BOTS)
            self.assertIn('name', CHESS_BOTS[bot_key])
            self.assertIn('depth', CHESS_BOTS[bot_key])
            self.assertIn('rating', CHESS_BOTS[bot_key])
