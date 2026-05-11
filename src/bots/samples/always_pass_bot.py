from __future__ import annotations

from src.competition.contracts import AuctionResult, GameObservation, TwoFunctionBot


class AlwaysPassBot(TwoFunctionBot):
    @property
    def bot_name(self) -> str:
        return "AlwaysPass"

    def choose_bid(self, obs: GameObservation) -> int:
        return 0

    def choose_card(self, obs: GameObservation, result: AuctionResult) -> str:
        if obs.private.info_cards_unrevealed:
            return obs.private.info_cards_unrevealed[0].id
        return obs.private.info_cards_revealed[0].id

