# -*- coding: utf-8 -*-
"""
Hardcoded chess bots using the Sunfish engine.
"""

from .sunfish_engine import get_best_move

# Hardcoded bot definitions
# Each bot has: name, description, rating (estimated), depth, max_time
CHESS_BOTS = {
    'beginner_bob': {
        'name': 'Beginner Bob',
        'description': 'A gentle opponent for learning the basics.',
        'rating': 800,
        'depth': 2,
        'time': 0.5,
    },
    'casual_carl': {
        'name': 'Casual Carl',
        'description': 'A moderate challenge with decent tactical awareness.',
        'rating': 1200,
        'depth': 4,
        'time': 1.0,
    },
    'serious_sam': {
        'name': 'Serious Sam',
        'description': 'A strong opponent who punishes mistakes.',
        'rating': 1500,
        'depth': 6,
        'time': 2.0,
    },
    'randy_ram': {
        'name': 'Randy Ram',
        'description': 'The ultimate challenge. Randy shows no mercy.',
        'rating': 1800,
        'depth': 8,
        'time': 3.0,
    },
}


def get_bot_selection(self):
    """Return bot selection list for Selection field."""
    return [(key, bot['name']) for key, bot in CHESS_BOTS.items()]


def get_bot_move(bot_key, fen):
    """
    Get the best move for the given bot and position.

    Args:
        bot_key: The bot identifier (e.g., 'beginner_bob')
        fen: FEN string of the current position

    Returns:
        UCI move string (e.g., 'e2e4') or None if no legal moves
    """
    bot = CHESS_BOTS.get(bot_key)
    if not bot:
        return None

    return get_best_move(fen, max_depth=bot['depth'], max_time=bot['time'])


def get_bot_info(bot_key):
    """Get bot information dictionary."""
    return CHESS_BOTS.get(bot_key)
