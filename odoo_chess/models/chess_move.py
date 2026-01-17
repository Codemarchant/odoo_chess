# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .chess_bot import CHESS_BOTS


class ChessMove(models.Model):
    _name = 'chess.move'
    _description = 'Chess Move'
    _order = 'game_id, sequence'

    game_id = fields.Many2one(
        'chess.game',
        string='Game',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(string='Move Number', required=True)
    player_id = fields.Many2one('res.users', string='Player')
    is_bot_move = fields.Boolean(string='Bot Move', default=False)
    bot_key = fields.Char(string='Bot Key')
    player_display = fields.Char(string='Played By', compute='_compute_player_display')

    # Move notation
    uci = fields.Char(string='UCI Notation', required=True, help='e.g., e2e4')
    san = fields.Char(string='SAN Notation', help='e.g., e4')

    # Position after move
    fen_after = fields.Char(string='FEN After Move')

    # Timing
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)

    # Time control tracking
    time_spent_ms = fields.Integer(
        string='Time Spent (ms)',
        default=0,
        help='Time spent on this move in milliseconds'
    )
    white_time_after = fields.Integer(
        string='White Time After (ms)',
        default=0,
        help='White player time remaining after this move in milliseconds'
    )
    black_time_after = fields.Integer(
        string='Black Time After (ms)',
        default=0,
        help='Black player time remaining after this move in milliseconds'
    )

    # Computed fields for display
    is_white_move = fields.Boolean(
        string='White Move',
        compute='_compute_is_white_move',
        store=True
    )

    @api.depends('sequence')
    def _compute_is_white_move(self):
        for move in self:
            # Odd sequence numbers are white moves (1, 3, 5, ...)
            move.is_white_move = move.sequence % 2 == 1

    @api.depends('player_id', 'is_bot_move', 'bot_key')
    def _compute_player_display(self):
        for move in self:
            if move.is_bot_move and move.bot_key:
                bot_info = CHESS_BOTS.get(move.bot_key, {})
                move.player_display = bot_info.get('name', 'Bot')
            elif move.player_id:
                move.player_display = move.player_id.name
            else:
                move.player_display = ''
