# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestChessElo(TransactionCase):
    """Test Elo rating calculations."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_white = cls.env['res.users'].create({
            'name': 'White Player',
            'login': 'white_elo_test',
            'email': 'white_elo@test.com',
            'chess_rating': 1200,
        })
        cls.user_black = cls.env['res.users'].create({
            'name': 'Black Player',
            'login': 'black_elo_test',
            'email': 'black_elo@test.com',
            'chess_rating': 1200,
        })

    def test_elo_equal_rating_white_wins(self):
        """Test Elo update when equal-rated players play and white wins."""
        initial_white = self.user_white.chess_rating
        initial_black = self.user_black.chess_rating

        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # White wins
        game.with_user(self.user_white).action_resign()
        # Oops, that's wrong - resign means white loses. Let's use a direct method
        game.state = 'active'  # Reset
        game.result = 'ongoing'
        game.result_reason = False

        # End game with white winning
        game._end_game('white_wins', 'checkmate')

        # With equal ratings and K=32, winner gains ~16, loser loses ~16
        self.user_white.invalidate_recordset()
        self.user_black.invalidate_recordset()

        self.assertGreater(self.user_white.chess_rating, initial_white)
        self.assertLess(self.user_black.chess_rating, initial_black)

        # For equal ratings: expected score is 0.5, actual is 1/0
        # New rating = old + K * (actual - expected) = 1200 + 32 * (1 - 0.5) = 1216
        self.assertEqual(self.user_white.chess_rating, 1216)
        self.assertEqual(self.user_black.chess_rating, 1184)

    def test_elo_equal_rating_draw(self):
        """Test Elo update when equal-rated players draw."""
        self.user_white.chess_rating = 1200
        self.user_black.chess_rating = 1200

        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        game._end_game('draw', 'draw_agreement')

        self.user_white.invalidate_recordset()
        self.user_black.invalidate_recordset()

        # Draw between equal-rated players should result in no change
        # Actually: 1200 + 32 * (0.5 - 0.5) = 1200
        self.assertEqual(self.user_white.chess_rating, 1200)
        self.assertEqual(self.user_black.chess_rating, 1200)

    def test_elo_upset_win(self):
        """Test that lower-rated player gains more for upset win."""
        self.user_white.chess_rating = 1000
        self.user_black.chess_rating = 1400

        initial_white = self.user_white.chess_rating
        initial_black = self.user_black.chess_rating

        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # Upset: lower-rated white wins
        game._end_game('white_wins', 'checkmate')

        self.user_white.invalidate_recordset()
        self.user_black.invalidate_recordset()

        # Lower rated player gains more for upset
        white_gain = self.user_white.chess_rating - initial_white
        black_loss = initial_black - self.user_black.chess_rating

        # Expected score for 1000 vs 1400: ~0.09 for white
        # So win gives: 32 * (1 - 0.09) ≈ 29 points
        self.assertGreater(white_gain, 20)  # Significant gain for upset
        self.assertEqual(white_gain, black_loss)  # Rating is zero-sum

    def test_elo_expected_win(self):
        """Test that higher-rated player gains less for expected win."""
        self.user_white.chess_rating = 1400
        self.user_black.chess_rating = 1000

        initial_white = self.user_white.chess_rating

        game = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })

        # Expected result: higher-rated white wins
        game._end_game('white_wins', 'checkmate')

        self.user_white.invalidate_recordset()

        # Higher rated player gains less for expected win
        white_gain = self.user_white.chess_rating - initial_white

        # Expected score for 1400 vs 1000: ~0.91 for white
        # So win gives: 32 * (1 - 0.91) ≈ 3 points
        self.assertLess(white_gain, 10)

    def test_win_loss_draw_counters(self):
        """Test that win/loss/draw counters update correctly."""
        self.user_white.chess_wins = 0
        self.user_white.chess_losses = 0
        self.user_white.chess_draws = 0
        self.user_black.chess_wins = 0
        self.user_black.chess_losses = 0
        self.user_black.chess_draws = 0

        # Game 1: White wins
        game1 = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })
        game1._end_game('white_wins', 'checkmate')

        self.user_white.invalidate_recordset()
        self.user_black.invalidate_recordset()

        self.assertEqual(self.user_white.chess_wins, 1)
        self.assertEqual(self.user_white.chess_losses, 0)
        self.assertEqual(self.user_black.chess_wins, 0)
        self.assertEqual(self.user_black.chess_losses, 1)

        # Game 2: Draw
        game2 = self.env['chess.game'].create({
            'white_player_id': self.user_white.id,
            'black_player_id': self.user_black.id,
            'state': 'active',
        })
        game2._end_game('draw', 'stalemate')

        self.user_white.invalidate_recordset()
        self.user_black.invalidate_recordset()

        self.assertEqual(self.user_white.chess_wins, 1)
        self.assertEqual(self.user_white.chess_draws, 1)
        self.assertEqual(self.user_black.chess_draws, 1)

    def test_games_played_computed(self):
        """Test that games_played is computed correctly."""
        self.user_white.chess_wins = 5
        self.user_white.chess_losses = 3
        self.user_white.chess_draws = 2

        self.user_white.invalidate_recordset()

        self.assertEqual(self.user_white.chess_games_played, 10)
