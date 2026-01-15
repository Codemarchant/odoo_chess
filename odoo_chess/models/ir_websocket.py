# -*- coding: utf-8 -*-
import re

from odoo import models
from odoo.exceptions import AccessError


class IrWebsocket(models.AbstractModel):
    _inherit = 'ir.websocket'

    def _build_bus_channel_list(self, channels):
        """
        Extend bus channel list to handle chess game channels.
        Validates that users can only subscribe to games they're playing in.
        """
        channels = super()._build_bus_channel_list(channels)

        if self.env.uid:
            # Process chess game channels
            channels_to_add = []
            for channel in list(channels):
                if isinstance(channel, str):
                    # Match chess_game_{id} pattern
                    match = re.match(r'^chess_game_(\d+)$', channel)
                    if match:
                        game_id = int(match.group(1))
                        try:
                            # Verify user has access to this game
                            game = self.env['chess.game'].browse(game_id)
                            if game.exists():
                                # Check if user is a player in this game
                                user = self.env.user
                                if user in (game.white_player_id, game.black_player_id):
                                    channels_to_add.append(channel)
                                else:
                                    # Remove channel if user is not a player
                                    channels.remove(channel)
                            else:
                                channels.remove(channel)
                        except AccessError:
                            channels.remove(channel)

        return channels
