# -*- coding: utf-8 -*-
{
    'name': 'Odoo Chess',
    'version': '17.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Play chess against colleagues or AI bots with Elo ratings, time controls, and leaderboards',
    'description': """
Odoo Chess - Multiplayer Chess Game
===================================

A fully integrated multiplayer chess game that runs entirely inside Odoo. Challenge colleagues, play against AI bots, and compete on the leaderboard!

Features
--------
* **Real-Time Multiplayer**: Challenge any Odoo user with instant move synchronization via Odoo's longpolling bus
* **AI Bot Opponents**: Practice against 4 difficulty levels - Beginner Bob (800), Casual Carl (1200), Serious Sam (1500), Randy Ram (1800)
* **Time Controls**: Bullet, Blitz, Rapid, Classical presets plus custom time with increment support
* **Elo Rating System**: Track skill with K-factor 32 ratings starting at 1200
* **Leaderboard**: Kanban view of top players with win/loss/draw statistics
* **Game Controls**: Resign, offer/accept/decline draws, claim draws by repetition or fifty-move rule, timeout claims
* **Invitation System**: Send challenges with optional stakes, real-time notifications, auto-created chat channels
* **Sound Effects**: Audio feedback for moves, captures, castling, check, and game results
* **Responsive Design**: Play on desktop or mobile with adaptive board sizing
* **Odoo Fun Facts**: Learn about Odoo while waiting for opponent's move

Technical Details
-----------------
* Server-side move validation with python-chess library
* OWL components with chessboard.js integration
* Chess Player and Chess Manager security groups
* Mail thread integration for game comments
* FEN/PGN notation tracking for complete game history

Requirements
------------
* python-chess library: pip install chess
    """,
    'author': 'Codemarchant',
    'website': 'https://github.com/Codemarchant/odoo_chess',
    'license': 'LGPL-3',
    'support': 'support@codemarchant.com',
    'depends': [
        'base',
        'web',
        'mail',
        'bus',
    ],
    'external_dependencies': {
        'python': ['chess'],
    },
    'data': [
        'security/chess_security.xml',
        'security/ir.model.access.csv',
        'data/chess_odoo_facts_data.xml',
        'wizard/chess_create_game_views.xml',
        'views/chess_game_views.xml',
        'views/chess_invitation_views.xml',
        'views/chess_leaderboard_views.xml',
        'views/res_users_views.xml',
        'views/chess_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo_chess/static/lib/chessboardjs/css/chessboard-1.0.0.min.css',
            'odoo_chess/static/lib/chessboardjs/js/chessboard-1.0.0.min.js',
            'odoo_chess/static/lib/chessjs/chess.min.js',
            'odoo_chess/static/src/components/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
