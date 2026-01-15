# -*- coding: utf-8 -*-
from odoo import api, fields, models


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

    # Move notation
    uci = fields.Char(string='UCI Notation', required=True, help='e.g., e2e4')
    san = fields.Char(string='SAN Notation', help='e.g., e4')

    # Position after move
    fen_after = fields.Char(string='FEN After Move')

    # Timing
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)

    # Computed fields for display
    move_pair_number = fields.Integer(
        string='Move Pair',
        compute='_compute_move_pair_number',
        store=True
    )
    is_white_move = fields.Boolean(
        string='White Move',
        compute='_compute_is_white_move',
        store=True
    )

    @api.depends('sequence')
    def _compute_move_pair_number(self):
        for move in self:
            # Move pair: 1 for moves 1-2, 2 for moves 3-4, etc.
            move.move_pair_number = (move.sequence + 1) // 2 + ((move.sequence + 1) % 2)

    @api.depends('sequence')
    def _compute_is_white_move(self):
        for move in self:
            # Odd sequence numbers are white moves (1, 3, 5, ...)
            move.is_white_move = move.sequence % 2 == 1
