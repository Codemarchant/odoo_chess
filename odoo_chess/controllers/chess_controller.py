# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ChessController(http.Controller):
    """Controller for chess game operations via HTTP."""

    @http.route('/chess/game/<int:game_id>/state', type='jsonrpc', auth='user')
    def get_game_state(self, game_id):
        """Get the full state of a chess game."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        return game.get_game_state()

    @http.route('/chess/game/<int:game_id>/move', type='jsonrpc', auth='user')
    def make_move(self, game_id, uci_move):
        """Make a move in the chess game."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        result = game.action_make_move(uci_move)
        return result

    @http.route('/chess/game/<int:game_id>/resign', type='jsonrpc', auth='user')
    def resign_game(self, game_id):
        """Resign from a chess game."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        try:
            game.action_resign()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/game/<int:game_id>/offer_draw', type='jsonrpc', auth='user')
    def offer_draw(self, game_id):
        """Offer a draw in a chess game."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        try:
            game.action_offer_draw()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/game/<int:game_id>/accept_draw', type='jsonrpc', auth='user')
    def accept_draw(self, game_id):
        """Accept a draw offer."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        try:
            game.action_accept_draw()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/game/<int:game_id>/decline_draw', type='jsonrpc', auth='user')
    def decline_draw(self, game_id):
        """Decline a draw offer."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        try:
            game.action_decline_draw()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/game/<int:game_id>/claim_draw', type='jsonrpc', auth='user')
    def claim_draw(self, game_id):
        """Claim draw by repetition or 50-move rule."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        try:
            game.action_claim_draw()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/game/<int:game_id>/claim_timeout', type='jsonrpc', auth='user')
    def claim_timeout(self, game_id):
        """Claim timeout win when opponent's time runs out."""
        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        return game.action_claim_timeout()

    @http.route('/chess/game/<int:game_id>/legal_moves', type='jsonrpc', auth='user')
    def get_legal_moves(self, game_id, square=None):
        """Get legal moves for the current position (optionally from a specific square)."""
        import chess

        game = request.env['chess.game'].browse(game_id)
        if not game.exists():
            return {'error': 'Game not found'}

        try:
            board = chess.Board(game.fen)
            legal_moves = []

            for move in board.legal_moves:
                if square is None or move.uci()[:2] == square:
                    legal_moves.append({
                        'uci': move.uci(),
                        'from': move.uci()[:2],
                        'to': move.uci()[2:4],
                        'promotion': move.uci()[4:] if len(move.uci()) > 4 else None,
                    })

            return {'legal_moves': legal_moves}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/leaderboard', type='jsonrpc', auth='user')
    def get_leaderboard(self, limit=20):
        """Get the chess leaderboard."""
        return request.env['res.users'].get_leaderboard(limit=limit)

    @http.route('/chess/my_stats', type='jsonrpc', auth='user')
    def get_my_stats(self):
        """Get current user's chess statistics."""
        return request.env.user.get_chess_stats()

    @http.route('/chess/random_fact', type='jsonrpc', auth='user')
    def get_random_fact(self):
        """Get a random Odoo fact."""
        fact = request.env['chess.odoo.fact'].get_random_fact()
        return {'fact': fact}

    @http.route('/chess/active_games', type='jsonrpc', auth='user')
    def get_active_games(self):
        """Get current user's active games."""
        games = request.env['chess.game'].get_my_active_games()
        return [{
            'id': g.id,
            'name': g.name,
            'state': g.state,
            'is_my_turn': g.is_my_turn,
            'opponent': g.black_player_id.name if g.white_player_id == request.env.user else g.white_player_id.name,
        } for g in games]

    @http.route('/chess/pending_invitations', type='jsonrpc', auth='user')
    def get_pending_invitations(self):
        """Get pending invitations for current user."""
        invitations = request.env['chess.invitation'].get_my_pending_invitations()
        return [{
            'id': inv.id,
            'inviter': inv.inviter_id.name,
            'inviter_rating': inv.inviter_id.chess_rating,
            'reward_text': inv.reward_text,
            'message': inv.message,
        } for inv in invitations]

    @http.route('/chess/invitation/<int:invitation_id>/accept', type='jsonrpc', auth='user')
    def accept_invitation(self, invitation_id):
        """Accept a chess invitation."""
        invitation = request.env['chess.invitation'].browse(invitation_id)
        if not invitation.exists():
            return {'error': 'Invitation not found'}

        try:
            result = invitation.action_accept()
            return {
                'success': True,
                'game_id': invitation.game_id.id,
            }
        except Exception as e:
            return {'error': str(e)}

    @http.route('/chess/invitation/<int:invitation_id>/decline', type='jsonrpc', auth='user')
    def decline_invitation(self, invitation_id):
        """Decline a chess invitation."""
        invitation = request.env['chess.invitation'].browse(invitation_id)
        if not invitation.exists():
            return {'error': 'Invitation not found'}

        try:
            invitation.action_decline()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}
