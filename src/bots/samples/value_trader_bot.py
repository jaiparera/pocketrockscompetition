from __future__ import annotations

from src.competition.contracts import ActionType, AuctionResult, GameObservation, TwoFunctionBot, legal_max_bid


class ValueTraderBot(TwoFunctionBot):
    def __init__(self, risk: float = 0.9):
        self.risk = float(risk)

    @property
    def bot_name(self) -> str:
        return f"ValueTrader(r={self.risk:.2f})"

    def _value_for_suit(self, obs: GameObservation, suit_name: str) -> int:
        counts = 0
        for g in obs.me.gems_owned:
            if g.suit.name == suit_name:
                counts += 1
        idx = min(counts + 1, len(obs.public.value_chart.mapping) - 1)
        current = obs.public.value_chart.mapping[min(counts, len(obs.public.value_chart.mapping) - 1)]
        next_val = obs.public.value_chart.mapping[idx]
        return max(0, next_val - current)

    def choose_bid(self, obs: GameObservation) -> int:
        max_bid = legal_max_bid(obs)
        if max_bid <= 0 or not obs.context.upcoming_gems:
            return 0

        target = obs.context.upcoming_gems[0]
        est_value = self._value_for_suit(obs, target.suit.name)
        base = int(round(est_value * self.risk))

        if obs.context.action.kind in (ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
            payout = 5 if obs.context.action.kind == ActionType.INVESTMENT_5 else 10
            base = int(round(min(payout, payout * (0.65 + (0.2 * min(self.risk, 1.0))))))
        if obs.context.action.kind in (ActionType.LOAN_10, ActionType.LOAN_20):
            base = 1 if max_bid > 0 else 0

        return max(0, min(max_bid, base))

    def choose_card(self, obs: GameObservation, result: AuctionResult) -> str:
        if not obs.private.info_cards_unrevealed:
            return obs.private.info_cards_revealed[0].id
        return sorted(obs.private.info_cards_unrevealed, key=lambda c: c.id)[0].id
