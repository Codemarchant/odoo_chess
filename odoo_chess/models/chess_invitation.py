# -*- coding: utf-8 -*-
import random

from markupsafe import Markup, escape

from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.exceptions import UserError


class ChessInvitation(models.Model):
    _name = 'chess.invitation'
    _description = 'Chess Game Invitation'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    game_id = fields.Many2one(
        'chess.game',
        string='Game',
        ondelete='cascade',
        readonly=True
    )
    inviter_id = fields.Many2one(
        'res.users',
        string='Inviter',
        required=True,
        readonly=True,
        default=lambda self: self.env.user
    )
    invitee_id = fields.Many2one(
        'res.users',
        string='Invitee',
        required=True,
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
    ], default='pending', tracking=True, string='Status')

    color_choice = fields.Selection([
        ('white', 'Inviter plays White'),
        ('black', 'Inviter plays Black'),
        ('random', 'Random'),
    ], default='random', string='Color Choice')

    reward_text = fields.Text(string='Stakes/Reward')
    message = fields.Text(string='Challenge Message')

    # Time Control
    is_timed = fields.Boolean(string='Timed Game', default=False)
    base_time = fields.Integer(
        string='Base Time (seconds)',
        default=0,
        help='Initial time for each player in seconds'
    )
    increment = fields.Integer(
        string='Increment (seconds)',
        default=0,
        help='Time added after each move in seconds'
    )
    time_control_display = fields.Char(
        string='Time Control',
        compute='_compute_time_control_display'
    )

    @api.depends('is_timed', 'base_time', 'increment')
    def _compute_time_control_display(self):
        for inv in self:
            if not inv.is_timed:
                inv.time_control_display = 'Untimed'
            else:
                minutes = inv.base_time // 60
                if inv.increment:
                    inv.time_control_display = f'{minutes}+{inv.increment}'
                else:
                    inv.time_control_display = f'{minutes} min'

    @api.model_create_multi
    def create(self, vals_list):
        invitations = super().create(vals_list)
        for invitation in invitations:
            invitation._send_invitation_notification()
        return invitations

    def _send_invitation_notification(self):
        """Send notification to invitee about the chess invitation."""
        self.ensure_one()

        # Build the notification message body using Odoo's URL helper
        invitation_url = self._notify_get_action_link('view')

        body_parts = [
            '<p><strong>%s</strong> has challenged you to a game of chess!</p>' % escape(self.inviter_id.name),
        ]

        if self.message:
            body_parts.append('<p><em>"%s"</em></p>' % escape(self.message))

        if self.reward_text:
            body_parts.append('<p><strong>Stakes:</strong> %s</p>' % escape(self.reward_text))

        body_parts.append(
            '<p><a href="%s" class="btn btn-primary">View Challenge</a></p>' % invitation_url
        )

        body = Markup(''.join(body_parts))

        # Post message and notify the invitee
        self.message_post(
            body=body,
            subject=_('Chess Challenge from %s') % self.inviter_id.name,
            partner_ids=[self.invitee_id.partner_id.id],
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
        )

        # Also send via bus for immediate notification
        channel = (self.env.cr.dbname, 'res.partner', self.invitee_id.partner_id.id)
        self.env['bus.bus']._sendone(channel, 'chess_invitation', {
            'type': 'invitation',
            'invitation_id': self.id,
            'inviter_name': self.inviter_id.name,
            'inviter_rating': self.inviter_id.chess_rating,
            'reward_text': self.reward_text,
            'message': self.message,
            'time_control_display': self.time_control_display,
        })

    def action_accept(self):
        """Accept the invitation and create/start the game."""
        self.ensure_one()

        if self.state != 'pending':
            raise UserError(_('This invitation is no longer pending'))

        if self.env.user != self.invitee_id:
            raise UserError(_('Only the invitee can accept this invitation'))

        # Determine colors
        if self.color_choice == 'white':
            white_player = self.inviter_id
            black_player = self.invitee_id
        elif self.color_choice == 'black':
            white_player = self.invitee_id
            black_player = self.inviter_id
        else:  # random
            if random.choice([True, False]):
                white_player = self.inviter_id
                black_player = self.invitee_id
            else:
                white_player = self.invitee_id
                black_player = self.inviter_id

        # Create the game with time control
        game_vals = {
            'white_player_id': white_player.id,
            'black_player_id': black_player.id,
            'state': 'active',
            'reward_text': self.reward_text,
            'invitation_id': self.id,
            # Time control fields
            'is_timed': self.is_timed,
            'base_time': self.base_time,
            'increment': self.increment,
        }

        # Set initial time remaining (convert seconds to milliseconds)
        if self.is_timed:
            initial_time_ms = self.base_time * 1000
            game_vals['white_time_remaining'] = initial_time_ms
            game_vals['black_time_remaining'] = initial_time_ms

        game = self.env['chess.game'].create(game_vals)

        self.write({
            'state': 'accepted',
            'game_id': game.id,
        })

        # Create or get chat channel between players and send game start message
        self._create_game_chat(game)

        # Notify inviter
        self._notify_inviter_accepted()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'chess.game',
            'res_id': game.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_decline(self):
        """Decline the invitation."""
        self.ensure_one()

        if self.state != 'pending':
            raise UserError(_('This invitation is no longer pending'))

        if self.env.user != self.invitee_id:
            raise UserError(_('Only the invitee can decline this invitation'))

        self.state = 'declined'

        # Notify inviter
        self._notify_inviter_declined()

        return True

    def action_cancel(self):
        """Cancel the invitation (by inviter)."""
        self.ensure_one()

        if self.state != 'pending':
            raise UserError(_('This invitation is no longer pending'))

        if self.env.user != self.inviter_id:
            raise UserError(_('Only the inviter can cancel this invitation'))

        self.state = 'cancelled'
        return True

    def _create_game_chat(self, game):
        """Create a chat channel between players and send game start message."""
        self.ensure_one()

        # Get or create chat channel between the two players
        partner_ids = [self.inviter_id.partner_id.id, self.invitee_id.partner_id.id]
        channel = self.env['discuss.channel']._get_or_create_chat(partner_ids)

        # Pin the channel for both users so chat popup appears for both
        channel.sudo().channel_member_ids.filtered(
            lambda m: m.partner_id.id in partner_ids
        ).write({'unpin_dt': False})

        # Broadcast to both partners to open the chat
        channel._broadcast(partner_ids)

        # Build message with link to game
        game_url = game._notify_get_action_link('view')
        body = Markup(
            '<p>♟️ Chess game started! <a href="%s">Open Game</a></p>'
        ) % game_url

        # Post message as superuser so both players get notified (neither is the author)
        channel.with_user(SUPERUSER_ID).message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=partner_ids,
        )

    def _notify_inviter_accepted(self):
        """Notify inviter that invitation was accepted."""
        channel = (self.env.cr.dbname, 'res.partner', self.inviter_id.partner_id.id)
        self.env['bus.bus']._sendone(channel, 'chess_invitation_response', {
            'type': 'accepted',
            'invitation_id': self.id,
            'game_id': self.game_id.id,
            'invitee_name': self.invitee_id.name,
        })

    def _notify_inviter_declined(self):
        """Notify inviter that invitation was declined."""
        channel = (self.env.cr.dbname, 'res.partner', self.inviter_id.partner_id.id)
        self.env['bus.bus']._sendone(channel, 'chess_invitation_response', {
            'type': 'declined',
            'invitation_id': self.id,
            'invitee_name': self.invitee_id.name,
        })

    @api.model
    def get_my_pending_invitations(self):
        """Get pending invitations for current user (as invitee)."""
        return self.search([
            ('invitee_id', '=', self.env.user.id),
            ('state', '=', 'pending'),
        ])
