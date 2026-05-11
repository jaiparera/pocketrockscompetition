from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .contracts import (
    Action,
    ActionType,
    AuctionResult,
    Bid,
    Card,
    GameObservation,
    GamePublicState,
    InvestmentPosition,
    LoanPosition,
    PlayerPrivateState,
    PlayerPublicState,
    PocketRocketsBot,
    ProductBoardState,
    Suit,
    TurnContext,
    ValueChart,
    count_gems,
)
from .products import PRODUCT_CATALOG, claim_eligible_products_for_winner, owned_from_active, select_products_for_game


@dataclass(frozen=True)
class EngineConfig:
    seed: int = 0
    info_cards_per_player: Optional[Mapping[int, int]] = None
    starting_cash_by_players: Optional[Mapping[int, int]] = None
    gems_per_suit: int = 6
    action_counts: Optional[Mapping[ActionType, int]] = None
    discard_on_all_pass: bool = False
    skip_auction2_if_insufficient_gems: bool = False
    products_enabled: bool = True
    products_per_game: int = 4
    product_catalog_override: Optional[Sequence] = None

    def __post_init__(self):
        object.__setattr__(self, "info_cards_per_player", self.info_cards_per_player or {3: 5, 4: 4, 5: 3})
        object.__setattr__(self, "starting_cash_by_players", self.starting_cash_by_players or {3: 30, 4: 25, 5: 20})
        object.__setattr__(
            self,
            "action_counts",
            self.action_counts
            or {
                ActionType.AUCTION_1: 12,
                ActionType.AUCTION_2: 5,
                ActionType.LOAN_10: 2,
                ActionType.LOAN_20: 2,
                ActionType.INVESTMENT_5: 2,
                ActionType.INVESTMENT_10: 2,
            },
        )


@dataclass
class _PlayerState:
    player_id: int
    name: str
    cash: int
    gems_owned: List[Card]
    loans: List[LoanPosition]
    investments: List[InvestmentPosition]
    products: List
    revealed_info: List[Card]
    unrevealed_info: List[Card]


