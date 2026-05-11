from __future__ import annotations

import random

from src.competition.contracts import AuctionResult, GameObservation, TwoFunctionBot, legal_max_bid


class RandomBidBot(TwoFunctionBot):
    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    @property
    def bot_name(self) -> str:
        return "RandomBid"

    def choose_bid(self, obs: GameObservation) -> int:
        max_bid = legal_max_bid(obs)
        if max_bid <= 0 or self._rng.random() < 0.35:
            return 0
        return self._rng.randint(0, min(5, max_bid))

    def choose_card(self, obs: GameObservation, result: AuctionResult) -> str:
        if not obs.private.info_cards_unrevealed:
            return obs.private.info_cards_revealed[0].id
        return self._rng.choice(list(obs.private.info_cards_unrevealed)).id

