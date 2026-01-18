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
    opponent_id = fields.Many2one('res.users', string='Opponent')

    # Bot opponent
    bot_key = fields.Selection(selection=get_bot_selection, string='Bot Opponent')

    # Color selection
    play_as = fields.Selection([
        ('random', 'Random'),
        ('white', 'White'),
        ('black', 'Black'),
    ], default='random', string='Play As')

    # Time Control
    time_control_type = fields.Selection([
        ('untimed', 'Untimed'),
        ('bullet', 'Bullet'),
        ('blitz', 'Blitz'),
        ('rapid', 'Rapid'),
        ('classical', 'Classical'),
        ('custom', 'Custom'),
    ], default='untimed', string='Time Control', required=True)

    time_control_preset = fields.Selection([
        # Bullet presets
        ('1+0', '1 min'),
        ('1+1', '1 | 1'),
        ('2+1', '2 | 1'),
        # Blitz presets
        ('3+0', '3 min'),
        ('3+2', '3 | 2'),
        ('5+0', '5 min'),
        ('5+3', '5 | 3'),
        # Rapid presets
        ('10+0', '10 min'),
        ('10+5', '10 | 5'),
        ('15+10', '15 | 10'),
        # Classical presets
        ('30+0', '30 min'),
        ('30+20', '30 | 20'),
        ('60+30', '60 | 30'),
    ], string='Time Preset')

    base_time_minutes = fields.Integer(
        string='Base Time (minutes)',
        default=5,
        help='Initial time on each player clock'
    )

    increment_seconds = fields.Integer(
        string='Increment (seconds)',
        default=0,
        help='Seconds added after each move'
    )

    # Stakes
    reward_text = fields.Text(
        string='Stakes/Reward',
        help='e.g., "Loser buys coffee" or "Winner gets bragging rights"'
    )

    # Challenge message
    message = fields.Text(
        string='Challenge Message',
    )

    @api.onchange('game_type')
    def _onchange_game_type(self):
        if self.game_type == 'bot':
            self.opponent_id = False
        else:
            self.bot_key = False

    @api.onchange('time_control_type')
    def _onchange_time_control_type(self):
        """Set default preset based on time control type."""
        presets = {
            'bullet': '1+0',
            'blitz': '5+0',
            'rapid': '10+0',
            'classical': '30+0',
        }
        if self.time_control_type in presets:
            self.time_control_preset = presets[self.time_control_type]
        elif self.time_control_type == 'untimed':
            self.time_control_preset = False
            self.base_time_minutes = 0
            self.increment_seconds = 0
        elif self.time_control_type == 'custom':
            self.time_control_preset = False
            # Keep existing values for custom or set defaults
            if not self.base_time_minutes:
                self.base_time_minutes = 5

    def _get_time_control_values(self):
        """Parse time control into base_time and increment values (in seconds)."""
        if self.time_control_type == 'untimed':
            return {'base_time': 0, 'increment': 0, 'is_timed': False}

        if self.time_control_type == 'custom':
            return {
                'base_time': self.base_time_minutes * 60,
                'increment': self.increment_seconds,
                'is_timed': True
            }

        # Parse preset (format: "X+Y" where X is minutes, Y is seconds increment)
        if self.time_control_preset:
            parts = self.time_control_preset.split('+')
            base_minutes = int(parts[0])
            increment = int(parts[1]) if len(parts) > 1 else 0
            return {
                'base_time': base_minutes * 60,
                'increment': increment,
                'is_timed': True
            }

        return {'base_time': 0, 'increment': 0, 'is_timed': False}

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

        # Get time control values
        time_vals = self._get_time_control_values()

        # Create invitation with time control
        invitation = self.env['chess.invitation'].create({
            'inviter_id': self.env.user.id,
            'invitee_id': self.opponent_id.id,
            'color_choice': color_choice,
            'reward_text': self.reward_text,
            'message': self.message,
            # Time control fields
            'is_timed': time_vals['is_timed'],
            'base_time': time_vals['base_time'],
            'increment': time_vals['increment'],
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

        # Get time control values
        time_vals = self._get_time_control_values()

        # Create game directly (no invitation needed for bot)
        game_vals = {
            'state': 'active',
            'reward_text': self.reward_text,
            'is_bot_game': True,
            'bot_key': self.bot_key,
            # Time control fields
            'is_timed': time_vals['is_timed'],
            'base_time': time_vals['base_time'],
            'increment': time_vals['increment'],
        }

        # Set initial time remaining (convert seconds to milliseconds)
        if time_vals['is_timed']:
            initial_time_ms = time_vals['base_time'] * 1000
            game_vals['white_time_remaining'] = initial_time_ms
            game_vals['black_time_remaining'] = initial_time_ms

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
