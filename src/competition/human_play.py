from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from src.competition.contracts import (
    AuctionResult,
    ActionType,
    Card,
    GameObservation,
    PocketRocketsBot,
    Suit,
    TwoFunctionBot,
    count_resources,
    legal_max_bid,
)


@dataclass(frozen=True)
class HumanDecisionRequest:
    kind: str
    player_id: int
    prompt: str
    minimum: int = 0
    maximum: int = 0
    options: Tuple[str, ...] = ()
    default: Optional[str] = None


@dataclass(frozen=True)
class HumanDecisionResponse:
    kind: str
    value: str


@dataclass(frozen=True)
class ResourceCardView:
    card_id: str
    suit: str


@dataclass(frozen=True)
class TurnEvent:
    turn_index: int
    action_kind: str
    winner_id: int
    winning_bid: int
    bids_by_player: Mapping[int, int]
    tied_player_ids: Tuple[int, ...]
    awarded_resource_suits: Tuple[str, ...]
    revealed_resource: Optional[ResourceCardView]
    product_claim_ids: Tuple[str, ...]
    priority_marker_before: int
    priority_marker_after: int
    summary: str


@dataclass(frozen=True)
class ProductTileView:
    product_id: str
    name: str
    requirement: Mapping[str, int]
    payout: int
    claimed_by_player_id: Optional[int]
    pattern: Optional[str] = None


@dataclass(frozen=True)
class UiPlayerState:
    player_id: int
    name: str
    cash: int
    resource_counts: Mapping[str, int]
    loan_principal_total: int
    investment_payout_total: int
    product_value_total: int
    revealed_info_count: int
    unrevealed_info_count: int
    private_resources: Tuple[ResourceCardView, ...]
    inventory_resources: Tuple[ResourceCardView, ...]


@dataclass(frozen=True)
class UiState:
    turn_index: int
    action_kind: str
    priority_marker_id: int
    resources_up_for_auction: Tuple[ResourceCardView, ...]
    resource_deck_count: int
    action_deck_count: int
    products_enabled: bool
    active_products: Tuple[ProductTileView, ...]
    value_chart: Tuple[int, ...]
    revealed_resources_by_suit: Mapping[str, Tuple[ResourceCardView, ...]]
    me_player_id: int
    players: Tuple[UiPlayerState, ...]
    turn_events: Tuple[TurnEvent, ...]
    auction_reveal_strip: Optional[TurnEvent]
    status_text: str
    final_scores: Tuple[Tuple[int, str, int], ...] = ()
    game_over: bool = False


class HumanControlBridge:
    def __init__(self):
        self._request_queue: Queue[HumanDecisionRequest] = Queue()
        self._response_queue: Queue[HumanDecisionResponse] = Queue()
        self._state_queue: Queue[UiState] = Queue()

    def request(self, req: HumanDecisionRequest) -> HumanDecisionResponse:
        self._request_queue.put(req)
        return self._response_queue.get()

    def post_response(self, response: HumanDecisionResponse) -> None:
        self._response_queue.put(response)

    def post_state(self, state: UiState) -> None:
        self._state_queue.put(state)

    def poll_request(self) -> Optional[HumanDecisionRequest]:
        if self._request_queue.empty():
            return None
        return self._request_queue.get_nowait()

    def poll_state(self) -> Optional[UiState]:
        if self._state_queue.empty():
            return None
        return self._state_queue.get_nowait()


