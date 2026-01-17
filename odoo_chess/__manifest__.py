# -*- coding: utf-8 -*-
{
    'name': 'Odoo Chess',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Multiplayer chess game for Odoo users',
    'description': """
Odoo Chess - Multiplayer Chess Game
===================================

A fully integrated multiplayer chess game that runs entirely inside Odoo.

Features:
---------
* Create chess games and invite other Odoo users
* Real-time gameplay using Odoo's longpolling bus
* Server-side move validation with python-chess
* Elo rating system for all players
* Leaderboard showing top players
* Play against bots (various difficulty levels)
* Customizable stakes/rewards for games
* Game persistence - resume disconnected games
* Resign and draw offer controls

Requirements:
-------------
* python-chess library (pip install python-chess)
    """,
    'author': 'Codemarchant',
    'website': 'https://codemarchant.com',
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
            # Ensure jQuery is loaded before chessboard.js (which depends on window.jQuery)
            ('include', 'web._assets_jquery'),
            'odoo_chess/static/lib/chessboardjs/css/chessboard-1.0.0.min.css',
            'odoo_chess/static/lib/chessboardjs/js/chessboard-1.0.0.min.js',
            'odoo_chess/static/lib/chessjs/chess.min.js',
            'odoo_chess/static/src/components/**/*',
            'odoo_chess/static/src/sounds/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