class PocketRocketsEngine:
    def __init__(self, bots: Sequence[PocketRocketsBot], config: EngineConfig, *, value_chart: ValueChart, bot_names: Optional[Sequence[str]] = None):
        if not (3 <= len(bots) <= 5):
            raise ValueError("PocketRockets supports 3-5 players.")
        self._cfg = config
        self._rng = random.Random(config.seed)
        self._bots = list(bots)
        self._num_players = len(bots)
        names = list(bot_names) if bot_names is not None else [getattr(b, "bot_name", f"Bot{i}") for i, b in enumerate(bots)]
        if len(names) != self._num_players:
            raise ValueError("bot_names length must match bots length.")
        cash = config.starting_cash_by_players[self._num_players]
        self._players = [
            _PlayerState(i, names[i], cash, [], [], [], [], [], [])
            for i in range(self._num_players)
        ]
        self._value_chart = value_chart
        self._gem_draw_pile = self._make_gem_deck(config.gems_per_suit)
        self._action_draw_pile = self._make_action_deck(config.action_counts)
        self._action_discard: List[Action] = []
        self._past_auctions: List[AuctionResult] = []
        self._rng.shuffle(self._gem_draw_pile)
        self._rng.shuffle(self._action_draw_pile)
        self._deal_info_cards(self._gem_draw_pile, config.info_cards_per_player[self._num_players])
        self._info_counts_by_suit_at_start = {s: 0 for s in Suit}
        for p in self._players:
            for c in p.unrevealed_info:
                self._info_counts_by_suit_at_start[c.suit] += 1
        self._upcoming: List[Card] = []
        self._refill_upcoming()
        self._seating_order = tuple(range(self._num_players))
        self._tiebreak_leader_id = self._rng.choice(self._seating_order)
        self._action_counts_remaining = dict(config.action_counts)
        catalog = list(config.product_catalog_override) if config.product_catalog_override else PRODUCT_CATALOG
        self._active_products = select_products_for_game(catalog, rng=self._rng, per_game=config.products_per_game) if config.products_enabled else []

    def _make_gem_deck(self, gems_per_suit: int) -> List[Card]:
        deck: List[Card] = []
        gid = 0
        for suit in Suit:
            for _ in range(gems_per_suit):
                deck.append(Card(id=f"G{gid}", suit=suit))
                gid += 1
        return deck

    def _make_action_deck(self, counts: Mapping[ActionType, int]) -> List[Action]:
        deck: List[Action] = []
        aid = 0
        for kind, n in counts.items():
            for _ in range(n):
                deck.append(Action(id=f"A{aid}", kind=kind))
                aid += 1
        return deck

    def _deal_info_cards(self, gem_deck: List[Card], per_player: int) -> None:
        for i in range(self._num_players):
            for _ in range(per_player):
                self._players[i].unrevealed_info.append(gem_deck.pop())

    def _refill_upcoming(self) -> None:
        while len(self._upcoming) < 2 and self._gem_draw_pile:
            self._upcoming.append(self._gem_draw_pile.pop())

    def _build_public_state(self) -> GamePublicState:
        players = tuple(
            PlayerPublicState(
                player_id=p.player_id,
                name=p.name,
                cash=p.cash,
                gems_owned=tuple(p.gems_owned),
                loans=tuple(p.loans),
                investments=tuple(p.investments),
                products=tuple(p.products),
                revealed_info=tuple(p.revealed_info),
                unrevealed_info_count=len(p.unrevealed_info),
            )
            for p in self._players
        )
        products = ProductBoardState(
            enabled=self._cfg.products_enabled,
            active_products=tuple(self._active_products),
            owned_products_by_player={p.player_id: tuple(p.products) for p in self._players},
        )
        return GamePublicState(
            num_players=self._num_players,
            players=players,
            products=products,
            value_chart=self._value_chart,
            action_discard=tuple(self._action_discard),
            past_auctions=tuple(self._past_auctions),
            action_counts_remaining=dict(self._action_counts_remaining),
        )

    def _build_obs(self, player_id: int, turn_index: int, action: Action) -> GameObservation:
        public = self._build_public_state()
        private = PlayerPrivateState(
            player_id=player_id,
            info_cards_unrevealed=tuple(self._players[player_id].unrevealed_info),
            info_cards_revealed=tuple(self._players[player_id].revealed_info),
        )
        context = TurnContext(turn_index, action, tuple(self._upcoming), len(self._gem_draw_pile), self._tiebreak_leader_id, self._seating_order)
        me = next(p for p in public.players if p.player_id == player_id)
        return GameObservation(public=public, private=private, context=context, me=me)

    def _tie_break_winner(self, tied_ids: List[int], leader_id: int) -> int:
        order = list(self._seating_order)
        leader_idx = order.index(leader_id)
        scan = order[leader_idx + 1 :] + order[: leader_idx + 1]
        for pid in scan:
            if pid in tied_ids:
                return pid
        return tied_ids[0]

    def _resolve_winner(self, bids: List[int]) -> Tuple[int, int]:
        max_bid = max(bids)
        tied = [pid for pid, b in enumerate(bids) if b == max_bid]
        if max_bid == 0 and self._cfg.discard_on_all_pass:
            return -1, 0
        if len(tied) == 1:
            return tied[0], max_bid
        return self._tie_break_winner(tied, self._tiebreak_leader_id), max_bid

    def _collect_bids(self, turn_index: int, action: Action) -> List[int]:
        bids = [0] * self._num_players
        for pid, bot in enumerate(self._bots):
            try:
                out = bot.get_bid(self._build_obs(pid, turn_index, action))
                amt = int(out.bid_amount)
            except Exception:
                amt = 0
            if amt < 0 or amt > self._players[pid].cash:
                amt = 0
            bids[pid] = amt
        return bids

    def _reveal_on_win(self, winner_id: int, turn_index: int, action: Action, result: AuctionResult) -> None:
        if winner_id < 0:
            return
        p = self._players[winner_id]
        if not p.unrevealed_info:
            return
        try:
            chosen = str(self._bots[winner_id].choose_info_to_reveal(self._build_obs(winner_id, turn_index, action), result))
        except Exception:
            chosen = ""
        idx = next((i for i, c in enumerate(p.unrevealed_info) if c.id == chosen), 0)
        p.revealed_info.append(p.unrevealed_info.pop(idx))

    def _compute_score(self, p: _PlayerState) -> int:
        total = p.cash
        for g in p.gems_owned:
            idx = min(self._info_counts_by_suit_at_start[g.suit], len(self._value_chart.mapping) - 1)
            total += self._value_chart.mapping[idx]
        for inv in p.investments:
            total += inv.payout + inv.locked
        for loan in p.loans:
            total -= loan.principal
        total += sum(prod.payout for prod in p.products)
        return int(total)

    def play(self) -> Dict[str, object]:
        turn_index = 0
        started = False
        while True:
            if len(self._upcoming) == 0 and len(self._gem_draw_pile) == 0:
                break
            if not self._action_draw_pile:
                if not self._action_discard:
                    break
                self._action_draw_pile = self._action_discard[:]
                self._action_discard = []
                self._rng.shuffle(self._action_draw_pile)
            action = self._action_draw_pile.pop()
            self._action_discard.append(action)
            self._action_counts_remaining[action.kind] = max(0, self._action_counts_remaining.get(action.kind, 0) - 1)
            if action.kind == ActionType.AUCTION_1 and len(self._upcoming) < 1:
                continue
            if action.kind == ActionType.AUCTION_2 and self._cfg.skip_auction2_if_insufficient_gems and len(self._upcoming) < 2:
                continue
            if not started:
                for pid, bot in enumerate(self._bots):
                    try:
                        bot.on_game_start(self._build_obs(pid, turn_index, action))
                    except Exception:
                        pass
                started = True
            bids = self._collect_bids(turn_index, action)
            winner_id, winning_bid = self._resolve_winner(bids)
            new_leader = self._tiebreak_leader_id if winner_id < 0 else winner_id
            if winner_id >= 0:
                self._players[winner_id].cash -= winning_bid
            auctioned: List[Card] = []
            claimed_ids: List[str] = []
            if action.kind == ActionType.AUCTION_1:
                gem = self._upcoming.pop(0)
                auctioned.append(gem)
                if winner_id >= 0:
                    self._players[winner_id].gems_owned.append(gem)
                    if self._cfg.products_enabled:
                        counts = count_gems(self._players[winner_id].gems_owned)
                        claimed = claim_eligible_products_for_winner(self._active_products, winner_id, counts)
                        for prod in claimed:
                            self._players[winner_id].products.append(owned_from_active(prod))
                            claimed_ids.append(prod.id)
                self._refill_upcoming()
            elif action.kind == ActionType.AUCTION_2:
                gems = [self._upcoming.pop(0)]
                if self._upcoming:
                    gems.append(self._upcoming.pop(0))
                auctioned.extend(gems)
                if winner_id >= 0:
                    self._players[winner_id].gems_owned.extend(gems)
                    if self._cfg.products_enabled:
                        counts = count_gems(self._players[winner_id].gems_owned)
                        claimed = claim_eligible_products_for_winner(self._active_products, winner_id, counts)
                        for prod in claimed:
                            self._players[winner_id].products.append(owned_from_active(prod))
                            claimed_ids.append(prod.id)
                self._refill_upcoming()
            elif action.kind in (ActionType.LOAN_10, ActionType.LOAN_20):
                if winner_id >= 0:
                    principal = 10 if action.kind == ActionType.LOAN_10 else 20
                    self._players[winner_id].cash += principal
                    self._players[winner_id].loans.append(LoanPosition(id=f"L{turn_index}", principal=principal, winning_bid=winning_bid))
            elif action.kind in (ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
                if winner_id >= 0:
                    payout = 5 if action.kind == ActionType.INVESTMENT_5 else 10
                    self._players[winner_id].investments.append(InvestmentPosition(id=f"I{turn_index}", payout=payout, locked=winning_bid))
            result = AuctionResult(turn_index, action, winner_id, winning_bid, tuple(auctioned), new_leader, tuple(claimed_ids), tuple(bids))
            self._tiebreak_leader_id = new_leader
            self._past_auctions.append(result)
            for pid, bot in enumerate(self._bots):
                try:
                    bot.on_auction_resolved(self._build_obs(pid, turn_index, action), result)
                except Exception:
                    pass
            self._reveal_on_win(winner_id, turn_index, action, result)
            turn_index += 1
        final_public = self._build_public_state()
        for pid, bot in enumerate(self._bots):
            try:
                bot.on_game_end(
                    GameObservation(
                        public=final_public,
                        private=PlayerPrivateState(pid, tuple(self._players[pid].unrevealed_info), tuple(self._players[pid].revealed_info)),
                        context=TurnContext(turn_index, Action(id="END", kind=ActionType.AUCTION_1), tuple(self._upcoming), len(self._gem_draw_pile), self._tiebreak_leader_id, self._seating_order),
                        me=next(p for p in final_public.players if p.player_id == pid),
                    )
                )
            except Exception:
                pass
        scores = [(p.player_id, p.name, self._compute_score(p)) for p in self._players]
        scores.sort(key=lambda x: x[2], reverse=True)
        return {"final_scores": scores, "winner_id": scores[0][0] if scores else -1, "history": tuple(self._past_auctions), "final_public_state": final_public}