class HumanInteractiveBot(TwoFunctionBot):
    def __init__(self, bridge: HumanControlBridge, player_label: str = "Human"):
        self._bridge = bridge
        self._label = player_label
        self._status_text = "Game starting..."
        self._turn_events: List[TurnEvent] = []
        self._latest_strip: Optional[TurnEvent] = None

    @property
    def bot_name(self) -> str:
        return self._label

    def _view_card(self, card: Card) -> ResourceCardView:
        return ResourceCardView(card_id=card.id, suit=card.suit.name)

    def _action_deck_remaining(self, obs: GameObservation) -> int:
        remaining = obs.public.action_counts_remaining
        if not remaining:
            return 0
        return int(sum(remaining.values()))

    def _revealed_by_suit(self, obs: GameObservation) -> Mapping[str, Tuple[ResourceCardView, ...]]:
        out: Dict[str, List[ResourceCardView]] = {s.name: [] for s in Suit}
        for p in obs.public.players:
            for card in p.revealed_info:
                out[card.suit.name].append(self._view_card(card))
        return {k: tuple(v) for k, v in out.items()}

    def _post_state(self, obs: GameObservation, *, game_over: bool = False, final_scores: Sequence[Tuple[int, str, int]] = ()) -> None:
        players: List[UiPlayerState] = []
        for p in obs.public.players:
            counts = count_resources(p.resources_owned)
            private_cards = ()
            if p.player_id == obs.me.player_id:
                private_cards = tuple(self._view_card(card) for card in obs.private.info_cards_unrevealed)
            players.append(
                UiPlayerState(
                    player_id=p.player_id,
                    name=p.name,
                    cash=p.cash,
                    resource_counts={s.name: int(counts[s]) for s in Suit},
                    loan_principal_total=sum(loan.principal for loan in p.loans),
                    investment_payout_total=sum(inv.payout for inv in p.investments),
                    product_value_total=sum(prod.payout for prod in p.products),
                    revealed_info_count=len(p.revealed_info),
                    unrevealed_info_count=p.unrevealed_info_count,
                    private_resources=private_cards,
                    inventory_resources=tuple(self._view_card(card) for card in p.resources_owned),
                )
            )
        state = UiState(
            turn_index=obs.context.turn_index,
            action_kind=obs.context.action.kind.value,
            priority_marker_id=obs.context.priority_marker_id,
            resources_up_for_auction=tuple(self._view_card(card) for card in obs.context.upcoming_resources),
            resource_deck_count=obs.context.resource_deck_count,
            action_deck_count=self._action_deck_remaining(obs),
            products_enabled=obs.public.products.enabled,
            active_products=tuple(
                ProductTileView(
                    product_id=prod.id,
                    name=prod.name,
                    requirement={s.name: int(v) for s, v in prod.requirement.items() if int(v) > 0},
                    payout=int(prod.payout),
                    claimed_by_player_id=prod.claimed_by_player_id,
                    pattern=prod.pattern,
                )
                for prod in obs.public.products.active_products
            ),
            value_chart=tuple(int(v) for v in obs.public.value_chart.mapping),
            revealed_resources_by_suit=self._revealed_by_suit(obs),
            me_player_id=obs.me.player_id,
            players=tuple(players),
            turn_events=tuple(self._turn_events[-12:]),
            auction_reveal_strip=self._latest_strip,
            status_text=self._status_text,
            final_scores=tuple(final_scores),
            game_over=game_over,
        )
        self._bridge.post_state(state)

    def choose_bid(self, obs: GameObservation) -> int:
        self._post_state(obs)
        max_bid = legal_max_bid(obs)
        req = HumanDecisionRequest(
            kind="bid",
            player_id=obs.me.player_id,
            prompt=f"Choose bid for {obs.context.action.kind.value} (resources up for auction)",
            minimum=0,
            maximum=max_bid,
            default="0",
        )
        response = self._bridge.request(req)
        try:
            raw = int(response.value)
        except (TypeError, ValueError):
            raw = 0
        return max(0, min(raw, max_bid))

    def choose_card(self, obs: GameObservation, result: AuctionResult) -> str:
        self._post_state(obs)
        available = [c.id for c in obs.private.info_cards_unrevealed]
        fallback = available[0] if available else (obs.private.info_cards_revealed[0].id if obs.private.info_cards_revealed else "")
        if not available:
            return fallback
        req = HumanDecisionRequest(
            kind="reveal",
            player_id=obs.me.player_id,
            prompt="Choose private resource card to reveal publicly in value display",
            options=tuple(available),
            default=fallback,
        )
        response = self._bridge.request(req)
        chosen = response.value
        if chosen not in available:
            return fallback
        return chosen

    def on_auction_resolved(self, obs: GameObservation, result: AuctionResult) -> None:
        bids_map = {pid: int(bid) for pid, bid in enumerate(result.bids or ())}
        max_bid = max(bids_map.values()) if bids_map else 0
        tied = tuple(sorted(pid for pid, amount in bids_map.items() if amount == max_bid))
        revealed_resource: Optional[ResourceCardView] = None
        if result.winner_id >= 0:
            winner_public = next(p for p in obs.public.players if p.player_id == result.winner_id)
            if winner_public.revealed_info:
                last = winner_public.revealed_info[-1]
                revealed_resource = self._view_card(last)
        summary = (
            f"T{result.turn_index} {result.action.kind.value} "
            f"winner=P{result.winner_id if result.winner_id >= 0 else 'None'} bid=${result.winning_bid}"
        )
        event = TurnEvent(
            turn_index=result.turn_index,
            action_kind=result.action.kind.value,
            winner_id=result.winner_id,
            winning_bid=result.winning_bid,
            bids_by_player=bids_map,
            tied_player_ids=tied,
            awarded_resource_suits=tuple(card.suit.name for card in result.auctioned_resources),
            revealed_resource=revealed_resource,
            product_claim_ids=tuple(result.claimed_products),
            priority_marker_before=obs.context.priority_marker_id,
            priority_marker_after=result.new_priority_marker_id,
            summary=summary,
        )
        self._turn_events.append(event)
        self._latest_strip = event
        self._status_text = summary
        self._post_state(obs)

    def on_game_end(self, obs: GameObservation) -> None:
        scores = [(p.player_id, p.name, p.cash) for p in obs.public.players]
        self._status_text = "Game ended. Money totals shown."
        self._post_state(obs, game_over=True, final_scores=tuple(scores))


def safe_private_and_public_bots() -> List[PocketRocketsBot]:
    from src.bots.registry import resolve_bot_specs

    specs = resolve_bot_specs(bot_sources=["public", "private"], include_private=True)
    return [s.factory() for s in specs]


def build_bot_lineup(all_bots: Sequence[PocketRocketsBot], seats_needed: int) -> List[PocketRocketsBot]:
    if seats_needed <= 0:
        return []
    if not all_bots:
        raise ValueError("No bots available to fill seats.")
    out: List[PocketRocketsBot] = []
    index = 0
    while len(out) < seats_needed:
        out.append(all_bots[index % len(all_bots)])
        index += 1
    return out
