# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Chess statistics
    chess_rating = fields.Integer(
        string='Chess Rating',
        default=1200,
        help='Elo rating for chess games'
    )
    chess_wins = fields.Integer(string='Chess Wins', default=0)
    chess_losses = fields.Integer(string='Chess Losses', default=0)
    chess_draws = fields.Integer(string='Chess Draws', default=0)
    chess_games_played = fields.Integer(
        string='Games Played',
        compute='_compute_chess_games_played',
        store=True
    )

    # Allow these fields to be written by the user themselves
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'chess_rating',
            'chess_wins',
            'chess_losses',
            'chess_draws',
            'chess_games_played',
        ]

    @api.depends('chess_wins', 'chess_losses', 'chess_draws')
    def _compute_chess_games_played(self):
        for user in self:
            user.chess_games_played = user.chess_wins + user.chess_losses + user.chess_draws

    def get_chess_stats(self):
        """Return chess statistics for the user."""
        self.ensure_one()
        win_rate = 0
        if self.chess_games_played > 0:
            win_rate = round((self.chess_wins / self.chess_games_played) * 100, 1)

        return {
            'rating': self.chess_rating,
            'wins': self.chess_wins,
            'losses': self.chess_losses,
            'draws': self.chess_draws,
            'games_played': self.chess_games_played,
            'win_rate': win_rate,
        }

    @api.model
    def get_leaderboard(self, limit=20):
        """Return top chess players by rating."""
        return self.search(
            [('chess_games_played', '>', 0)],
            order='chess_rating desc',
            limit=limit
        ).read(['name', 'chess_rating', 'chess_wins', 'chess_losses', 'chess_draws', 'chess_games_played'])
