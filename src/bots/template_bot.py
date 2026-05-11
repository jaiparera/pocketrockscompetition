from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from src.competition.contracts import AuctionResult, GameObservation, Suit, TwoFunctionBot, legal_max_bid


@dataclass(frozen=True)
class TemplateConfig:
    mode: str = "heuristic"  # heuristic | stats | model
    max_risk_fraction: float = 0.25
    stats_weight: float = 0.20
    model_path: Optional[str] = None


class TemplateBot(TwoFunctionBot):
    """
    Single flexible scaffold for:
    - handcrafted heuristic logic
    - lightweight statistics-based logic
    - model-backed logic (optional artifact load)
    """

    def __init__(self, config: Optional[TemplateConfig] = None):
        self.config = config or TemplateConfig()
        self._model_bias = self._load_model_bias(self.config.model_path)

    @property
    def bot_name(self) -> str:
        return f"Template[{self.config.mode}]"

    def _load_model_bias(self, model_path: Optional[str]) -> float:
        if not model_path:
            return 0.0
        path = Path(model_path)
        if not path.exists():
            return 0.0
        try:
            return float(path.read_text(encoding="utf-8").strip())
        except Exception:
            return 0.0

    def _suit_counts(self, obs: GameObservation) -> Dict[Suit, int]:
        counts = {s: 0 for s in Suit}
        for c in obs.me.gems_owned:
            counts[c.suit] += 1
        return counts

    def _heuristic_bid(self, obs: GameObservation) -> int:
        max_bid = legal_max_bid(obs)
        if max_bid <= 0:
            return 0
        base = int(max_bid * self.config.max_risk_fraction)
        return max(0, min(max_bid, base))

    def _stats_adjustment(self, obs: GameObservation) -> int:
        if not obs.context.upcoming_gems:
            return 0
        counts = self._suit_counts(obs)
        target = obs.context.upcoming_gems[0].suit
        rarity_signal = max(0, 3 - counts[target])
        return int(rarity_signal * self.config.stats_weight * 2)

    def _model_adjustment(self, obs: GameObservation) -> int:
        if self.config.mode != "model":
            return 0
        return int(round(self._model_bias))

    def choose_bid(self, obs: GameObservation) -> int:
        max_bid = legal_max_bid(obs)
        if max_bid <= 0:
            return 0
        bid = self._heuristic_bid(obs)
        if self.config.mode in ("stats", "model"):
            bid += self._stats_adjustment(obs)
        bid += self._model_adjustment(obs)
        return max(0, min(max_bid, bid))

    def choose_card(self, obs: GameObservation, result: AuctionResult) -> str:
        if not obs.private.info_cards_unrevealed:
            return obs.private.info_cards_revealed[0].id
        # Keep more diverse info hidden by revealing duplicate suits first.
        suit_counts = {}
        for c in obs.private.info_cards_unrevealed:
            suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        reveal = sorted(
            obs.private.info_cards_unrevealed,
            key=lambda c: (-suit_counts[c.suit], c.id),
        )[0]
        return reveal.id

