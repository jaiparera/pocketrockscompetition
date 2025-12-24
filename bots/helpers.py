from competition.interface import *
from competition.simulator import BotEntry

# -----------------------------
# Small helpers for bots
# -----------------------------

def _my_id(obs: "GameObservation") -> int:
    return obs.private.player_id


def _suit_value(obs: "GameObservation", suit: "Suit") -> int:
    """
    Expected per-gem value from chart given current revealed info.
    We approximate unknown info using the prior mean of remaining counts.
    This keeps bots simple but not totally dumb.
    """
    chart = obs.public.value_chart.mapping

    # Total info cards dealt at start is known: unrevealed counts are explicit.
    total_info = 0
    for p in obs.public.players:
        total_info += p.unrevealed_info_count + len(p.revealed_info)

    # Known revealed counts by suit (public)
    known: Dict[Suit, int] = {s: 0 for s in Suit}
    for p in obs.public.players:
        for c in p.revealed_info:
            known[c.suit] += 1

    known_total = sum(known.values())
    remaining = max(0, total_info - known_total)

    # If nothing remains hidden, use exact
    if remaining == 0:
        idx = known[suit]
        if idx < 0:
            idx = 0
        if idx >= len(chart):
            idx = len(chart) - 1
        return int(chart[idx])

    # Simple Bayesian-ish smoothing: distribute remaining equally among suits.
    # E[count_suit] = known + remaining/5
    exp_count = known[suit] + (remaining / len(Suit))
    idx = int(round(exp_count))
    idx = max(0, min(idx, len(chart) - 1))
    return int(chart[idx])


def _bundle_value(obs: "GameObservation", cards: Tuple["Card", ...]) -> int:
    return sum(_suit_value(obs, c.suit) for c in cards)


def _best_trinket_bonus_if_win(obs: "GameObservation", gained: Tuple["Card", ...]) -> int:
    """
    Approximate immediate trinket gain if we win and add gained cards.
    Assumes we might claim multiple; uses actual objective_satisfied helper.
    """
    me_pub = obs.me
    after = list(me_pub.gems_owned) + list(gained)

    bonus = 0
    for ts in obs.public.trinkets:
        if ts.claimed_by is not None:
            continue
        if objective_satisfied(ts.objective, after):
            bonus += ts.objective.points
    return bonus


def _affordable(bid: int, obs: "GameObservation") -> int:
    return max(0, min(int(bid), legal_max_bid(obs)))


def _current_item(obs: "GameObservation") -> Tuple[Tuple["Card", ...], str]:
    """Returns (auctioned_cards, kind_string)."""
    kind = obs.context.action.kind
    up = obs.context.upcoming_gems
    if kind == ActionType.AUCTION_1:
        return (tuple(up[:1]), "GEMS")
    if kind == ActionType.AUCTION_2:
        return (tuple(up[:2]), "GEMS")
    if kind in (ActionType.LOAN_10, ActionType.LOAN_20):
        return (tuple(), "LOAN")
    if kind in (ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
        return (tuple(), "INVEST")
    return (tuple(), "OTHER")