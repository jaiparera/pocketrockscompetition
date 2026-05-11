from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


class Suit(Enum):
    RUBY = auto()
    SAPPHIRE = auto()
    EMERALD = auto()
    AMETHYST = auto()
    DIAMOND = auto()


@dataclass(frozen=True)
class Card:
    id: str
    suit: Suit


class ActionType(str, Enum):
    AUCTION_1 = "AUCTION_1"
    AUCTION_2 = "AUCTION_2"
    LOAN_10 = "LOAN_10"
    LOAN_20 = "LOAN_20"
    INVESTMENT_5 = "INVESTMENT_5"
    INVESTMENT_10 = "INVESTMENT_10"


@dataclass(frozen=True)
class Action:
    id: str
    kind: ActionType


@dataclass(frozen=True)
class LoanPosition:
    id: str
    principal: int
    winning_bid: int


@dataclass(frozen=True)
class InvestmentPosition:
    id: str
    payout: int
    locked: int


@dataclass(frozen=True)
class ProductDefinition:
    id: str
    name: str
    requirement: Mapping[Suit, int]
    payout: int
    pattern: Optional[str] = None


@dataclass(frozen=True)
class ActiveProduct(ProductDefinition):
    claimed_by_player_id: Optional[int] = None


@dataclass(frozen=True)
class OwnedProduct(ProductDefinition):
    pass


@dataclass(frozen=True)
class ValueChart:
    mapping: List[int]


@dataclass(frozen=True)
class PlayerPublicState:
    player_id: int
    name: str
    cash: int
    gems_owned: Tuple[Card, ...]
    loans: Tuple[LoanPosition, ...]
    investments: Tuple[InvestmentPosition, ...]
    products: Tuple[OwnedProduct, ...]
    revealed_info: Tuple[Card, ...]
    unrevealed_info_count: int


@dataclass(frozen=True)
class PlayerPrivateState:
    player_id: int
    info_cards_unrevealed: Tuple[Card, ...]
    info_cards_revealed: Tuple[Card, ...]


@dataclass(frozen=True)
class TurnContext:
    turn_index: int
    action: Action
    upcoming_gems: Tuple[Card, ...]
    biddable_pile_count: int
    tiebreak_leader_id: int
    seating_order: Tuple[int, ...]


@dataclass(frozen=True)
class ProductBoardState:
    enabled: bool
    active_products: Tuple[ActiveProduct, ...]
    owned_products_by_player: Mapping[int, Tuple[OwnedProduct, ...]]


@dataclass(frozen=True)
class AuctionResult:
    turn_index: int
    action: Action
    winner_id: int
    winning_bid: int
    auctioned_gems: Tuple[Card, ...]
    new_tiebreak_leader_id: int
    claimed_products: Tuple[str, ...]
    bids: Optional[Tuple[int, ...]] = None


@dataclass(frozen=True)
class GamePublicState:
    num_players: int
    players: Tuple[PlayerPublicState, ...]
    products: ProductBoardState
    value_chart: ValueChart
    action_discard: Tuple[Action, ...]
    past_auctions: Tuple[AuctionResult, ...]
    action_counts_remaining: Optional[Mapping[ActionType, int]] = None


@dataclass(frozen=True)
class GameObservation:
    public: GamePublicState
    private: PlayerPrivateState
    context: TurnContext
    me: PlayerPublicState


@dataclass(frozen=True)
class Bid:
    bid_amount: int


class PocketRocketsBot(ABC):
    @property
    @abstractmethod
    def bot_name(self) -> str:
        raise NotImplementedError

    def on_game_start(self, obs: GameObservation) -> None:
        return None

    @abstractmethod
    def get_bid(self, obs: GameObservation) -> Bid:
        raise NotImplementedError

    def on_auction_resolved(self, obs: GameObservation, result: AuctionResult) -> None:
        return None

    @abstractmethod
    def choose_info_to_reveal(self, obs: GameObservation, result: AuctionResult) -> str:
        raise NotImplementedError

    def on_game_end(self, obs: GameObservation) -> None:
        return None


class TwoFunctionBot(PocketRocketsBot):
    @property
    @abstractmethod
    def bot_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def choose_bid(self, obs: GameObservation) -> int:
        raise NotImplementedError

    @abstractmethod
    def choose_card(self, obs: GameObservation, result: AuctionResult) -> str:
        raise NotImplementedError

    def get_bid(self, obs: GameObservation) -> Bid:
        return Bid(int(self.choose_bid(obs)))

    def choose_info_to_reveal(self, obs: GameObservation, result: AuctionResult) -> str:
        return self.choose_card(obs, result)


def get_player(public: GamePublicState, player_id: int) -> PlayerPublicState:
    for p in public.players:
        if p.player_id == player_id:
            return p
    raise KeyError(f"player_id {player_id} not found")


def legal_max_bid(obs: GameObservation) -> int:
    return max(0, obs.me.cash)


def count_gems(cards: Iterable[Card]) -> Dict[Suit, int]:
    out: Dict[Suit, int] = {s: 0 for s in Suit}
    for c in cards:
        out[c.suit] += 1
    return out


def count_owned_gems(cards: Sequence[Card]) -> Dict[Suit, int]:
    return count_gems(cards)
