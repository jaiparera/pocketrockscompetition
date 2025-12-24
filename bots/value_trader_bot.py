from competition.interface import *
from bots.helpers import _current_item, legal_max_bid, _affordable, _bundle_value, _best_trinket_bonus_if_win
import math
# -----------------------------
# Bot 4: ValueTrader
# - Bids based on expected gem value (from partial info),
#   plus trinket bonus, plus rational handling of loans/investments.
# - Loans are treated as "net cost = bid" now and "repay principal later":
#   so only take loans if bid is low and you need liquidity (or late game).
# - Investments are treated as "profit = payout - 0" + return of locked:
#   so net gain at end is payout; bid should be <= discounted payout.
# -----------------------------

class ValueTraderBot(PocketRocketsBot):
    def __init__(self, risk: float = 0.9):
        """
        risk in (0,1.2] roughly: higher bids more aggressively relative to estimated value.
        """
        self.risk = float(risk)

    @property
    def bot_name(self) -> str:
        return f"ValueTrader(r={self.risk:.2f})"

    def get_bid(self, obs: "GameObservation") -> "Bid":
        kind = obs.context.action.kind
        max_bid = legal_max_bid(obs)

        # Estimate game stage for small behavior tweaks
        # (upcoming not counted in pile count, so total remaining gems is upcoming + pile)
        remaining_gems = len(obs.context.upcoming_gems) + obs.context.biddable_pile_count
        late = remaining_gems <= 6

        if kind in (ActionType.AUCTION_1, ActionType.AUCTION_2):
            cards, _ = _current_item(obs)
            if not cards:
                return Bid(0)

            v = _bundle_value(obs, cards)
            v += _best_trinket_bonus_if_win(obs, cards)

            # Small premium late game (values are more known + fewer turns to recover)
            mult = self.risk * (1.05 if late else 1.0)

            bid = int(round(mult * v))
            return Bid(_affordable(bid, obs))

        if kind in (ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
            payout = 5 if kind == ActionType.INVESTMENT_5 else 10

            # Investment net gain at end is payout (locked returns), so bid should be <= payout,
            # but we discount early game because locking cash can lose gem opportunities.
            discount = 0.9 if late else 0.65
            bid = int(math.floor(discount * payout))
            return Bid(_affordable(bid, obs))

        if kind in (ActionType.LOAN_10, ActionType.LOAN_20):
            principal = 10 if kind == ActionType.LOAN_10 else 20

            # Loan gives principal now, but you repay principal later; bid is a pure cost.
            # Only worth it if: (a) bid is tiny, and (b) you are cash constrained now.
            cash = obs.me.cash
            constrained = cash <= 3
            if not constrained and not late:
                return Bid(0)

            # If constrained, you might pay 1–2 to gain liquidity.
            # If late, sometimes worth 1 to buy a last gem.
            bid = 2 if constrained else 1
            # Never bid more than a small fraction of principal
            bid = min(bid, max(0, principal // 10))
            return Bid(_affordable(bid, obs))

        return Bid(0)

    def choose_info_to_reveal(self, obs: "GameObservation", result: "AuctionResult") -> str:
        """
        Slightly more nuanced: reveal a suit that (given public reveals) would
        move market beliefs *toward neutrality* rather than swinging prices.
        We approximate by revealing the suit with the smallest absolute deviation
        between:
          our private count for that suit
        and
          the public expected count for that suit among remaining hidden info.
        """
        unrevealed = list(obs.private.info_cards_unrevealed)
        if not unrevealed:
            return obs.private.info_cards_revealed[0].id

        # Compute public known counts and remaining hidden
        total_info = 0
        known: Dict[Suit, int] = {s: 0 for s in Suit}
        for p in obs.public.players:
            total_info += p.unrevealed_info_count + len(p.revealed_info)
            for c in p.revealed_info:
                known[c.suit] += 1
        remaining = max(0, total_info - sum(known.values()))
        exp_each = remaining / len(Suit) if remaining else 0.0

        # Our private counts
        my_counts: Dict[Suit, int] = {s: 0 for s in Suit}
        for c in unrevealed:
            my_counts[c.suit] += 1

        # Choose card whose suit is closest to "neutral" (exp_each) to minimize info impact
        best = min(
            unrevealed,
            key=lambda c: (abs(my_counts[c.suit] - exp_each), my_counts[c.suit], c.id),
        )
        return best.id
