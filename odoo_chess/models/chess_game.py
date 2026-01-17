# -*- coding: utf-8 -*-
import logging

import chess

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .chess_bot import get_bot_selection, get_bot_move, get_bot_info

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
    bot_key = fields.Selection(selection=get_bot_selection, string='Bot Opponent')
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

    # Time Control Configuration
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

    # Time Tracking (stored in milliseconds for precision)
    white_time_remaining = fields.Integer(
        string='White Time Remaining (ms)',
        default=0,
        help='White player remaining time in milliseconds'
    )
    black_time_remaining = fields.Integer(
        string='Black Time Remaining (ms)',
        default=0,
        help='Black player remaining time in milliseconds'
    )
    clock_started_at = fields.Datetime(
        string='Clock Started At',
        help='When the current player clock started running'
    )

    # Time Display Fields (computed)
    time_control_display = fields.Char(
        string='Time Control',
        compute='_compute_time_control_display'
    )
    white_time_display = fields.Char(
        string='White Time',
        compute='_compute_time_display'
    )
    black_time_display = fields.Char(
        string='Black Time',
        compute='_compute_time_display'
    )

    # Network grace period in milliseconds
    NETWORK_GRACE_MS = 500

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

    @api.depends('is_timed', 'base_time', 'increment')
    def _compute_time_control_display(self):
        for game in self:
            if not game.is_timed:
                game.time_control_display = 'Untimed'
            else:
                minutes = game.base_time // 60
                if game.increment:
                    game.time_control_display = f'{minutes}+{game.increment}'
                else:
                    game.time_control_display = f'{minutes} min'

    @api.depends('white_time_remaining', 'black_time_remaining')
    def _compute_time_display(self):
        for game in self:
            game.white_time_display = game._format_time_ms(game.white_time_remaining)
            game.black_time_display = game._format_time_ms(game.black_time_remaining)

    def _format_time_ms(self, milliseconds):
        """Format milliseconds as MM:SS or H:MM:SS."""
        if milliseconds <= 0:
            return '0:00'

        total_seconds = milliseconds // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f'{hours}:{minutes:02d}:{seconds:02d}'
        else:
            return f'{minutes}:{seconds:02d}'

    def _get_current_turn_color(self):
        """Get the current turn color from FEN."""
        self.ensure_one()
        if self.fen:
            parts = self.fen.split(' ')
            if len(parts) >= 2:
                return 'white' if parts[1] == 'w' else 'black'
        return 'white'

    def _start_clock(self):
        """Start the clock for the current player."""
        self.ensure_one()
        if not self.is_timed or self.state != 'active':
            return

        self.clock_started_at = fields.Datetime.now()

    def _stop_clock_and_calculate_time(self, player_color):
        """
        Stop the specified player's clock and deduct elapsed time.
        Returns elapsed time in milliseconds.
        """
        self.ensure_one()
        if not self.is_timed or not self.clock_started_at:
            return 0

        # Calculate elapsed time
        now = fields.Datetime.now()
        elapsed = now - self.clock_started_at
        elapsed_ms = int(elapsed.total_seconds() * 1000)

        # Apply grace period (only for network latency, not display)
        elapsed_ms_with_grace = max(0, elapsed_ms - self.NETWORK_GRACE_MS)

        # Deduct time from the player who just moved
        if player_color == 'white':
            new_time = self.white_time_remaining - elapsed_ms_with_grace
            self.white_time_remaining = max(0, new_time)
        else:
            new_time = self.black_time_remaining - elapsed_ms_with_grace
            self.black_time_remaining = max(0, new_time)

        # Clear clock started timestamp
        self.clock_started_at = False

        return elapsed_ms_with_grace

    def _apply_increment(self, player_color):
        """Apply time increment to the player who just moved."""
        self.ensure_one()
        if not self.is_timed or self.increment <= 0:
            return

        increment_ms = self.increment * 1000

        if player_color == 'white':
            self.white_time_remaining += increment_ms
        else:
            self.black_time_remaining += increment_ms

    def _check_timeout(self):
        """
        Check if the current player has timed out.
        Returns dict with result info if timeout, None otherwise.
        """
        self.ensure_one()
        if not self.is_timed or self.state != 'active':
            return None

        # If clock hasn't started yet (first move), no timeout possible
        if not self.clock_started_at:
            return None

        # Calculate current time accounting for running clock
        now = fields.Datetime.now()
        elapsed = now - self.clock_started_at
        elapsed_ms = int(elapsed.total_seconds() * 1000)

        current_turn = self._get_current_turn_color()

        if current_turn == 'white':
            current_time = self.white_time_remaining - elapsed_ms
            if current_time <= 0:
                return {'result': 'black_wins', 'reason': 'timeout'}
        else:
            current_time = self.black_time_remaining - elapsed_ms
            if current_time <= 0:
                return {'result': 'white_wins', 'reason': 'timeout'}

        return None

    def _get_current_times_with_running_clock(self):
        """
        Get current times accounting for the running clock.
        Used for sending accurate time data to clients.
        """
        self.ensure_one()
        white_time = self.white_time_remaining
        black_time = self.black_time_remaining
        active_clock = 'none'

        if self.is_timed and self.clock_started_at and self.state == 'active':
            now = fields.Datetime.now()
            elapsed = now - self.clock_started_at
            elapsed_ms = int(elapsed.total_seconds() * 1000)

            current_turn = self._get_current_turn_color()
            active_clock = current_turn

            # Deduct from active player's clock for display
            if current_turn == 'white':
                white_time = max(0, white_time - elapsed_ms)
            else:
                black_time = max(0, black_time - elapsed_ms)

        return {
            'white_time': white_time,
            'black_time': black_time,
            'active_clock': active_clock,
            'server_time': fields.Datetime.now().isoformat(),
        }

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
        Server-side move validation and execution with time control support.
        Returns dict with success/error status and updated game state.
        """
        self.ensure_one()

        # Check game state
        if self.state != 'active':
            return {'error': _('Game is not active')}

        # Check for timeout before processing move (for timed games)
        if self.is_timed:
            timeout_result = self._check_timeout()
            if timeout_result:
                self._end_game(timeout_result['result'], timeout_result['reason'])
                return {
                    'error': _('Time has run out'),
                    'game_over': True,
                    'result': timeout_result['result'],
                }

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

            # Determine current player color (before move is made)
            player_color = 'white' if board.turn == chess.WHITE else 'black'

            # Determine if this is a bot move (for bot games)
            is_bot_move = False
            if self.is_bot_game and self.bot_color:
                is_bot_move = (player_color == self.bot_color)

            # Time control: Stop clock and deduct time for the player who just moved
            time_spent_ms = 0
            if self.is_timed and self.clock_started_at:
                time_spent_ms = self._stop_clock_and_calculate_time(player_color)
                # Apply increment after successful move
                self._apply_increment(player_color)

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

            # Record move in history with time data
            move_vals = {
                'game_id': self.id,
                'sequence': self.move_count,
                'uci': uci_move,
                'san': san,
                'fen_after': board.fen(),
                'time_spent_ms': time_spent_ms,
                'white_time_after': self.white_time_remaining,
                'black_time_after': self.black_time_remaining,
            }
            if is_bot_move:
                move_vals['is_bot_move'] = True
                move_vals['bot_key'] = self.bot_key
            else:
                move_vals['player_id'] = self.env.user.id
            self.env['chess.move'].create(move_vals)

            # Check for game over conditions
            game_over_result = self._check_game_over(board)
            if game_over_result:
                self._end_game(game_over_result['result'], game_over_result['reason'])
            else:
                # Start clock for next player (if timed game and game not over)
                if self.is_timed:
                    self._start_clock()

            # Get time info for broadcast
            time_info = self._get_current_times_with_running_clock() if self.is_timed else None

            # Broadcast move via bus (with time info)
            self._broadcast_move(uci_move, san, board.fen(), is_bot_move, time_info)

            # If bot game and now bot's turn, schedule bot move
            if self.is_bot_game and self._is_bot_turn() and self.state == 'active':
                self._schedule_bot_move()

            # Build response
            response = {
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

            # Include time info in response for timed games
            if self.is_timed:
                current_times = self._get_current_times_with_running_clock()
                response.update({
                    'white_time': current_times['white_time'],
                    'black_time': current_times['black_time'],
                    'active_clock': current_times['active_clock'],
                })

            return response

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
        if not self.is_bot_game or not self.bot_color:
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
        if not self.is_bot_game or not self.bot_key:
            return

        bot_uci = get_bot_move(self.bot_key, self.fen)
        if bot_uci:
            # Use sudo to make the bot move
            self.sudo().action_make_move(bot_uci)

    def _broadcast_move(self, uci, san, fen, is_bot_move=False, time_info=None):
        """Broadcast move to all participants via bus.

        Args:
            uci: UCI notation of the move
            san: SAN notation of the move
            fen: FEN position after the move
            is_bot_move: True if this move was made by the bot
            time_info: Optional dict with time control data
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

        # Add time control info if timed game
        if self.is_timed and time_info:
            message.update({
                'white_time': time_info['white_time'],
                'black_time': time_info['black_time'],
                'active_clock': time_info['active_clock'],
                'server_time': time_info['server_time'],
            })

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

        state = {
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
            # Time control fields
            'is_timed': self.is_timed,
            'time_control_display': self.time_control_display,
        }

        # Add bot info for bot games
        if self.is_bot_game and self.bot_key:
            bot_info = get_bot_info(self.bot_key)
            if bot_info:
                state['bot_name'] = bot_info.get('name', 'Bot')
                state['bot_color'] = self.bot_color

        # Add detailed time info for timed games
        if self.is_timed:
            time_info = self._get_current_times_with_running_clock()
            state.update({
                'base_time': self.base_time,
                'increment': self.increment,
                'white_time': time_info['white_time'],
                'black_time': time_info['black_time'],
                'active_clock': time_info['active_clock'],
                'server_time': time_info['server_time'],
            })

        return state

    @api.model
    def get_my_active_games(self):
        """Get all active games for current user."""
        return self.search([
            ('state', 'in', ['pending', 'active']),
            '|',
            ('white_player_id', '=', self.env.user.id),
            ('black_player_id', '=', self.env.user.id),
        ])

    def action_claim_timeout(self):
        """
        Claim a timeout win. Called by client when opponent's time runs out.
        Server validates the timeout before ending the game.
        Returns dict with success status and game result.
        """
        self.ensure_one()

        if self.state != 'active':
            return {'error': _('Game is not active')}

        if not self.is_timed:
            return {'error': _('This is not a timed game')}

        # Verify the caller is a player in this game
        if self.env.user not in (self.white_player_id, self.black_player_id):
            # For bot games, the user plays both sides
            if not self.is_bot_game:
                return {'error': _('You are not a player in this game')}

        # Check for actual timeout (server is authoritative)
        timeout_result = self._check_timeout()
        if not timeout_result:
            return {'error': _('No timeout has occurred')}

        # End the game
        _logger.info(
            "Game %s timeout claimed: %s by %s",
            self.id, timeout_result['result'], timeout_result['reason']
        )
        self._end_game(timeout_result['result'], timeout_result['reason'])

        return {
            'success': True,
            'result': timeout_result['result'],
            'reason': timeout_result['reason'],
        }
