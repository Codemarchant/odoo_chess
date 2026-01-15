# -*- coding: utf-8 -*-
import random
from datetime import timedelta

from odoo import api, fields, models, _
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
        domain=[('share', '=', False)]  # Only internal users
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='pending', tracking=True, string='Status')

    color_choice = fields.Selection([
        ('white', 'Inviter plays White'),
        ('black', 'Inviter plays Black'),
        ('random', 'Random'),
    ], default='random', string='Color Choice')

    reward_text = fields.Text(string='Stakes/Reward')
    expires_at = fields.Datetime(
        string='Expires At',
        default=lambda self: fields.Datetime.now() + timedelta(hours=24)
    )
    message = fields.Text(string='Challenge Message')

    # Computed
    is_expired = fields.Boolean(compute='_compute_is_expired')

    @api.depends('expires_at')
    def _compute_is_expired(self):
        now = fields.Datetime.now()
        for invitation in self:
            invitation.is_expired = invitation.expires_at and invitation.expires_at < now

    @api.model_create_multi
    def create(self, vals_list):
        invitations = super().create(vals_list)
        for invitation in invitations:
            invitation._send_invitation_notification()
        return invitations

    def _send_invitation_notification(self):
        """Send notification to invitee about the chess invitation."""
        self.ensure_one()

        # Create activity for the invitee
        self.env['mail.activity'].sudo().create({
            'res_model_id': self.env['ir.model']._get_id('chess.invitation'),
            'res_id': self.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'summary': _('Chess Challenge from %s') % self.inviter_id.name,
            'note': self.message or _('%s has challenged you to a game of chess!') % self.inviter_id.name,
            'user_id': self.invitee_id.id,
            'date_deadline': self.expires_at.date() if self.expires_at else fields.Date.today(),
        })

        # Also send via bus for immediate notification
        channel = (self.env.cr.dbname, 'res.partner', self.invitee_id.partner_id.id)
        self.env['bus.bus']._sendone(channel, 'chess_invitation', {
            'type': 'invitation',
            'invitation_id': self.id,
            'inviter_name': self.inviter_id.name,
            'inviter_rating': self.inviter_id.chess_rating,
            'reward_text': self.reward_text,
            'message': self.message,
        })

    def action_accept(self):
        """Accept the invitation and create/start the game."""
        self.ensure_one()

        if self.state != 'pending':
            raise UserError(_('This invitation is no longer pending'))

        if self.is_expired:
            self.state = 'expired'
            raise UserError(_('This invitation has expired'))

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

        # Create the game
        game = self.env['chess.game'].create({
            'white_player_id': white_player.id,
            'black_player_id': black_player.id,
            'state': 'active',
            'reward_text': self.reward_text,
            'invitation_id': self.id,
        })

        self.write({
            'state': 'accepted',
            'game_id': game.id,
        })

        # Mark activity as done
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'chess.invitation'),
            ('res_id', '=', self.id),
        ])
        activities.action_done()

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

        # Mark activity as done
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'chess.invitation'),
            ('res_id', '=', self.id),
        ])
        activities.action_done()

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

        # Mark activity as done
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'chess.invitation'),
            ('res_id', '=', self.id),
        ])
        activities.unlink()

        return True

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
            ('expires_at', '>', fields.Datetime.now()),
        ])

    @api.model
    def _cron_expire_invitations(self):
        """Cron job to expire old invitations."""
        expired = self.search([
            ('state', '=', 'pending'),
            ('expires_at', '<', fields.Datetime.now()),
        ])
        expired.write({'state': 'expired'})
        return True
