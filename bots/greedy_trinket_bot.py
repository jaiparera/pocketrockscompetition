from competition.interface import *
from bots.helpers import _current_item, _best_trinket_bonus_if_win, _bundle_value, _affordable

# -----------------------------
# Bot 3: GreedyTrinket
# - Values only gems + immediate trinket points.
# - Ignores loans/investments except as "usually bad".
# -----------------------------

class GreedyTrinketBot(PocketRocketsBot):
    @property
    def bot_name(self) -> str:
        return "GreedyTrinket"

    def get_bid(self, obs: "GameObservation") -> "Bid":
        kind = obs.context.action.kind
        max_bid = legal_max_bid(obs)

        # Avoid debt/locking by default
        if kind in (ActionType.LOAN_10, ActionType.LOAN_20, ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
            return Bid(0)

        cards, _ = _current_item(obs)
        if not cards:
            return Bid(0)

        # Simple value = expected gem values + potential trinkets
        v = _bundle_value(obs, cards) + _best_trinket_bonus_if_win(obs, cards)

        # Bid up to ~70% of value, capped
        bid = int(max(0, round(0.7 * v)))
        return Bid(_affordable(bid, obs))

    def choose_info_to_reveal(self, obs: "GameObservation", result: "AuctionResult") -> str:
        """
        Hide strength: reveal a suit that seems "average/low" given our private info.
        Heuristic: reveal the suit with the *lowest* private count (to keep strong suits hidden).
        """
        unrevealed = list(obs.private.info_cards_unrevealed)
        if not unrevealed:
            return obs.private.info_cards_revealed[0].id

        # Count our private info by suit and reveal the least frequent
        counts: Dict[Suit, int] = {s: 0 for s in Suit}
        for c in unrevealed:
            counts[c.suit] += 1
        best = min(unrevealed, key=lambda c: (counts[c.suit], c.id))
        return best.id
