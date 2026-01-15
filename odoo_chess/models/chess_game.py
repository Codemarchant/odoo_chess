# -*- coding: utf-8 -*-
import logging
import chess

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


class ChessGame(models.Model):
    _name = 'chess.game'
    _description = 'Chess Game'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Game Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('pending', 'Pending Acceptance'),
        ('active', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', tracking=True, string='Status')

    # Players
    white_player_id = fields.Many2one('res.users', string='White Player', required=True)
    black_player_id = fields.Many2one('res.users', string='Black Player')
    current_player_id = fields.Many2one(
        'res.users', string='Current Turn',
        compute='_compute_current_player', store=True
    )
    creator_id = fields.Many2one(
        'res.users', string='Created By',
        default=lambda self: self.env.user
    )

    # Game State
    fen = fields.Char(string='FEN Position', default=STARTING_FEN)
    pgn = fields.Text(string='PGN Notation')
    move_count = fields.Integer(string='Move Count', default=0)
    last_move_uci = fields.Char(string='Last Move (UCI)')
    last_move_san = fields.Char(string='Last Move (SAN)')
    last_activity = fields.Datetime(string='Last Activity', default=fields.Datetime.now)

    # Result
    result = fields.Selection([
        ('ongoing', 'Ongoing'),
        ('white_wins', 'White Wins'),
        ('black_wins', 'Black Wins'),
        ('draw', 'Draw'),
    ], default='ongoing', string='Result')
    result_reason = fields.Selection([
        ('checkmate', 'Checkmate'),
        ('resignation', 'Resignation'),
        ('stalemate', 'Stalemate'),
        ('draw_agreement', 'Draw by Agreement'),
        ('timeout', 'Timeout'),
        ('insufficient_material', 'Insufficient Material'),
        ('threefold_repetition', 'Threefold Repetition'),
        ('fifty_move_rule', 'Fifty Move Rule'),
    ], string='Result Reason')
    winner_id = fields.Many2one('res.users', string='Winner', compute='_compute_winner', store=True)

    # Bot Game
    is_bot_game = fields.Boolean(string='Bot Game', default=False)
    bot_id = fields.Many2one('chess.bot', string='Bot Opponent')
    bot_color = fields.Selection([
        ('white', 'White'),
        ('black', 'Black'),
    ], string='Bot Plays As')

    # Stakes/Rewards
    reward_text = fields.Text(string='Stakes/Reward')

    # Relations
    move_ids = fields.One2many('chess.move', 'game_id', string='Moves')
    invitation_id = fields.Many2one('chess.invitation', string='Invitation')

    # Draw Handling
    draw_offered_by = fields.Many2one('res.users', string='Draw Offered By')

    # Computed Fields
    is_my_turn = fields.Boolean(compute='_compute_is_my_turn')
    my_color = fields.Selection([
        ('white', 'White'),
        ('black', 'Black'),
        ('spectator', 'Spectator'),
    ], compute='_compute_my_color')
    is_check = fields.Boolean(compute='_compute_board_status')
    is_checkmate = fields.Boolean(compute='_compute_board_status')
    is_stalemate = fields.Boolean(compute='_compute_board_status')
    can_claim_draw = fields.Boolean(compute='_compute_board_status')

    @api.depends('white_player_id', 'black_player_id', 'create_date')
    def _compute_name(self):
        for game in self:
            white_name = game.white_player_id.name or 'White'
            black_name = game.black_player_id.name or 'Black' if game.black_player_id else 'TBD'
            date_str = game.create_date.strftime('%Y-%m-%d') if game.create_date else ''
            game.name = f"{white_name} vs {black_name} ({date_str})"

    @api.depends('fen')
    def _compute_current_player(self):
        for game in self:
            if game.fen and game.state == 'active':
                # FEN has turn indicator as second component: 'w' or 'b'
                parts = game.fen.split(' ')
                if len(parts) >= 2:
                    turn = parts[1]
                    game.current_player_id = game.white_player_id if turn == 'w' else game.black_player_id
                else:
                    game.current_player_id = game.white_player_id
            else:
                game.current_player_id = False

    @api.depends('result', 'white_player_id', 'black_player_id')
    def _compute_winner(self):
        for game in self:
            if game.result == 'white_wins':
                game.winner_id = game.white_player_id
            elif game.result == 'black_wins':
                game.winner_id = game.black_player_id
            else:
                game.winner_id = False

    def _compute_is_my_turn(self):
        for game in self:
            if game.is_bot_game and game.bot_color:
                # For bot games, check if it's NOT the bot's turn
                game.is_my_turn = not game._is_bot_turn() and game.state == 'active'
            else:
                game.is_my_turn = game.current_player_id == self.env.user

    def _compute_my_color(self):
        for game in self:
            # For bot games, determine color based on bot_color (user plays opposite)
            if game.is_bot_game and game.bot_color:
                if game.bot_color == 'white':
                    game.my_color = 'black'
                else:
                    game.my_color = 'white'
            elif game.white_player_id == self.env.user:
                game.my_color = 'white'
            elif game.black_player_id == self.env.user:
                game.my_color = 'black'
            else:
                game.my_color = 'spectator'

    @api.depends('fen')
    def _compute_board_status(self):
        for game in self:
            if game.fen:
                try:
                    board = chess.Board(game.fen)
                    game.is_check = board.is_check()
                    game.is_checkmate = board.is_checkmate()
                    game.is_stalemate = board.is_stalemate()
                    game.can_claim_draw = board.can_claim_draw()
                except Exception:
                    game.is_check = False
                    game.is_checkmate = False
                    game.is_stalemate = False
                    game.can_claim_draw = False
            else:
                game.is_check = False
                game.is_checkmate = False
                game.is_stalemate = False
                game.can_claim_draw = False

    def _get_board_from_moves(self):
        """Reconstruct board from move history for accurate draw detection."""
        self.ensure_one()
        board = chess.Board()
        for move in self.move_ids.sorted('sequence'):
            try:
                board.push_uci(move.uci)
            except Exception:
                pass
        return board

    def action_make_move(self, uci_move):
        """
        Server-side move validation and execution.
        Returns dict with success/error status and updated game state.
        """
        self.ensure_one()

        # Check game state
        if self.state != 'active':
            return {'error': _('Game is not active')}

        # Check if it's this player's turn
        if self.env.user != self.current_player_id:
            # Allow bot to move if it's a bot game and it's bot's turn
            if not (self.is_bot_game and self._is_bot_turn()):
                return {'error': _('Not your turn')}

        # Validate move with python-chess
        try:
            board = chess.Board(self.fen)
            move = chess.Move.from_uci(uci_move)

            if move not in board.legal_moves:
                return {'error': _('Illegal move')}

            # Determine if this is a bot move (for bot games)
            is_bot_move = False
            if self.is_bot_game and self.bot_color:
                current_turn = 'white' if board.turn == chess.WHITE else 'black'
                is_bot_move = (current_turn == self.bot_color)

            # Get SAN notation before pushing
            san = board.san(move)

            # Apply move
            board.push(move)

            # Update game state
            self.write({
                'fen': board.fen(),
                'move_count': self.move_count + 1,
                'last_move_uci': uci_move,
                'last_move_san': san,
                'last_activity': fields.Datetime.now(),
                'draw_offered_by': False,  # Clear any pending draw offer
            })

            # Record move in history
            self.env['chess.move'].create({
                'game_id': self.id,
                'sequence': self.move_count,
                'player_id': self.env.user.id,
                'uci': uci_move,
                'san': san,
                'fen_after': board.fen(),
            })

            # Check for game over conditions
            game_over_result = self._check_game_over(board)
            if game_over_result:
                self._end_game(game_over_result['result'], game_over_result['reason'])

            # Broadcast move via bus
            self._broadcast_move(uci_move, san, board.fen(), is_bot_move)

            # If bot game and now bot's turn, schedule bot move
            if self.is_bot_game and self._is_bot_turn() and self.state == 'active':
                self._schedule_bot_move()

            # Return current state (self.fen may have been updated by bot move)
            return {
                'success': True,
                'fen': self.fen,  # Use self.fen to include any bot moves
                'san': san,
                'uci': uci_move,
                'move_count': self.move_count,
                'game_over': self.state == 'completed',
                'result': self.result if self.state == 'completed' else None,
                'is_bot_game': self.is_bot_game,
                'is_my_turn': self.is_my_turn,
            }

        except ValueError as e:
            return {'error': _('Invalid move format: %s') % str(e)}
        except Exception as e:
            _logger.exception("Error processing move: %s", e)
            return {'error': _('Error processing move')}

    def _check_game_over(self, board):
        """Check for checkmate, stalemate, and draw conditions."""
        if board.is_checkmate():
            # The player who just moved wins
            if board.turn == chess.WHITE:
                return {'result': 'black_wins', 'reason': 'checkmate'}
            else:
                return {'result': 'white_wins', 'reason': 'checkmate'}

        if board.is_stalemate():
            return {'result': 'draw', 'reason': 'stalemate'}

        if board.is_insufficient_material():
            return {'result': 'draw', 'reason': 'insufficient_material'}

        # Check using full move history for repetition/50-move rule
        full_board = self._get_board_from_moves()
        if full_board.is_fivefold_repetition():
            return {'result': 'draw', 'reason': 'threefold_repetition'}

        if full_board.is_seventyfive_moves():
            return {'result': 'draw', 'reason': 'fifty_move_rule'}

        return None

    def _end_game(self, result, reason):
        """End the game and update ratings."""
        self.write({
            'state': 'completed',
            'result': result,
            'result_reason': reason,
        })
        self._update_elo_ratings()
        self._broadcast_game_end()

    def _update_elo_ratings(self):
        """Calculate and apply Elo rating changes."""
        if self.is_bot_game or not self.white_player_id or not self.black_player_id:
            return

        K = 32  # K-factor

        white_rating = self.white_player_id.chess_rating
        black_rating = self.black_player_id.chess_rating

        # Expected scores
        exp_white = 1 / (1 + 10 ** ((black_rating - white_rating) / 400))
        exp_black = 1 - exp_white

        # Actual scores
        if self.result == 'white_wins':
            score_white, score_black = 1, 0
            white_wins, white_losses = 1, 0
            black_wins, black_losses = 0, 1
            draws = 0
        elif self.result == 'black_wins':
            score_white, score_black = 0, 1
            white_wins, white_losses = 0, 1
            black_wins, black_losses = 1, 0
            draws = 0
        else:  # draw
            score_white, score_black = 0.5, 0.5
            white_wins, white_losses = 0, 0
            black_wins, black_losses = 0, 0
            draws = 1

        # New ratings
        new_white = round(white_rating + K * (score_white - exp_white))
        new_black = round(black_rating + K * (score_black - exp_black))

        # Update white player
        self.white_player_id.sudo().write({
            'chess_rating': new_white,
            'chess_wins': self.white_player_id.chess_wins + white_wins,
            'chess_losses': self.white_player_id.chess_losses + white_losses,
            'chess_draws': self.white_player_id.chess_draws + draws,
        })

        # Update black player
        self.black_player_id.sudo().write({
            'chess_rating': new_black,
            'chess_wins': self.black_player_id.chess_wins + black_wins,
            'chess_losses': self.black_player_id.chess_losses + black_losses,
            'chess_draws': self.black_player_id.chess_draws + draws,
        })

        _logger.info(
            "Elo updated: %s (%d -> %d), %s (%d -> %d)",
            self.white_player_id.name, white_rating, new_white,
            self.black_player_id.name, black_rating, new_black
        )

    def action_resign(self):
        """Current player resigns."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Cannot resign - game is not active'))

        if self.env.user not in (self.white_player_id, self.black_player_id):
            raise UserError(_('You are not a player in this game'))

        if self.env.user == self.white_player_id:
            result = 'black_wins'
        else:
            result = 'white_wins'

        self._end_game(result, 'resignation')
        return True

    def action_offer_draw(self):
        """Current player offers a draw."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Cannot offer draw - game is not active'))

        if self.env.user not in (self.white_player_id, self.black_player_id):
            raise UserError(_('You are not a player in this game'))

        if self.draw_offered_by:
            raise UserError(_('A draw offer is already pending'))

        self.draw_offered_by = self.env.user
        self._broadcast_draw_offer()
        return True

    def action_accept_draw(self):
        """Accept a pending draw offer."""
        self.ensure_one()
        if not self.draw_offered_by:
            raise UserError(_('No draw offer to accept'))

        if self.draw_offered_by == self.env.user:
            raise UserError(_('You cannot accept your own draw offer'))

        self._end_game('draw', 'draw_agreement')
        return True

    def action_decline_draw(self):
        """Decline a pending draw offer."""
        self.ensure_one()
        if not self.draw_offered_by:
            raise UserError(_('No draw offer to decline'))

        self.draw_offered_by = False
        self._broadcast_draw_declined()
        return True

    def action_claim_draw(self):
        """Claim draw by threefold repetition or 50-move rule."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Cannot claim draw - game is not active'))

        board = self._get_board_from_moves()
        if board.can_claim_threefold_repetition():
            self._end_game('draw', 'threefold_repetition')
        elif board.can_claim_fifty_moves():
            self._end_game('draw', 'fifty_move_rule')
        else:
            raise UserError(_('Draw cannot be claimed in current position'))
        return True

    def _is_bot_turn(self):
        """Check if it's the bot's turn based on FEN position."""
        if not self.is_bot_game or not self.bot_id or not self.bot_color:
            return False
        # Check the FEN turn indicator ('w' or 'b') directly
        if self.fen:
            parts = self.fen.split(' ')
            if len(parts) >= 2:
                fen_turn = parts[1]  # 'w' = white's turn, 'b' = black's turn
                if self.bot_color == 'white' and fen_turn == 'w':
                    return True
                if self.bot_color == 'black' and fen_turn == 'b':
                    return True
        return False

    def _schedule_bot_move(self):
        """Make the bot move (called after player moves in bot game)."""
        self.ensure_one()
        if not self.is_bot_game or not self.bot_id:
            return

        bot_uci = self.bot_id.get_move(self.fen)
        if bot_uci:
            # Use sudo to make the bot move
            self.sudo().action_make_move(bot_uci)

    def _get_bus_channel(self):
        """Get the bus channel name for this game."""
        return f'chess_game_{self.id}'

    def _broadcast_move(self, uci, san, fen, is_bot_move=False):
        """Broadcast move to all participants via bus.

        Args:
            uci: UCI notation of the move
            san: SAN notation of the move
            fen: FEN position after the move
            is_bot_move: True if this move was made by the bot
        """
        channel = f'chess_game_{self.id}'
        message = {
            'type': 'move',
            'game_id': self.id,
            'uci': uci,
            'san': san,
            'fen': fen,
            'move_count': self.move_count,
            'is_bot_move': is_bot_move,
            'is_check': self.is_check,
        }
        self.env['bus.bus']._sendone(channel, 'chess_move', message)

    def _broadcast_game_end(self):
        """Broadcast game end to all participants."""
        channel = f'chess_game_{self.id}'
        message = {
            'type': 'game_end',
            'game_id': self.id,
            'result': self.result,
            'result_reason': self.result_reason,
            'winner_id': self.winner_id.id if self.winner_id else None,
        }
        self.env['bus.bus']._sendone(channel, 'chess_game_end', message)

    def _broadcast_draw_offer(self):
        """Broadcast draw offer."""
        channel = f'chess_game_{self.id}'
        message = {
            'type': 'draw_offer',
            'game_id': self.id,
            'offered_by': self.draw_offered_by.id,
            'offered_by_name': self.draw_offered_by.name,
        }
        self.env['bus.bus']._sendone(channel, 'chess_draw_offer', message)

    def _broadcast_draw_declined(self):
        """Broadcast draw declined."""
        channel = f'chess_game_{self.id}'
        message = {
            'type': 'draw_declined',
            'game_id': self.id,
        }
        self.env['bus.bus']._sendone(channel, 'chess_draw_declined', message)

    def get_game_state(self):
        """Return full game state for client initialization."""
        self.ensure_one()
        moves = [{
            'sequence': m.sequence,
            'uci': m.uci,
            'san': m.san,
            'player_id': m.player_id.id,
        } for m in self.move_ids.sorted('sequence')]

        return {
            'id': self.id,
            'state': self.state,
            'fen': self.fen,
            'moves': moves,
            'move_count': self.move_count,
            'white_player': {
                'id': self.white_player_id.id,
                'name': self.white_player_id.name,
                'rating': self.white_player_id.chess_rating,
            },
            'black_player': {
                'id': self.black_player_id.id,
                'name': self.black_player_id.name,
                'rating': self.black_player_id.chess_rating,
            } if self.black_player_id else None,
            'current_player_id': self.current_player_id.id if self.current_player_id else None,
            'is_my_turn': self.is_my_turn,
            'my_color': self.my_color,
            'result': self.result,
            'result_reason': self.result_reason,
            'reward_text': self.reward_text,
            'draw_offered_by': self.draw_offered_by.id if self.draw_offered_by else None,
            'is_check': self.is_check,
            'is_bot_game': self.is_bot_game,
        }

    @api.model
    def get_my_active_games(self):
        """Get all active games for current user."""
        return self.search([
            ('state', 'in', ['pending', 'active']),
            '|',
            ('white_player_id', '=', self.env.user.id),
            ('black_player_id', '=', self.env.user.id),
        ])
