from competition.interface import *
import random
from time import time

# -----------------------------
# Bot 2: RandomBid
# -----------------------------

class RandomBidBot(PocketRocketsBot):
    def __init__(self):
        self._rng = random.Random(int(time()*10000)%10000)

    @property
    def bot_name(self) -> str:
        return "RandomBid"

    def get_bid(self, obs: "GameObservation") -> "Bid":
        max_bid = legal_max_bid(obs)
        if max_bid <= 0:
            return Bid(0)
        # Random small-ish bids; passes sometimes
        if self._rng.random() < 0.35:
            return Bid(0)
        return Bid(self._rng.randint(0, max(0, min(5, max_bid))))

    def choose_info_to_reveal(self, obs: "GameObservation", result: "AuctionResult") -> str:
        # Reveal random unrevealed
        if not obs.private.info_cards_unrevealed:
            return obs.private.info_cards_revealed[0].id
        c = self._rng.choice(list(obs.private.info_cards_unrevealed))
        return c.id