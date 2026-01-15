# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


class TestChessGame(TransactionCase):
    """Test chess game core functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_white = cls.env['res.users'].create({
            'name': 'White Player',
            'login': 'white_player',
            'email': 'white@test.com',
        })
        cls.user_black = cls.env['res.users'].create({
            'name': 'Black Player',
            'login': 'black_player',
            'email': 'black@test.com',
        })

    def test_game_creation(self):
        """Test basic game creation."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        self.assertEqual(game.state, 'active')
        self.assertEqual(game.fen, STARTING_FEN)
        self.assertEqual(game.move_count, 0)
        self.assertEqual(game.result, 'ongoing')
        self.assertEqual(game.current_player_id, self.user_white)

    def test_initial_fen(self):
        """Test that game starts with standard position."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })
        self.assertEqual(game.fen, STARTING_FEN)

    def test_valid_move(self):
        """Test that legal move updates FEN correctly."""
        game = self.env['chess.game'].with_user(self.user_white).create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        result = game.with_user(self.user_white).action_make_move('e2e4')

        self.assertTrue(result.get('success'))
        self.assertEqual(game.move_count, 1)
        self.assertIn('e4', game.fen.lower())  # Pawn on e4

    def test_invalid_move_rejected(self):
        """Test that illegal move returns error."""
        game = self.env['chess.game'].with_user(self.user_white).create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # Pawn can't move 3 squares
        result = game.with_user(self.user_white).action_make_move('e2e5')

        self.assertTrue(result.get('error'))
        self.assertEqual(game.move_count, 0)
        self.assertEqual(game.fen, STARTING_FEN)

    def test_wrong_turn_rejected(self):
        """Test that move by wrong player is rejected."""
        game = self.env['chess.game'].with_user(self.user_white).create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # It's white's turn, black tries to move
        result = game.with_user(self.user_black).action_make_move('e7e5')

        self.assertTrue(result.get('error'))
        self.assertIn('turn', result['error'].lower())

    def test_move_alternation(self):
        """Test that turns alternate correctly."""
        game = self.env['chess.game'].with_user(self.user_white).create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # White moves
        game.with_user(self.user_white).action_make_move('e2e4')
        self.assertEqual(game.current_player_id, self.user_black)

        # Black moves
        game.with_user(self.user_black).action_make_move('e7e5')
        self.assertEqual(game.current_player_id, self.user_white)

    def test_resignation(self):
        """Test resignation ends game correctly."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        game.with_user(self.user_white).action_resign()

        self.assertEqual(game.state, 'completed')
        self.assertEqual(game.result, 'black_wins')
        self.assertEqual(game.result_reason, 'resignation')

    def test_draw_offer_flow(self):
        """Test draw offer and acceptance."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # White offers draw
        game.with_user(self.user_white).action_offer_draw()
        self.assertEqual(game.draw_offered_by, self.user_white)

        # Black accepts
        game.with_user(self.user_black).action_accept_draw()

        self.assertEqual(game.state, 'completed')
        self.assertEqual(game.result, 'draw')
        self.assertEqual(game.result_reason, 'draw_agreement')

    def test_draw_decline(self):
        """Test declining draw offer."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        game.with_user(self.user_white).action_offer_draw()
        game.with_user(self.user_black).action_decline_draw()

        self.assertEqual(game.state, 'active')
        self.assertFalse(game.draw_offered_by)

    def test_cannot_accept_own_draw(self):
        """Test that player cannot accept their own draw offer."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        game.with_user(self.user_white).action_offer_draw()

        with self.assertRaises(UserError):
            game.with_user(self.user_white).action_accept_draw()

    def test_checkmate_scholars_mate(self):
        """Test checkmate detection with Scholar's Mate."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # Scholar's Mate sequence
        moves = [
            ('e2e4', self.user_white),  # 1. e4
            ('e7e5', self.user_black),  # 1... e5
            ('f1c4', self.user_white),  # 2. Bc4
            ('b8c6', self.user_black),  # 2... Nc6
            ('d1h5', self.user_white),  # 3. Qh5
            ('g8f6', self.user_black),  # 3... Nf6?? (blunder)
            ('h5f7', self.user_white),  # 4. Qxf7# Checkmate!
        ]

        for uci, player in moves:
            game.with_user(player).action_make_move(uci)

        self.assertEqual(game.state, 'completed')
        self.assertEqual(game.result, 'white_wins')
        self.assertEqual(game.result_reason, 'checkmate')

    def test_game_state_serialization(self):
        """Test get_game_state returns correct structure."""
        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
            'reward_text': 'Winner buys coffee!',
        })

        state = game.with_user(self.user_white).get_game_state()

        self.assertEqual(state['id'], game.id)
        self.assertEqual(state['state'], 'active')
        self.assertEqual(state['fen'], STARTING_FEN)
        self.assertEqual(state['my_color'], 'white')
        self.assertTrue(state['is_my_turn'])
        self.assertEqual(state['reward_text'], 'Winner buys coffee!')
