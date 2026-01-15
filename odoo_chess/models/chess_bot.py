# -*- coding: utf-8 -*-
import random
import chess

from odoo import api, fields, models


class ChessBot(models.Model):
    _name = 'chess.bot'
    _description = 'Chess Bot'

    name = fields.Char(string='Bot Name', required=True)
    difficulty = fields.Selection([
        ('random', 'Random Moves'),
        ('easy', 'Easy (Depth 1)'),
        ('medium', 'Medium (Depth 2)'),
        ('hard', 'Hard (Depth 3)'),
    ], default='random', string='Difficulty')
    avatar = fields.Image(string='Avatar', max_width=128, max_height=128)
    rating = fields.Integer(string='Rating', default=800)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    # Piece values for evaluation
    PIECE_VALUES = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 20000,
    }

    def get_move(self, fen):
        """Calculate bot's move based on difficulty level."""
        self.ensure_one()
        board = chess.Board(fen)

        if not list(board.legal_moves):
            return None

        if self.difficulty == 'random':
            return self._get_random_move(board)
        else:
            depth = self._get_depth()
            return self._get_minimax_move(board, depth)

    def _get_depth(self):
        """Get search depth based on difficulty."""
        return {
            'easy': 1,
            'medium': 2,
            'hard': 3,
        }.get(self.difficulty, 1)

    def _get_random_move(self, board):
        """Return a random legal move."""
        legal_moves = list(board.legal_moves)
        if legal_moves:
            return random.choice(legal_moves).uci()
        return None

    def _get_minimax_move(self, board, depth):
        """Get the best move using minimax with alpha-beta pruning."""
        best_move = None
        best_value = float('-inf')
        alpha = float('-inf')
        beta = float('inf')

        for move in board.legal_moves:
            board.push(move)
            value = -self._minimax(board, depth - 1, -beta, -alpha, not board.turn)
            board.pop()

            if value > best_value:
                best_value = value
                best_move = move

            alpha = max(alpha, value)

        return best_move.uci() if best_move else None

    def _minimax(self, board, depth, alpha, beta, maximizing):
        """Minimax algorithm with alpha-beta pruning."""
        if depth == 0 or board.is_game_over():
            return self._evaluate_board(board)

        if maximizing:
            max_eval = float('-inf')
            for move in board.legal_moves:
                board.push(move)
                eval_score = self._minimax(board, depth - 1, alpha, beta, False)
                board.pop()
                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval
        else:
            min_eval = float('inf')
            for move in board.legal_moves:
                board.push(move)
                eval_score = self._minimax(board, depth - 1, alpha, beta, True)
                board.pop()
                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval

    def _evaluate_board(self, board):
        """Evaluate the board position."""
        if board.is_checkmate():
            return float('-inf') if board.turn else float('inf')
        if board.is_stalemate() or board.is_insufficient_material():
            return 0

        score = 0

        # Material count
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                value = self.PIECE_VALUES.get(piece.piece_type, 0)
                if piece.color == chess.WHITE:
                    score += value
                else:
                    score -= value

        # Add some positional bonuses
        score += self._evaluate_position(board)

        # Return from perspective of side to move
        return score if board.turn == chess.WHITE else -score

    def _evaluate_position(self, board):
        """Add positional evaluation bonuses."""
        score = 0

        # Center control bonus
        center_squares = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center_squares:
            piece = board.piece_at(square)
            if piece:
                if piece.color == chess.WHITE:
                    score += 10
                else:
                    score -= 10

        # Development bonus (knights and bishops off back rank)
        for square in [chess.B1, chess.C1, chess.F1, chess.G1]:
            piece = board.piece_at(square)
            if piece and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                if piece.color == chess.WHITE:
                    score -= 15  # Penalty for undeveloped pieces
                else:
                    score += 15

        for square in [chess.B8, chess.C8, chess.F8, chess.G8]:
            piece = board.piece_at(square)
            if piece and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                if piece.color == chess.BLACK:
                    score += 15  # Penalty for undeveloped pieces
                else:
                    score -= 15

        return score
