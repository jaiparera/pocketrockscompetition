from __future__ import annotations
from competition.interface import *

# -----------------------------
# Bot 1: AlwaysPass
# -----------------------------

class AlwaysPassBot(PocketRocketsBot):
    @property
    def bot_name(self) -> str:
        return "AlwaysPass"

    def get_bid(self, obs: "GameObservation") -> "Bid":
        return Bid(bid_amount=0)

    def choose_info_to_reveal(self, obs: "GameObservation", result: "AuctionResult") -> str:
        # Should rarely be called; pick first if needed
        if obs.private.info_cards_unrevealed:
            return obs.private.info_cards_unrevealed[0].id
        return obs.private.info_cards_revealed[0].id

