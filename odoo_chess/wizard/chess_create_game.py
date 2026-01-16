# -*- coding: utf-8 -*-
import random

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.odoo_chess.models.chess_bot import get_bot_selection


class ChessCreateGame(models.TransientModel):
    _name = 'chess.create.game'
    _description = 'Create Chess Game Wizard'

    game_type = fields.Selection([
        ('human', 'Play vs Human'),
        ('bot', 'Play vs Bot'),
    ], default='human', string='Game Type', required=True)

    # Human opponent
    opponent_id = fields.Many2one(
        'res.users',
        string='Opponent',
        domain="[('share', '=', False), ('id', '!=', uid)]"
    )

    # Bot opponent
    bot_key = fields.Selection(selection=get_bot_selection, string='Bot Opponent')

    # Color selection
    play_as = fields.Selection([
        ('random', 'Random'),
        ('white', 'White'),
        ('black', 'Black'),
    ], default='random', string='Play As')

    # Stakes
    reward_text = fields.Text(
        string='Stakes/Reward',
        help='e.g., "Loser buys coffee" or "Winner gets bragging rights"'
    )

    # Challenge message
    message = fields.Text(
        string='Challenge Message',
        placeholder='Add a message to your challenge...'
    )

    @api.onchange('game_type')
    def _onchange_game_type(self):
        if self.game_type == 'bot':
            self.opponent_id = False
        else:
            self.bot_key = False

    def action_create_game(self):
        """Create game based on type selection."""
        self.ensure_one()

        if self.game_type == 'human':
            return self._create_human_game()
        else:
            return self._create_bot_game()

    def _create_human_game(self):
        """Create a game invitation for a human opponent."""
        if not self.opponent_id:
            raise UserError(_('Please select an opponent'))

        if self.opponent_id == self.env.user:
            raise UserError(_('You cannot challenge yourself'))

        # Map play_as to color_choice
        color_choice = self.play_as

        # Create invitation
        invitation = self.env['chess.invitation'].create({
            'inviter_id': self.env.user.id,
            'invitee_id': self.opponent_id.id,
            'color_choice': color_choice,
            'reward_text': self.reward_text,
            'message': self.message,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'chess.invitation',
            'res_id': invitation.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    def _create_bot_game(self):
        """Create a game against a bot."""
        if not self.bot_key:
            raise UserError(_('Please select a bot opponent'))

        # Determine colors
        if self.play_as == 'random':
            user_plays_white = random.choice([True, False])
        else:
            user_plays_white = self.play_as == 'white'

        # Create game directly (no invitation needed for bot)
        game_vals = {
            'state': 'active',
            'reward_text': self.reward_text,
            'is_bot_game': True,
            'bot_key': self.bot_key,
        }

        if user_plays_white:
            game_vals.update({
                'white_player_id': self.env.user.id,
                'black_player_id': self.env.user.id,  # Placeholder for bot games
                'bot_color': 'black',
            })
        else:
            game_vals.update({
                'white_player_id': self.env.user.id,  # Placeholder for bot games
                'black_player_id': self.env.user.id,
                'bot_color': 'white',
            })

        game = self.env['chess.game'].create(game_vals)

        # If bot plays white, make bot's first move
        if not user_plays_white:
            game._schedule_bot_move()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'chess.game',
            'res_id': game.id,
            'view_mode': 'form',
            'target': 'current',
        }
